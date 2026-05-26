# Differentiation — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Differentiation before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Differentiation deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Differentiation appears in 11/11 years on Paper 1 — the single most-tested strand in the entire corpus.** Average ≈ 10.5 parts per paper. Total: **115 P1 parts**, more than any other strand.
- **Recent surge:** 2021 → 14, 2022 → 13, 2023 → 12, **2024 → 16, 2025 → 14.** Pre-2021 average was 8. Plan as if 2026 is in the 13–16 range.
- **Section B heavy.** 72 of 115 parts live in Section B contexts — Diff is the spine of every applied optimisation, related-rates, and curve-sketching question. Section A handles the mechanical pieces (slope at a point, simple derivatives).
- **Cross-paper reach.** Rate problems cross onto Paper 2 — 8 P2 parts in 2016, 2017, 2018, 2020, 2021, 2024. Diff also fires inside Algebra (`f'(x) = 0` reduces to quadratic/cubic), Functions & Graphs (turning points → curve sketches), Integration (antiderivative reversal), and AVM (cone/sphere geometry for rate problems).

**The takeaway.** Diff isn't a topic; it's a workload. Roughly 1 in 4 marks on Paper 1 lives here. The Section B Q9 / Q10 calculus question is reliably worth 50+ marks and almost always involves either Diff 15's turning-point recipe or Diff 20's rate problem.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Turning-points + max/min recipe** | 20 min | diff-15 — 24 P1 citations; every year; the highest-ROI single tutorial |
| **Chain rule (bracket-to-the-power)** | 15 min | diff-8 — 16 P1 citations; tested 2019, 2021, 2022, 2023, 2024 |
| **Rate problems (cones, spheres, ladders)** | 15 min | diff-20 — 10 P1 citations; tested 2017, 2020, 2022, 2023, 2025 — the hardest application |
| **Rates of change (velocity / acceleration)** | 10 min | diff-18 — 16 P1 citations; classic Section B physics-flavoured part |
| **Slopes + tangent / normal equations** | 10 min | diff-14 + diff-19 — 12 P1 citations; bread-and-butter Section A |
| **Quick-fire:** product, quotient, implicit, e^x, ln x | 15 min | diff-5/6/7/9/10 — formula sheet page 25 |

---

## 📊 Top differentiation tutorials by exam frequency (P1 main, 11 years)

| Rank | Tutorial | P1 citations | What it tests |
|---|---|---|---|
| 1 | `differentiation-1` Introduction | **30** | The power rule itself. Every paper. |
| 2 | `differentiation-15` Turning Points / Max-Min | **24** | The 5-step recipe; second-derivative test. |
| 3 | `differentiation-5` Exponentials | **17** | `d/dx[eˣ] = eˣ` plus "multiply by derivative of the angle". |
| 4 | `differentiation-8` Chain Rule | **16** | Bracket-to-the-power method. |
| 5 | `differentiation-18` Rates of Change | **16** | velocity = `ds/dt`, acceleration = `d²s/dt²`. |
| 6 | `differentiation-14` Slopes | **12** | Tangent slope = `f'(a)`; cross-link to coordinate-geometry p.18. |
| 7 | `differentiation-20` Rate Problems | **10** | Multi-variable related rates — the hardest single application. |
| 8 | `differentiation-13` Second Derivative | **9** | Concavity, max/min test, inflection setup. |
| 9 | `differentiation-3` Trig Derivatives | **9** | `sin → cos → −sin → ...` cycle. |

> **Read this as:** tutorials 1, 2, 8, 15, 18, 20 alone account for >100 cited appearances. Nothing else is close.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 25** | `d/dx[xⁿ] = n·x^(n−1)` | Power rule (with negative + fractional powers after rewriting). |
| **p. 25** | `d/dx[sin x] = cos x`, `d/dx[cos x] = −sin x`, `d/dx[tan x] = sec²x` | Trig derivatives. Multiply by derivative of the angle (PTA). |
| **p. 25** | `d/dx[eˣ] = eˣ`, `d/dx[ln x] = 1/x`, `d/dx[aˣ] = aˣ · ln a` | Exponential / log derivatives. |
| **p. 25** | Product rule `(uv)' = u'v + uv'` and quotient rule `(u/v)' = (vu' − uv')/v²` | Product + quotient (page 25 lists both). |
| **p. 21** | Rules of indices | Rewrite `1/xⁿ` as `x^(−n)`, `√x` as `x^(1/2)` BEFORE differentiating. |
| **p. 10** | Volume / surface formulas | Sphere, cone, cylinder — for rate problems. |

> **🎯 Do NOT use page 25's chain-rule formula.** Paul's [00:04] directive in diff-8: *"if you go to page 25 in your maths tables you will notice that there is a formula for the chain rule there. However you're better off if you just watch me doing this one."* Use the bracket-to-the-power method (technique #2 below).

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. The 5-step turning-point recipe (diff-15)

1. Differentiate to get `f'(x)`.
2. Set `f'(x) = 0`. Solve for `x` (usually a quadratic or cubic).
3. For each x-solution, **sub into the ORIGINAL `f(x)`** to get the y-coordinate. Write the point `(x₀, y₀)`.
4. Differentiate again to get `f''(x)`.
5. Sub each x-value into `f''(x)`. **`f''(x) > 0` ⇒ MINIMUM. `f''(x) < 0` ⇒ MAXIMUM.**

### 2. The bracket-to-the-power chain rule (diff-8)

For `y = [bracket]ⁿ`:
```
dy/dx = n · [bracket]^(n−1) · (derivative of the bracket)
```
For square roots, rewrite as a `^(1/2)` power first; for `1/(bracket)ⁿ` rewrite as `(bracket)^(−n)`. **Always** carry the rewrite as a visible line of working.

### 3. The reciprocal trick for rate problems (diff-20)

You're given one rate (`dV/dt`) and asked for another (`dR/dt`). The geometric formula gives `V = f(R)`, so you can compute `dV/dR` directly. The chain rule needs `dR/dV`, so:
```
dR/dV = 1 / (dV/dR)
```
Then `dR/dt = (dR/dV) · (dV/dt)`. For 3-variable shapes (cone with `V`, `R`, `h`), use **similar triangles** to eliminate one variable BEFORE differentiating.

### 4. Velocity = first derivative, acceleration = second derivative

`v(t) = ds/dt`, `a(t) = dv/dt = d²s/dt²`. Same for vector phrasing (displacement → velocity → acceleration). Particle at rest ⇔ `v(t) = 0`.

---

## 🚨 LOAD-BEARING — the five things that win or lose the differentiation question

### 1. Sub turning-point `x` into the ORIGINAL `f(x)`, NOT into `f'(x)` (diff-15)

The single most-flagged deduction across the corpus.

> 🚨 **Paul, diff-15 [07:02]:** *"Often a mistake people make is they sub it into the first derivative. You do not want to sub it into the first derivative. That's the slope. You want to sub the x value into the original function f of x. It's really really important."*
>
> Recurs ~10/11 years. Trivial fix; catastrophic loss if you don't.

### 2. Do the second-derivative test EVEN IF the question doesn't ask which is max and which is min (diff-15)

> 🚨 **Paul, diff-15 [13:13]:** *"Even though the question doesn't explicitly say it in the Leaving Cert, even if it doesn't explicitly say it, just to cover yourself and ensure you get the full marks…"*
>
> The marking scheme rewards mathematical verification, not visual inspection. Recurs every year a max/min question is asked.

### 3. Chain rule via the bracket method — NOT page 25 (diff-8)

| Form | Method |
|---|---|
| `[bracket]ⁿ` | `n · [bracket]^(n−1) · (derivative of bracket)` |
| `1/[bracket]ⁿ` | Rewrite as `[bracket]^(−n)` first, then bracket method |
| `√[bracket]` | Rewrite as `[bracket]^(1/2)` first, then bracket method |

> 🚨 **Paul's directive at diff-8 [00:04]:** the page-25 formula `(dy/dx) = (dy/du)·(du/dx)` introduces a `u`-substitution that students conflate with the `u, v` substitution from product/quotient rule. **Use the bracket method.** Tested 2019, 2021, 2022, 2023, 2024.

### 4. Related rates: substitute the geometric constraint BEFORE differentiating (diff-20)

For cone-style problems where `R` and `h` are linked by similar triangles (e.g. `h = 5R`), substitute the relationship into `V = (1/3)πR²h` to get `V` as a function of a single variable BEFORE you differentiate. If you differentiate first and try to substitute later, the bookkeeping collapses.

> 🚨 The reciprocal trick `dR/dV = 1/(dV/dR)` is the load-bearing skill. Tested 2017, 2020, 2022, 2023, 2025.

### 5. Reporting a signed rate of change

A signed derivative like `dR/dt = −1/(4π)` means **radius decreasing at `1/(4π)`**. The marking scheme accepts both phrasings, but the question wording chooses. "Find the rate of decrease" ⇒ report the magnitude with the word "decreasing"; "find `dR/dt`" ⇒ keep the negative sign.

> 🚨 **For "deceleration" specifically (diff-18 [06:52]):** *"acceleration and deceleration refer to the same thing — it's just that one of them is positive and one of them is negative."* Report the magnitude when the question asks for deceleration. Tested 2020, 2023, 2024 P1.

---

## 🎯 The 8 techniques you must execute without thinking

1. **Power rule** with negative/fractional powers — always rewrite `1/xⁿ` as `x^(−n)` and `√x` as `x^(1/2)` BEFORE differentiating. Carry the rewrite as a visible line. *"Always consider should I simplify this before I differentiate"* (diff-1 [142]).
2. **Product rule** `(uv)' = u'v + uv'`. Commutative — order doesn't matter.
3. **Quotient rule** `(u/v)' = (vu' − uv')/v²`. **NOT commutative** — `v·du/dx` comes FIRST in the numerator. Swapping the order flips the sign of your answer.
4. **Implicit differentiation** — differentiate term-by-term wrt `x`; every `d/dx[yⁿ]` becomes `n·y^(n−1)·dy/dx`. Then collect `dy/dx` terms on one side, factor, divide.
5. **Slope of a tangent at `(a, b)`** — `f'(a)` is the slope. Equation via `y − b = f'(a)·(x − a)`.
6. **Normal line** — perpendicular to tangent, so slope is `−1/f'(a)`.
7. **Increasing / decreasing intervals** — solve `f'(x) > 0` for increasing, `f'(x) < 0` for decreasing. Sign-analysis on the factorised `f'(x)`.
8. **Point of inflection** — solve `f''(x) = 0` AND verify concavity changes sign across that x. Concavity test: `f''` switches from `+` to `−` (or vice versa).

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Subbing turning-point `x` into `f'(x)` instead of `f(x)` | Sub into ORIGINAL function for the y-coordinate |
| Skipping the second-derivative test when not explicitly asked | Always include step 5; the MS expects it |
| Using page-25 chain-rule formula and confusing `u` with product-rule `u` | Use the bracket method |
| Quotient-rule numerator order reversed → sign flip | `v·du/dx` first, `u·dv/dx` second |
| Forgetting brackets in chain rule (writing `2x³` instead of `2·(x+1)³`) | Always keep the bracket visible |
| Differentiating `1/x²` directly instead of rewriting as `x^(−2)` | Rewrite first; differentiate second |
| Implicit differentiation: forgetting `·dy/dx` on the y-term derivatives | Every `y` derivative carries a `dy/dx` factor |
| Rate problem: differentiating before substituting the constraint (`h = 5R`) | Substitute first; differentiate second |
| Reporting `dR/dt = −1/(4π)` when the question asks for "rate of decrease" | Drop the minus sign and say "decreasing" |
| Forgetting units (m/s, m/s², m³/min) | The MS deducts marks for missing units |
| `f'(x)` has a denominator — students argue from the denominator about zero | A fraction is zero iff its NUMERATOR is zero (diff-15 [29:38]) |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Find the slope of the tangent at x = a"* | `f'(a)` is the slope. One line. |
| *"Find the equation of the tangent at (a, b)"* | Slope = `f'(a)`; `y − b = f'(a)(x − a)`. |
| *"Find the equation of the normal at (a, b)"* | Slope = `−1/f'(a)`; same point-slope form. |
| *"Find the turning points / coordinates of the max and min"* | Full 5-step recipe. Don't skip step 5. |
| *"Show that f has no turning points"* | Show `f'(x) = 0` has no solutions. Argue from the numerator. |
| *"Find the values of x for which f is increasing"* | Solve `f'(x) > 0`. Factor and sign-analyse. |
| *"Find the point of inflection"* | `f''(x) = 0`; verify concavity changes sign. |
| *"Find the value of t when the particle is at rest"* | `v(t) = 0`. |
| *"Find the maximum value of …"* | Optimisation — set up the constraint, reduce to one variable, then 5-step. |
| *"At what rate is X changing when …"* | Rate problem — diff-20 reciprocal trick + chain rule. |
| *"Hence find …"* | Use the previous part's result. Don't re-derive. |

---

## 💡 Three exam-day tips that move the needle

1. **Always show `f'(x) = ...` on its own line before evaluating.** Three lines: derivative formula, derivative, sub-in. Even if your arithmetic is wrong, the first two lines earn method marks. Skipping to the answer = 0 marks if wrong.

2. **For rate problems, draw the figure first and label every variable with its units.** Five minutes spent labelling saves twenty minutes of confusion in the algebra. Annotate `dV/dt`, `dR/dt` and which one is given vs sought BEFORE picking up the chain rule.

3. **The Section B calculus question is worth 50 marks — pace yourself.** Section A questions average ~6 min; Section B sub-parts average ~3–5 min. The full Q9/Q10 calculus problem deserves 25–30 min. If a single sub-part (usually the rate problem) is taking >10 min, mark it and return at the end.

---

## 🔗 Cross-strand connections (where else differentiation fires)

- **Diff ↔ Algebra** — `f'(x) = 0` reduces to a quadratic or cubic; the algebra is what wins or loses the question. Factor Theorem and long division show up inside max/min cubics.
- **Diff ↔ Functions & Graphs** — turning points + inflection + sign-analysis = curve sketch. Tested 2017, 2019, 2024.
- **Diff ↔ Integration** — antiderivative reversal; rate-of-change questions sometimes ask you to integrate `v(t)` back to displacement.
- **Diff ↔ Sequences & Series** — find the maximum of a discrete sequence by treating it as a continuous function, differentiating, and checking the integer values either side.
- **Diff ↔ Indices & Logs** — log differentiation; "take ln of both sides" before differentiating exotic forms.
- **Diff ↔ AVM (Paper 2)** — cone/sphere formulas (page 10) drive every related-rates problem.
- **Diff ↔ Trig 2/3/4** — compound-angle and double-angle identities sometimes need to be applied BEFORE chain-rule differentiation.
- **Diff ↔ Paper 2 rate problems** — 8 P2 parts across 2016/17/18/20/21/24. Same techniques; different paper.

> Differentiation is the spine of Paper 1 Section B. Even when the wording is "physics" or "optimisation", the last 30 seconds of the working are pure calculus mechanics.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Sub turning-point x into ORIGINAL `f(x)` | differentiation-15 | recurring; every max/min year |
| Second-derivative test for max/min (even if not asked) | differentiation-15 | every year |
| Bracket-to-the-power chain rule | differentiation-8 | 2019, 2021, 2022, 2023, 2024 |
| Related rates: substitute constraint BEFORE differentiating | differentiation-20 | 2017, 2020, 2022, 2023, 2025 |
| Reciprocal trick `dR/dV = 1/(dV/dR)` | differentiation-20 | 2017, 2020, 2023, 2025 |
| Signed-rate reporting (negative ⇒ "decreasing") | differentiation-18 | 2020, 2023, 2024 |
| Particle at rest ⇒ `v(t) = 0` | differentiation-18 | 2015, 2017, 2022, 2024 |
| Implicit differentiation `d/dx[yⁿ] = n·y^(n−1)·dy/dx` | differentiation-10 | 2024 P1 |

> If you've internalised everything in this table, you've insured ~80% of the differentiation marks on the next paper.
