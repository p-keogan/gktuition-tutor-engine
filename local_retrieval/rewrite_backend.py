"""``local-hybrid-rewrite`` backend — the production-representative parity layer
for Snowflake-exit Phase-0 **v3** (AGENT_32).

This wraps AGENT_31's :func:`local_retrieval.hybrid.retrieve_hybrid` with the
query-rewrite layer the *live* system already runs, so the offline gate reflects
the production retrieval the awkward prompts actually receive. It mirrors
production's two firing mechanisms (``api/orchestrator/query_rewrite.py``):

* **iter-1** (pre-retrieval): for a row whose cached ``mechanism == "iter1"`` and
  which has a non-empty cached ``rewritten_query``, retrieve directly with the
  rewritten query — production rewrites these *before* the first retrieve.
* **fallback** (retrieve-then-rewrite): retrieve with the original query; if the
  result is **sub-floor** (top-1 dense cosine < ``RETRIEVAL_FLOOR`` = 0.30) and
  the row's cached ``mechanism == "fallback"`` with a non-empty rewrite,
  re-retrieve with the rewritten query and return the better of the two.

Sub-floor signal
----------------
The hybrid RRF score is normalised so its top is always 1.0 (v2 §5) — useless as
a floor. We therefore measure sub-floor on the **dense (arctic) top-1 cosine**, a
real [0, 1] confidence directly comparable to ``RETRIEVAL_FLOOR`` and the offline
analogue of production's reranker/cosine floor.

Cache miss / empty rewrite ⇒ pure pass-through to hybrid (a no-op), so an
un-populated cache reproduces ``local-hybrid`` exactly.

Spike-only: never imported by ``api/``. The rewrite *text* is read from
``eval/rewrite_cache.csv`` (generated offline by ``eval/build_rewrite_cache.py``),
so scoring is fully offline, free, and reproducible — no LLM call at score time.

The retriever callables are injectable so the backend is unit-testable without
fastembed / a lance index: tests pass fakes; production wiring uses the defaults.
"""
from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# RETRIEVAL_FLOOR mirrored from api/orchestrator/retriever.py (read-only); defined
# locally so this spike module adds no dependency on the live serving path.
RETRIEVAL_FLOOR = 0.30

RetrieveFn = Callable[[str, int], list[tuple[str, float]]]
DenseTop1Fn = Callable[[str], float]


@dataclass(frozen=True)
class RewriteEntry:
    fired: bool
    mechanism: str  # "iter1" | "fallback" | ""
    rewritten_query: str


def load_rewrite_cache(path: str | Path) -> dict[str, RewriteEntry]:
    """Load ``rewrite_cache.csv`` → ``original_query`` → :class:`RewriteEntry`.

    Keyed by the original query text (the backend contract is query-keyed). Rows
    with ``fired == false`` or an empty ``rewritten_query`` become no-op entries.
    Missing file ⇒ empty map (everything passes through to hybrid).
    """
    path = Path(path)
    out: dict[str, RewriteEntry] = {}
    if not path.is_file():
        return out
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["original_query"]] = RewriteEntry(
                fired=(r.get("fired", "").strip().lower() == "true"),
                mechanism=(r.get("mechanism") or "").strip(),
                rewritten_query=(r.get("rewritten_query") or "").strip(),
            )
    return out


def make_rewrite_backend(
    cache: dict[str, RewriteEntry],
    *,
    hybrid_fn: RetrieveFn,
    dense_top1_fn: DenseTop1Fn,
    retrieval_floor: float = RETRIEVAL_FLOOR,
) -> RetrieveFn:
    """Build the ``local-hybrid-rewrite`` retrieve callable.

    Parameters
    ----------
    cache:
        ``original_query`` → :class:`RewriteEntry` (see :func:`load_rewrite_cache`).
    hybrid_fn:
        ``(query, top_k) -> [(slug, score)]`` — AGENT_31's hybrid retriever.
    dense_top1_fn:
        ``(query) -> float`` — the dense (arctic) top-1 cosine for the sub-floor
        decision. Production-faithful: only the dense confidence, not the
        normalised hybrid score, gates the fallback.
    retrieval_floor:
        Sub-floor threshold (default 0.30, mirroring the live retriever).
    """

    def retrieve(query: str, top_k: int = 5) -> list[tuple[str, float]]:
        entry = cache.get(query)
        # No cache entry, didn't fire, or no rewrite available ⇒ pure hybrid.
        if entry is None or not entry.fired or not entry.rewritten_query:
            return hybrid_fn(query, top_k)

        if entry.mechanism == "iter1":
            # Production rewrites conceptual framings BEFORE the first retrieve.
            return hybrid_fn(entry.rewritten_query, top_k)

        # Fallback: retrieve original; only substitute if genuinely sub-floor.
        base = hybrid_fn(query, top_k)
        if dense_top1_fn(query) >= retrieval_floor:
            return base  # cleared the floor on the first try → no rewrite.
        rewritten = hybrid_fn(entry.rewritten_query, top_k)
        # Return the better result (guards against a rewrite that retrieves worse).
        base_top = base[0][1] if base else 0.0
        rw_top = rewritten[0][1] if rewritten else 0.0
        return rewritten if rw_top >= base_top else base

    return retrieve
