#!/usr/bin/env python3
"""Walk a git diff and emit a JSON manifest of changed `.md` files
grouped by which Snowflake loader needs to fire.

The downstream consumer is ``sync/run_loaders.py``; together they form
the GitHub Action's body. The manifest design is deliberately
machine-first: every value is a list (so the consumer never has to
distinguish "one file" from "several") and the keys are stable across
runs.

Output shape (written to ``stdout`` or to ``--output PATH``):

    {
      "from":  "abc123",
      "to":    "def456",
      "tutorials":      ["tutorials/LCHL_Algebra/...md", ...],
      "exam_solutions": ["tutorials/LCHL_Maths_Exams/Solutions/...md", ...],
      "summaries":      ["tutorials/LCHL_Trigonometry_1/_SUMMARY-...md", ...],
      "schema":         ["tutorials/SCHEMA.md"],
      "loader_code_changed": false,
      "summary": {
        "n_tutorials":      3,
        "n_exam_solutions": 1,
        "n_summaries":      0,
        "schema_touched":   false,
        "loader_touched":   false
      }
    }

Categorisation rules
--------------------
Path matching is performed on the path **relative to the repo root**
(what git emits). The repo root is inferred from the cwd by ``git
rev-parse --show-toplevel`` unless ``--repo-root`` overrides it.

* **tutorials**: ``tutorials/LCHL_*/*.md`` except summaries (the
  ``_SUMMARY-*.md`` prefix) and the Maths_Exams folder. Also
  includes ``tutorials/LCHL_Paper_*_Proofs/proof-*.md`` — those are
  out-of-schema for the loader but still tutorial-corpus content
  that downstream consumers may want flagged.

* **exam_solutions**: ``tutorials/LCHL_Maths_Exams/Solutions/<YYYY>_*_solutions.md``
  (the 30 canonical solutions files). Skips
  ``AGENT_PROMPT_*.md``, ``LCHL_exam_trends.md``, ``README.md``.

* **summaries**: ``tutorials/LCHL_*/_SUMMARY-*.md``.

* **schema**: ``tutorials/SCHEMA.md``. Changes here flow through to
  every loader and trigger a STOP — the runner requires human review.

* **loader_code_changed**: any file under
  ``gktuition-tutor-engine/snowflake/`` changed. Same STOP semantics.

Files that don't match any of the above are silently ignored; the
manifest is intentionally narrow because the consumer must do
exactly one of {fire-the-right-loader, abort-for-review}.

Usage
-----

    # In CI — diff the previous commit against HEAD.
    python sync/detect_changes.py --from HEAD~1 --to HEAD

    # Locally — what does my un-pushed branch want to load?
    python sync/detect_changes.py --from origin/main --to HEAD

    # From a specific repo root (the engine repo's CI may run from
    # one repo and need to inspect the sibling tutorials repo).
    python sync/detect_changes.py --from main --to HEAD \\
        --repo-root /path/to/career-transition-2026

    # Write to a file the runner picks up later.
    python sync/detect_changes.py --from HEAD~1 --to HEAD \\
        --output manifest.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
log = logging.getLogger("detect_changes")

# ─────────────────────────────────────────────────────────────────────
# Path classifiers
# ─────────────────────────────────────────────────────────────────────
TUTORIAL_RE = re.compile(
    r"^tutorials/LCHL_(?!Maths_Exams\b)[^/]+/(?!_SUMMARY-)[^/]+\.md$"
)
SOLUTION_RE = re.compile(
    # Accepts: <YYYY>_P[12]_solutions.md, <YYYY>_DF_P[12]_solutions.md,
    # and the inverted form <YYYY>_P[12]_DF_solutions.md that the 2022
    # P1 deferred uses. Tolerant by design — the corpus has both
    # orderings and tightening here would silently drop one of the
    # 30 canonical files.
    r"^tutorials/LCHL_Maths_Exams/Solutions/\d{4}_(?:DF_)?P[12](?:_DF)?_solutions\.md$"
)
SUMMARY_RE = re.compile(r"^tutorials/LCHL_[^/]+/_SUMMARY-[^/]+\.md$")
SCHEMA_RE = re.compile(r"^tutorials/SCHEMA\.md$")
LOADER_CODE_RE = re.compile(r"^(gktuition-tutor-engine/)?snowflake/.+\.(py|sql)$")

CATEGORY_TUTORIALS = "tutorials"
CATEGORY_EXAM_SOLUTIONS = "exam_solutions"
CATEGORY_SUMMARIES = "summaries"
CATEGORY_SCHEMA = "schema"


def classify(rel_path: str) -> str | None:
    """Return one of the manifest keys, or None if the path is
    irrelevant. ``rel_path`` must be repo-relative and POSIX-style."""
    if SUMMARY_RE.match(rel_path):
        return CATEGORY_SUMMARIES
    if SOLUTION_RE.match(rel_path):
        return CATEGORY_EXAM_SOLUTIONS
    if SCHEMA_RE.match(rel_path):
        return CATEGORY_SCHEMA
    if TUTORIAL_RE.match(rel_path):
        return CATEGORY_TUTORIALS
    return None


# ─────────────────────────────────────────────────────────────────────
# Git plumbing
# ─────────────────────────────────────────────────────────────────────
def _git_diff_names(repo_root: Path, ref_from: str, ref_to: str) -> list[str]:
    """Return the list of paths changed between two refs (ACMR only —
    we don't care about deletions for load-side propagation; a deleted
    tutorial doesn't need re-loading, only re-deleting, which is out
    of scope for v1).
    """
    cmd = [
        "git",
        "diff",
        "--name-only",
        "--diff-filter=ACMR",
        f"{ref_from}..{ref_to}",
    ]
    try:
        out = subprocess.check_output(cmd, cwd=str(repo_root), text=True)
    except subprocess.CalledProcessError as e:
        log.error("git diff failed: %s", e)
        raise
    return [line.strip() for line in out.splitlines() if line.strip()]


def _git_rev_parse_toplevel(start: Path) -> Path:
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=str(start), text=True
    )
    return Path(out.strip())


# ─────────────────────────────────────────────────────────────────────
# Manifest model
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Manifest:
    """JSON-serialisable shape consumed by ``sync/run_loaders.py``."""

    from_ref: str = ""
    to_ref: str = ""
    tutorials: list[str] = field(default_factory=list)
    exam_solutions: list[str] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    schema: list[str] = field(default_factory=list)
    loader_code_changed: bool = False
    loader_code_files: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_json(self) -> str:
        # Custom serialisation — dataclasses.asdict would emit
        # ``from_ref`` but the consumer wants ``from``/``to``.
        d = asdict(self)
        d["from"] = d.pop("from_ref")
        d["to"] = d.pop("to_ref")
        return json.dumps(d, indent=2, sort_keys=True)

    def finalise_summary(self) -> None:
        self.summary = {
            "n_tutorials": len(self.tutorials),
            "n_exam_solutions": len(self.exam_solutions),
            "n_summaries": len(self.summaries),
            "schema_touched": bool(self.schema),
            "loader_touched": self.loader_code_changed,
        }


def build_manifest(
    changed_paths: Iterable[str],
    *,
    from_ref: str,
    to_ref: str,
) -> Manifest:
    """Pure function: classify a set of git-diff paths into a Manifest."""
    m = Manifest(from_ref=from_ref, to_ref=to_ref)
    for p in changed_paths:
        # Normalise to forward slashes (git always emits forward
        # slashes but be defensive — the classifier regexes assume it).
        p = p.replace("\\", "/")
        # Loader-code changes are a separate, orthogonal flag.
        if LOADER_CODE_RE.match(p):
            m.loader_code_changed = True
            m.loader_code_files.append(p)
            continue
        cat = classify(p)
        if cat == CATEGORY_TUTORIALS:
            m.tutorials.append(p)
        elif cat == CATEGORY_EXAM_SOLUTIONS:
            m.exam_solutions.append(p)
        elif cat == CATEGORY_SUMMARIES:
            m.summaries.append(p)
        elif cat == CATEGORY_SCHEMA:
            m.schema.append(p)
    # Stable ordering for downstream diff-checks.
    m.tutorials.sort()
    m.exam_solutions.sort()
    m.summaries.sort()
    m.schema.sort()
    m.loader_code_files.sort()
    m.finalise_summary()
    return m


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--from",
        dest="ref_from",
        default="HEAD~1",
        help="Git ref to diff from (default: HEAD~1).",
    )
    ap.add_argument(
        "--to",
        dest="ref_to",
        default="HEAD",
        help="Git ref to diff to (default: HEAD).",
    )
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to `git rev-parse --show-toplevel`.",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write manifest to this file. Defaults to stdout.",
    )
    ap.add_argument(
        "--paths-from-file",
        type=Path,
        default=None,
        help="Skip the git diff and read changed paths from this file "
             "(one per line). Useful for tests and local replay.",
    )
    args = ap.parse_args(argv)

    if args.paths_from_file:
        try:
            changed = [
                line.strip()
                for line in args.paths_from_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError as e:
            log.error("could not read --paths-from-file: %s", e)
            return 2
        from_ref = args.ref_from
        to_ref = args.ref_to
    else:
        repo_root = args.repo_root or _git_rev_parse_toplevel(Path.cwd())
        repo_root = repo_root.resolve()
        if not repo_root.is_dir():
            log.error("repo root not found: %s", repo_root)
            return 2
        try:
            changed = _git_diff_names(repo_root, args.ref_from, args.ref_to)
        except subprocess.CalledProcessError:
            return 2
        from_ref = args.ref_from
        to_ref = args.ref_to

    manifest = build_manifest(changed, from_ref=from_ref, to_ref=to_ref)

    payload = manifest.to_json()
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
        log.info("Wrote manifest to %s", args.output)
    else:
        sys.stdout.write(payload + "\n")

    # Log a one-line summary to stderr so a human reading the CI log
    # gets immediate feedback even if the manifest itself is large.
    log.info(
        "Diff %s..%s — tutorials=%d, exam_solutions=%d, summaries=%d, "
        "schema_touched=%s, loader_touched=%s",
        from_ref,
        to_ref,
        len(manifest.tutorials),
        len(manifest.exam_solutions),
        len(manifest.summaries),
        bool(manifest.schema),
        manifest.loader_code_changed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
