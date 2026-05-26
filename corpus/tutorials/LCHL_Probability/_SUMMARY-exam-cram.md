# Probability — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Probability before Paper 2. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Probability deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Probability appears in 11/11 years on Paper 2.** Average ≈ 7.1 parts per paper. Total: **78 P2 parts** — the **single most-tested strand on Paper 2**.
- **Recent surge:** 2024 had **10** probability parts; 2025 had **11**. Prior 9-year average was ≈ 6.4. Plan as if 2026 keeps climbing.
- **Section A and Section B both fire** — Section A for sample-space mechanics and short combinations questions; Section B for the long Bernoulli-trial contexts and expected-value games of chance.
- **Cross-strand reach:** the `nCr` machinery is shared with Algebra 21 (Binomial Theorem); "find `n` such that `q^n < 0.01`" uses Indices & Logs 5; Bernoulli's normal approximation reaches into Statistics (CLT).

**The takeaway.** Probability is the **biggest P2 strand and getting bigger**. Marks lost here cost more than in any other Paper 2 topic, because they recur in five+ questions across the paper.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Bernoulli trials + the "kth-time-on-nth-shot" trick** | 20 min | `probability-8` — 18 P2 citations; tested ~9/11 years |
| **Independent events + conditional probability** | 15 min | `probability-3` — **32 P2 citations**, the single most-cited tutorial in the strand |
| **Combinations + stratified counting** | 10 min | `probability-6` — 10 P2 citations; the "at least 4 of these" pattern |
| **Permutations + block-the-letters trick** | 10 min | `probability-5` — rising in 2023/24/25 main + 2023/24/25 DF |
| **Expected value + games of chance** | 10 min | `probability-9` — 12 P2 citations; "fair game" + profit-per-play |
| **Mutually exclusive vs not (addition rule)** | 5 min | `probability-2` — tested 2016, 2024, 2025; back-to-back recent years |
| **Quick-fire:** factorial peel-off + twin rule + JC sample space | 15 min | `probability-4`, `-7`, `-1` — page 33 / page 20 formula drills |

---

## 📊 Top probability tutorials by exam frequency (P2 main, 11 years)

| Rank | Tutorial | P2 citations | What it tests |
|---|---|---|---|
| 1 | `probability-3` Independent Events & Conditional Probability | **32** | `P(A∩B) = P(A)·P(B)`; `P(A\|B) = P(A∩B)/P(B)` |
| 2 | `probability-8` Bernoulli Trials | **18** | `P(R of n) = C(n,R)·p^R·q^(n−R)`; kth-time-on-nth-shot |
| 3 | `probability-1` JC Revision | **12** | Sample-space enumeration; "and means multiply"; complement |
| 4 | `probability-9` Relative Frequency + Expected Value | **12** | `E = Σ P·X`; games of chance; fair game |
| 5 | `probability-6` Combinations | **10** | `nCr`; stratified counting; inclusion-exclusion shortcut |
| 6 | `probability-5` Permutations | ~6 | `nPr`; block-the-letters trick |
| 7 | `probability-2` Mutually Exclusive | ~5 | `P(A∪B) = P(A)+P(B)−P(A∩B)`; Venn with X |
| 8 | `probability-4` Factorials | ~3 | `n! = n·(n−1)!`; `0! = 1` |
| 9 | `probability-7` Twin Rule | ~2 | `nCr = nC(n−r)` — bottom numbers add to top |

> **Read this as:** if you only have 90 minutes, tutorials 1–4 alone account for **74 cited appearances** across Paper 2. Do not skip them.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 33** | `P(A∪B) = P(A) + P(B) − P(A∩B)` | Not-mutually-exclusive addition rule |
| **p. 33** | `P(A∩B) = P(A)·P(B)` (independent events) | Multiplication rule; independence test |
| **p. 33** | `P(A\|B) = P(A∩B)/P(B)` | Conditional probability; Bayes-style questions |
| **p. 33** | `nPr = n!/(n−r)!` | Permutations (order matters) |
| **p. 33** | `nCr = n!/[r!(n−r)!]` | Combinations (order doesn't matter); also p. 20 |
| **p. 33** | `P(R of n) = C(n,R)·p^R·q^(n−R)` | Bernoulli/binomial — **tested 11/11 years** |
| **p. 33** | `E(X) = Σ P·X` | Expected value; fair-game and profit-per-play |

> **🎯 Page 33 is the whole strand.** Open it before you start Q9/Q10. Every formula above is sitting there in front of you — use working memory for **techniques and recipes**, the page for **formulas**.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. Paul's language rule: "and means multiply, or means add"

> Paul opens `probability-1` with: *"take that down and highlight it."*

If you can put the word **"and"** between two events → **multiply** their probabilities. If you can put the word **"or"** → **add**. This is the engine behind everything: independence (and), mutually exclusive (or), conditional (given), Bernoulli (k successes AND n−k failures).

### 2. The 4-condition Bernoulli definition

ALL FOUR must hold before you reach for `(n R)·p^R·q^(n−R)`:

1. **Finite** number of trials `n`.
2. Only **two** possible outcomes (success / failure).
3. Trials are **independent** of each other.
4. Probability of success `p` is **the same** for each trial — the question often signals this with the word **"always"**.

> If any condition fails, the formula doesn't apply. State the conditions in "show this is Bernoulli" parts.

### 3. The "kth time on the nth shot" recipe

The final trial is **forced** to be a success. So:

```
P(kth success lands on trial n) = C(n−1, k−1) · p^(k−1) · q^(n−k)  ·  p
                                  └─── Bernoulli on first n−1 ───┘     └ final shot fixed
```

> 🚨 Forgetting the final `× p` is the canonical mark loss on this pattern. Do not apply `C(n,k)·p^k·q^(n−k)` directly — that counts arrangements where the kth success could land anywhere.

### 4. The "at least one" / "at least k" complement trick

```
P(at least k) = 1 − P(fewer than k) = 1 − P(0) − P(1) − … − P(k−1)
```

> For `k = 1`, this collapses to `P(at least one) = 1 − P(none)` — the most common application. Tested ~6/11 years.

---

## 🚨 LOAD-BEARING — the five things that win or lose the Probability question

### 1. Independent events ⟹ probabilities multiply — `probability-3`

> `A` and `B` independent **⟺** `P(A ∩ B) = P(A) · P(B)`.

Used **two ways** in exams:

| Direction | What you do |
|---|---|
| **Given independent**, find `P(A∩B)` | Multiply: `P(A) · P(B)` |
| **Investigate independence** | Compute both sides **separately** from the data; check whether they agree |

> 🚨 **Independence ≠ mutually exclusive.** `probability-3` content warning: *"Independent ↔ causation-free; mutually exclusive ↔ timing."* Two events can be mutually exclusive AND not independent. Two events can be independent AND not mutually exclusive. Do not collapse the two. Tested in 2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025 — basically **every year**.

### 2. The Bernoulli formula + the 4-condition gate — `probability-8`

> `P(R successes in n trials) = C(n, R) · p^R · q^(n−R)` — page 33.

The 4-condition gate (above) comes **first**. Only then substitute `n`, `R`, `p`, `q = 1 − p`. The **"kth time on nth shot"** variant (recipe in §3 of Learning Work) is the recurring trap.

> 🚨 Tested 2015, 2017, 2020, 2021, 2022, 2023, 2024, 2025 — **and every DF sitting 2022–2025**. The 2025 P2 paper used the complement variant: *"P(X ≥ 2) = 1 − P(0) − P(1)"* — two terms instead of four.

### 3. Without replacement: the denominator drops — `probability-3`

> If two items are drawn without replacement, the second draw's denominator is `(n − 1)`, not `n`.

This is conditional probability under another name. Tree diagrams make it visual: multiply along the branches.

> 🚨 **2025 P2 Q9(b)** explicitly trapped this. The MS interpretation is **without replacement** unless the question says otherwise. With-replacement gives a close-but-wrong answer — the marks split between MPC and Full Credit on this distinction.

### 4. Stratified counting + the inclusion-exclusion shortcut — `probability-6`

For compound combinations questions ("at least 4 Germans from 6 chosen", "no more than 2 South Africans"):

| Phrasing | Method |
|---|---|
| "**at least k** of type A" | Enumerate cases `k, k+1, …, max` and **sum** them |
| "**at most k** of type A" | Enumerate `0, 1, …, k` and sum |
| "at least one **from each group**" | **Total minus all-from-one-group** (inclusion-exclusion shortcut) |

> 🚨 Stratified counting recurs 2017, 2019, 2020, 2022, 2023, 2024, 2025. The inclusion-exclusion shortcut saves time when the eligible cases outnumber the ineligible ones.

### 5. Expected value + the "fair game" identity — `probability-9`

> `E(X) = Σ (probability × value)` — page 33.

The **fair game** translation: a game is fair **iff** the expected payout equals the cost per play. Operator profit per play = `(charge) − E(payout)`. Total profit over `N` plays = `N × (profit per play)`.

> 🚨 Tested 2016, 2017, 2018, 2020, 2021, 2022, 2024, 2025. 2024 P2 used the "fair game ⟹ E = cost" framing directly. **Always identify the operator** before computing profits — students confuse who pays whom.

---

## 🎯 The 8 techniques you must execute without thinking

1. **Set up Bernoulli** — state `n`, `R`, `p`, `q = 1 − p`, then substitute into `C(n,R)·p^R·q^(n−R)`. State the 4 conditions if asked.
2. **Venn diagram with X for the unknown intersection** — `probability-2`/`-3`'s canonical exam pattern. Label `A only = P(A) − X`, `B only = P(B) − X`; use `total = 1` to solve for `X`.
3. **Tree diagram** for any 2-stage experiment. Multiply along branches; sum across paths that match the outcome.
4. **Sample-space enumeration** — when in doubt, list outcomes. `P = favourable / possible`. Fundamental Principle of Counting: `m × n`.
5. **Permutations — slot method + block-the-letters** — for "all vowels together" / "M and T together", treat the bunch as ONE object, count arrangements of the resulting (n − k + 1) objects, then multiply by `k!` for internal arrangements.
6. **Combinations — stratified cases or inclusion-exclusion** — pick the route with the fewest cases.
7. **Factorial peel-off** — `n! = n × (n−1)!`. Peel until the denominator cancels. Remember `0! = 1`.
8. **Expected value chain** — for games of chance: (i) compute `E = Σ P·X` over all outcomes; (ii) profit per play = charge − `E`; (iii) long-run profit = `N × (profit per play)`.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Without replacement vs with replacement — wrong denominator | Default to **without replacement** unless told otherwise; second draw uses `(n − 1)` |
| Confusing **independent** with **mutually exclusive** | Independent ↔ multiplication; mutually exclusive ↔ addition. Different concepts. |
| Bernoulli "kth time on nth shot" using `C(n,k)·p^k·q^(n−k)` directly | Fix final trial as success: `C(n−1, k−1)·p^(k−1)·q^(n−k) × p` |
| "At least 2" computed as `1 − P(0)` (forgetting `P(1)`) | `P(≥2) = 1 − P(0) − P(1)`; check the inequality carefully |
| `P(A\|B)` (vertical line) confused with `A \ B` (backslash) | `\|` = conditional probability; `\` = set difference. Paul flags this at `probability-3` [03:59] |
| Block-the-letters: forgetting the internal `× k!` | After bunching `k` items into one block, multiply by `k!` for internal arrangements |
| Confusing **`nPr`** with **`nCr`** | "Arrange / order" → `nPr`; "choose / select" → `nCr` |
| "Fair game" interpreted as `E = 0` | Fair game ⟺ `E(payout) = cost`. Not `E = 0` unless the cost is zero. |
| Forgetting `0! = 1` in factorial fractions | The recursive rule `n! = n·(n−1)!` needs `0! = 1` to terminate |
| "At least one from each group" enumerated case-by-case | Use the inclusion-exclusion shortcut: total − all-from-one-group |
| Not stating the 4 Bernoulli conditions when asked | "Show this is a Bernoulli trial" demands the 4-condition checklist. Method marks. |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Exactly k successes in n trials"* | Bernoulli direct: `C(n,k)·p^k·q^(n−k)` |
| *"At least k successes"* | Complement: `1 − P(0) − P(1) − … − P(k−1)` |
| *"For the kth time on the nth shot/spin/day"* | Fix final trial as success: `C(n−1, k−1)·p^(k−1)·q^(n−k) × p` |
| *"Investigate / show whether independent"* | Compute `P(A∩B)` and `P(A)·P(B)` **separately**; check equality |
| *"Given that A has occurred, …"* | Conditional: `P(B\|A) = P(A∩B)/P(A)` |
| *"All vowels together"*, *"M and T together"* | Block-the-letters; multiply by internal `k!` |
| *"In how many ways can …"* | Counting: `nPr` if order matters, `nCr` if it doesn't |
| *"Choose / select"* | `nCr` |
| *"Arrange / line up / in how many orders"* | `nPr` or slot method |
| *"Without replacement"* (explicit OR default) | Denominator drops by 1 each draw |
| *"Fair game"* | `E(payout) = cost per play` |
| *"How much profit per play"* | Charge − `E(payout)` |

---

## 💡 Three exam-day tips that move the needle

1. **Page 33 is open in front of you.** Every probability formula on the strand lives there — addition rule, multiplication rule, conditional, `nPr`, `nCr`, Bernoulli, expected value. Flip and substitute. Working memory is for **techniques and recipes**, not formulas.

2. **State the 4 Bernoulli conditions, even when the question doesn't ask.** If the question is a Bernoulli setup, naming the conditions costs ~20 seconds and is often worth a method mark — especially in the "show that this is a Bernoulli trial" parts which the SEC has increasingly favoured.

3. **Draw the tree for any multi-stage question.** Trees make conditional probability visual: multiply along branches, sum across paths that match. The MS marking notes routinely award partial credit for "tree diagram drawn correctly" even before any numbers are computed.

---

## 🔗 Cross-strand connections (where else Probability fires)

- **Probability ↔ Algebra (Binomial Theorem)** — `nCr` machinery is identical (page 20 OR page 33). `(p + q)^n` expansion = sum of Bernoulli probabilities.
- **Probability ↔ Statistics (CLT)** — Bernoulli/binomial approximated by the normal distribution when `n` is large. Cross-cited in `probability-8` ↔ `statistics-18`.
- **Probability ↔ Indices & Logs** — "Find smallest `n` such that `q^n < 0.01`" reduces to `n > log(0.01)/log(q)` — `indices-logs-5` territory. Tested 2017, 2024.
- **Probability ↔ Induction** — factorial proofs and `nCr` identities sometimes appear in Paper 1 induction questions.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL P2 main |
|---|---|---|
| Multiplication rule for independent events | `probability-3` | 2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025 |
| Bernoulli formula `C(n,R)·p^R·q^(n−R)` | `probability-8` | 2015, 2017, 2020, 2021, 2022, 2023, 2024, 2025 (+ 2022–25 DF) |
| "kth time on nth shot" — fix final as success | `probability-8` | 2017, 2023; recurring |
| "At least k" via complement | `probability-8`, `probability-1` | 2017, 2023, 2025; ~6/11 years |
| Without-replacement (denominator drops) | `probability-3` | 2017, 2019, 2024, 2025 |
| Stratified counting / inclusion-exclusion | `probability-6` | 2017, 2019, 2020, 2022, 2023, 2024, 2025 |
| Expected value + fair-game / profit-per-play | `probability-9` | 2016, 2017, 2018, 2020, 2021, 2022, 2024, 2025 |
| Addition rule (mutually exclusive vs not) | `probability-2` | 2016, 2024, 2025 |
| Block-the-letters / permutations | `probability-5` | 2018, 2021, 2023, 2024, 2025 |

> If you've internalised everything in this table, you've insured ~85% of the probability marks on the next paper.
