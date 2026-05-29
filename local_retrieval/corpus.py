"""Corpus loading for the local index — REUSES the canonical Cortex parser.

To keep the local index row-for-row equivalent to what fed Cortex
(``GKTUITION_TUTOR.RAW.TUTORIALS``), we do not re-implement the markdown walk
or the YAML frontmatter handling. We import ``walk_corpus`` / ``LoadReport``
straight out of ``snowflake/load_tutorials.py`` (the same code the live loader
runs), so parity is meaningful: identical slug set, identical
``title_plus_phrasings`` / ``body`` construction, identical skip rules
(``_SUMMARY-*``, ``README.md``, and slug-less out-of-schema files).

``snowflake/`` is not an installable package, so we add it to ``sys.path`` by
path and import the module by name. This is import-time side-effecting but
contained to this module.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# Repo root = parent of the local_retrieval/ package dir.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOADER_PATH = _REPO_ROOT / "snowflake" / "load_tutorials.py"

# Default corpus root: the ctr-2026 tutorials tree that fed Cortex. Mirrors the
# default in snowflake/load_tutorials.py (repo-root/../career-transition-2026).
DEFAULT_CORPUS_ROOT = _REPO_ROOT.parent / "career-transition-2026" / "tutorials"


def _load_loader_module():
    """Import snowflake/load_tutorials.py as a module, by file path."""
    if not _LOADER_PATH.is_file():
        raise FileNotFoundError(
            f"Cannot reuse the canonical parser: {_LOADER_PATH} not found. "
            "The local index must build from the same parser that fed Cortex."
        )
    spec = importlib.util.spec_from_file_location("_gk_load_tutorials", _LOADER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build import spec for {_LOADER_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_gk_load_tutorials", mod)
    spec.loader.exec_module(mod)
    return mod


def load_tutorial_rows(corpus_root: Path | str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Walk the tutorial corpus and return ``(rows, report_summary)``.

    ``rows`` are the exact dicts ``load_tutorials.build_row`` produces — each
    carries ``slug``, ``title``, ``title_plus_phrasings``, ``body``, ``topic``,
    ``subtopic`` and the rest of the TUTORIALS shape. ``report_summary`` is a
    small dict of walk counts for the delivery note.
    """
    loader = _load_loader_module()
    report = loader.LoadReport()
    rows = loader.walk_corpus(Path(corpus_root).resolve(), report)
    summary = {
        "walked": report.walked,
        "parsed": report.parsed,
        "skipped_summary": report.skipped_summary,
        "skipped_readme": report.skipped_readme,
        "skipped_out_of_schema": len(report.skipped_out_of_schema),
        "parse_errors": len(report.parse_errors),
    }
    return rows, summary
