# Cortex Search scoring report

**Run timestamp:** 2026-05-26T13:07:46
**Rows scored:** 3194  (errors during query: 0)
**Source filter:** full eval set  ·  top-K = 5

## Overall

- **precision@1**: 0.911
- **recall@5**: 0.984
- **MRR**: 0.942

## By source

| source | n | precision@1 | recall@5 | MRR | errors |
|---|---:|---:|---:|---:|---:|
| phrasings | 1511 | 0.822 | 0.966 | 0.884 | 0 |
| solution_cross_ref | 1683 | 0.990 | 1.000 | 0.994 | 0 |

## By difficulty tier

| difficulty | n | precision@1 | recall@5 | MRR |
|---|---:|---:|---:|---:|
| auto-easy | 1530 | 0.839 | 0.969 | 0.894 |
| auto-medium | 782 | 0.986 | 0.997 | 0.992 |
| auto-hard | 882 | 0.969 | 0.998 | 0.980 |

## By topic (weakest first)

| topic | n | precision@1 | recall@5 | MRR |
|---|---:|---:|---:|---:|
| **function composition** — compute `f(g(x))` and `g(f(x))` separately, then compare. (These two functions happen to be **inverses** of each other, so both compositions return `x` — a special case that the question is implicitly testing your awareness of.) | 5 | 0.400 | 1.000 | 0.600 |
| **prescribed double-angle proof** — derive `sin 2A = 2 sin A cos A` from the compound angle formula by substituting `B = A` | 5 | 0.400 | 1.000 | 0.700 |
| exponential equation that converts into the quadratic from part (i) by the substitution `y = 4ˣ`. The keyword **"hence"** is the load-bearing hint — re-use the result of (i) | 6 | 0.500 | 1.000 | 0.625 |
| de Moivre identity proof — expand `(cos θ + i sin θ)²` two different ways, equate real parts | 5 | 0.600 | 1.000 | 0.700 |
| coordinate-geometry-line | 97 | 0.649 | 0.990 | 0.810 |
| algebra | 186 | 0.758 | 0.919 | 0.825 |
| complex-numbers | 57 | 0.772 | 0.930 | 0.837 |
| trigonometry | 351 | 0.803 | 0.977 | 0.874 |
| indices-and-logs | 87 | 0.805 | 0.943 | 0.858 |
| statistics | 16 | 0.812 | 0.938 | 0.875 |
| synthetic-geometry | 139 | 0.813 | 0.964 | 0.878 |
| coordinate-geometry-circle | 78 | 0.846 | 0.936 | 0.881 |
| area-volume-measurement | 31 | 0.871 | 0.903 | 0.887 |
| integration | 65 | 0.877 | 0.969 | 0.918 |
| financial-maths | 57 | 0.877 | 1.000 | 0.936 |
| differentiation | 111 | 0.883 | 1.000 | 0.933 |
| number-theory | 51 | 0.902 | 0.980 | 0.941 |
| sequences-series-patterns-limits | 69 | 0.913 | 1.000 | 0.952 |
| functions-and-graphs | 66 | 0.955 | 0.985 | 0.966 |
| probability | 48 | 0.958 | 1.000 | 0.976 |
| **point of inflection of a cubic** — the `x`-coordinate where `f''(x) = 0`. Then verify the resulting `(x, y)` point lies on `g(x)` by substitution | 5 | 1.000 | 1.000 | 1.000 |
| **substitute `t = 0`** into the model | 8 | 1.000 | 1.000 | 1.000 |
| **square roots** of a complex number using De Moivre's Theorem — a **multi-valued** root extraction. Two roots because the power is `1/2` | 9 | 1.000 | 1.000 | 1.000 |
| evaluate a definite integral with a quadratic integrand. Recover the classic pyramid-volume formula `V = (1/3) × base × height` | 5 | 1.000 | 1.000 | 1.000 |
| reading slope, function composition, and inverse function — all directly from a graph | 5 | 1.000 | 1.000 | 1.000 |

## Sample failures (precision@1 == 0, expected absent from top-5)

| eval_id | source | expected | top-1 returned |
|---|---|---|---|
| `phr_algebra-10-generating-a-cubic-equation-given-the-roots_007` | phrasings | `algebra-10-generating-a-cubic-equation-given-the-roots` | `integration-12-area-curve-x-axis` |
| `phr_algebra-10-generating-a-cubic-equation-given-the-roots_010` | phrasings | `algebra-10-generating-a-cubic-equation-given-the-roots` | `complex-numbers-2-addition-subtraction-multiplication` |
| `phr_algebra-16-modulus-graphs_007` | phrasings | `algebra-16-modulus-graphs` | `algebra-19-simultaneous-equations-by-substitution` |
| `phr_algebra-19-simultaneous-equations-by-substitution_004` | phrasings | `algebra-19-simultaneous-equations-by-substitution` | `the-circle-4-intersection-of-line-and-circle` |
| `phr_avm-1-1-jc-revision_008` | phrasings | `avm-1-1-jc-revision` | `avm-1-3-trapezoidal-rule` |
| `phr_avm-1-1-jc-revision_009` | phrasings | `avm-1-1-jc-revision` | `avm-1-2-unit-conversion` |
| `phr_complex-numbers-10-introduction-to-polar-form_005` | phrasings | `complex-numbers-10-introduction-to-polar-form` | `geometry-1-7-proof-of-theorem-4` |
| `phr_complex-numbers-10-introduction-to-polar-form_007` | phrasings | `complex-numbers-10-introduction-to-polar-form` | `statistics-11-z-scores-3` |
| `phr_complex-numbers-4-argand-plane-and-modulus_005` | phrasings | `complex-numbers-4-argand-plane-and-modulus` | `the-line-4-area-of-triangle` |
| `phr_algebra-13-long-division_009` | phrasings | `algebra-13-long-division` | `algebra-19-simultaneous-equations-by-substitution` |
| `phr_differentiation-1-introduction_001` | phrasings | `differentiation-1-introduction` | `integration-2-integrating-1-over-x` |
| `phr_differentiation-1-introduction_006` | phrasings | `differentiation-1-introduction` | `indices-logs-6-quadratic-equations-1` |
| `phr_differentiation-14-slopes_002` | phrasings | `differentiation-14-slopes` | `the-circle-7-tangent-at-point-or-parallel-to-line` |
| `phr_financial-maths-4-rate-conversion_009` | phrasings | `financial-maths-4-rate-conversion` | `indices-logs-5-unknown-in-power-natural-log` |
| `phr_functions-graphs-10-limits_007` | phrasings | `functions-graphs-10-limits` | `algebra-19-simultaneous-equations-by-substitution` |
| `phr_functions-graphs-3-vertex-form-completing-the-square_004` | phrasings | `functions-graphs-3-vertex-form-completing-the-square` | `algebra-2-factorising-quadratics` |
| `phr_functions-graphs-5-injective-functions_003` | phrasings | `functions-graphs-5-injective-functions` | `functions-graphs-6-surjective-functions` |
| `phr_geometry-1-1-axioms-theorems-corollaries_007` | phrasings | `geometry-1-1-axioms-theorems-corollaries` | `geometry-1-4-proof-of-theorem-6` |
| `phr_geometry-1-11-proof-of-theorem-19_003` | phrasings | `geometry-1-11-proof-of-theorem-19` | `geometry-1-1-axioms-theorems-corollaries` |
| `phr_geometry-1-18-transformations_004` | phrasings | `geometry-1-18-transformations` | `avm-1-7-area-between-function-and-y-axis` |
| `phr_geometry-1-18-transformations_005` | phrasings | `geometry-1-18-transformations` | `algebra-16-modulus-graphs` |
| `phr_geometry-1-18-transformations_008` | phrasings | `geometry-1-18-transformations` | `complex-numbers-7-rotations` |
| `phr_geometry-1-2-constructions-overview_007` | phrasings | `geometry-1-2-constructions-overview` | `the-circle-7-tangent-at-point-or-parallel-to-line` |
| `phr_indices-logs-1-jc-revision_010` | phrasings | `indices-logs-1-jc-revision` | `avm-1-2-unit-conversion` |
| `phr_indices-logs-6-quadratic-equations-1_008` | phrasings | `indices-logs-6-quadratic-equations-1` | `indices-logs-7-quadratic-equations-2` |
| `phr_integration-12-area-curve-x-axis_007` | phrasings | `integration-12-area-curve-x-axis` | `algebra-10-generating-a-cubic-equation-given-the-roots` |
| `phr_integration-6-trigonometry-2_005` | phrasings | `integration-6-trigonometry-2` | `trigonometry-2-5-coefficient-in-front-of-the-angle` |
| `phr_number-theory-5-construct-root-3_009` | phrasings | `number-theory-5-construct-root-3` | `geometry-1-10-proof-of-theorem-14` |
| `phr_sequences-series-2-arithmetic-sequences-2_006` | phrasings | `sequences-series-2-arithmetic-sequences-2` | `indices-logs-3-rules-of-logs-2` |
| `phr_sequences-series-7-geometric-sequences-3_007` | phrasings | `sequences-series-7-geometric-sequences-3` | `algebra-5-fractions-part-2` |

