"""Retriever — fan-out to Cortex Search Services and Cortex Analyst.

Given a ``QueryClass``, the retriever picks one or more retrieval surfaces:

* ``concept``           → ``TUTOR_SEARCH``
* ``solution_lookup``   → ``SOLUTIONS_SEARCH``
* ``summary_request``   → ``SUMMARY_SEARCH``
* ``analytical``        → Cortex Analyst REST endpoint
* ``image_extracted``   → same as ``concept`` (extraction has already happened)
* ``ambiguous``         → all three Cortex Search Services + Analyst, in parallel

Snowflake connections are pooled and reused — opening one per request burns
~150ms on the TCP / TLS / auth dance, which is more than the search query
itself. See :class:`SnowflakeConnectionPool`.

All Snowflake / HTTP calls are routed through injectable seams so tests can
swap them out for fakes without monkey-patching imports.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

import httpx

from .contract import (
    Citation,
    QueryClass,
    RetrievalResult,
    RetrievedChunk,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TUTOR_SEARCH = "GKTUITION_TUTOR.CORTEX.TUTOR_SEARCH"
SOLUTIONS_SEARCH = "GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH"
SUMMARY_SEARCH = "GKTUITION_TUTOR.CORTEX.SUMMARY_SEARCH"

ANALYST_SEMANTIC_MODEL_FILE = (
    "@GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE/semantic_model.yaml"
)

TOP_K = 5
# A single exam question has many sub-parts (a, b(i), b(ii), c(i)…); keep more
# of them for solution-lookup so the full worked solution reaches the model.
SOLUTIONS_TOP_K = 12

# Sub-floor below which retrieval is considered too weak to ground an answer.
# Tuned per the eval set's auto-easy precision floor — eval reports below
# this score on a row are essentially noise.
RETRIEVAL_FLOOR = 0.30


# ---------------------------------------------------------------------------
# Blended-score post-rank (Algebra precision@1 tuning, DAY_31)
# ---------------------------------------------------------------------------
#
# Default weights for the optional ``_blended_score`` re-rank. The formula
# is::
#
#     blended = w_r * sigmoid(reranker) + w_c * cosine + w_t * text_match
#
# where ``sigmoid(reranker)`` is the same calibration the standalone
# ``_normalise_score`` path uses, so blended outputs land in ``[0, 1]`` and
# remain directly comparable with ``RETRIEVAL_FLOOR``.
#
# The starting-point weights were chosen from the AGENT_16 failure-inspector
# analysis on the locked Phase-1 baseline (see
# ``eval/algebra_tuning_DAY_31.md``): the dominant Algebra fail mode is
# close-cousin within-strand confusion where the reranker semantic signal
# is the only one that can disambiguate, so ``w_r`` carries the bulk of
# the weight. ``cosine`` adds a topical-prior nudge for the small number
# of rows where the reranker ranks two semantically-close candidates
# tightly; ``text_match`` carries the least weight because boilerplate
# overlap is *causing* several of the within-strand misranks rather than
# resolving them.
BLENDED_WEIGHT_RERANKER = float(os.environ.get("BLENDED_WEIGHT_RERANKER", "0.6"))
BLENDED_WEIGHT_COSINE = float(os.environ.get("BLENDED_WEIGHT_COSINE", "0.3"))
BLENDED_WEIGHT_TEXT_MATCH = float(os.environ.get("BLENDED_WEIGHT_TEXT_MATCH", "0.1"))


def _blended_scoring_enabled() -> bool:
    """Feature-flag gate. Defaults to OFF so the helper can land + be
    test-covered without changing live ranking behaviour.

    Flip via ``BLENDED_SCORING_ENABLED=true`` (any of: ``true``, ``1``,
    ``yes`` — matches the convention used elsewhere in the firewall code).
    Read on every call rather than at import time so a test or a Fly
    secret-flip takes effect without a service restart.
    """
    raw = os.environ.get("BLENDED_SCORING_ENABLED", "").strip().lower()
    return raw in ("true", "1", "yes", "on")


# ---------------------------------------------------------------------------
# Connection-pool seams
# ---------------------------------------------------------------------------


class SnowflakeCursor(Protocol):
    """Subset of the connector cursor we actually use."""

    description: Any  # list[tuple] | None — set by execute()

    def execute(self, sql: str, params: Any | None = ...) -> Any: ...
    def fetchone(self) -> Any: ...
    def fetchall(self) -> list[Any]: ...
    def close(self) -> None: ...


class SnowflakeConnection(Protocol):
    def cursor(self) -> SnowflakeCursor: ...
    def close(self) -> None: ...


# Module-level connection (single-pool, single-process). Replaced under test.
_snowflake_connection: SnowflakeConnection | None = None
_snowflake_lock = Lock()


def set_snowflake_connection(conn: SnowflakeConnection | None) -> None:
    """Inject a Snowflake connection at app startup or in tests.

    Pass ``None`` at teardown to clear the pool.
    """
    global _snowflake_connection
    _snowflake_connection = conn


def _sf_env(*names: str) -> str | None:
    """Return the first non-empty value among ``names`` from the environment.

    Lets the orchestrator accept either the canonical ``SNOWFLAKE_*``
    prefix (used by the loaders, the connector docs, and local dev) or
    the ``SF_*`` prefix that ``scripts/setup_fly_secrets.sh`` (Agent 12)
    pushes to Fly. Pattern mirrors ``api/routes/health.py``'s defensive
    ``SNOWFLAKE_ACCOUNT or SF_ACCOUNT`` reads.
    """
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def _get_or_open_snowflake() -> SnowflakeConnection:
    """Lazy-open the Snowflake connection on first use.

    Reads ``SNOWFLAKE_*`` env vars per the convention used across all the
    sister agents' loaders, with a fallback to ``SF_*`` for compatibility
    with ``scripts/setup_fly_secrets.sh`` (Agent 12), which pushes the
    Fly-side secrets under the user's local ``~/.zprofile`` naming
    (``SF_USER``, ``SF_ACCOUNT``, ``SF_PRIVATE_KEY``, …). The same dual-read
    pattern already lives in ``api/routes/health.py`` (lines 164, 206);
    this brings the orchestrator into line with it. The two conventions
    should be unified in a future cleanup — see the DAY_27 punchlist —
    but until then this dual-read keeps the live deploy working.
    Raises if neither password nor private-key auth is configured —
    there is no silent fallback.
    """
    global _snowflake_connection
    if _snowflake_connection is not None:
        return _snowflake_connection

    with _snowflake_lock:
        if _snowflake_connection is not None:
            return _snowflake_connection

        import snowflake.connector

        account = _sf_env("SNOWFLAKE_ACCOUNT", "SF_ACCOUNT")
        user = _sf_env("SNOWFLAKE_USER", "SF_USER")
        if not account or not user:
            raise RuntimeError(
                "SNOWFLAKE_ACCOUNT / SF_ACCOUNT and SNOWFLAKE_USER / SF_USER "
                "must be set to open a Cortex connection."
            )
        kw: dict[str, Any] = {
            "account": account,
            "user": user,
            # Omit if unset — Snowflake then uses the user's DEFAULT_ROLE,
            # which we set to GKTUITION_APP_RW on the service account.
            # Defaulting to ACCOUNTADMIN here was dangerous AND broken in
            # production: the service account can't USE ACCOUNTADMIN
            # (least-privilege), so an unset SNOWFLAKE_ROLE env var on a
            # future deploy would silently fail auth instead of falling
            # through to the user's intended role.
            "role": _sf_env("SNOWFLAKE_ROLE", "SF_ROLE"),
            "warehouse": (
                _sf_env("SNOWFLAKE_WAREHOUSE", "SF_WAREHOUSE") or "WH_TUTOR"
            ),
            "database": (
                _sf_env("SNOWFLAKE_DATABASE", "SF_DATABASE")
                or "GKTUITION_TUTOR"
            ),
            "schema": _sf_env("SNOWFLAKE_SCHEMA", "SF_SCHEMA") or "CORTEX",
            "client_session_keep_alive": True,
        }
        if pk_path := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
            # Path-based PEM key (local dev or the path-style sister
            # loaders' convention).
            kw["private_key_file"] = pk_path
            kw["authenticator"] = os.environ.get(
                "SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT"
            )
        elif raw_pk := os.environ.get("SF_PRIVATE_KEY"):
            # Agent 12's setup_fly_secrets.sh materialises the contents of
            # ``$SF_PRIVATE_KEY_PATH`` (a local .p8 PEM file) into the
            # ``SF_PRIVATE_KEY`` env var before pushing it to Fly. Snowflake's
            # connector prefers a path for PEM keys (the raw ``private_key=``
            # kwarg wants DER bytes), so we write the PEM content to a
            # short-lived temp file at startup and hand the path over.
            import tempfile

            fd, tmp_pk_path = tempfile.mkstemp(suffix=".p8", prefix="sf_pk_")
            try:
                os.write(fd, raw_pk.encode("utf-8"))
            finally:
                os.close(fd)
            kw["private_key_file"] = tmp_pk_path
            kw["authenticator"] = os.environ.get(
                "SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT"
            )
        elif password := _sf_env("SNOWFLAKE_PASSWORD", "SF_PASSWORD"):
            kw["password"] = password
        else:
            raise RuntimeError(
                "Snowflake auth missing — set one of: "
                "SNOWFLAKE_PRIVATE_KEY_PATH (path to PEM key), "
                "SF_PRIVATE_KEY (PEM key contents, used by Fly deploy), "
                "or SNOWFLAKE_PASSWORD / SF_PASSWORD."
            )
        _snowflake_connection = snowflake.connector.connect(**kw)
        logger.info("Opened pooled Snowflake connection (account=%s)", account)
        return _snowflake_connection


@contextmanager
def _cursor() -> Iterator[SnowflakeCursor]:
    conn = _get_or_open_snowflake()
    cs = conn.cursor()
    try:
        yield cs
    finally:
        cs.close()


# ---------------------------------------------------------------------------
# Cortex Analyst HTTP seam — injectable
# ---------------------------------------------------------------------------


AnalystCaller = Callable[[str], "AnalystResponse"]
_analyst_caller: AnalystCaller | None = None


@dataclass(frozen=True)
class AnalystResponse:
    """Subset of the Cortex Analyst response we use.

    ``sql`` is the generated SQL; ``rows`` is what we get back after the
    orchestrator executes that SQL against the warehouse (the Analyst REST
    endpoint returns SQL, not rows — we do the execution step ourselves so
    the result lands in the same query log as everything else).
    """

    sql: str
    rows: list[dict[str, Any]]
    natural_language_response: str | None = None


def set_analyst_caller(fn: AnalystCaller | None) -> None:
    global _analyst_caller
    _analyst_caller = fn


def _default_analyst_caller(question: str) -> AnalystResponse:
    """Call the Cortex Analyst REST endpoint and execute the returned SQL.

    Endpoint: ``https://<account>.snowflakecomputing.com/api/v2/cortex/analyst/message``
    Auth: ``Authorization: Bearer <PAT>``.

    The endpoint returns a streamed JSON document whose ``message.content[]``
    array contains both a natural-language answer and one or more SQL
    statements. We extract the first ``type='sql'`` block, execute it against
    the warehouse, and return rows alongside the SQL for logging.
    """
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    pat = os.environ.get("SNOWFLAKE_PAT") or os.environ.get("SNOWFLAKE_PASSWORD")
    if not account or not pat:
        raise RuntimeError(
            "SNOWFLAKE_ACCOUNT and SNOWFLAKE_PAT (or _PASSWORD) must be set "
            "to call Cortex Analyst."
        )
    url = f"https://{account}.snowflakecomputing.com/api/v2/cortex/analyst/message"
    payload = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
        "semantic_model_file": ANALYST_SEMANTIC_MODEL_FILE,
    }
    headers = {
        "Authorization": f"Bearer {pat}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        body = r.json()

    sql: str = ""
    nl: str | None = None
    for block in (body.get("message") or {}).get("content") or []:
        if block.get("type") == "sql" and not sql:
            sql = (block.get("statement") or block.get("sql") or "").strip()
        elif block.get("type") == "text" and nl is None:
            nl = block.get("text")
    if not sql:
        return AnalystResponse(sql="", rows=[], natural_language_response=nl)

    # Execute the SQL on the same warehouse the Search Services use.
    rows: list[dict[str, Any]] = []
    with _cursor() as cs:
        cs.execute(sql)
        cols = [d[0] for d in (cs.description or [])]
        for r_row in cs.fetchall() or []:
            rows.append(dict(zip(cols, r_row)))
    return AnalystResponse(sql=sql, rows=rows, natural_language_response=nl)


def _call_analyst(question: str) -> AnalystResponse:
    fn = _analyst_caller or _default_analyst_caller
    return fn(question)


# ---------------------------------------------------------------------------
# Cortex Search Preview
# ---------------------------------------------------------------------------


def _search_preview(
    service_fqn: str,
    query: str,
    columns: list[str],
    limit: int = TOP_K,
    filter_obj: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Wrap ``SNOWFLAKE.CORTEX.SEARCH_PREVIEW`` against ``service_fqn``.

    Mirrors the call shape used by ``score_against_cortex_search.py`` so the
    query path is row-by-row compatible with the eval scorer — feeding a
    row from the scorer through this retriever and through the eval CSV
    independently should produce the same top-K slug list.
    """
    payload: dict[str, Any] = {"query": query, "columns": columns, "limit": limit}
    if filter_obj:
        payload["filter"] = filter_obj
    with _cursor() as cs:
        cs.execute(
            """
            SELECT PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(%s, %s)
            ):results::ARRAY AS top_hits
            """,
            (service_fqn, json.dumps(payload)),
        )
        raw = cs.fetchone()
    if not raw or raw[0] is None:
        return []
    results = raw[0]
    if isinstance(results, str):
        results = json.loads(results)
    return list(results)


# ---------------------------------------------------------------------------
# Per-service retrievers — synchronous helpers, wrapped in asyncio.to_thread
# ---------------------------------------------------------------------------


def _from_tutor_search(query: str) -> tuple[list[RetrievedChunk], list[Citation]]:
    hits = _search_preview(
        TUTOR_SEARCH, query, columns=["slug", "title", "body", "topic"]
    )
    chunks: list[RetrievedChunk] = []
    citations: list[Citation] = []
    for h in hits:
        slug = str(h.get("slug") or "")
        if not slug:
            continue
        snippet = _shorten(h.get("body") or h.get("title") or "", 600)
        score = _normalise_score(h)
        chunks.append(RetrievedChunk(slug=slug, snippet=snippet, score=score))
        citations.append(
            Citation(
                slug=slug,
                title=str(h.get("title") or slug),
                timestamp_seconds=h.get("timestamp_seconds"),
                score=score,
            )
        )
    return chunks, citations


def _parse_paper_ref(query: str) -> dict[str, int]:
    """Extract {year, paper, question_number} from a paper-specific query.

    e.g. "I'm stuck on 2024 P2 Q7(a)" → {year:2024, paper:2, question_number:7}.
    Year/paper/question are stored as metadata on EXAM_PARTS (not in the
    searchable solution text), so we turn them into a Cortex Search filter to
    target the exact question rather than relying on weak topical similarity.
    """
    ql = query.lower()
    ref: dict[str, object] = {}
    m = re.search(r"\b(?:19|20)\d{2}\b", query)
    if m:
        ref["year"] = int(m.group(0))
    m = re.search(r"\b(?:p|paper)\s*([12])\b", ql)
    if m:
        ref["paper"] = int(m.group(1))
    m = re.search(r"\bq(?:uestion)?\s*0*(\d+)", ql)
    if m:
        ref["question_number"] = int(m.group(1))
    # Default to the main sitting for a specific-paper query unless the student
    # explicitly says deferred/DF (avoids mixing main + deferred Q7s).
    if "year" in ref:
        ref["sitting"] = "df" if re.search(r"\bdeferred\b|\bdf\b", ql) else "main"
    return ref


def _from_solutions_search(query: str) -> tuple[list[RetrievedChunk], list[Citation]]:
    # When the student names a specific paper (year/paper/question), filter the
    # index to exactly that question — the reference lives in metadata, not the
    # searchable text, so an unfiltered semantic search ranks it poorly.
    ref = _parse_paper_ref(query)
    filter_obj: dict[str, Any] | None = None
    if ref:
        conds = [{"@eq": {k: v}} for k, v in ref.items()]
        filter_obj = conds[0] if len(conds) == 1 else {"@and": conds}

    hits = _search_preview(
        SOLUTIONS_SEARCH,
        query,
        columns=["part_id", "topic", "question_text", "solution_text", "tutorials_referenced"],
        filter_obj=filter_obj,
        # Pull every sub-part of the question, not just the global top-5, so the
        # complete worked solution is in the evidence.
        limit=SOLUTIONS_TOP_K if filter_obj else TOP_K,
    )
    # If the student gave a precise paper+question reference and we found the
    # matching part(s), treat it as a confident hit so the retrieval floor
    # doesn't guardrail the exact solution they asked for.
    exact_match = bool(ref.get("question_number") and filter_obj and hits)
    chunks: list[RetrievedChunk] = []
    citations: list[Citation] = []
    seen_tutorials: set[str] = set()
    for h in hits:
        part_id = str(h.get("part_id") or "")
        if not part_id:
            continue
        # Keep most of the worked solution — truncating to 800 chars was losing
        # whole sub-parts, forcing the model to improvise the question.
        snippet = _shorten(
            (h.get("question_text") or "") + "\n\n" + (h.get("solution_text") or ""),
            2200,
        )
        score = 0.95 if exact_match else _normalise_score(h)
        chunks.append(RetrievedChunk(slug=part_id, snippet=snippet, score=score))
        # Cite the underlying TUTORIALS (they have pages the widget links to).
        # We don't cite the exam-part id — it has no page, so it would render as
        # a dead link and crowd out the useful tutorial links.
        refs = h.get("tutorials_referenced") or []
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except json.JSONDecodeError:
                refs = []
        for tslug in refs:
            ts = str(tslug).strip()
            if ts and ts not in seen_tutorials:
                seen_tutorials.add(ts)
                citations.append(
                    Citation(slug=ts, title=ts, timestamp_seconds=None, score=score)
                )
    return chunks, citations


def _from_summary_search(query: str) -> tuple[list[RetrievedChunk], list[Citation]]:
    hits = _search_preview(
        SUMMARY_SEARCH, query, columns=["summary_id", "strand_name", "body"]
    )
    chunks: list[RetrievedChunk] = []
    citations: list[Citation] = []
    for h in hits:
        sid = str(h.get("summary_id") or "")
        if not sid:
            continue
        snippet = _shorten(h.get("body") or "", 800)
        score = _normalise_score(h)
        chunks.append(RetrievedChunk(slug=sid, snippet=snippet, score=score))
        citations.append(
            Citation(
                slug=sid,
                title=str(h.get("strand_name") or sid),
                timestamp_seconds=None,
                score=score,
            )
        )
    return chunks, citations


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def retrieve(query: str, query_class: QueryClass) -> RetrievalResult:
    """Fan out per ``query_class`` and return a :class:`RetrievalResult`.

    The retriever does NOT call the synthesiser — it just gathers evidence.
    Each service-specific helper is synchronous; we wrap them in
    ``asyncio.to_thread`` so the fan-out is genuinely concurrent under
    asyncio. Snowflake's Python connector is not asyncio-aware but is
    perfectly thread-safe.
    """
    started = time.perf_counter()
    services_called: list[str] = []
    chunks: list[RetrievedChunk] = []
    citations: list[Citation] = []
    analyst_rows: list[dict[str, Any]] = []
    analyst_sql: str | None = None

    tasks: list[asyncio.Future[Any]] = []
    if query_class in (QueryClass.CONCEPT, QueryClass.IMAGE_EXTRACTED):
        services_called.append(TUTOR_SEARCH)
        tasks.append(asyncio.create_task(asyncio.to_thread(_from_tutor_search, query)))
    elif query_class == QueryClass.SOLUTION_LOOKUP:
        services_called.append(SOLUTIONS_SEARCH)
        tasks.append(asyncio.create_task(asyncio.to_thread(_from_solutions_search, query)))
    elif query_class == QueryClass.SUMMARY_REQUEST:
        services_called.append(SUMMARY_SEARCH)
        tasks.append(asyncio.create_task(asyncio.to_thread(_from_summary_search, query)))
    elif query_class == QueryClass.ANALYTICAL:
        services_called.append("cortex.analyst")
        analyst = await asyncio.to_thread(_call_analyst, query)
        analyst_sql = analyst.sql
        analyst_rows = analyst.rows
    elif query_class == QueryClass.AMBIGUOUS:
        # Fan out to all three search services + Analyst in parallel. Merge
        # by score with a tie-break on document type (preference order:
        # tutorial → exam part → summary).
        services_called.extend([TUTOR_SEARCH, SOLUTIONS_SEARCH, SUMMARY_SEARCH, "cortex.analyst"])
        tasks.extend([
            asyncio.create_task(asyncio.to_thread(_from_tutor_search, query)),
            asyncio.create_task(asyncio.to_thread(_from_solutions_search, query)),
            asyncio.create_task(asyncio.to_thread(_from_summary_search, query)),
        ])
        analyst_task = asyncio.create_task(asyncio.to_thread(_call_analyst, query))
    else:
        # Unreachable in practice — kept for static-checker exhaustiveness.
        services_called.append(TUTOR_SEARCH)
        tasks.append(asyncio.create_task(asyncio.to_thread(_from_tutor_search, query)))

    # Collect search results from whichever tasks we kicked off.
    for done in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(done, Exception):
            logger.warning("retrieval task failed: %s", done)
            continue
        c, cit = done  # type: ignore[misc]
        chunks.extend(c)
        citations.extend(cit)

    if query_class == QueryClass.AMBIGUOUS:
        analyst = await analyst_task
        analyst_sql = analyst.sql
        analyst_rows = analyst.rows

    # Sort chunks by score desc, keep top-K overall, and dedupe by slug. For
    # solution-lookup we keep more chunks so a full multi-part exam question
    # survives; citations stay capped at TOP_K (the widget shows 2 anyway).
    chunk_cap = SOLUTIONS_TOP_K if query_class == QueryClass.SOLUTION_LOOKUP else TOP_K
    chunks = _dedupe_by_slug(sorted(chunks, key=lambda c: -c.score))[:chunk_cap]
    citations = _dedupe_by_slug(sorted(citations, key=lambda c: -c.score))[:TOP_K]
    top_score = chunks[0].score if chunks else 0.0

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "retrieve query_class=%s services=%s chunks=%d top_score=%.3f elapsed_ms=%d",
        query_class.value, services_called, len(chunks), top_score, elapsed_ms,
    )

    # Attach curated exam appearances for the top cited tutorials (loaded from
    # the shipped corpus/exam_appearances.json). Best-effort: never fail
    # retrieval if the index is missing or a row is malformed.
    from . import exam_refs

    try:
        exam_appearances = exam_refs.exam_appearances_for_citations(citations)
    except Exception:
        logger.exception("exam-appearance lookup failed (non-fatal)")
        exam_appearances = []

    return RetrievalResult(
        query_class=query_class,
        chunks=chunks,
        citations=citations,
        analyst_rows=analyst_rows,
        analyst_sql=analyst_sql,
        top_reranker_score=top_score,
        services_called=services_called,
        exam_appearances=exam_appearances,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shorten(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _extract_reranker_score(hit: dict[str, Any]) -> float:
    """Pull the raw reranker score out of a Cortex Search Preview hit.

    The Cortex Search response shape (verified against the live
    TUTOR_SEARCH service 2026-05-25) nests scores under ``@scores``::

        {
          "slug": "...",
          "title": "...",
          "@scores": {
            "reranker_score":    2.4509184,   # unbounded; can be negative
            "cosine_similarity": 0.6312332,   # [0, 1]
            "text_match":        0.43972465   # [0, 1]
          }
        }

    The previous parser read ``hit.get("score")`` — that field doesn't
    exist in real responses, so every chunk landed at score=0.0 and
    tripped the synthesis confidence gate (RETRIEVAL_FLOOR=0.30), forcing
    the "I'm not sure" fallback on every concept query.

    Fallback order: ``@scores.reranker_score`` → ``@scores.cosine_similarity``
    → ``hit['score']`` (preserves test-fixture compatibility) → 0.0. NaN
    or non-numeric values return 0.0 (defensive against malformed
    responses).
    """
    scores = hit.get("@scores")
    if isinstance(scores, dict):
        for key in ("reranker_score", "cosine_similarity", "text_match"):
            v = scores.get(key)
            if v is not None:
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                if f == f:  # not NaN
                    return f
    # Fallback for the test fixture, which puts a flat ``score`` field at
    # the top level of each hit. Keeps existing tests compatible without
    # forcing every test to mirror the production response shape.
    raw = hit.get("score")
    if raw is None:
        return 0.0
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if f != f:  # NaN
        return 0.0
    return f


def _sigmoid_normalize(raw: float) -> float:
    """Map an unbounded reranker score onto ``[0, 1]`` via the logistic.

    Raw reranker scores are unbounded (observed range in our corpus is
    roughly -3 to +5). Downstream consumers — the Pydantic contract
    (``contract.RetrievalResult.top_reranker_score`` is ``ge=0.0, le=1.0``),
    the query-log schema, and the firewall — assume a bounded score, so we
    sigmoid-normalize before passing on.

    The mapping is order-preserving (so ranking is unchanged) and gives a
    natural calibration against the existing ``RETRIEVAL_FLOOR = 0.30``:

        raw  -2.0  →  σ ≈ 0.12   (below floor → "I don't know" fallback)
        raw   0.0  →  σ = 0.50   (neutral; above floor → synthesise)
        raw  +2.0  →  σ ≈ 0.88   (confident; well above floor)
        raw  +4.0  →  σ ≈ 0.98

    The previous ``_normalise_score`` clamped to ``[0, 1]`` directly,
    which only worked when scores were already in range — i.e. never,
    against the real ``@scores.reranker_score`` field. Tests below pin
    representative inputs to expected outputs so any future change to
    this calibration is visible.
    """
    if raw != raw:  # NaN guard
        return 0.0
    # Avoid OverflowError on extreme inputs; math.exp(-1000) is fine but
    # math.exp(1000) overflows. Cortex never returns values that extreme,
    # but a single defensive clamp keeps a future malformed response from
    # crashing the request.
    if raw >= 700:
        return 1.0
    if raw <= -700:
        return 0.0
    return 1.0 / (1.0 + math.exp(-raw))


def _normalise_score(hit: dict[str, Any]) -> float:
    """Extract a reranker score from a Cortex hit and normalize to ``[0, 1]``.

    Composition of :func:`_extract_reranker_score` and
    :func:`_sigmoid_normalize` — the canonical scoring path for the three
    per-service parsers. If ``BLENDED_SCORING_ENABLED`` is on, falls
    through to :func:`_blended_score` instead.
    """
    if _blended_scoring_enabled():
        return _blended_score(hit)
    return _sigmoid_normalize(_extract_reranker_score(hit))


def _scores_block(hit: dict[str, Any]) -> dict[str, Any]:
    """Return the hit's ``@scores`` block as a dict (or empty dict if absent).

    Defensive against the response-shape change that shipped DAY_30: pre-fix
    Cortex Search responses didn't have ``@scores`` at all, just a flat
    ``score`` field. Returning ``{}`` on miss lets ``_blended_score`` fall
    back through the same fixture-compatibility path as the reranker
    extractor.
    """
    sc = hit.get("@scores")
    return sc if isinstance(sc, dict) else {}


def _extract_cosine_similarity(hit: dict[str, Any]) -> float:
    """Pull ``@scores.cosine_similarity`` (already in ``[0, 1]``). Returns
    0.0 if missing — same defensive policy as :func:`_extract_reranker_score`.
    """
    v = _scores_block(hit).get("cosine_similarity")
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f:  # NaN
        return 0.0
    return f


def _extract_text_match(hit: dict[str, Any]) -> float:
    """Pull ``@scores.text_match`` (already in ``[0, 1]``)."""
    v = _scores_block(hit).get("text_match")
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f:  # NaN
        return 0.0
    return f


def _blended_score(hit: dict[str, Any]) -> float:
    """Linear blend of (sigmoid-normalised reranker, cosine, text_match).

    Formula::

        blended = w_r * sigmoid(reranker) + w_c * cosine + w_t * text_match

    The reranker leg is sigmoid-normalised first so all three terms live
    on the same ``[0, 1]`` scale and the weights have intuitive meaning.

    Returns a value in ``[0, sum(weights)]`` — when the weights sum to 1
    (the default; ``w_r=0.6, w_c=0.3, w_t=0.1``), the output is in
    ``[0, 1]`` and directly comparable with ``RETRIEVAL_FLOOR``.

    Gated behind the ``BLENDED_SCORING_ENABLED`` env flag at the
    ``_normalise_score`` callsite — this helper itself is unconditional so
    tests can pin its arithmetic without touching the flag.
    """
    r = _sigmoid_normalize(_extract_reranker_score(hit))
    c = _extract_cosine_similarity(hit)
    t = _extract_text_match(hit)
    return (
        BLENDED_WEIGHT_RERANKER * r
        + BLENDED_WEIGHT_COSINE * c
        + BLENDED_WEIGHT_TEXT_MATCH * t
    )


_TC = tuple[list[RetrievedChunk], list[Citation]]


def _dedupe_by_slug(items: list[Any]) -> list[Any]:
    """Stable de-dupe by ``slug`` attribute — keeps the first (highest-scored)
    occurrence.
    """
    seen: set[str] = set()
    out: list[Any] = []
    for it in items:
        slug = getattr(it, "slug", None)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(it)
    return out
