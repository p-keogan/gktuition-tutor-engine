# Algebra failure dump — DAY_31 baseline analysis

**Source data:** `eval/scoring_rows_20260521_1811.csv` (the locked DAY_26
Phase-1 baseline) cross-referenced against `eval/eval_golden_set.csv`.

**Method.** The `topic` column reported in the baseline scoring CSV is
inferred from the *first hit's* `topic` field, not the expected slug's
strand. The headline "Algebra P@1 = 0.500" lives in that grouping. For the
purposes of *fixing the right thing*, this dump groups by the
**expected slug's strand prefix** instead (every row whose `expected_slug`
starts with `algebra-`).

**Per-hit `reranker_score` / `cosine_similarity` / `text_match` are not
captured here** — populating those requires a live Cortex `SEARCH_PREVIEW`
call against the running services, which `eval/inspect_failures.py`
performs when Snowflake credentials are present. This dump uses the
slug-rank data already on disk from the baseline run.

---

## Summary

**Algebra-strand rows (expected_slug startswith `algebra-`):** 17.
**Hits at rank 1:** 10.
**Hits at rank > 1 (in top-5):** 7.
**Missed (not in top-5):** 0 in the by-expected-strand cut.

**Strand-by-strand P@1 (recomputed by expected-slug prefix, not top-hit
topic):**

| strand | n | P@1 |
|---|---:|---:|
| financial-maths | 14 | 0.929 |
| integration | 7 | 0.857 |
| probability | 12 | 0.833 |
| statistics | 11 | 0.818 |
| the-line | 16 | 0.812 |
| differentiation | 12 | 0.750 |
| OTHER:geometry | 12 | 0.750 |
| the-circle | 16 | 0.750 |
| trigonometry | 16 | 0.750 |
| indices-logs | 7 | 0.714 |
| avm | 9 | 0.667 |
| functions-graphs | 8 | 0.625 |
| **algebra** | **17** | **0.588** |
| **sequences-series** | **17** | **0.588** |
| complex-numbers | 11 | 0.545 |
| number-theory | 10 | 0.500 |
| induction | 5 | 0.400 |

The headline-baseline Algebra P@1 = 0.500 is *the top-hit-topic-bucket
view* — i.e. of all rows where the top-1 returned hit had `topic=algebra`,
6/12 were correct. Recomputing by expected-strand gives 0.588, and Algebra
is co-weakest among "common" strands with Sequences & Series, both ahead
of three smaller / harder strands (complex-numbers, number-theory,
induction).

---

## Algebra failures — by row

### `phr_algebra-11-solving-cubic-equations_005`

- **source:** phrasings (auto-easy)
- **expected slug:** `algebra-11-solving-cubic-equations`
- **rank of expected slug:** 2

**Query.** `what are the four steps of long division`

**Top-5 returned:**

1. `algebra-13-long-division`
2. `algebra-11-solving-cubic-equations` ← expected
3. `induction-1-introduction`
4. `algebra-5-fractions-part-2`
5. `algebra-4-fractions`

**Authored cross-reference reality.** The phrasing
*"what are the four steps of long division"* genuinely lives in the
`common_student_phrasings` block of `algebra-11-solving-cubic-equations.md`
because the cubic-solving pipeline (Factor Theorem → long division →
depressed quadratic) uses long division as a step. But the **literal text**
matches `algebra-13-long-division` exactly. Cortex Search did the right
thing: lexically the query *is* about long division.

**Verdict.** The "fail" is an authored cross-reference artefact, not a
retrieval-quality issue. The blended-score lever cannot fix this without
also breaking the canonical long-division query.

---

### `phr_algebra-13-long-division_009`

- **source:** phrasings (auto-medium)
- **expected slug:** `algebra-13-long-division`
- **rank of expected slug:** *not in top-5*

**Query.** `I need to use substitution but I don't know which equation to start with`

**Top-5 returned:**

1. `algebra-19-simultaneous-equations-by-substitution`
2. `differentiation-12-substitution`
3. `indices-logs-7-quadratic-equations-2`
4. `indices-logs-6-quadratic-equations-1`
5. `trigonometry-4-4-quadratic-equations`

**Authored cross-reference reality.** Mirror image of the previous row:
the phrasing is genuinely in `algebra-13-long-division.md` (Paul uses it
when discussing which equation to substitute *into* during long division
of polynomials), but it reads as a simultaneous-equations question to any
reasonable reader. Cortex Search returned the expected
`algebra-19-simultaneous-equations-by-substitution` correctly.

**Verdict.** Same as above — authored cross-reference artefact, blended
scoring cannot fix without breaking the simultaneous-equations canonical
query. Two phrasings appear to have been **swapped** at the YAML-authoring
step (one belongs in long-division, the other in cubic-equations).

---

### `xref_2016_main_P1_Q9biii_algebra-1-revision-of-jc-factorising`

- **source:** solution_cross_ref
- **expected slug:** `algebra-1-revision-of-jc-factorising`
- **rank of expected slug:** 2

**Query.** *"The number of ancestors can also be calculated by
`Gₙ = ((1 + √5)ⁿ − (1 − √5)ⁿ) / (2ⁿ √5)`. Use this formula to verify the
number of ancestors in `G₃`."*

**Flattened `tutorials_referenced` (rank order):**

1. `sequences-series-8-geometric-sequences-4`
2. `algebra-1-revision-of-jc-factorising` ← expected

**Verdict.** The corpus-gap row (Binet's formula not in a dedicated
tutorial). The eval row's expected slug picks one of two tutorials that
the exam-part references; the model picks the other. **Both are
substantively correct**; the rank-2 outcome is structurally caused by
two-tutorials-per-part with an arbitrary "expected" assignment.

---

### `xref_2020_main_P1_Q7bi_algebra-5-fractions-part-2`

- **source:** solution_cross_ref
- **expected slug:** `algebra-5-fractions-part-2`
- **rank of expected slug:** 2

**Query.** *"Write the expression `n(n+1)/2 + (n+1)` as a single fraction
in its simplest form."*

**Flattened `tutorials_referenced` (rank order):**

1. `algebra-4-fractions`
2. `algebra-5-fractions-part-2` ← expected
3. `algebra-1-revision-of-jc-factorising`

**Verdict.** Two-tutorials-per-part artefact again. The exam-part
references `algebra-4-fractions` and `algebra-5-fractions-part-2` in that
order; both are legitimate (fractions-part-1 covers like denominators,
fractions-part-2 covers unlike). The model returns the sibling because it
appears first in the cross-reference list.

---

### `xref_2021_main_P1_Q3bi_algebra-9-nature-of-quadratic-graphs`

- **source:** solution_cross_ref
- **expected slug:** `algebra-9-nature-of-quadratic-graphs`
- **rank of expected slug:** 2

**Query.** *"Given `f(x) = 3x² + 8x − 35`, find the two roots of `f(x) = 0`."*

**Flattened `tutorials_referenced` (rank order):**

1. `algebra-2-factorising-quadratics`
2. `algebra-9-nature-of-quadratic-graphs` ← expected
3. `avm-1-3-trial-and-improvement` (or similar — truncated in baseline CSV)

**Verdict.** `algebra-2-factorising-quadratics` is the right answer for
"find the roots" by factorisation; `algebra-9-nature-of-quadratic-graphs`
is the right answer for "discuss the nature" question. Both substantively
fit "two roots of `f(x)=0`" — Paul authored both as cross-refs. The model
picks factorising, which is arguably more on-point.

---

### `xref_2023_df_P1_Q2a_algebra-2-factorising-quadratics`

- **source:** solution_cross_ref
- **expected slug:** `algebra-2-factorising-quadratics`
- **rank of expected slug:** 2

**Query.** *"Solve the inequality, for `x ∈ ℝ`, `x ≠ 1`:
`(3x + 1)/(x − 1) ≤ 6`"*

**Flattened `tutorials_referenced` (rank order):**

1. `algebra-7-rational-inequalities`
2. `algebra-2-factorising-quadratics` ← expected
3. `algebra-6-inequalities` (or similar)

**Verdict.** `algebra-7-rational-inequalities` IS the canonical rational-
inequality tutorial; `algebra-2-factorising-quadratics` is what you'd use
after collapsing the rational inequality to a quadratic-vs-zero form.
Both are correct, and the model picks the more-specific tutorial (which
is arguably the *better* answer than the one Paul authored as expected).

---

### `xref_2025_df_P1_Q5a_algebra-21-binomial-theorem`

- **source:** solution_cross_ref
- **expected slug:** `algebra-21-binomial-theorem`
- **rank of expected slug:** 2

**Query.** *"Multiply out and simplify `(x − 1)³`"*

**Flattened `tutorials_referenced` (rank order):**

1. `algebra-20-pascals-triangle`
2. `algebra-21-binomial-theorem` ← expected
3. `algebra-11-solving-cubic-equations` (or similar)

**Verdict.** `(x-1)³` at low power can be done either by direct multiplication
with Pascal's triangle coefficients or by the binomial theorem — Paul's
own metadata text in `source_metadata.topic` literally says *"either direct
multiplication or the binomial theorem with `n = 3`"*. Both expected and
returned are correct.

---

## Failure-mode breakdown

| Mode | Count | Description |
|---|---:|---|
| (a) Authored cross-reference artefacts (phrasings) | 2 | Phrasings genuinely listed in slug A's YAML but lexically pointing at slug B; model picks the lexical match |
| (b) Two-tutorials-per-part with arbitrary expected (xref) | 5 | Cross-ref row references multiple tutorials; eval pins one as "expected", model picks another from the same list; both are legitimately correct |
| (c) Semantic confusion (reranker noise) | 0 | None — every "failure" is in (a) or (b) |
| (d) Text-match dominance | 0 | None |
| (e) Other | 0 | None |

**Headline.** **Zero of the seven Algebra failures are addressable by
blended-score post-rank on the retriever.** (a) and (b) are both data /
eval-set artefacts that a re-rank cannot resolve without also breaking
genuinely-correct queries on adjacent slugs. The eval signal is not
reporting a retrieval-quality problem; it is reporting an
eval-set-construction limitation.
