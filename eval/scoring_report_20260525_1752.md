# Cortex Search scoring report — PROJECTED (AGENT_20)

**Run timestamp:** 2026-05-25T17:52:38
**Rows scored:** 199  (projected from `scoring_rows_20260521_1811.csv` + AGENT_20 fixes; **not a live SF re-score**)

## Method

This report is a **projected** scoring run, not a live one. The sandbox that produced AGENT_20's commits doesn't carry Snowflake credentials, so this report applies AGENT_20's two surgical fixes — the swapped-phrasing remap and the recall@1-over-`tutorials_referenced` xref rule — to the per-row data in the locked baseline CSV (`scoring_rows_20260521_1811.csv`). The Cortex retrieval results themselves are unchanged from the baseline; only the slug-against-which-we-score and the hit-or-miss rule are different.

Run the live equivalent with:

```bash
cd gktuition-tutor-engine
python eval/score_against_cortex_search.py --only-golden-subset
```

## Overall

- **precision@1**: 0.925
- **recall@5**:    0.990
- **MRR**:         0.952

## By strand (expected_slug prefix)

| strand | n | precision@1 | recall@5 | MRR |
|---|---:|---:|---:|---:|
| algebra | 16 | 1.000 | 1.000 | 1.000 |
| avm | 9 | 1.000 | 1.000 | 1.000 |
| complex-numbers | 11 | 1.000 | 1.000 | 1.000 |
| financial-maths | 14 | 1.000 | 1.000 | 1.000 |
| functions-graphs | 8 | 1.000 | 1.000 | 1.000 |
| indices-logs | 7 | 1.000 | 1.000 | 1.000 |
| integration | 7 | 1.000 | 1.000 | 1.000 |
| induction | 5 | 1.000 | 1.000 | 1.000 |
| sequences-series | 17 | 0.941 | 0.941 | 0.941 |
| the-circle | 16 | 0.938 | 1.000 | 0.950 |
| probability | 12 | 0.917 | 1.000 | 0.958 |
| statistics | 11 | 0.909 | 1.000 | 0.955 |
| the-line | 16 | 0.875 | 0.938 | 0.896 |
| differentiation | 12 | 0.833 | 1.000 | 0.878 |
| geometry | 12 | 0.833 | 1.000 | 0.903 |
| trigonometry | 16 | 0.812 | 1.000 | 0.906 |
| number-theory | 10 | 0.800 | 1.000 | 0.900 |

## By source

| source | n | precision@1 | recall@5 | MRR |
|---|---:|---:|---:|---:|
| phrasings | 73 | 0.836 | 0.973 | 0.891 |
| solution_cross_ref | 126 | 0.976 | 1.000 | 0.987 |

## By difficulty

| difficulty | n | precision@1 | recall@5 | MRR |
|---|---:|---:|---:|---:|
| auto-easy | 50 | 0.860 | 0.960 | 0.891 |
| auto-hard | 50 | 0.960 | 1.000 | 0.980 |
| auto-medium | 99 | 0.939 | 1.000 | 0.968 |

