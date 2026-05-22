"""Unit tests for every generator in :mod:`api.visualisation.generators`.

Each test asserts the output shape (trace count, sample-point count, axis
labels, NaN propagation at discontinuities) rather than rendered pixels —
the Plotly JSON is the contract the widget consumes. Spot-checking the
visual appearance is deferred to the smoke test in AGENT_13_DELIVERY.md
verification step 2.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from api.visualisation import generators
from api.visualisation.generators import (
    DEFAULT_SAMPLES,
    plot_data_points,
    plot_exponential,
    plot_log,
    plot_overlay,
    plot_piecewise,
    plot_polynomial,
    plot_trig,
)


# ---------------------------------------------------------------------------
# plot_polynomial — 6 tests
# ---------------------------------------------------------------------------


def test_polynomial_quadratic_shape() -> None:
    fig = plot_polynomial([1, 0, -4])  # x^2 - 4
    assert isinstance(fig, dict)
    assert "data" in fig and "layout" in fig
    assert fig["layout"]["xaxis"]["title"] == "x"
    assert fig["layout"]["yaxis"]["title"] == "y"
    # 1 line trace + 1 zeros trace (default show_zeros=True)
    assert len(fig["data"]) == 2
    line = fig["data"][0]
    assert len(line["x"]) == DEFAULT_SAMPLES
    assert len(line["y"]) == DEFAULT_SAMPLES
    # The line is fully finite (a polynomial has no NaN over a finite range).
    assert all(v is not None for v in line["y"])


def test_polynomial_quadratic_zeros_found() -> None:
    fig = plot_polynomial([1, 0, -4], x_range=(-5, 5), show_zeros=True)
    # x^2 - 4 has roots at -2 and +2.
    zeros_trace = fig["data"][1]
    assert zeros_trace["mode"] == "markers"
    zs = sorted(zeros_trace["x"])
    assert math.isclose(zs[0], -2.0, abs_tol=1e-6)
    assert math.isclose(zs[1], 2.0, abs_tol=1e-6)


def test_polynomial_cubic_with_turning_points() -> None:
    # x^3 - 3x has turning points at x=±1
    fig = plot_polynomial([1, 0, -3, 0], show_turning_points=True, show_zeros=False)
    assert len(fig["data"]) == 2  # line + turning points
    tps = fig["data"][1]
    assert tps["name"] == "turning points"
    xs = sorted(tps["x"])
    assert math.isclose(xs[0], -1.0, abs_tol=1e-6)
    assert math.isclose(xs[1], 1.0, abs_tol=1e-6)


def test_polynomial_title_autogen() -> None:
    fig = plot_polynomial([1, 0, -4])
    assert "f(x)" in fig["layout"]["title"]["text"]


def test_polynomial_empty_coefficients_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        plot_polynomial([])


def test_polynomial_non_numeric_coefficients_raises() -> None:
    with pytest.raises(ValueError, match="numeric"):
        plot_polynomial([1, "x", 3])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# plot_trig — 7 tests
# ---------------------------------------------------------------------------


def test_trig_sin_default_shape() -> None:
    fig = plot_trig("sin")
    assert len(fig["data"]) == 1
    trace = fig["data"][0]
    assert len(trace["x"]) == DEFAULT_SAMPLES
    assert all(v is not None for v in trace["y"])


def test_trig_sin_amplitude_period_phase_shift() -> None:
    # y = 2 sin(2(x - π/4)) + 1
    fig = plot_trig(
        "sin", amplitude=2.0, period=math.pi, phase=math.pi / 4, vertical_shift=1.0
    )
    # Max should be 2*1 + 1 = 3; min = 2*-1 + 1 = -1
    ys = [y for y in fig["data"][0]["y"] if y is not None]
    assert max(ys) == pytest.approx(3.0, abs=0.05)
    assert min(ys) == pytest.approx(-1.0, abs=0.05)


def test_trig_tan_has_nan_at_asymptotes() -> None:
    # tan(x) over (-π, π) has an asymptote at ±π/2 → expect None entries.
    fig = plot_trig("tan", x_range=(-math.pi, math.pi))
    ys = fig["data"][0]["y"]
    assert any(v is None for v in ys), "tan plot must include NaN/None at asymptotes"
    assert fig["data"][0]["connectgaps"] is False


def test_trig_sec_has_nan_at_asymptotes() -> None:
    fig = plot_trig("sec", x_range=(-math.pi, math.pi))
    ys = fig["data"][0]["y"]
    assert any(v is None for v in ys)


def test_trig_unknown_family_raises() -> None:
    with pytest.raises(ValueError, match="unknown family"):
        plot_trig("snake")


def test_trig_zero_amplitude_raises() -> None:
    with pytest.raises(ValueError, match="amplitude"):
        plot_trig("sin", amplitude=0)


def test_trig_negative_period_raises() -> None:
    with pytest.raises(ValueError, match="period"):
        plot_trig("sin", period=-1)


# ---------------------------------------------------------------------------
# plot_exponential — 5 tests
# ---------------------------------------------------------------------------


def test_exponential_e_default_growth() -> None:
    fig = plot_exponential()
    assert len(fig["data"]) == 1
    ys = fig["data"][0]["y"]
    # e^x is monotonically increasing
    assert ys[0] < ys[-1]


def test_exponential_decay() -> None:
    fig = plot_exponential(base=math.e, growth_rate=-1.0)
    ys = fig["data"][0]["y"]
    assert ys[0] > ys[-1]


def test_exponential_base_2_at_zero_equals_offset_plus_multiplier() -> None:
    # f(0) = multiplier * base^0 + offset = multiplier + offset
    fig = plot_exponential(base=2.0, multiplier=3.0, offset=5.0, x_range=(-1, 1))
    xs = fig["data"][0]["x"]
    ys = fig["data"][0]["y"]
    # Find sample nearest to 0
    idx = min(range(len(xs)), key=lambda i: abs(xs[i]))
    assert ys[idx] == pytest.approx(8.0, abs=0.1)


def test_exponential_invalid_base_raises() -> None:
    with pytest.raises(ValueError, match="base"):
        plot_exponential(base=-2.0)
    with pytest.raises(ValueError, match="base"):
        plot_exponential(base=1.0)


def test_exponential_zero_multiplier_raises() -> None:
    with pytest.raises(ValueError, match="multiplier"):
        plot_exponential(multiplier=0)


# ---------------------------------------------------------------------------
# plot_log — 5 tests
# ---------------------------------------------------------------------------


def test_log_default_natural() -> None:
    fig = plot_log()
    assert len(fig["data"]) == 1
    ys = [y for y in fig["data"][0]["y"] if y is not None]
    # ln(1) = 0
    assert any(abs(y) < 0.1 for y in ys)


def test_log_base_10_at_x_equals_1_is_zero() -> None:
    fig = plot_log(base=10.0, x_range=(0.5, 2.0))
    xs = fig["data"][0]["x"]
    ys = fig["data"][0]["y"]
    idx = min(range(len(xs)), key=lambda i: abs(xs[i] - 1.0))
    assert ys[idx] == pytest.approx(0.0, abs=0.05)


def test_log_negative_x_range_punches_nan() -> None:
    # Crossing zero from the left → log undefined; we punch NaN, not crash.
    fig = plot_log(x_range=(-1.0, 5.0))
    ys = fig["data"][0]["y"]
    assert any(v is None for v in ys)


def test_log_invalid_base_raises() -> None:
    with pytest.raises(ValueError, match="base"):
        plot_log(base=-1.0)
    with pytest.raises(ValueError, match="base"):
        plot_log(base=1.0)


def test_log_zero_inner_scale_raises() -> None:
    with pytest.raises(ValueError, match="inner_scale"):
        plot_log(inner_scale=0)


# ---------------------------------------------------------------------------
# plot_piecewise — 4 tests
# ---------------------------------------------------------------------------


def test_piecewise_modulus_two_pieces() -> None:
    fig = plot_piecewise([
        (lambda x: -x, -5, 0),
        (lambda x: x, 0, 5),
    ])
    assert len(fig["data"]) == 1
    trace = fig["data"][0]
    # Each piece is 200 points; with a None separator that's 200+1+200 = 401 entries.
    assert len(trace["x"]) == 401
    # Separator None at index 200
    assert trace["x"][200] is None
    assert trace["y"][200] is None
    assert trace["connectgaps"] is False


def test_piecewise_single_piece() -> None:
    fig = plot_piecewise([(lambda x: x**2, -2, 2)])
    trace = fig["data"][0]
    # 200 samples, no separator (only one piece).
    assert len(trace["x"]) == 200


def test_piecewise_empty_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        plot_piecewise([])


def test_piecewise_malformed_piece_raises() -> None:
    with pytest.raises(ValueError, match="triple"):
        plot_piecewise([(lambda x: x, 0)])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# plot_data_points — 4 tests
# ---------------------------------------------------------------------------


def test_data_points_basic_scatter() -> None:
    pts = [(1, 2), (2, 4), (3, 6), (4, 8)]
    fig = plot_data_points(pts)
    assert len(fig["data"]) == 1
    trace = fig["data"][0]
    assert trace["mode"] == "markers"
    assert trace["x"] == [1.0, 2.0, 3.0, 4.0]
    assert trace["y"] == [2.0, 4.0, 6.0, 8.0]


def test_data_points_with_best_fit() -> None:
    pts = [(1, 2), (2, 4), (3, 6), (4, 8)]
    fig = plot_data_points(pts, show_best_fit=True)
    assert len(fig["data"]) == 2
    fit = fig["data"][1]
    assert fit["mode"] == "lines"
    # y = 2x, so endpoints should be (1, 2) and (4, 8)
    assert fit["y"][0] == pytest.approx(2.0, abs=0.05)
    assert fit["y"][1] == pytest.approx(8.0, abs=0.05)


def test_data_points_empty_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        plot_data_points([])


def test_data_points_malformed_pair_raises() -> None:
    with pytest.raises(ValueError, match="pair"):
        plot_data_points([(1,)])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# plot_overlay — 4 tests
# ---------------------------------------------------------------------------


def test_overlay_two_polynomials() -> None:
    f1 = plot_polynomial([1, 0, 0], show_zeros=False)  # y = x^2
    f2 = plot_polynomial([1, 0, 0, 0], show_zeros=False)  # y = x^3
    fig = plot_overlay([f1, f2])
    assert len(fig["data"]) == 2
    assert fig["layout"]["xaxis"]["title"] == "x"


def test_overlay_recolours_traces_distinctly() -> None:
    f1 = plot_polynomial([1, 0, 0], show_zeros=False)
    f2 = plot_polynomial([1, 0, 0], show_zeros=False)  # same poly
    fig = plot_overlay([f1, f2])
    c1 = fig["data"][0]["line"]["color"]
    c2 = fig["data"][1]["line"]["color"]
    assert c1 != c2, "overlay must recolour each trace distinctly"


def test_overlay_empty_raises() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        plot_overlay([])


def test_overlay_malformed_input_raises() -> None:
    with pytest.raises(ValueError, match="'data' list"):
        plot_overlay([{"layout": {}}])


# ---------------------------------------------------------------------------
# JSON-serialisability and cross-generator invariants — 3 tests
# ---------------------------------------------------------------------------


def test_every_generator_returns_json_serialisable_output() -> None:
    """Every generator's output must round-trip through json.dumps."""
    cases = [
        plot_polynomial([1, 0, -4]),
        plot_trig("sin"),
        plot_trig("tan", x_range=(-math.pi, math.pi)),  # has NaN → None
        plot_exponential(),
        plot_log(),
        plot_piecewise([(lambda x: x, -1, 1)]),
        plot_data_points([(1, 2), (3, 4)], show_best_fit=True),
        plot_overlay([plot_polynomial([1, -1])]),
    ]
    for i, fig in enumerate(cases):
        try:
            json.dumps(fig)
        except (ValueError, TypeError) as exc:
            raise AssertionError(f"figure {i} not JSON-serialisable: {exc}") from exc


def test_every_generator_has_consistent_layout_keys() -> None:
    """Every figure must carry the shared layout shape."""
    figures = [
        plot_polynomial([1, 0]),
        plot_trig("cos"),
        plot_exponential(),
        plot_log(),
        plot_piecewise([(lambda x: x, 0, 1)]),
        plot_data_points([(1, 1)]),
        plot_overlay([plot_polynomial([1])]),
    ]
    for fig in figures:
        layout = fig["layout"]
        assert "title" in layout
        assert "xaxis" in layout
        assert "yaxis" in layout
        assert layout["showlegend"] is True
        assert layout["meta"]["summary"]


def test_nan_to_none_helper_handles_edge_cases() -> None:
    arr = np.array([1.0, np.nan, float("inf"), float("-inf"), 2.5])
    out = generators._nan_to_none(arr)
    assert out == [1.0, None, None, None, 2.5]
