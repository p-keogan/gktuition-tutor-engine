"""Offline tests for the ``local-hybrid-rewrite`` backend (AGENT_32, Phase-0 v3).

Fully offline — no fastembed, no lance index, no LLM. The hybrid + dense
retrievers are injected fakes, so these tests assert only the rewrite
substitution policy that mirrors production's two firing mechanisms.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Load the pure-stdlib backend module by file path so the test does not pull in
# the local_retrieval package __init__ (which eagerly imports lancedb/fastembed).
_spec = importlib.util.spec_from_file_location(
    "rewrite_backend", REPO / "local_retrieval" / "rewrite_backend.py")
_rb = importlib.util.module_from_spec(_spec)
# Register before exec so @dataclass can resolve sys.modules[cls.__module__].
sys.modules.setdefault("rewrite_backend", _rb)
_spec.loader.exec_module(_rb)
RewriteEntry = _rb.RewriteEntry
load_rewrite_cache = _rb.load_rewrite_cache
make_rewrite_backend = _rb.make_rewrite_backend

# A fake hybrid index: original queries retrieve "wrong", rewritten retrieve
# "right". Lets us prove a substitution actually changed the result.
_HYBRID = {
    "orig-iter1": [("wrong-slug", 1.0), ("noise", 0.5)],
    "rewritten-iter1": [("right-slug", 1.0), ("noise", 0.5)],
    "orig-fallback": [("wrong-slug", 1.0)],
    "rewritten-fallback": [("right-slug", 1.0)],
    "orig-abovefloor": [("already-right", 1.0)],
    "rewritten-abovefloor": [("would-be-different", 1.0)],
    "orig-nofire": [("hybrid-default", 1.0)],
}


def _hybrid_fn(q, k):
    return _HYBRID.get(q, [])[:k]


def _make(cache, *, dense_scores):
    def dense_top1_fn(q):
        return dense_scores.get(q, 1.0)
    return make_rewrite_backend(cache, hybrid_fn=_hybrid_fn,
                                dense_top1_fn=dense_top1_fn)


def test_cache_miss_is_noop():
    """A query absent from the cache passes straight through to hybrid."""
    retrieve = _make({}, dense_scores={})
    assert retrieve("orig-nofire", 5) == [("hybrid-default", 1.0)]


def test_fired_but_empty_rewrite_is_noop():
    """fired=True but no rewritten_query (e.g. cache not yet LLM-populated)."""
    cache = {"orig-fallback": RewriteEntry(True, "fallback", "")}
    retrieve = _make(cache, dense_scores={"orig-fallback": 0.05})
    assert retrieve("orig-fallback", 5) == [("wrong-slug", 1.0)]


def test_iter1_substitutes_pre_retrieval():
    """iter1 rewrites BEFORE retrieval, irrespective of any floor signal."""
    cache = {"orig-iter1": RewriteEntry(True, "iter1", "rewritten-iter1")}
    retrieve = _make(cache, dense_scores={"orig-iter1": 1.0})  # above floor, still fires
    assert retrieve("orig-iter1", 5)[0][0] == "right-slug"


def test_fallback_substitutes_only_when_sub_floor():
    """fallback substitutes the rewrite only if the dense top-1 is sub-floor."""
    cache = {"orig-fallback": RewriteEntry(True, "fallback", "rewritten-fallback")}
    sub = _make(cache, dense_scores={"orig-fallback": 0.10})   # < 0.30
    assert sub("orig-fallback", 5)[0][0] == "right-slug"


def test_fallback_passes_through_above_floor():
    """Above-floor fallback rows keep their original (first-attempt) result."""
    cache = {"orig-abovefloor": RewriteEntry(True, "fallback", "rewritten-abovefloor")}
    above = _make(cache, dense_scores={"orig-abovefloor": 0.80})  # >= 0.30
    assert above("orig-abovefloor", 5) == [("already-right", 1.0)]


def test_fallback_returns_better_of_two():
    """A rewrite that retrieves worse than the original must not degrade the row."""
    hybrid = {
        "orig": [("good", 0.9)],
        "rw": [("bad", 0.2)],
    }
    cache = {"orig": RewriteEntry(True, "fallback", "rw")}
    retrieve = make_rewrite_backend(
        cache,
        hybrid_fn=lambda q, k: hybrid.get(q, [])[:k],
        dense_top1_fn=lambda q: 0.05,  # sub-floor → eligible to substitute
    )
    # base top (0.9) >= rewrite top (0.2) → keep base.
    assert retrieve("orig", 5) == [("good", 0.9)]


def test_load_rewrite_cache_roundtrip(tmp_path):
    p = tmp_path / "rewrite_cache.csv"
    p.write_text(
        "eval_id,source,fired,mechanism,original_query,rewritten_query\n"
        "a,phrasings,true,iter1,explain pensions,present value of a pension\n"
        "b,phrasings,false,,how do I factorise,\n",
        encoding="utf-8",
    )
    cache = load_rewrite_cache(p)
    assert cache["explain pensions"].fired is True
    assert cache["explain pensions"].mechanism == "iter1"
    assert cache["explain pensions"].rewritten_query == "present value of a pension"
    assert cache["how do I factorise"].fired is False


def test_missing_cache_file_is_empty():
    assert load_rewrite_cache("/nonexistent/path/rewrite_cache.csv") == {}
