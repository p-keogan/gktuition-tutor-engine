"""Exam-appearance lookup for cited tutorials.

The curated ``exam_appearances`` live in each tutorial's YAML frontmatter in
the source corpus (career-transition-2026), which is NOT shipped in the engine
image — only the strand summaries are. So at build/sync time we extract a
compact ``corpus/exam_appearances.json`` (slug -> list of appearances) and ship
that. This module loads it once and maps a query's citations to the most
recent exam appearances, which the widget renders as a "Seen in exams" block.

Regenerate the JSON with ``scripts/build_exam_appearances.py`` (or the snippet
in QUALITY_TESTING_NOTES) whenever the tutorial frontmatter changes.
"""
from __future__ import annotations

import functools
import json
import logging

from .contract import ExamAppearance
from . import voice_anchor

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _index() -> dict[str, list[dict]]:
    """Load slug -> [appearance dict] from corpus/exam_appearances.json."""
    path = voice_anchor.corpus_root() / "exam_appearances.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        logger.warning("exam_appearances.json not found at %s — exam refs disabled", path)
        return {}
    except Exception:
        logger.exception("failed to load exam_appearances.json")
        return {}


def _for_slug(slug: str) -> list[ExamAppearance]:
    out: list[ExamAppearance] = []
    for a in _index().get(slug, []):
        try:
            out.append(
                ExamAppearance(
                    year=int(a["year"]),
                    paper=int(a["paper"]),
                    question=str(a.get("question", "")),
                    level=str(a.get("level", "LCHL")),
                    marks=int(a.get("marks", 0)),
                    note=a.get("note"),
                )
            )
        except Exception:
            # A single malformed row must never break retrieval.
            continue
    return out


def exam_appearances_for_citations(
    citations: list,
    *,
    max_tutorials: int = 2,
    max_total: int = 4,
) -> list[ExamAppearance]:
    """Aggregate exam appearances for a query's top cited tutorials.

    Looks at the top ``max_tutorials`` citations, de-dupes by (year, paper,
    question), sorts newest-first, and returns at most ``max_total``. The widget
    further trims to the two most recent for display.
    """
    seen: set[tuple[int, int, str]] = set()
    result: list[ExamAppearance] = []
    for c in citations[:max_tutorials]:
        slug = getattr(c, "slug", None)
        if not slug:
            continue
        for ea in _for_slug(slug):
            key = (ea.year, ea.paper, ea.question)
            if key in seen:
                continue
            seen.add(key)
            result.append(ea)
    result.sort(key=lambda e: (e.year, e.paper), reverse=True)
    return result[:max_total]
