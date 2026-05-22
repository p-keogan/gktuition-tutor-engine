"""
Integration shim for the existing /query handler.

ASSUMPTION (Agent 06): the existing ADR-003 text path exposes an internal
function (NOT just the HTTP route) that takes a question string plus some
request metadata and returns a dict matching the ADR-003 Decision item 5
response contract. We call it via a registered callable so we don't need to
import across module boundaries that may not exist yet.

Wire up the real function at app startup:

    from api.services import query_pipeline
    from api.routes.query import run_text_query   # the real one
    query_pipeline.set_text_query_runner(run_text_query)
"""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

# Signature: (question: str, *, user_id: str, request_id: str) -> dict
TextQueryRunner = Callable[..., dict | Awaitable[dict]]

_runner: TextQueryRunner | None = None


def set_text_query_runner(fn: TextQueryRunner) -> None:
    """Register the existing /query internal handler at app startup."""
    global _runner
    _runner = fn


async def run_text_query(
    question: str,
    *,
    user_id: str,
    request_id: str,
) -> dict:
    """Call the registered /query handler. Accepts sync or async callables."""
    if _runner is None:
        raise RuntimeError(
            "No text query runner registered. Call set_text_query_runner(...) "
            "at app startup."
        )
    result = _runner(question, user_id=user_id, request_id=request_id)
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, dict):
        raise TypeError(
            f"text query runner returned {type(result).__name__}, expected dict"
        )
    return result
