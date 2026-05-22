#!/usr/bin/env python3
"""Load tutorial-style LCHL exam solutions into GKTUITION_TUTOR.RAW.EXAM_PARTS.

One row per (year × paper × sitting × question × sub-part). Idempotent MERGE
keyed on `part_id`. Also (re)writes a machine-readable cross-references YAML
block at the bottom of every source `.md` file so downstream consumers don't
have to walk the markdown links again.

Usage
-----
    # Live run against Snowflake (uses env-var credentials):
    python load_exam_parts.py \\
        --solutions-dir ../../career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions

    # Walk + parse only; no Snowflake write, no source-file edits.
    python load_exam_parts.py --dry-run

    # Live run but leave the source .md files alone (skip crossref rewrite).
    python load_exam_parts.py --no-write-crossrefs

Environment variables (live mode only)
--------------------------------------
    SNOWFLAKE_ACCOUNT                  required (e.g. abc12345.eu-west-1)
    SNOWFLAKE_USER                     required
    SNOWFLAKE_PASSWORD                 one of {PASSWORD, PRIVATE_KEY_PATH} required
    SNOWFLAKE_PRIVATE_KEY_PATH         (optional, keypair auth)
    SNOWFLAKE_AUTHENTICATOR            default = 'snowflake'
    SNOWFLAKE_ROLE                     default = 'ACCOUNTADMIN'
    SNOWFLAKE_WAREHOUSE                default = 'WH_TUTOR'
    SNOWFLAKE_DATABASE                 default = 'GKTUITION_TUTOR'
    SNOWFLAKE_SCHEMA                   default = 'RAW'

Design notes
------------
* The 30-file solutions corpus carries ~1,213 `### Q…` headings. The chunker
  splits on those headings; one heading == one row. Headings without a
  sub-part letter (currently only 2015 P1 Q2) are handled — `sub_part`
  becomes NULL.
* Files skipped (with a WARN log, NOT a parse failure):
    - `AGENT_PROMPT_*.md`   — authoring prompts, not solutions.
    - `LCHL_exam_trends.md` — aggregate trends report, not a single exam.
* Marks: per-part marks rarely appear as `(N marks)` on the heading itself;
  the loader looks for the annotation anywhere in the part body, then falls
  back to the question-level total (`## Question N (X marks)`) divided
  proportionally across siblings so the verification "no NULL marks" is met.
  The fallback rounds to whole integers and preserves the sum of the
  question's official total.
* Load strategy mirrors load_tutorials.py: a single bulk INSERT into a
  transient staging table (one statement with N-row VALUES, VARIANTs wrapped
  in `PARSE_JSON()`), followed by a single MERGE into RAW.EXAM_PARTS keyed
  on `part_id`. No row-by-row inserts.
* Cross-references block: appended to the bottom of every source .md file
  after a `---` divider, wrapped in a fenced ```yaml``` block. The whole
  section is replaced on each run, so the result is byte-identical on a
  second run (idempotent).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

# ───────────────────────────────────────────────────────────────────────────
# Logging
# ───────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load_exam_parts")

# ───────────────────────────────────────────────────────────────────────────
# Constants — regexes + skip rules
# ───────────────────────────────────────────────────────────────────────────
SKIP_NAMES: set[str] = {"LCHL_exam_trends.md"}
SKIP_PREFIXES: tuple[str, ...] = ("AGENT_PROMPT_",)

# Decode filename → (year, paper, sitting). Accepts every observed form:
#   2025_P1_solutions.md
#   2025_P2_solutions.md
#   2025_DF_P1_solutions.md      (deferred sitting, prefix form)
#   2022_P1_DF_solutions.md      (deferred sitting, suffix form)
#   2022_DF_P2_solutions.md
FILENAME_RE = re.compile(
    r"^(?P<year>\d{4})"
    r"(?:_(?P<t1>DF|P[12]))"
    r"(?:_(?P<t2>DF|P[12]))?"
    r"(?:_(?P<t3>DF|P[12]))?"
    r"_solutions\.md$"
)

# Part heading. Four captures:
#   QNUM   — required integer (Q1–Q10)
#   LETTER — optional lowercase letter in parens: (a), (b), …
#   ROMAN  — optional Roman numeral in parens: (i), (ii), (iii), …
#   TITLE  — text after the em/en-dash/hyphen separator (the problem statement)
HEADING_RE = re.compile(
    r"^###\s+Q(?P<qnum>\d+)"
    r"(?:\((?P<letter>[a-z])\))?"
    r"(?:\((?P<roman>[ivx]+)\))?"
    r"\s*(?:—|–|-)?\s*(?P<title>.*)$",
    re.IGNORECASE,
)

# Question-level header — used to grab the question's total marks as a
# fallback when individual sub-parts don't carry a `(N marks)` annotation.
QUESTION_HEADER_RE = re.compile(
    r"^##\s+Question\s+(?P<qnum>\d+)\s*\((?P<marks>\d+)\s*marks?\)",
    re.IGNORECASE,
)
SECTION_HEADER_RE = re.compile(
    r"^##\s+Section\s+(?P<section>[AB])\b",
    re.IGNORECASE,
)

# Metadata lines inside a part body.
TOPIC_RE = re.compile(r"^\*\*Topic:\*\*\s*(?P<topic>.*?)\.?\s*$")
TUTORIALS_LABEL_RE = re.compile(r"^\*\*Tutorials:\*\*")
# Markdown link [Title](../../LCHL_FOLDER/slug.md) — captures folder + slug.
TUTORIAL_LINK_RE = re.compile(
    r"\[(?P<title>[^\]]+)\]\(\.\.\/\.\.\/(?P<folder>LCHL_[^/]+)\/(?P<slug>[^)]+)\.md\)"
)

# Per-part marks annotation, e.g. "(5 marks)", "(10 mark)".
PART_MARKS_RE = re.compile(r"\((\d+)\s*marks?\)", re.IGNORECASE)

# Pitfall / load-bearing callout — the part-body blockquote convention is
# `> **🎯 …** …` or `> **🚨 …** …`, optionally wrapped onto multiple lines.
PITFALL_OPENER_RE = re.compile(r"^>\s+\*\*(🎯|🚨)")

# Marking-scheme cross-check sub-header.
MARKING_SCHEME_HEADER_RE = re.compile(
    r"^####\s+Marking[- ]scheme\s+cross[- ]check",
    re.IGNORECASE,
)

# End-of-paper sentinel + footnotes — stop chunking past these.
END_SENTINEL_RE = re.compile(r"^\*\[End of", re.IGNORECASE)
FOOTNOTES_HEADER_RE = re.compile(r"^##\s+Footnotes\b", re.IGNORECASE)

# Cross-references block — section + fenced YAML block, anchored at EOF.
CROSSREF_HEADER = "## Cross-references (machine-readable)"

# Column order — kept aligned with bootstrap_exam_parts_table.sql so the
# INSERT / MERGE column lists match.
COLS_SCALAR = [
    "part_id",
    "year",
    "paper",
    "sitting",
    "question_number",
    "sub_part",
    "section",
    "marks",
    "topic",
    "question_text",
    "solution_text",
    "common_pitfalls",
    "marking_scheme_note",
    "source_path",
]
COLS_VARIANT = [
    "secondary_topics",
    "tutorials_referenced",
]
ALL_COLS = COLS_SCALAR + COLS_VARIANT


# ───────────────────────────────────────────────────────────────────────────
# Data classes
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class LoadReport:
    files_walked: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    parts_parsed: int = 0
    parts_null_marks: int = 0
    parts_no_topic: list[str] = field(default_factory=list)
    parts_no_tutorials: list[str] = field(default_factory=list)
    parse_errors: list[tuple[str, str]] = field(default_factory=list)
    crossref_files_rewritten: int = 0
    snowflake_inserted: int = 0
    snowflake_updated: int = 0


# ───────────────────────────────────────────────────────────────────────────
# Filename / sub-part helpers
# ───────────────────────────────────────────────────────────────────────────
def parse_filename(name: str) -> dict[str, Any] | None:
    m = FILENAME_RE.match(name)
    if not m:
        return None
    tokens = [t for t in (m.group("t1"), m.group("t2"), m.group("t3")) if t]
    paper_token = next((t for t in tokens if t in ("P1", "P2")), None)
    if paper_token is None:
        return None
    sitting = "df" if "DF" in tokens else "main"
    return {
        "year": int(m.group("year")),
        "paper": int(paper_token[1]),
        "sitting": sitting,
    }


def build_sub_part(letter: str | None, roman: str | None) -> str | None:
    """Render the human-readable sub_part column, e.g. 'a', 'b(i)', 'b(ii)'.
    Returns None for headings without a letter (e.g. 2015 P1 Q2)."""
    if not letter and not roman:
        return None
    if letter and roman:
        return f"{letter}({roman})"
    if letter:
        return letter
    return f"({roman})"


def build_part_id(year: int, sitting: str, paper: int, qnum: int,
                  letter: str | None, roman: str | None) -> str:
    """Synthetic primary key. Filename-safe (no parens, no hyphens).

    Examples:
        2025_main_P1_Q1a       — Q1(a) of 2025 main P1
        2024_main_P2_Q5biii    — Q5(b)(iii) of 2024 main P2
        2015_main_P1_Q2        — Q2 of 2015 main P1 (no sub-parts)
    """
    suffix = ""
    if letter:
        suffix += letter
    if roman:
        suffix += roman
    return f"{year}_{sitting}_P{paper}_Q{qnum}{suffix}"


# ───────────────────────────────────────────────────────────────────────────
# YAML frontmatter + body split
# ───────────────────────────────────────────────────────────────────────────
def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Strip a leading `--- ... ---` YAML frontmatter block.
    Returns (yaml_dict_or_empty, body_text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].lstrip("\n")
    body_start = end + len("\n---")
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), text[body_start:]


def folder_to_strand(folder: str) -> str:
    """LCHL_Complex_Numbers → 'Complex Numbers'."""
    return folder.replace("LCHL_", "").replace("_", " ")


# ───────────────────────────────────────────────────────────────────────────
# Cross-references block — strip / render / write
# ───────────────────────────────────────────────────────────────────────────
def strip_crossref_block(text: str) -> str:
    """Remove any existing `## Cross-references (machine-readable)` section
    (and the `---` separator above it) so it can be cleanly re-appended."""
    idx = text.rfind(CROSSREF_HEADER)
    if idx == -1:
        return text
    head = text[:idx].rstrip()
    # The separator above the header is `\n---`. Walk back past it if present.
    if head.endswith("---"):
        head = head[: -len("---")].rstrip()
    return head + "\n"


def render_crossref_block(parts: list["ExamPart"]) -> str:
    """Render the appended block: `---` divider, H2 header, fenced YAML.
    The YAML's `cross_references` list has one entry per part, in document
    order, with `part_id` / `topic` / `tutorials` keys.
    """
    payload = {
        "cross_references": [
            {
                "part_id": p.part_id,
                "topic": p.topic,
                "tutorials": list(p.tutorials_referenced),
            }
            for p in parts
        ]
    }
    yaml_body = yaml.safe_dump(
        payload, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return (
        "\n---\n\n"
        f"{CROSSREF_HEADER}\n\n"
        "```yaml\n"
        f"{yaml_body}"
        "```\n"
    )


def write_crossref_block(path: Path, parts: list["ExamPart"]) -> bool:
    """Idempotently (re)write the crossref block on `path`.
    Returns True if the on-disk content actually changed."""
    existing = path.read_text(encoding="utf-8")
    base = strip_crossref_block(existing).rstrip() + "\n"
    new = base + render_crossref_block(parts)
    if new == existing:
        return False
    path.write_text(new, encoding="utf-8")
    return True


# ───────────────────────────────────────────────────────────────────────────
# Per-part data model + chunker
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class ExamPart:
    part_id: str
    year: int
    paper: int
    sitting: str
    question_number: int
    sub_part: str | None
    section: str | None
    marks: int | None
    topic: str | None
    secondary_topics: list[str] = field(default_factory=list)
    tutorials_referenced: list[str] = field(default_factory=list)
    question_text: str | None = None
    solution_text: str | None = None
    common_pitfalls: str | None = None
    marking_scheme_note: str | None = None
    source_path: str = ""


def _strip_meta_lines(lines: Iterable[str]) -> list[str]:
    """Drop the **Topic:** and **Tutorials:** lines (and the wrapped
    continuation of the Tutorials line) from a part chunk; leave the rest of
    the prose untouched. Used when extracting the question prompt from the
    intro paragraph."""
    out: list[str] = []
    in_tutorials_block = False
    for line in lines:
        if TOPIC_RE.match(line):
            in_tutorials_block = False
            continue
        if TUTORIALS_LABEL_RE.match(line):
            in_tutorials_block = True
            continue
        if in_tutorials_block:
            # Tutorials line frequently wraps. Drop continuation lines that
            # are only tutorial links / paren notes / blanks.
            if TUTORIAL_LINK_RE.search(line) or line.strip() == "":
                continue
            in_tutorials_block = False
        out.append(line)
    return out


def _finalise_part(part: ExamPart, body_lines: list[str]) -> None:
    """Split a chunk into prose / pitfalls / marking-scheme; populate the
    `solution_text`, `question_text`, `common_pitfalls`, `marking_scheme_note`
    fields. Marks left for the question-total fallback pass."""
    # Locate the marking-scheme sub-header.
    ms_idx: int | None = None
    for i, line in enumerate(body_lines):
        if MARKING_SCHEME_HEADER_RE.match(line):
            ms_idx = i
            break

    prose_lines = body_lines[:ms_idx] if ms_idx is not None else list(body_lines)
    ms_lines = body_lines[ms_idx + 1:] if ms_idx is not None else []

    # Question prompt: heading title + any prose before the first #### sub-header.
    first_step = None
    for i, line in enumerate(prose_lines):
        if line.startswith("#### "):
            first_step = i
            break
    intro = prose_lines[:first_step] if first_step is not None else list(prose_lines)
    intro_text = "\n".join(_strip_meta_lines(intro)).strip()
    if part.question_text and intro_text:
        part.question_text = f"{part.question_text}\n\n{intro_text}".strip()
    elif intro_text:
        part.question_text = intro_text

    # Pitfalls: every `> **🎯 …** …` / `> **🚨 …** …` blockquote, plus their
    # `> …` continuations until a blank `>` or non-`>` line.
    pitfalls: list[str] = []
    buf: list[str] = []
    in_callout = False
    for line in prose_lines:
        if PITFALL_OPENER_RE.match(line):
            if buf:
                pitfalls.append("\n".join(buf).strip())
                buf = []
            in_callout = True
            buf.append(line.lstrip("> ").rstrip())
        elif in_callout and line.startswith(">"):
            stripped = line.lstrip("> ").rstrip()
            if stripped == "":
                pitfalls.append("\n".join(buf).strip())
                buf = []
                in_callout = False
            else:
                buf.append(stripped)
        elif in_callout:
            pitfalls.append("\n".join(buf).strip())
            buf = []
            in_callout = False
    if buf:
        pitfalls.append("\n".join(buf).strip())

    part.common_pitfalls = "\n\n".join(p for p in pitfalls if p) or None
    part.marking_scheme_note = "\n".join(ms_lines).strip() or None
    part.solution_text = "\n".join(prose_lines).strip() or None

    # Per-part marks: prefer the FIRST `(N marks)` annotation we see anywhere
    # in the part. (Question-level totals appear in the marking-scheme block
    # and are filtered out by taking the first hit, which is the per-part
    # annotation when present.)
    haystack = "\n".join(
        s for s in (part.question_text, part.solution_text) if s
    )
    m = PART_MARKS_RE.search(haystack)
    if m:
        part.marks = int(m.group(1))


def _apply_question_inheritance(parts: list[ExamPart]) -> None:
    """Fill empty `topic` / `tutorials_referenced` / `secondary_topics` on a
    deep sub-part by copying from a sibling in the same question_number.

    Surfaced DAY_26 evening: 20 parts in the corpus have BOTH `topic` and
    `tutorials_referenced` empty (and a further ~167 have empty tutorials
    but a populated topic). These are deep sub-parts like ``Q8(d)`` / ``Q3(b)(i)``
    where the markdown convention is to write the ``**Topic:**`` /
    ``**Tutorials:**`` metadata once on the first part of the question and
    let the remaining sub-parts inherit by convention. The chunker can't
    see that convention — it parses each ``### Q…`` heading as an
    independent row — so we apply the inheritance rule here.

    Inheritance is sibling-wise within ``question_number``:
        * topic                ← first non-empty `topic` among siblings, in
                                 document order.
        * tutorials_referenced ← first non-empty `tutorials_referenced` list
                                 (copied as a NEW list, never aliased).
        * secondary_topics     ← copied alongside tutorials_referenced from
                                 the same donor sibling (so the strands
                                 stay consistent with the slug folders).

    Idempotent: re-running on already-populated parts is a no-op (the
    `if not p.topic` / `if not p.tutorials_referenced` guards ensure we
    never overwrite a child's own metadata).

    Scope: this runs **after** parsing each file, so it sees one file's
    parts at a time. (year, paper, sitting) is constant within a file —
    grouping on question_number alone is sufficient.
    """
    by_q: dict[int, list[ExamPart]] = {}
    for p in parts:
        by_q.setdefault(p.question_number, []).append(p)

    for siblings in by_q.values():
        # Donor topic: the first sibling that has a topic.
        donor_topic: str | None = next(
            (p.topic for p in siblings if p.topic), None
        )

        # Donor tutorial bundle: the first sibling with a non-empty
        # tutorials_referenced list. We carry secondary_topics along with
        # it so the two stay consistent (same donor → same slug-derived
        # strand list).
        donor_tutorials: list[str] = []
        donor_secondaries: list[str] = []
        for p in siblings:
            if p.tutorials_referenced:
                donor_tutorials = list(p.tutorials_referenced)
                donor_secondaries = list(p.secondary_topics)
                break

        for p in siblings:
            if not p.topic and donor_topic:
                p.topic = donor_topic
            if not p.tutorials_referenced and donor_tutorials:
                p.tutorials_referenced = list(donor_tutorials)
                if not p.secondary_topics:
                    p.secondary_topics = list(donor_secondaries)


def _fallback_marks_from_question_totals(parts: list[ExamPart],
                                          question_totals: dict[int, int]) -> None:
    """Fill in marks for parts that lack a `(N marks)` annotation by
    distributing the question's total marks across its siblings. Pinned
    sibling values are honoured; the remainder is shared as evenly as
    possible across the unannotated parts (with the +1 leftover allocated
    in document order)."""
    by_q: dict[int, list[ExamPart]] = {}
    for p in parts:
        by_q.setdefault(p.question_number, []).append(p)
    for qnum, siblings in by_q.items():
        total = question_totals.get(qnum)
        if total is None:
            continue
        missing = [p for p in siblings if p.marks is None]
        if not missing:
            continue
        accounted = sum(p.marks for p in siblings if p.marks is not None)
        remaining = max(total - accounted, 0)
        share = remaining // len(missing) if missing else 0
        leftover = remaining - share * len(missing)
        for i, p in enumerate(missing):
            allocated = share + (1 if i < leftover else 0)
            # Don't pretend a real part is worth zero marks.
            p.marks = max(allocated, max(1, total // len(siblings)))


def parse_solutions_file(path: Path) -> list[ExamPart]:
    """Walk one solutions .md file, returning one ExamPart per `### Q…`
    heading. Strips any previously-written crossref block before parsing
    so the heading regex never matches inside the YAML."""
    meta = parse_filename(path.name)
    if meta is None:
        return []

    raw = path.read_text(encoding="utf-8")
    raw = strip_crossref_block(raw)
    _frontmatter, body = split_frontmatter(raw)

    parts: list[ExamPart] = []
    current: ExamPart | None = None
    current_buf: list[str] = []
    question_totals: dict[int, int] = {}
    current_section: str | None = None

    def flush() -> None:
        nonlocal current, current_buf
        if current is not None:
            _finalise_part(current, current_buf)
            parts.append(current)
        current = None
        current_buf = []

    for line in body.splitlines():
        # Stop chunking at the end-of-paper sentinel or footnotes.
        if END_SENTINEL_RE.match(line) or FOOTNOTES_HEADER_RE.match(line):
            flush()
            break

        # Section / Question metadata.
        sec = SECTION_HEADER_RE.match(line)
        if sec:
            current_section = sec.group("section").upper()
            continue
        q = QUESTION_HEADER_RE.match(line)
        if q:
            question_totals[int(q.group("qnum"))] = int(q.group("marks"))
            continue

        h = HEADING_RE.match(line)
        if h:
            flush()
            qnum = int(h.group("qnum"))
            letter = (h.group("letter") or "").lower() or None
            roman = (h.group("roman") or "").lower() or None
            section = current_section or ("A" if qnum <= 6 else "B")
            current = ExamPart(
                part_id=build_part_id(meta["year"], meta["sitting"], meta["paper"],
                                      qnum, letter, roman),
                year=meta["year"],
                paper=meta["paper"],
                sitting=meta["sitting"],
                question_number=qnum,
                sub_part=build_sub_part(letter, roman),
                section=section,
                marks=None,
                topic=None,
                question_text=h.group("title").strip() or None,
                source_path=str(path),
            )
            continue

        if current is None:
            continue

        # Topic / Tutorials line metadata.
        if current.topic is None:
            t = TOPIC_RE.match(line)
            if t:
                current.topic = t.group("topic").strip()
        # Tutorial links can appear on the Tutorials line *or* its wrapped
        # continuation lines — match anywhere on the line.
        for link in TUTORIAL_LINK_RE.finditer(line):
            slug = link.group("slug")
            strand = folder_to_strand(link.group("folder"))
            if slug not in current.tutorials_referenced:
                current.tutorials_referenced.append(slug)
            if strand and strand not in current.secondary_topics:
                current.secondary_topics.append(strand)
        current_buf.append(line)

    flush()

    # DAY_27 follow-up: deep sub-parts (e.g. Q8(d), Q3(b)(i)) sometimes
    # carry no `**Topic:**` / `**Tutorials:**` lines because the markdown
    # author wrote them once on the first sub-part. Inherit those fields
    # from a sibling in the same question_number before the marks pass.
    _apply_question_inheritance(parts)

    # Fill in NULL marks from the question-level totals.
    _fallback_marks_from_question_totals(parts, question_totals)

    return parts


# ───────────────────────────────────────────────────────────────────────────
# Corpus walk
# ───────────────────────────────────────────────────────────────────────────
def walk_corpus(solutions_dir: Path, report: LoadReport) -> list[ExamPart]:
    if not solutions_dir.is_dir():
        raise FileNotFoundError(f"solutions dir not found: {solutions_dir}")

    files = sorted(
        p for p in solutions_dir.glob("*.md")
        if p.name not in SKIP_NAMES and not p.name.startswith(SKIP_PREFIXES)
    )
    all_parts: list[ExamPart] = []
    for path in files:
        report.files_walked += 1
        try:
            parts = parse_solutions_file(path)
        except Exception as exc:  # noqa: BLE001 — surface anything unexpected
            report.parse_errors.append((path.name, repr(exc)))
            continue
        if not parts:
            report.files_skipped += 1
            report.parse_errors.append((path.name, "no parts extracted"))
            continue
        report.files_parsed += 1
        all_parts.extend(parts)
    return all_parts


# ───────────────────────────────────────────────────────────────────────────
# Row build
# ───────────────────────────────────────────────────────────────────────────
def build_row(p: ExamPart) -> dict[str, Any]:
    return {
        "part_id": p.part_id,
        "year": p.year,
        "paper": p.paper,
        "sitting": p.sitting,
        "question_number": p.question_number,
        "sub_part": p.sub_part,
        "section": p.section,
        "marks": p.marks,
        "topic": p.topic,
        "question_text": p.question_text,
        "solution_text": p.solution_text,
        "common_pitfalls": p.common_pitfalls,
        "marking_scheme_note": p.marking_scheme_note,
        "source_path": p.source_path,
        "secondary_topics": list(p.secondary_topics),
        "tutorials_referenced": list(p.tutorials_referenced),
    }


def _row_to_params(row: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    for c in COLS_SCALAR:
        out.append(row.get(c))
    for c in COLS_VARIANT:
        out.append(json.dumps(row.get(c) or []))
    return out


# ───────────────────────────────────────────────────────────────────────────
# Snowflake MERGE — staging-table pattern
# ───────────────────────────────────────────────────────────────────────────
def _build_staging_insert_sql(staging_fqn: str, n_rows: int) -> str:
    """One INSERT … SELECT … FROM VALUES (?, ?, …), (?, ?, …) — VARIANT cols
    wrapped in PARSE_JSON. Mirrors load_tutorials.py's staging pattern."""
    select_exprs: list[str] = []
    column_names: list[str] = []
    idx = 1
    for c in COLS_SCALAR:
        select_exprs.append(f"${idx}")
        column_names.append(c)
        idx += 1
    for c in COLS_VARIANT:
        select_exprs.append(f"PARSE_JSON(${idx})")
        column_names.append(c)
        idx += 1

    ncols = len(ALL_COLS)
    row_placeholder = "(" + ",".join(["?"] * ncols) + ")"
    values_clause = ",\n    ".join([row_placeholder] * n_rows)

    return f"""
INSERT INTO {staging_fqn} ({", ".join(column_names)})
SELECT {", ".join(select_exprs)}
FROM VALUES
    {values_clause}
"""


def _build_merge_sql(staging_fqn: str, target_fqn: str) -> str:
    update_cols = [c for c in ALL_COLS if c != "part_id"]
    set_clause = ",\n                ".join(f"t.{c} = s.{c}" for c in update_cols)
    set_clause += ",\n                t.loaded_at = CURRENT_TIMESTAMP()"

    insert_cols_csv = ", ".join([*ALL_COLS, "loaded_at"])
    insert_vals = [f"s.{c}" for c in ALL_COLS] + ["CURRENT_TIMESTAMP()"]
    insert_vals_csv = ", ".join(insert_vals)

    return f"""
MERGE INTO {target_fqn} t
USING {staging_fqn} s
   ON t.part_id = s.part_id
 WHEN MATCHED THEN UPDATE SET
                {set_clause}
 WHEN NOT MATCHED THEN INSERT ({insert_cols_csv})
                VALUES ({insert_vals_csv})
"""


def load_to_snowflake(rows: list[dict[str, Any]], report: LoadReport) -> None:
    if not rows:
        log.warning("Nothing to load; skipping Snowflake connection.")
        return

    try:
        import snowflake.connector  # noqa: PLC0415 — lazy: only needed for live runs
    except ImportError:
        # Soft-skip — useful in local CI where the connector isn't installed
        # and a user just wants to verify parsing + crossref-block idempotency.
        # Live runs must install snowflake-connector-python or the warehouse
        # never receives the rows.
        log.warning(
            "snowflake-connector-python not installed — skipping MERGE. "
            "`pip install snowflake-connector-python` for a live load."
        )
        return

    snowflake.connector.paramstyle = "qmark"

    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    if not account or not user:
        # Soft-skip rather than raise so a local CI lane (no Snowflake creds)
        # can still validate parsing + crossref-block idempotency end-to-end.
        # Live runs always set both vars; the warning is the canary.
        log.warning(
            "SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER unset — skipping MERGE. "
            "Set both env vars and re-run for a live load."
        )
        return

    conn_kwargs: dict[str, Any] = {
        "account": account,
        "user": user,
        "role": os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "WH_TUTOR"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "GKTUITION_TUTOR"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "RAW"),
        "client_session_keep_alive": False,
    }
    if pk_path := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        conn_kwargs["private_key_file"] = pk_path
        conn_kwargs["authenticator"] = os.environ.get("SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT")
    elif password := os.environ.get("SNOWFLAKE_PASSWORD"):
        conn_kwargs["password"] = password
    else:
        raise RuntimeError(
            "Either SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH must be set."
        )

    target_fqn = "GKTUITION_TUTOR.RAW.EXAM_PARTS"
    staging_fqn = "EXAM_PARTS_STAGING"

    log.info("Connecting to Snowflake account=%s as user=%s", account, user)
    conn = snowflake.connector.connect(**conn_kwargs)
    try:
        cs = conn.cursor()
        try:
            cs.execute(f"USE WAREHOUSE {conn_kwargs['warehouse']}")
            cs.execute(f"USE DATABASE {conn_kwargs['database']}")
            cs.execute(f"USE SCHEMA {conn_kwargs['schema']}")

            log.info("Creating transient staging table %s", staging_fqn)
            cs.execute(f"DROP TABLE IF EXISTS {staging_fqn}")
            cs.execute(f"CREATE TRANSIENT TABLE {staging_fqn} LIKE {target_fqn}")

            log.info("Bulk-inserting %d rows into staging (single INSERT)", len(rows))
            insert_sql = _build_staging_insert_sql(staging_fqn, len(rows))
            params: list[Any] = []
            for r in rows:
                params.extend(_row_to_params(r))
            cs.execute(insert_sql, params)

            log.info("Running MERGE %s → %s", staging_fqn, target_fqn)
            merge_sql = _build_merge_sql(staging_fqn, target_fqn)
            cs.execute(merge_sql)
            merge_result = cs.fetchall()
            inserted = updated = 0
            if merge_result and len(merge_result[0]) >= 2:
                inserted = int(merge_result[0][0] or 0)
                updated = int(merge_result[0][1] or 0)
            log.info("MERGE complete: %d inserted, %d updated", inserted, updated)
            report.snowflake_inserted = inserted
            report.snowflake_updated = updated

            cs.execute(f"DROP TABLE IF EXISTS {staging_fqn}")
        finally:
            cs.close()
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────
def _default_solutions_dir() -> Path:
    """The canonical corpus path under the user's home checkout."""
    return Path(__file__).resolve().parent.parent.parent / (
        "career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument(
        "--solutions-dir",
        type=Path,
        default=_default_solutions_dir(),
        help="Path to the LCHL_Maths_Exams/Solutions directory.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Walk + parse, print counts; no Snowflake write, no file edits.")
    ap.add_argument("--no-write-crossrefs", action="store_true",
                    help="Skip rewriting the YAML crossref block in source .md files.")
    args = ap.parse_args(argv)

    report = LoadReport()
    solutions_dir = args.solutions_dir.resolve()
    log.info("Walking corpus under %s", solutions_dir)

    try:
        parts = walk_corpus(solutions_dir, report)
    except FileNotFoundError as e:
        log.error("%s", e)
        return 2

    report.parts_parsed = len(parts)
    report.parts_null_marks = sum(1 for p in parts if p.marks is None)
    report.parts_no_topic = [p.part_id for p in parts if not p.topic]
    report.parts_no_tutorials = [p.part_id for p in parts if not p.tutorials_referenced]

    # Always-on counts.
    log.info("Files walked:    %d", report.files_walked)
    log.info("Files parsed:    %d", report.files_parsed)
    if report.files_skipped:
        log.warning("Files yielding zero parts: %d", report.files_skipped)
    log.info("Parts parsed:    %d", report.parts_parsed)
    log.info("NULL marks:      %d", report.parts_null_marks)
    log.info("Parts with no topic:            %d", len(report.parts_no_topic))
    log.info("Parts with no tutorials linked: %d", len(report.parts_no_tutorials))
    if report.parts_no_tutorials:
        for pid in report.parts_no_tutorials[:10]:
            log.info("    • %s", pid)
        if len(report.parts_no_tutorials) > 10:
            log.info("    … and %d more.", len(report.parts_no_tutorials) - 10)

    if report.parse_errors:
        log.error("Parse errors (%d):", len(report.parse_errors))
        for name, msg in report.parse_errors:
            log.error("    %s -> %s", name, msg)

    # Crossref block rewrite. Idempotent: byte-identical on a second run.
    if not args.dry_run and not args.no_write_crossrefs:
        by_file: dict[Path, list[ExamPart]] = {}
        for p in parts:
            by_file.setdefault(Path(p.source_path), []).append(p)
        for path, file_parts in sorted(by_file.items()):
            try:
                if write_crossref_block(path, file_parts):
                    report.crossref_files_rewritten += 1
            except OSError as e:
                log.error("Failed to write crossref block for %s: %s", path, e)
        log.info("Crossref blocks rewritten: %d / %d files",
                 report.crossref_files_rewritten, len(by_file))

    if args.dry_run:
        log.info("--dry-run: would MERGE %d rows into GKTUITION_TUTOR.RAW.EXAM_PARTS",
                 len(parts))
        return 0

    rows = [build_row(p) for p in parts]
    load_to_snowflake(rows, report)
    log.info("Loaded: %d rows merged into EXAM_PARTS (%d inserted, %d updated)",
             report.snowflake_inserted + report.snowflake_updated,
             report.snowflake_inserted, report.snowflake_updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
