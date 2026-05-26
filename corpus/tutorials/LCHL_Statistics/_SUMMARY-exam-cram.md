# Statistics — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Statistics before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Statistics deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Statistics appears in 11/11 years on Paper 2.** Average ≈ **6.5 parts per paper**. Total: **71 P2 parts** across 11 years — the second-biggest P2 strand after Probability.
- **Section B–heavy: 45 parts in Section B vs 26 in Section A.** Statistics questions are almost always contextual — they wrap your z/CI/HT machinery in a real-world story about lions, polls, factory output, or exam results.
- **Recent surge.** P2 statistics parts: 5 (2019), 7 (2020), 4 (2021), 5 (2022), 7 (2023), **8 (2024), 10 (2025)** — plus **12 parts in the 2024 DF paper**. Plan as if 2026 is statistics-heavy too.
- **Cross-strand reach.** Statistics shares the page-36/37 z-table with the Bernoulli normal approximation, the page-33 standard-deviation formula with Probability, and algebra-14 manipulation whenever you solve `1/√n ≤ X` for `n`.

**The takeaway.** Half of every Section B paper is a Statistics story with a CI, a z-test, or both at the bottom. The same five formulas drive all of it.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Standardising formula — single value vs sample mean** | 15 min | statistics-13 + statistics-14 — 18 + 9 P2 citations; the single most-mistaken distinction on the paper |
| **Confidence intervals (mean + proportion)** | 15 min | statistics-17 — 14 P2 citations; mean CI `x̄ ± 1.96·σ/√n`, proportion CI `p̂ ± 1.96·√(p̂(1−p̂)/n)` |
| **Hypothesis testing — full z-test recipe** | 15 min | statistics-19 — 11 P2 citations; "the master video of the inferential strand" |
| **CI-HT duality (Stat 21) + p-values (Stat 20)** | 10 min | statistics-21 + statistics-20 — tested 2015, 2019, 2022, 2024, 2025; the "is the claim inside the CI?" shortcut |
| **Empirical Rule + the fill-the-curve-first method** | 10 min | statistics-8 — tested every year wherever "normally distributed" appears |
| **Descriptive stats — mean/median/IQR/SD calculator drill** | 10 min | statistics-3 — 9 P2 citations; the Casio 1-VAR routine |
| **Margin of error + scatter/correlation refresher** | 10 min | statistics-16 (2015/16/20) + statistics-5 (8 P2 citations); the line-of-best-fit through `(x̄, ȳ)` rule |

---

## 📊 Top tutorials by exam frequency (P2 main, 11 years)

| Rank | Tutorial | P2 citations | What it tests |
|---|---|---|---|
| 1 | `statistics-13` Standardising Formula | **18** | `z = (x − μ)/σ` — convert raw value to standard normal |
| 2 | `statistics-17` Confidence Intervals | **14** | `x̄ ± 1.96·σ/√n` (mean), `p̂ ± 1.96·√(p̂(1−p̂)/n)` (proportion) |
| 3 | `statistics-19` Hypothesis Testing | **11** | Two-tailed z-test; the ±1.96 critical-region decision rule |
| 4 | `statistics-14` Standardising Sample Means | 9 | CLT in practice — `σ/√n` not `σ` when the question says "sample" |
| 5 | `statistics-3` Mean / Median / IQR / SD / Percentiles | 9 | Descriptive measures; the page-33 SD formula |
| 6 | `statistics-5` Scatter Graphs + Correlation Coefficient | 8 | Line of best fit through `(x̄, ȳ)`; `r` via calculator |

> **Read this as:** if you only have 90 minutes, tutorials 1–4 alone account for **52 cited appearances** across Paper 2. Almost every Section B statistics question routes through them.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 33** | `σ = √( Σ(x − μ)² / n )` (population SD) | Show-the-formula calculations; SEC sometimes asks for the manual route, not just the calculator answer |
| **p. 34** | `x̄ ± 1.96·σ/√n` and `p̂ ± 1.96·√(p̂(1−p̂)/n)` | Confidence-interval construction (Stat 17 and Stat 21) |
| **p. 36/37** | Standard normal CDF `Φ(z) = P(Z ≤ z)` | Every z-score lookup. Tables are **left-tail only**, two decimal places |

> **🎯 The tables only tabulate left-tail for `z ≥ 0`.** Upper-tail (`P(Z ≥ a) = 1 − Φ(a)`) and negative-z (`Φ(−a) = 1 − Φ(a)`) come from symmetry — see techniques 3 and 4 below.

---

## 📚 Learning work — what must be in your head before you sit down

The items the log tables **don't** give you. Drill until automatic.

### 1. The Empirical Rule percentages — 68, 95, 99.7

Memorise as a phone number. Per statistics-8: *"the percentages **never change**. Every empirical-rule question has the exact same bell curve underneath it. The only thing that changes is the numbers along the x-axis."*

```
... | 0.15% | 2.35% | 13.5% | 34% | 34% | 13.5% | 2.35% | 0.15% | ...
   −3σ    −2σ      −σ       μ       +σ      +2σ       +3σ
```

> Within ±1σ → 68%. Within ±2σ → 95%. Within ±3σ → 99.7%. Outside ±2σ → 5% (half above, half below = 2.5% each tail).

### 2. The 1.96 ↔ 95% anchor

`P(−1.96 ≤ Z ≤ 1.96) = 0.95`. The same 1.96 drives every CI, every two-tailed HT critical region, and every margin of error at LCHL. At 95% confidence the multiplier is **always 1.96** — never 2.

### 3. CLT in one sentence

> *"If 30 or more sample means of a particular set of data are calculated, the graph of the sample means (x̄) will always form a normal curve."* (statistics-18, verbatim.)

Consequence: SD of the sample mean is `σ/√n`, **not** `σ`. **The size of the population does not matter** — only the sample size. This second insight is a 5–10 mark SEC question on its own.

### 4. The two-tailed hypothesis-test template

Status quo `H₀: parameter = claimed value` with equality. Alternative `Hₐ: parameter ≠ claimed value` with `≠` (never `>` or `<` at LCHL). Compute `z`. If `|z| > 1.96` → **reject H₀**. If `|z| ≤ 1.96` → **fail to reject H₀**.

---

## 🚨 LOAD-BEARING — the five things that win or lose the statistics question

### 1. Empirical Rule precondition — "normally distributed"

> 🚨 statistics-8 content warning: *"the empirical rule ONLY applies if the data is normally distributed. The question MUST contain the phrase 'normally distributed' for the empirical rule to be available."*

If the question doesn't say normal, you cannot use 68/95/99.7. The default tool at HL is z-scores. **Using the empirical rule when the question doesn't permit it loses marks even if the arithmetic is right.**

Paul's method (statistics-8): **fill in all eight regions BEFORE you read the question parts.** Every sub-part then reduces to adding percentages off your diagram. Tested every year a normality question appears.

### 2. `σ` vs `σ/√n` — the most-marked single distinction

| Question wording | Formula | Why |
|---|---|---|
| *"a randomly chosen student"*, *"one lion"*, *"a single bulb"* | `z = (x − μ)/σ` | Single observation — statistics-13 |
| *"a sample of n has an average / mean of …"* | `z = (x̄ − μ)/(σ/√n)` | Sample mean — statistics-14, by CLT |

> 🚨 statistics-19 confusion 6: *"You MUST divide by σ/√n, not σ. The standard error of a sample mean is σ/√n, not σ. Forgetting the /√n is the most common single error on Stat 19-shaped questions; SEC marking schemes deduct 2–3 marks for it."* Look for "sample of" + "average / mean" — that's the trigger to add `/√n`.

### 3. Confidence-interval pair (mean and proportion)

```
mean:        x̄ ± 1.96 · σ/√n          (when σ given; LCHL almost always)
proportion:  p̂ ± 1.96 · √(p̂(1−p̂)/n)   (estimation context — Stat 17)
proportion:  p₀ ± 1.96 · √(p₀(1−p₀)/n) (testing context — Stat 21, uses hypothesised p₀)
```

> 🚨 **Read the noun.** *"Average / mean"* → mean CI. *"Proportion / percentage / fraction"* → proportion CI. Convert percentages to decimals first (35% → `p̂ = 0.35`). Interpretation language matters: *"We are 95% confident that the true population [mean / proportion] lies between [low] and [high]"* — **not** *"there is a 95% probability that μ lies in this range"* (μ is a fixed unknown, not a random variable).

Tested 14× across the 11-year window; pair with Stat 21 (CI-HT duality) for the heaviest Section B question on most papers.

### 4. CI-HT duality (Stat 21) — the shortcut decision rule

> A 95% CI captures all parameter values that would **not** be rejected by a two-tailed 5% z-test. So:
>
> - **Hypothesised value inside the CI** → fail to reject `H₀`.
> - **Hypothesised value outside the CI** → reject `H₀`.

🚨 All three decision rules — critical region (`|z| > 1.96`), p-value (`p < 0.05`), CI containment — give **identical** decisions on the same data. SEC questions can ask for any of the three; know all three. Tested 2015, 2019, 2022, 2024, 2025.

### 5. Margin of error — exact vs `1/√n` conservative

| Use exact formula when… | Use `1/√n` (conservative) when… |
|---|---|
| Question gives a specific `p̂` (e.g. "436 of 1000 prefer A") | Question gives only `n` and asks for a generic margin |
| Numerical context: `1.96·σ/√n` for means | Categorical context with no `p̂`: derived by setting `p̂ = 0.5` (max of `p(1−p) = 0.25`) |

> 🚨 The `1/√n` formula is the **worst-case** margin and is what poll articles quote. Sample-size design questions — *"What `n` is needed for ME ≤ 3%?"* — solve `1/√n ≤ 0.03` for `n` (= ~1,100). Tested ~7/11 years; classic 2015, 2016, 2020 wording.

---

## 🎯 The seven techniques you must execute without thinking

1. **Casio 1-VAR routine** for `μ, σ, x̄`. Mode → STAT → 1-VAR → enter data → AC → Shift 1 → use `σx` (population SD), **not `sx`** (sample SD). SEC always wants `σx`. Lose 2 marks if you give sample SD.
2. **Page-33 SD formula by hand** — 5 steps: subtract mean, square, sum, divide by `n`, square root. Show every column; SEC awards method marks even if final answer is off.
3. **Negative-z and upper-tail lookups via symmetry.** `Φ(−a) = 1 − Φ(a)`; `P(Z ≥ a) = 1 − Φ(a)`. The tables are left-tail and `z ≥ 0` only.
4. **Two-decimal z rounding.** `z = 1.834` → look up 1.83. Mark scheme allows interpolation but two-decimal is universal.
5. **Paired-diagram convention for z-questions.** Draw the real-units curve AND the standard-normal curve, side by side, shade the same region on both. SEC mark schemes allocate 1–2 marks for the diagram itself.
6. **Fill-the-curve-first for Empirical Rule questions.** All eight regions before you read any sub-part. Then every part is just "add these regions".
7. **Line of best fit MUST pass through `(x̄, ȳ)`.** statistics-5 content warning: *"the line of best fit MUST go through the average point. This is non-negotiable. Marker awards no marks for a line of best fit that doesn't pass through `(x̄, ȳ)`."* Compute `(x̄, ȳ)` first, plot it, then draw the line.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Using `σ` when the question says "sample of n has an average" | Standard error is `σ/√n` for sample means. Always. |
| Using `p̂` in the SE for a hypothesis test where `p₀` is given | Estimation context → `p̂`; testing context → hypothesised `p₀` |
| Plugging a percentage straight into the proportion CI formula | Convert first: 35% → `p̂ = 0.35` |
| "We have proved H₀ is true" / "we have proved Hₐ" | Statistical tests never prove. Use *"sufficient / insufficient evidence to reject"* |
| `z = +1.95` → reject | Strictly: `|z| > 1.96` to reject. `1.95` fails to reject — no "almost" category at LCHL |
| Using empirical rule without "normally distributed" in the question | Default to z-scores. Empirical rule needs the explicit normality phrase |
| Reading `z = 1.834` as `1.84` on the table | Round to two decimals: look up `1.83` |
| Population SD `σx` vs sample SD `sx` on the calculator | SEC always uses `σx`. Don't tap the wrong one |
| Forgetting variance vs SD: question gives `σ² = 49`, you plug 49 | Take √ first: `σ = 7` |
| Forgetting to interpret in context after computing a CI | "We are 95% confident the true mean lies between X and Y kg" — the units matter for the 5-mark interpret step |
| Line of best fit not through `(x̄, ȳ)` | No marks. Compute average point, plot, then draw |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"normally distributed"* + nice tick-marks at integer σ | Empirical rule. Fill-curve-first method |
| *"a randomly chosen X"* (single object) | `z = (x − μ)/σ`. Stat 13 |
| *"a sample of n has an average / mean of …"* | `z = (x̄ − μ)/(σ/√n)`. Stat 14 |
| *"construct a 95% confidence interval for the [mean / proportion]"* | CI formula from page 34. Then interpret in real units |
| *"test at the 5% level whether …"* | Full z-test: state `H₀, Hₐ`, compute `z`, compare to ±1.96, conclude in context |
| *"use the confidence interval to test the claim that μ = X"* | Stat 21. Is `X` inside the CI? If yes → fail to reject. If no → reject |
| *"what is the p-value?"* / *"using the p-value method"* | Stat 20. Two-tailed: `p = 2·(1 − Φ(\|z\|))`. Reject if `p < 0.05` |
| *"find the margin of error"* (no specific `p̂` given) | Conservative `1/√n` |
| *"what sample size is needed for ME ≤ X%?"* | Solve `1/√n ≤ X` for `n` |
| *"state the Central Limit Theorem"* | Verbatim from Stat 18. 5 marks for the sentence |
| *"correlation coefficient r"* | Calculator route only. Then interpret as "strong / weak", "positive / negative", linear |

---

## 💡 Three exam-day tips that move the needle

1. **State `H₀` and `Hₐ` explicitly even if not asked.** 2–4 free marks every hypothesis test. SEC mark scheme awards the setup separately from the calculation. *"Manager's claim is the status quo: `H₀: μ = 170; Hₐ: μ ≠ 170`."*

2. **Show the standardising formula → substitute → answer.** Three lines, three method marks. *"`z = (x̄ − μ)/(σ/√n)` → `z = (167 − 170)/(6/√10)` → `z = −1.58`."* Skipping straight to `z = −1.58` risks 0 if your arithmetic is off.

3. **End every hypothesis test with a context sentence.** *"There is insufficient evidence at the 5% level to dispute the manager's claim that the average player height is 170 cm."* The interpret-in-context line is worth ~5 marks on its own — it's the cheapest sentence on the paper.

---

## 🔗 Cross-strand connections (where else statistics fires)

- **Statistics ↔ Probability** — every P2 paper has a normal-distribution probability part feeding into Bernoulli or expected-value follow-ups. The page-36/37 lookup is shared territory.
- **Statistics ↔ Algebra** — sample-size design (`1/√n ≤ X`) is an algebra-14 manipulation problem in disguise; CI-width inequalities reduce to solving `√n ≥ k`.
- **Statistics ↔ Sampling / Data Types (Stat 1 + Stat 2)** — short Section A items asking *"name the sampling method"* or *"is this categorical or numerical?"* are reliable 5-mark pickups. Stratified sampling tested 2025 P2.
- **Statistics ↔ Probability (Bernoulli)** — when `n` is large and `np`, `n(1−p) > 5`, Bernoulli answers are computed via the normal approximation using z-tables. The same Stat 13 standardising machinery.
- **Statistics ↔ Functions & Graphs** — `p(1−p)` is a downward parabola with vertex at `p = 0.5` (max `0.25`); the *"why is ME largest at p = 0.5?"* question is a calculus-style argument inside a statistics shell (Stat 18).

> Statistics is rarely tested in isolation. Each Section B story arc pulls in sampling, probability, and algebraic manipulation in turn.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Empirical Rule (68-95-99.7) | statistics-8 | every year a normality question appears; explicit 2017, 2018, 2025 |
| Standardising single value `z = (x − μ)/σ` | statistics-13 | tested ~every year — 18 P2-main citations |
| Sample-mean standardising `σ/√n` (CLT) | statistics-14 + statistics-18 | ~10/11 years |
| Confidence interval for mean / proportion | statistics-17 | 12/11 years (14 citations); recurring on every paper |
| Two-tailed z-test (`|z| > 1.96`) | statistics-19 | every year a hypothesis test appears; 11 P2 citations |
| CI–HT duality ("is the claim inside the CI?") | statistics-21 | 2015, 2019, 2022, 2024, 2025 |
| p-value method | statistics-20 | 2017, 2018, 2025 (main + DF) |
| Margin of error — `1/√n` conservative | statistics-16 | 2015, 2016, 2020 confirmed; ~7/11 years per trends |
| Mean / median / IQR / SD on the calculator | statistics-3 | every year a descriptive-stats sub-part appears; 9 P2 citations |
| Line of best fit through `(x̄, ȳ)` + `r` | statistics-5 | 8 P2 citations; recurring Section A item |

> If you've internalised everything in this table, you've insured ~85% of the statistics marks on the next paper.
