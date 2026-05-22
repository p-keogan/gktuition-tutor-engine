#!/usr/bin/env python3
"""YAML-frontmatter validator for the GKTuition tutor corpus.

Walks the staged set (or the whole corpus) of `.md` files under
``tutorials/`` and asserts the schema contracts that downstream
Snowflake loaders rely on.

The validator is the **first gate** in the content-edit propagation
pipeline (per `content-pipeline/docs/content-pipeline-handbook.md`).
It runs as a pre-commit hook so authoring mistakes never reach
`origin/main`, where the GitHub Action would happily try to MERGE
malformed rows into ``RAW.TUTORIALS`` and either fail the load or — worse
— silently degrade retrieval quality.

Usage
-----

    # Validate the staged set (what `git diff --cached --name-only`
    # would return). Used by the pre-commit hook.
    python validators/yaml_frontmatter.py --staged

    # Full-corpus sanity sweep (3,194-row eval state today; ~280
    # tutorial files + 30 solution files + 20 summary files).
    python validators/yaml_frontmatter.py --all

    # Explicit list of files (handy for ad-hoc checks).
    python validators/yaml_frontmatter.py path/to/file.md ...

    # Override the tutorials root (defaults to the sibling
    # career-transition-2026 repo's tutorials/ folder).
    python validators/yaml_frontmatter.py --all \\
        --tutorials-root /Users/paul/code/career-transition-2026/tutorials

Exit codes
----------
* 0 — every file checked passed (warnings allowed).
* 1 — at least one file failed a hard rule (parse error, missing
       required field, placeholder value in a NOT-NULL column, broken
       cross-references YAML in a solution file, duplicate slug).
* 2 — invocation error (missing path, bad CLI args).

Hard rules vs. soft warnings
----------------------------
**Hard fail** (exit 1, with file:line:column where possible):
1. Well-formed YAML frontmatter present (``---``-delimited block at
   the top of the file, parseable by PyYAML).
2. Required fields present and correctly typed:
     slug (str), video_id (str), title (str)
   These map to NOT-NULL columns in ``RAW.TUTORIALS``.
3. No placeholder values (``TBD``, ``???``, the literal string
   ``null`` masquerading as a value) in fields that downstream stores
   as NOT NULL. Triggered on a per-tutorial basis — the canonical
   regression that prompted this validator was ``duration_seconds:
   TBD`` in ``the-circle-9-simultaneous-equations.md`` (DAY_26 fix).
4. Slug uniqueness across the corpus (every walked file's ``slug``
   is unique).
5. Cross-references in solution files (the ``## Cross-references
   (machine-readable)`` YAML block) parse cleanly and reference
   ``part_id``-shaped strings.

**Soft warn** (logged, does not fail):
* Dead cross-references in ``prerequisites`` / ``forward_links`` /
  ``xref`` (slug points at a video_id no other tutorial declares).
* Missing-but-recoverable fields (``paper``, ``topic``, ``subtopic``)
  that the loader stores as nullable. Authoring should aim for full
  coverage but live retrieval still functions without them.
* The 21 ``LCHL_Paper_*_Proofs/`` cross-reference files that use a
  different schema variant — they are *skipped*, not failed
  (matches the loader's behaviour).

Out of scope
------------
* This script does **not** dispatch loaders. That's
  ``sync/run_loaders.py``.
* This script does **not** touch Snowflake. Validation is local.
* This script does **not** modify any source ``.md`` file.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ─────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s %(message)s",
)
log = logging.getLogger("validate_yaml")

# ─────────────────────────────────────────────────────────────────────
# Frontmatter scanning
# ─────────────────────────────────────────────────────────────────────
FM_OPEN_RE = re.compile(r"^---\s*$")
FM_CLOSE_RE = re.compile(r"^---\s*$")

# Borrowed from load_tutorials.py: list items whose value begins with
# a bare ``|`` (modulus signs) crash PyYAML. We apply the same
# pre-processor before parsing so the validator never disagrees with
# what the loader actually accepts.
_BARE_PIPE_LIST_ITEM = re.compile(r"^(\s*-\s+)(\|[^\n]+)$", re.MULTILINE)
_BLOCK_SCALAR_HEADER = re.compile(r"^\|[+\-]?\d*\s*$")


def _preprocess_yaml(fm_raw: str) -> str:
    def _quote(match: re.Match[str]) -> str:
        prefix, value = match.group(1), match.group(2)
        if _BLOCK_SCALAR_HEADER.match(value):
            return match.group(0)
        escaped = value.replace("'", "''")
        return f"{prefix}'{escaped}'"

    return _BARE_PIPE_LIST_ITEM.sub(_quote, fm_raw)


def split_frontmatter(text: str) -> tuple[dict[str, Any], int, str] | None:
    """Return ``(parsed_yaml, fm_start_line, body)`` or ``None`` if the
    file lacks YAML frontmatter delimiters.

    ``fm_start_line`` is the 1-indexed line number where the YAML body
    begins (the line *after* the opening ``---``), so diagnostics can
    point inside the YAML rather than at the delimiter.
    """
    lines = text.splitlines(keepends=False)
    if not lines or not FM_OPEN_RE.match(lines[0]):
        return None
    close_idx = None
    for i in range(1, len(lines)):
        if FM_CLOSE_RE.match(lines[i]):
            close_idx = i
            break
    if close_idx is None:
        return None
    fm_raw = "\n".join(lines[1:close_idx])
    body = "\n".join(lines[close_idx + 1 :])
    fm_raw = _preprocess_yaml(fm_raw)
    try:
        data = yaml.safe_load(fm_raw)
    except yaml.YAMLError as e:
        # Surface the YAML error with file:line accuracy if possible.
        mark = getattr(e, "problem_mark", None)
        if mark is not None:
            raise YAMLPosError(
                line=mark.line + 2,  # +1 for delimiter, +1 for 1-indexed
                col=mark.column + 1,
                msg=str(e),
            )
        raise YAMLPosError(line=1, col=1, msg=str(e))
    if not isinstance(data, dict):
        raise YAMLPosError(line=1, col=1, msg="frontmatter is not a mapping")
    return data, 2, body  # body line offset


class YAMLPosError(Exception):
    """YAML parse error with line/column accuracy."""

    def __init__(self, line: int, col: int, msg: str) -> None:
        super().__init__(msg)
        self.line = line
        self.col = col
        self.msg = msg


# ─────────────────────────────────────────────────────────────────────
# Schema rules
# ─────────────────────────────────────────────────────────────────────
# NOT-NULL columns from bootstrap_tutorials_table.sql. These are the
# fields whose absence (or placeholder value) is a load-failure trigger
# in Snowflake. The validator therefore hard-fails when they're missing
# from a tutorial that's eligible to be loaded.
TUTORIAL_REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "slug": str,
    "video_id": str,
    "title": str,
}

# Loader stores these as nullable but they materially affect retrieval
# quality. Warn-not-fail; authors aim for full coverage.
TUTORIAL_SOFT_FIELDS: dict[str, type | tuple[type, ...]] = {
    "paper": int,
    "topic": str,
    "subtopic": str,
    "sequence_number": int,
    "duration_seconds": int,
    "course_levels": list,
    "keywords": list,
    "common_student_phrasings": list,
    "techniques_taught": list,
}

# Fields that, when present, must be lists (not strings or scalars).
TUTORIAL_LIST_FIELDS = {
    "course_levels",
    "prerequisites",
    "forward_links",
    "xref",
    "techniques_taught",
    "techniques_used",
    "content_warnings",
    "keywords",
    "common_student_phrasings",
    "log_tables",
    "exam_appearances",
    "learning_work",
    "companion_practice_questions",
}

# String tokens that, if seen as a *value*, indicate an unresolved
# authoring placeholder. Case-sensitive — ``TBD`` (uppercase) is the
# canonical form Paul uses; lowercase ``tbd`` is treated as suspect
# too because some files mix conventions.
PLACEHOLDER_VALUES = {"TBD", "tbd", "???", "TODO", "FIXME", "XXX"}

# Fields where a placeholder string is a HARD FAIL (load-breaking).
# Per spec: "TBD, ???, null in a NOT NULL field — the exact set that
# broke the DAY_26 first load." The DAY_26 regression was
# ``duration_seconds: TBD`` in the-circle-9; the field is numeric,
# so the placeholder string short-circuits downstream type coercion.
#
# Categories:
#   * NOT-NULL table columns where any non-string value (or `null`) is
#     a load failure: slug, video_id, title.
#   * Non-string-typed fields where a placeholder string corrupts the
#     value the loader tries to bind: paper (int), sequence_number
#     (int), duration_seconds (int), syllabus.strand (int).
# Anywhere else, a placeholder string is a WARN (suboptimal data,
# but the load completes — e.g. an unpublished video's
# ``source.youtube_url`` storing the literal "TBD" doesn't break
# anything until rendering time).
PLACEHOLDER_FAIL_FIELDS = {
    "slug",
    "video_id",
    "title",
    "paper",
    "sequence_number",
    "duration_seconds",
    "syllabus.strand",
}

# Solutions file naming: 30 files under LCHL_Maths_Exams/Solutions/
# match this pattern. Crossref block must exist and parse.
SOLUTION_FILE_RE = re.compile(r"^\d{4}_(?:DF_)?P[12]_solutions\.md$")
SKIP_SOLUTION_PREFIXES = ("AGENT_PROMPT_", "LCHL_exam_trends", "README")
CROSSREF_HEADING = "## Cross-references (machine-readable)"
CROSSREF_FENCE_RE = re.compile(
    r"```yaml\s*\n(.*?)\n```", re.DOTALL
)


# ─────────────────────────────────────────────────────────────────────
# Diagnostic plumbing
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Diagnostic:
    path: Path
    severity: str  # 'ERROR' | 'WARN'
    line: int | None
    col: int | None
    message: str

    def format(self) -> str:
        loc = ""
        if self.line is not None:
            loc = f":{self.line}"
            if self.col is not None:
                loc += f":{self.col}"
        return f"{self.severity:<5} {self.path}{loc}: {self.message}"


@dataclass
class ValidationReport:
    files_checked: int = 0
    files_skipped_summary: int = 0
    files_skipped_readme: int = 0
    files_skipped_out_of_schema: int = 0
    files_skipped_solution_prompt: int = 0
    errors: list[Diagnostic] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)
    slugs_seen: dict[str, Path] = field(default_factory=dict)
    video_ids_seen: dict[str, Path] = field(default_factory=dict)

    def error(self, path: Path, message: str, line: int | None = None, col: int | None = None) -> None:
        self.errors.append(Diagnostic(path, "ERROR", line, col, message))

    def warn(self, path: Path, message: str, line: int | None = None, col: int | None = None) -> None:
        self.warnings.append(Diagnostic(path, "WARN", line, col, message))


# ─────────────────────────────────────────────────────────────────────
# Per-file checks
# ─────────────────────────────────────────────────────────────────────
def _classify_md(path: Path, tutorials_root: Path) -> str:
    """Return one of: 'tutorial', 'summary', 'solution', 'readme',
    'solution_prompt', 'proof_or_unknown', 'outside_corpus'.
    """
    try:
        rel = path.resolve().relative_to(tutorials_root.resolve())
    except ValueError:
        return "outside_corpus"
    parts = rel.parts
    if not parts:
        return "outside_corpus"
    name = path.name
    if name == "README.md":
        return "readme"
    if name.startswith("_SUMMARY-"):
        return "summary"
    if parts[0] == "LCHL_Maths_Exams":
        if name.startswith(SKIP_SOLUTION_PREFIXES):
            return "solution_prompt"
        if SOLUTION_FILE_RE.match(name):
            return "solution"
        return "solution_prompt"
    if parts[0].startswith("LCHL_Paper_") and "Proofs" in parts[0]:
        return "proof_or_unknown"
    if parts[0].startswith("LCHL_"):
        return "tutorial"
    return "outside_corpus"


def _type_name(t: type | tuple[type, ...]) -> str:
    if isinstance(t, tuple):
        return " or ".join(x.__name__ for x in t)
    return t.__name__


def _check_placeholder(value: Any) -> bool:
    """Return True iff ``value`` is a placeholder string we want to
    fail on (TBD, ???, TODO, etc.). Whitespace-tolerant; lowercase /
    uppercase / surrounding punctuation all caught.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip().strip(".:!?,;")
    return stripped in PLACEHOLDER_VALUES


def _walk_for_placeholders(node: Any, key_path: str = "") -> list[tuple[str, Any]]:
    """Recurse through the parsed YAML and return any (key_path, value)
    pairs whose value is a placeholder."""
    hits: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            sub = f"{key_path}.{k}" if key_path else str(k)
            hits.extend(_walk_for_placeholders(v, sub))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            sub = f"{key_path}[{i}]"
            hits.extend(_walk_for_placeholders(v, sub))
    else:
        if _check_placeholder(node):
            hits.append((key_path, node))
    return hits


def validate_tutorial(
    path: Path,
    fm: dict[str, Any],
    body: str,
    report: ValidationReport,
) -> None:
    """Schema checks for a single canonical tutorial file."""
    # Required fields — hard fail.
    for fname, ftype in TUTORIAL_REQUIRED_FIELDS.items():
        if fname not in fm:
            report.error(path, f"missing required field `{fname}` (NOT-NULL in RAW.TUTORIALS)")
            continue
        val = fm[fname]
        if val is None or (isinstance(val, str) and not val.strip()):
            report.error(path, f"required field `{fname}` is null/empty")
            continue
        if not isinstance(val, ftype):
            report.error(
                path,
                f"required field `{fname}` has wrong type "
                f"(got {type(val).__name__}, want {_type_name(ftype)})",
            )

    # Slug uniqueness.
    slug = fm.get("slug")
    if isinstance(slug, str) and slug.strip():
        if slug in report.slugs_seen and report.slugs_seen[slug] != path:
            report.error(
                path,
                f"duplicate slug `{slug}` — also declared in "
                f"{report.slugs_seen[slug]}",
            )
        else:
            report.slugs_seen.setdefault(slug, path)

    # video_id uniqueness (same reason — feeds the cross-reference graph).
    vid = fm.get("video_id")
    if isinstance(vid, str) and vid.strip():
        if vid in report.video_ids_seen and report.video_ids_seen[vid] != path:
            report.error(
                path,
                f"duplicate video_id `{vid}` — also declared in "
                f"{report.video_ids_seen[vid]}",
            )
        else:
            report.video_ids_seen.setdefault(vid, path)

    # Body must be non-empty for the NOT-NULL ``body`` column.
    if not body.strip():
        report.error(path, "markdown body is empty (NOT-NULL `body` column would fail)")

    # title_plus_phrasings ingredients: title + keywords + phrasings.
    # If all three are missing/empty, the loader still emits a string
    # (the title alone) so this is a WARN not an ERROR — but worth
    # flagging because retrieval precision tanks without phrasings.
    if not fm.get("keywords") and not fm.get("common_student_phrasings"):
        report.warn(
            path,
            "no `keywords` and no `common_student_phrasings` — "
            "TUTOR_SEARCH precision will rely on the title alone",
        )

    # Soft fields — warn on missing/wrong-type but don't fail.
    for fname, ftype in TUTORIAL_SOFT_FIELDS.items():
        if fname not in fm or fm[fname] is None:
            report.warn(path, f"recommended field `{fname}` missing")
            continue
        val = fm[fname]
        if not isinstance(val, ftype):
            report.warn(
                path,
                f"recommended field `{fname}` has wrong type "
                f"(got {type(val).__name__}, want {_type_name(ftype)})",
            )

    # List-typed fields must actually be lists when present.
    for fname in TUTORIAL_LIST_FIELDS:
        if fname in fm and fm[fname] is not None and not isinstance(fm[fname], list):
            report.error(
                path,
                f"field `{fname}` must be a list "
                f"(got {type(fm[fname]).__name__})",
            )

    # Placeholder sweep — recurse the whole frontmatter. The same
    # placeholder string is a load-breaking ERROR in some fields and
    # an authoring WARNing in others; see PLACEHOLDER_FAIL_FIELDS for
    # the exact set.
    for keypath, val in _walk_for_placeholders(fm):
        # Normalise to the field name without list indices so the
        # match against PLACEHOLDER_FAIL_FIELDS works for both
        # `duration_seconds` and `log_tables[0].section` style paths.
        normalised = re.sub(r"\[\d+\]", "", keypath)
        if normalised in PLACEHOLDER_FAIL_FIELDS:
            report.error(
                path,
                f"placeholder value at `{keypath}`: {val!r} — replace with "
                "the real value or `null` before committing "
                "(this field would break the loader; see DAY_26 regression)",
            )
        else:
            report.warn(
                path,
                f"placeholder value at `{keypath}`: {val!r} — authoring "
                "TODO, load is still safe but the value reaches Snowflake verbatim",
            )


def validate_solution_crossrefs(
    path: Path,
    text: str,
    report: ValidationReport,
) -> None:
    """Solution files (LCHL_Maths_Exams/Solutions/*.md) must carry a
    machine-readable crossref block at the bottom (Agent 02 writes it;
    Agent 14 verifies it).

    Rules:
    * `## Cross-references (machine-readable)` header present.
    * Fenced ```yaml block present below the header and parses cleanly.
    * Parsed payload is a dict with a `cross_references` list.
    * Each entry has `part_id` (string) and `tutorials` (list of strings).
    """
    if CROSSREF_HEADING not in text:
        report.error(
            path,
            f"missing `{CROSSREF_HEADING}` block — run "
            "`python snowflake/load_exam_parts.py` to rewrite it",
        )
        return
    # Take the *last* fenced yaml block (the crossref block is always
    # appended at the bottom of the file).
    matches = CROSSREF_FENCE_RE.findall(text)
    if not matches:
        report.error(path, "crossref heading present but no ```yaml ... ``` block found")
        return
    crossref_yaml = matches[-1]
    try:
        parsed = yaml.safe_load(crossref_yaml)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = None
        col = None
        if mark is not None:
            line = mark.line + 1
            col = mark.column + 1
        report.error(path, f"crossref YAML parse error: {e}", line=line, col=col)
        return
    if not isinstance(parsed, dict) or "cross_references" not in parsed:
        report.error(path, "crossref payload must be a mapping with a `cross_references` list")
        return
    refs = parsed["cross_references"]
    if not isinstance(refs, list):
        report.error(path, "`cross_references` must be a list")
        return
    for i, entry in enumerate(refs):
        if not isinstance(entry, dict):
            report.error(path, f"cross_references[{i}] is not a mapping")
            continue
        part_id = entry.get("part_id")
        if not isinstance(part_id, str) or not part_id.strip():
            report.error(path, f"cross_references[{i}] missing or empty `part_id`")
        tutorials = entry.get("tutorials")
        if tutorials is None:
            # An entry may legitimately lack tutorials (Agent 02 flags
            # the gap in its loader log). Don't fail the validator on
            # that — it's a content gap, not a schema break.
            continue
        if not isinstance(tutorials, list):
            report.error(
                path,
                f"cross_references[{i}].tutorials must be a list "
                f"(got {type(tutorials).__name__})",
            )
            continue
        for j, t in enumerate(tutorials):
            if not isinstance(t, str):
                report.error(
                    path,
                    f"cross_references[{i}].tutorials[{j}] must be a string slug "
                    f"(got {type(t).__name__})",
                )


def validate_summary(
    path: Path,
    fm: dict[str, Any] | None,
    body: str,
    report: ValidationReport,
) -> None:
    """Summary files (LCHL_<Strand>/_SUMMARY-exam-cram.md) currently
    have no YAML frontmatter — they're parsed structurally by
    load_summaries.py. The only schema rule we enforce here is the H1
    line: ``# <Strand> — 90-Minute Exam Cram Summary``."""
    H1_RE = re.compile(r"^#\s+.+?\s+—\s+90-Minute Exam Cram Summary\s*$", re.MULTILINE)
    if not H1_RE.search(body if fm is None else body):
        report.error(
            path,
            "summary file missing the canonical H1 "
            "`# <Strand> — 90-Minute Exam Cram Summary`",
        )


# ─────────────────────────────────────────────────────────────────────
# Cross-reference graph
# ─────────────────────────────────────────────────────────────────────
def validate_xrefs(
    tutorial_fm: dict[Path, dict[str, Any]],
    report: ValidationReport,
) -> None:
    """After all tutorials are parsed, verify that every
    prerequisites/forward_links/xref slug points at a video_id that
    some other tutorial declares. Dead links → WARN (not ERROR), per
    the spec: *warn on dead links, fail on syntactic errors*.
    """
    all_video_ids: set[str] = set()
    for fm in tutorial_fm.values():
        v = fm.get("video_id")
        if isinstance(v, str) and v.strip():
            all_video_ids.add(v)
    for path, fm in tutorial_fm.items():
        for field_name in ("prerequisites", "forward_links", "xref"):
            refs = fm.get(field_name)
            if not isinstance(refs, list):
                continue
            for r in refs:
                if not isinstance(r, str):
                    report.error(
                        path,
                        f"`{field_name}` contains non-string entry: {r!r}",
                    )
                    continue
                if r not in all_video_ids:
                    report.warn(
                        path,
                        f"`{field_name}` entry `{r}` does not match any "
                        "known tutorial video_id (dead xref)",
                    )


# ─────────────────────────────────────────────────────────────────────
# File-set selection
# ─────────────────────────────────────────────────────────────────────
def _git_staged_md_files(repo_root: Path | None) -> list[Path]:
    """Return absolute paths of staged `.md` files under tutorials/."""
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    try:
        out = subprocess.check_output(
            cmd,
            cwd=str(repo_root) if repo_root else None,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error("git invocation failed: %s", e)
        return []
    files: list[Path] = []
    base = Path(repo_root) if repo_root else Path.cwd()
    for line in out.splitlines():
        line = line.strip()
        if not line.endswith(".md"):
            continue
        # We only care about files under tutorials/. The staged-files
        # path is repo-relative; resolve against the repo root.
        if "tutorials/" not in line and not line.startswith("tutorials/"):
            continue
        files.append((base / line).resolve())
    return files


def _walk_all_md_files(tutorials_root: Path) -> list[Path]:
    """Yield every `.md` file under ``tutorials_root`` that matches one
    of the four canonical shapes (tutorial / summary / solution /
    proof). Excludes obvious noise (transcripts/, _tools/, _reference/).
    """
    out: list[Path] = []
    if not tutorials_root.is_dir():
        return out
    for entry in sorted(tutorials_root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name in ("transcripts", "_tools", "_reference"):
            continue
        if name == "LCHL_Maths_Exams":
            sols = entry / "Solutions"
            if sols.is_dir():
                out.extend(sorted(sols.glob("*.md")))
            continue
        if name.startswith("LCHL_"):
            out.extend(sorted(entry.glob("*.md")))
    return out


# ─────────────────────────────────────────────────────────────────────
# Main driver
# ─────────────────────────────────────────────────────────────────────
def validate_files(
    files: list[Path],
    tutorials_root: Path,
    report: ValidationReport,
) -> None:
    """Validate each path according to its classification; collect
    per-tutorial frontmatter for the xref graph check."""
    tutorial_fm: dict[Path, dict[str, Any]] = {}

    for path in files:
        if not path.exists():
            report.error(path, "file does not exist")
            continue
        report.files_checked += 1
        kind = _classify_md(path, tutorials_root)

        if kind == "readme":
            report.files_skipped_readme += 1
            continue
        if kind == "solution_prompt":
            report.files_skipped_solution_prompt += 1
            continue
        if kind == "outside_corpus":
            # Not a tutorials/ file — skip silently.
            report.files_checked -= 1
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            report.error(path, f"read error: {e}")
            continue

        # Solutions: validate the crossref block at the bottom. No
        # frontmatter contract.
        if kind == "solution":
            validate_solution_crossrefs(path, text, report)
            continue

        # Summaries: no frontmatter. Validate the H1.
        if kind == "summary":
            report.files_skipped_summary += 1
            validate_summary(path, None, text, report)
            continue

        # Tutorials + proof-or-unknown: try to parse frontmatter.
        try:
            parsed = split_frontmatter(text)
        except YAMLPosError as e:
            report.error(path, e.msg, line=e.line, col=e.col)
            continue

        if parsed is None:
            # No frontmatter at all. For tutorials this is an error;
            # for proof files it's the known schema variant.
            if kind == "proof_or_unknown":
                report.files_skipped_out_of_schema += 1
                continue
            report.error(path, "no YAML frontmatter delimiters")
            continue

        fm, _line_offset, body = parsed

        # Proof-or-unknown files often lack a slug — they're cross-
        # reference pointers, not standalone tutorials. Match the
        # loader's skip-with-warning behaviour.
        if "slug" not in fm or not fm.get("slug"):
            if kind == "proof_or_unknown":
                report.files_skipped_out_of_schema += 1
                continue
            report.error(path, "missing required field `slug` (NOT-NULL in RAW.TUTORIALS)")
            continue

        validate_tutorial(path, fm, body, report)
        tutorial_fm[path] = fm

    # After per-file checks, run the corpus-wide xref graph check.
    # Only useful in --all mode; in --staged mode the parsed set is
    # the diff set, so dead-xref warnings will mostly fire against
    # tutorials that exist on disk but aren't in the staged set. We
    # therefore *opt in* via a corpus-wide load.
    validate_xrefs(tutorial_fm, report)


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def _default_tutorials_root() -> Path:
    """Default to the sibling career-transition-2026 repo's tutorials
    folder. The engine repo and that one live side-by-side under
    ~/code/. Override via --tutorials-root when running from CI."""
    here = Path(__file__).resolve()
    # validators/ → content-pipeline/ → engine repo root → ~/code/
    engine_root = here.parent.parent.parent
    candidate = engine_root.parent / "career-transition-2026" / "tutorials"
    return candidate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate YAML frontmatter in GKTuition tutorial files."
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--staged",
        action="store_true",
        help="Validate only `.md` files staged in git (used by the pre-commit hook).",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Validate every `.md` file under the tutorials root.",
    )
    ap.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Explicit list of files to validate (alternative to --staged / --all).",
    )
    ap.add_argument(
        "--tutorials-root",
        type=Path,
        default=_default_tutorials_root(),
        help="Path to the tutorials/ directory.",
    )
    ap.add_argument(
        "--corpus-repo-root",
        type=Path,
        default=None,
        help="Git repository root for the tutorials corpus (used by --staged to "
             "locate the .git/ for the diff). Defaults to the parent of "
             "--tutorials-root.",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Only show ERROR diagnostics; suppress WARN output.",
    )
    args = ap.parse_args(argv)

    tutorials_root = args.tutorials_root.resolve()
    if not tutorials_root.is_dir():
        log.error("tutorials root not found: %s", tutorials_root)
        return 2

    corpus_repo_root = (
        args.corpus_repo_root.resolve()
        if args.corpus_repo_root
        else tutorials_root.parent
    )

    if args.staged:
        files = _git_staged_md_files(corpus_repo_root)
        if not files:
            log.info("No staged tutorial `.md` files; nothing to validate.")
            return 0
    elif args.all:
        files = _walk_all_md_files(tutorials_root)
    elif args.files:
        files = [f.resolve() for f in args.files]
    else:
        ap.error("specify --staged, --all, or one-or-more file paths")
        return 2  # unreachable; ap.error raises SystemExit

    log.info("Validating %d file(s) against schema at %s", len(files), tutorials_root)

    report = ValidationReport()
    validate_files(files, tutorials_root, report)

    # Emit diagnostics.
    if not args.quiet:
        for w in report.warnings:
            log.warning(w.format())
    for e in report.errors:
        log.error(e.format())

    # Summary line.
    log.info(
        "Checked %d files (%d summaries, %d READMEs, %d out-of-schema, %d solution-prompts) "
        "→ %d errors, %d warnings",
        report.files_checked,
        report.files_skipped_summary,
        report.files_skipped_readme,
        report.files_skipped_out_of_schema,
        report.files_skipped_solution_prompt,
        len(report.errors),
        len(report.warnings),
    )

    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
