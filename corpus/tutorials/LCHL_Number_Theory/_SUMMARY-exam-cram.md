# Number Theory — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Number Theory before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Number Theory deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Number Theory appears in 5/11 years on Paper 1** — 10 parts total. Pre-2019 it was zero; from 2019 it's a regular feature.
- **It's small but spiky.** When it appears, it dominates: 2019 P1 Q6(b) was a 10-mark prescribed proof; 2023 P1 Q3(a) was the same proof again; 2023 P1 Q9(a) was three connected divisor-counting parts inside a 50-mark Section B.
- **2024–25 trend.** Both 2024 and 2025 had only **1** cross-strand Number Theory part each — the strand was light. **But:** the `√2` proof's prescribed-proof status means examiners can drop it in any year without warning. A "quiet year" doesn't mean a quiet 2026.
- **Cross-strand reach.** Number Theory 1's set-notation (`ℕ ⊂ ℤ ⊂ ℚ ⊂ ℝ ⊂ ℂ`) is the **shared vocabulary** of every other strand. Complex Numbers borrows the Venn-classification structure (2022 DF P1 Q1(c)). Construct `√3` migrated onto Paper 2 in 2022 DF Q6(a).

**The takeaway.** Number Theory is small in part-count but heavy in marks-per-question. The `√2` proof alone is worth 10 marks of Section A in a tested year. You can't afford to skip it.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **The `√2` irrational proof — 8-step skeleton** | 30 min | `number-theory-3` — tested 2019, 2023; one of the **five prescribed P1 proofs** |
| **Divisor-counting `(a₁+1)(a₂+1)…`** | 15 min | `number-theory-2` — tested 2023 P1 Q9(a) as a 3-part Section B spine |
| **Types of numbers + Venn classification** | 15 min | `number-theory-1` — tested 2022 DF P1 Q1(c); fires inside other strands every year |
| **Construct `√2` (right triangle, legs 1)** | 10 min | `number-theory-4` — syllabus-named outcome |
| **Construct `√3` (vesica piscis, Pythagoras on half-altitude)** | 15 min | `number-theory-5` — tested 2022 DF P2 Q6(a); the harder of the pair |

---

## 📊 Top tutorials by exam frequency (P1 main + deferred, 11 years)

| Rank | Tutorial | Citations | What it tests |
|---|---|---|---|
| 1 | `number-theory-3` Proof `√2` is irrational | ~5 | The prescribed proof-by-contradiction (one of five Paper 1 proofs) |
| 2 | `number-theory-2` Prime Factorisation | ~3 | Division ladder; HCF/LCM via Venn; divisor counting |
| 3 | `number-theory-1` Types of Numbers | ~3 | `ℕ ⊂ ℤ ⊂ ℚ ⊂ ℝ ⊂ ℂ`; rational vs irrational classification |
| 4 | `number-theory-4` Construct `√2` | ~2 | Geometric construction — Pythagoras with legs `1, 1` |
| 5 | `number-theory-5` Construct `√3` | ~1 | Vesica piscis; half-altitude `√3/2`, doubled by symmetry |

> **Read this as:** the strand has only 5 tutorials. You can revise it cover-to-cover in 90 minutes. Most strands can't say that.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 16** | `a² + b² = c²` (Pythagoras) | Both constructions — `1² + 1² = (√2)²` and `(1/2)² + (√3/2)² = 1²` |
| **p. 24** | Logic symbols `∈, ∧, ∨, ¬, ⇒, ⇔, ∀, ∃` | Reading the question stem when it uses set notation |

> **🎯 Notice how short this is.** Number Theory is the strand where the log tables help you least. Almost everything is **learning work** — definitions, the proof skeleton, the construction recipe. Don't expect the booklet to bail you out.

---

## 📚 Learning work — what must be in your head before you sit down

### 1. The set hierarchy `ℕ ⊂ ℤ ⊂ ℚ ⊂ ℝ ⊂ ℂ`

- `ℕ` = `{1, 2, 3, …}` — **starts at 1** in LCHL convention, not 0
- `ℤ` = `{…, −2, −1, 0, 1, 2, …}` — adds zero and negatives
- `ℚ` = anything expressible as `a/b` in **simplest form** with `a, b ∈ ℤ`, `b ≠ 0`
- `ℝ` = rationals ∪ irrationals — every number on the number line
- `ℂ` = generalisation including `i² = −1`

### 2. The rational/irrational classification trap-list

- **`1` is NOT prime** (only one divisor). **`2` is the only even prime.** From `number-theory-1` [00:59].
- **Recurring decimals ARE rational** — `0.3̇ = 1/3`, `0.9̇0̇ = 10/11`. Non-recurring forever is what makes a number irrational.
- **`0` is rational** (`= 0/1`). Catches students in Venn-classification questions.
- **`√n` is irrational only if `n` is not a perfect square** — `√4 = 2` is rational.

### 3. The divisor-counting formula (Section B 2023 spine)

For `N = p₁^(a₁) × p₂^(a₂) × … × p_k^(a_k)` (distinct primes):

```
d(N) = (a₁ + 1)(a₂ + 1) … (a_k + 1)
```

> **Not in the log tables, not named in the syllabus** — but the reasoning (Fundamental Theorem + multiplication principle) is on-syllabus, and 2023 P1 Q9(a)(iii) needed exactly this for `2¹⁰ × 3¹²` → `11 × 13 = 143` factors.

### 4. The `√2` irrational proof — the 8-step skeleton

This is **the** load-bearing piece of the strand. Memorise as a chain:

```
1. Assume √2 is rational → √2 = a/b, a,b ∈ ℤ, in simplest form
2. Square both sides              → 2 = a²/b²
3. Clear the denominator          → 2b² = a²
4. 2b² is even ⇒ a² is even ⇒ a is even
5. Substitute a = 2k              → 2b² = 4k² → b² = 2k²
6. By the same parity argument    → b is even
7. Both a and b even ⇒ a/b NOT in simplest form ← CONTRADICTION
8. Therefore √2 is irrational. ∎
```

---

## 🚨 LOAD-BEARING — the four things that win or lose the Number Theory question

### 1. The explicit conclusion line — *"Therefore √2 is irrational"*

Every prescribed proof on LCHL Paper 1 ends with an explicit *"Therefore …"* statement. The marking scheme awards a discrete mark for the conclusion sentence, separate from the algebra.

> 🚨 **From `number-theory-3` and the 2019/2023 MS notes.** *"A proof without an explicit conclusion sentence is marked down even with flawless algebra. The conclusion is the **point** of the proof — write it."* Students who do all eight algebra lines and forget the *"Therefore"* lose marks they could not afford. Tested 2019 P1 Q6(b), 2023 P1 Q3(a) — both with the conclusion explicitly required.

### 2. The "even square ⇒ even base" justification

Step 4 of the proof is where students stumble. Why does `a²` being even force `a` to be even?

| `n` | `n²` | parity match |
|---|---|---|
| 2 | 4 | even/even |
| 3 | 9 | odd/odd |
| 4 | 16 | even/even |
| 5 | 25 | odd/odd |

> 🚨 Paul's empirical argument from `number-theory-3` [06:15]: the parity of `n²` matches the parity of `n`. So if `a²` is even, `a` cannot be odd — it must be even. The formal version: `(2k+1)² = 2(2k²+2k) + 1`, which is odd; contrapositive gives the result. **Drill this — it's the step the MS singles out for Mid-Partial credit.**

### 3. The contradiction comes from "simplest form", not from the algebra

> 🚨 **The contradiction is NOT "both `a` and `b` are even" by itself.** It's that both being even contradicts the **simplest-form** assumption you made at the start. Without naming "simplest form" in step 1, you have no contradiction to name in step 7.

Students lose this mark by writing *"…but `a/b` is a fraction, contradiction"* instead of *"…but `a/b` was in simplest form, contradiction"*. The simplest-form clause is load-bearing; cite it in step 1 **and** invoke it in step 7.

### 4. The maths-set requirement — visible compass arcs, not freehand

> 🚨 From `number-theory-4` and the corpus-wide voice guide: *"the marker awards no marks unless it is visually clear from the diagram that the student used a maths set."* Constructions drawn freehand — even if geometrically correct — score zero on the construction marks.

For `√2`: ruler for `|AB|=1`, **set square** for the perpendicular at B, **compass** for the radius-1 circle, ruler for AC.
For `√3`: ruler for `|AB|=1`, **compass** for both radius-1 circles (the two visible arcs ARE the marks). No set square needed — perpendicularity emerges from the chord-bisector theorem.

Tested 2022 DF P2 Q6(a) (Construct `√3`). The MS docks marks for invisible compass work.

---

## 🎯 The seven techniques you must execute without thinking

1. **Read set-membership notation fluently.** `x ∈ ℕ` ⇒ positive integer; `x ∈ ℤ` ⇒ integer (incl. zero, negatives); `x ∈ ℚ` ⇒ rational; `x ∈ ℝ` ⇒ real; `x ∈ ℂ` ⇒ complex. Paul [00:19]: *"the question is simply going to say something like x is an element of ℕ."*
2. **Division-ladder for prime factorisation.** Start at 2; if it divides, keep dividing by 2 until it doesn't; move to 3; continue up the primes (5, 7, 11, 13, 17, …); stop when you reach 1. Group repeated primes as exponents.
3. **HCF / LCM by Venn diagram.** Each number's prime factors fill one circle; the **intersection** holds shared primes at the **lowest** shared exponent. HCF = product of intersection; LCM = product of every prime in the diagram (each at its **highest** exponent).
4. **Squaring to eliminate a surd.** `√2 = a/b` → `2 = a²/b²`. Same machinery as `algebra-17`, applied as step 2 of the proof. (Algebra-17's verification step doesn't apply here — this is a one-way deduction inside a proof.)
5. **Write any even number as `2k`.** The substitution `a = 2k` (for some `k ∈ ℤ`) is the definition of "even" used algebraically. Squaring gives `4k²`, the move that produces `b² = 2k²` and re-triggers the parity argument.
6. **Construct `√2`:** unit segment AB → set-square perpendicular at B → compass circle radius 1 centred at B → mark intersection C → AC has length `√2` (Pythagoras: `1² + 1² = 2`).
7. **Construct `√3`:** unit segment AB → compass circle radius 1 at A → second compass circle radius 1 at B (vesica piscis) → mark intersections C (above) and D (below) → AB ⊥ CD at midpoint O (chord-bisector theorem) → right triangle AOC has `|AO| = 1/2`, `|AC| = 1`, so `|CO| = √3/2` → by symmetry `|CD| = √3`.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Forgetting the *"Therefore √2 is irrational"* conclusion line | Always write it explicitly as the last line of the proof |
| Citing the contradiction as "both even" without naming "simplest form" | Step 1 sets up simplest form; step 7 must invoke it by name |
| Calling `1` a prime number | `1` has only one divisor; it's neither prime nor composite |
| Calling recurring decimals irrational | `0.3̇ = 1/3`, `0.9̇ = 1`. Recurring = rational |
| Calling `√17` "not a real number" | `√17` is real; it's just not rational. It sits in `ℝ \ ℚ` |
| Freehand constructions (no visible compass arcs) | Zero construction marks. The arcs ARE the evidence |
| Adding `(n+1) + (m+1)` instead of multiplying for divisor counts | Independent choices multiply: `(n+1)(m+1)` |
| Off-by-one in divisor counting (`n` instead of `n+1`) | Exponent runs `0, 1, …, n` — that's `n+1` values, not `n` |
| Skipping `p⁰ = 1` from the factor list of `pⁿ` | `1` is always a factor; it's `p⁰` in the powers-of-`p` framing |
| Listing only one of two surd roots in `a ± b√c` form | Both signs every time — *"Full Credit minus 1"* trap (2023 DF P1) |
| Treating LCHL `ℕ` as including 0 | LCHL convention: `ℕ` starts at 1. For 0, use `ℤ` or `ℕ ∪ {0}` |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Prove, using contradiction, that `√2` is not a rational number"* | The 8-step skeleton. End with the explicit conclusion line. |
| *"Show that `√3` is irrational"* | Same skeleton with "even" replaced by "divisible by 3" |
| *"Write `N` as a product of prime factors"* | Division ladder from 2 upward; group repeats as exponents |
| *"Find the HCF and LCM of `M` and `N`"* | Prime-factorise both; Venn diagram; intersection = HCF, full diagram = LCM |
| *"How many different factors does `pⁿ` have?"* | `n + 1`. (Or `(a₁+1)(a₂+1)…` for products of prime powers.) |
| *"Construct a segment of length `√2`"* | Right triangle with legs 1, 1. Visible set square + compass + ruler. |
| *"Construct a segment of length `√3`"* | Two overlapping unit circles. Visible compass arcs from both. |
| *"Classify each number in the Venn diagram with `ℝ`, `ℂ`, `X` …"* | Write each number as `a + bi`. Check (i) `b = 0` (real?), (ii) are `a`, `b` both rational? |
| *"Is `0.3̇` rational?"* / *"Is `√17` real?"* | Yes / Yes. Don't second-guess the trap. |

---

## 💡 Three exam-day tips that move the needle

1. **Rehearse the `√2` proof in writing, not just in your head.** The 8 steps fit on half a page; write them out cold once before the exam. If it appears on the paper, you've already done the question.

2. **Show every line of the proof — even the "obvious" ones.** *"2b² is even because every multiple of 2 is even."* That's a mark. The MS rewards the small justifications students skip because they feel redundant.

3. **Bring a working maths set.** Both `√2` and `√3` constructions need a compass; `√2` also needs a set square. Without the tools, you can't earn the construction marks — and the exam paper specifies a maths set as standard equipment.

---

## 🔗 Cross-strand connections (where else Number Theory fires)

- **Number Theory ↔ Paper 1 Proofs** — `number-theory-3` is cross-listed as Paper 1 Proofs §1. Same video, two homes in the spine.
- **Number Theory ↔ Complex Numbers (§4.4)** — set-notation `ℂ` and the Venn classification (`ℝ`, `ℂ`, "rational parts") tested 2022 DF P1 Q1(c).
- **Number Theory ↔ Algebra-17 (Surd Equations)** — squaring both sides to eliminate `√` is the same move used in step 2 of the `√2` proof.
- **Number Theory ↔ Algebra (Fractions)** — the LCM technique from `number-theory-2` is the same LCM used to clear denominators in `algebra-4`.
- **Number Theory ↔ Induction (§3.1 also)** — the two proof techniques on the LCHL syllabus. Contradiction proves *"this is impossible"*; induction proves *"this holds for all `n ∈ ℕ`"*.
- **Number Theory ↔ Indices and Logs** — domain awareness (`ln x` requires `x > 0`); scientific-notation conventions (`a × 10ⁿ` with `1 ≤ a < 10`).
- **Number Theory ↔ Trigonometry / Geometry** — Pythagoras (log tables p. 16) is the engine for both constructions; the construction discipline (visible maths-set use) is the same as Geometry §2's 22-construction list.
- **Number Theory ↔ Paper 2** — Construct `√3` appeared on **Paper 2** in 2022 DF Q6(a), not Paper 1. The strand crosses papers.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| `√2` irrational proof — 8-step skeleton + explicit conclusion | `number-theory-3` | 2019 P1 Q6(b); 2023 P1 Q3(a) |
| Divisor-counting `(n+1)` rule + multiplication principle | `number-theory-2` | 2023 P1 Q9(a)(i)(ii)(iii) |
| Venn classification with `ℝ, ℂ`, rational parts | `number-theory-1` | 2022 DF P1 Q1(c) |
| Construct `√3` — vesica piscis + Pythagoras on half-altitude | `number-theory-5` | 2022 DF P2 Q6(a) |
| Set-notation literacy (cross-strand) | `number-theory-1` | 2019, 2021, 2024, 2025 (cross-strand citations) |

> If you've internalised every row of this table, you've covered every Number Theory citation in the 11-year exam record.
