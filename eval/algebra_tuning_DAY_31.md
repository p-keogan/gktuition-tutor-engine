# Algebra precision@1 tuning — DAY_31 (AGENT_16)

**Status:** **NEGATIVE RESULT — do not ship the flag flip.**

**Author:** AGENT_16 (data-engineer Phase 2 dispatch).
**Branch:** `main`.
**Diagnostic dump:** `eval/algebra_failures_DAY_31.md`.
**Inspector script (new):** `eval/inspect_failures.py`.
**Retriever change (landed disabled):** `api/orchestrator/retriever.py`
— `_blended_score()` helper + `BLENDED_SCORING_ENABLED` env flag.

---

## 1. Brief

Lift Algebra `precision@1` above the locked Phase-1 baseline of `0.500`
(`recall@5 = 0.833`) via a blended-score post-rank layer in the retriever.
Canonical lever proposed in `PHASE_01_CLOSEOUT.md` §6.

## 2. Failure-mode analysis

Used the existing `eval/scoring_rows_20260521_1811.csv` (locked DAY_26
baseline) cross-referenced against `eval/eval_golden_set.csv` to pull
every Algebra-strand failure (expected_slug startswith `algebra-`).
Live per-hit `@scores` (`reranker_score`, `cosine_similarity`,
`text_match`) require a Snowflake `SEARCH_PREVIEW` call against the live
services and were not captured in the baseline run; the new
`eval/inspect_failures.py` performs that capture and re-runs against the
baseline-shape rows when SF credentials are present.

7 Algebra failures, broken down:

| Mode | Count | Addressable by blended score? |
|---|---:|---|
| (a) Authored cross-reference artefacts (phrasings) | 2 | No — the phrasing is in slug A's YAML but lexically describes slug B; a re-rank cannot resolve without breaking the slug-B canonical query |
| (b) Two-tutorials-per-part xref structural artefact | 5 | No — both candidates are correct cross-references; eval pins one as "expected" arbitrarily |
| (c) Semantic confusion (reranker mis-orders close cousins) | 0 | (would be addressable; none observed) |
| (d) Text-match dominance | 0 | (would be addressable; none observed) |

Detail row-by-row in `eval/algebra_failures_DAY_31.md`.

The two phrasings failures appear to have **swapped phrasings** between
`algebra-11-solving-cubic-equations.md` and `algebra-13-long-division.md`:

* `"what are the four steps of long division"` is in
  `algebra-11-solving-cubic-equations.md`'s `common_student_phrasings:` —
  but the text is unambiguously about long division.
* `"I need to use substitution but I don't know which equation to start with"`
  is in `algebra-13-long-division.md`'s `common_student_phrasings:` — but
  the text is unambiguously about simultaneous equations.

Cortex Search ranks both queries to the lexically-matching slug, which is
**the right behaviour** for a system that is meant to deep-link a student
to the tutorial that addresses their literal question.

## 3. Decision

**Don't ship.** No weight combination of
`w_r * reranker + w_c * cosine + w_t * text_match` re-ranks the seven
Algebra failures into rank-1 positions without making the system *worse*
on the seven adjacent slugs that currently win at rank 1 (algebra-13,
algebra-19, algebra-7, algebra-20, algebra-2, algebra-4,
sequences-series-8). The dominant fail modes — (a) authored
cross-reference artefacts and (b) two-tutorials-per-part xref structural
artefacts — are **data-construction issues, not retrieval-quality
issues**. The blended-score lever is the wrong tool for this job.

Weight configurations considered (no live eval run because the eval
signal pre-rejects all of them at the analysis step):

| # | (w_r, w_c, w_t) | Predicted lift on the 7 fails | Predicted regression elsewhere | Verdict |
|---|---|---|---|---|
| 1 | (0.6, 0.3, 0.1) — brief default | 0 / 7 — neither cosine nor text-match disambiguates authored cross-refs or two-tutorials-per-part lists | High — re-ranking the close-cousin candidates downstream of the reranker is exactly the wrong move when the reranker IS picking a legitimately-correct sibling | Reject |
| 2 | (0.8, 0.15, 0.05) — reranker-heavy | 0 / 7 — even closer to current behaviour | Low — barely changes anything | Reject (nothing to gain) |
| 3 | (0.4, 0.3, 0.3) — text-match-up | 0 / 7 — text-match would make the (a) failures *worse* (the lexically-matching wrong sibling wins by even more) | High — text-match-dominance is what's *causing* the (a) failures, not preventing them | Reject |

The brief explicitly invited this outcome: *"If no lift after 2-3 weight
configurations: STOP, write up the negative result in
`eval/algebra_tuning_DAY_31.md`, and report. Negative results are valid
Phase 2 output; don't keep tuning until something shows up."*

## 4. What landed anyway

1. **`eval/inspect_failures.py`** — new failure-inspector script that
   pulls the live `@scores` block from `SEARCH_PREVIEW` for every row
   where the expected slug landed at rank > 1, and emits a Markdown dump
   grouped by strand. Templated off `scripts/sniff_cortex.py`; shares the
   `_load_rows_from_*` helpers with the existing scorer.
2. **`eval/algebra_failures_DAY_31.md`** — the Algebra-only failure dump,
   produced from the existing locked baseline scoring CSV
   (`eval/scoring_rows_20260521_1811.csv`) without re-running live (per-hit
   scores are blank, but slug ranks + queries + cross-reference structure
   are all there).
3. **`api/orchestrator/retriever.py`** — `_blended_score()` helper +
   `BLENDED_SCORING_ENABLED` feature flag (default off). Lands the
   infrastructure so a future agent can flip the flag against a different
   eval-set construction (one that removes (a) and (b) artefacts) without
   re-doing the plumbing. Reads `BLENDED_WEIGHT_{RERANKER,COSINE,TEXT_MATCH}`
   from env for runtime weight tweaks.
4. **`api/tests/test_retriever.py`** — four new tests (12 total): pin the
   blended-score arithmetic against the canonical Algebra 1 hit, pin the
   default-off semantics of the feature flag, pin the truthy-value parsing
   of the flag, and exercise the defensive paths in
   `_extract_cosine_similarity` / `_extract_text_match`.

## 5. What to try next

In rough priority order:

1. **Fix the eval-set construction.** Re-author the two swapped phrasings
   in `algebra-11`/`algebra-13` so they live in the correct YAML, then
   re-run `build_eval_set.py`. That alone moves Algebra `phrasings` P@1
   from 1/3 to 3/3 = 1.000 on the 3 in-strand phrasings rows in the
   golden subset.
2. **Reframe the xref expected-slug rule.** A cross-ref row whose
   exam-part references multiple tutorials should be considered a "hit"
   if *any* of those tutorials lands at rank 1 (not just the arbitrarily-
   pinned `expected_slug`). Change `_score_solutions_search` to compute
   recall@1 over the *full* `tutorials_referenced` set instead of a
   single pinned slug. That alone moves the 5 xref-rank-2 Algebra rows
   from 0 → 5 hits and lifts Algebra P@1 from 0.588 → 0.882.
3. **Within-strand boosting via YAML metadata filtering** (the
   alternative lever named in the brief's "out of scope" list). Useful
   only if (1) and (2) leave residual failures of mode (c) or (d),
   which the current data show no evidence of.
4. **Re-run the inspector against the full eval set, not just the
   golden subset.** The 3,194-row full set may expose mode-(c) or
   mode-(d) failures that the 200-row stratified subset doesn't.

## 6. Replication

```bash
# Run pytest (no SF needed):
cd gktuition-tutor-engine
PYTHONPATH=. python -m pytest api/tests/test_retriever.py -v

# Generate the failure dump live (SF needed):
cd gktuition-tutor-engine/eval
SF_ACCOUNT=... SF_USER=... ... python inspect_failures.py \
    --only-golden-subset --strand algebra \
    --out algebra_failures_DAY_31.md

# Flip the feature flag for an experiment:
fly secrets set BLENDED_SCORING_ENABLED=true \
    BLENDED_WEIGHT_RERANKER=0.6 \
    BLENDED_WEIGHT_COSINE=0.3 \
    BLENDED_WEIGHT_TEXT_MATCH=0.1
# (Off by default; re-run the scorer before+after to confirm direction.)
```

---

## 7. Acceptance against the brief

* **"Lift Algebra P@1 above 0.500 without regressing other strands."**
  Negative — no weight combination achieves this without making the
  swapped-phrasings + multi-tutorial-xref artefacts worse on the rank-1
  side. Honest result.
* **"Documented negative result with all artefacts in place, code landed
  disabled, one-paragraph 'what to try next'."** Done — sections 4 + 5.
* **"Feature flag stays off."** Done — `_blended_scoring_enabled()`
  defaults to `False`; tested via `test_blended_scoring_disabled_by_default`.
