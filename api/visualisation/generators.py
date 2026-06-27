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
# 1b. plot_quadratic_inequality
# ---------------------------------------------------------------------------
#
# Quadratic inequalities (Algebra strand) are taught as a sketch-and-shade
# method: factorise → sketch the parabola → read off the region(s) of x where
# the inequality holds. A bare parabola plot doesn't carry the answer; the
# *shaded solution region* is the point. This generator draws the parabola and
# shades the x-interval(s) that satisfy the inequality, marks the roots
# open/closed for strict/non-strict, and annotates the solution set. The region
# is computed deterministically from the coefficients + operator — the LLM
# tool-router only supplies those two facts, never the region maths.

# Operator spellings the router (or a tutorial snippet) might emit, normalised
# to one of the four canonical forms.
_INEQ_OPERATORS = {
    "<": "<",
    "<=": "<=",
    "=<": "<=",
    "≤": "<=",  # ≤
    ">": ">",
    ">=": ">=",
    "=>": ">=",
    "≥": ">=",  # ≥
}


def _normalise_operator(operator: str) -> str:
    op = str(operator).strip().replace(" ", "")
    if op not in _INEQ_OPERATORS:
        raise ValueError(
            f"operator must be one of <, <=, >, >= (or ≤/≥); got {operator!r}"
        )
    return _INEQ_OPERATORS[op]


def _quadratic_expr(a: float, b: float, c: float) -> str:
    """Render ``ax² + bx + c`` (drops zero/unit terms) for a title."""
    sup = "²"
    parts: list[str] = []
    # a·x²
    if a != 0:
        lead = "x" + sup if a == 1 else ("-x" + sup if a == -1 else f"{a:g}x{sup}")
        parts.append(lead)
    # b·x
    if b != 0:
        sign = "+" if b > 0 else "−"
        mag = abs(b)
        term = "x" if mag == 1 else f"{mag:g}x"
        parts.append(f" {sign} {term}" if parts else (f"-{term}" if b < 0 else term))
    # c
    if c != 0:
        sign = "+" if c > 0 else "−"
        parts.append(f" {sign} {abs(c):g}" if parts else f"{c:g}")
    return "".join(parts) if parts else "0"


def plot_quadratic_inequality(
    coefficients: list[float],
    operator: str,
    x_range: tuple[float, float] | None = None,
    *,
    title: str = "",
    samples: int = DEFAULT_SAMPLES,
) -> dict[str, Any]:
    """Plot a quadratic and shade where ``a x² + b x + c  [op]  0`` holds.

    Args:
        coefficients: ``[a, b, c]`` (highest-degree first). ``a`` must be
                      non-zero — this is a *quadratic* inequality generator.
        operator:     one of ``<``, ``<=``, ``>``, ``>=`` (``≤``/``≥`` accepted).
        x_range:      optional plot bounds. When omitted, a sensible window is
                      derived from the roots (or the vertex if there are none).

    The satisfying x-region(s) are shaded as vertical bands, the roots are
    marked (open circle for a strict inequality, filled for non-strict), and
    the solution set is annotated on the figure.

    Raises:
        ValueError: if ``coefficients`` is not ``[a, b, c]`` with ``a != 0``,
        or ``operator`` is unrecognised.
    """
    if not (isinstance(coefficients, list | tuple) and len(coefficients) == 3):
        raise ValueError(
            f"coefficients must be [a, b, c] for a quadratic; got {coefficients!r}"
        )
    if not all(isinstance(c, int | float) for c in coefficients):
        raise ValueError(f"coefficients must be numeric; got {coefficients!r}")
    a, b, c = (float(coefficients[0]), float(coefficients[1]), float(coefficients[2]))
    if a == 0:
        raise ValueError("a (the x² coefficient) must be non-zero for a quadratic.")

    op = _normalise_operator(operator)
    strict = op in ("<", ">")
    want_negative = op in ("<", "<=")

    # --- Roots ----------------------------------------------------------------
    disc = b * b - 4.0 * a * c
    if disc > 0:
        sqrt_d = disc**0.5
        r1, r2 = sorted(((-b - sqrt_d) / (2 * a), (-b + sqrt_d) / (2 * a)))
        real_roots = [r1, r2]
    elif disc == 0:
        r1 = r2 = -b / (2 * a)
        real_roots = [r1]
    else:
        r1 = r2 = None
        real_roots = []

    # --- Plot window ----------------------------------------------------------
    if x_range is not None:
        lo, hi = _validate_x_range(x_range)
    elif r1 is not None and r2 is not None and r2 > r1:
        pad = max(r2 - r1, 1.0) * 0.8
        lo, hi = r1 - pad, r2 + pad
    elif r1 is not None:
        lo, hi = r1 - 3.0, r1 + 3.0
    else:
        vx = -b / (2 * a)
        lo, hi = vx - 4.0, vx + 4.0

    xs = _make_xs((lo, hi), samples)
    ys = np.polyval(np.array([a, b, c], dtype=float), xs)

    # --- Satisfying bands (sampled mask → contiguous intervals) ---------------
    mask = (ys < 0) if want_negative else (ys > 0)
    bands: list[tuple[float, float]] = []
    band_start: float | None = None
    for i, m in enumerate(mask):
        if m and band_start is None:
            band_start = float(xs[i])
        elif not m and band_start is not None:
            bands.append((band_start, float(xs[i - 1])))
            band_start = None
    if band_start is not None:
        bands.append((band_start, float(xs[-1])))

    shapes = [
        {
            "type": "rect",
            "xref": "x",
            "yref": "paper",
            "x0": bl,
            "x1": br,
            "y0": 0,
            "y1": 1,
            "fillcolor": "rgba(39, 174, 96, 0.18)",
            "line": {"width": 0},
            "layer": "below",
        }
        for (bl, br) in bands
    ]

    # --- Traces: the parabola + the roots -------------------------------------
    traces: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": "f(x)",
            "x": xs.tolist(),
            "y": _nan_to_none(ys),
            "line": {"color": PALETTE[0], "width": 2},
            "hovertemplate": "x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>",
        }
    ]
    if real_roots:
        traces.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": "roots",
                "x": [float(r) for r in real_roots],
                "y": [0.0] * len(real_roots),
                "marker": {
                    "color": PALETTE[1],
                    "size": 10,
                    # Open circle = boundary NOT included (strict); filled = included.
                    "symbol": "circle-open" if strict else "circle",
                    "line": {"width": 2, "color": PALETTE[1]},
                },
                "hovertemplate": "x=%{x:.3f}<extra></extra>",
            }
        )

    # --- Solution-set string --------------------------------------------------
    solution = _inequality_solution_text(a, op, strict, want_negative, r1, r2, disc)

    expr = _quadratic_expr(a, b, c)
    op_glyph = {"<": "<", "<=": "≤", ">": ">", ">=": "≥"}[op]
    auto_title = title or f"{expr} {op_glyph} 0"

    layout = _base_layout(
        auto_title,
        summary=f"Parabola y = {expr} with the region where {expr} {op_glyph} 0 shaded. Solution: {solution}.",
    )
    layout["shapes"] = shapes
    layout["annotations"] = [
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 1.0,
            "yanchor": "bottom",
            "showarrow": False,
            "text": f"Solution: {solution}",
            "font": {"size": 13, "color": PALETTE[2]},
        }
    ]
    return {"data": traces, "layout": layout}


def _inequality_solution_text(
    a: float,
    op: str,
    strict: bool,
    want_negative: bool,
    r1: float | None,
    r2: float | None,
    disc: float,
) -> str:
    """Human-readable solution set for the quadratic inequality."""
    # No real roots: the parabola never crosses zero, so f keeps the sign of a.
    if disc < 0 or r1 is None:
        f_positive_everywhere = a > 0
        satisfied = f_positive_everywhere == (not want_negative)
        return "all real x" if satisfied else "no real solutions"

    # Repeated root: f touches zero at one point and otherwise keeps sign(a).
    if disc == 0:
        r = r1
        f_positive_elsewhere = a > 0
        if want_negative:
            if f_positive_elsewhere:
                # f ≤ 0 only at the root; f < 0 nowhere.
                return f"x = {r:g}" if not strict else "no real solutions"
            return "all real x" if not strict else f"x ≠ {r:g}"
        else:  # want_positive
            if f_positive_elsewhere:
                return "all real x" if not strict else f"x ≠ {r:g}"
            return f"x = {r:g}" if not strict else "no real solutions"

    # Distinct roots r1 < r2. With a>0 the parabola is negative *between* the
    # roots; with a<0 it's positive between them.
    between_is_negative = a > 0
    region_between = (want_negative and between_is_negative) or (
        (not want_negative) and (not between_is_negative)
    )
    if region_between:
        return (
            f"{r1:g} < x < {r2:g}" if strict else f"{r1:g} ≤ x ≤ {r2:g}"
        )
    return (
        f"x < {r1:g} or x > {r2:g}"
        if strict
        else f"x ≤ {r1:g} or x ≥ {r2:g}"
    )


# ---------------------------------------------------------------------------
# 1c. plot_linear_inequality
# ---------------------------------------------------------------------------
#
# A one-variable linear inequality (e.g. ``2x - 3 > 5`` → ``x > 4``) has a ray
# for its solution set. The standard sketch is a number line with the
# satisfying ray shaded and the endpoint drawn open (strict ``<``/``>``) or
# filled (non-strict ``≤``/``≥``). Pass the SOLVED form: a boundary value and
# the operator relating ``x`` to it.


def plot_linear_inequality(
    boundary: float,
    operator: str,
    *,
    variable: str = "x",
    x_range: tuple[float, float] | None = None,
    title: str = "",
) -> dict[str, Any]:
    """Draw a number line shading where ``x [op] boundary`` holds.

    Args:
        boundary: the value ``x`` is compared to (e.g. ``4`` for ``x > 4``).
        operator: one of ``<``, ``<=``, ``>``, ``>=`` (``≤``/``≥`` accepted).
        variable: axis label / variable name (default ``"x"``).
        x_range:  optional bounds; a sensible window around the boundary is
                  used when omitted.

    Raises:
        ValueError: if ``boundary`` is non-numeric or ``operator`` unknown.
    """
    if not isinstance(boundary, int | float):
        raise ValueError(f"boundary must be a number; got {boundary!r}")
    b = float(boundary)
    op = _normalise_operator(operator)
    strict = op in ("<", ">")
    greater = op in (">", ">=")

    if x_range is not None:
        lo, hi = _validate_x_range(x_range)
    else:
        pad = max(4.0, abs(b) * 0.5)
        lo, hi = b - pad, b + pad

    band = (b, hi) if greater else (lo, b)
    ray_x = [b, hi] if greater else [lo, b]

    op_glyph = {"<": "<", "<=": "≤", ">": ">", ">=": "≥"}[op]
    solution = f"{variable} {op_glyph} {b:g}"

    traces: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": "number line",
            "x": [lo, hi],
            "y": [0.0, 0.0],
            "line": {"color": "#888", "width": 2},
            "hoverinfo": "skip",
        },
        {
            "type": "scatter",
            "mode": "lines",
            "name": "solution",
            "x": ray_x,
            "y": [0.0, 0.0],
            "line": {"color": PALETTE[0], "width": 6},
            "hovertemplate": f"{solution}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "markers",
            "name": "boundary",
            "x": [b],
            "y": [0.0],
            "marker": {
                "color": PALETTE[0],
                "size": 13,
                # Open circle = endpoint NOT included (strict); filled = included.
                "symbol": "circle-open" if strict else "circle",
                "line": {"width": 3, "color": PALETTE[0]},
            },
            "hovertemplate": f"{variable}={b:g}<extra></extra>",
        },
    ]

    layout = _base_layout(
        title or solution,
        x_label=variable,
        y_label="",
        summary=f"Number line with the solution {solution} shaded.",
    )
    layout["shapes"] = [
        {
            "type": "rect",
            "xref": "x",
            "yref": "paper",
            "x0": band[0],
            "x1": band[1],
            "y0": 0,
            "y1": 1,
            "fillcolor": "rgba(39, 174, 96, 0.18)",
            "line": {"width": 0},
            "layer": "below",
        }
    ]
    # A 1-D number line — suppress the y-axis entirely.
    layout["yaxis"] = {"visible": False, "range": [-1, 1], "fixedrange": True}
    layout["showlegend"] = False
    layout["annotations"] = [
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 1.0,
            "yanchor": "bottom",
            "showarrow": False,
            "text": f"Solution: {solution}",
            "font": {"size": 13, "color": PALETTE[2]},
        }
    ]
    return {"data": traces, "layout": layout}


# ---------------------------------------------------------------------------
# 1d. plot_polynomial_shapes
# ---------------------------------------------------------------------------
#
# "Tell me about the shapes of polynomials" / "what does a positive vs negative
# quadratic/cubic look like" is a general-shape question, not a specific
# equation. The pedagogy is a reference card: side-by-side sketches of the
# canonical shapes (+x², −x², +x³, −x³) so the student sees how the sign of the
# leading coefficient flips the curve and how odd vs even degree changes the
# end behaviour. This generator builds that card as a small-multiples grid:
# one row per degree, positive on the left, negative on the right.

_SUPERSCRIPTS = {1: "", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶"}


def plot_polynomial_shapes(
    degrees: list[int] = [2, 3],
    x_range: tuple[float, float] = (-2.5, 2.5),
    *,
    title: str = "Shapes of polynomials",
    samples: int = 200,
) -> dict[str, Any]:
    """Reference card of canonical polynomial shapes (+ and − leading coeff).

    Args:
        degrees: which degrees to show, one row each (default quadratic +
                 cubic). Capped at 4 rows so the grid stays legible in the
                 narrow chat panel.
        x_range: shared x-domain for every sketch.

    Each row shows ``+x^n`` (left) and ``−x^n`` (right). y-axes auto-scale per
    sketch so each shape reads clearly regardless of how fast it grows.

    Raises:
        ValueError: if ``degrees`` is empty / non-integer / out of 1..6, or
        more than 4 degrees are requested.
    """
    if not (isinstance(degrees, list | tuple) and degrees):
        raise ValueError(f"degrees must be a non-empty list; got {degrees!r}")
    if len(degrees) > 4:
        raise ValueError("at most 4 degrees can be shown at once.")
    degs: list[int] = []
    for d in degrees:
        if not isinstance(d, int) or d < 1 or d > 6:
            raise ValueError(f"each degree must be an int in 1..6; got {d!r}")
        degs.append(d)

    lo, hi = _validate_x_range(x_range)
    rows, cols = len(degs), 2
    hgap, vgap = 0.14, 0.18
    col_w = (1.0 - hgap) / cols
    row_h = (1.0 - vgap * (rows - 1)) / rows

    data: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    layout: dict[str, Any] = {
        "title": {"text": title, "x": 0.5, "xanchor": "center"},
        "plot_bgcolor": "#ffffff",
        "paper_bgcolor": "#ffffff",
        "showlegend": False,
        "margin": {"l": 30, "r": 20, "t": 70, "b": 30},
        "meta": {
            "summary": (
                "Reference sketches of polynomial shapes: positive and negative "
                + ", ".join(f"degree-{d}" for d in degs)
                + " curves, showing how the leading-coefficient sign and odd/even "
                "degree determine the shape."
            )
        },
    }

    for r, deg in enumerate(degs):
        for c, sign in enumerate((1, -1)):
            n = r * cols + c + 1
            suf = "" if n == 1 else str(n)
            xs = np.linspace(lo, hi, samples)
            ys = sign * np.power(xs, deg)

            x0 = c * (col_w + hgap)
            x1 = x0 + col_w
            y1 = 1.0 - r * (row_h + vgap)
            y0 = y1 - row_h

            data.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "name": "f(x)",
                    "x": xs.tolist(),
                    "y": _nan_to_none(ys),
                    "xaxis": f"x{suf}",
                    "yaxis": f"y{suf}",
                    "line": {"color": PALETTE[0], "width": 2},
                    "hovertemplate": "x=%{x:.2f}<br>y=%{y:.2f}<extra></extra>",
                }
            )
            layout[f"xaxis{suf}"] = {
                "domain": [x0, x1],
                "anchor": f"y{suf}",
                "zeroline": True,
                "zerolinecolor": "#888",
                "showgrid": False,
                "showticklabels": False,
            }
            layout[f"yaxis{suf}"] = {
                "domain": [y0, y1],
                "anchor": f"x{suf}",
                "zeroline": True,
                "zerolinecolor": "#888",
                "showgrid": False,
                "showticklabels": False,
            }
            sign_str = "" if sign > 0 else "−"
            label = f"y = {sign_str}x{_SUPERSCRIPTS.get(deg, f'^{deg}')}"
            annotations.append(
                {
                    "xref": "paper",
                    "yref": "paper",
                    "x": (x0 + x1) / 2.0,
                    "y": y1 + 0.015,
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "showarrow": False,
                    "text": label,
                    "font": {"size": 12, "color": PALETTE[0]},
                }
            )

    layout["annotations"] = annotations
    return {"data": data, "layout": layout}


# ---------------------------------------------------------------------------
# 1e. plot_modulus
# ---------------------------------------------------------------------------
#
# A modulus graph y = |inner(x)| is taught as "draw inner(x), then reflect the
# part below the x-axis up". This generator shows both: the inner polynomial as
# a faint dashed line and y = |inner(x)| as the solid curve, so the reflection
# is visible. Default inner is x (the canonical V-shaped y = |x|).


def plot_modulus(
    inner_coefficients: list[float] = [1, 0],
    x_range: tuple[float, float] | None = None,
    *,
    title: str = "",
    samples: int = DEFAULT_SAMPLES,
) -> dict[str, Any]:
    """Plot ``y = |inner(x)|`` where ``inner`` is a polynomial.

    Args:
        inner_coefficients: polynomial inside the modulus, highest-degree
                            first. Default ``[1, 0]`` → ``y = |x|``. Examples:
                            ``[1, -2]`` → ``|x - 2|``; ``[1, 0, -4]`` → ``|x²-4|``.
        x_range:            optional bounds; derived from the inner roots /
                            vertex when omitted.

    Draws the inner polynomial as a faint dashed reference and ``|inner|`` as
    the solid curve so the reflection of the negative part is visible.

    Raises:
        ValueError: if ``inner_coefficients`` is empty or non-numeric.
    """
    if not (isinstance(inner_coefficients, list | tuple) and inner_coefficients):
        raise ValueError("inner_coefficients must be a non-empty list of numbers.")
    if not all(isinstance(c, int | float) for c in inner_coefficients):
        raise ValueError(
            f"inner_coefficients must be numeric; got {inner_coefficients!r}"
        )

    coeffs = np.array(inner_coefficients, dtype=float)

    if x_range is not None:
        lo, hi = _validate_x_range(x_range)
    else:
        roots = _polynomial_real_roots(coeffs, (-1e6, 1e6))
        if roots:
            span = max(max(roots) - min(roots), 1.0)
            pad = max(2.0, span * 0.6)
            lo, hi = min(roots) - pad, max(roots) + pad
        else:
            lo, hi = -5.0, 5.0

    xs = _make_xs((lo, hi), samples)
    inner_ys = np.polyval(coeffs, xs)
    abs_ys = np.abs(inner_ys)

    inner_expr = _polynomial_title(coeffs).removeprefix("f(x) = ")
    auto_title = title or f"y = |{inner_expr}|"

    traces: list[dict[str, Any]] = [
        {
            "type": "scatter",
            "mode": "lines",
            "name": f"{inner_expr} (before |·|)",
            "x": xs.tolist(),
            "y": _nan_to_none(inner_ys),
            "line": {"color": "#9ca3af", "width": 1.5, "dash": "dash"},
            "hovertemplate": "x=%{x:.2f}<br>y=%{y:.2f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "lines",
            "name": f"|{inner_expr}|",
            "x": xs.tolist(),
            "y": _nan_to_none(abs_ys),
            "line": {"color": PALETTE[0], "width": 2.5},
            "hovertemplate": "x=%{x:.2f}<br>y=%{y:.2f}<extra></extra>",
        },
    ]
    return {
        "data": traces,
        "layout": _base_layout(
            auto_title,
            summary=(
                f"Modulus graph y = |{inner_expr}|: the dashed line is "
                f"{inner_expr}, and the solid curve reflects its negative part "
                "above the x-axis."
            ),
        ),
    }


# ---------------------------------------------------------------------------
# 1f. plot_venn
# ---------------------------------------------------------------------------
#
# Venn diagrams are the canonical visual for the LCHL probability set concepts:
# mutually exclusive events (two disjoint circles), not-mutually-exclusive /
# overlapping events and the addition rule (two intersecting circles with the
# A∩B region), and one event contained in another (subset). Plotly has no Venn
# trace, so we draw the sample-space rectangle and the set circles as layout
# ``shapes`` and label the regions with annotations. Equal axis scaling keeps
# the circles round in the narrow chat panel.

_VENN_RELATIONSHIPS = {
    "disjoint": "disjoint",
    "mutually_exclusive": "disjoint",
    "mutually exclusive": "disjoint",
    "exclusive": "disjoint",
    "overlapping": "overlapping",
    "overlap": "overlapping",
    "intersecting": "overlapping",
    "not_mutually_exclusive": "overlapping",
    "not mutually exclusive": "overlapping",
    "subset": "subset",
    "contained": "subset",
}


def plot_venn(
    relationship: str = "overlapping",
    set_labels: list[str] | tuple[str, str] = ("A", "B"),
    *,
    region_values: dict[str, str] | None = None,
    title: str = "",
    show_sample_space: bool = True,
) -> dict[str, Any]:
    """Draw a two-set Venn diagram for a probability set concept.

    Args:
        relationship: ``"disjoint"`` (mutually exclusive — separate circles),
                      ``"overlapping"`` (not mutually exclusive — intersecting,
                      shows A∩B), or ``"subset"`` (B inside A). Common synonyms
                      ("mutually exclusive", "not mutually exclusive", …) accepted.
        set_labels:   two labels for the circles (default ``("A", "B")``).
        region_values: optional text to place in regions — keys among
                       ``"A"``/``"B"``/``"both"``/``"neither"`` (e.g. probabilities).
        show_sample_space: draw the enclosing sample-space rectangle (S).

    Raises:
        ValueError: if ``relationship`` is unrecognised or ``set_labels`` isn't
        a pair.
    """
    rel = _VENN_RELATIONSHIPS.get(str(relationship).strip().lower())
    if rel is None:
        raise ValueError(
            "relationship must be one of disjoint / overlapping / subset "
            f"(or a known synonym); got {relationship!r}"
        )
    if not (isinstance(set_labels, list | tuple) and len(set_labels) == 2):
        raise ValueError(f"set_labels must be a pair; got {set_labels!r}")
    a_label, b_label = str(set_labels[0]), str(set_labels[1])
    region_values = region_values or {}

    a_fill = "rgba(31, 64, 104, 0.32)"   # navy
    b_fill = "rgba(192, 57, 43, 0.30)"   # crimson
    line_a = {"color": "#1f4068", "width": 2}
    line_b = {"color": "#c0392b", "width": 2}

    shapes: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []

    if show_sample_space:
        shapes.append(
            {
                "type": "rect", "xref": "x", "yref": "y",
                "x0": 0.3, "y0": 0.3, "x1": 9.7, "y1": 5.7,
                "line": {"color": "#9ca3af", "width": 1.5}, "fillcolor": "rgba(0,0,0,0)",
            }
        )
        annotations.append(
            {"xref": "x", "yref": "y", "x": 0.7, "y": 5.3, "text": "S",
             "showarrow": False, "font": {"size": 14, "color": "#6b7280"}}
        )

    def circle(cx: float, cy: float, r: float, fill: str, line: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "circle", "xref": "x", "yref": "y",
            "x0": cx - r, "y0": cy - r, "x1": cx + r, "y1": cy + r,
            "fillcolor": fill, "line": line, "layer": "above",
        }

    def label(x: float, y: float, text: str, color: str = "#111827", size: int = 15) -> None:
        annotations.append(
            {"xref": "x", "yref": "y", "x": x, "y": y, "text": text,
             "showarrow": False, "font": {"size": size, "color": color}}
        )

    if rel == "disjoint":
        shapes += [circle(3.0, 3.0, 1.7, a_fill, line_a), circle(7.0, 3.0, 1.7, b_fill, line_b)]
        label(3.0, 4.4, a_label, "#1f4068"); label(7.0, 4.4, b_label, "#c0392b")
        if "A" in region_values: label(3.0, 3.0, region_values["A"])
        if "B" in region_values: label(7.0, 3.0, region_values["B"])
        if "neither" in region_values: label(5.0, 1.0, region_values["neither"], "#6b7280", 12)
        auto_title = title or "Mutually exclusive events (A ∩ B = ∅)"
    elif rel == "overlapping":
        shapes += [circle(4.1, 3.0, 2.2, a_fill, line_a), circle(5.9, 3.0, 2.2, b_fill, line_b)]
        label(2.7, 4.2, a_label, "#1f4068"); label(7.3, 4.2, b_label, "#c0392b")
        if "A" in region_values: label(2.9, 3.0, region_values["A"])
        if "both" in region_values: label(5.0, 3.0, region_values["both"])
        if "B" in region_values: label(7.1, 3.0, region_values["B"])
        if "neither" in region_values: label(5.0, 0.9, region_values["neither"], "#6b7280", 12)
        auto_title = title or "Overlapping events (A ∩ B ≠ ∅)"
    else:  # subset
        shapes += [circle(5.0, 3.0, 2.4, a_fill, line_a), circle(5.0, 2.6, 1.1, b_fill, line_b)]
        label(5.0, 4.8, a_label, "#1f4068"); label(5.0, 2.6, b_label, "#c0392b")
        auto_title = title or f"{b_label} ⊆ {a_label} (subset)"

    invisible = {
        "type": "scatter", "mode": "markers", "name": "venn",
        "x": [0, 10], "y": [0, 6], "marker": {"opacity": 0}, "hoverinfo": "skip",
        "showlegend": False,
    }

    layout: dict[str, Any] = {
        "title": {"text": auto_title, "x": 0.5, "xanchor": "center"},
        "plot_bgcolor": "#ffffff", "paper_bgcolor": "#ffffff", "showlegend": False,
        "margin": {"l": 10, "r": 10, "t": 50, "b": 10},
        "xaxis": {"visible": False, "range": [0, 10], "fixedrange": True},
        "yaxis": {
            "visible": False, "range": [0, 6], "fixedrange": True,
            "scaleanchor": "x", "scaleratio": 1,
        },
        "shapes": shapes,
        "annotations": annotations,
        "meta": {"summary": f"{auto_title}: a Venn diagram of sets {a_label} and {b_label}."},
    }
    return {"data": [invisible], "layout": layout}


def _fmt_num(v: float) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else f"{f:.2f}".rstrip("0").rstrip(".")


def plot_argand(
    real: float = 3.0,
    imag: float = 2.0,
    *,
    title: str = "",
    show_modulus: bool = True,
) -> dict[str, Any]:
    """Draw a complex number on the Argand plane, showing its argument θ.

    Renders the number ``a + bi`` as a vector from the origin, with the
    argument (the angle measured anticlockwise from the positive real axis)
    drawn as an arc and labelled θ, the modulus r along the vector, and dashed
    projections onto the real and imaginary axes.

    Args:
        real:  the real part ``a``.
        imag:  the imaginary part ``b``.
        title: optional override for the auto-generated title.
        show_modulus: label the vector with the computed modulus value.

    Raises:
        ValueError: if the number is 0 (the argument is undefined).
    """
    a = float(real)
    b = float(imag)
    if a == 0.0 and b == 0.0:
        raise ValueError("0 has no argument — cannot draw an Argand argument diagram for it.")

    r = float(np.hypot(a, b))
    # Measure the argument anticlockwise from the positive real axis in [0, 360),
    # matching how it's taught at LCHL (Q3 = 180 + ref, Q4 = 360 − ref) rather
    # than the principal-value (−180, 180] convention atan2 returns.
    theta = float(np.arctan2(b, a))
    if theta < 0:
        theta += 2.0 * np.pi
    theta_deg = float(np.degrees(theta))  # [0, 360)
    lim = r * 1.25 + 0.6

    label = (
        f"{_fmt_num(a)} + {_fmt_num(b)}i" if b >= 0 else f"{_fmt_num(a)} − {_fmt_num(abs(b))}i"
    )

    ra = float(max(0.45, min(0.9, 0.32 * r)))
    ts = np.linspace(0.0, theta, 60)

    vector = {
        "type": "scatter", "mode": "lines+markers", "x": [0.0, a], "y": [0.0, b],
        "line": {"color": "#1f4068", "width": 3},
        "marker": {"size": [0, 10], "color": "#1f4068"},
        "hoverinfo": "skip", "showlegend": False, "name": "z",
    }
    proj = {
        "type": "scatter", "mode": "lines",
        "x": [a, a, None, a, 0.0], "y": [b, 0.0, None, b, b],
        "line": {"color": "#9ca3af", "width": 1.5, "dash": "dot"},
        "hoverinfo": "skip", "showlegend": False,
    }
    arc = {
        "type": "scatter", "mode": "lines",
        "x": (ra * np.cos(ts)).tolist(), "y": (ra * np.sin(ts)).tolist(),
        "line": {"color": "#6b2d8e", "width": 2.5},
        "hoverinfo": "skip", "showlegend": False,
    }

    mid = theta / 2.0
    annotations = [
        {"x": a, "y": b, "text": label, "showarrow": False,
         "xanchor": "left" if a >= 0 else "right", "yanchor": "bottom" if b >= 0 else "top",
         "xshift": 8 if a >= 0 else -8, "yshift": 8 if b >= 0 else -8,
         "font": {"size": 15, "color": "#1f4068"}},
        {"x": (ra + 0.3) * float(np.cos(mid)), "y": (ra + 0.3) * float(np.sin(mid)),
         "text": "θ", "showarrow": False, "font": {"size": 17, "color": "#6b2d8e"}},
        {"x": a / 2.0, "y": b / 2.0, "text": (f"r = {_fmt_num(r)}" if show_modulus else "r"),
         "showarrow": False, "xshift": -12, "yshift": 12,
         "font": {"size": 13, "color": "#1f4068"}},
        {"x": lim - 0.1, "y": 0.0, "text": "Re", "showarrow": False,
         "xanchor": "right", "yanchor": "top", "font": {"size": 12, "color": "#6b7280"}},
        {"x": 0.0, "y": lim - 0.1, "text": "Im", "showarrow": False,
         "xanchor": "left", "yanchor": "top", "xshift": 6, "font": {"size": 12, "color": "#6b7280"}},
    ]

    auto_title = title or f"Argument of {label}:  θ ≈ {_fmt_num(round(theta_deg, 1))}°"
    axis = {
        "range": [-lim, lim], "zeroline": True, "zerolinecolor": "#374151",
        "zerolinewidth": 1.5, "showgrid": False, "fixedrange": True, "visible": True,
        "showticklabels": False,
    }
    layout = {
        "title": {"text": auto_title, "x": 0.5, "xanchor": "center"},
        "plot_bgcolor": "#ffffff", "paper_bgcolor": "#ffffff", "showlegend": False,
        "margin": {"l": 10, "r": 10, "t": 50, "b": 10},
        "xaxis": dict(axis),
        "yaxis": {**axis, "scaleanchor": "x", "scaleratio": 1},
        "annotations": annotations,
        "meta": {"summary": (
            f"Argand diagram of {label} showing its modulus r and argument "
            f"θ ≈ {_fmt_num(round(theta_deg, 1))}° from the positive real axis."
        )},
    }
    return {"data": [proj, vector, arc], "layout": layout}


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
    "plot_quadratic_inequality": plot_quadratic_inequality,
    "plot_linear_inequality": plot_linear_inequality,
    "plot_polynomial_shapes": plot_polynomial_shapes,
    "plot_modulus": plot_modulus,
    "plot_venn": plot_venn,
    "plot_argand": plot_argand,
    "plot_trig": plot_trig,
    "plot_exponential": plot_exponential,
    "plot_log": plot_log,
    "plot_piecewise": plot_piecewise,
    "plot_data_points": plot_data_points,
    "plot_overlay": plot_overlay,
}
"""Name → callable map, used by the synthesiser extension to route an LLM
tool-call to a concrete generator."""
