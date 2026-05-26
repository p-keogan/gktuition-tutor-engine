# Functions and Graphs — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Functions and Graphs before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Functions and Graphs deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **F&G appears in 10/11 years on Paper 1** (the only miss is 2015). Average ≈ 3.9 parts per paper. Total: **43 P1 main-sitting parts**.
- **Recent surge:** 2024 had **8** F&G-tagged parts; 2025 had **9** (counting all sub-citations across the paper). Two years ago (2022) the paper had **1**. F&G has more than doubled — plan as if 2026 is graph-heavy.
- **Section A leans on the mechanical end** (composite, inverse, limits-at-infinity), **Section B leans on the modelling end** (graph-sketching inside a real-world context — disease growth, cost models, periodic motion). Most papers carry both flavours.
- **Cross-strand reach:** F&G is the visual layer over everything calculus-flavoured. The same `f(x)` you sketch in F&G-9 is the `f(x)` you differentiate, the same vertex form from F&G-3 is the discriminant condition in Algebra 9, and F&G-10's limits-at-infinity recipe is the engine for asymptotes inside Differentiation 21 curve-sketching.

**The takeaway.** F&G isn't algebraically deep — it's *conceptually obscure* (Paul's word, F&G-10 [23:58]). Students lose marks because the **language** (codomain, injective, "in the form…") is unfamiliar, not because the algebra is hard. Drill the vocabulary and the routines, and the marks fall out.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Graph-drawing from a table of values** | 15 min | functions-graphs-9 — 15 citations, tested 10/11 main years. The single most-cited F&G tutorial. |
| **Vertex form / completing the square** | 15 min | functions-graphs-3 — tested 2016, 2017, 2021, 2023, 2025. The algebraic engine behind every "find the turning point" Section B sub-part. |
| **Composite functions** | 10 min | functions-graphs-4 — tested 2017, 2022, 2022 DF, 2023, 2024 (×2), 2024 DF, 2025 |
| **Limits at infinity (Type 2 recipe)** | 10 min | functions-graphs-10 — tested 2017, 2018, 2019, 2022 DF, 2023, 2025, 2025 DF |
| **Inverse functions (4-step recipe + bijectivity)** | 10 min | functions-graphs-8 — tested 2016, 2018, 2020, 2022 DF, 2025 |
| **Quadratic transformations (inside vs outside the bracket)** | 10 min | functions-graphs-2 — tested 2017, 2021, 2024, 2025 |
| **Quick-fire:** injective / surjective / bijective vocabulary | 15 min | functions-graphs-5/6/7 — short Section A questions; vocabulary marks |

---

## 📊 Top F&G tutorials by exam frequency (P1, 11 main years + 4 deferred)

| Rank | Tutorial | Citations | What it tests |
|---|---|---|---|
| 1 | `functions-graphs-9` Drawing Graphs | **15** | Table-of-values sketches; cubics, exponentials, logs; smooth curve discipline |
| 2 | `functions-graphs-4` Composite Functions | **11** | `f(g(x))` — substitute, expand, peel inside-out |
| 3 | `functions-graphs-3` Vertex form / Completing the Square | **10** | `ax² + bx + c → a(x − h)² + k`; turning point by inspection |
| 4 | `functions-graphs-2` Shapes of Quadratic Functions | **9** | Inside-bracket horizontal shift; outside-bracket vertical shift |
| 5 | `functions-graphs-10` Limits | **9** | Divide by the highest power of `n` as `n → ∞` |
| 6 | `functions-graphs-8` Inverse Functions | **7** | Isolate `x` recipe; bijective ⟺ inverse-is-a-function |
| 7 | `functions-graphs-1` JC Revision | **7** | Function-evaluation `f(a)`; the vertical-line-test definition |
| 8 | `functions-graphs-5` Injective Functions | **5** | Horizontal line test (at most once) |
| 9 | `functions-graphs-6` Surjective Functions | **2** | Codomain restriction (at least once) |

> **Read this as:** if you only have 90 minutes, tutorials 1–5 account for **54 cited appearances** across Paper 1. Do not skip them.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 20** | `x = (−b ± √(b² − 4ac))/(2a)` | The axis of symmetry of a parabola is `x = −b/(2a)` — drop the radical to read the vertex's x-coordinate directly. |
| **p. 20** | Discriminant `b² − 4ac` | Discriminant `= 0` ⟹ turning point sits on the x-axis. Discriminant `< 0` and `a > 0` ⟹ graph entirely above the x-axis. |
| **p. 21** | Log laws (Rule 3: `ln(x^n) = n ln x`) | Inverting `eˣ` (introduce ln to bring the exponent down). |

> **🎯 Functions and Graphs is a low-formula strand.** The marks come from *technique* — completing the square, the inside-out substitution, the divide-by-highest-power routine — not from looking things up. Working memory carries this strand, not the booklet.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until automatic.

### 1. The inside-vs-outside-the-bracket transformation rule

Memorise as a two-row table:

```
g(x) = f(x − h) + k    ⟺   shift the graph of f(x) RIGHT by h, UP by k
g(x) = f(x + h) − k    ⟺   shift the graph of f(x) LEFT by h, DOWN by k
```

> **The counter-intuitive bit (Paul, F&G-2 [04:42]):** *"A plus 2 in the brackets will move it to the **left** 2 units, whereas a minus 2 in the brackets will move it to the **right** 2 units. Probably the opposite of what you might have guessed."* Inside the bracket, the sign of the shift is **opposite** to the sign in the bracket.

### 2. The vertex-form reading rule

Given `f(x) = a(x − h)² + k`, the turning point is `(h, k)`. **Flip the sign of the bracket constant; keep the sign of the outside constant.** So `(x + 5)² − 7` ⟹ turning point `(−5, −7)`.

### 3. The composite-function inside-out rule

`f(g(x))` means: substitute the *entire* expression `g(x)` for *every* `x` in `f`. For triple composites `h(g(f(x)))`, peel innermost outward.

> **Paul, F&G-4 [01:43]:** *"f(g(x)) means whatever's in the bracket — you're subbing into the function f."* The exam will throw three notations at you for the same thing: `fg(x)`, `f∘g(x)`, `f(g(x))`. **All three mean the same thing.**

### 4. The bijective ⟺ invertible theorem

> **Paul, F&G-8 [07:44]:** *"If a function is bijective, then the inverse of that function will also be a function."*

The contrapositive is the exam-useful version: **if `f⁻¹` contains a fractional power (`√`, `∛`, `^(1/n)`), then `f` is NOT bijective.** This gives you a proof technique — find the inverse, inspect it, conclude.

---

## 🚨 LOAD-BEARING — the five things that win or lose the F&G question

### 1. Inside the bracket ⟹ horizontal shift; outside the bracket ⟹ vertical shift — and the horizontal direction is OPPOSITE to the sign

| Form | Movement | Direction |
|---|---|---|
| `f(x − h)` | Horizontal | RIGHT by `h` |
| `f(x + h)` | Horizontal | LEFT by `h` |
| `f(x) + k` | Vertical | UP by `k` |
| `f(x) − k` | Vertical | DOWN by `k` |

> 🚨 **The sign flip is where students lose the mark.** `(x + 3)²` shifts the graph LEFT, not right. Paul (functions-graphs-2) makes you derive this from "what value of `x` makes the bracket zero?" — that's where the vertex lives. Tested 2017, 2021, 2024, 2025 P1.

### 2. Completing the square with `a ≠ 1` — FACTOR, don't divide

To put `ax² + bx + c` into vertex form `a(x − h)² + k`:

1. **Factor out `a`** from the `x²` and `x` terms only — *not* from `c`.
2. Inside the bracket, halve the coefficient of `x`, square it, add and subtract.
3. Pull the subtracted term out through the `a`.
4. Read off `(h, k)` by inspection.

> 🚨 **Dividing through by `a` loses you marks.** It destroys the original equation. (functions-graphs-3 load-bearing rule.) The technique surfaces in every "express in the form `a(x − h)² + k`, **hence** find the turning point" question. Tested 2016, 2017, 2021, 2023, 2025 P1.

### 3. Composite-function evaluation — substitute the ENTIRE inner expression wherever `x` appears

For `f(g(x))`:
1. Write down `f(x)`'s definition.
2. Wherever you see an `x` in `f`, substitute the entire `g(x)` expression (with brackets).
3. Expand and simplify.

For triple/iterated composites like `h(g(f(x)))` or `h²(g(x)) = h(h(g(x)))`, **peel innermost outward.** For *numeric* composition, work inside-out and evaluate to a number first; for *symbolic* composition, substitute symbolically and expand at the end.

> 🚨 **The trap is the brackets.** Writing `f(2x + 1) = (2x + 1)² + 3 = 4x² + 3` (forgetting the cross-term) is the #1 deduction in MS notes. Always expand fully: `(2x + 1)² = 4x² + 4x + 1`. Tested every year from 2022 onwards (2022, 2022 DF, 2023, 2024 ×2, 2024 DF, 2025).

### 4. Limit at infinity — divide every term by the highest power of `n`

> The recipe (functions-graphs-10):
> 1. Identify the **highest power of `n`** in the expression (top *and* bottom together).
> 2. **Divide every term** by that power.
> 3. As `n → ∞`, every `(constant)/n^k` term collapses to `0`. Read off what's left.

> 🚨 **The four properties of limits (sum, product, quotient, root) only apply when `x → constant`, NOT when `x → ∞`.** Paul calls this out at functions-graphs-10 [40:54]. The Type-2 (`n → ∞`) and Type-1 (`x → a`) routines are different recipes — don't mix them. Tested 2017, 2018, 2019, 2022 DF, 2023, 2023 DF, 2025, 2025 DF.

### 5. Inverse functions — bijective implies invertible (and how to use that backwards)

The recipe (functions-graphs-8): write `y = f(x)`, **isolate `x` on the right-hand side**, swap labels — that's `f⁻¹(x)`. For quadratics with two `x` terms, **complete the square first** so there's only one `x` to isolate.

> 🚨 **If `f⁻¹` contains a `√`, `∛`, or any `^(1/n)`, then `f⁻¹` is NOT a function ⟹ `f` is NOT bijective.** This is the exam-useful contrapositive of Paul's *"bijective ⟹ inverse is a function"* theorem. Used as a proof technique in 2025 P1 and 2022 DF. Tested 2016, 2018, 2020, 2022 DF, 2025.

---

## 🎯 The seven techniques you must execute without thinking

1. **Function evaluation `f(a)`** — substitute `a` for every `x` in the formula; arithmetic only.
2. **Sketch a graph from a table of values** — three columns (`x`, `f(x)`, coordinate); plot points; join with a **smooth curve**, not straight segments. Label axes. (functions-graphs-9.)
3. **Identify the codomain notation `h(x) ∈ ℝ < c`** — this restricts the *y*-values (outputs), not the inputs. Affects surjectivity, not injectivity. (functions-graphs-6.)
4. **Horizontal line test** — `at most once` ⟹ injective; `at least once` ⟹ surjective; `exactly once for every horizontal line in the codomain` ⟹ bijective.
5. **The classical inverse pair `eˣ ↔ ln(x)`** — when you see `eˣ`, the inverse is `ln(x)`; when you see `ln(x)`, the inverse is `eˣ`. (functions-graphs-8 + indices-logs-5.)
6. **Reflection rules** — `f(−x)` reflects in the **y-axis**; `−f(x)` reflects in the **x-axis**; the inverse `f⁻¹` reflects the graph of `f` in the line `y = x`.
7. **Recognise the four "fraction-with-zero / fraction-with-infinity" cases** — `0/k = 0`, `k/∞ = 0`, `k/0 = undefined`, `∞/k = ∞ = undefined`. The two undefined cases are what you spot before reaching for L'Hôpital-style cancellations.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| `(x + 3)²` shifts the graph right | Inside the bracket, the direction is **opposite** to the sign — left, not right |
| Dividing through by `a` when completing the square (`a ≠ 1`) | **Factor** `a` out of the `x²` and `x` terms only; leave `c` alone |
| `f(2x + 1) = (2x + 1)² + 3 = 4x² + 3` (missing cross-term) | Expand `(2x + 1)²` fully = `4x² + 4x + 1` |
| Treating `fg(x)`, `f∘g(x)`, `f(g(x))` as different things | They're the same notation in three dresses |
| Trying the sum/product/quotient limit rules on `n → ∞` problems | Those four rules are for `x → constant` ONLY — for `n → ∞` divide by the highest power |
| Calling `f(x) = x²` on ℝ injective | Quadratics on ℝ are **never** injective — paired x-values straddle the vertex. Only injective on a restricted domain (e.g. `[0, ∞)`) |
| Saying a function "isn't surjective" without checking the codomain | Surjectivity depends on the **codomain**, not the formula. The same `h(x)` can be surjective or not depending on the codomain you're given |
| `f⁻¹(x) = 1/f(x)` | The `−1` is not a power. `f⁻¹` means the inverse function, not the reciprocal |
| Forgetting domain-exclusion for `1/x` graphs | `x = 0` is **not** in the domain; the y-axis is an asymptote |
| Drawing a cubic with straight line segments | Always join points with a **smooth curve**; mark turning points and the point of inflection |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Express in the form `a(x − h)² + k`"* | Complete the square. Then read off `(h, k)`. |
| *"Hence find the turning point"* | Use the previous part — *do not* redo via differentiation |
| *"Draw the graph of `f(x)` in the domain…"* | Table of values; smooth curve; label axes and intercepts |
| *"Find `(f ∘ g)(x)`" / "Find `fg(x)`" / "Find `f(g(x))`"* | All the same — substitute `g(x)` into `f` |
| *"Find `lim_{n→∞} …`"* | Type 2 recipe — divide every term by the highest power of `n` |
| *"Find `lim_{x→a} …`" (a constant)* | Type 1 — substitute and simplify; if you get `0/0`, factor the numerator and cancel |
| *"Show that `f` is bijective"* | Find `f⁻¹`; if it's a function (no `√` or `^(1/n)`), then `f` is bijective |
| *"Find the values of `k` for which the codomain…"* | Surjectivity check — what's the range of `f`? Match to the codomain |
| *"Sketch `f(−x)` / `−f(x)` / `f⁻¹(x)`"* | Reflect in y-axis / x-axis / line `y = x` respectively |

---

## 💡 Three exam-day tips that move the needle

1. **For "draw the graph" questions, plot the points first, then connect.** Get the points right and you've banked the method marks even if your curve is wobbly. Skipping straight to the curve from memory = 0 marks if a turning point is wrong.

2. **For "hence" sub-parts, use the previous part's result — don't re-derive.** "Hence find the turning point" after "express in the form `(x−h)² + k`" means **read it off**, not differentiate. Re-deriving is slower and a marker may penalise the missed "hence".

3. **Vocabulary marks are free if you've memorised the words.** "Injective", "surjective", "bijective", "codomain", "asymptote" — Paul opens F&G-10 [23:58] calling the territory *"obscure"*. The algebra is light; the language carries the marks.

---

## 🔗 Cross-strand connections (where else F&G fires)

- **F&G ↔ Algebra** — completing the square is functions-graphs-3 AND algebra-9 simultaneously; the discriminant condition controls whether the parabola's turning point sits on the x-axis.
- **F&G ↔ Differentiation** — the turning point you find by completing the square is the same point you find by `f'(x) = 0`. The shapes-of-derivatives questions (differentiation-21) lean on functions-graphs-9's drawing conventions.
- **F&G ↔ Sequences and Series** — `S∞` exists iff `|r| < 1`; that's a **convergent** geometric sequence in functions-graphs-10's vocabulary. The limit Paul develops at functions-graphs-10 is the formal version.
- **F&G ↔ Indices and Logs** — the classical inverse pair `eˣ ↔ ln(x)`; indices-logs-5's "introduce ln" technique is what powers Worked Example 4 of functions-graphs-8.
- **F&G ↔ Financial Maths / Modelling** — Section B contextual questions (disease growth, periodic motion, cost models) reach for functions-graphs-2's amplitude+vertical-shift framework and functions-graphs-9's plotting discipline. 2025 P1 Q9 used both.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL (main + DF) |
|---|---|---|
| Inside-vs-outside bracket transformations | functions-graphs-2 | 2017, 2021, 2024, 2025 |
| Completing the square (`a ≠ 1` factor, don't divide) | functions-graphs-3 | 2016, 2017, 2021, 2023, 2025 |
| Composite-function substitution (inside-out) | functions-graphs-4 | 2017, 2022, 2022 DF, 2023, 2024, 2024 DF, 2025 |
| Limit at infinity (divide by highest power) | functions-graphs-10 | 2017, 2018, 2019, 2022 DF, 2023, 2023 DF, 2025, 2025 DF |
| Bijective ⟺ invertible (and the contrapositive) | functions-graphs-8 | 2016, 2018, 2020, 2022 DF, 2025 |
| Drawing graphs from a table of values | functions-graphs-9 | 2016, 2017, 2018, 2019, 2021, 2023, 2024, 2024 DF, 2025, 2025 DF |
| Function evaluation `f(a)` and the vertical-line-test definition | functions-graphs-1 | 2018, 2022 DF, 2023 DF, 2024, 2024 DF, 2025 |

> If you've internalised everything in this table, you've insured ~85% of the F&G marks on the next paper. The 2024–25 surge says the next paper is more likely to lean heavier than the historical 3.9-parts-per-paper average — drill graph-drawing and composite functions first.
