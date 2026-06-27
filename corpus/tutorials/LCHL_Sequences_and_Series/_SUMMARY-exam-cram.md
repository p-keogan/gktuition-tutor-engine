# Sequences, Series and Limits — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Sequences and Series before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Sequences and Series deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Sequences and Series appears in 11/11 years on Paper 1.** Average ≈ 6.0 parts per paper. Total: **66 P1 parts**.
- **2025 surge:** 2025 had **12** S&S parts — double the historical average and the highest single-year count since 2018 (which had 11). The 2019–2024 average was 5.2; 2025 broke that pattern hard. Plan as if 2026 could swing high too.
- **Geometric content dominates arithmetic.** `sequences-series-5` (geometric `Tₙ` and `Sₙ`) has 21 P1 citations; the arithmetic opener has 11. If you only revise one half of the strand, revise geometric.
- **Section split:** "Usually in Q4 or Q5 of Section A (sequence-pattern fluency) and Q7 of Section B (financial-maths context)" — exam trends file. The Section B Q7 financial-maths spine is reliably worth ~50 marks when it appears.
- **Cross-strand reach:** S&S also fires inside Financial Maths (the annuity / amortisation formulas *are* geometric series), Indices & Logs (whenever `n` is in the exponent — IL-5 fires), Algebra (`Sₙ > bound` collapses to a quadratic inequality — 2025 P1), F&G/Limits (S&S-14 is the canonical cross-listing to F&G-10), Induction (S&S-10 is the prescribed proof), and Paper 1 Proofs (S&S-15 — S∞ derivation).

**The takeaway.** S&S has the highest year-to-year variance of any Tier-1 strand: 3 parts in 2023, 12 in 2025. The downside is unpredictable weight; the upside is that the load-bearing rules are short, the page-22 formulas do most of the work, and the question patterns repeat.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Geometric `Tₙ`, `Sₙ`, identifying `a` and `r`** | 15 min | sequences-series-5 — 21 P1 citations; #7 most-cited tutorial in the entire P1 corpus |
| **Sum to infinity `S∞ = a/(1−r)` + the `\|r\| < 1` check** | 15 min | sequences-series-8 — 16 P1 citations; tested 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2024 DF |
| **Arithmetic `Tₙ`, `Sₙ`, and `Sₙ > bound` (quadratic inequality)** | 10 min | sequences-series-1 + 3 — 2025 P1 Q4 was exactly this; algebra-9 spillover |
| **Geometric proof methods (T₂/T₁ = T₃/T₂) + "find a and r" simultaneous** | 10 min | sequences-series-6 + 7 — recurring 2018, 2020, 2022, 2024 |
| **Limits at infinity: divide by highest power of n** | 10 min | sequences-series-14 / F&G-10 — Calculation Type 2; tested 2020, 2022, 2023, 2023 DF, 2024 |
| **Patterns 1 & 2 (quadratic / cubic via differences)** | 10 min | sequences-series-patterns-1,2 — Section A staple; 2025 P1 Q4(c) Method 3 |
| **Quick-fire:** induction proof of `Sₙ`, recurring decimals as fractions, year-indexing | 15 min | S&S-10 (Induction §7); S&S-9; financial-maths overlap |

---

## 📊 Top tutorials by exam frequency (P1 main, 11 years)

| Rank | Tutorial | P1 citations | What it tests |
|---|---|---|---|
| 1 | `sequences-series-5` Geometric Sequences 1 | **21** | `Tₙ = a·r^(n−1)`, `Sₙ = a(1−rⁿ)/(1−r)`; identifying `a` and `r` |
| 2 | `sequences-series-8` Geometric Sequences 4 | **16** | `S∞ = a/(1−r)`, the `\|r\| < 1` convergence check |
| 3 | `sequences-series-1` Arithmetic Sequences 1 | **11** | `Tₙ = a + (n−1)d`, `Sₙ = (n/2)[2a + (n−1)d]` |
| 4 | `sequences-series-14` Convergence/Limits | 6 | `rⁿ → 0` when `\|r\| < 1`; limits at infinity |
| 5 | `sequences-series-patterns-1` Quadratic Patterns | ~4 | Second-differences constant ⇒ `Tₙ = an² + bn + c` |
| 6 | `sequences-series-6` Geometric Sequences 2 | ~4 | Proving geometric — the `T₂/T₁ = T₃/T₂` method |
| 7 | `sequences-series-7` Geometric Sequences 3 | ~3 | "Find `a` and `r`" simultaneous equations |
| 8 | `sequences-series-3` Arithmetic Sequences 3 | ~3 | `Sₙ` inversion: "for what `n` does the sum exceed K?" |

> **Read this as:** tutorials 1–3 alone account for 48 cited appearances across Paper 1. If you only have 30 minutes, do those three. (Counts 5–8 are estimates derived from grep over the solutions corpus — the trends file gives exact figures for 1–4 only.)

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 22** | `Tₙ = a + (n−1)d` | Arithmetic — nth term. `a` = first term, `d` = common difference |
| **p. 22** | `Sₙ = (n/2)[2a + (n−1)d]` | Arithmetic — sum to n terms |
| **p. 22** | `Tₙ = a·r^(n−1)` | Geometric — nth term. `a` = first term, `r` = `T₂/T₁` |
| **p. 22** | `Sₙ = a(1−rⁿ)/(1−r)` (or `a(rⁿ−1)/(r−1)`) | Geometric — sum to n terms. Use the `1−r` form when `r < 1`, the `r−1` form when `r > 1` |
| **p. 22** | `S∞ = a/(1−r)`, valid when `\|r\| < 1` | Sum to infinity. The convergence condition is **printed beside the formula** |
| p. 21 | `log(aⁿ) = n·log(a)` | Whenever `n` is in the exponent — IL-5 |

> **🎯 Page 22 is your entire strand.** Both arithmetic and geometric formulas, plus `S∞`, live on one page. Flip to it once at the start of the question and don't shut it.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items page 22 **doesn't** give you. Drill until they're automatic.

### 1. The `|r| < 1` convergence condition for `S∞`

Printed next to the formula, but easy to miss in exam pressure. **Apply `S∞` only when `|r| < 1`.** If `|r| ≥ 1` the series diverges and the formula gives nonsense.

> Paul (sequences-series-8 [04:38]): *"Beside the sum to infinity formula, it tells you that you can only use this formula if the absolute value of r is less than 1. Mathematically another way of saying that is saying that r needs to be between 1 and minus 1."*

This is also the rejection criterion when "find `r`" produces two candidates — drop the one with `|r| ≥ 1`. Paul (S&S-8 [20:18]): *"only one of these answers is valid… It's because there's a sum to infinity. If a sum to infinity exists that means that the absolute value of r has to be less than 1."*

### 2. The differences-method for quadratic and cubic patterns

Not on the tables. You must have them cold:

```
Quadratic pattern  Tₙ = an² + bn + c   ⇔   2nd difference is constant, equal to  2a
Cubic pattern      Tₙ = an³ + bn² + cn + d   ⇔   3rd difference is constant, equal to  6a
```

Once you have `a` from the constant difference, sub `n = 1, 2` (and `n = 3` for cubic) into the form to get simultaneous equations in the remaining coefficients.

> Paul (Patterns 1 [00:12]): *"In order to identify something as a quadratic pattern you need to prove that the second difference is common."* Also [01:21]: *"In the Leaving Cert if you've got a question like this you should mention the phrase 'second difference'."* — state the test by name.

### 3. The `Tₙ = Sₙ − Sₙ₋₁` identity

When the question gives you `Sₙ` (not `Tₙ`) and asks for individual terms, you can always recover `Tₙ = Sₙ − Sₙ₋₁`. Companion identity for the slice-sum trick: `S_m − S_k` = sum from term `k+1` to `m` (sequences-series-3).

### 4. The `(a−d, a, a+d)` and `(a/r, a, ar)` tricks

When "three consecutive terms of an AP/GP" is set up symmetrically as `(a−d, a, a+d)` (AP) or `(a/r, a, ar)` (GP), the middle-term parameter `a` drops out of any sum or product condition, halving the algebra (sequences-series-4 closing block).

### 5. Year-0 vs year-1 indexing in financial sequences

The `Tₙ = a·r^(n−1)` formula assumes term 1 = `a`. For year-0-indexed sequences ("price in Year 0 = `a`"), use `Tₖ = a·rᵏ` — raise to the power that **counts the years**. Tested 2017, 2020, 2022 DF, 2024.

---

## 🚨 LOAD-BEARING — the five things that win or lose the S&S question

### 1. The page-22 formulas, applied with the right `a`, `r`, `d`, `n`

> The formulas are given. **The marks are for setting up `a`, `r`, and `n` correctly.**

Most lost marks here aren't formula failures — they're parameter-identification failures. For arithmetic: `a` = first term, `d` = (any term) − (previous term). For geometric: `a` = first term, `r = T₂/T₁` (must equal `T₃/T₂` — if not, it isn't geometric).

> 🚨 **Tested every year. 11/11 since 2015.**

### 2. `|r| < 1` is mandatory before applying `S∞`

The single most-deducted error on `S∞` questions. **State the convergence check explicitly** — even if it's "obviously" satisfied.

| Condition | What to do |
|---|---|
| `\|r\| < 1` | `S∞ = a/(1−r)` applies — finite |
| `\|r\| ≥ 1` | Diverges. `S∞` does NOT exist. Reject this `r` candidate if the question asks for `S∞` |
| Two candidate `r`s, one with `\|r\| < 1` and one with `\|r\| ≥ 1` | Reject the divergent one. (2018 Q4 was exactly this — pick `x = 8` over `x = 1`) |

> 🚨 Tested 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2024 DF — every other year, on average.

### 3. "Smallest `n` for which `Tₙ < bound`" — take logs, watch the sign-flip

The geometric-decay pattern. For `0 < r < 1`:

1. Write `a·r^(n−1) < bound`.
2. **Take logs of both sides** (IL-5 — load-bearing toolkit cross-strand).
3. **Divide by `log(r)`**, which is **negative** since `r < 1` — **inequality flips**.
4. Round **up** to the next integer (smallest `n` strictly greater than the algebraic answer).

> 🚨 Paul (sequences-series-8 [09:30]): *"ignore the inequality and ... actually work out what is the value for n for which Tₙ is equal to 0.01. When I get that value at the end I can then deduce whether I need to round up or round down."* Tested 2017, 2021, 2024 DF, 2025 DF.

### 4. `Sₙ > bound` for an arithmetic series ⇒ quadratic inequality

For arithmetic, `Sₙ = (n/2)[2a + (n−1)d]` is **quadratic in `n`**. When asked "for what `n` does `Sₙ > K`?", set up `Sₙ = K`, expand to `An² + Bn − K = 0`, solve via the quadratic formula (page 20), take the positive root, round up.

> 🚨 2025 P1 was this exact pattern. Tested heavily in the 2020/2025 algebra–S&S crossover. Algebra-9 (quadratic formula) is the load-bearing partner.

### 5. Limits as `n → ∞` — divide every term by the highest power of `n`

Calculation Type 2 from F&G-10 / S&S-14. For `lim_{n→∞} (3n² + 5)/(2n² − n + 1)`:

```
divide top and bottom by n²:   (3 + 5/n²) / (2 − 1/n + 1/n²)  →  3/2  as  n → ∞
```

Each `(constant)/n^k` term tends to 0. Companion fact: `rⁿ → 0` whenever `|r| < 1` (which is also the `S∞` convergence condition — same idea).

> 🚨 Tested 2020, 2022, 2023, 2023 DF, 2024. Limits is the silent half of "sequences and series and limits" — easy marks if you've seen the recipe.

---

## 🎯 The 7 techniques you must execute without thinking

1. **Identify `a` and `r` (or `a` and `d`)** from the first two or three terms. For geometric, always verify `T₂/T₁ = T₃/T₂` — if it doesn't, the sequence isn't geometric.
2. **Prove a sequence is arithmetic / geometric** by Method 1 (show the constant-difference / constant-ratio relation directly) or Method 2 (derive `Tₙ`, then compute `Tₙ₊₁ − Tₙ` or `Tₙ₊₁/Tₙ` and show it doesn't depend on `n`).
3. **"Find `a` and `r`" simultaneous equations.** Given two equations like `Tₚ = X` and `Tq = Y`, divide them — `a` cancels — solve for `r`, then back-substitute (sequences-series-7).
4. **Slice-sum trick.** `S_m − S_k` = sum of terms from `T_{k+1}` to `T_m`. Useful when the question asks for a partial range, e.g. "sum of terms 10 to 20".
5. **Patterns method (quadratic / cubic).** Build a difference table. Constant 2nd diff ⇒ quadratic; constant 3rd diff ⇒ cubic. Use `2a = constant 2nd diff` (or `6a = constant 3rd diff`), then 2 (or 3) simultaneous equations from `T₁, T₂` (and `T₃`) to get the remaining coefficients.
6. **Recurring decimal → fraction via `S∞`.** Write the recurring block as a geometric series with first term = block/10^(block length) and ratio = 1/10^(block length); apply `S∞` (sequences-series-9).
7. **Induction proof of `Sₙ`.** The 4-step framework — *Prove P(n) is true for n = 1; Assume P(n) is true for n = k; Hence, prove P(n) is true for n = k+1; Conclusion* — applied to the arithmetic or geometric sum formula (sequences-series-10). Requires the full Induction §1–6 chapter as prerequisite.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Applying `S∞` without checking `\|r\| < 1` | State the check explicitly. If `\|r\| ≥ 1`, the series diverges — answer "does not exist" |
| Picking the wrong `r` when two candidates exist (e.g. `r = 1/2` vs `r = 2`) | If the question mentions `S∞`, pick `\|r\| < 1`. That's the rejection criterion |
| Forgetting to flip the inequality when dividing by `log(r)` with `r < 1` | `log(0.9) < 0` — dividing by a negative flips the inequality |
| `Tₙ` vs `Sₙ`: using `Tₙ = a + (n−1)d` when the question asks for the sum | Read carefully. "The 10th term" → `Tₙ`. "The sum of the first 10 terms" → `Sₙ` |
| Year-indexing off-by-one (5 years compounding ≠ `T₅`) | Write out Year 0, Year 1, Year 2… in a table before applying `Tₙ` |
| Patterns: mistaking the constant 2nd difference for `a` itself | The constant 2nd difference equals **2a**, not `a`. Halve it |
| Solving `Sₙ > K` and rounding down | The smallest `n` for which `Sₙ > K` is the ceiling of the algebraic answer — round **up** |
| `Sₙ` formula direction: using `(rⁿ − 1)/(r − 1)` when `r < 1` | Both forms are equivalent. The `(1 − rⁿ)/(1 − r)` form keeps numerator positive when `r < 1` |
| Mixing AP and GP formulas (they sit next to each other on p. 22) | Read the formula line carefully — different `T` and `S` for each |
| For `S∞` on alternating series, treating `r = −1/3` as divergent | `\|r\|` = `1/3` < 1, so it converges. The sign of `r` doesn't affect convergence, only the magnitude |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Show that the sequence is arithmetic / geometric"* | Method 1 — show `T₂ − T₁ = T₃ − T₂` (or ratio version). Name the method |
| *"Find the value of `n` for which `Tₙ = K`"* | Set `a + (n−1)d = K` (AP) or `a·r^(n−1) = K` (GP); for GP take logs |
| *"Find the smallest `n` for which `Tₙ < bound`"* (decaying GP) | Take logs, flip inequality (since `log(r) < 0`), round up |
| *"Find the sum to infinity"* | Verify `\|r\| < 1`, then apply `S∞ = a/(1−r)` |
| *"For what value of `x` does the series have a sum to infinity?"* | Solve `\|r(x)\| < 1` — usually a linear or quadratic inequality on `x` |
| *"Find `n` such that `Sₙ > bound`"* (AP) | Set up `(n/2)[2a + (n−1)d] = bound`, solve quadratic, round up |
| *"Express the recurring decimal as a fraction"* | Decompose as a geometric series, apply `S∞` |
| *"Prove by induction that …"* | 4-step framework — *Prove P(n) is true for n = 1; Assume P(n) is true for n = k; Hence, prove P(n) is true for n = k+1; Conclusion* |
| *"Find the limit as `n → ∞`"* | Divide top and bottom by highest power of `n`, send each `c/n^k → 0` |
| *"Verify that the second difference is constant"* | Build a difference table; state "second difference = …" explicitly |

---

## 💡 Three exam-day tips that move the needle

1. **State the convergence check before applying `S∞`.** Two lines: "`|r| = … < 1`, so `S∞` exists" then the formula. The check is worth a method mark every time and prevents you from applying the formula to a divergent series.

2. **Build a table for indexed problems.** Whenever the question mentions Year 0 / Year 1 / month 1 / repayment 1, write the first three rows of the table before reaching for `Tₙ`. The off-by-one error vanishes once the table is in front of you.

3. **For Section B Q7 financial-maths, set up `a`, `r`, and `n` first — then read the question again.** Q7 is dense with context; the maths only starts after you've identified the geometric structure underneath the words. The annuity / amortisation formulas are geometric-series sums in disguise.

---

## 🔗 Cross-strand connections (where else S&S fires)

- **S&S ↔ Financial Maths** — the annuity formula and the amortisation formula (Paper 1 Proofs §4) are direct geometric-series applications. Q7 of Section B in financial-maths years (2017, 2020, 2023, 2024, 2024 DF, 2025 DF) is essentially an S&S question with a money skin.
- **S&S ↔ Indices and Logs** — `Tₙ = a·r^(n−1) < bound` always demands IL-5 (take logs to bring `n` down). Sign-flip rule from IL-5/algebra-6 fires when `log(r) < 0`.
- **S&S ↔ Algebra** — `Sₙ > bound` for an AP is a quadratic inequality in `n` (2025 P1; 2020 P1). Algebra-9's quadratic formula is the partner.
- **S&S ↔ Functions and Graphs (§10 Limits)** — sequences-series-14 is the cross-listing. F&G-10 is the canonical home of limits at infinity (Calculation Type 2: divide by highest power of `n`).
- **S&S ↔ Induction** — sequences-series-10 is the prescribed induction proof of the geometric `Sₙ` formula. Requires the full Induction chapter as prerequisite.
- **S&S ↔ Paper 1 Proofs** — sequences-series-15 is the direct-limit proof of `S∞` (Paper 1 Proofs §5). One of the **five prescribed Paper 1 proofs** that can be asked verbatim. Sum-of-geometric-series proof appeared in 2015.
- **S&S ↔ Complex Numbers** — sum of the `n`-th roots of unity = geometric series sum (2015 P1).
- **S&S ↔ Number Theory** — recurring decimals as rationals via `S∞` (sequences-series-9).

> S&S is the strand that lets the financial-maths question be a question at all. Most of the "30+ marks Section B" payoffs in P1 are S&S in disguise.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Page-22 formulas applied with correct `a`, `r`, `d`, `n` | S&S 1, 5 | every year (11/11) |
| `\|r\| < 1` mandatory check before `S∞` | S&S 8 | 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2024 DF |
| "Smallest `n` for `Tₙ < bound`" — logs + sign-flip | S&S 5–8 + IL 5 | 2017, 2021, 2024 DF, 2025 DF |
| `Sₙ > bound` (AP) → quadratic inequality | S&S 3 + algebra-9 | 2020 P1, 2025 P1 |
| Limit as `n → ∞` — divide by highest power | S&S 14 / F&G 10 | 2020, 2022, 2023, 2023 DF, 2024 |
| Year-0 vs year-1 indexing | S&S 5 + financial-maths | 2017, 2020, 2022 DF, 2024 |
| Patterns 1 & 2 — second/third differences | Patterns 1, 2 | 2018, 2025 (Method 3 in MS) |
| Induction proof of `Sₙ` | S&S 10 + Induction 5 | 2025 P1 Q5 |

> If you've internalised everything in this row, you've insured ~80% of the S&S marks on the next paper — and most of the financial-maths Q7 marks as well.
