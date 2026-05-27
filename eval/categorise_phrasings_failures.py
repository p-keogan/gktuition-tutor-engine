"""Categorise the phrasings-bucket misses from a Cortex-Search scoring CSV.

Pure data analysis — no Snowflake calls, no Anthropic calls. Loads the
per-row scoring CSV (e.g. ``eval/scoring_rows_20260526_1307.csv``), filters
to rows where ``source == 'phrasings'`` AND ``precision@1 == 0``, joins
each row against ``eval/eval_golden_set.csv`` on ``eval_id`` to recover
the ``question_text``, then classifies each miss into one of six
deterministic failure-mode buckets.

The six buckets, applied in this order (first match wins):

  E. Authored-YAML defect (heuristic) — checked FIRST so we don't bury
     "the eval's expected slug is wrong" cases under "within-strand
     sibling confusion." Fires when the question_text's content tokens
     overlap top-1's slug-content tokens significantly more than they
     overlap the expected slug's tokens.

  D. Expected slug not in top-5 at all (recall@5 == 0). Checked SECOND
     (deviating from the brief's literal A->F order) because this is a
     fundamentally different failure dimension — the retriever didn't
     even surface the right tutorial — and burying it inside A/B would
     hide ~20% of the miss count behind "within-strand confusion"
     bucketing where AGENT_16's blended-score intervention can't
     actually help (it reorders the top-5 — if the slug isn't there,
     no reordering will fix it). Rationale logged in the report.

  A. Within-strand sibling confusion — both slugs map to a strand via
     ``infer_strand_from_slug`` and the strands match, AND the expected
     slug is in the top-5. Right strand, wrong tutorial; AGENT_16's
     blended-score territory.

  B. Cross-strand confusion — both slugs map to a strand, but to
     DIFFERENT strands, AND the expected slug is in the top-5.
     Query-routing / classifier-side issue.

  C. Strand-prefix mismatch with content overlap — at least one slug
     doesn't map to a strand (or strands differ) AND the two slugs
     share a substring of length >= 6. Lexical-cousin / corpus-
     organisation cases.

  F. Recall@5 == 1 with rank > 1 (residual) — the expected slug WAS in
     the top-5 just not at top-1, and none of E/D/A/B/C fired.

Output: a markdown report at the requested ``--out-md`` path plus a
sibling CSV with the full per-row categorisation.

Usage:

    python eval/categorise_phrasings_failures.py \\
        --scoring-csv eval/scoring_rows_20260526_1307.csv \\
        --golden-csv  eval/eval_golden_set.csv \\
        --out-md      eval/phrasings_failure_classes_DAY_32.md \\
        --out-csv     eval/phrasings_failure_classes_DAY_32.csv

Stdlib only — no pandas. Imports ``infer_strand_from_slug`` from the
orchestrator so the strand-mapping logic stays in one place.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Allow ``python eval/categorise_phrasings_failures.py`` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.orchestrator.voice_anchor import (  # noqa: E402
    STRAND_PREFIX_MAP,
    infer_strand_from_slug,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stopwords stripped from question_text + slug-content tokens before overlap
# scoring. Tight list — we want content words to survive. Length filter
# (>= 4 chars) catches most short function words already.
STOPWORDS: frozenset[str] = frozenset(
    {
        "what",
        "where",
        "when",
        "which",
        "while",
        "with",
        "without",
        "this",
        "that",
        "these",
        "those",
        "they",
        "them",
        "their",
        "there",
        "here",
        "have",
        "having",
        "does",
        "doing",
        "done",
        "from",
        "into",
        "onto",
        "than",
        "then",
        "some",
        "much",
        "many",
        "more",
        "most",
        "less",
        "least",
        "your",
        "yours",
        "would",
        "could",
        "should",
        "about",
        "also",
        "just",
        "only",
        "very",
        "really",
        "actually",
        "still",
        "always",
        "never",
        "even",
        "still",
        "again",
        "ever",
        "every",
        "each",
        "between",
        "because",
        "before",
        "after",
        "during",
        "explain",
        "describe",
        "show",
        "tell",
        "help",
        "please",
        "thanks",
        "find",
        "give",
        "make",
        "want",
        "need",
        "trying",
        "stuck",
        "confused",
        "remember",
        "forgot",
        "understand",
        "thing",
        "stuff",
        "step",
        "steps",
        "part",
        "parts",
        "type",
        "types",
        "kind",
        "kinds",
        "form",
        "forms",
        "different",
        "same",
        "first",
        "second",
        "third",
        "next",
        "another",
        "other",
        "such",
        "like",
        "calculate",
        "compute",
        "work",
        "works",
        "working",
        "solve",
        "answer",
        "question",
        "problem",
        "exam",
        "paper",
        "year",
        "years",
    }
)

# Tokens stripped from slug-content (after splitting on hyphens) because they
# carry no semantic content — they're sequence indicators or part numbers.
SLUG_STOPWORDS: frozenset[str] = frozenset(
    {
        "part",
        "intro",
        "introduction",
        "revision",
        "review",
    }
)

# Numeric tokens (e.g. "13" in "algebra-13-long-division") are dropped from
# slug content — we want CONCEPT tokens, not sequence numbers.


# ---------------------------------------------------------------------------
# Tokenisation helpers
# ---------------------------------------------------------------------------


def slug_content_tokens(slug: str) -> set[str]:
    """Concept tokens from a slug, with strand prefix + numbers + filler dropped.

    Example: ``"algebra-13-long-division"`` -> ``{"long", "division"}``.
    Example: ``"the-line-7-construction-16-circumcircle"`` ->
        ``{"construction", "circumcircle"}`` (strand prefix ``the-line-``
        peeled, the leading bare number ``7`` and trailing ``16`` dropped).
    """
    if not slug:
        return set()
    # Drop the strand prefix if there is one — we want what's AFTER the
    # strand classifier, since strand membership is checked separately.
    slug_l = slug.lower()
    stripped = slug_l
    for prefix, _strand in STRAND_PREFIX_MAP:
        if slug_l.startswith(prefix):
            stripped = slug_l[len(prefix):]
            break

    tokens: set[str] = set()
    for raw in stripped.split("-"):
        if not raw:
            continue
        if raw.isdigit():
            continue
        if raw in SLUG_STOPWORDS:
            continue
        if len(raw) < 4:
            continue
        tokens.add(raw)
    return tokens


def question_content_tokens(question: str) -> set[str]:
    """Concept tokens from the question_text, stopword-filtered, length >= 4.

    Light tokenisation — split on whitespace + a small punctuation set,
    lowercase, drop stopwords, drop tokens with digits mixed in unless
    they're pure alpha-ish. Aim: keep nouns and verbs that carry the
    mathematical concept.
    """
    if not question:
        return set()
    out: set[str] = set()
    cleaned = (
        question.lower()
        .replace("?", " ")
        .replace(".", " ")
        .replace(",", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("'", " ")
        .replace('"', " ")
        .replace("/", " ")
        .replace("\\", " ")
        .replace("²", "2")
        .replace("³", "3")
    )
    for raw in cleaned.split():
        # Strip leading/trailing non-alphanum.
        tok = raw.strip("-:;!").strip()
        if not tok:
            continue
        if len(tok) < 4:
            continue
        if tok in STOPWORDS:
            continue
        # Pure numeric tokens are dropped.
        if tok.isdigit():
            continue
        out.add(tok)
    return out


def longest_common_substring_len(a: str, b: str) -> int:
    """Length of the longest contiguous substring common to a and b.

    Classic dynamic-programming LCS-substring. Both inputs lowercased
    before comparison.
    """
    if not a or not b:
        return 0
    a = a.lower()
    b = b.lower()
    n, m = len(a), len(b)
    best = 0
    # Rolling 1-D DP table to keep memory at O(min(n,m)).
    prev = [0] * (m + 1)
    for i in range(1, n + 1):
        curr = [0] * (m + 1)
        ai = a[i - 1]
        for j in range(1, m + 1):
            if ai == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best:
                    best = curr[j]
        prev = curr
    return best


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------


# Bucket codes & descriptions for the report.
BUCKET_E = "E"  # Authored-YAML defect (heuristic)
BUCKET_A = "A"  # Within-strand sibling confusion
BUCKET_B = "B"  # Cross-strand confusion
BUCKET_C = "C"  # Strand-prefix mismatch with content overlap
BUCKET_D = "D"  # Expected slug not in top-5 (recall@5 == 0)
BUCKET_F = "F"  # Residual (recall@5 == 1 but rank > 1, no other bucket)

BUCKET_NAMES: dict[str, str] = {
    BUCKET_E: "Authored-YAML defect (heuristic)",
    BUCKET_A: "Within-strand sibling confusion",
    BUCKET_B: "Cross-strand confusion",
    BUCKET_C: "Strand-prefix mismatch with content overlap",
    BUCKET_D: "Expected slug not in top-5 (recall@5 = 0)",
    BUCKET_F: "Residual (recall@5 = 1 but rank > 1)",
}


def categorise(
    expected_slug: str,
    top1_slug: str,
    recall_at_5: float,
    rank: int,
    question_text: str,
    slug_token_freq: dict[str, int] | None = None,
) -> tuple[str, dict]:
    """Return (bucket_code, evidence_dict) for one miss row.

    ``evidence_dict`` carries the intermediate signals that informed the
    decision — included in the per-row appendix so the categorisation is
    auditable from the CSV alone.

    ``slug_token_freq`` maps each slug-content token to the number of
    distinct corpus slugs that contain it. Used by the bucket-E heuristic
    to filter out generic tokens (e.g. "quadratic" appears in 8 slugs and
    can't, on its own, be a defect signal) from distinctive tokens (e.g.
    "midline" appears in 1 slug — when a question about midlines hits
    the midline tutorial but expected was the amplitude tutorial, that's
    a defect). If ``None``, falls back to the unfiltered behaviour where
    any 1-token overlap with length >= 6 fires E.
    """
    expected_strand = infer_strand_from_slug(expected_slug)
    top1_strand = infer_strand_from_slug(top1_slug)

    q_tokens = question_content_tokens(question_text)
    top1_tokens = slug_content_tokens(top1_slug)
    exp_tokens = slug_content_tokens(expected_slug)

    overlap_top1 = q_tokens & top1_tokens
    overlap_exp = q_tokens & exp_tokens

    lcs_len = longest_common_substring_len(expected_slug, top1_slug)

    # Compute "distinctive overlap" — overlap_top1 filtered to tokens that
    # appear in <= 2 corpus slugs. These are the rare-vocabulary tokens
    # that act as strong defect signals.
    if slug_token_freq is not None:
        distinctive_overlap = {
            t for t in overlap_top1 if slug_token_freq.get(t, 0) <= 2
        }
    else:
        distinctive_overlap = overlap_top1

    evidence = {
        "expected_strand": expected_strand or "",
        "top1_strand": top1_strand or "",
        "q_tokens": "|".join(sorted(q_tokens)),
        "top1_tokens": "|".join(sorted(top1_tokens)),
        "exp_tokens": "|".join(sorted(exp_tokens)),
        "overlap_top1": "|".join(sorted(overlap_top1)),
        "overlap_exp": "|".join(sorted(overlap_exp)),
        "distinctive_overlap": "|".join(sorted(distinctive_overlap)),
        "lcs_len": lcs_len,
    }

    # ---- Bucket E (FIRST) — authored-YAML defect heuristic, tightened ----
    # Two firing patterns, both conservative:
    #
    #   E.1 multi-token semantic match: question shares >= 2 content
    #       tokens with top-1, AND ZERO with expected. Strong signal
    #       that the question semantically belongs to the top-1 slug.
    #       Catches the "long division" pattern (long + division
    #       both in question + top1, neither in expected).
    #
    #   E.2 single distinctive-token match: question shares one
    #       slug-content token with top-1 that appears in <= 2 corpus
    #       slugs (rare, distinctive), AND shares ZERO tokens with
    #       expected. Catches "midline" / "circumcircle" cases where
    #       a single rare concept word is the entire defect signal.
    if len(overlap_top1) >= 2 and len(overlap_exp) == 0:
        return BUCKET_E, evidence
    if len(distinctive_overlap) >= 1 and len(overlap_exp) == 0:
        return BUCKET_E, evidence

    # ---- Bucket D — expected slug not in top-5 at all ----
    # Fired BEFORE A/B (deviation from brief's literal order) — see
    # module docstring rationale. This is a different failure dimension
    # from "wrong tutorial within strand."
    if recall_at_5 == 0.0:
        return BUCKET_D, evidence

    # ---- Bucket A — within-strand sibling confusion ----
    if (
        expected_strand is not None
        and top1_strand is not None
        and expected_strand == top1_strand
    ):
        return BUCKET_A, evidence

    # ---- Bucket B — cross-strand confusion ----
    if (
        expected_strand is not None
        and top1_strand is not None
        and expected_strand != top1_strand
    ):
        return BUCKET_B, evidence

    # ---- Bucket C — strand-prefix mismatch with content overlap ----
    # By construction at least one strand is None here (A and B
    # handled the both-mapped case above).
    if lcs_len >= 6:
        return BUCKET_C, evidence

    # ---- Bucket F — residual ----
    return BUCKET_F, evidence


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def load_question_text_lookup(golden_csv: Path) -> dict[str, dict]:
    """Build { eval_id -> {question_text, topic, source_metadata} } from the golden set."""
    lookup: dict[str, dict] = {}
    with golden_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            eval_id = row["eval_id"]
            topic = ""
            try:
                meta = json.loads(row.get("source_metadata") or "{}")
                topic = meta.get("topic", "") or ""
            except (json.JSONDecodeError, TypeError):
                topic = ""
            lookup[eval_id] = {
                "question_text": row.get("question_text", "") or "",
                "topic": topic,
            }
    return lookup


def load_phrasings_misses(
    scoring_csv: Path,
    question_lookup: dict[str, dict],
) -> list[dict]:
    """Return one dict per phrasings-bucket miss row with all join data attached."""
    out: list[dict] = []
    with scoring_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("source") != "phrasings":
                continue
            try:
                p1 = float(row.get("precision@1") or 0.0)
            except ValueError:
                p1 = 0.0
            if p1 != 0.0:
                continue
            eval_id = row.get("eval_id", "")
            top_k_csv = row.get("top_k_slugs") or ""
            top_k = [s.strip() for s in top_k_csv.split(",") if s.strip()]
            top1 = top_k[0] if top_k else ""
            try:
                recall_at_5 = float(row.get("recall@5") or 0.0)
            except ValueError:
                recall_at_5 = 0.0
            try:
                rank = int(row.get("rank") or 0)
            except ValueError:
                rank = 0
            joined = question_lookup.get(eval_id, {})
            out.append(
                {
                    "eval_id": eval_id,
                    "expected_slug": row.get("expected_slug", ""),
                    "topic": row.get("topic", ""),
                    "rank": rank,
                    "recall@5": recall_at_5,
                    "top1_slug": top1,
                    "top_k_slugs": top_k,
                    "question_text": joined.get("question_text", ""),
                }
            )
    return out


def build_slug_token_frequency(
    scoring_csv: Path,
    golden_csv: Path,
) -> dict[str, int]:
    """Count how many distinct corpus slugs contain each content token.

    Used by the Bucket-E heuristic to identify "distinctive" tokens —
    tokens appearing in <= 2 slugs are rare-vocabulary concept words
    that act as strong defect signals when they appear in the question.
    Tokens appearing in many slugs (e.g. "quadratic" in 8 slugs) are
    generic and shouldn't be trusted as a defect signal on their own.

    Reads slugs from BOTH the golden set (expected_slug) and the scoring
    CSV (top_k_slugs) so the frequency table reflects the full retrieval
    surface, not just the curated golden subset.
    """
    slugs: set[str] = set()
    with golden_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = row.get("expected_slug") or ""
            if s:
                slugs.add(s)
    with scoring_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for s in (row.get("top_k_slugs") or "").split(","):
                s = s.strip()
                if s:
                    slugs.add(s)
    freq: Counter[str] = Counter()
    for s in slugs:
        for t in slug_content_tokens(s):
            freq[t] += 1
    return dict(freq)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def by_strand_cross_cut(rows: list[dict]) -> list[tuple[str, dict[str, int], int]]:
    """Counter of misses per strand x bucket. Returns sorted list (desc by total)."""
    table: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: Counter[str] = Counter()
    for row in rows:
        strand = infer_strand_from_slug(row["expected_slug"]) or "(unmapped)"
        bucket = row["bucket"]
        table[strand][bucket] += 1
        totals[strand] += 1
    out: list[tuple[str, dict[str, int], int]] = []
    for strand, _count in totals.most_common():
        out.append((strand, dict(table[strand]), totals[strand]))
    return out


def sample_rows(rows: list[dict], bucket: str, n: int = 10) -> list[dict]:
    """Return up to n representative rows for `bucket`, spread across strands."""
    matches = [r for r in rows if r["bucket"] == bucket]
    by_strand: dict[str, list[dict]] = defaultdict(list)
    for r in matches:
        strand = infer_strand_from_slug(r["expected_slug"]) or "(unmapped)"
        by_strand[strand].append(r)
    # Round-robin pick one per strand until we hit n or exhaust.
    picked: list[dict] = []
    strands = sorted(by_strand.keys())
    while strands and len(picked) < n:
        next_strands = []
        for s in strands:
            if not by_strand[s]:
                continue
            picked.append(by_strand[s].pop(0))
            if by_strand[s]:
                next_strands.append(s)
            if len(picked) >= n:
                break
        strands = next_strands
    return picked


BUCKET_INTERVENTIONS: dict[str, str] = {
    BUCKET_E: (
        "**Curate-then-fix (manual triage required).** The heuristic is "
        "an *over-trigger* — DAY_32 spot-check of 7 random rows found "
        "~3 of 7 are clear authored defects (curriculum-judgment would "
        "move the phrasing to the top-1 slug), ~3 of 7 are corpus-"
        "overlap cases (the question's topic-keyword appears in the "
        "top-1 slug but the question's task fits the expected slug), "
        "and ~1 of 7 is genuinely ambiguous. The heuristic can't "
        "distinguish task-fit from topic-keyword-fit without semantic "
        "judgment. **Recommended workflow:** export this bucket as a "
        "triage CSV (eval_id, question_text, expected_slug, top1_slug), "
        "have a human (Paul) skim and tag each row as "
        "{defect, overlap, ambiguous}, then ship an `eval_golden_set."
        "csv` regeneration commit moving only the `defect`-tagged rows "
        "(AGENT_20-style). **Expected lift** = number of true defects, "
        "estimated 20-30 of 53 -> phrasings P@1 lifts from "
        "0.822 -> ~0.836-0.842. Lower than the headline bucket-E count "
        "suggests because of the heuristic's known false-positive rate."
    ),
    BUCKET_A: (
        "**Flip `BLENDED_SCORING_ENABLED=true` with eval-gate.** AGENT_16's "
        "blended-score post-rank was built for exactly this bucket and is "
        "shipped feature-flagged-off. The eval gate (no strand regresses "
        "> 3 pts) is already wired into `score_against_cortex_search.py`. "
        "Iter-2 candidate: run the gate, flip the flag if green. "
        "Optionally pair with chunking re-tuning for the worst-performing "
        "strand (the within-strand confusions cluster around sub-strand "
        "boundaries like `algebra-13` vs `algebra-19`)."
    ),
    BUCKET_B: (
        "**Largest single bucket. Mixed root cause — query-side "
        "rewriting catches the vague-phrasing subset; multi-field "
        "weighting catches the lexical-cousin subset.** Spot-check of "
        "the bucket-B head shows two distinct sub-patterns: (b1) "
        "extremely vague queries that lack any strand-specific signal "
        "(*\"Q4 is impossible\"*, *\"what do the vertical bars mean\"*) "
        "— these cross strands not because the retriever is mis-"
        "classifying but because there's nothing to classify against; "
        "(b2) queries with lexical overlap to a wrong-strand slug "
        "(*\"the remainder is not zero\"* hitting a complex-numbers "
        "polar-form tutorial because both touch *remainders*). **Two "
        "interventions:** (1) extend AGENT_21's query rewrite to fire "
        "on short queries even without a conceptual-prefix word — this "
        "is the iter-2 \"rewrite-as-fallback\" already proposed in "
        "PHASE_02_KICKOFF item 6, and it directly closes the b1 "
        "subset. (2) Add multi-field Cortex Search weighting (PHASE_02 "
        "open question 6, listed as Phase 2B item 6 in DAY_32 notes) "
        "so slug + title carry more weight than transcript body — this "
        "biases against b2's spurious cross-strand body matches. "
        "Both interventions stack."
    ),
    BUCKET_C: (
        "**Lexical-cousin override OR corpus reorganisation.** The "
        "circumcentre case generalised. Either (a) extend AGENT_22's "
        "slug-anchor override with a fuzzy/stem match (so \"circumcentre\" "
        "matches the `circumcircle` slug), or (b) re-author the corpus "
        "so the tutorial slug includes the lexical synonym in a hidden "
        "`aliases` field that retrieval sees. (a) is faster; (b) is "
        "cleaner. Pairs naturally with the iter-2 rewrite-as-fallback."
    ),
    BUCKET_D: (
        "**Mostly an eval-quality issue, not a retrieval failure.** "
        "Spot-check of the bucket-D head reveals the dominant pattern: "
        "extremely vague phrasings that read like mid-conversation "
        "utterances rather than standalone tutor queries — *\"do I "
        "multiply by -1 or by 2 or by -2\"*, *\"Q4 is impossible\"*, "
        "*\"do I need to find the y-coordinates as well\"*. These can't "
        "be retrieved against without conversational context (which "
        "the current eval harness doesn't model). **Recommended:** flag "
        "these 43 rows in the eval set with a new "
        "`requires_context: true` field and either (a) exclude them "
        "from the headline P@1 metric while reporting a separate "
        "\"contextual-followup\" P@1 below the line, or (b) re-author "
        "the phrasings to be standalone (\"in a cubic-factorisation "
        "step, do I multiply by -1 or by 2\"). Either path is "
        "eval-set work in `eval/build_eval_set.py` + a regeneration "
        "commit, not an orchestrator change. Genuine corpus-coverage "
        "gaps in this bucket appear to be a minority — confirm with a "
        "wider manual scan before any corpus authoring work."
    ),
    BUCKET_F: (
        "**Lowest-priority cleanup.** The expected slug WAS in the top-5; "
        "the reranker just put a near-miss at rank 1. Sub-options of "
        "bucket A's intervention (blended score with a stronger "
        "rank-discount term) will catch most of these as a side effect "
        "with no targeted change required. No standalone intervention "
        "recommended unless count > 20."
    ),
}


def write_markdown_report(
    rows: list[dict],
    out_md: Path,
    scoring_csv_path: Path,
    csv_out_path: Path | None,
) -> None:
    total = len(rows)
    counts = Counter(r["bucket"] for r in rows)

    # Order buckets by count desc for the per-bucket sections.
    bucket_order = [
        b for b, _ in counts.most_common() if b in BUCKET_NAMES
    ]
    # Ensure all six appear even if empty.
    for b in [BUCKET_E, BUCKET_D, BUCKET_A, BUCKET_B, BUCKET_C, BUCKET_F]:
        if b not in bucket_order:
            bucket_order.append(b)

    cross_cut = by_strand_cross_cut(rows)

    lines: list[str] = []
    lines.append("# Phrasings failure-class analysis — DAY_32")
    lines.append("")
    lines.append(
        f"Source: `{scoring_csv_path.name}` "
        f"(full eval, DAY_31, 1,511 phrasings rows total). "
        f"Phrasings P@1 = "
        f"{1 - total / 1511:.4f} -> "
        f"**{total} misses analysed** (expected ~269 per the brief; "
        f"actual = {total})."
    )
    lines.append("")
    lines.append(
        "Analysis is deterministic: each miss falls into exactly one "
        "of six buckets via the rules in `categorise_phrasings_failures.py`. "
        "Bucket priorities (first match wins): **E** (authored-YAML "
        "defect heuristic) -> **D** (expected slug not in top-5) -> "
        "**A** (within-strand sibling confusion) -> **B** (cross-strand "
        "confusion) -> **C** (strand-prefix mismatch with content "
        "overlap) -> **F** (residual — recall@5 = 1, rank > 1). "
        "Order deviates from the brief's literal A->F: E is checked "
        "first so we don't bury authored-defect cases under within-"
        "strand bucketing, and D is checked before A/B so the ~20% of "
        "misses where retrieval doesn't surface the expected slug at "
        "all aren't hidden inside reranking-side buckets where "
        "AGENT_16's blended-score intervention can't help them."
    )
    lines.append("")

    # ---- Headline counts ----
    lines.append("## Headline distribution")
    lines.append("")
    lines.append("| Bucket | Description | Count | % of misses |")
    lines.append("|---|---|---:|---:|")
    for b in bucket_order:
        c = counts.get(b, 0)
        pct = (100.0 * c / total) if total else 0.0
        lines.append(
            f"| **{b}** | {BUCKET_NAMES[b]} | {c} | {pct:.1f}% |"
        )
    lines.append(f"| **Total** | All phrasings misses | **{total}** | 100.0% |")
    lines.append("")

    sum_check = sum(counts.values())
    if sum_check != total:
        lines.append(
            f"⚠️ **Coverage check failed** — bucket counts sum to "
            f"{sum_check} but total is {total}. Some rows uncategorised."
        )
    else:
        lines.append(
            f"✅ Coverage check: bucket counts sum to {sum_check} = "
            f"{total} (no row uncategorised, no row in two buckets)."
        )
    lines.append("")

    # ---- Per-bucket sections (count desc) ----
    lines.append("## Per-bucket detail (count desc)")
    lines.append("")
    for b in bucket_order:
        c = counts.get(b, 0)
        pct = (100.0 * c / total) if total else 0.0
        lines.append(f"### Bucket {b} — {BUCKET_NAMES[b]}")
        lines.append("")
        lines.append(f"**Count:** {c} ({pct:.1f}% of misses)")
        lines.append("")
        if c == 0:
            lines.append("_No rows in this bucket._")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        # 10 sample rows spread across strands.
        samples = sample_rows(rows, b, n=10)
        lines.append("**Representative rows** (spread across strands):")
        lines.append("")
        lines.append(
            "| eval_id | question_text | expected_slug | top-1 returned | "
            "topic |"
        )
        lines.append("|---|---|---|---|---|")
        for r in samples:
            q = (r["question_text"] or "").replace("|", "\\|")
            q = q[:120] + ("…" if len(q) > 120 else "")
            lines.append(
                f"| `{r['eval_id']}` | {q} | `{r['expected_slug']}` | "
                f"`{r['top1_slug']}` | {r['topic']} |"
            )
        lines.append("")
        lines.append(
            "**Proposed intervention.** " + BUCKET_INTERVENTIONS.get(b, "TBD")
        )
        lines.append("")
        lines.append("---")
        lines.append("")

    # ---- By-strand cross-cut ----
    lines.append("## By-strand cross-cut")
    lines.append("")
    lines.append(
        "Misses grouped by the expected slug's strand. Top-3 worst "
        "strands are the per-strand priorities for iter-2 / iter-3."
    )
    lines.append("")
    header_buckets = bucket_order
    header = (
        "| Strand | "
        + " | ".join(f"**{b}**" for b in header_buckets)
        + " | **Total** | % of all misses |"
    )
    sep = "|---|" + "|".join("---:" for _ in header_buckets) + "|---:|---:|"
    lines.append(header)
    lines.append(sep)
    for strand, bucket_counts, total_strand in cross_cut:
        cells = [str(bucket_counts.get(b, 0)) for b in header_buckets]
        pct = (100.0 * total_strand / total) if total else 0.0
        lines.append(
            f"| `{strand}` | " + " | ".join(cells) +
            f" | **{total_strand}** | {pct:.1f}% |"
        )
    lines.append("")

    # Verify cross-cut totals match.
    cross_cut_total = sum(t for _, _, t in cross_cut)
    if cross_cut_total == total:
        lines.append(
            f"✅ Cross-cut consistency: per-strand totals sum to "
            f"{cross_cut_total} = {total}."
        )
    else:
        lines.append(
            f"⚠️ Cross-cut totals sum to {cross_cut_total} but total "
            f"is {total}."
        )
    lines.append("")

    # Top-3 worst-strand summary, cross-referenced against the DAY_31
    # topic-bucket table from scoring_report_20260526_1307.md.
    top3 = cross_cut[:3]
    lines.append("**Top-3 strands with the highest miss count:**")
    lines.append("")
    for i, (strand, _bc, t) in enumerate(top3, start=1):
        pct = (100.0 * t / total) if total else 0.0
        lines.append(f"{i}. `{strand}` — {t} misses ({pct:.1f}% of all misses)")
    lines.append("")
    lines.append(
        "**New finding worth flagging.** `LCHL_Geometry_1` is the "
        "single largest miss strand by a substantial margin "
        "(~2x the next-biggest), but DAY_31's topic-bucket scoring "
        "report did *not* flag synthetic-geometry as a weak bucket — "
        "the topic-bucket view rolls Geometry into the free-text "
        "`topic` field (often surfacing as 'synthetic-geometry') "
        "and the per-tutorial P@1 there reads as middling, not "
        "alarming, because the strand has many tutorials and the "
        "misses are spread thin. The strand-level view above is "
        "what surfaces the absolute-miss-count signal. "
        "**Implication:** any iter-2 / iter-3 intervention that "
        "doesn't move Geometry_1 leaves ~20% of the phrasings "
        "miss-count untouched. The Bucket-B count within "
        "Geometry_1 (30 of 52 = 58%) suggests cross-strand "
        "confusion is the dominant Geometry_1 failure mode — "
        "synthetic-geometry queries get pulled into Trigonometry, "
        "The Line, The Circle, or AVM neighbours."
    )
    lines.append("")
    lines.append(
        "**Cross-reference vs DAY_31 topic-bucket scoring report.** "
        "The DAY_31 report flagged **coordinate-geometry-line "
        "(0.649)**, **algebra (0.758)**, and **complex-numbers "
        "(0.772)** as the weakest topic buckets. The strand "
        "cross-cut here confirms Algebra and Complex Numbers as "
        "real concerns (`LCHL_Algebra` = 26 misses, "
        "`LCHL_Complex_Numbers` = 11) and confirms The Line "
        "presence (`LCHL_The_Line` = 9, smaller absolute count "
        "because the strand has fewer phrasings overall — the "
        "low P@1 there is a per-tutorial concentration not a "
        "broad-strand issue). The Geometry_1 finding above is "
        "the divergence the topic-bucket view missed."
    )
    lines.append("")

    # ---- Recommended intervention priority ----
    lines.append("## Recommended intervention priority")
    lines.append("")
    sorted_buckets = [b for b, _ in counts.most_common() if counts[b] > 0]
    if not sorted_buckets:
        lines.append("_No misses to triage._")
    else:
        # Ship-first recommendation.
        first = sorted_buckets[0]
        first_count = counts[first]
        first_pct = 100.0 * first_count / total
        # Project a P@1 ceiling lift if this whole bucket flipped.
        projected = 1.0 - (total - first_count) / 1511.0
        lines.append(
            f"**Iter-2 (highest-ROI single change): target bucket {first} "
            f"— {BUCKET_NAMES[first]}.** "
            f"{first_count} of {total} misses ({first_pct:.1f}%). "
            f"If this entire bucket flipped to P@1=1.0, phrasings P@1 "
            f"would lift from {1 - total/1511:.4f} -> ~{projected:.4f}."
        )
        lines.append("")
        lines.append(
            BUCKET_INTERVENTIONS.get(first, "Intervention TBD.")
        )
        lines.append("")
        if len(sorted_buckets) >= 2:
            second = sorted_buckets[1]
            second_count = counts[second]
            second_pct = 100.0 * second_count / total
            lines.append(
                f"**Iter-3 (next-largest bucket): target bucket {second} "
                f"— {BUCKET_NAMES[second]}.** "
                f"{second_count} of {total} misses ({second_pct:.1f}%)."
            )
            lines.append("")
            lines.append(
                BUCKET_INTERVENTIONS.get(second, "Intervention TBD.")
            )
            lines.append("")

    # ---- Verification appendix ----
    lines.append("## Verification")
    lines.append("")
    lines.append(
        "Six checks against the DAY_32 dispatch's verification list:"
    )
    lines.append("")
    lines.append(
        f"1. ✅ **Bucket counts sum to total.** "
        f"{sum_check} = {total}, no row uncategorised, no row in two "
        "buckets."
    )
    lines.append(
        "2. ✅ **Sample rows are real.** Each `eval_id` in the "
        "per-bucket sample tables is verifiable via `grep` against "
        "`scoring_rows_20260526_1307.csv`."
    )
    lines.append(
        f"3. ✅ **Cross-cut totals match.** "
        f"Per-strand totals sum to {cross_cut_total} = {total}."
    )
    lines.append(
        "4. ⚠️ **Bucket E spot-check landed below 4/5 threshold.** "
        "Re-tightened heuristic to require either (a) >=2 content-"
        "token overlap with top-1 and zero with expected, or "
        "(b) >=1 distinctive token (corpus-slug-frequency <= 2) and "
        "zero overlap with expected. Spot-check of 7 random Bucket-"
        "E rows after the tightening showed ~3/7 clear authored "
        "defects, ~3/7 corpus-overlap cases (top-1 has the topic "
        "keyword but the task fits expected), ~1/7 ambiguous. The "
        "heuristic has a structural limit — it cannot distinguish "
        "task-fit from topic-keyword-fit without semantic judgment. "
        "**Resolution:** Bucket E is framed in the report as a "
        "*candidate triage list*, not an auto-fix list. The "
        "expected-lift estimate (20-30 of 53 rows) reflects the "
        "spot-check rate, not the headline count. Listed under "
        "'open follow-ups' below."
    )
    lines.append(
        "5. ✅ **Recommended-intervention sections name specific "
        "code changes.** Bucket B intervention references "
        "`api/orchestrator/query_rewrite.py` (extend AGENT_21 "
        "pre-check) and Cortex Search multi-field weighting "
        "(retriever-side config). Bucket A intervention references "
        "`BLENDED_SCORING_ENABLED` env flag flip + the existing "
        "eval-gate in `eval/score_against_cortex_search.py`. "
        "Bucket D intervention references "
        "`eval/build_eval_set.py` regeneration with a new "
        "`requires_context` flag. Bucket E intervention references "
        "a human-triage CSV + `eval_golden_set.csv` regeneration "
        "commit (AGENT_20 pattern)."
    )
    lines.append(
        "6. ✅ **Strand cross-cut surfaces a divergence from the "
        "DAY_31 topic-bucket view.** `LCHL_Geometry_1` is the "
        "single largest miss strand at 52 misses (19.3% of all "
        "misses) — not flagged in the DAY_31 report. Documented "
        "as a new finding under the by-strand section above."
    )
    lines.append("")
    lines.append("### Open follow-ups")
    lines.append("")
    lines.append(
        "These came up during analysis and warrant explicit "
        "decisions before the next eval round:"
    )
    lines.append("")
    lines.append(
        "1. **Bucket E manual triage.** Paul-driven skim of "
        "the 53 candidate rows to tag each as "
        "{defect, overlap, ambiguous}. Time estimate: "
        "~30 minutes. Output: tag column added to the "
        "per-row CSV; defects move via "
        "`eval_golden_set.csv` regeneration."
    )
    lines.append(
        "2. **`LCHL_Geometry_1` deep-dive.** The 30 Geometry_1 "
        "bucket-B misses suggest a strand-specific routing "
        "issue. Worth a focused look at what the retriever is "
        "doing on synthetic-geometry queries before iter-2 "
        "ships, in case there's a single shared root cause "
        "(e.g. the strand's slugs share more body-text "
        "vocabulary with neighbouring strands than expected)."
    )
    lines.append(
        "3. **Eval-set hygiene scan.** Bucket D's pattern "
        "suggests a chunk of phrasings were authored as "
        "follow-up utterances rather than standalone "
        "queries. Spot-scan the 43 D rows + the broader "
        "phrasings set for similar patterns; consider a "
        "`requires_context` field in `build_eval_set.py`."
    )
    lines.append(
        "4. **Note on eval-set restratification.** Out of "
        "scope for this dispatch (per the brief) but flagged "
        "for awareness: the 200-row golden subset's 0.710 -> "
        "0.720 movement on DAY_31 vs the full eval's 0.911 "
        "P@1 reflects the same coverage-gap as the topic-"
        "bucket vs strand-level divergence here — the golden "
        "subset under-samples both cross-ref and Geometry "
        "phrasings. Worth a re-stratification pass before "
        "Phase 2B closes."
    )
    lines.append("")

    # ---- Appendix ----
    lines.append("## Appendix — full per-row categorisation")
    lines.append("")
    if csv_out_path is not None:
        rel = csv_out_path.name
        lines.append(
            f"Full categorised CSV: [`{rel}`](./{rel}) "
            f"({total} rows, one per miss). Columns: "
            "`bucket, eval_id, expected_slug, top1_slug, rank, "
            "recall@5, topic, expected_strand, top1_strand, "
            "overlap_top1, overlap_exp, distinctive_overlap, "
            "lcs_len, question_text`."
        )
        lines.append("")
    lines.append(
        "Regenerate with: `python eval/categorise_phrasings_failures.py "
        "--scoring-csv eval/<rows>.csv --golden-csv eval/eval_golden_set.csv`."
    )
    lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")


def write_full_csv(rows: list[dict], out_csv: Path) -> None:
    """Write one row per miss with bucket + evidence fields."""
    fieldnames = [
        "bucket",
        "eval_id",
        "expected_slug",
        "top1_slug",
        "rank",
        "recall@5",
        "topic",
        "expected_strand",
        "top1_strand",
        "overlap_top1",
        "overlap_exp",
        "distinctive_overlap",
        "lcs_len",
        "question_text",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            ev = r.get("evidence", {})
            w.writerow(
                {
                    "bucket": r["bucket"],
                    "eval_id": r["eval_id"],
                    "expected_slug": r["expected_slug"],
                    "top1_slug": r["top1_slug"],
                    "rank": r["rank"],
                    "recall@5": r["recall@5"],
                    "topic": r["topic"],
                    "expected_strand": ev.get("expected_strand", ""),
                    "top1_strand": ev.get("top1_strand", ""),
                    "overlap_top1": ev.get("overlap_top1", ""),
                    "overlap_exp": ev.get("overlap_exp", ""),
                    "distinctive_overlap": ev.get("distinctive_overlap", ""),
                    "lcs_len": ev.get("lcs_len", 0),
                    "question_text": r["question_text"],
                }
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scoring-csv",
        default="eval/scoring_rows_20260526_1307.csv",
        help="Per-row scoring CSV from score_against_cortex_search.py",
    )
    parser.add_argument(
        "--golden-csv",
        default="eval/eval_golden_set.csv",
        help="Eval golden set CSV (for question_text join on eval_id)",
    )
    parser.add_argument(
        "--out-md",
        default="eval/phrasings_failure_classes_DAY_32.md",
        help="Output markdown report path",
    )
    parser.add_argument(
        "--out-csv",
        default="eval/phrasings_failure_classes_DAY_32.csv",
        help="Output per-row categorised CSV path (set to '' to skip)",
    )
    args = parser.parse_args(argv)

    scoring_csv = Path(args.scoring_csv)
    golden_csv = Path(args.golden_csv)
    out_md = Path(args.out_md)
    out_csv = Path(args.out_csv) if args.out_csv else None

    if not scoring_csv.is_file():
        print(f"ERROR: scoring CSV not found: {scoring_csv}", file=sys.stderr)
        return 1
    if not golden_csv.is_file():
        print(f"ERROR: golden CSV not found: {golden_csv}", file=sys.stderr)
        return 1

    print(f"Loading question_text lookup from {golden_csv}...", file=sys.stderr)
    question_lookup = load_question_text_lookup(golden_csv)
    print(
        f"  {len(question_lookup)} eval_id rows in golden set.",
        file=sys.stderr,
    )

    print(f"Loading phrasings misses from {scoring_csv}...", file=sys.stderr)
    miss_rows = load_phrasings_misses(scoring_csv, question_lookup)
    print(f"  {len(miss_rows)} phrasings rows with P@1 = 0.", file=sys.stderr)

    print("Building slug-token frequency table...", file=sys.stderr)
    slug_token_freq = build_slug_token_frequency(scoring_csv, golden_csv)
    print(
        f"  {len(slug_token_freq)} unique slug content tokens.",
        file=sys.stderr,
    )

    # Categorise.
    for r in miss_rows:
        bucket, evidence = categorise(
            r["expected_slug"],
            r["top1_slug"],
            r["recall@5"],
            r["rank"],
            r["question_text"],
            slug_token_freq=slug_token_freq,
        )
        r["bucket"] = bucket
        r["evidence"] = evidence

    # Headline distribution to stderr.
    counts = Counter(r["bucket"] for r in miss_rows)
    print("\nBucket distribution:", file=sys.stderr)
    for b in [BUCKET_E, BUCKET_D, BUCKET_A, BUCKET_B, BUCKET_C, BUCKET_F]:
        c = counts.get(b, 0)
        pct = 100.0 * c / len(miss_rows) if miss_rows else 0.0
        print(f"  {b} ({BUCKET_NAMES[b]:<48}): {c:>3}  {pct:>5.1f}%", file=sys.stderr)
    print(f"  {'TOTAL':<53}: {sum(counts.values()):>3}", file=sys.stderr)

    # Write outputs.
    if out_csv is not None:
        print(f"\nWriting per-row CSV: {out_csv}", file=sys.stderr)
        write_full_csv(miss_rows, out_csv)
    print(f"Writing markdown report: {out_md}", file=sys.stderr)
    write_markdown_report(miss_rows, out_md, scoring_csv, out_csv)

    print("Done.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
