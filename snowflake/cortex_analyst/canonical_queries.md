# Cortex Analyst — Canonical Analytical Queries

Ten queries the `lchl_exam_analytics` Cortex Analyst service must answer
fluently. Each was chosen because either (a) the student would plausibly ask
it during revision, (b) Paul would plausibly ask it during exam-prep advice,
or (c) it exercises a SQL pattern the model needs to learn (cross-year
deltas, multi-filter, full-outer joins for "compared-to" questions).

The "Expected SQL" column is what `semantic_model.yaml` ships as the
verified-query SQL — it's what the model should produce when the
natural-language question hits. The "Teaches" column explains what each
query was designed to anchor in the model, so when the live Analyst produces
a different SQL Paul can match it back to the synonym list that needs
adjusting.

Each query targets `GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT` or
`GKTUITION_TUTOR.CORTEX.EXAM_PARTS_BY_TUTORIAL`. Both views are defined in
`views.sql`.

---

## 1 — Integration by parts on P1, last five years

**Question (natural language):**
> How often has integration by parts appeared on Paper 1 in the last five years?

**Expected SQL:**

```sql
SELECT COUNT(*) AS parts_count
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE topic_strand = 'integration'
  AND paper = 1
  AND sitting = 'main'
  AND year BETWEEN 2021 AND 2025
  AND (
        topic_raw     ILIKE '%integration by parts%'
     OR solution_text ILIKE '%integration by parts%'
  );
```

**Teaches:** the model how to combine a strand filter (`topic_strand`) with
a sub-technique filter (substring match on `topic_raw` and `solution_text`),
and how to interpret "the last five years" as `BETWEEN 2021 AND 2025`. The
hybrid filter matters because the LCHL strand bucket is `integration`, not
`integration-by-parts` — the fine-grained technique lives in the free-form
topic line.

---

## 2 — Discriminant questions on P1, year by year

**Question (natural language):**
> How many discriminant questions appear on Paper 1 each year?

**Expected SQL:**

```sql
SELECT year,
       COUNT(*) AS parts_count
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE paper = 1
  AND sitting = 'main'
  AND (
        topic_raw ILIKE '%discriminant%'
     OR topic_raw ILIKE '%nature of roots%'
     OR topic_raw ILIKE '%nature of the roots%'
  )
GROUP BY year
ORDER BY year;
```

**Teaches:** the model to recognise "discriminant" as a teacher synonym for
"nature of roots" — both phrases refer to the same algebraic test
(`b² − 4ac`). Both forms must be matched because the `topic_raw` strings
that Paul wrote vary across years. If a future query "nature of roots
questions" produces SQL with only the first ILIKE branch, the synonym list
needs `"nature of roots"` and `"nature of the roots"` added explicitly to
`topic_strand`'s synonyms (they're already there).

---

## 3 — Differentiation trend, P1

**Question (natural language):**
> What's the year-over-year trend of differentiation parts on Paper 1?

**Expected SQL:**

```sql
SELECT year,
       COUNT(*) AS parts_count
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE topic_strand = 'differentiation'
  AND paper = 1
  AND sitting = 'main'
GROUP BY year
ORDER BY year;
```

**Teaches:** the canonical "trend by year" pattern — group by year, order by
year ascending so the result reads as a time series. The trend file
documents the answer (6, 8, 8, 4, 6, 9, 14, 13, 12, 16, 14 — climbing
steeply since 2021); a working Analyst should reproduce these counts within
±1 (per Agent 02's "1,213 vs 1,212" reconciliation note).

---

## 4 — Strand growth on P2, since 2020

**Question (natural language):**
> Which Paper 2 strands have grown since 2020?

**Expected SQL:**

```sql
WITH recent AS (
    SELECT topic_strand, COUNT(*) AS recent_parts
    FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
    WHERE paper = 2 AND sitting = 'main' AND year BETWEEN 2020 AND 2025
    GROUP BY topic_strand
),
prior AS (
    SELECT topic_strand, COUNT(*) AS prior_parts
    FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
    WHERE paper = 2 AND sitting = 'main' AND year BETWEEN 2015 AND 2019
    GROUP BY topic_strand
)
SELECT COALESCE(r.topic_strand, p.topic_strand) AS topic_strand,
       COALESCE(p.prior_parts, 0)              AS prior_2015_2019,
       COALESCE(r.recent_parts, 0)             AS recent_2020_2025,
       COALESCE(r.recent_parts, 0)
          - COALESCE(p.prior_parts, 0)          AS delta
FROM recent r
FULL OUTER JOIN prior p USING (topic_strand)
ORDER BY delta DESC;
```

**Teaches:** the "before / after / delta" template — two CTEs windowed on
disjoint year ranges, FULL OUTER JOIN so a strand that appears in only one
era still surfaces with a zero on the other side. Trends file claims
Probability and Statistics grew substantially in the 2020–2025 window
(Probability hit 10 and 11 parts in 2024/2025 respectively vs an average of
6 before); this query should surface that.

---

## 5 — Average mark allocation, nature-of-roots questions

**Question (natural language):**
> What's the average mark allocation for a 'nature of roots' question?

**Expected SQL:**

```sql
SELECT AVG(marks) AS avg_marks_per_part,
       COUNT(*)   AS parts_count
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE topic_raw ILIKE '%nature of%root%'
   OR topic_raw ILIKE '%discriminant%';
```

**Teaches:** the model to use the `avg_marks_per_part` measure on a
substring-filtered subset (not on `topic_strand`, which is too coarse), and
to emit a parallel `COUNT(*)` so the answer carries its own sample size. The
average-marks measure is one of the most commonly-asked patterns in the
trends file and the synonym list explicitly covers "average marks", "marks
per part", and "mean marks".

---

## 6 — Most-cited tutorial across all P1 papers

**Question (natural language):**
> Which single tutorial is cited most often on Paper 1 across all years?

**Expected SQL:**

```sql
SELECT tutorial_slug,
       COUNT(*) AS citation_count
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_BY_TUTORIAL
WHERE paper = 1
  AND sitting = 'main'
GROUP BY tutorial_slug
ORDER BY citation_count DESC
LIMIT 10;
```

**Teaches:** the model to switch to the second table
(`EXAM_PARTS_BY_TUTORIAL`) when the question grain is "per tutorial". The
trends file's answer is `indices-logs-5-unknown-in-power-natural-log` with
31 citations across the 11 main P1 sittings. If the model produces a SQL
that GROUPs on `EXAM_PARTS_FLAT` and tries to FLATTEN the array inline, the
synonym list for `tutorial_slug` needs strengthening so the model picks the
right table by default.

---

## 7 — Deferred vs main, strand mix, P2

**Question (natural language):**
> How does the strand mix differ between main and deferred sittings on Paper 2?

**Expected SQL:**

```sql
SELECT topic_strand,
       COUNT_IF(sitting = 'main') AS main_parts,
       COUNT_IF(sitting = 'df')   AS deferred_parts
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE paper = 2
GROUP BY topic_strand
ORDER BY main_parts DESC;
```

**Teaches:** the "compared to" / "vs" pattern using `COUNT_IF` rather than
two CTEs — cheaper than the FULL OUTER JOIN form, fine when both populations
share the same dimension. The `sitting` dimension's synonyms include "main
sitting", "deferred sitting", "DF", "df", "supplementary exam" — any of
these should land on this query.

---

## 8 — P1 vs P2 part counts, year by year

**Question (natural language):**
> How does the Paper 1 vs Paper 2 part count compare year by year?

**Expected SQL:**

```sql
SELECT year,
       COUNT_IF(paper = 1) AS paper_1_parts,
       COUNT_IF(paper = 2) AS paper_2_parts
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE sitting = 'main'
GROUP BY year
ORDER BY year;
```

**Teaches:** another "compared-to" pattern, this time with the dimension
being `paper`. Combined with query 4, the model learns that "compared to"
phrasing should prefer pivot-style output (two columns) over long-form
output (one row per (year, paper) combination) when the comparison axis has
exactly two values. The format-shift signal from the trends file is
embedded in this query — pre-2021 both papers had ~35 parts; from 2021
onwards, ~45.

---

## 9 — Ten-year average parts per strand, P1

**Question (natural language):**
> What's the 10-year average number of parts per strand on Paper 1?

**Expected SQL:**

```sql
SELECT topic_strand,
       COUNT(*)                                AS total_parts,
       COUNT(DISTINCT year)                    AS years_appeared,
       ROUND(COUNT(*) * 1.0
             / COUNT(DISTINCT year), 1)        AS avg_parts_per_year_appeared
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE paper = 1
  AND sitting = 'main'
  AND year BETWEEN 2015 AND 2025
GROUP BY topic_strand
ORDER BY total_parts DESC;
```

**Teaches:** the "average per year **a strand appeared**" pattern, which is
the form the trends file uses for its headline tables. Crucially, this is
*not* `AVG()` of parts_count — that would average across only the years a
strand showed up. The denominator `COUNT(DISTINCT year)` does the right
thing: Algebra appears in 11 years and has 98 parts ⟹ 8.9 parts/year.
Differentiation appears in 11 years and has 115 parts ⟹ 10.5 parts/year.
Both numbers reproduce the trends file's headline averages exactly.

---

## 10 — Multi-filter: differentiation, P1, since 2020, ≥10 marks

**Question (natural language):**
> How many differentiation parts on Paper 1 since 2020 are worth 10 marks or more?

**Expected SQL:**

```sql
SELECT year,
       COUNT(*) AS heavy_diff_parts
FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
WHERE topic_strand = 'differentiation'
  AND paper = 1
  AND sitting = 'main'
  AND year >= 2020
  AND marks >= 10
GROUP BY year
ORDER BY year;
```

**Teaches:** four filters in one query, with two of them numeric inequalities.
This is the hardest pattern for text-to-SQL to nail consistently: it's easy
to drop a filter or misinterpret "≥10 marks" as `= 10`. If the Analyst
produces SQL with the wrong inequality direction, the synonym list for the
`marks` dimension may need a "worth at least N marks" entry — but more
likely the model is being asked to reason about inequalities and just needs
the verified-query exemplar to anchor on.

---

## How to use these in production

1. **Drift detection.** If the live Analyst generates SQL that differs from
   the Expected SQL above by more than a syntactic reshuffle, that's a
   signal to tighten the synonym list or add another verified query. The
   exact strings in `topic_strand`'s synonym list are deliberately
   comprehensive to bias the model toward these forms.

2. **Eval anchors.** All ten questions should appear in
   `RAW.EVAL_GOLDEN_SET` (Agent 05's deliverable) with `route =
   "analytical"` and the Expected SQL as the gold answer. This is the
   smallest-effort way to keep the Analyst honest as the synonym list
   evolves.

3. **Re-checking after schema changes.** Any change to the columns surfaced
   by `EXAM_PARTS_FLAT` or `EXAM_PARTS_BY_TUTORIAL` requires re-running each
   of these ten queries directly against the warehouse to confirm the SQL
   still executes without error. The synonym layer is the brittle one; the
   schema layer is the load-bearing one.

4. **Coverage gaps to flag.** The current ten queries do not exercise:
   - Section A vs Section B splits (mentioned in the trends file but a low-priority pattern).
   - `is_load_bearing` filter (relies on Agent 02's text-tag flagging fidelity).
   - The `tutorial_strand` dimension on `EXAM_PARTS_BY_TUTORIAL` (one-step
     more general than `tutorial_slug`).

   Add verified queries for these only if real student queries demand them
   — adding speculative verified queries dilutes the signal the model uses
   to pick the right pattern.
