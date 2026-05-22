# Cortex Search scoring report

**Run timestamp:** 2026-05-21T18:11:40
**Rows scored:** 200  (errors during query: 0)
**Source filter:** golden subset only  ·  top-K = 5

## Overall

- **precision@1**: 0.710
- **recall@5**: 0.985
- **MRR**: 0.835

## By source

| source | n | precision@1 | recall@5 | MRR | errors |
|---|---:|---:|---:|---:|---:|
| phrasings | 74 | 0.811 | 0.959 | 0.873 | 0 |
| solution_cross_ref | 126 | 0.651 | 1.000 | 0.813 | 0 |

## By difficulty tier

| difficulty | n | precision@1 | recall@5 | MRR |
|---|---:|---:|---:|---:|
| auto-easy | 50 | 0.840 | 0.960 | 0.881 |
| auto-medium | 100 | 0.680 | 0.990 | 0.833 |
| auto-hard | 50 | 0.640 | 1.000 | 0.792 |

## By topic (weakest first)

| topic | n | precision@1 | recall@5 | MRR |
|---|---:|---:|---:|---:|
| algebra | 12 | 0.500 | 0.833 | 0.628 |
| trigonometry | 8 | 0.750 | 1.000 | 0.875 |
| synthetic-geometry | 5 | 0.800 | 1.000 | 0.867 |
| number-theory | 5 | 0.800 | 1.000 | 0.900 |
| coordinate-geometry-line | 7 | 0.857 | 1.000 | 0.929 |
| coordinate-geometry-circle | 8 | 0.875 | 1.000 | 0.900 |
| financial-maths | 8 | 1.000 | 1.000 | 1.000 |

## Sample failures (precision@1 == 0, expected absent from top-5)

| eval_id | source | expected | top-1 returned |
|---|---|---|---|
| `phr_algebra-13-long-division_009` | phrasings | `algebra-13-long-division` | `algebra-19-simultaneous-equations-by-substitution` |
| `phr_sequences-series-patterns-1-quadratic-patterns_002` | phrasings | `sequences-series-patterns-1-quadratic-patterns` | `algebra-14-manipulation-of-formula` |
| `phr_the-line-1-jc-revision_003` | phrasings | `the-line-1-jc-revision` | `complex-numbers-2-addition-subtraction-multiplication` |

