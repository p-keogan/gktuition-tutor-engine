# Phrasings failure-class analysis — DAY_32

Source: `scoring_rows_20260526_1307.csv` (full eval, DAY_31, 1,511 phrasings rows total). Phrasings P@1 = 0.8220 -> **269 misses analysed** (expected ~269 per the brief; actual = 269).

Analysis is deterministic: each miss falls into exactly one of six buckets via the rules in `categorise_phrasings_failures.py`. Bucket priorities (first match wins): **E** (authored-YAML defect heuristic) -> **D** (expected slug not in top-5) -> **A** (within-strand sibling confusion) -> **B** (cross-strand confusion) -> **C** (strand-prefix mismatch with content overlap) -> **F** (residual — recall@5 = 1, rank > 1). Order deviates from the brief's literal A->F: E is checked first so we don't bury authored-defect cases under within-strand bucketing, and D is checked before A/B so the ~20% of misses where retrieval doesn't surface the expected slug at all aren't hidden inside reranking-side buckets where AGENT_16's blended-score intervention can't help them.

## Headline distribution

| Bucket | Description | Count | % of misses |
|---|---|---:|---:|
| **B** | Cross-strand confusion | 93 | 34.6% |
| **A** | Within-strand sibling confusion | 80 | 29.7% |
| **E** | Authored-YAML defect (heuristic) | 53 | 19.7% |
| **D** | Expected slug not in top-5 (recall@5 = 0) | 43 | 16.0% |
| **C** | Strand-prefix mismatch with content overlap | 0 | 0.0% |
| **F** | Residual (recall@5 = 1 but rank > 1) | 0 | 0.0% |
| **Total** | All phrasings misses | **269** | 100.0% |

✅ Coverage check: bucket counts sum to 269 = 269 (no row uncategorised, no row in two buckets).

## Per-bucket detail (count desc)

### Bucket B — Cross-strand confusion

**Count:** 93 (34.6% of misses)

**Representative rows** (spread across strands):

| eval_id | question_text | expected_slug | top-1 returned | topic |
|---|---|---|---|---|
| `phr_algebra-11-solving-cubic-equations_008` | the remainder is not zero, what did I do wrong | `algebra-11-solving-cubic-equations` | `complex-numbers-15-polar-form-de-moivres-theorem-and-fraction-in-the-power` | complex-numbers |
| `phr_complex-numbers-10-introduction-to-polar-form_004` | how do I find theta | `complex-numbers-10-introduction-to-polar-form` | `trigonometry-2-9-use-the-calculator-to-find-the-reference-angle` | trigonometry |
| `phr_differentiation-10-implicit-differentiation_004` | tangent slope from circle equation | `differentiation-10-implicit-differentiation` | `the-circle-7-tangent-at-point-or-parallel-to-line` | coordinate-geometry-circle |
| `phr_functions-graphs-1-jc-revision_003` | how do I do the vertical line test | `functions-graphs-1-jc-revision` | `the-line-2-position-of-a-point-relative-to-a-line` | coordinate-geometry-line |
| `phr_geometry-1-11-questions-on-theorem-19-circle-questions_007` | how do I identify which arc | `geometry-1-11-questions-on-theorem-19-circle-questions` | `trigonometry-1-8-sector-of-a-circle` | trigonometry |
| `phr_indices-logs-1-jc-revision_003` | what does a to the power of 0 equal | `indices-logs-1-jc-revision` | `integration-4-constant-to-power-of-unknown` | integration |
| `phr_integration-12-area-curve-x-axis_005` | how do I find where two curves meet | `integration-12-area-curve-x-axis` | `algebra-19-simultaneous-equations-by-substitution` | algebra |
| `phr_number-theory-2-prime-factorisation_008` | do I have to start with 2 | `number-theory-2-prime-factorisation` | `induction-3-factorials` | induction |
| `phr_probability-1-jc-revision_002` | how do I draw a tree diagram | `probability-1-jc-revision` | `functions-graphs-9-drawing-graphs` | functions-and-graphs |
| `phr_sequences-series-1-arithmetic-sequences-1_002` | where's Tn in the log tables | `sequences-series-1-arithmetic-sequences-1` | `indices-logs-2-rules-of-logs-1` | indices-and-logs |

**Proposed intervention.** **Largest single bucket. Mixed root cause — query-side rewriting catches the vague-phrasing subset; multi-field weighting catches the lexical-cousin subset.** Spot-check of the bucket-B head shows two distinct sub-patterns: (b1) extremely vague queries that lack any strand-specific signal (*"Q4 is impossible"*, *"what do the vertical bars mean"*) — these cross strands not because the retriever is mis-classifying but because there's nothing to classify against; (b2) queries with lexical overlap to a wrong-strand slug (*"the remainder is not zero"* hitting a complex-numbers polar-form tutorial because both touch *remainders*). **Two interventions:** (1) extend AGENT_21's query rewrite to fire on short queries even without a conceptual-prefix word — this is the iter-2 "rewrite-as-fallback" already proposed in PHASE_02_KICKOFF item 6, and it directly closes the b1 subset. (2) Add multi-field Cortex Search weighting (PHASE_02 open question 6, listed as Phase 2B item 6 in DAY_32 notes) so slug + title carry more weight than transcript body — this biases against b2's spurious cross-strand body matches. Both interventions stack.

---

### Bucket A — Within-strand sibling confusion

**Count:** 80 (29.7% of misses)

**Representative rows** (spread across strands):

| eval_id | question_text | expected_slug | top-1 returned | topic |
|---|---|---|---|---|
| `phr_algebra-1-revision-of-jc-factorising_004` | I have something like ax + ay + bx + by, what do I do | `algebra-1-revision-of-jc-factorising` | `algebra-8-quadratic-graphs` | algebra |
| `phr_complex-numbers-2-addition-subtraction-multiplication_006` | what is a complex number | `complex-numbers-2-addition-subtraction-multiplication` | `complex-numbers-1-introduction` | complex-numbers |
| `phr_differentiation-1-introduction_002` | how to differentiate x cubed | `differentiation-1-introduction` | `differentiation-8-chain-rule` | differentiation |
| `phr_financial-maths-1-simple-interest_002` | how do I find the future value | `financial-maths-1-simple-interest` | `financial-maths-3-time-value-of-money` | financial-maths |
| `phr_geometry-1-1-axioms-theorems-corollaries_002` | how many theorems do I need to know for leaving cert | `geometry-1-1-axioms-theorems-corollaries` | `geometry-1-7-proof-of-theorem-4` | synthetic-geometry |
| `phr_indices-logs-1-jc-revision_002` | what's on log tables page 21 | `indices-logs-1-jc-revision` | `indices-logs-4-changing-the-base` | indices-and-logs |
| `phr_integration-1-algebra_001` | how do I integrate x squared | `integration-1-algebra` | `integration-12-area-curve-x-axis` | integration |
| `phr_sequences-series-1-arithmetic-sequences-1_004` | find the sum of the first n terms | `sequences-series-1-arithmetic-sequences-1` | `sequences-series-3-arithmetic-sequences-3` | sequences-series-patterns-limits |
| `phr_the-circle-1-introduction_001` | how do I find the equation of a circle? | `the-circle-1-introduction` | `the-circle-9-simultaneous-equations` | coordinate-geometry-circle |
| `phr_the-line-1-jc-revision_007` | what's the quickest way to find the equation of a parallel line | `the-line-1-jc-revision` | `the-line-5-perpendicular-distance-from-a-point-to-a-line` | coordinate-geometry-line |

**Proposed intervention.** **Flip `BLENDED_SCORING_ENABLED=true` with eval-gate.** AGENT_16's blended-score post-rank was built for exactly this bucket and is shipped feature-flagged-off. The eval gate (no strand regresses > 3 pts) is already wired into `score_against_cortex_search.py`. Iter-2 candidate: run the gate, flip the flag if green. Optionally pair with chunking re-tuning for the worst-performing strand (the within-strand confusions cluster around sub-strand boundaries like `algebra-13` vs `algebra-19`).

---

### Bucket E — Authored-YAML defect (heuristic)

**Count:** 53 (19.7% of misses)

**Representative rows** (spread across strands):

| eval_id | question_text | expected_slug | top-1 returned | topic |
|---|---|---|---|---|
| `phr_algebra-10-generating-a-cubic-equation-given-the-roots_007` | what does it mean when the curve turns ON the x axis | `algebra-10-generating-a-cubic-equation-given-the-roots` | `integration-12-area-curve-x-axis` | integration |
| `phr_complex-numbers-10-introduction-to-polar-form_008` | do I leave my answer in degrees or radians | `complex-numbers-10-introduction-to-polar-form` | `trigonometry-2-8-converting-degrees-radians-dms` | trigonometry |
| `phr_differentiation-15-turning-points-max-min_002` | second derivative test | `differentiation-15-turning-points-max-min` | `differentiation-13-second-derivative` | differentiation |
| `phr_financial-maths-3-time-value-of-money_004` | rearrange compound interest formula | `financial-maths-3-time-value-of-money` | `financial-maths-2-compound-interest` | financial-maths |
| `phr_functions-graphs-2-shapes-of-quadratic-functions_003` | where is the turning point | `functions-graphs-2-shapes-of-quadratic-functions` | `differentiation-15-turning-points-max-min` | differentiation |
| `phr_geometry-1-1-axioms-theorems-corollaries_014` | similar triangles ratio formula | `geometry-1-1-axioms-theorems-corollaries` | `geometry-1-16-similar-triangles` | synthetic-geometry |
| `phr_indices-logs-2-rules-of-logs-1_008` | how do I find the base of a log | `indices-logs-2-rules-of-logs-1` | `indices-logs-4-changing-the-base` | indices-and-logs |
| `phr_integration-6-trigonometry-2_005` | what to do when there's no 2 in front | `integration-6-trigonometry-2` | `trigonometry-2-5-coefficient-in-front-of-the-angle` | trigonometry |
| `phr_number-theory-1-types-of-numbers_003` | is 1 a prime number | `number-theory-1-types-of-numbers` | `number-theory-2-prime-factorisation` | number-theory |
| `phr_probability-1-jc-revision_004` | how do I work out expected value | `probability-1-jc-revision` | `probability-9-relative-frequency-expected-value` | probability |

**Proposed intervention.** **Curate-then-fix (manual triage required).** The heuristic is an *over-trigger* — DAY_32 spot-check of 7 random rows found ~3 of 7 are clear authored defects (curriculum-judgment would move the phrasing to the top-1 slug), ~3 of 7 are corpus-overlap cases (the question's topic-keyword appears in the top-1 slug but the question's task fits the expected slug), and ~1 of 7 is genuinely ambiguous. The heuristic can't distinguish task-fit from topic-keyword-fit without semantic judgment. **Recommended workflow:** export this bucket as a triage CSV (eval_id, question_text, expected_slug, top1_slug), have a human (Paul) skim and tag each row as {defect, overlap, ambiguous}, then ship an `eval_golden_set.csv` regeneration commit moving only the `defect`-tagged rows (AGENT_20-style). **Expected lift** = number of true defects, estimated 20-30 of 53 -> phrasings P@1 lifts from 0.822 -> ~0.836-0.842. Lower than the headline bucket-E count suggests because of the heuristic's known false-positive rate.

---

### Bucket D — Expected slug not in top-5 (recall@5 = 0)

**Count:** 43 (16.0% of misses)

**Representative rows** (spread across strands):

| eval_id | question_text | expected_slug | top-1 returned | topic |
|---|---|---|---|---|
| `phr_avm-1-1-jc-revision_008` | what shape formulas are on the log tables | `avm-1-1-jc-revision` | `avm-1-3-trapezoidal-rule` | area-volume-measurement |
| `phr_algebra-10-generating-a-cubic-equation-given-the-roots_010` | do I multiply by -1 or by 2 or by -2 | `algebra-10-generating-a-cubic-equation-given-the-roots` | `complex-numbers-2-addition-subtraction-multiplication` | complex-numbers |
| `phr_complex-numbers-10-introduction-to-polar-form_005` | why do I need to add 180 to my angle | `complex-numbers-10-introduction-to-polar-form` | `geometry-1-7-proof-of-theorem-4` | synthetic-geometry |
| `phr_differentiation-1-introduction_001` | what's the power rule | `differentiation-1-introduction` | `integration-2-integrating-1-over-x` | integration |
| `phr_financial-maths-4-rate-conversion_009` | do I use logs or fractional exponents | `financial-maths-4-rate-conversion` | `indices-logs-5-unknown-in-power-natural-log` | indices-and-logs |
| `phr_functions-graphs-10-limits_007` | why can't I just sub in | `functions-graphs-10-limits` | `algebra-19-simultaneous-equations-by-substitution` | algebra |
| `phr_geometry-1-1-axioms-theorems-corollaries_007` | do I need to know the junior cert proofs for leaving cert | `geometry-1-1-axioms-theorems-corollaries` | `geometry-1-4-proof-of-theorem-6` | synthetic-geometry |
| `phr_indices-logs-1-jc-revision_010` | what's the difference between cube root and square root | `indices-logs-1-jc-revision` | `avm-1-2-unit-conversion` | area-volume-measurement |
| `phr_integration-12-area-curve-x-axis_007` | how do I sketch a cubic | `integration-12-area-curve-x-axis` | `algebra-10-generating-a-cubic-equation-given-the-roots` | algebra |
| `phr_number-theory-5-construct-root-3_009` | how do I prove the construction works | `number-theory-5-construct-root-3` | `geometry-1-10-proof-of-theorem-14` | synthetic-geometry |

**Proposed intervention.** **Mostly an eval-quality issue, not a retrieval failure.** Spot-check of the bucket-D head reveals the dominant pattern: extremely vague phrasings that read like mid-conversation utterances rather than standalone tutor queries — *"do I multiply by -1 or by 2 or by -2"*, *"Q4 is impossible"*, *"do I need to find the y-coordinates as well"*. These can't be retrieved against without conversational context (which the current eval harness doesn't model). **Recommended:** flag these 43 rows in the eval set with a new `requires_context: true` field and either (a) exclude them from the headline P@1 metric while reporting a separate "contextual-followup" P@1 below the line, or (b) re-author the phrasings to be standalone ("in a cubic-factorisation step, do I multiply by -1 or by 2"). Either path is eval-set work in `eval/build_eval_set.py` + a regeneration commit, not an orchestrator change. Genuine corpus-coverage gaps in this bucket appear to be a minority — confirm with a wider manual scan before any corpus authoring work.

---

### Bucket C — Strand-prefix mismatch with content overlap

**Count:** 0 (0.0% of misses)

_No rows in this bucket._

---

### Bucket F — Residual (recall@5 = 1 but rank > 1)

**Count:** 0 (0.0% of misses)

_No rows in this bucket._

---

## By-strand cross-cut

Misses grouped by the expected slug's strand. Top-3 worst strands are the per-strand priorities for iter-2 / iter-3.

| Strand | **B** | **A** | **E** | **D** | **C** | **F** | **Total** | % of all misses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `LCHL_Geometry_1` | 30 | 12 | 4 | 6 | 0 | 0 | **52** | 19.3% |
| `LCHL_Algebra` | 8 | 11 | 4 | 3 | 0 | 0 | **26** | 9.7% |
| `LCHL_Trigonometry_2` | 8 | 11 | 3 | 1 | 0 | 0 | **23** | 8.6% |
| `LCHL_Trigonometry_3` | 3 | 6 | 10 | 2 | 0 | 0 | **21** | 7.8% |
| `LCHL_Sequences_and_Series` | 8 | 5 | 3 | 3 | 0 | 0 | **19** | 7.1% |
| `LCHL_Trigonometry_4` | 3 | 9 | 1 | 5 | 0 | 0 | **18** | 6.7% |
| `LCHL_Indices_and_Logs` | 4 | 7 | 2 | 2 | 0 | 0 | **15** | 5.6% |
| `LCHL_Trigonometry_1` | 5 | 2 | 4 | 3 | 0 | 0 | **14** | 5.2% |
| `LCHL_Differentiation` | 4 | 4 | 2 | 3 | 0 | 0 | **13** | 4.8% |
| `LCHL_Complex_Numbers` | 3 | 4 | 1 | 3 | 0 | 0 | **11** | 4.1% |
| `LCHL_The_Circle` | 2 | 1 | 5 | 2 | 0 | 0 | **10** | 3.7% |
| `LCHL_Functions_and_Graphs` | 4 | 0 | 2 | 3 | 0 | 0 | **9** | 3.3% |
| `LCHL_Number_Theory` | 4 | 0 | 4 | 1 | 0 | 0 | **9** | 3.3% |
| `LCHL_The_Line` | 4 | 1 | 2 | 2 | 0 | 0 | **9** | 3.3% |
| `LCHL_Financial_Maths` | 0 | 4 | 1 | 1 | 0 | 0 | **6** | 2.2% |
| `LCHL_Integration` | 1 | 3 | 1 | 1 | 0 | 0 | **6** | 2.2% |
| `LCHL_Probability` | 1 | 0 | 2 | 0 | 0 | 0 | **3** | 1.1% |
| `LCHL_Statistics` | 1 | 0 | 2 | 0 | 0 | 0 | **3** | 1.1% |
| `LCHL_AVM_1` | 0 | 0 | 0 | 2 | 0 | 0 | **2** | 0.7% |

✅ Cross-cut consistency: per-strand totals sum to 269 = 269.

**Top-3 strands with the highest miss count:**

1. `LCHL_Geometry_1` — 52 misses (19.3% of all misses)
2. `LCHL_Algebra` — 26 misses (9.7% of all misses)
3. `LCHL_Trigonometry_2` — 23 misses (8.6% of all misses)

**New finding worth flagging.** `LCHL_Geometry_1` is the single largest miss strand by a substantial margin (~2x the next-biggest), but DAY_31's topic-bucket scoring report did *not* flag synthetic-geometry as a weak bucket — the topic-bucket view rolls Geometry into the free-text `topic` field (often surfacing as 'synthetic-geometry') and the per-tutorial P@1 there reads as middling, not alarming, because the strand has many tutorials and the misses are spread thin. The strand-level view above is what surfaces the absolute-miss-count signal. **Implication:** any iter-2 / iter-3 intervention that doesn't move Geometry_1 leaves ~20% of the phrasings miss-count untouched. The Bucket-B count within Geometry_1 (30 of 52 = 58%) suggests cross-strand confusion is the dominant Geometry_1 failure mode — synthetic-geometry queries get pulled into Trigonometry, The Line, The Circle, or AVM neighbours.

**Cross-reference vs DAY_31 topic-bucket scoring report.** The DAY_31 report flagged **coordinate-geometry-line (0.649)**, **algebra (0.758)**, and **complex-numbers (0.772)** as the weakest topic buckets. The strand cross-cut here confirms Algebra and Complex Numbers as real concerns (`LCHL_Algebra` = 26 misses, `LCHL_Complex_Numbers` = 11) and confirms The Line presence (`LCHL_The_Line` = 9, smaller absolute count because the strand has fewer phrasings overall — the low P@1 there is a per-tutorial concentration not a broad-strand issue). The Geometry_1 finding above is the divergence the topic-bucket view missed.

## Recommended intervention priority

**Iter-2 (highest-ROI single change): target bucket B — Cross-strand confusion.** 93 of 269 misses (34.6%). If this entire bucket flipped to P@1=1.0, phrasings P@1 would lift from 0.8220 -> ~0.8835.

**Largest single bucket. Mixed root cause — query-side rewriting catches the vague-phrasing subset; multi-field weighting catches the lexical-cousin subset.** Spot-check of the bucket-B head shows two distinct sub-patterns: (b1) extremely vague queries that lack any strand-specific signal (*"Q4 is impossible"*, *"what do the vertical bars mean"*) — these cross strands not because the retriever is mis-classifying but because there's nothing to classify against; (b2) queries with lexical overlap to a wrong-strand slug (*"the remainder is not zero"* hitting a complex-numbers polar-form tutorial because both touch *remainders*). **Two interventions:** (1) extend AGENT_21's query rewrite to fire on short queries even without a conceptual-prefix word — this is the iter-2 "rewrite-as-fallback" already proposed in PHASE_02_KICKOFF item 6, and it directly closes the b1 subset. (2) Add multi-field Cortex Search weighting (PHASE_02 open question 6, listed as Phase 2B item 6 in DAY_32 notes) so slug + title carry more weight than transcript body — this biases against b2's spurious cross-strand body matches. Both interventions stack.

**Iter-3 (next-largest bucket): target bucket A — Within-strand sibling confusion.** 80 of 269 misses (29.7%).

**Flip `BLENDED_SCORING_ENABLED=true` with eval-gate.** AGENT_16's blended-score post-rank was built for exactly this bucket and is shipped feature-flagged-off. The eval gate (no strand regresses > 3 pts) is already wired into `score_against_cortex_search.py`. Iter-2 candidate: run the gate, flip the flag if green. Optionally pair with chunking re-tuning for the worst-performing strand (the within-strand confusions cluster around sub-strand boundaries like `algebra-13` vs `algebra-19`).

## Verification

Six checks against the DAY_32 dispatch's verification list:

1. ✅ **Bucket counts sum to total.** 269 = 269, no row uncategorised, no row in two buckets.
2. ✅ **Sample rows are real.** Each `eval_id` in the per-bucket sample tables is verifiable via `grep` against `scoring_rows_20260526_1307.csv`.
3. ✅ **Cross-cut totals match.** Per-strand totals sum to 269 = 269.
4. ⚠️ **Bucket E spot-check landed below 4/5 threshold.** Re-tightened heuristic to require either (a) >=2 content-token overlap with top-1 and zero with expected, or (b) >=1 distinctive token (corpus-slug-frequency <= 2) and zero overlap with expected. Spot-check of 7 random Bucket-E rows after the tightening showed ~3/7 clear authored defects, ~3/7 corpus-overlap cases (top-1 has the topic keyword but the task fits expected), ~1/7 ambiguous. The heuristic has a structural limit — it cannot distinguish task-fit from topic-keyword-fit without semantic judgment. **Resolution:** Bucket E is framed in the report as a *candidate triage list*, not an auto-fix list. The expected-lift estimate (20-30 of 53 rows) reflects the spot-check rate, not the headline count. Listed under 'open follow-ups' below.
5. ✅ **Recommended-intervention sections name specific code changes.** Bucket B intervention references `api/orchestrator/query_rewrite.py` (extend AGENT_21 pre-check) and Cortex Search multi-field weighting (retriever-side config). Bucket A intervention references `BLENDED_SCORING_ENABLED` env flag flip + the existing eval-gate in `eval/score_against_cortex_search.py`. Bucket D intervention references `eval/build_eval_set.py` regeneration with a new `requires_context` flag. Bucket E intervention references a human-triage CSV + `eval_golden_set.csv` regeneration commit (AGENT_20 pattern).
6. ✅ **Strand cross-cut surfaces a divergence from the DAY_31 topic-bucket view.** `LCHL_Geometry_1` is the single largest miss strand at 52 misses (19.3% of all misses) — not flagged in the DAY_31 report. Documented as a new finding under the by-strand section above.

### Open follow-ups

These came up during analysis and warrant explicit decisions before the next eval round:

1. **Bucket E manual triage.** Paul-driven skim of the 53 candidate rows to tag each as {defect, overlap, ambiguous}. Time estimate: ~30 minutes. Output: tag column added to the per-row CSV; defects move via `eval_golden_set.csv` regeneration.
2. **`LCHL_Geometry_1` deep-dive.** The 30 Geometry_1 bucket-B misses suggest a strand-specific routing issue. Worth a focused look at what the retriever is doing on synthetic-geometry queries before iter-2 ships, in case there's a single shared root cause (e.g. the strand's slugs share more body-text vocabulary with neighbouring strands than expected).
3. **Eval-set hygiene scan.** Bucket D's pattern suggests a chunk of phrasings were authored as follow-up utterances rather than standalone queries. Spot-scan the 43 D rows + the broader phrasings set for similar patterns; consider a `requires_context` field in `build_eval_set.py`.
4. **Note on eval-set restratification.** Out of scope for this dispatch (per the brief) but flagged for awareness: the 200-row golden subset's 0.710 -> 0.720 movement on DAY_31 vs the full eval's 0.911 P@1 reflects the same coverage-gap as the topic-bucket vs strand-level divergence here — the golden subset under-samples both cross-ref and Geometry phrasings. Worth a re-stratification pass before Phase 2B closes.

## Appendix — full per-row categorisation

Full categorised CSV: [`phrasings_failure_classes_DAY_32.csv`](./phrasings_failure_classes_DAY_32.csv) (269 rows, one per miss). Columns: `bucket, eval_id, expected_slug, top1_slug, rank, recall@5, topic, expected_strand, top1_strand, overlap_top1, overlap_exp, distinctive_overlap, lcs_len, question_text`.

Regenerate with: `python eval/categorise_phrasings_failures.py --scoring-csv eval/<rows>.csv --golden-csv eval/eval_golden_set.csv`.
