"""Visualisation layer — Plotly-JSON generators consumed by the React widget.

Per ADR-005, the tutor response carries a ``graphs: list[GraphSpec]`` field;
each entry is a Plotly JSON figure dict produced by one of the seven
generators in :mod:`api.visualisation.generators`. The widget renders each
entry via ``react-plotly.js`` directly under the answer text.

Nothing in this package opens a network connection or persists state —
generators are pure functions over their inputs, and the synthesiser
extension is the only place that calls an LLM (Haiku 4.5 only, with a
strict tool-call schema). See :mod:`api.visualisation.synthesizer_extension`.
"""
from __future__ import annotations

from . import generators
from .generators import (
    plot_data_points,
    plot_exponential,
    plot_log,
    plot_overlay,
    plot_piecewise,
    plot_polynomial,
    plot_trig,
)
from .synthesizer_extension import select_and_invoke_generator, should_emit_graph

__all__ = [
    "generators",
    "plot_data_points",
    "plot_exponential",
    "plot_log",
    "plot_overlay",
    "plot_piecewise",
    "plot_polynomial",
    "plot_trig",
    "select_and_invoke_generator",
    "should_emit_graph",
]
