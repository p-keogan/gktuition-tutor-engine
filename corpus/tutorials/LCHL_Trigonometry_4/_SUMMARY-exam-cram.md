# Trigonometry 4 — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Trig 4 before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Trig 4 deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Trig 4 appears in 7/11 years on Paper 2 main** — 11 parts total. It's a small strand by part-count but **mark-dense**: a compound-angle proof is typically 10–15 marks of Section B, and a quadratic-trig equation can run 20+ marks across sub-parts.
- **2024–25 main paper trend.** Both 2024 P2 and 2025 P2 had **0** Trig 4 parts in the main sitting. **But:** 2023 DF, 2024 DF, and 2025 DF all tested it heavily (`sin(A+B)` proof, `cos 105°` evaluation, `sin 2A` proof, `sin(X+Y)` in a Spiral-of-Theodorus context). The pattern: when main sittings skip Trig 4, deferred sittings load it. **A "quiet" 2024–25 main paper signals 2026 is overdue.**
- **Cross-paper reach.** Trig 4 isn't only Paper 2. Double-angle `sin 2θ = 2 sin θ cos θ` fired in **2020 P1 Q8** as the engine of a differentiation question (`A(θ) = 50 sin 2θ` — easier to differentiate than `100 sin θ cos θ`). The page-14 sum formulas also drove the 2018 P1 De Moivre induction proof.
- **Cross-strand reach.** Trig 4 ↔ Differentiation, Integration (power-reduction `sin²x = (1 − cos 2x)/2`), Complex Numbers (De Moivre), Trig 2 (unit-circle solving in step 5 of quadratic-trig), Paper 2 Proofs (the eight trig proofs are cross-listed there).

**The takeaway.** Trig 4 is small by part-count but every part is mark-heavy. Two skipped main sittings in a row makes 2026 a forecastable hot year.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Compound-angle formula — Types 1/2/3 workflow** | 25 min | `trig-4-1` — 9 citations; tested 2015, 2022, 2023, 2023 DF, 2024 DF, 2025 DF |
| **Double-angle formula + three forms of cos 2A** | 20 min | `trig-4-2` — 10 citations; tested 2016, 2018, 2019, 2020 P1, 2021, 2023, 2023 DF, 2024 DF |
| **Trig proofs 1, 4, 5, 7 (the diagram-driven ones)** | 20 min | The Paper 2 Proofs spine; chronological rule is load-bearing |
| **Quadratic-trig 5-step workflow** | 10 min | `trig-4-4` — Paul calls this *"the most difficult questions you could get in trigonometry"* |
| **Power-reduction + 3A split + page-15 product-to-sum** | 10 min | Quick-fire; appears as a step inside other questions |

---

## 📊 Top tutorials by exam frequency (P1 + P2 main + deferred, 11 years)

| Rank | Tutorial | Citations | What it tests |
|---|---|---|---|
| 1 | `trig-4-2` Double Angle Formula | 10 | `sin 2A`, three forms of `cos 2A`, `tan 2A`, power reduction, `3A = 2A + A` |
| 2 | `trig-4-1` Compound Angle Formula | 9 | Six page-14 identities; non-standard-angle evaluation; identity proofs |
| 3 | `trig-4-4` Quadratic Equations | 2 | Identity → substitute → factor → unit-circle each root |
| 4 | `trig-4-8` Trig Proof 4: `cos(A−B)` | 2 | Distance formula + unit circle (Paul's hardest of the eight) |
| 5 | `trig-4-3` Products to Sums | 1 | Page-15 eight formulas; coefficient-scaling trick |
| 6 | `trig-4-5` Trig Proof 1 (Pythagorean) | 1 | Unit circle + distance formula — the chronological foundation |
| 7 | `trig-4-11` Trig Proof 7: `sin(A+B)` | 1 | Complementary-angle bridge from `cos(A−B)` |

> **Read this as:** `trig-4-1` and `trig-4-2` alone account for **19 of 26** Trig 4 citations across the 11-year window. If you have only 45 minutes, spend them here.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 13** | `cos² A + sin² A = 1`; standard-angle ratios in surd form (`cos 45 = 1/√2`, `tan 30 = 1/√3`) | The Pythagorean identity is the workhorse substitution of all of Trig 4 |
| **p. 14** | `sin(A ± B)`, `cos(A ± B)`, `tan(A ± B)`; `sin 2A`, `cos 2A`, `tan 2A` | Every Trig 4 question except the page-15 ones — **copy, don't memorise** |
| **p. 15** | Sum-to-product (four) + product-to-sum (four) | When you see `cos A ± cos B`, `sin A ± sin B`, or `2 cos A cos B` etc. |
| **p. 18** | Distance formula `√[(x₂−x₁)² + (y₂−y₁)²]` | Trig proofs 1 and 3 — the page-18 formula is exempt from the chronological rule |

> **🎯 Don't memorise pages 14 or 15. Copy them.** Paul at `trig-4-1` [01:11]: *"on page 14 and 15 in your maths tables there's another 21 formula all of which are on the Leaving Cert course."* Memorisation invites sign errors; copying is mark-safe.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. The cos sign-flip rule

> `cos(A + B)` has **MINUS** in the formula. `cos(A − B)` has **PLUS**. The cos formulas REVERSE the natural sign-with-sign pattern. The sin formulas don't flip.

The single most-failed memory item in all of Trig 4. Even if you copy from page 14, mis-reading the row swaps the sign. Practise reading the row twice.

### 2. The three forms of `cos 2A` — and how to pick the right one

```
cos 2A = cos²A − sin²A             (default — page 14)
cos 2A = 2 cos²A − 1               (use when you only have cos A)
cos 2A = 1 − 2 sin²A               (use when you only have sin A)
```

Each is derivable from the next via the Pythagorean identity. **Match the form to the variable available in the equation** — the wrong form forces an extra Pythagoras step.

### 3. The power-reduction formulas (NOT on page 14)

```
sin²A = (1 − cos 2A) / 2
cos²A = (1 + cos 2A) / 2
```

Rearrangements of the `cos 2A` alternates. Used in (a) half-angle questions like 2021 P2 Q4(a)(ii) (find `cos θ` from `sin(θ/2)`), and (b) integration of `sin²x` and `cos²x` on Paper 1.

### 4. The LCHL surd convention — `1/√2`, not `√2/2`

LCHL trig keeps surds in the denominator. Calculators output `√2/2`; page 13 prints `1/√2`. Match page 13. From `trig-4-0` [03:08]: *"if your calculator tells you the cos of 45 is root 2 over 2 you should write down 1 over root 2."*

---

## 🚨 LOAD-BEARING — the five things that win or lose the Trig 4 question

### 1. Copy the compound-angle formula from page 14 — don't memorise it

> 🚨 From `trig-4-1` [01:11]. The six identities live on page 14. Memorising them invites the cos sign-flip error. Reading them off takes seconds and is mark-safe. The exam paper expects students to use the log tables; not opening the book is a self-inflicted handicap.

### 2. The chronological rule for the eight trig proofs

> 🚨 From `trig-4-5` [00:22]: *"on page 13, 14, 15 and 16 the formula there read like a story. You are not allowed to use something on the next page in order to prove it."*

Pages 13/14/15/16 are an ordered hierarchy. To prove a formula on page N you may use only formulae on pages ≤ N. Using compound-angle (page 14) to prove the Pythagorean identity (page 13) is circular reasoning — it "works" arithmetically but loses marks. The distance formula (page 18) is exempt because it lives outside the trig hierarchy.

The proofs and what they may use:
- **Proof 1** (`cos²A + sin²A = 1`, page 13): unit circle + distance formula only
- **Proof 4** (`cos(A−B)`, page 14): same diagram as Proof 1, applied to two points on the unit circle
- **Proof 5** (`cos(A+B)`, page 14): derives from Proof 4 by `B → −B`
- **Proof 7** (`sin(A+B)`, page 14): bridges via complementary angle `sin A = cos(90°−A)`

### 3. The cos 2A form-choice strategy

> 🚨 From `trig-4-2` [11:56]: *"the choice of form depends on what variable you HAVE in the question."*

When solving a quadratic-trig equation containing `cos 2x` and `sin x`, use `cos 2x = 1 − 2 sin² x` (eliminates cos, keeps sin). When `cos 2x` is paired with `cos x`, use `cos 2x = 2 cos² x − 1`. Choosing the wrong form leaves you with a mixed equation that needs another substitution — a wasted step under exam time pressure. Tested 2016, 2019, 2021, 2023 — every recent Trig 4 paper.

### 4. The quadratic-trig 5-step workflow

> 🚨 From `trig-4-4` [00:03]: *"the types of questions we're exploring in this video as far as I'm concerned are among the most difficult questions you could get in trigonometry."*

When an equation contains **two incompatible trig terms** — either different angles (`cos 2x` AND `sin x`) or different ratios (`sec² θ` AND `tan θ`):

1. **Apply an identity to unify** into one trig function of one angle
2. **Substitute `y = trig`** to get a clean quadratic-in-y
3. **Factor** the quadratic in y
4. **Reverse-substitute** to get each root as `trig = constant`
5. **Solve via unit circle** (Trig 2.2) — and **DISCARD impossible values** (`cos = 2`) before the unit-circle step, not after

### 5. The diagram IS the proof

> 🚨 From `trig-4-5` [01:00]: *"for the vast majority of these proofs, it's getting the diagram right at the start is the tricky thing."*

Proof 1: unit circle, mark a point as `(cos A, sin A)`. Proof 3 (cosine rule): circle of radius `c` centred at A, vertex B at `(b, 0)`. Proof 4: two points on the unit circle at angles A and B. Get the diagram right and the algebra is two lines. Drill the diagrams until automatic — Paul names this as the tractability gate for all eight proofs.

---

## 🎯 The eight techniques you must execute without thinking

1. **Type 1 compound-angle workflow** (evaluate `sin 75°`, `cos 105°`, `tan 15°` without calculator) — split into standard pair (`75° = 30° + 45°`); apply page-14 formula; substitute page-13 ratios; rationalise final denominator.
2. **Type 2 compound-angle workflow** — given `cos A = 3/5` and `sin B = 9/41`, draw two right triangles, apply Pythagoras on each to recover the missing trig values, then substitute all four into the compound-angle formula. **The Pythagoras working is a marks step — show it.**
3. **Type 3 (trig identity proof)** — start from ONE side (usually LHS), expand using compound-angle formulas, look for terms that cancel (`+cos(π/4)·sinA` and `−cos(π/4)·sinA`) or combine (`2 sin(π/4)·cosA = √2 cosA`). Never start by assuming LHS = RHS.
4. **Double-angle in calculus** — `sin 2θ = 2 sin θ cos θ` rewrites `sin·cos` products as a single trig function, making differentiation/integration mechanical. Tested 2020 P1 Q8.
5. **`3A = 2A + A` split** — for `sin 3A` or `cos 3A` questions: split, apply compound, then double, then Pythagorean. Two canonical results: `sin 3A = 3 sin A − 4 sin³A`; `cos 3A = 4 cos³A − 3 cos A`.
6. **Power-reduction for half-angle questions** — given `sin(θ/2)`, square it and use `sin²(θ/2) = (1 − cos θ)/2` to find `cos θ`. Tested 2021 P2 Q4(a)(ii).
7. **Page-15 sum-to-product / product-to-sum** — identify the formula by the **shape** of the input. `cos A ± cos B` → page-15 formula; `2 sin A cos B` → product-to-sum formula. **Scale the right-hand side** by `k/2` when the question's coefficient `k` isn't 2 (Paul's [07:36] rule).
8. **`sec²θ = 1 + tan²θ`** — Pythagorean identity divided through by `cos²θ`. Not on page 14; derivable in two lines. Used in quadratic-trig questions that mix `sec²` with `tan`.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| `cos(A+B) = cos A cos B + sin A sin B` (wrong sign) | Page 14: cos REVERSES. `cos(A+B)` has MINUS |
| `tan(A+B)` denominator `1 + tan A tan B` (wrong sign) | Tan also reverses: `tan(A+B)` has MINUS in denominator |
| Wrong form of `cos 2A` for the equation at hand | Match the form to the variable: have `cos A` only → `2cos²A − 1` |
| Forgetting `y = 2` is impossible after solving quadratic-in-cos | `sin` and `cos` live in `[−1, 1]`. Discard before unit-circle step |
| Rationalising `1/√2` to `√2/2` (Junior Cycle habit) | LCHL trig: keep `1/√2` to match page 13 |
| Using page-14 to prove a page-13 identity | Chronological rule: only formulae on pages ≤ N to prove page N |
| Assuming `LHS = RHS` and working both sides | Start from ONE side. Two-side circular reasoning loses marks |
| Forgetting to scale page-15 formulas when coefficient isn't 2 | `6 cos 15x cos 3x` → multiply RHS by `6/2 = 3` |
| Not showing Pythagoras working in Type-2 questions | "Show your Pythagoras" is a method mark — write it out |
| Decimalising instead of giving surd form | *"Use compound angle and maths tables"* = no calculator, surds throughout |
| `cos A − cos B = 2 cos · cos` (wrong; it's `−2 sin · sin`) | Page 15: the minus version SWITCHES from cos·cos to −2 sin·sin |
| Forgetting domain halves when substituting `θ/2` | If `0 ≤ θ ≤ 360°`, then `0 ≤ θ/2 ≤ 180°` |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Use compound angle formula and maths tables to evaluate `sin 75°`"* | Type 1 — split angle, apply page 14, substitute page 13 ratios, rationalise |
| *"Given `cos A = …` and `sin B = …`, express `cos(A − B)`…"* | Type 2 — Pythagoras for the two missing trig values, then page-14 formula |
| *"Prove that `sin(A + B) = sin A cos B + cos A sin B`"* | Trig Proof 7 — bridge via `sin A = cos(90° − A)` from `cos(A − B)` |
| *"Show that `cos 2θ = 1 − 2 sin²θ`"* | Compound `B = A` → `cos 2A = cos²A − sin²A` → Pythagorean substitution |
| *"Solve `cos 2x − sin x = 1` for `0 ≤ x ≤ 360°`"* | Quadratic-trig 5-step: use `cos 2x = 1 − 2sin²x`, substitute `y = sin x`, factor, unit-circle each root |
| *"Express `cos 6x − cos x` as a product"* | Page-15 sum-to-product: `−2 sin((A+B)/2) sin((A−B)/2)` |
| *"Express `6 cos 15x cos 3x` as a sum"* | Page-15 product-to-sum; scale RHS by `6/2 = 3` |
| *"Given `sin(θ/2) = 1/√5`, find `cos θ`"* | Half-angle via `cos θ = 1 − 2 sin²(θ/2)` |
| *"Find `sin(X + Y)` exactly given right triangles with hypotenuses √26, √27"* | Read off `sin X, cos X, sin Y, cos Y` from each triangle; apply compound-angle |

---

## 💡 Three exam-day tips that move the needle

1. **Open page 14 before you read the question.** The exam pays no extra marks for memorising the compound-angle formulas; copying them takes seconds and prevents the cos sign-flip error. For Trig 4 questions, page 14 should be open the entire time.

2. **For trig proofs, draw the diagram first, write the algebra second.** Paul names the diagram as the tractability gate for all eight proofs. A blank-page student who starts writing algebra without the unit circle drawn is solving the wrong problem.

3. **Don't fight an impossible trig value.** If your quadratic-in-y gives `y = 2`, that's `cos = 2` — impossible. Discard immediately, move to the other root. Students who try to apply ASTC and reference angles to `cos = 2` lose 3–5 minutes on a problem with no solution.

---

## 🔗 Cross-strand connections (where else Trig 4 fires)

- **Trig 4 ↔ Paper 2 Proofs** — the eight trig proofs (`trig-4-5` through `trig-4-12`) are cross-listed in the Paper 2 Proofs spine. Same videos, two homes.
- **Trig 4 ↔ Trig 2 (Unit Circle)** — step 5 of every quadratic-trig question is unit-circle work (Trig 2.2). Trig 4 doesn't end; it hands off.
- **Trig 4 ↔ Trig 1 (Pythagoras + Complementary Angles)** — Type-2 compound questions use Pythagoras to recover missing trig values; Proof 7 uses `sin A = cos(90° − A)`.
- **Trig 4 ↔ Differentiation** — `sin 2θ = 2 sin θ cos θ` rewrites products as single trig functions, simplifying derivatives. Tested 2020 P1 Q8.
- **Trig 4 ↔ Integration** — power-reduction `sin²x = (1 − cos 2x)/2` is the standard substitution for `∫ sin² x dx`; page-15 product-to-sum simplifies `∫ sin · cos` integrals.
- **Trig 4 ↔ Complex Numbers (De Moivre)** — `cos 3A` and `sin 3A` can be derived from `(cos A + i sin A)³` using De Moivre; 2018 P1's De Moivre induction proof used page-14 `sin(A+B)` and `cos(A+B)` as its closing step.
- **Trig 4 ↔ The Line / Coordinate Geometry** — distance formula (page 18) is used in Proofs 1 and 3; coordinate geometry is exempt from the trig chronological rule.

> Trig 4 is a Paper 2 strand on paper. In practice, its formulas fire across both papers and several strands.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Compound-angle proof / evaluation (cos sign-flip) | `trig-4-1` | 2015 P2, 2022 P2, 2023 P2, 2023 DF P2, 2024 DF P2, 2025 DF P2 |
| Three forms of `cos 2A` / `sin 2A` derivation | `trig-4-2` | 2016 P2, 2018 P2, 2019 P2, 2020 P1, 2021 P2, 2023 P2, 2023 DF P2, 2024 DF P2 |
| Quadratic-trig 5-step workflow | `trig-4-4` | 2015 P1, 2023 P2 |
| Trig proofs (chronological rule + diagram) | `trig-4-5/8/11` | 2015 P2 (tan(A+B)), 2019 P2 (`cos 2θ`), 2021 P2 (`cos 2A`), 2022 P2 (tan(A−B)), 2023 P2 (`sin(A+B)`), 2023 DF P2 (`sin(A+B)`), 2024 DF P2 (`sin 2A`) |
| Page-15 sum-to-product | `trig-4-3` | 2016 P2 |
| Power-reduction (half-angle) | `trig-4-2` | 2021 P2 Q4(a)(ii) |

> If you've internalised every row of this table, you've covered every Trig 4 citation in the 11-year exam record — and you're ready for the strand to surge in 2026 after two quiet main sittings.
