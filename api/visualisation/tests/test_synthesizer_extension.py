"""Unit tests for :mod:`api.visualisation.synthesizer_extension`.

Three groups of tests:

1. ``should_emit_graph`` on hand-curated positive (graph-shaped) and
   negative (not-graph-shaped) phrases.
2. ``select_and_invoke_generator`` routing — one test per generator, plus
   the ``name="none"`` short-circuit.
3. ``select_and_invoke_generator`` resilience — malformed JSON, unknown
   tool name, missing required args, generator raising ValueError.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from api.visualisation import synthesizer_extension as se

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeChunk:
    """Minimal duck for RetrievedChunk — only .slug and .snippet are read."""

    slug: str
    snippet: str = "x"
    score: float = 0.9


# ---------------------------------------------------------------------------
# Group 1 — should_emit_graph: 10 positive + 10 negative phrases.
# ---------------------------------------------------------------------------

POSITIVE_PHRASES: list[tuple[str, str, list[FakeChunk]]] = [
    ("sketch the graph of y = sin(2x)", "concept", []),
    ("plot y = x^2 - 4 for me", "concept", []),
    ("can you draw f(x) = e^x", "concept", []),
    ("show me the shape of a cubic", "concept", []),
    ("what does y = tan(x) look like near pi/2", "concept", []),
    ("find the turning point of f(x) = x^3 - 3x", "concept", []),
    ("describe the asymptote behaviour of 1/x", "concept", []),
    ("graph the modulus function", "concept", []),
    ("visualise the parabola y = (x-1)^2 + 2", "concept", []),
    # Slug-driven positive (no trigger phrase in the query).
    (
        "what's the next step here",
        "concept",
        [FakeChunk(slug="functions-graphs-2-shapes-of-quadratic-functions")],
    ),
]

NEGATIVE_PHRASES: list[tuple[str, str, list[FakeChunk]]] = [
    ("explain why factorisation is useful", "concept", []),
    ("what is the definition of a function", "concept", []),
    ("how do I solve simultaneous equations", "concept",
     [FakeChunk(slug="algebra-3-simultaneous-equations")]),
    ("prove that the sum of two odd numbers is even", "concept",
     [FakeChunk(slug="number-theory-1-divisibility")]),
    ("when did the discriminant come up on paper 1 since 2015", "analytical", []),
    ("how many parts on 2023 P2", "analytical", []),
    ("what's the point of the chain rule", "concept",
     [FakeChunk(slug="algebra-2-quadratic-equations")]),
    ("define the discriminant", "concept",
     [FakeChunk(slug="algebra-1-revision-of-jc-factorising")]),
    ("how to factorise x^2 - 5x + 6", "concept",
     [FakeChunk(slug="algebra-1-revision-of-jc-factorising")]),
    ("revise complex numbers for me", "summary_request",
     [FakeChunk(slug="complex-numbers-1-introduction")]),
]


@pytest.mark.parametrize("query,query_class,retrieved", POSITIVE_PHRASES)
def test_should_emit_graph_positive(
    query: str, query_class: str, retrieved: list[FakeChunk]
) -> None:
    assert se.should_emit_graph(query, query_class, retrieved) is True, (
        f"expected positive trigger for {query!r}"
    )


@pytest.mark.parametrize("query,query_class,retrieved", NEGATIVE_PHRASES)
def test_should_emit_graph_negative(
    query: str, query_class: str, retrieved: list[FakeChunk]
) -> None:
    assert se.should_emit_graph(query, query_class, retrieved) is False, (
        f"expected negative for {query!r}"
    )


def test_should_emit_graph_empty_query_returns_false() -> None:
    assert se.should_emit_graph("", "concept", []) is False
    assert se.should_emit_graph("   ", "concept", []) is False


def test_should_emit_graph_analytical_always_false() -> None:
    # Even with a trigger phrase, analytical queries are excluded in v1.
    assert (
        se.should_emit_graph("plot how often differentiation appears", "analytical", [])
        is False
    )


def test_should_emit_graph_llm_fallback_yes() -> None:
    def fake_llm(prompt: str) -> str:
        return "yes"

    out = se.should_emit_graph(
        "tell me about the structure of a recursive function",
        "concept",
        [],
        llm_client=fake_llm,
    )
    assert out is True


def test_should_emit_graph_llm_fallback_no() -> None:
    def fake_llm(prompt: str) -> str:
        return "no"

    out = se.should_emit_graph(
        "tell me about the structure of a recursive function",
        "concept",
        [],
        llm_client=fake_llm,
    )
    assert out is False


def test_should_emit_graph_llm_raises_falls_closed() -> None:
    def fake_llm(prompt: str) -> str:
        raise RuntimeError("network gremlin")

    out = se.should_emit_graph("what is interesting about pi", "concept", [],
                               llm_client=fake_llm)
    assert out is False


def test_should_emit_graph_accepts_dict_chunks() -> None:
    # Some callers will pass plain dicts (e.g. from raw retrieval output).
    assert (
        se.should_emit_graph(
            "explain",
            "concept",
            [{"slug": "functions-graphs-3-vertex-form-completing-the-square"}],
        )
        is True
    )


# ---------------------------------------------------------------------------
# Group 2 — select_and_invoke_generator routing: one per generator.
# ---------------------------------------------------------------------------


def _make_llm_returning(payload: dict) -> callable:
    """Build a fake llm_client(sys, user) → str(json.dumps(payload))."""

    def _fake(system_prompt: str, user_prompt: str) -> str:
        return json.dumps(payload)

    return _fake


def test_select_invokes_plot_polynomial() -> None:
    llm = _make_llm_returning(
        {
            "name": "plot_polynomial",
            "arguments": {"coefficients": [1, 0, -4], "x_range": [-5, 5]},
        }
    )
    figs = se.select_and_invoke_generator("sketch y = x^2 - 4", [], llm_client=llm)
    assert len(figs) == 1
    fig = figs[0]
    assert "data" in fig
    assert any(t.get("name") == "f(x)" for t in fig["data"])


def test_select_invokes_plot_trig() -> None:
    llm = _make_llm_returning(
        {
            "name": "plot_trig",
            "arguments": {"family": "sin", "amplitude": 2.0, "period": 3.14159},
        }
    )
    figs = se.select_and_invoke_generator("sketch y = 2 sin(2x)", [], llm_client=llm)
    assert len(figs) == 1
    assert figs[0]["data"][0]["name"] == "sin"


def test_select_invokes_plot_exponential() -> None:
    llm = _make_llm_returning(
        {
            "name": "plot_exponential",
            "arguments": {"base": 2.0, "growth_rate": 1.0, "multiplier": 1.0},
        }
    )
    figs = se.select_and_invoke_generator("plot 2^x", [], llm_client=llm)
    assert len(figs) == 1
    assert figs[0]["data"][0]["name"] == "f(x)"


def test_select_invokes_plot_log() -> None:
    llm = _make_llm_returning(
        {"name": "plot_log", "arguments": {"base": 10.0}}
    )
    figs = se.select_and_invoke_generator("plot log base 10", [], llm_client=llm)
    assert len(figs) == 1


def test_select_invokes_plot_data_points() -> None:
    llm = _make_llm_returning(
        {
            "name": "plot_data_points",
            "arguments": {
                "points": [[1, 2], [2, 4], [3, 6], [4, 8]],
                "show_best_fit": True,
            },
        }
    )
    figs = se.select_and_invoke_generator(
        "scatter plot of (1,2), (2,4), (3,6), (4,8)", [], llm_client=llm
    )
    assert len(figs) == 1
    assert len(figs[0]["data"]) == 2  # data + fit line


def test_select_invokes_plot_overlay() -> None:
    """plot_overlay needs already-built figures; we synthesise two and feed."""
    from api.visualisation.generators import plot_polynomial

    f1 = plot_polynomial([1, 0, 0], show_zeros=False)
    f2 = plot_polynomial([1, 0, 0, 0], show_zeros=False)
    llm = _make_llm_returning(
        {"name": "plot_overlay", "arguments": {"figures": [f1, f2]}}
    )
    figs = se.select_and_invoke_generator("compare x^2 and x^3", [], llm_client=llm)
    assert len(figs) == 1
    assert len(figs[0]["data"]) == 2


def test_select_refuses_plot_piecewise_from_llm() -> None:
    # plot_piecewise needs callables → not JSON-serialisable from an LLM.
    # The extension refuses at the router boundary.
    llm = _make_llm_returning(
        {"name": "plot_piecewise", "arguments": {"pieces": [[None, -1, 1]]}}
    )
    figs = se.select_and_invoke_generator("plot the modulus", [], llm_client=llm)
    assert figs == []


def test_select_returns_empty_when_llm_chooses_none() -> None:
    llm = _make_llm_returning({"name": "none", "arguments": {}})
    figs = se.select_and_invoke_generator("when did Pythagoras die", [], llm_client=llm)
    assert figs == []


# ---------------------------------------------------------------------------
# Group 3 — resilience: malformed JSON, unknown tool, missing args, raise.
# ---------------------------------------------------------------------------


def test_select_handles_malformed_json() -> None:
    def fake_llm(system_prompt: str, user_prompt: str) -> str:
        return "this is { not } valid json"

    figs = se.select_and_invoke_generator("anything", [], llm_client=fake_llm)
    assert figs == []


def test_select_handles_unknown_generator_name() -> None:
    llm = _make_llm_returning({"name": "plot_quaternion", "arguments": {}})
    figs = se.select_and_invoke_generator("anything", [], llm_client=llm)
    assert figs == []


def test_select_handles_missing_required_arg() -> None:
    # plot_polynomial requires `coefficients`.
    llm = _make_llm_returning({"name": "plot_polynomial", "arguments": {}})
    figs = se.select_and_invoke_generator("anything", [], llm_client=llm)
    assert figs == []


def test_select_handles_generator_raising_value_error() -> None:
    # Negative log base → ValueError inside the generator.
    llm = _make_llm_returning({"name": "plot_log", "arguments": {"base": -1.0}})
    figs = se.select_and_invoke_generator("plot log", [], llm_client=llm)
    assert figs == []


def test_select_handles_llm_client_raising() -> None:
    def fake_llm(system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("api went away")

    figs = se.select_and_invoke_generator("anything", [], llm_client=fake_llm)
    assert figs == []


def test_select_returns_empty_when_no_llm_client_wired() -> None:
    figs = se.select_and_invoke_generator("sketch y = x^2", [], llm_client=None)
    assert figs == []


def test_select_strips_markdown_code_fences() -> None:
    """Defends against LLMs that wrap their JSON in ```json fences."""

    def fake_llm(system_prompt: str, user_prompt: str) -> str:
        return '```json\n{"name": "plot_polynomial", "arguments": {"coefficients": [1, 0]}}\n```'

    figs = se.select_and_invoke_generator("sketch y = x", [], llm_client=fake_llm)
    assert len(figs) == 1


def test_select_drops_unexpected_kwargs() -> None:
    """LLM passing extra args (e.g. __class__) must be filtered out, not crash."""
    llm = _make_llm_returning(
        {
            "name": "plot_polynomial",
            "arguments": {"coefficients": [1, 0], "__class__": "evil"},
        }
    )
    figs = se.select_and_invoke_generator("anything", [], llm_client=llm)
    assert len(figs) == 1
