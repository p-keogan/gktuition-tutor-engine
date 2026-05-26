# Financial Maths — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Financial Maths before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Financial Maths deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Financial Maths appears in 6/11 main P1 years — but when it shows up, it dominates Section B.** Total: **20 P1 parts**. Per-paper average when present ≈ 3–6 parts, almost all clustered in a single Section B question worth ~50 marks.
- **Years tested (main):** 2015, 2017, 2020, 2023, 2024, 2025. **Years it skipped:** 2016, 2018, 2019, 2021, 2022. Plus every recent deferred sitting (2022 DF, 2023 DF, 2024 DF, 2025 DF) has carried a full FM Section B question.
- **The 2024–25 picture is split.** 2024 P1 had **5** FM parts (the 25-year mortgage in Q7 plus a continuous-compounding AER part). 2025 P1 collapsed to **1** — but 2025 DF P1 came roaring back with a full savings-+-drawdown annuity in Q8. Treat 2026 as a coin-flip: prep as if FM *is* on the paper.
- **Cross-strand reach:** Financial Maths is two strands wearing a trench coat — page-22 geometric-series spine + page-31 amortisation closed form. It also pulls Indices & Logs (find `n` via logs), Algebra 14 (manipulation of formula), and one of the **five prescribed Paper 1 proofs** (amortisation, asked in 2020).

**The takeaway.** When FM lands on the paper it's worth ~50 marks in one go. Skipping it costs you 10% of P1 in a single decision.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **FM 6: discounted-cash-flow + identifying `a`, `R`, `n`** | 25 min | The 85-minute tutorial — **9 P1 citations**, the spine of every paying-back question (2017, 2020, 2023, 2023 DF, 2024) |
| **FM 4: rate conversion (monthly ↔ APR)** | 15 min | Tested every FM-year. The single most common opener of an FM question |
| **Amortisation formula proof (FM 7 = P1 Proofs §4)** | 10 min | Prescribed proof, tested 2020. If FM is the proof-year, ~10 marks on its own |
| **FM 5: savings annuity setup (beginning vs end of month)** | 10 min | 2017 Rohan, 2025 DF Q8(a) — the geometric-series setup with deposits |
| **FM 3: present value definition + the `P = F/(1+i)ᵗ` rearrangement** | 10 min | 2017 Q8(b)(i), 2020 Q7(c) — usually worth a definition mark + an arithmetic part |
| **FM 2: compound interest + log-bridge to find `t`** | 10 min | Q-stem for almost every FM question; the log-bridge is the "how many years until..." pattern |
| **Quick-fire:** simple interest, AER from continuous, end-of-loan balance | 5 min | The non-core marks; page-30 forward, page-30 inverse, `e^k − 1` |

---

## 📊 Top FM tutorials by exam frequency (P1 main, 11 years)

| Rank | Tutorial | P1 citations | What it tests |
|---|---|---|---|
| 1 | `financial-maths-6` Annuities — Paying Back | **9** | Mortgages, loans, balance-after-N-payments. Discounted-cash-flow geometric series. |
| 2 | `financial-maths-2` Compound Interest | ~5 | `F = P(1+i)ᵗ`. The Q-stem of every FM question. |
| 3 | `financial-maths-3` Time Value of Money | ~4 | Present-value definition + rearrangement. |
| 4 | `financial-maths-4` Rate Conversion | ~4 | AER ↔ monthly. `(1+i)^k = (1+APR)`. |
| 5 | `financial-maths-5` Annuities — Saving | ~3 | Deposits compounding into a fund (Rohan 2017, 2025 DF Q8a). |
| 6 | `financial-maths-7` Amortisation Proof | ~2 | One of five prescribed Paper 1 proofs (2020). |
| 7 | `financial-maths-1` Simple Interest | ~2 | Percentage-of-an-amount baseline. |
| 8 | `financial-maths-8` Pensions | — | Capstone; not directly cited in the corpus but FM 5+6 combined. |

> **Read this as:** if FM appears on your paper, ~80% of the marks live inside FM 6 + FM 4. Drill those two first.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 30** | `F = P(1 + i)ᵗ` and `P = F/(1 + i)ᵗ` | Compound interest, forward and inverse. Both forms are the same formula rearranged. |
| **p. 31** | `A = P · i(1+i)ᵗ / ((1+i)ᵗ − 1)` | Amortisation formula. Vanilla loans only — see load-bearing rule 4. |
| **p. 22** | `Sₙ = a(1 − Rⁿ)/(1 − R)` | Geometric-series sum. The real engine behind every annuity question. **Cross-strand.** |
| **p. 21** | `a^(1/n) = ⁿ√a`; `ln(aᵇ) = b·ln(a)` | Fifth rule for rate conversion; third rule for log-bridge to find `n`. |

> **🎯 Stop memorising the page-30 second formula.** From FM 3: *"These are both the same formula and when I teach this to students I don't think you should segregate these."* Rearrange when you need `P`; don't memorise as separate.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. The rate-conversion master framework

```
(1 + i_short)^k  =  (1 + i_long)^1
```

Where `k` = number of short periods in one long period. Monthly → APR: `(1 + i_month)¹² = 1 + APR`. Quarterly → APR: `(1 + i_q)⁴ = 1 + APR`. **Never** divide the APR by `k` — that's the nominal rate, not the equivalent rate. Inverse direction uses the page-21 fifth rule of indices: `i_month = (1 + APR)^(1/12) − 1`.

### 2. The discounted-cash-flow setup (FM 6's backbone)

For any paying-back annuity:

```
loan_amount  =  F/(1+i)¹ + F/(1+i)² + ... + F/(1+i)ⁿ
```

That's a geometric series with `a = F/(1+i)`, `R = 1/(1+i)`, `n` terms. Identify `a`, `R`, `n`, plug into `Sₙ` from page 22, solve for whatever's missing.

### 3. The variable family naming convention

`P` = principal (today's lump sum). `F` = future value. `i` = rate per period (as decimal). `t` or `n` = number of periods. `A` = level repayment (FM 6/7). In Paul's exam phrasings, `A` and `a` mean different things in the amortisation proof — capital `A` is the repayment, lowercase `a` is the first term of the geometric series.

### 4. The two-stage pension architecture (FM 8)

Stage 1: saving annuity → fund at retirement (FM 5 mechanic). Stage 2: paying-back annuity → drawdown until fund hits zero (FM 6 mechanic). Bridge them with `fund_at_retirement_stage_1 = fund_at_retirement_stage_2`. The same person, the same fund, two different cash-flow directions.

---

## 🚨 LOAD-BEARING — the five things that win or lose the Financial Maths question

### 1. Rate-and-time units must agree

If the rate is monthly, `n` is in months. If the rate is annual (AER/APR), `n` is in years. Mixing units sinks the question instantly.

> 🚨 **Read the question once for the rate, again for the time, a third time for "is it per month or per year?"** Paul's FM 1 [06:54]: *"I'd always in a question just double check is it per month or per week or per year."* Tested **every** FM year. The 2020 P1 Q7 mortgage question hands you a monthly rate; if you treat `n` as years instead of `25 × 12 = 300` months, every subsequent number is wrong.

### 2. Rate conversion uses the `k`-th root, not division by `k`

| Direction | Correct | Wrong |
|---|---|---|
| APR → monthly | `i_month = (1 + APR)^(1/12) − 1` | `i_month = APR/12` |
| Monthly → APR | `APR = (1 + i_month)¹² − 1` | `APR = 12 · i_month` |
| Continuous `k` → AER | `AER = e^k − 1` | `AER = k` |

> 🚨 **Dividing the APR by 12 gives the *nominal* monthly rate, not the *equivalent* one.** The marking scheme caps that route at High Partial. From 2017 P1 Q8(c): the correct quarterly rate from `2.4%` APR is `0.5947…%`, NOT `0.6%`. From 2024 P1 Q7(c)(iii): the AER from `F(t) = 5000 e^(0.04t)` is `4.08%`, NOT `4%` — and the MS deducts a mark for `0.04` even with supporting work. Tested 2017, 2022 DF, 2023, 2023 DF, 2024.

### 3. Present value uses DIVIDE, not multiply

A future payment `F` due `k` periods from now is worth `F/(1+i)^k` today. **Discounting shrinks.** If your present value comes out larger than the future payment, you've multiplied when you should have divided.

> 🚨 **This is the single most common arithmetic-direction error in FM.** From 2020 P1 Q5(b) commentary: *"some students multiply, getting an answer larger than the future payments would total. Discounting shrinks; growing compounds."* The discounted-cash-flow expression in FM 6 is `F ÷ (1+i)^k`, always.

### 4. Geometric series **always** beats the amortisation formula

| Question feature | Method |
|---|---|
| Vanilla — same payment, no deferral, no growth | Either works; amortisation is faster |
| Deferred payments (grace period) | Geometric series only — shift the leading exponent of `a` |
| Variable / growing payments | Geometric series only — combine ratios into a single `R` |
| Find `n` (how many months) | Geometric series + log-bridge — amortisation can't solve for `n` directly |
| Balance owed at intermediate point | Geometric series (present value of remaining payments) |

> 🚨 **Paul's directive at FM 6 [00:53]:** *"my advice is that you should always use the geometric series… using a geometric series for these questions will always work. However, using the amortization formula, if they change the question a little bit, it can be very, very difficult to figure out how to change your amortization formula."* The page-31 formula is a shortcut for vanilla questions only. Tested 2017, 2020, 2023, 2023 DF, 2024, 2025 DF.

### 5. Amortisation formula derivation = one of the five prescribed P1 proofs

If a "prove that the amortisation formula equals `A = P · i(1+i)ᵗ / ((1+i)ᵗ − 1)`" prompt appears, the marks are for the **exact prescribed structure** (FM 7 = Paper 1 Proofs §4):

1. Each future repayment `A` discounted to present: `A/(1+i)ⁿ`.
2. Sum of present values equals the loan: `P = A/(1+i) + A/(1+i)² + ... + A/(1+i)ᵗ`.
3. Apply `Sₙ = a(1 − Rᵗ)/(1 − R)` with `a = A/(1+i)`, `R = 1/(1+i)`.
4. Simplify the fraction-of-fractions by multiplying numerator and denominator by `(1+i)/i`.
5. Cross-multiply / rearrange to isolate `A`.

> 🚨 **Tested in 2020 P1 Q8(a) as the prescribed proof.** From FM 7 [00:53]: *"the only proof in financial maths on the Leaving Cert course is the proof of this formula."* Variations — skipping a step, replacing the algebra with words — lose marks. The MS marking notes are explicit.

---

## 🎯 The seven techniques you must execute without thinking

1. **Identify `a`, `R`, `n` from a discounted-cash-flow expression.** Write out the first three terms — `F/(1+i)¹ + F/(1+i)² + F/(1+i)³ + ...` — and the pattern names itself.
2. **Rate conversion via fractional exponent.** `i_short = (1 + i_long)^(1/k) − 1`. Keep **7–8 decimal places** during intermediate work — Paul's FM 4 [09:12] rule. Money rounds to 2dp only at the final step.
3. **Log-bridge to find `n`.** When `n` is in the exponent, take `ln` of both sides; page-21 third rule brings it down: `ln(aⁿ) = n·ln(a)`. **Round UP** for "how many payments needed" — you can't make 0.535 of a payment (FM 5: `37.535 → 38`).
4. **Beginning-vs-end-of-month adjustment.** End-of-month: last deposit earns zero interest; first deposit compounds `n − 1` times. Beginning-of-month: every deposit gets one extra period (multiply the whole answer by `(1+i)`).
5. **Payment-deferral handling.** If repayments start `X` months late, shift the leading exponent of `a` from `(1+i)¹` to `(1+i)^(X+1)`. The series length stays at `n`.
6. **Verify by summing present values.** From FM 6 Worked Example 1: compute the present value of each repayment individually, sum them, check the total equals the loan. Catches rate-conversion errors instantly.
7. **Two-stage pension bridge.** Compute fund at retirement via stage-1 saving annuity. Set that equal to the present value of the stage-2 drawdown annuity. Solve for whichever variable is unknown.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| `i_month = APR / 12` instead of 12th root | Always `(1 + APR)^(1/12) − 1`. Page-21 fifth rule. |
| Multiplying for present value instead of dividing | Future → present = ÷ by `(1+i)^k`. Discounting shrinks. |
| `n` = number of years instead of repayment periods | `25 years × 12 = 300` monthly periods. Match the rate. |
| Answering `0.04` for the AER of `F(t) = Pe^(0.04t)` | AER = `e^(0.04) − 1 = 0.0408 = 4.08%`. The MS deducts a mark for `0.04` even with full working. |
| Rounding `n` down for "minimum payments needed" | Round **up** — you cannot make a fractional payment. |
| Money-rounding intermediate calculations | Keep 7–8 decimal places for rates; money rounds to 2dp only at the end. |
| Beginning-of-month payments treated as end-of-month | Beginning-of-month: every payment earns one extra period of interest. Worked Examples 2 and 3 of FM 5 use identical numbers and yield €19,277.85 vs €19,207.27 because of this. |
| Using amortisation formula for deferred or variable payments | Switch to geometric series. The amortisation formula breaks. |
| Capital `A` vs lowercase `a` confused in the proof | Capital `A` = repayment; lowercase `a` = first term of the geometric series = `A/(1+i)`. |
| Mixing AER (earning, savings) with APR (paying, loans) | Same maths, opposite direction. Read the question for context. |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"…monthly rate of 0.287%…"* | Already monthly — match `n` in months. No conversion needed. |
| *"…APR of 4.5%, monthly repayments…"* | Convert APR → monthly first. Then build the cash-flow. |
| *"…doesn't begin repaying for 12 months…"* | Payment deferral. Geometric series only; shift leading exponent. |
| *"How many payments will it take…"* | Log-bridge. Set up `Sₙ`, isolate `Rⁿ`, take `ln`, page-21 third rule. Round up. |
| *"Balance still owed after `k` years…"* | Present value of all **remaining** payments. Sum a geometric series. |
| *"Find the AER equivalent to a monthly rate of…"* | `(1 + i_month)¹² − 1`. Direct computation, no logs. |
| *"…compounded continuously at rate `k`…"* | AER = `e^k − 1`. Don't answer `k`. |
| *"Derive / Prove the amortisation formula"* | Prescribed proof. Five-step structure from FM 7. |
| *"Present value of a payment of €1000 in 1 year"* | Definition: amount today that grows to €1000 with compound interest. Then arithmetic. |
| *"Show that the monthly repayment is…"* | Set up the geometric series, sum, solve for `A`. The target value is given — drive toward it. |

---

## 💡 Three exam-day tips that move the needle

1. **Convert the rate FIRST, before you touch anything else.** A wrong rate poisons every subsequent line. Write the rate-conversion step at the top of your answer so the examiner sees it explicitly — that's a method mark before the real work starts.

2. **Write out the first three terms of the cash-flow series.** Don't jump to `Sₙ`. Writing `F/(1+i)¹ + F/(1+i)² + F/(1+i)³ + ...` makes `a`, `R`, and the leading exponent visible — and the MS awards Low Partial Credit for "a relevant present value" even if the sum is wrong.

3. **Sanity-check the total repaid.** 300 × monthly-repayment for a 25-year mortgage should be roughly 1.4–1.6× the principal at typical rates. If your monthly repayment comes out at €400 for a €250,000 loan, you've dropped a zero somewhere.

---

## 🔗 Cross-strand connections (where else Financial Maths fires)

- **Financial Maths ↔ Sequences & Series** — page-22 geometric sum is the engine. FM 5 has **11+ explicit page-22 citations** in a single tutorial. If you don't know `Sₙ`, FM 6 collapses.
- **Financial Maths ↔ Indices & Logs** — page-21 third rule for "find `n`"; page-21 fifth rule for rate conversion. The unknown-in-power pattern from IL 5 is the single most-cited tutorial across all P1 (31 citations).
- **Financial Maths ↔ Algebra 14** — manipulation of formula. Rearranging `F = P(1+i)ᵗ` for any of the four variables is pure algebra-14.
- **Financial Maths ↔ Paper 1 Proofs** — the amortisation derivation is proof #4 of the five prescribed (tested 2020).
- **Financial Maths ↔ Differentiation** — 2024 P1 Q7(c) had continuous compounding `F(t) = 5000 e^(0.04t)`. AER becomes `e^k − 1`; if asked for "rate at time `t`", differentiate.
- **Financial Maths ↔ Number Theory / Percentages** — `i = (rate %) ÷ 100` conversion is the simplest building block.

> The 2017 Q8 is the strand's archetype: it touches FM 2, FM 3, FM 4, FM 5, AND probability + percentages across six sub-parts. Master Q8 of 2017 and you've covered 90% of what FM throws at you.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Rate-and-time units must agree | FM 1 / FM 4 | every FM year |
| Rate conversion via `k`-th root | FM 4 | 2017, 2022 DF, 2023, 2023 DF, 2024, 2024 DF |
| Present value = divide by `(1+i)^k` | FM 3 | 2017, 2020, 2023 DF, 2024, 2025 DF |
| Geometric-series annuity setup | FM 5 / FM 6 | 2017, 2023, 2023 DF, 2024, 2025 DF |
| Amortisation formula in use | FM 6 | 2017, 2020, 2023, 2023 DF, 2024 |
| Amortisation formula proof (prescribed P1 proof) | FM 7 | 2020 |
| Log-bridge to find `n` | FM 2 / IL 5 | 2017, 2023 |
| AER from continuous compounding (`e^k − 1`) | FM 4 | 2024 |
| Beginning-vs-end-of-month annuity | FM 5 | 2025 DF |
| Payment deferral (shift leading exponent) | FM 6 | 2024 P1 Q7 (25-year mortgage variant) |

> If you've internalised everything in this column, you've insured ~80% of the marks on whichever year's FM question appears — and unless 2026 breaks the 6-of-11 pattern hard, FM is on the paper.
