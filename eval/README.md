# Eval — offline retrieval-quality measurement

This folder is Agent 05's delivery from PLAN_PIVOT_DAY_26. It bootstraps the
Week 13 ≥ 80% precision@1 milestone from ~200 hand-curated golden questions
down to "filter ~200 from an auto-generated set of ≥ 3,000", swapping a
multi-week curation slog for a quick filtering pass.

The four files in this directory:

| File | What it does |
|---|---|
| `bootstrap_eval_table.sql` | DDL for `GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET`. Idempotent. |
| `build_eval_set.py` | Walks the tutorial corpus + exam-solutions corpus, emits one row per `(question_text, expected_slug)` pair, MERGEs into the table, writes a portable CSV. |
| `select_golden_subset.py` | Stratified random pick of ~200 rows; flips `is_in_golden_subset = TRUE`. |
| `score_against_cortex_search.py` | Issues each question against the appropriate Cortex Search Service, captures top-K=5 results, computes precision@1 / recall@5 / MRR with breakdowns. |

The CSV (`eval_golden_set.csv`) is the canonical committed artefact — it
captures the full eval set in a form that doesn't require Snowflake access,
and is what the scoring script reads with `--from-csv`.

## Why two bootstrap sources

The two channels emit substantively different kinds of evaluation pairs and
exercise different parts of the retrieval surface. Both end up in the same
table, distinguished by the `source` column.

`source = 'phrasings'`. Each entry in a tutorial's `common_student_phrasings[]`
YAML field is, by definition, a retrieval target that tutorial claims to
answer. So `(phrasing, tutorial.slug)` is a self-labelled positive pair.
These rows test `TUTOR_SEARCH` (Agent 01's service over `RAW.TUTORIALS`).

`source = 'solution_cross_ref'`. Agent 02's exam-solution chunker recorded
the `tutorials_referenced[]` array on every exam part. So
`(exam_part.question_text, tutorial in tutorials_referenced)` is a
positive pair where the question is a real exam prompt and the expected
tutorial is the one the curriculum-judging human linked it to in the
solution write-up. These rows test `SOLUTIONS_SEARCH` (Agent 02's service
over `RAW.EXAM_PARTS`) — the top-K parts' `tutorials_referenced` arrays
are flattened to rank slugs.

Both sources are deterministic and idempotent — re-running emits the same
row dicts with the same `eval_id` values, and the MERGE is keyed on
`eval_id` so no row is duplicated on re-runs.

## Locked baselines

The canonical numbers every subsequent improvement is measured against.

| Phase | Date | Sample | Overall P@1 | Recall@5 | MRR | Phrasings P@1 | Cross-ref P@1 |
|---|---|---|---:|---:|---:|---:|---:|
| **Phase 1 (DAY_26)** | 2026-05-21 | 200-row golden subset | **0.710** | 0.985 | 0.835 | 0.811 | 0.651 |
| **Phase 2A (DAY_31)** | 2026-05-26 | full 3,194-row eval | **0.911** | 0.984 | 0.942 | 0.822 | **0.990** |

The Phase-2A locked baseline is measured on the full eval set, not the 200-row golden subset. **Same-sample re-score of the 200-row golden subset on DAY_31 lands at 0.720** (i.e. Phase-1 → Phase-2A on the same subset moved +0.010, within noise). The subset under-samples the cross-ref rows where AGENT_20's scorer-xref rule (rank-1 hit on ANY `tutorials_referenced` slug = correct) drives the bulk of the lift — the subset's phrasings/cross-ref split is 74/126 versus the full eval's 1,511/1,683. **The golden subset needs re-stratification in Phase 2B** so it becomes a useful proxy for full-eval performance again; until then, the nightly `scheduled_eval.yml` workflow that runs against the subset is a regression-detector on phrasings only, not a Phase-2A baseline tracker.

## Algebra bucketing convention (reconciliation)

AGENT_16 (DAY_30) flagged that the same underlying data appears as two different Algebra P@1 numbers depending on bucketing:

- **Topic-bucket view** (the `by_topic` table in the scoring report) buckets eval rows by their `EXAM_PARTS.topic` string. Algebra here reads **0.500** at Phase-1 baseline and **0.758** at Phase-2A on the full eval.
- **Strand-prefix view** (an analytical breakdown that buckets rows by the strand-directory prefix on the expected slug — e.g. anything matching `algebra-*` lands in the Algebra bucket regardless of `EXAM_PARTS.topic` value) reads **0.588** at Phase-1 baseline.

The two views disagree because the `EXAM_PARTS.topic` field on the solutions side contains some descriptive sentences instead of clean topic labels (a corpus contamination item logged for Phase-2B cleanup), so the topic-bucket view either drops or mis-buckets some Algebra-strand rows that the strand-prefix view correctly captures.

**Going-forward convention: the strand-prefix view is canonical for per-strand P@1 reporting.** It's deterministic given the `STRAND_PREFIX_MAP` in `api/orchestrator/voice_anchor.py` and unaffected by free-text contamination in the topic field. The scoring report's existing topic-bucket section stays for back-compat + topic-level drill-down, but per-strand baselines (the kind we cite in CV / closeout docs) are the strand-prefix view. The cleanest fix is to populate a `strand` column on the per-row CSV emitted by `score_against_cortex_search.py`, derived from `infer_strand_from_slug(expected_slug)`, and add a `by_strand` table to the scoring report next to `by_topic`. Tracked as a Phase-2B chore.

## How to run

```bash
# From the project's Python 3.12 venv.
source ../../career-transition-2026/.venv-py312/bin/activate

# 0. Once, per Snowflake account.
#    From a worksheet, with ACCOUNTADMIN role:
\!source bootstrap_eval_table.sql

# 1. Build the full eval set. The --from-files flag parses cross-references
#    from the solutions .md files on disk (Agent 02 wrote machine-readable
#    YAML blocks there) — no Snowflake credentials needed for the read.
#    The CSV is always written; the Snowflake MERGE runs unless --dry-run.
python build_eval_set.py --from-files
#   → eval_golden_set.csv  (≥ 3,000 rows)
#   → MERGE into RAW.EVAL_GOLDEN_SET

# 2. Pick the ~200-row golden subset. Stratified 50 easy / 100 medium / 50 hard,
#    balanced across source and strand. Deterministic given --seed.
python select_golden_subset.py --from-csv eval_golden_set.csv \
                               --write-csv eval_golden_set.csv \
                               --reset
#   → CSV: ~200 rows now have is_in_golden_subset = TRUE
#   Or, against the live table (no --from-csv):
python select_golden_subset.py --reset

# 3. Score against the live Cortex Search Services. Needs Snowflake creds.
python score_against_cortex_search.py --only-golden-subset
#   → scoring_report_YYYYMMDD_HHMM.md
#   → scoring_rows_YYYYMMDD_HHMM.csv

# The full set can be scored too, but it costs ~3,000 SEARCH_PREVIEW calls
# on WH_TUTOR. Keep that for a once-per-week run, not iteration.
python score_against_cortex_search.py
```

## Cross-ref scoring rule (AGENT_20, DAY_31)

For ``source = 'solution_cross_ref'`` rows, the scorer counts a hit when
**any** slug in the row's exam-part's ``tutorials_referenced`` set lands
at rank 1 in the flattened SOLUTIONS_SEARCH ranking — not just the
arbitrarily-pinned ``expected_slug``. The eval set emits one row per
``(part_id, slug)`` pair, so a part that references three tutorials emits
three rows whose ``expected_slug`` values are all individually legitimate
cross-refs of the same exam question. Counting only the pinned slug as
correct understated retrieval quality on multi-tutorial parts; the
new rule makes the precision@1 number directly interpretable as "the
retrieval surface put a substantively-correct tutorial at rank 1."

Implementation lives in ``_score_solutions_search`` + the helper
``_best_rank_over_slugs``. The set of valid sibling slugs for each row
is recovered by ``_build_part_id_to_referenced_slugs(rows)`` at
orchestration time (grouping the loaded eval rows on ``part_id``). A
regression test pins the behaviour in
``api/tests/test_score_xref_rule.py``.

**Locked baseline pointer.** The Phase-1 locked baseline
(``scoring_rows_20260521_1811.csv``, overall P@1 = 0.710, Algebra P@1 =
0.500 under the old top-hit-topic-bucket view) remains the on-disk
historical reference. The current candidate-baseline file is
``scoring_rows_20260525_1752.csv`` (overall P@1 = 0.925, Algebra P@1 =
1.000 on the 200-row golden subset). The candidate-baseline file is a
**projected** scoring run (the locked baseline's per-row data
reinterpreted under the new rule + the AGENT_20 phrasing remap, since
the producing sandbox didn't carry SF creds). The operator should
publish a live re-score using ``python eval/score_against_cortex_search.py
--only-golden-subset`` once the regenerated ``eval_golden_set.csv`` is
MERGE'd into ``RAW.EVAL_GOLDEN_SET`` and the golden subset is re-flagged
via ``select_golden_subset.py``.

## How to read the report

The markdown report has four sections:

1. **Overall** — single-number headline (precision@1 / recall@5 / MRR).
2. **By source** — phrasings vs solution_cross_ref. Expect the phrasings
   number to be higher: a phrasing was literally written to match its
   tutorial, while exam-question prompts are harder.
3. **By difficulty tier** — `auto-easy` / `auto-medium` / `auto-hard`. The
   easy tier is the baseline; the hard tier surfaces where the retrieval
   surface struggles.
4. **By topic (weakest first)** — the actionable section. Topics with
   precision@1 well below the source average are likely showing a
   chunking or embedding problem worth investigating.

A per-row CSV is also written so you can drill into specific failures:
"the eval row with id `xref_2024_main_P2_Q5b_complex-numbers-7-rotations`
expected `complex-numbers-7-rotations` but the top-K parts only returned
`complex-numbers-10-introduction-to-polar-form`" — that's the kind of
detail you need to decide whether the gap is a real retrieval failure or
a noisy expected label.

## Realistic v1 numbers

The retrieval surface is brand new and the eval set was bootstrapped
without any human filtering, so the first scoring run will be noisier
than the headline targets. Reasonable v1 expectations:

| Slice | Target | Why the floor isn't higher |
|---|---|---|
| Phrasings — precision@1 | ≥ 70% | Phrasings are written to match the tutorial, but the multi-field index has to rank across 237 tutorials including near-duplicate sequence numbers ("trigonometry 3" vs "trigonometry 4"). Some confusion is real. |
| Solution cross-refs — precision@1 | ≥ 50% | Exam questions often span multiple tutorials. A part with `tutorials_referenced = [A, B, C]` produces three eval rows; only one of A/B/C can be at rank 1. The recall@5 number is the more honest signal here. |
| Combined — precision@1 | ≥ 65% | Weighted average — depends on the mix in the golden subset (we currently target ~50/50 phrasings vs cross-refs). |

Anything materially below those floors is a real problem (likely the
multi-field `ON` syntax not active on the account, or the embedding lag
not yet caught up — both flagged in Agent 01's delivery note).

Anything materially above is suspicious — most often it means the
question_text has accidentally leaked the expected slug. Spot-check the
report's sample failures section if precision@1 comes back >90% on a
first run.

## Idempotency and re-running

* Every `eval_id` is deterministic: the phrasings rows use
  `phr_{slug}_{NNN}` where N is the 1-indexed position within the
  tutorial's `common_student_phrasings[]`; the cross-ref rows use
  `xref_{part_id}_{expected_slug}`. New phrasings or new exam papers
  appear as new rows; nothing else changes.
* The MERGE in `build_eval_set.py` updates everything **except**
  `is_manually_reviewed` and `is_in_golden_subset`. Those flags are
  owned respectively by the human curator and by
  `select_golden_subset.py` — a re-bootstrap shouldn't blow them away.
* `select_golden_subset.py` re-runs deterministically given `--seed`.
  Pass `--reset` to clear the previous selection before re-picking.

## Out of scope

This eval set is **offline only** — it never modifies the production
retrieval surface or its scoring thresholds. It exists to measure, not
to tune.

The script does not modify any tutorial `.md` file, nor the EXAM_PARTS
table. The only side effect (besides Snowflake writes to
`EVAL_GOLDEN_SET`) is the CSV file in this directory.

Hand-curating eval rows is also out of scope: the human picks the
golden subset from the auto-generated set, doesn't author replacement
rows. The auto-generated rows are good enough to bootstrap; the human
filters for the ones they trust most, and that filtered subset becomes
the headline number.
