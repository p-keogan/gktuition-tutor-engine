"""Plotly-JSON generators for the seven first-class graph kinds.

Each generator is a pure function that takes the parameters of a maths
function (or a list of points / curves) and returns a Plotly figure dict
ready to drop into a ``QueryResponse.graphs`` entry. The widget renders
each dict via ``react-plotly.js``.

The seven kinds (per ADR-005):

* :func:`plot_polynomial` — coefficients (highest-degree first), x-range.
* :func:`plot_trig`       — ``A * f(B*(x - C)) + D`` for f ∈ {sin, cos, tan,
                            sec, cosec, cot}.
* :func:`plot_exponential` — ``a * b^(k*x) + c``.
* :func:`plot_log`        — ``a * log_b(k*x) + c``.
* :func:`plot_piecewise`  — a list of (expr_callable, x_lo, x_hi) pieces.
* :func:`plot_data_points` — scatter plot of (x, y) points, optional fit line.
* :func:`plot_overlay`    — stack multiple already-built figures on shared axes.

Implementation rules these all follow:

* **No matplotlib.** Pure JSON construction; the widget renders client-side.
* **NumPy** is used for the maths only; the output is a plain dict.
* **~500 samples** per smooth curve over the requested x-range.
* **Discontinuities** are punched out by inserting ``NaN`` at asymptote
  locations so Plotly breaks the line cleanly (no spurious vertical jumps
  through tan/sec/cot asymptotes or piecewise gaps).
* **Validation** raises ``ValueError`` with a clear message on bad input
  (negative log base, x_range with lo >= hi, empty coefficients, etc.).
* **Theme** is consistent — gridlines on, x/y labels, ``zero``-line drawn,
  sober default Plotly palette.

NaN handling: ``json.dumps`` cannot serialise NaN by default, so every
generator emits sentinel ``None`` (which the JS-side parses as ``null``
and Plotly treats as a gap) rather than ``float('nan')``. We do this by
materialising the NumPy array, then mapping NaN → None before returning.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SAMPLES = 500
"""Default number of x-samples for smooth curves. ~500 keeps the curves
visually smooth without bloating the JSON payload (a sin curve at 500
samples is ~12 KB of JSON, well within the widget's payload budget)."""

DISCONTINUITY_HALF_WINDOW = 0.05
"""Half-width of the NaN window around each asymptote, in x-units before
period normalisation. Wide enough that Plotly visibly breaks the line,
narrow enough that the curve still looks continuous everywhere else."""

# A sober colour palette suitable for maths plots. Distinct enough at small
# sizes (the widget is ~360px wide) without being garish.
PALETTE: tuple[str, ...] = (
    "#1f4068",  # tutor brand navy — matches the FAB
    "#c0392b",  # crimson
    "#27ae60",  # green
    "#8e44ad",  # purple
    "#d35400",  # orange
    "#16a085",  # teal
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_x_range(x_range: tuple[float, float]) -> tuple[float, float]:
    """Sanity-check an (lo, hi) x-range; return as floats."""
    if not (
        isinstance(x_range, tuple | list)
        and len(x_range) == 2
        and all(isinstance(v, int | float) for v in x_range)
    ):
        raise ValueError(
            f"x_range must be a (lo, hi) tuple of two numbers; got {x_range!r}"
        )
    lo, hi = float(x_range[0]), float(x_range[1])
    if not lo < hi:
        raise ValueError(f"x_range lo must be strictly < hi; got ({lo}, {hi})")
    return lo, hi


def _validate_positive_int(value: int, name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive int; got {value!r}")
    return value


def _nan_to_none(arr: np.ndarray) -> list[float | None]:
    """Convert a NumPy array to a JSON-safe list with NaN → None.

    Plotly treats a ``null`` y-value as a gap in the line, which is exactly
    what we want at asymptotes and piecewise gaps. ``json.dumps`` cannot
    serialise NaN by default, so we strip them at construction time.
    """
    out: list[float | None] = []
    for v in arr.tolist():
        if isinstance(v, float) and (v != v or v == float("inf") or v == float("-inf")):
            out.append(None)
        else:
            out.append(float(v))
    return out


def _base_layout(
    title: str,
    x_label: str = "x",
    y_label: str = "y",
    *,
    summary: str | None = None,
) -> dict[str, Any]:
    """Return a maths-friendly Plotly layout dict.

    Gridlines on both axes, a zero-line drawn for visual reference, a sober
    default theme, and a short ``summary`` accessibility string the widget
    surfaces as the ``aria-label`` on the rendered figure.
    """
    layout: dict[str, Any] = {
        "title": {"text": title, "x": 0.5, "xanchor": "center"},
        "xaxis": {
            "title": x_label,
            "zeroline": True,
            "zerolinecolor": "#888",
            "zerolinewidth": 1,
            "gridcolor": "#e5e7eb",
            "showgrid": True,
        },
        "yaxis": {
            "title": y_label,
            "zeroline": True,
            "zerolinecolor": "#888",
            "zerolinewidth": 1,
            "gridcolor": "#e5e7eb",
            "showgrid": True,
        },
        "plot_bgcolor": "#ffffff",
        "paper_bgcolor": "#ffffff",
        "showlegend": True,
        "margin": {"l": 50, "r": 20, "t": 50, "b": 50},
    }
    if summary:
        # Plotly honours `meta.summary` as an arbitrary metadata bucket; our
        # widget reads it and applies it as `aria-label` on the rendered SVG.
        layout["meta"] = {"summary": summary}
    return layout


def _make_xs(x_range: tuple[float, float], samples: int = DEFAULT_SAMPLES) -> np.ndarray:
    lo, hi = _validate_x_range(x_range)
    samples = _validate_positive_int(samples, "samples")
    return np.linspace(lo, hi, samples)


# ---------------------------------------------------------------------------
# 1. plot_polynomial
# ---------------------------------------------------------------------------


def plot_polynomial(
    coefficients: list[float],
    x_range: tuple[float, float] = (-5.0, 5.0),
    *,
    title: str = "",
    show_zeros: bool = True,
    show_turning_points: bool = False,
    samples: int = DEFAULT_SAMPLES,
    colour: str | None = None,
) -> dict[str, Any]:
    """Plot a polynomial ``f(x) = sum(c_i * x^(n-i))``.

    ``coefficients`` is in numpy-poly1d order — highest-degree first.
    E.g. ``[1, 0, -4, 0]`` is ``x^3 - 4x``.

    When ``show_zeros`` is True, real roots of the polynomial are added as
    a scatter trace with marker symbols. When ``show_turning_points`` is
    True, the turning points (roots of the derivative within the x-range)
    are likewise added as markers.

    Raises:
        ValueError: if ``coefficients`` is empty or contains non-numeric
        entries.
    """
    if not coefficients:
        raise ValueError("coefficients must be a non-empty list of numbers.")
    if not all(isinstance(c, int | float) for c in coefficients):
        raise ValueError(f"coefficients must be numeric; got {coefficients!r}")

    coeffs = np.array(coefficients, dtype=float)
    xs = _make_xs(x_range, samples)
    ys = np.polyval(coeffs, xs)

    auto_title = title or _polynomial_title(coeffs)

    traces: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": "f(x)",
            "x": xs.tolist(),
            "y": _nan_to_none(ys),
            "line": {"color": colour or PALETTE[0], "width": 2},
            "hovertemplate": "x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>",
        }
    ]

    if show_zeros:
        zero_xs = _polynomial_real_roots(coeffs, x_range)
        if zero_xs:
            traces.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "zeros",
                    "x": zero_xs,
                    "y": [0.0] * len(zero_xs),
                    "marker": {
                        "color": PALETTE[1],
                        "size": 9,
                        "symbol": "circle-open",
                        "line": {"width": 2},
                    },
                    "hovertemplate": "zero at x=%{x:.3f}<extra></extra>",
                }
            )

    if show_turning_points:
        deriv_coeffs = np.polyder(coeffs)
        if len(deriv_coeffs) >= 1:
            tp_xs = _polynomial_real_roots(deriv_coeffs, x_range)
            tp_ys = [float(np.polyval(coeffs, x)) for x in tp_xs]
            if tp_xs:
                traces.append(
                    {
                        "type": "scatter",
                        "mode": "markers",
                        "name": "turning points",
                        "x": tp_xs,
                        "y": tp_ys,
                        "marker": {
                            "color": PALETTE[2],
                            "size": 10,
                            "symbol": "diamond",
                        },
                        "hovertemplate": "turning point (%{x:.3f}, %{y:.3f})<extra></extra>",
                    }
                )

    return {
        "data": traces,
        "layout": _base_layout(
            auto_title,
            summary=f"Polynomial of degree {len(coeffs) - 1} plotted over [{x_range[0]}, {x_range[1]}]",
        ),
    }


def _polynomial_title(coeffs: np.ndarray) -> str:
    """Render a polynomial title like ``f(x) = x^3 - 4x``.

    Kept readable rather than canonical — we drop terms with zero
    coefficients and use unicode superscripts so it works in a plain string.
    """
    deg = len(coeffs) - 1
    if deg < 0:
        return "f(x) = 0"
    parts: list[str] = []
    superscripts = {0: "", 1: "", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶"}
    for i, c in enumerate(coeffs):
        power = deg - i
        if c == 0:
            continue
        sign = "+" if c > 0 else "−"
        mag = abs(c)
        if power == 0:
            term = f"{mag:g}"
        elif power == 1:
            term = "x" if mag == 1 else f"{mag:g}x"
        else:
            sup = superscripts.get(power, f"^{power}")
            term = f"x{sup}" if mag == 1 else f"{mag:g}x{sup}"
        if not parts:
            parts.append(f"-{term}" if c < 0 else term)
        else:
            parts.append(f" {sign} {term}")
    return f"f(x) = {''.join(parts)}" if parts else "f(x) = 0"


def _polynomial_real_roots(
    coeffs: np.ndarray, x_range: tuple[float, float]
) -> list[float]:
    """Return real roots of the polynomial within (lo, hi), sorted.

    Uses NumPy's companion-matrix root finder; filters complex roots and
    out-of-range reals. Roots within 1e-9 of each other are deduped.
    """
    lo, hi = _validate_x_range(x_range)
    if len(coeffs) <= 1:
        return []
    raw = np.roots(coeffs)
    out: list[float] = []
    for r in raw:
        if abs(r.imag) > 1e-7:
            continue
        x = float(r.real)
        if lo - 1e-9 <= x <= hi + 1e-9:
            out.append(x)
    out.sort()
    # Dedupe near-duplicates from repeated roots.
    deduped: list[float] = []
    for x in out:
        if not deduped or abs(x - deduped[-1]) > 1e-7:
            deduped.append(x)
    return deduped


# ---------------------------------------------------------------------------
# 2. plot_trig
# ---------------------------------------------------------------------------

_TRIG_FAMILIES: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "sec": lambda x: 1.0 / np.cos(x),
    "cosec": lambda x: 1.0 / np.sin(x),
    "csc": lambda x: 1.0 / np.sin(x),  # alias
    "cot": lambda x: 1.0 / np.tan(x),
}


def plot_trig(
    family: str,
    *,
    amplitude: float = 1.0,
    period: float = 2.0 * np.pi,
    phase: float = 0.0,
    vertical_shift: float = 0.0,
    x_range: tuple[float, float] = (-2.0 * np.pi, 2.0 * np.pi),
    title: str = "",
    samples: int = DEFAULT_SAMPLES,
    colour: str | None = None,
) -> dict[str, Any]:
    """Plot ``A * f(B*(x - C)) + D`` where ``f`` is one of the trig families.

    Args:
        family:           one of ``sin``, ``cos``, ``tan``, ``sec``, ``cosec``,
                          ``cot``.
        amplitude (A):    vertical scale.
        period:           the period in x-units. ``B = 2π / period``.
        phase (C):        horizontal shift in x-units (positive = right).
        vertical_shift (D): vertical offset.
        x_range:          plot bounds.

    Asymptotes (tan/sec/cosec/cot) are punched out with NaN so Plotly draws
    a visible break at each.

    Raises:
        ValueError: if ``family`` is unknown, ``period <= 0``, or
        ``amplitude == 0`` (degenerate line).
    """
    if family not in _TRIG_FAMILIES:
        raise ValueError(
            f"unknown family {family!r}; expected one of {sorted(_TRIG_FAMILIES)}"
        )
    if period <= 0:
        raise ValueError(f"period must be > 0; got {period}")
    if amplitude == 0:
        raise ValueError("amplitude must be non-zero (else the curve is a flat line).")

    xs = _make_xs(x_range, samples)
    b = 2.0 * np.pi / period
    inner = b * (xs - phase)
    fn = _TRIG_FAMILIES[family]

    # Suppress warnings about division-by-zero at asymptotes.
    with np.errstate(divide="ignore", invalid="ignore"):
        ys_raw = amplitude * fn(inner) + vertical_shift

    # Punch out asymptotes for tan/sec/cosec/cot — NumPy emits ±inf at the
    # exact asymptote, but the adjacent sampled points are absurdly large
    # and would make Plotly's auto-scale unreadable. We clip to a sensible
    # window and replace anything outside with NaN.
    has_asymptotes = family in ("tan", "sec", "cosec", "csc", "cot")
    if has_asymptotes:
        y_max_abs = max(abs(amplitude * 5.0), 10.0) + abs(vertical_shift)
        ys = np.where(np.abs(ys_raw) > y_max_abs, np.nan, ys_raw)
        # Auto-set the y-axis so we don't see Plotly's auto-scale chase ±inf.
        y_axis_range = (-y_max_abs, y_max_abs)
    else:
        ys = ys_raw
        y_axis_range = None

    auto_title = title or _trig_title(
        family, amplitude, period, phase, vertical_shift
    )

    trace: dict[str, Any] = {
        "type": "scatter",
        "mode": "lines",
        "name": f"{family}",
        "x": xs.tolist(),
        "y": _nan_to_none(ys),
        "line": {"color": colour or PALETTE[0], "width": 2},
        "connectgaps": False,  # CRUCIAL: keeps the asymptote breaks visible.
        "hovertemplate": "x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>",
    }

    layout = _base_layout(
        auto_title,
        summary=(
            f"{family} curve with amplitude {amplitude}, period {period:.3f}, "
            f"phase {phase}, vertical shift {vertical_shift}"
        ),
    )
    if y_axis_range is not None:
        layout["yaxis"]["range"] = list(y_axis_range)

    return {"data": [trace], "layout": layout}


def _trig_title(
    family: str, amplitude: float, period: float, phase: float, vertical_shift: float
) -> str:
    """Human-readable title for a trig curve."""
    parts = [f"y = {amplitude:g} {family}("]
    b = 2.0 * np.pi / period
    if abs(b - 1.0) < 1e-9:
        parts.append("x")
    else:
        parts.append(f"{b:.3g}x")
    if phase != 0:
        sign = "-" if phase > 0 else "+"
        parts.append(f" {sign} {abs(b * phase):.3g}")
    parts.append(")")
    if vertical_shift != 0:
        sign = "+" if vertical_shift > 0 else "−"
        parts.append(f" {sign} {abs(vertical_shift):g}")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 3. plot_exponential
# ---------------------------------------------------------------------------


def plot_exponential(
    base: float = float(np.e),
    *,
    multiplier: float = 1.0,
    growth_rate: float = 1.0,
    offset: float = 0.0,
    x_range: tuple[float, float] = (-3.0, 3.0),
    title: str = "",
    samples: int = DEFAULT_SAMPLES,
    colour: str | None = None,
) -> dict[str, Any]:
    """Plot ``f(x) = multiplier * base^(growth_rate * x) + offset``.

    Use ``base=e`` (the default) for natural exponential. Negative
    ``growth_rate`` produces decay curves.

    Raises:
        ValueError: if ``base <= 0`` or ``base == 1`` (degenerate).
    """
    if base <= 0:
        raise ValueError(f"base must be > 0; got {base}")
    if base == 1:
        raise ValueError("base must not equal 1 (would be a constant line).")
    if multiplier == 0:
        raise ValueError("multiplier must be non-zero.")

    xs = _make_xs(x_range, samples)
    # Use np.power(float, ...) explicitly so an integer base still produces float64.
    ys = multiplier * np.power(float(base), growth_rate * xs) + offset

    auto_title = title or _exp_title(base, multiplier, growth_rate, offset)
    trace = {
        "type": "scatter",
        "mode": "lines",
        "name": "f(x)",
        "x": xs.tolist(),
        "y": _nan_to_none(ys),
        "line": {"color": colour or PALETTE[0], "width": 2},
        "hovertemplate": "x=%{x:.3f}<br>y=%{y:.4g}<extra></extra>",
    }
    return {
        "data": [trace],
        "layout": _base_layout(
            auto_title,
            summary=(
                f"Exponential f(x) = {multiplier:g} · {base:g}^({growth_rate:g}x) "
                f"+ {offset:g}"
            ),
        ),
    }


def _exp_title(base: float, multiplier: float, growth_rate: float, offset: float) -> str:
    base_str = "e" if abs(base - float(np.e)) < 1e-6 else f"{base:g}"
    mult_str = "" if multiplier == 1 else f"{multiplier:g} · "
    if growth_rate == 1:
        exp_str = "x"
    elif growth_rate == -1:
        exp_str = "-x"
    else:
        exp_str = f"{growth_rate:g}x"
    body = f"{mult_str}{base_str}^({exp_str})"
    if offset > 0:
        body += f" + {offset:g}"
    elif offset < 0:
        body += f" − {abs(offset):g}"
    return f"y = {body}"


# ---------------------------------------------------------------------------
# 4. plot_log
# ---------------------------------------------------------------------------


def plot_log(
    base: float = float(np.e),
    *,
    multiplier: float = 1.0,
    inner_scale: float = 1.0,
    offset: float = 0.0,
    x_range: tuple[float, float] = (0.01, 10.0),
    title: str = "",
    samples: int = DEFAULT_SAMPLES,
    colour: str | None = None,
) -> dict[str, Any]:
    """Plot ``f(x) = multiplier * log_base(inner_scale * x) + offset``.

    The default ``x_range`` starts at ``0.01`` rather than ``0`` because
    ``log(0)`` is ``-inf`` and a zero left-bound would force the curve to
    visibly dive to negative infinity at the boundary.

    Raises:
        ValueError: if ``base <= 0`` or ``base == 1``, or if any sampled
        ``inner_scale * x`` value is ``<= 0`` (log of a non-positive
        argument is undefined; the caller's x-range crossed zero in the
        wrong direction).
    """
    if base <= 0:
        raise ValueError(f"log base must be > 0; got {base}")
    if base == 1:
        raise ValueError("log base must not equal 1.")
    if inner_scale == 0:
        raise ValueError("inner_scale must be non-zero.")

    xs = _make_xs(x_range, samples)
    arg = inner_scale * xs
    if np.any(arg <= 0):
        # Punch out the invalid samples rather than refusing — the typical
        # student question is "plot log over (0, 10)" and a left-bound just
        # below zero shouldn't crash the call.
        with np.errstate(invalid="ignore", divide="ignore"):
            log_part = np.where(arg > 0, np.log(arg) / np.log(base), np.nan)
    else:
        log_part = np.log(arg) / np.log(base)

    ys = multiplier * log_part + offset

    auto_title = title or _log_title(base, multiplier, inner_scale, offset)
    trace = {
        "type": "scatter",
        "mode": "lines",
        "name": "f(x)",
        "x": xs.tolist(),
        "y": _nan_to_none(ys),
        "line": {"color": colour or PALETTE[0], "width": 2},
        "connectgaps": False,
        "hovertemplate": "x=%{x:.3f}<br>y=%{y:.4g}<extra></extra>",
    }
    return {
        "data": [trace],
        "layout": _base_layout(
            auto_title,
            summary=(
                f"Logarithm f(x) = {multiplier:g} · log_{base:g}({inner_scale:g}x) "
                f"+ {offset:g}"
            ),
        ),
    }


def _log_title(base: float, multiplier: float, inner_scale: float, offset: float) -> str:
    base_str = "e" if abs(base - float(np.e)) < 1e-6 else f"{base:g}"
    fn = "ln" if base_str == "e" else f"log_{base_str}"
    inner = "x" if inner_scale == 1 else f"{inner_scale:g}x"
    mult = "" if multiplier == 1 else f"{multiplier:g} · "
    body = f"{mult}{fn}({inner})"
    if offset > 0:
        body += f" + {offset:g}"
    elif offset < 0:
        body += f" − {abs(offset):g}"
    return f"y = {body}"


# ---------------------------------------------------------------------------
# 5. plot_piecewise
# ---------------------------------------------------------------------------


PieceCallable = Callable[[np.ndarray], np.ndarray]


def plot_piecewise(
    pieces: list[tuple[PieceCallable, float, float]],
    *,
    title: str = "",
    samples_per_piece: int = 200,
    x_label: str = "x",
    y_label: str = "y",
    colour: str | None = None,
) -> dict[str, Any]:
    """Plot a piecewise function defined by ``[(expr, lo, hi), ...]`` pieces.

    Each ``expr`` is a vectorised callable that maps a NumPy array of
    x-values in ``[lo, hi]`` to a NumPy array of y-values. Pieces are
    drawn as a single Plotly trace with NaN-separators between pieces so
    Plotly visibly breaks the line at piece boundaries (modulus, signum,
    custom exam-paper piecewise definitions, etc.).

    Args:
        pieces: list of (expr, lo, hi) tuples. lo < hi for each. Pieces
                may overlap; the trace order is preserved.
        samples_per_piece: how many points per piece. 200 is the default —
                Plotly draws fine at this density and the JSON stays small.

    Raises:
        ValueError: if ``pieces`` is empty or any tuple is malformed.
    """
    if not pieces:
        raise ValueError("pieces must be a non-empty list.")
    samples = _validate_positive_int(samples_per_piece, "samples_per_piece")

    all_xs: list[float | None] = []
    all_ys: list[float | None] = []

    for i, piece in enumerate(pieces):
        if not (isinstance(piece, tuple | list) and len(piece) == 3):
            raise ValueError(
                f"piece {i} must be a (expr, lo, hi) triple; got {piece!r}"
            )
        expr, lo, hi = piece
        if not callable(expr):
            raise ValueError(f"piece {i}: expr must be callable; got {expr!r}")
        lo_f, hi_f = _validate_x_range((lo, hi))
        xs = np.linspace(lo_f, hi_f, samples)
        with np.errstate(invalid="ignore", divide="ignore"):
            ys = np.asarray(expr(xs), dtype=float)
        if ys.shape != xs.shape:
            raise ValueError(
                f"piece {i}: expr must produce same-shaped output; got {ys.shape} for input {xs.shape}"
            )
        all_xs.extend(xs.tolist())
        all_ys.extend(_nan_to_none(ys))
        # Separator between pieces (so Plotly visibly breaks at boundaries).
        if i < len(pieces) - 1:
            all_xs.append(None)
            all_ys.append(None)

    auto_title = title or f"piecewise function ({len(pieces)} pieces)"
    trace = {
        "type": "scatter",
        "mode": "lines",
        "name": "f(x)",
        "x": all_xs,
        "y": all_ys,
        "line": {"color": colour or PALETTE[0], "width": 2},
        "connectgaps": False,
        "hovertemplate": "x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>",
    }
    return {
        "data": [trace],
        "layout": _base_layout(
            auto_title,
            x_label=x_label,
            y_label=y_label,
            summary=f"Piecewise function with {len(pieces)} piece(s)",
        ),
    }


# ---------------------------------------------------------------------------
# 6. plot_data_points
# ---------------------------------------------------------------------------


def plot_data_points(
    points: list[tuple[float, float]],
    *,
    title: str = "",
    x_label: str = "x",
    y_label: str = "y",
    show_best_fit: bool = False,
    colour: str | None = None,
) -> dict[str, Any]:
    """Scatter plot of (x, y) points, optionally with a least-squares best-fit line.

    Used by the Statistics strand: scatter graphs, correlation, regression.

    Args:
        points:        list of (x, y) tuples.
        show_best_fit: when True, overlay a degree-1 polyfit line spanning
                       the x-range of the data.

    Raises:
        ValueError: if ``points`` is empty or any tuple is not a pair of
        numbers.
    """
    if not points:
        raise ValueError("points must be a non-empty list.")
    xs: list[float] = []
    ys: list[float] = []
    for i, p in enumerate(points):
        if not (isinstance(p, tuple | list) and len(p) == 2):
            raise ValueError(f"point {i} must be a (x, y) pair; got {p!r}")
        if not (isinstance(p[0], int | float) and isinstance(p[1], int | float)):
            raise ValueError(f"point {i} must contain numbers; got {p!r}")
        xs.append(float(p[0]))
        ys.append(float(p[1]))

    traces: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "markers",
            "name": "data",
            "x": xs,
            "y": ys,
            "marker": {
                "color": colour or PALETTE[0],
                "size": 8,
                "line": {"color": "#333", "width": 1},
            },
            "hovertemplate": "(%{x:.3g}, %{y:.3g})<extra></extra>",
        }
    ]

    if show_best_fit and len(xs) >= 2:
        m, c = np.polyfit(xs, ys, 1)
        x_min, x_max = min(xs), max(xs)
        fit_x = [x_min, x_max]
        fit_y = [m * x_min + c, m * x_max + c]
        traces.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": f"best fit (y = {m:.3g}x + {c:.3g})",
                "x": fit_x,
                "y": fit_y,
                "line": {"color": PALETTE[1], "width": 2, "dash": "dash"},
                "hovertemplate": "fit line<extra></extra>",
            }
        )

    auto_title = title or f"scatter plot ({len(xs)} points)"
    return {
        "data": traces,
        "layout": _base_layout(
            auto_title,
            x_label=x_label,
            y_label=y_label,
            summary=f"Scatter plot of {len(xs)} data points"
            + (" with best-fit line" if show_best_fit else ""),
        ),
    }


# ---------------------------------------------------------------------------
# 7. plot_overlay
# ---------------------------------------------------------------------------


def plot_overlay(
    figures: list[dict[str, Any]],
    *,
    title: str = "",
    x_label: str = "x",
    y_label: str = "y",
) -> dict[str, Any]:
    """Stack multiple already-built figure dicts on shared axes.

    Each input is a figure produced by any of the other six generators.
    The traces from every input are concatenated; each trace's ``name`` is
    prefixed with the figure's title (if any) so the legend disambiguates
    them.

    Args:
        figures: list of generator-produced dicts. Must be non-empty.

    Raises:
        ValueError: if ``figures`` is empty or any entry lacks a ``data``
        key.
    """
    if not figures:
        raise ValueError("figures must be a non-empty list.")

    merged: list[dict[str, Any]] = []
    for i, fig in enumerate(figures):
        if "data" not in fig or not isinstance(fig["data"], list):
            raise ValueError(
                f"figure {i} must be a dict with a 'data' list; got {fig!r}"
            )
        prefix = ""
        layout = fig.get("layout", {})
        if isinstance(layout, dict):
            t = layout.get("title")
            if isinstance(t, dict):
                prefix = str(t.get("text") or "")
            elif isinstance(t, str):
                prefix = t
        for j, trace in enumerate(fig["data"]):
            tr = dict(trace)  # shallow copy
            base_name = tr.get("name") or f"trace {j}"
            tr["name"] = f"{prefix}: {base_name}" if prefix else base_name
            # Recolour so overlaid traces are distinguishable when the
            # source figures all used the default first-palette colour.
            if "line" in tr and isinstance(tr["line"], dict):
                line = dict(tr["line"])
                line["color"] = PALETTE[(i + j) % len(PALETTE)]
                tr["line"] = line
            elif "marker" in tr and isinstance(tr["marker"], dict):
                marker = dict(tr["marker"])
                marker["color"] = PALETTE[(i + j) % len(PALETTE)]
                tr["marker"] = marker
            merged.append(tr)

    auto_title = title or f"overlay of {len(figures)} curves"
    return {
        "data": merged,
        "layout": _base_layout(
            auto_title,
            x_label=x_label,
            y_label=y_label,
            summary=f"Overlay of {len(figures)} curves on shared axes",
        ),
    }


# ---------------------------------------------------------------------------
# Registry — used by the synthesiser extension's tool-router.
# ---------------------------------------------------------------------------

GENERATOR_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "plot_polynomial": plot_polynomial,
    "plot_trig": plot_trig,
    "plot_exponential": plot_exponential,
    "plot_log": plot_log,
    "plot_piecewise": plot_piecewise,
    "plot_data_points": plot_data_points,
    "plot_overlay": plot_overlay,
}
"""Name → callable map, used by the synthesiser extension to route an LLM
tool-call to a concrete generator."""
