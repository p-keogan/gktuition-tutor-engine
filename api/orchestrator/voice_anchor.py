"""Voice anchoring — strand cram summary + ``_voice.md`` rules as prompt prefix.

Phase 2 §"Voice match is the load-bearing differentiator" (see
``career-transition-2026/PHASE_02_KICKOFF.md``) makes the generation prompt
load-bearing: a soft-path Cortex/Mistral answer that doesn't sound like Paul
fails the bar even when the maths is correct. This module is the prompt-side
of that bet — for every successful retrieval, we look up

1. The **strand cram summary** (one of the 20 ``_SUMMARY-exam-cram.md``
   files in ``career-transition-2026/tutorials/LCHL_*/``) whose strand
   matches the top retrieved slug. Injected verbatim (up to a char cap).
2. The **voice rules** from ``tutorials/_voice.md``. Injected verbatim.

Both blocks live in the *sibling* repo, not in this engine repo. The path is
resolved from the ``CORPUS_ROOT`` env var (default
``/Users/paul/code/career-transition-2026``) so the same code runs locally
and on Fly.io once the secret is plumbed through.

Everything is pure and side-effect-free except the in-process file cache; if
``CORPUS_ROOT`` is unset, missing, or points to a directory without the
expected layout, every helper returns ``None`` and the synthesiser proceeds
without the anchor. We never raise — the orchestrator MUST still answer the
question if the anchor files happen to be unavailable.

Slug → strand mapping is derived from the corpus's own slug conventions
(``algebra-1-...`` → ``LCHL_Algebra``, ``trigonometry-2-3-...`` →
``LCHL_Trigonometry_2``, etc.). Solution-side slugs (e.g.
``2023_P1_solutions``) have no strand prefix and the helper returns ``None``
for them — we don't synthesise an anchor we can't ground.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from .contract import RetrievalResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Default location of the voice + strand-summary corpus on Paul's laptop.
# Fly.io overrides via the ``CORPUS_ROOT`` env var (set in ``fly.toml`` /
# ``scripts/setup_fly_secrets.sh``). Tests override via monkeypatch.
CORPUS_ROOT_ENV = "CORPUS_ROOT"
DEFAULT_CORPUS_ROOT = "/Users/paul/code/career-transition-2026"

# Maximum characters of strand summary + voice rules to inject. ~12,000 chars
# is roughly 3,000 tokens at the 4-chars-per-token rule of thumb, matching
# the PHASE_02_KICKOFF.md "~3,000 tokens" cost budget for the prefix.
DEFAULT_MAX_ANCHOR_CHARS = 12_000

# Filenames under ``CORPUS_ROOT/tutorials/<strand>/`` and
# ``CORPUS_ROOT/tutorials/`` respectively.
SUMMARY_FILENAME = "_SUMMARY-exam-cram.md"
VOICE_GUIDE_FILENAME = "_voice.md"

# Slug-prefix → strand-directory mapping. Order matters: longest matching
# prefix wins (so ``trigonometry-2-3-...`` resolves to ``LCHL_Trigonometry_2``
# and not the would-be shorter ``trigonometry-`` catch-all). Mapping derived
# from the actual corpus on 2026-05-25 — 22 strand directories under
# ``career-transition-2026/tutorials/LCHL_*/``.
STRAND_PREFIX_MAP: tuple[tuple[str, str], ...] = (
    # Trigonometry has 4 numbered sub-strands; match the longer prefix first.
    ("trigonometry-1-", "LCHL_Trigonometry_1"),
    ("trigonometry-2-", "LCHL_Trigonometry_2"),
    ("trigonometry-3-", "LCHL_Trigonometry_3"),
    ("trigonometry-4-", "LCHL_Trigonometry_4"),
    # Geometry currently ships only the §1 strand; the §2+ folders are
    # planned for the curriculum-reform refresh and are out of scope here.
    ("geometry-1-", "LCHL_Geometry_1"),
    # AVM 1 (Area, Volume, Measurement — Part 1).
    ("avm-1-", "LCHL_AVM_1"),
    # Everything else: longest unambiguous prefix.
    ("complex-numbers-", "LCHL_Complex_Numbers"),
    ("number-theory-", "LCHL_Number_Theory"),
    ("sequences-series-", "LCHL_Sequences_and_Series"),
    ("financial-maths-", "LCHL_Financial_Maths"),
    ("functions-graphs-", "LCHL_Functions_and_Graphs"),
    ("indices-logs-", "LCHL_Indices_and_Logs"),
    ("differentiation-", "LCHL_Differentiation"),
    ("integration-", "LCHL_Integration"),
    ("probability-", "LCHL_Probability"),
    ("statistics-", "LCHL_Statistics"),
    ("induction-", "LCHL_Induction"),
    ("the-circle-", "LCHL_The_Circle"),
    ("the-line-", "LCHL_The_Line"),
    # algebra-2-..., algebra-22-... must NOT match a `algebra-2-` substring
    # of something else — the prefix is anchored with the trailing hyphen.
    ("algebra-", "LCHL_Algebra"),
)


# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------


# Strand-summary cache: { (corpus_root, strand): summary_text_or_None }.
# Memoised across requests so we read each summary file once per process.
# ``None`` is cached too — missing files don't trigger a re-read on every
# query. Cleared by ``_clear_caches`` (test helper).
_summary_cache: dict[tuple[str, str], str | None] = {}

# Voice-guide cache: { corpus_root: voice_text_or_None }.
_voice_cache: dict[str, str | None] = {}

_cache_lock = threading.Lock()


def _clear_caches() -> None:
    """Test helper. Wipe the memoisation tables.

    Called by ``api/tests/test_voice_anchor.py``'s ``autouse`` fixture so each
    test sees a fresh filesystem read.
    """
    with _cache_lock:
        _summary_cache.clear()
        _voice_cache.clear()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def corpus_root() -> Path:
    """Resolve the corpus root directory from ``CORPUS_ROOT`` or the default.

    Returned as a ``Path`` even when the directory doesn't exist — the
    downstream loaders test ``is_file()`` and fall back to ``None``.
    """
    return Path(os.environ.get(CORPUS_ROOT_ENV, DEFAULT_CORPUS_ROOT))


def infer_strand_from_slug(slug: str) -> str | None:
    """Return the ``LCHL_<Strand>`` directory name for a tutorial slug.

    Returns ``None`` when the slug doesn't match any known strand prefix —
    e.g. solution-side slugs (``2023_P1_solutions``), summary-side slugs, or
    test fixtures with synthetic identifiers. Pure function; safe to call
    from any thread.
    """
    if not slug:
        return None
    slug_l = slug.lower()
    for prefix, strand in STRAND_PREFIX_MAP:
        if slug_l.startswith(prefix):
            return strand
    return None


def load_strand_summary(strand: str, root: Path | None = None) -> str | None:
    """Read ``<root>/tutorials/<strand>/_SUMMARY-exam-cram.md`` if it exists.

    Memoised per (root, strand). Returns ``None`` on any of:

    * the strand directory doesn't exist,
    * the summary file doesn't exist (some strands don't ship a summary —
      currently all 20 LCHL_* strands do, but Paper_1_Proofs / Paper_2_Proofs
      / Maths_Exams correctly resolve to ``None``),
    * the file is unreadable for any I/O reason.

    Never raises. The synthesiser depends on this never killing the request.
    """
    if not strand:
        return None
    root_path = root if root is not None else corpus_root()
    key = (str(root_path), strand)
    with _cache_lock:
        if key in _summary_cache:
            return _summary_cache[key]

    summary_path = root_path / "tutorials" / strand / SUMMARY_FILENAME
    try:
        text: str | None = summary_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # File missing or unreadable — cache the None so we don't keep
        # hitting the filesystem.
        text = None

    with _cache_lock:
        _summary_cache[key] = text
    return text


def load_voice_guide(root: Path | None = None) -> str | None:
    """Read ``<root>/tutorials/_voice.md`` if it exists.

    Memoised per root. Returns ``None`` when the file is missing or
    unreadable. Never raises.
    """
    root_path = root if root is not None else corpus_root()
    key = str(root_path)
    with _cache_lock:
        if key in _voice_cache:
            return _voice_cache[key]

    voice_path = root_path / "tutorials" / VOICE_GUIDE_FILENAME
    try:
        text: str | None = voice_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        text = None

    with _cache_lock:
        _voice_cache[key] = text
    return text


# ---------------------------------------------------------------------------
# Public entrypoint — called by the synthesiser
# ---------------------------------------------------------------------------


def infer_strand_from_retrieval(retrieval: RetrievalResult) -> str | None:
    """Return the strand directory name for the top-1 retrieved chunk.

    Returns ``None`` when retrieval is empty or when the top-1 slug doesn't
    map to any strand. Surfaced to the wire via
    ``QueryResponse.voice_anchor_strand`` for debugging + the eval harness.
    """
    if not retrieval.chunks:
        return None
    return infer_strand_from_slug(retrieval.chunks[0].slug)


def build_voice_anchor(
    retrieval: RetrievalResult,
    max_chars: int = DEFAULT_MAX_ANCHOR_CHARS,
) -> str | None:
    """Return the system-prompt prefix string for ``retrieval``, or ``None``.

    The returned string contains, in order:

    1. The strand cram-summary block (when retrieval lands inside a strand
       with a ``_SUMMARY-exam-cram.md``), framed with a clear header.
    2. The voice rules block (always included when ``_voice.md`` is
       readable, even if the strand summary is missing — voice rules apply
       to every answer).

    Returns ``None`` when **both** the strand summary and the voice guide
    are unavailable. The synthesiser interprets ``None`` as "no anchor, use
    the bare SYSTEM_PROMPT" and falls back to Phase-1 behaviour.

    The ``max_chars`` cap is split: at most ``2/3 * max_chars`` for the
    strand summary, at most ``1/3 * max_chars`` for the voice rules — the
    summary is strand-specific (high-signal) and the voice rules are
    corpus-wide (medium-signal); the split keeps the prefix at ~3,000
    tokens regardless of which strand fired.
    """
    strand = infer_strand_from_retrieval(retrieval)

    summary_text: str | None = None
    if strand is not None:
        summary_text = load_strand_summary(strand)

    voice_text = load_voice_guide()

    if summary_text is None and voice_text is None:
        return None

    summary_cap = (2 * max_chars) // 3
    voice_cap = max_chars - summary_cap

    parts: list[str] = []

    if summary_text is not None and strand is not None:
        trimmed = _truncate_at_section_boundary(summary_text, summary_cap)
        parts.append(
            "STRAND CONTEXT — the cram summary for the strand the student's "
            f"question lands in ({strand}). Treat the phrasing, priorities, "
            "and 'what to memorise vs what to look up' calls in this section "
            "as the canonical voice for your answer:\n\n"
            f"```markdown\n{trimmed}\n```"
        )

    if voice_text is not None:
        trimmed = _truncate_at_section_boundary(voice_text, voice_cap)
        parts.append(
            "VOICE RULES — load-bearing pedagogy from the corpus-wide voice "
            "guide. These rules override the default 'shortest correct "
            "answer' heuristic. In particular: end every 'show that' / "
            "'prove that' answer with an explicit 'Therefore...' sentence; "
            "cite log-tables page numbers when a relevant formula exists; "
            "default to Paul's preferred method even when alternatives are "
            "shorter; no motivational filler:\n\n"
            f"```markdown\n{trimmed}\n```"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _truncate_at_section_boundary(text: str, max_chars: int) -> str:
    """Trim ``text`` to ~``max_chars`` while preferring a markdown section break.

    Markdown summaries are heading-delimited; chopping mid-paragraph wastes
    the LLM's attention on a half-thought. If the text already fits, return
    it untouched. Otherwise truncate at the last ``\\n## `` (or, failing
    that, ``\\n`` then character) boundary before ``max_chars``.
    """
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]

    # Prefer the last top-level section header (## ) so we hand the LLM a
    # complete section every time.
    last_section = window.rfind("\n## ")
    if last_section > max_chars // 2:
        return window[:last_section].rstrip() + "\n\n[...truncated for prompt-length budget]"

    # Fall back to the last paragraph break.
    last_para = window.rfind("\n\n")
    if last_para > max_chars // 2:
        return window[:last_para].rstrip() + "\n\n[...truncated for prompt-length budget]"

    # Last resort: cut at the last newline.
    last_newline = window.rfind("\n")
    if last_newline > 0:
        return window[:last_newline] + "\n[...truncated for prompt-length budget]"

    return window + "\n[...truncated for prompt-length budget]"
