# Induction — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Induction before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Induction deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Induction appears in 6/11 P1 main sittings:** 2016, 2018, 2019, 2020, 2021, 2025. Total: **6 main-paper parts**.
- **When it appears, it's worth ~10 marks** — almost always a single Section A part (Q2 or Q4), occasionally a Section B sub-part (2020 Q7(d), 2025 Q10(e)(ii)). The marks are *concentrated*, not distributed.
- **The 2022–2024 gap is over.** Main sittings 2022, 2023, 2024 had no induction. **But every deferred sitting in that gap did** — 2022 DF (`tⁿ` is odd), 2023 DF (`13ⁿ − 1` div by 12), 2024 DF (`∑n = n(n+1)/2`). The 2025 main sitting *and* 2025 DF both restored it. Plan as if **2026 has an induction proof**.
- **Cross-strand reach:** Induction supplies **2 of the 5 prescribed Paper 1 proofs** — De Moivre's theorem (Complex Numbers §16) and the geometric-series `Sₙ` formula (Sequences §13). When a prescribed proof appears in Section A (5 of 11 years), there's a 2-in-5 chance it's induction-flavoured.

**The takeaway.** Induction is binary: either it's there for ~10 marks, or it isn't. The skeleton is identical every time. You insure those marks for the cost of memorising one 4-step template.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **The 4-step skeleton + conclusion sentence** | 10 min | `induction-1` — load-bearing for every induction proof since 2015 |
| **Divisibility template (substitute-then-factor)** | 20 min | `induction-4` — tested 2016, 2021, 2023 DF; the most-tested specific template |
| **Series template (append-(k+1)th term + factor out)** | 20 min | `induction-5` — tested 2020, 2024 DF, 2025 DF, 2025 (variant) — **dominant in last 5 years** |
| **Inequalities template (split-into-pairs)** | 10 min | `induction-2` — tested 2019; sister technique to divisibility |
| **Factorials template (factorial recurrence)** | 5 min | `induction-3` — lower priority, but cleanest mechanic if it appears |
| **The two prescribed induction proofs** | 15 min | De Moivre (`induction-6`/CN 16, tested 2018) + Sₙ (`induction-7`/Sequences 13) |
| Quick-check log tables p. 21, p. 22 | 5 min | First rule of powers + `∑k²` closed form |

---

## 📊 Top induction tutorials by exam frequency (P1 main + DF, 11 years)

| Rank | Tutorial | P1 citations | What it tests |
|---|---|---|---|
| 1 | `induction-1-introduction` | **~4** main + every DF | The 4-step skeleton — cited in EVERY induction question. |
| 2 | `induction-4-divisibility` | **~3** | "Prove `aⁿ ± c` is divisible by `D`" — split-the-coefficient. |
| 3 | `induction-5-series` | **~2** main + 3 DF | Sum-formula proofs (∑n, ∑k², triangular numbers). |
| 4 | `induction-2-inequalities` | ~2 | "Prove `3ⁿ > 2n`" — split-into-pairs with coefficient. |
| 5 | `induction-3-factorials` | rare | Factorial recurrence `(k+1)! = (k+1)·k!`. Mentioned, not yet tested in main. |
| 6 | `induction-6-de-moivre-by-induction` | 1 (2018) | Prescribed Paper 1 proof — canonical home is CN 16. |
| 7 | `induction-7-sum-of-geometric-series-by-induction` | rare | Prescribed Paper 1 proof — canonical home is Sequences §13. |

> **Read this as:** `induction-1` is the universal opener — every other tutorial assumes it. Divisibility + Series together account for **~7 of the last 10 induction questions** (main + DF combined). If you've drilled those two templates, you've insured most of the strand.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 21** | `a^p · a^q = a^(p+q)` (first rule of powers) | Step 3 — splits `a^(k+1) = a^k · a` so the assumption can be applied. Cited at induction-1 [05:30]. |
| **p. 22** | `∑k = n(n+1)/2`, `∑k² = n(n+1)(2n+1)/6`, `∑k³ = [n(n+1)/2]²` | If the question gives you a `∑` formula to prove, the **target form is on page 22**. You still have to prove it by induction. |

> **🎯 Working memory for the skeleton, log tables for the formulas.** Page 22 confirms the target — flip to it before you start manipulating the algebra so you know exactly what RHS at `n=k+1` should simplify to.

---

## 📚 Learning work — what must be in your head before you sit down

These items the log tables **don't** give you. Drill until they're automatic.

### 1. The 4-step skeleton — write it BEFORE reading the algebra

| Step | Title to write (EXACT words) | What you do |
|---|---|---|
| 1 | **Prove `P(n)` is true for `n = N₀`** | Substitute smallest `n` (`N₀`, e.g. `n = 1` or `n = 7`); verify LHS = RHS (or LHS > RHS, etc.). |
| 2 | **Assume `P(n)` is true for `n = k`** | State the proposition with `n = k` — highlight it. |
| 3 | **Hence, prove `P(n)` is true for `n = k+1`** | Manipulate LHS-at-(k+1) using the assumption + algebra until it equals RHS-at-(k+1). |
| 4 | **Conclusion** | The explicit conclusion sentence (verbatim). |

> 🚨 **Write the skeleton across your answer sheet FIRST, then fill it in.** The four boxes are method marks regardless of what's inside them — but you must **label each step with the exact title above.** Shortening Step 2 to just "Assumption", dropping the "Hence," in Step 3, or omitting the Conclusion all cost marks.

### 2. The conclusion sentence — verbatim

> *"True for `n = k+1` if true for `n = k`. But true for `n = N₀`. Therefore true for `n = N₀+1, N₀+2, ...`, all `n ∈ ℕ`."*

The MS deducts **Full Credit −1** for "Omits conclusion but otherwise correct" (2024 DF Q2(b) marking notes, identical wording across years). This is non-negotiable structural punctuation.

### 3. The universal "factor out `(k+1)`" move for series

When series-induction algebra leaves you with `formula(k) + (k+1)th term`, write both terms over a common denominator and **factor `(k+1)` out of the numerator**. The remaining factor will be exactly what you need to match RHS-at-(k+1). Paul (induction-5): *"the universal series-induction trick."* Used identically in 2020, 2024 DF, 2025, 2025 DF.

### 4. The substitute-then-factor split for divisibility

To prove `aⁿ ± c` is divisible by `D` (where `D | (a − 1)`):

```
a^(k+1) = (1 + (a−1)) · a^k = 1·a^k + (a−1)·a^k
         → first piece matches assumption; second has D as factor
```

Tested 2016 (`a = 8, D = 7`), 2021 (`a = 2^3 = 8, D = 7`), 2023 DF (`a = 13, D = 12`).

---

## 🚨 LOAD-BEARING — the five things that win or lose the induction question

### 1. The conclusion sentence is a SEPARATE scoring item

> 🚨 Stop the proof at Step 3 → automatic **Full Credit −1**. The algebra can be flawless and you still lose a mark. Paul drills this at induction-1 [12:42]: *"every single question you do induction, you're going to follow those four steps."* Tested every induction year — the MS callouts on 2020, 2024 DF, 2025 DF are explicit.

### 2. "Prove by induction" forbids algebraic shortcuts

If the question says **"Prove by induction"**, the **4-step skeleton is mandatory**. Alternative proofs score zero — even if mathematically valid.

> 🚨 **2023 DF Q4(a) trap.** You can prove `13ⁿ − 1` divisible by 12 directly via the identity `13ⁿ − 1 = 12 · (13^(n−1) + ... + 1)`. **It scores zero on this question.** The marking note from `2023_DF_P1_solutions.md`: *"This is a valid proof but does NOT score induction marks — the question asks for proof by induction, which requires the 4-step skeleton."*

### 3. First rule of powers: `a^(k+1) = a^k · a`

> 🚨 Every exponential induction (inequality, divisibility, factorial-vs-exponential) opens Step 3 with this split. Page 21 of the log tables. Without it the assumption can't be substituted. Used at 2016, 2018, 2019, 2021, 2022 DF, 2025.

### 4. Substitute-then-factor for divisibility (split as `1 + (a−1)`)

| Proposition shape | Mechanic |
|---|---|
| `aⁿ ± c` divisible by `D` (where `D \| (a−1)`) | `a^(k+1) = (1 + (a−1))·a^k` — first piece matches assumption, second has `D` as factor |
| `a^(bn+c) ± d` divisible by `D` | Split `a^b` as `1 + (a^b − 1)` — same mechanic, with `a^b` taking the role of `a` |
| Polynomial like `n³ − n` divisible by `D` | Expand-and-group: expand `f(k+1)`, rearrange to expose `f(k)` plus a multiple-of-`D` remainder |

> 🚨 **Choose the split so `D` divides `(a−1)`.** If your remainder coefficient isn't a multiple of `D`, you've split wrong or the proposition is false. Tested 2016, 2021, 2023 DF.

### 5. Series-induction: append the (k+1)th term to both sides, then factor

> Take the assumption `S_k = formula(k)`. Add `a_{k+1}` to both sides. LHS becomes `S_{k+1}`. Manipulate the RHS — common denominator, then **factor `(k+1)` out of the numerator** — until it matches `formula(k+1)`.

> 🚨 **Don't manipulate both sides simultaneously.** That's the style of solving an equation, not proving one. Stay on the LHS at `n=k+1`; the RHS at `n=k+1` is the target, not a workspace. (2024 DF marking note.) Tested 2020 (`∑k²`), 2024 DF (`∑k`), 2025 DF (`∑k`), 2025 main (recurrence variant).

---

## 🎯 The 7 techniques you must execute without thinking

1. **Write the 4-step skeleton first.** Four boxes on the page before you read the algebra. Exact headings: `Step 1 — Prove P(n) is true for n = N₀`, `Step 2 — Assume P(n) is true for n = k`, `Step 3 — Hence, prove P(n) is true for n = k+1`, `Step 4 — Conclusion`.
2. **Test the starting value.** Substitute `n = 1, 2, 3, ...` until the proposition first becomes true. That's your `N₀`. For `n! > 2ⁿ` it's `n = 4`; for `n² > 4n + 3` it's `n = 5`. The question's stated range usually tells you, but verify by substitution.
3. **State the assumption explicitly.** Box it or label it `[Eq. A]`. Paul (induction-1 [04:10]): *"you should always highlight your assumption because it's impossible to finish off this question without writing that out."*
4. **Split-into-pairs / factor-distribution** for inequalities. Coefficient `a` → split as `1·X + (a−1)·X`. Used at 2019: `3·3^k = 3^k + 2·3^k` — first piece matches assumption, second bounds against the range condition.
5. **Factorial recurrence:** `(k+1)! = (k+1) · k!`. Always rewrite `(k+1)!` this way to expose `k!` so the assumption can substitute.
6. **Append-(k+1)th-term + common denominator + factor `(k+1)`** for series. The universal three-move sequence.
7. **Write the conclusion sentence verbatim** at the end. Don't paraphrase under exam pressure — you'll forget a clause.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Stop at Step 3 without conclusion → **FC −1** | Write the conclusion sentence verbatim. 5 seconds of writing = 1 mark. |
| "Prove by induction" answered by algebraic identity → **0 marks** | If the question says "by induction", use the 4-step skeleton. No exceptions. |
| Step 1 at `n=1` when proposition needs `n ≥ 5` | Test small `n` first. Start Step 1 at the smallest valid `n` stated in the question. |
| Manipulating BOTH sides in Step 3 | Stay on LHS-at-(k+1); RHS-at-(k+1) is the target, not a workspace. |
| Assumption stated implicitly (not labelled) | Write `Assume P(k): ...` explicitly, with the proposition substituted. Box or label it. |
| Wrong split: `a = 1 + b` where `D ∤ b` | Choose `b` so `D` divides `b`. If you can't, re-read the question — the divisor might suggest splitting `a^b` instead of `a`. |
| Forgetting page-21 first rule of powers in Step 3 | If you see `a^(k+1)`, immediately rewrite as `a^k · a`. |
| Series: leaving the answer un-factored after common denominator | Factor `(k+1)` out of the numerator. The remaining factor is what matches RHS-at-(k+1). |
| Divisibility: ending Step 3 with the "two pieces" but not stating both are divisible by `D` | Explicitly say: *"first piece divisible by D from the assumption; second piece divisible by D because the coefficient is a multiple of D; therefore the sum is divisible by D."* |
| De Moivre by induction: skipping the page-14 sum-of-angles step | The trig identities `cos(A+B), sin(A+B)` collapse the product — they're on page 14. Don't skip; that's where the marks live. |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Prove by induction that..."* | 4-step skeleton, no shortcuts. Algebraic identity scores 0. |
| *"Show that..."* (no "by induction") | Algebraic argument acceptable; induction usually still cleanest. |
| *"...is divisible by D"* / *"D is a factor of..."* | Interchangeable. Divisibility template: substitute-then-factor. |
| *"...for all n ∈ ℕ"* | Default range. Step 1 at `n = 1`. |
| *"...for n ≥ N₀"* | Start Step 1 at `N₀`, not at `n = 1`. The range condition is part of the proof. |
| *"Hence, prove..."* | Use the previous part as your Step 1 base case or as a sub-result inside Step 3. |
| *"...where t is a positive odd number"* | Multiplicative-version induction (2022 DF `tⁿ` is odd). The assumption: `t^k = 2m+1` for some integer `m`. |
| *"Prove De Moivre's theorem..."* | One of the 5 prescribed Paper 1 proofs — reproduce the exact CN 16 structure. |

---

## 💡 Three exam-day tips that move the needle

1. **Write the 4-step skeleton across your answer sheet BEFORE you read the algebra.** Four headings, four boxes. The four headings alone score method marks regardless of what you fill in. If you blank on Step 3's algebra, you still bank Steps 1, 2, and 4.

2. **Memorise the conclusion sentence verbatim.** *"True for `n = k+1` if true for `n = k`. But true for `n = N₀`. Therefore true for all `n ∈ ℕ`."* It's worth 2–3 marks. Don't paraphrase under pressure — you'll forget a clause and lose the mark.

3. **If Step 3 won't budge, rewrite LHS-at-(k+1) to expose LHS-at-(k).** For exponentials use `a^(k+1) = a^k · a`. For factorials use `(k+1)! = (k+1)·k!`. For sums use `S_{k+1} = S_k + a_{k+1}`. Once the assumption's LHS appears, substitute via the inductive hypothesis. The remainder bounds against the range condition.

---

## 🔗 Cross-strand connections (where else Induction fires)

- **Induction ↔ Complex Numbers (§4.4)** — De Moivre's theorem by induction is `induction-6` / CN 16 / Paper 1 Proofs §3. One of 5 prescribed P1 proofs. Tested 2018.
- **Induction ↔ Sequences & Series (§4.5)** — Sum of geometric series `Sₙ` formula by induction is `induction-7` / Sequences §13 / Paper 1 Proofs §2. Another of the 5 prescribed proofs.
- **Induction ↔ Paper 1 Proofs** — induction provides 2 of the 5 prescribed proofs (the other three are non-induction: `√2` irrational, amortisation formula, sum-to-infinity).
- **Induction ↔ Number Theory** — divisibility shares the substitute-then-factor mechanic; many Number Theory questions hide an induction.
- **Induction ↔ Algebra** — Step 3's algebra (factoring quadratics, common denominators, polynomial expand-and-group) is pure algebra-strand technique. Page 21 first rule of powers is shared.
- **Induction ↔ Functions & Graphs / Differentiation** — recurrence-defined sequences (2025 Q10 used `H(n+1) = H(n) + 2n + 3`) can ask for an induction proof inside a Section B question.

> Induction is structurally isolated — it lives in its own Section A part most years — but the **techniques** it uses (algebra, factoring, sigma notation, page-21 powers) are borrowed from everywhere else.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| 4-step skeleton + explicit conclusion | `induction-1` | Every induction year — main: 2016, 2018, 2019, 2020, 2021, 2025; DF: 2022, 2023, 2024, 2025 |
| First rule of powers `a^(k+1) = a^k · a` | `induction-1` (cites p. 21) | 2016, 2018, 2019, 2020, 2021, 2022 DF, 2025 |
| Substitute-then-factor for divisibility | `induction-4` | 2016 (`8ⁿ−1`), 2021 (`2^(3n−1)+3`), 2023 DF (`13ⁿ−1`) |
| Append-(k+1)th-term + factor `(k+1)` (series) | `induction-5` | 2020 (`∑k²`), 2024 DF (`∑k`), 2025 DF (`∑k`), 2025 main (recurrence variant) |
| Split-into-pairs (inequality) | `induction-2` | 2019 (`f(n) ≥ g(n)` exponential vs linear) |
| Multiplicative variant (`tⁿ` is odd) | `induction-1` + `induction-4` | 2022 DF |
| De Moivre by induction (prescribed proof) | `induction-6` / CN 16 | 2018 |

> If you've internalised everything in this table — the 4-step skeleton, the divisibility split, and the series-induction three-move sequence — you've insured ~95% of the induction marks on any sitting that includes a proof.
