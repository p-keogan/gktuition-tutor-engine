# Algebra — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Algebra before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Algebra deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Algebra appears in 11/11 years on Paper 1.** Average ≈ 8.9 parts per paper. Total: **98 P1 parts**.
- **Recent surge:** 2024 had **19** algebra parts; 2025 had **17**. Prior 9-year average was ≈ 7.7. Plan as if 2026 is algebra-heavy too.
- **Section A leans heavier than B** (60 vs 38). Algebra is mostly tested as concepts/skills, occasionally as the spine of a Section B financial-maths or geometric-series problem.
- **Cross-strand reach:** Algebra also fires inside Differentiation (`f'(x) = 0` → quadratic), Complex Numbers (conjugate pairs), Integration (algebraic simplification), and Paper 2 (quadratic formula for circle-line intersections — 16 cross-strand P2 citations).

**The takeaway.** Algebra isn't just one strand; it's the *enabling toolkit*. Marks lost here cascade through every other Paper 1 topic and several Paper 2 ones.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Cubics: Factor Theorem + long division** | 20 min | algebra-11 + algebra-13 — tested 2020/21/23/24, again in 2025 |
| **Manipulation of formula** | 10 min | algebra-14 — tested **every year**, 21 P1 citations |
| **Discriminant & quadratic-roots questions** | 10 min | algebra-9 — 21 P1 citations; pillar of every "find values of k" question |
| **Modulus equations + inequalities** | 10 min | algebra-15 — tested 2020/22/23/24/25 (every recent year) |
| **Surd equations + the verification step** | 10 min | algebra-17 — tested 2018/22/24/25 |
| **Simultaneous (3-var + linear–quadratic)** | 10 min | algebra-18 + algebra-19 — appeared 2024 DF, 2025, 2025 DF |
| **Quick-fire:** binomial / Pascal / fractions / sign rules | 15 min | All formula-sheet driven — page 20 |

---

## 📊 Top 10 algebra tutorials by exam frequency (P1 main, 11 years)

| Rank | Tutorial | P1 citations | What it tests |
|---|---|---|---|
| 1 | `algebra-2` Factorising Quadratics | **30** | Every paper. Factor before you solve. |
| 2 | `algebra-9` Nature of Quadratic Graphs | **21** | Discriminant; "no real roots", "real and equal" |
| 3 | `algebra-1` JC Factorising | **21** | Difference of two squares, four-term grouping |
| 4 | `algebra-14` Manipulation of Formula | **21** | Change of subject — "express k in terms of …" |
| 5 | `algebra-13` Long Division | 12 | Polynomial long division (the cubic engine) |
| 6 | `algebra-6` Inequalities | 11 | Quadratic-inequality region sketch |
| 7 | `algebra-11` Solving Cubic Equations | 9 | Factor Theorem |
| 8 | `algebra-17` Surd Equations | 9 | Squaring + mandatory verification |
| 9 | `algebra-7` Rational Inequalities | ~6 | Multiply by `(denom)²` to preserve direction |
| 10 | `algebra-15/16` Modulus | ~6 | Equations + inequalities |

> **Read this as:** if you only have 90 minutes, your tutorials 1–4 alone account for *93 cited appearances* across Paper 1. Do not skip them.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 20** | `x = (−b ± √(b² − 4ac))/(2a)` | Quadratic formula. The discriminant `b² − 4ac` lives under the radical. |
| **p. 20** | Sum of roots `= −b/a`, Product of roots `= c/a` | "Form the quadratic given the roots"; Vieta's sanity check on cubics |
| **p. 20** | Binomial theorem `(x + y)ⁿ = Σ C(n,r) · xⁿ⁻ʳ · yʳ` | Binomial-expansion questions |
| **p. 20** | `C(n,r) = n!/(r!(n−r)!)` | Specific coefficient |
| **p. 21** | Index laws | Powers/log simplification before algebra |

> **🎯 Stop memorising the binomial theorem.** Flip to page 20 and substitute. Use working memory for **techniques**, the tables for **formulas**.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. The four discriminant scenarios

Memorise the table above as a **mapping from inequality to root-count phrasing**:

- `b² − 4ac > 0` → two real distinct roots
- `b² − 4ac = 0` → one real repeated root (two equal real roots)
- `b² − 4ac ≥ 0` → two real roots (no qualifier on distinctness)
- `b² − 4ac < 0` → two complex conjugate roots

> Drill until you can write the four scenarios in 20 seconds without thinking. The exam wording chooses which inequality you need to solve.

### 2. Factorising sum and difference of two cubes

These are **not on the log tables.** You must have them cold:

```
a³ + b³ = (a + b)(a² − ab + b²)
a³ − b³ = (a − b)(a² + ab + b²)
```

> **Mnemonic.** The sign of the **first** bracket matches the sign on the LHS. The **middle** term of the quadratic bracket has the **opposite** sign. The first and last terms of the quadratic bracket are always **positive**. (SOAP: Same — Opposite — Always Positive.)

### 3. Forming a quadratic from its roots (sum-and-product method)

Given two roots `α` and `β`, the monic quadratic with those roots is:

```
x² − (α + β)x + (αβ) = 0
       ↑ sum         ↑ product
```

For a non-monic quadratic `ax² + bx + c = 0` with roots `α, β`:

```
sum     α + β = −b/a
product α · β =  c/a
```

> **Used three ways in exams:**
> 1. "The roots are 3 and −5. Form the quadratic." → `x² − (−2)x + (−15) = x² + 2x − 15 = 0`.
> 2. "Given one root is `2 + 3i`, find the quadratic with real coefficients." → conjugate is `2 − 3i`; sum = 4, product = `2² + 3² = 13`; quadratic is `x² − 4x + 13 = 0`.
> 3. **Vieta's sanity check on cubics** — once you've found three roots, sum should equal `−b/a` of the cubic, product should equal `−d/a`. Quick check that catches sign errors.

---

## 🚨 LOAD-BEARING — the five things that win or lose the algebra question

### 1. Discriminant `b² − 4ac` — nature of roots of `ax² + bx + c = 0`

The four-scenario rubric. Match the exam phrasing to the right inequality:

| Discriminant | Roots | Exam phrasing |
|---|---|---|
| `> 0` | Two real, **distinct** | "Two distinct real roots", "two different real roots" |
| `= 0` | One real, **repeated** (a.k.a. two equal real roots) | "Real and equal", "exactly one solution", "a repeated root" |
| `≥ 0` | **Two real roots** (distinct OR equal) | "Two real roots" *without* the word "distinct" — both `> 0` and `= 0` are allowed |
| `< 0` | Two **complex conjugate** roots | "No real roots", "complex roots" |

> 🚨 **Read the wording carefully.** "Two real roots" (no qualifier) is *not* the same as "two distinct real roots". The `≥ 0` scenario is the easy mark students lose by collapsing it into `> 0`.
>
> **"Real and equal" ⇒ `b² − 4ac = 0`. Solve for the unknown parameter.** This is the #1 'find the value of k' pattern. Tested 2025 P1 Q3 and many earlier years. Always check by subbing k back in.

### 2. Factor Theorem (cubics)

> `(x − a)` is a factor of `f(x)` **if and only if** `f(a) = 0`.

**The cubic-solving recipe:**
1. **Find one root** — try `±1, ±2, ±3` (and divisors of the constant term).
2. **Long division** — divide `f(x)` by `(x − a)` to get a quadratic.
3. **Solve the quadratic** — factorise or use page 20.
4. **State all three roots.**

> 🚨 **Use long division.** Coefficient-matching and grid methods look quicker but generate sign and bookkeeping errors that students never recover from. (Paul opens algebra-13 with: *"as far as I'm concerned the material that we cover in this video is the hardest material on the LCHL Higher Level Algebra section."* Tested 2020/21/23/24, again in 2025 P1 Q3 and 2025 DF P1.)

### 3. Modulus — equations vs inequalities

| Form | Method |
|---|---|
| `\|x − a\| = b` | **Either method works** — split into `x − a = b` OR `x − a = −b` (usually faster) |
| `\|x − a\| < b` | **Square both sides.** Becomes `(x − a)² < b²`, factor as a quadratic inequality, sketch parabola, read off interval |
| `\|x − a\| > b` | **Square both sides.** Same routine; the answer is the two outer intervals |

> 🚨 **For modulus + inequality, ALWAYS square.** Paul's clear-cut rule at algebra-15 [07:48]: *"If you have an inequality and a modulus, square both sides. It is so much easier."* The split-into-± method does not compose cleanly with inequality signs (multiplying or dividing by a negative flips them). Tested in 2020, 2022, 2023, 2024, and 2025 — **every recent year**.

### 4. Conjugate Root Theorem (polynomials with complex roots)

> If `f(x)` has real coefficients and `(p + qi)` is a root, then **`(p − qi)` is also a root**.

So a cubic with one given complex root automatically has a second one (its conjugate) and a third real root. The recipe is: write the conjugate, build the quadratic from sum-and-product, long-divide the cubic by that quadratic to expose the linear factor.

> 🚨 Tested 2025 DF P1 with the full three-step recipe.

### 5. The "immediate complication" master strategy — algebra-14

> Whenever you face a change-of-subject or solve-for-x problem: **what is the immediate complication?** Clear it first.

1. **Fractions** → multiply through by the LCM
2. **Brackets** → distribute
3. **Target letter on both sides** → collect and factor it out
4. **Surd / radical** → isolate, then square (then verify — see rule 5 of techniques below)

> 🚨 algebra-14 is tested **every year** — 21 P1 citations. It's not a "topic"; it's a discipline that fires inside every algebra-flavoured question across all strands.

---

## 🎯 The 8 techniques you must execute without thinking

1. **Factorise a quadratic** by inspection (sum-product method) or by `−b` formula. Recognise difference of two squares: `a² − b² = (a − b)(a + b)`. Recognise four-term grouping pattern.
2. **Factorise sum/difference of two cubes**: `a³ ± b³ = (a ± b)(a² ∓ ab + b²)`. (HL-specific.)
3. **Algebraic fractions** — common denominator, then either solve or simplify. State restrictions (denominators ≠ 0).
4. **Long division of polynomials** — the row-by-row layout. Practise the "change signs and subtract" discipline once cold.
5. **Complete the square** — `ax² + bx + c → a(x + h)² + k`. Used for turning points and quadratic graphs. **Critical distinction:** when `a ≠ 1`, factor out `a` from the `x²` and `x` terms first; do NOT divide through.
6. **Binomial expansion** — `(a + b)ⁿ` via the general term `C(n,r)·aⁿ⁻ʳ·bʳ`; solve for `r` to find a specific term. For `n ≤ 4` Pascal's triangle is often faster (see algebra-20).
7. **Simultaneous equations:**
   - **3 unknowns linear**: 5-step elimination cascade — label A/B/C → eliminate one variable into D and E → solve 2×2 → back-substitute.
   - **1 linear + 1 quadratic**: solve the linear for one variable, substitute into the quadratic, get a 1-variable quadratic, back-substitute.
8. **Surd equations** — isolate the surd, square BOTH sides, solve, **verify each candidate in the ORIGINAL equation.** Squaring can introduce extraneous roots that satisfy the squared equation but not the original.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Multiplying/dividing inequality by negative → **flip the sign** | Always check sign of multiplier; flip if negative |
| `(x − 2)² = 4` → `x − 2 = ±2`, NOT just `+2` | Square roots are `±` |
| `(2x + 6)² = 4x² + 36` (wrong) | Expand fully: `4x² + 24x + 36` |
| Squaring a surd equation but forgetting to verify | Always sub final answers back into the **original** equation |
| Cubic with only one root listed | Three roots: real + real + real, OR one real + one complex conjugate pair |
| Modulus inequality split into ± cases | For inequalities, **square**. The split method is for equations only. |
| Forgetting denominator ≠ 0 restriction | State the restriction; sometimes worth a method mark |
| Discriminant sign error: `b² − 4ac` vs `b² + 4ac` | The formula sheet (p. 20) has it correct — don't trust memory |
| "Find k" using sum/product of roots — wrong sign on `b/a` | Sum of roots = **−b/a** (the minus matters) |
| Long division: forgetting to subtract, or sign error in row | Write each subtraction explicitly; line up powers of x |
| Completing the square with `a ≠ 1`: dividing instead of factoring | Factor `a` out of the `x²` and `x` terms only |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Show that…"* | Method marks heavy — show every step, even "obvious" ones |
| *"Hence…"* | Use the previous part's result — don't re-derive |
| *"Find the value(s) of k for which…"* | Set up an equation (often `discriminant = 0`, or sub the given root into `f(x) = 0`) |
| *"Verify that…"* | Sub in the given value and demonstrate equality (no working required beyond substitution) |
| *"Express in the form…"* | Algebraic rearrangement; the target form is given — drive toward it |
| *"Solve for x ∈ ℝ"* | Reject complex roots; don't reject negatives unless excluded by context |
| *"Solve for x ∈ ℂ"* | Keep complex roots; expect a conjugate pair |
| *"(x − c) is a factor"* | Factor Theorem: `f(c) = 0`. Then long-divide. |

---

## 💡 Three exam-day tips that move the needle

1. **Show the formula → substitute → answer.** Three lines, three method marks. Even if your arithmetic is wrong, the first two lines get marks. *Skipping straight to the answer = 0 marks if wrong.*

2. **Use the log tables for formulas, not for techniques.** Page 20 (quadratic formula, sum/product of roots, binomial theorem) is open in front of you — don't waste working memory on memorising them.

3. **If a question is taking >12 minutes, move on.** Section A questions average ~6 min; Section B sub-parts average ~3–5 min. Mark a stuck question and return at the end. Algebra surges in 2024–25 mean some Section B sub-parts demand 8–10 min — that's the *upper* end, not the median.

---

## 🔗 Cross-strand connections (where else algebra fires)

- **Algebra ↔ Complex Numbers (§4.4)** — Conjugate Root Theorem; cubics with complex roots (2025 DF P1).
- **Algebra ↔ Sequences & Series** — `Sₙ > bound` reduces to a quadratic inequality (2025 P1); `Tₙ = ar^(n−1)` rearrangements demand algebra-14 manipulation.
- **Algebra ↔ Functions & Graphs** — completing the square ⇒ vertex form; discriminant ⇒ turning point on x-axis.
- **Algebra ↔ Differentiation** — `f'(x) = 0` reduces to a quadratic or cubic; turning-point and max/min questions live or die on the algebra.
- **Algebra ↔ Integration** — algebraic manipulation BEFORE integrating (splitting fractions, expanding brackets, substituting bounds).
- **Algebra ↔ Indices & Logs** — log equations reduce to algebra (2025 DF P1 had a log equation that became a quadratic in `n`).
- **Algebra ↔ Paper 2 (Circle / Line)** — quadratic formula for circle–line intersections; substitution for tangent conditions; discriminant for tangency. **16 cross-strand P2 citations** in the 11-year window.

> Algebra is not "one of the strands". It is the spine. Even when the question is labelled Probability or Geometry, the last 30 seconds of the working are almost always pure algebra.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| "Is a factor of …" → long division | algebra-13 | 2020, 2021, 2023, 2024, 2025 |
| Modulus + inequality → square | algebra-15 | 2020, 2022, 2023, 2024, 2025 |
| Surd equation → verify | algebra-17 | 2018, 2022, 2024, 2025 |
| Change-of-subject (immediate complication) | algebra-14 | every year |
| Discriminant = 0 ⇒ find k | algebra-9 | recurring; 2025 P1 confirmed |
| Conjugate root theorem on cubics | algebra-11 + Complex 9 | 2025 DF P1 (3-step recipe) |
| 3-variable simultaneous (5-step cascade) | algebra-18 | 2024 P1; recurring |

> If you've internalised everything in this row, you've insured ~80% of the algebra marks on the next paper.
