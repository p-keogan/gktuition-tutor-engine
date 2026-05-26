# Indices and Logs — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Indices and Logs before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Indices and Logs deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Indices and Logs appears in 10/11 years on Paper 1** (missing only 2015). Average ≈ 4 parts per paper. Total: **44 P1 parts**.
- **`indices-logs-5-unknown-in-power-natural-log` is the single most-cited tutorial in the entire 1,212-part P1 corpus** — **31 citations**, about 7% of every P1 paper touches IL-5 specifically. Paul's framing at [00:09]: *"this is the most important video that we're going to explore on logs because what we're going to do in this video is going to crop up in almost every single topic in maths."* The data validates the claim.
- **2024–25 looks stable, not surging.** Yearly P1 counts: 0-5-4-5-1-**7**-3-**7**-4-3-5 for 2015–2025. The 2020 and 2022 papers were peak years (7 parts each); 2024–25 sit at 3 and 5 — slightly below average. Plan as if 2026 will be a "normal" year (~4 parts), with the bulk of the work hidden inside other strands.
- **Cross-strand reach is the real story.** IL-5 is the spine of S&S ("smallest `n` with `Tₙ < bound`"), Financial Maths ("how many years"), Differentiation (simplify `ln(x³) → 3 ln(x)` before differentiating), Integration (`∫ 1/x dx`, `∫ e^(kx)`), and Algebra (exponential equations).

**The takeaway.** IL marks themselves look modest (~4 parts/year), but IL techniques are the silent half of half of Paper 1. If `n` is in the exponent anywhere on the paper, IL-5 fires.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **IL-5: take logs to bring the unknown down from the power** | 25 min | 31 P1 citations — **the most-cited tutorial in the entire P1 corpus**. Every paper touches it |
| **IL-3: the three rules of logs (product / quotient / power)** + IL-2 (log-index conversion) | 15 min | 13+ P1 citations combined; tested every year since 2016 |
| **IL-4: change of base — "big number on top", "go down not up"** | 10 min | tested 2018, 2021, 2023, 2023 DF, 2024 DF |
| **IL-6 + IL-7: the `y = aˣ` quadratic-in-disguise substitution** | 10 min | tested 2016, 2021, 2022, 2025 DF |
| **IL-1: rules of indices on page 21** (fractional, negative, zero exponents) | 10 min | the JC base layer that powers all higher work |
| **The inequality-flip when dividing by `ln(r)` with `r < 1`** | 5 min | recurring trap — tested 2017, 2018, 2020, 2021, 2022, 2022 DF, 2024 |
| **Quick-fire:** `ln/e` inverse pair, `log_a(a^k) = k`, `aˣ = y ⇔ x = logₐ y` | 10 min | the three identities that make every IL question collapse |

---

## 📊 Top tutorials by exam frequency (P1 main, 11 years)

| Rank | Tutorial | P1 citations | What it tests |
|---|---|---|---|
| 1 | `indices-logs-5` Unknown in the Power / Natural Log | **31** | Take logs to bring the unknown out of the exponent; `ln(e^x) = x` |
| 2 | `indices-logs-2` Rules of Logs Part 1 | **13** | Log–index conversion `logₐ y = x ⟺ aˣ = y`; the anchor identities |
| 3 | `indices-logs-3` Rules of Logs Part 2 | ~10 | Product, quotient, power rules (same base required) |
| 4 | `indices-logs-4` Changing the Base | ~5 | Change-of-base formula; tested in surd-form log problems |
| 5 | `indices-logs-1` JC Revision | ~5 | The 8 rules of indices on page 21 |
| 6 | `indices-logs-6` Quadratic Equations 1 | ~3 | Substitute `y = aˣ` — quadratic in disguise |
| 7 | `indices-logs-7` Quadratic Equations 2 | ~2 | Same pattern, with negative exponents |
| 8 | `indices-logs-8` Log Problems | ~1 | Log-log linearisation of power laws |

> **Read this as:** IL-5 alone accounts for 31 cited appearances — more than any other tutorial in the entire P1 corpus. IL-5 + IL-2 + IL-3 together account for ~54 P1 citations. Skip IL-5 at your peril. (Counts 3, 5, 6–8 are grep-derived estimates; the trends file gives exact figures for 1, 2, 4.)

---

## 📖 Log tables — the pages you'll actually flip to

> **🎯 Page 21 is the entire strand.** Paul's "four corners" of page 21:

| Page 21 region | Content | Tutorial |
|---|---|---|
| **Top left** | 8 rules of indices (`a⁰ = 1`, `a⁻ⁿ = 1/aⁿ`, `aᵐ · aⁿ = a^(m+n)`, etc.) | IL-1 |
| **Top right** | Log–index conversion `logₐ y = x ⟺ aˣ = y` (the defining identity) | IL-2 |
| **Middle column** | Product: `logₐ(xy) = logₐ x + logₐ y`. Quotient: `logₐ(x/y) = logₐ x − logₐ y`. Power: `logₐ(xⁿ) = n · logₐ x`. | IL-3 |
| **Right column** | Change of base: `logₐ x = log_b x / log_b a` | IL-4 |

| Other pages | Formula | When to use |
|---|---|---|
| p. 20 | Quadratic formula | After IL-6 substitution yields a quadratic in `y` |
| p. 21 | `e ≈ 2.71828…` and `ln` is `logₑ` | Natural-log context (IL-5) |

> **🎯 The defining identity is page 21, top right.** `logₐ y = x ⟺ aˣ = y` — *"the log asks: what power?"*. Every IL technique reduces to this conversion. If you remember nothing else, remember this.

---

## 📚 Learning work — what must be in your head before you sit down

The log tables give you the formulas. These are the **bonus identities** and **anchor values** that make the formulas collapse cleanly.

### 1. The bonus identities — `log_a(a^k) = k` and `ln(e^k) = k`

Direct consequences of the defining identity. They're what makes "take logs of both sides" actually simplify the algebra.

- `log_a(a) = 1` (because `a¹ = a`)
- `log_a(1) = 0` (because `a⁰ = 1`)
- `log_a(a^k) = k` for any `k`
- `ln(e^k) = k` and `e^(ln k) = k` — the `ln/e` inverse pair

> Paul (IL-5 [00:09]): *"In any topic in maths if the unknown is in the power you can use logs in order to eliminate the power."* The bonus identities are the cleanup step that makes it land.

### 2. The "any base works" rule (and which to choose)

When the unknown is in the exponent, you can take logs in **any base** — `ln`, `log₁₀`, `log₂` — and the answer is the same. Choose the base that matches the equation:

- Base is `e` (i.e. `e^(stuff)`) → use `ln` (because `ln(e^k) = k` is exact, no calculator look-up)
- Base is `10` or unspecified → use `log₁₀` (calculator default)
- Base is a specific integer like 3 or 5 → either `log₁₀` or `ln` works; pick whichever your calculator is set to

> Paul (IL-5, 2026 pedagogical regret flagged in tutorial): the IL-5 video uses `ln` for all worked examples, which can make students think `ln` is mandatory. **It isn't.** `log₁₀(2^x) = log₁₀(8)` works exactly as well as `ln(2^x) = ln(8)` — both give `x = 3 log 2 / log 2 = 3`.

### 3. The same-base constraint on combining logs

The product, quotient, and power rules **only fire when the bases match**.

> Paul (IL-3 [00:19]): *"Notice that I always am going to have the same base in all of these. The base is always A."* You cannot combine `log₂(8) + log₃(9)` directly. When bases differ, you need **change of base** (IL-4) first.

### 4. The change-of-base mnemonic — "big number on top, go down not up"

`logₐ x = log_b x / log_b a`. The **argument** goes on top of the new fraction; the **original base** goes on the bottom. The intermediate base `b` is your choice — and you should choose **smaller**, not larger.

> Paul (IL-4 [01:21]): *"The big number goes on the top, the small number goes on the bottom."* And [06:30]: *"go down not up"* — when you have a choice between converting to base 2 or base 10 (say), pick the smaller. Smaller intermediate bases produce cleaner numbers.

### 5. The reject-negative-argument rule

Logs are only defined for **positive** arguments. After solving any log equation, **test each candidate against the original log expressions** and reject any that produces `log(negative)` or `log(0)`.

> Paul (IL-3 [05:57]): *"x can't be negative in this case. 6 to the power of anything will never give me a negative value. So I can't have the log of minus 9 to the base 6 — it's impossible."* Standard quadratic-in-log trap.

---

## 🚨 LOAD-BEARING — the five things that win or lose the IL question

### 1. "Unknown in the exponent" → take logs of both sides

The single most-tested rule on Paper 1 (across all strands). Pattern: `a · b^(stuff with x)` `= constant`. Steps:

1. Isolate the exponential.
2. Take logs of both sides (any base; `ln` if the base is `e`).
3. Use the **power rule** `log(b^k) = k · log(b)` to bring the unknown out front.
4. Divide by `log(b)` to isolate the unknown.

> 🚨 Tested **every year since 2016**. Inside S&S, Financial Maths, Differentiation (rate problems), Algebra (exponential equations) — IL-5 fires across at least 4 strands per paper.

### 2. Inequality flips when dividing by `log(r)` with `r < 1`

If `r < 1`, then `log(r) < 0` (because `log(1) = 0` and `log` is increasing). Dividing both sides of an inequality by a negative number **flips the inequality direction**.

> 🚨 Paul (referenced in 2017 P1 grep): *"log of a number less than 1 is negative, so dividing by it FLIPS the inequality."* Tested 2017, 2018, 2020, 2021, 2022, 2022 DF, 2024 P1.

Standard trigger: "find the smallest `n` such that `(0.9)^n < threshold`" — the answer requires both taking logs AND flipping the inequality. Missing the flip gives the wrong direction every time.

### 3. The log-index conversion `logₐ y = x ⟺ aˣ = y`

The page-21 top-right identity. Every log equation eventually reduces to this conversion. Standard application: given `log₃ t = 24/5`, convert to `t = 3^(24/5)`.

> 🚨 Paul (IL-2 [01:00]): *"the base to the power of the answer is equal to whatever this number is."* Tested 2016, 2020, 2021, 2023, 2023 DF, 2024 DF, 2025 P1, 2025 DF — basically every log-equation question.

### 4. The change-of-base formula (page 21, right column)

When two logs in the same equation have **different bases**, neither the product nor the quotient nor the power rule applies. Apply change of base FIRST to make every log share a base, THEN combine.

```
logₐ x = log_b x / log_b a    (b is your choice — pick the smaller)
```

> 🚨 Tested 2018, 2021, 2023, 2023 DF, 2024 DF. The 2023 DF P1 problem was the telescoping product `∏(log_k(k+1))` — pure change-of-base machinery.

### 5. The `y = aˣ` substitution for "quadratic in disguise" exponentials

When the equation has both `a^(2x)` (or `a^x · a^x`) and `aˣ` terms, **substitute `y = aˣ`** to get a quadratic in `y`. Solve the quadratic (page 20), back-substitute, take logs to recover `x`.

> 🚨 Paul (IL-6): *"the trick is to spot when an exponential equation is secretly a quadratic in disguise."* Tested 2016 P1, 2021 P1 (3^(2m+1) version), 2022 P1, 2025 DF P1. IL-7 is the same pattern with negative exponents (`a^(−x) = 1/aˣ`).

Watch for the after-the-substitution step: reject any `y ≤ 0` since `aˣ > 0` always. Then take logs to extract `x`.

---

## 🎯 The 7 techniques you must execute without thinking

1. **Convert log → index.** `logₐ y = x` becomes `aˣ = y`. Do this whenever a log equation has resolved to "log of something equals a number".
2. **Take logs of both sides.** Whenever the unknown is in an exponent. Use `ln` if the base is `e`; `log₁₀` otherwise.
3. **Bring the power down.** `log(a^k) = k · log(a)`. The power-rule step is what isolates the unknown.
4. **Combine logs into one.** Product/quotient/power rules in **reverse**: `log A + log B = log(AB)`, etc. Same base required.
5. **Change the base.** When bases differ, `logₐ x = log_b x / log_b a`. Pick `b` smaller than `a` ("go down not up").
6. **Substitute `y = aˣ`.** For quadratic-in-disguise equations. Solve the quadratic in `y`, reject negatives, take logs to recover `x`.
7. **Simplify the log BEFORE differentiating or integrating.** `ln(x³) → 3 ln(x)` before applying `d/dx`. Saves a chain-rule step.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Combining `log A + log B` when the bases differ | Same-base rule. Change base first |
| Taking logs but forgetting to apply the power rule | Step after `log(a^x) = log K` is `x · log(a) = log K`, then divide |
| Forgetting the inequality flip when dividing by `log(r)` with `r < 1` | `log(0.9) < 0` — flip the inequality |
| Keeping a negative `x` from a log equation | Logs of negatives are undefined. Reject; back-substitute the positive candidate |
| `log(x²) = 2 log(x)` — but only for `x > 0` | The power rule needs positive arguments. If `x` could be negative, write `log(x²) = 2 log\|x\|` |
| `aᵐ · aⁿ = a^(mn)` (wrong) | Multiplication of bases ADDS exponents: `aᵐ · aⁿ = a^(m+n)`; power-of-a-power MULTIPLIES: `(aᵐ)ⁿ = a^(mn)` |
| `ln(A + B) = ln A + ln B` (wrong) | The product rule is for `ln(AB)`, not `ln(A+B)`. There is no log-of-a-sum rule |
| Mixing `log` and `ln` mid-equation | Pick one base at the start; switching mid-stream introduces errors |
| Forgetting to back-substitute after `y = aˣ` | Solving for `y` gives a number; you still need `x = logₐ y` |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Solve for `x`"* + `x` in the exponent | Take logs of both sides; use power rule to bring `x` down |
| *"Solve for `t`"* in a financial/exponential model | IL-5 — `t = ln(stuff)/ln(other)`. Use `ln` if the base is `e` |
| *"Find the smallest `n` for which (decay)ⁿ < threshold"* | Take logs, **flip the inequality** (decay rate < 1 ⟹ log < 0), round up |
| *"Express as a single log"* | Combine using product/quotient/power rules (same base) |
| *"Express in terms of `log₂ 3`"* (or similar) | Change of base. Convert all logs to base 2 (or whichever is named) |
| *"Solve the equation `log_a(...) = log_a(...)`"* | De-log: arguments must be equal. Solve the resulting algebraic equation, then check for extraneous (negative) roots |
| *"Solve `aˣ + b · a^(−x) = c`"* (or similar) | Multiply through by `aˣ`, substitute `y = aˣ`, get quadratic in `y` |
| *"Show that `log₃ X = (a/b)`"* with `X` irrational | Convert to index form, use rules to manipulate, recover the fraction |
| *"Differentiate `ln(f(x))`"* with `f(x)` a power or product | Simplify the log first (power rule, product rule), THEN differentiate |
| *"Without a calculator"* | The argument is engineered to a `log_a(a^k) = k` form. Look for the matching power of the base |

---

## 💡 Three exam-day tips that move the needle

1. **Take logs at the right moment.** Before you take logs, **isolate the exponential** if you can. `3 · 2^x − 5 = 19` → first `2^x = 8`, then `x · log 2 = log 8`. Taking logs too early gives `log(3 · 2^x − 5) = log 19`, which is hopeless because there's no log-of-a-sum rule.

2. **State which rule you're applying.** "Using the power rule of logs (page 21): `log(2^x) = x · log 2`". Three words, one method mark. Examiners can't read your mind — the method marks reward visible technique.

3. **Always check for extraneous roots.** A log equation with a quadratic step almost always produces a "trap" root that gives `log(negative)` when substituted back into the original. Quick check at the end: do BOTH roots make every log in the original equation defined? If not, state which you're rejecting and why.

---

## 🔗 Cross-strand connections (where else IL fires)

- **IL ↔ Sequences and Series** — every "smallest `n` with `Tₙ < bound`" question takes logs of `a · r^(n−1) < bound`. Tested 2017, 2021, 2024 DF, 2025 DF. Without IL-5, S&S "smallest `n`" questions are unsolvable.
- **IL ↔ Financial Maths** — every "how many years until value reaches X?" question on Q7 Section B becomes `(1 + i)^t = ratio`, solved by taking logs (IL-5). Tested 2017, 2023 DF, multiple Q7 questions.
- **IL ↔ Differentiation** — simplify `ln(x³) → 3 ln(x)` BEFORE differentiating (skips a chain-rule step). Also: `d/dx[ln x] = 1/x` (Diff 9). Tested 2024 DF, 2025 P1 (line 2725).
- **IL ↔ Integration** — `∫ 1/x dx = ln\|x\| + C` (Int 2); `∫ e^(kx) dx = (1/k) e^(kx) + C` (Int 3). The IL-2 quotient rule fires in definite integrals of `ln`. Tested 2020 P1, 2023 P1, 2025 P1.
- **IL ↔ Algebra** — surd manipulation (IL-1 rules of indices); quadratic-in-disguise pattern (IL-6) shares the substitution method with algebra-2.
- **IL ↔ Number Theory** — `log` domain restriction (`x > 0`); checking that solutions are real / positive.

> IL doesn't "have a question" most years. It has a **technique** that lives inside someone else's question. Every paper.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Take logs to bring unknown out of exponent | IL-5 | every year since 2016 (10/11) |
| Inequality flips when dividing by `log(r)`, `r < 1` | IL-5 + algebra-6 | 2017, 2018, 2020, 2021, 2022, 2022 DF, 2024 |
| Log–index conversion `logₐ y = x ⟺ aˣ = y` | IL-2 | 2016, 2020, 2021, 2023, 2023 DF, 2024 DF, 2025, 2025 DF |
| Product / quotient / power rules of logs (same base) | IL-3 | 2016, 2020, 2024, 2024 DF, 2025, 2025 DF |
| Change of base — "go down not up", "big number on top" | IL-4 | 2018, 2021, 2023, 2023 DF, 2024 DF |
| `y = aˣ` substitution (quadratic in disguise) | IL-6 / IL-7 | 2016 P1, 2021 P1, 2022 P1, 2025 DF P1 |
| Simplify `ln(x^n) = n ln x` before differentiating | IL-3 | 2024 P1, 2024 DF P1, 2025 P1 |
| Reject negative argument of log | IL-3 | every log-equation-with-quadratic question |

> Internalise this row and you've insured ~85% of the IL marks — plus the IL-shaped portions of S&S, Financial Maths, Differentiation, and Integration.
