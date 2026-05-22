"""Pydantic models for the `/query` request/response contract.

The canonical shape is defined in ADR-003 "Decision item 5" and extended with
`query_class` per ADR-004 Decision 1. This module is the single source of
truth — every other file imports its types from here so the OpenAPI schema at
`/docs` stays consistent with what's wire-serialised.

The contract has six query classes:

* ``concept``           — first-exposure conceptual question. RAG over TUTOR_SEARCH.
* ``solution_lookup``   — "how was 2024 P2 Q5 solved" — RAG over SOLUTIONS_SEARCH.
* ``summary_request``   — "I'm cramming The Line tonight" — RAG over SUMMARY_SEARCH.
* ``analytical``        — text-to-SQL via Cortex Analyst.
* ``image_extracted``   — extracted text from /image_query; treated as ``concept``.
* ``ambiguous``         — fans out to all three search services + Analyst.

Anything that touches the wire goes through these models.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class QueryClass(str, Enum):
    """Routing decision the deterministic classifier emits.

    Values match the literal strings used in ``routing_contract.md`` so
    operators can grep across the orchestrator + the routing spec without
    paying for an enum→string mapping in their heads.
    """

    CONCEPT = "concept"
    SOLUTION_LOOKUP = "solution_lookup"
    SUMMARY_REQUEST = "summary_request"
    ANALYTICAL = "analytical"
    IMAGE_EXTRACTED = "image_extracted"
    AMBIGUOUS = "ambiguous"


Tier = Literal["anonymous", "authenticated_free", "paying"]


# ---------------------------------------------------------------------------
# Sub-types appearing inside QueryResponse
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """A pointer to a specific moment in a tutorial / solution / summary.

    The ``timestamp_seconds`` field is non-null only for tutorial citations
    (we time-anchor the YouTube playback in the widget). For solution and
    summary citations it is ``None``.
    """

    model_config = ConfigDict(frozen=True)

    slug: str = Field(..., description="Canonical slug identifying the tutorial / part / summary.")
    title: str = Field(..., description="Human-readable title rendered in the widget.")
    timestamp_seconds: int | None = Field(
        None,
        ge=0,
        description="Seconds offset into the source video. None for non-video sources.",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Reranker / search-service confidence, normalised to 0..1.",
    )


class RetrievedChunk(BaseModel):
    """A retrieved evidence chunk surfaced back to the client so the widget
    can render the 'related tutorials' tray even when the answer model
    refuses to commit.
    """

    model_config = ConfigDict(frozen=True)

    slug: str = Field(..., description="Source slug.")
    snippet: str = Field(..., description="Verbatim text chunk used as evidence.")
    score: float = Field(..., ge=0.0, le=1.0, description="Reranker score.")


class ExamAppearance(BaseModel):
    """Hand-curated per-tutorial exam-appearance row, sourced from YAML
    frontmatter under ``exam_appearances[]`` in each tutorial. v1 returns
    empty lists for tutorials not yet curated — degraded but valid.
    """

    model_config = ConfigDict(frozen=True)

    year: int = Field(..., ge=2000, le=2099)
    paper: int = Field(..., ge=1, le=3, description="1, 2, or 3 (sample paper).")
    question: str = Field(..., description="Question + sub-part identifier, e.g. 'Q5b'.")
    level: str = Field(..., description="LCHL / LCOL / LCFL — currently always LCHL.")
    marks: int = Field(..., ge=0, le=100)
    note: str | None = Field(None, description="Author's note on what the question tested.")


class LearningWorkEntry(BaseModel):
    """Hand-curated per-tutorial learning-work entry — the 'what to practice
    next' cross-reference. Sourced from ``learning_work[]`` YAML frontmatter.
    """

    model_config = ConfigDict(frozen=True)

    topic: str = Field(..., description="Free-text topic label.")
    tutorial_slug: str = Field(..., description="Slug of the next-step tutorial.")
    note: str | None = Field(None, description="Author's note on why this is the next step.")


class GraphSpec(BaseModel):
    """A Plotly JSON figure spec the widget renders inline under the answer.

    Per ADR-005 (visualisation layer), an answer about a sketchable maths
    function (sinusoidal, polynomial, exponential, etc.) carries one or
    more graph specs in ``QueryResponse.graphs``. Each spec is a Plotly
    figure dict (``{"data": [...], "layout": {...}}``) produced by one of
    the seven generators in :mod:`api.visualisation.generators`. The widget
    detects the field and renders one ``react-plotly.js`` chart per entry.

    The wrapping ``data``/``layout`` keys are the documented Plotly figure
    shape; we store the dict verbatim rather than re-typing every Plotly
    primitive because the JS-side renderer consumes the same JSON
    regardless of which generator produced it.
    """

    model_config = ConfigDict(frozen=True)

    kind: str = Field(
        ...,
        description=(
            "Which generator produced this figure — one of "
            "'polynomial' | 'trig' | 'exponential' | 'log' | 'piecewise' | "
            "'data_points' | 'overlay'. Used by the widget for analytics + "
            "by the eval harness for graph-emission precision scoring."
        ),
    )
    figure: dict[str, Any] = Field(
        ...,
        description=(
            "The Plotly figure dict — {data: [...], layout: {...}}. "
            "JSON-serialisable (NaN values are punched as nulls)."
        ),
    )


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """``POST /query`` body.

    The ``tier`` field is intentionally NOT trusted from the wire — the route
    overwrites it with the value decoded from the JWT. We accept it in the
    schema so the OpenAPI page at ``/docs`` is self-documenting (and so the
    automated tests can drive the field directly without forging JWTs).
    """

    q: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The student's question. Plain text; LaTeX/Markdown is acceptable.",
    )
    tier: Tier = Field(
        "anonymous",
        description=(
            "Caller tier. The route overrides this with the JWT-decoded value; "
            "exposed in the schema for OpenAPI docs and test ergonomics."
        ),
    )
    debug: bool = Field(
        False,
        description=(
            "When true, the response includes diagnostic fields (raw retrieval "
            "scores, classifier match phrases). Off by default."
        ),
    )


class QueryResponse(BaseModel):
    """``POST /query`` response — the canonical ADR-003 + ADR-004 contract.

    See ``ADR-003`` Decision item 5 and ``ADR-004`` Decision 1 for the
    rationale on every field. ``query_class`` was added in ADR-003 Edit 6
    (cross-referenced by ADR-004 Decision 1) so the widget can render an
    intent-appropriate progress indicator.
    """

    query: str = Field(..., description="Echo of the input query (post-trim).")
    answer: str = Field(..., description="The synthesised answer, plain text or markdown.")
    query_class: QueryClass = Field(
        ...,
        description="The routing decision the deterministic classifier emitted.",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Per-source citations the answer relies on. Empty if the floor was not met.",
    )
    retrieved: list[RetrievedChunk] = Field(
        default_factory=list,
        description="Top-K retrieved chunks, always populated when retrieval ran.",
    )
    exam_appearances: list[ExamAppearance] = Field(
        default_factory=list,
        description="Hand-curated exam-appearance rows for the top tutorial.",
    )
    related_learning_work: list[LearningWorkEntry] = Field(
        default_factory=list,
        description="Hand-curated 'practice next' cross-references for the top tutorial.",
    )
    graphs: list[GraphSpec] = Field(
        default_factory=list,
        description=(
            "Plotly figure specs the widget renders inline under the answer "
            "text. Empty for non-graph-shaped queries. Added in ADR-005."
        ),
    )
    model_used: str = Field(
        ...,
        description=(
            "One of: 'cortex.mistral-large2', 'anthropic.claude-haiku-4-5', "
            "'anthropic.claude-sonnet-4', 'cortex.analyst', or '(none)' "
            "(set when the answer is the 'I don't know' guardrail)."
        ),
    )
    from_cache: bool = Field(
        False,
        description=(
            "Always False from Agent 09's path. Agent 10's semantic cache "
            "wrapper flips this when serving a cache hit."
        ),
    )
    elapsed_ms: int = Field(..., ge=0, description="End-to-end latency in milliseconds.")

    # Optional diagnostic field — only populated when QueryRequest.debug=True.
    debug_info: dict[str, Any] | None = Field(
        None,
        description="Set only when QueryRequest.debug=True. Raw retrieval scores etc.",
    )


# ---------------------------------------------------------------------------
# Internal — not exported on the wire
# ---------------------------------------------------------------------------


class RetrievalResult(BaseModel):
    """In-process container returned by the retriever to the synthesizer.

    NOT returned to clients. The synthesiser converts the contents of this
    into the public ``QueryResponse`` fields.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    query_class: QueryClass
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    analyst_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Cortex Analyst rows when query_class includes analytical.",
    )
    analyst_sql: str | None = Field(
        None, description="The SQL the analyst generated (None for non-analytical)."
    )
    top_reranker_score: float = Field(0.0, ge=0.0, le=1.0)
    exam_appearances: list[ExamAppearance] = Field(default_factory=list)
    related_learning_work: list[LearningWorkEntry] = Field(default_factory=list)
    services_called: list[str] = Field(default_factory=list)
