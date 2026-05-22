"""L3 — semantic cache (between retrieval and synthesis).

Lives **after** the retriever (per ADR-003 Edit 2 — retrieval is always run
because Cortex Search on an XS warehouse is cheap and produces value on
every call) and **before** the synthesiser (which makes the expensive LLM
call). The cache key encodes the retrieval *result* plus the model + tier,
so a near-duplicate question that retrieves the same top-K slugs reuses the
prior LLM completion.

Cache key: ``sha256(normalised_query + sorted_top_k_slugs + model_used + tier)``.

* ``normalised_query`` is the raw query lowercased, with all whitespace
  collapsed to single spaces and a small maths-symbol normalisation pass
  (``×`` → ``*``, ``÷`` → ``/``, ``−`` → ``-``, etc.). Same canonicalisation
  the orchestrator's classifier would benefit from but kept here so the
  cache key is computed from one source.
* The query string is included in the key so trivially-different questions
  hitting the same chunks still get distinct cache rows — important because
  the LLM output changes with the question wording even when evidence is
  identical.

Bypass: ``query_class == "analytical"``. Cortex Analyst already caches at
the warehouse layer, and analytical queries are meant to be re-run for
freshness.

Toggle: ``SEMANTIC_CACHE_ENABLED=true``.

Storage: ``GKTUITION_TUTOR.CORTEX.QUERY_CACHE`` (DDL in
``api/sql/firewall_tables.sql``). TTL 30 days, evaluated lazily at read time
(delete-on-stale rather than a scheduled cleanup, so the table never grows
past its working set on a sleepy site).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from ._log import event
from .settings import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage seam — injectable for tests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CachedResponse:
    """Subset of the canonical ``QueryResponse`` we persist + restore.

    The cache MUST NOT change the JSON contract. We persist exactly the
    fields Agent 09's contract declares and reassemble a ``QueryResponse``
    around them when serving the hit. ``from_cache`` is overwritten at serve
    time so it's never persisted; ``elapsed_ms`` is recomputed from the
    cache-hit codepath's own clock.
    """

    response_json: dict[str, Any]
    model_used: str
    created_at: float


# (lookup, store) functions. Both injectable. Default impls hit Snowflake.
CacheLookup = Callable[[str], CachedResponse | None]
CacheStore = Callable[[str, CachedResponse], None]

_lookup: CacheLookup | None = None
_store: CacheStore | None = None
_in_memory_store: dict[str, CachedResponse] = {}
_in_memory_lock = Lock()


def set_cache_backends(
    *, lookup: CacheLookup | None, store: CacheStore | None
) -> None:
    """Inject the persistence layer. Used by main.py at startup and by tests."""
    global _lookup, _store
    _lookup = lookup
    _store = store


def clear_in_memory_cache() -> None:
    """Wipe the in-memory fallback store. Used by tests."""
    with _in_memory_lock:
        _in_memory_store.clear()


# ---------------------------------------------------------------------------
# Default Snowflake-backed impls
# ---------------------------------------------------------------------------


def _default_lookup(cache_key: str) -> CachedResponse | None:
    """Look up ``cache_key`` in ``QUERY_CACHE``. Returns None on miss / stale.

    Deletes-on-stale: if the row is older than ``cache_ttl_seconds`` we
    issue a DELETE and treat as a miss.
    """
    settings = get_settings()
    try:
        from ..orchestrator.retriever import _cursor
    except Exception:  # pragma: no cover - import-time failure
        return None
    table = settings.cache_table_fqn
    try:
        with _cursor() as cs:
            cs.execute(
                f"SELECT response_json, model_used, "
                f"       DATE_PART('EPOCH_SECOND', created_at) AS created_epoch "
                f"FROM {table} WHERE cache_key = %s",
                (cache_key,),
            )
            row = cs.fetchone()
            if row is None:
                return None
            response_json, model_used, created_epoch = row[0], row[1], float(row[2])
            if (time.time() - created_epoch) > settings.cache_ttl_seconds:
                cs.execute(
                    f"DELETE FROM {table} WHERE cache_key = %s", (cache_key,)
                )
                return None
            if isinstance(response_json, str):
                response_json = json.loads(response_json)
            # Bump hit counter (best-effort).
            try:
                cs.execute(
                    f"UPDATE {table} "
                    f"SET hits = hits + 1, last_hit_at = CURRENT_TIMESTAMP() "
                    f"WHERE cache_key = %s",
                    (cache_key,),
                )
            except Exception:
                logger.debug("cache hit counter update failed", exc_info=True)
            return CachedResponse(
                response_json=response_json,
                model_used=str(model_used),
                created_at=created_epoch,
            )
    except Exception:
        logger.exception("cache lookup failed; treating as miss")
        return None


def _default_store(cache_key: str, payload: CachedResponse) -> None:
    settings = get_settings()
    try:
        from ..orchestrator.retriever import _cursor
    except Exception:  # pragma: no cover
        return
    table = settings.cache_table_fqn
    try:
        with _cursor() as cs:
            cs.execute(
                f"INSERT INTO {table} (cache_key, response_json, model_used, "
                f"hits, last_hit_at, created_at) "
                f"VALUES (%s, PARSE_JSON(%s), %s, 0, CURRENT_TIMESTAMP(), "
                f"CURRENT_TIMESTAMP())",
                (
                    cache_key,
                    json.dumps(payload.response_json),
                    payload.model_used,
                ),
            )
    except Exception:
        # Probably a PK conflict from a concurrent write — fine to drop.
        logger.debug("cache store failed (likely concurrent write)", exc_info=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_cache_key(
    *,
    query: str,
    top_k_slugs: list[str],
    model_used: str,
    tier: str,
) -> str:
    """Stable cache key for the (normalised_query, slugs, model, tier) tuple."""
    norm = _normalise_query(query)
    slugs = sorted(s for s in top_k_slugs if s)
    payload = json.dumps(
        {"q": norm, "slugs": slugs, "model": model_used, "tier": tier},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lookup(
    *,
    query: str,
    top_k_slugs: list[str],
    model_used: str,
    tier: str,
    query_class: str,
) -> CachedResponse | None:
    """Cache lookup. Returns None on miss, on disabled, or on analytical bypass."""
    settings = get_settings()
    if not settings.cache_enabled:
        return None
    if query_class == "analytical":
        event("L3", "bypass", reason="analytical", tier=tier)
        return None

    key = compute_cache_key(
        query=query, top_k_slugs=top_k_slugs, model_used=model_used, tier=tier
    )
    fn = _lookup or _default_lookup
    if fn is _default_lookup:
        # Lazy in-memory fallback used when nobody has wired a Snowflake
        # writer — primarily a test convenience but also gives us a working
        # cache in dev without a Snowflake connection.
        with _in_memory_lock:
            mem = _in_memory_store.get(key)
        if mem is not None:
            if (time.time() - mem.created_at) > settings.cache_ttl_seconds:
                with _in_memory_lock:
                    _in_memory_store.pop(key, None)
                event("L3", "miss", reason="stale", tier=tier)
                return None
            event("L3", "hit", tier=tier, model=mem.model_used)
            return mem
        # Try the real Snowflake-backed lookup too — if no connection is set
        # the helper degrades to None silently.
        res = fn(key)
        if res is None:
            event("L3", "miss", tier=tier)
        else:
            event("L3", "hit", tier=tier, model=res.model_used)
        return res

    res = fn(key)
    if res is None:
        event("L3", "miss", tier=tier)
    else:
        event("L3", "hit", tier=tier, model=res.model_used)
    return res


def store(
    *,
    query: str,
    top_k_slugs: list[str],
    model_used: str,
    tier: str,
    query_class: str,
    response_json: dict[str, Any],
) -> None:
    """Persist a fresh response. No-op on disabled / analytical bypass."""
    settings = get_settings()
    if not settings.cache_enabled:
        return
    if query_class == "analytical":
        return
    key = compute_cache_key(
        query=query, top_k_slugs=top_k_slugs, model_used=model_used, tier=tier
    )
    payload = CachedResponse(
        response_json=dict(response_json),
        model_used=model_used,
        created_at=time.time(),
    )
    fn = _store or _default_store
    if fn is _default_store:
        with _in_memory_lock:
            _in_memory_store[key] = payload
    fn(key, payload)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_WHITESPACE_RE = re.compile(r"\s+")


# Common maths-symbol substitutions so "5 × 4" and "5 * 4" share a cache row.
_SYMBOL_MAP = {
    "×": "*",
    "·": "*",
    "÷": "/",
    "−": "-",  # U+2212 minus
    "–": "-",  # U+2013 en-dash
    "—": "-",  # U+2014 em-dash
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "≈": "~=",
    "²": "^2",
    "³": "^3",
}


def _normalise_query(q: str) -> str:
    q = (q or "").strip().lower()
    for from_, to_ in _SYMBOL_MAP.items():
        q = q.replace(from_, to_)
    q = _WHITESPACE_RE.sub(" ", q)
    return q
