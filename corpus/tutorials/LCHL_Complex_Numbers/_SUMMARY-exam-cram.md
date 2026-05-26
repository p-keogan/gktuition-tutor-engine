# Complex Numbers — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Complex Numbers before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Complex Numbers deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025, 30 papers, 1,212 tagged question-parts):

- **Complex Numbers appears in 11/11 years on Paper 1.** Average ≈ 3.0 parts per paper. Total: **33 P1 parts**.
- **Almost entirely Section A** (32 of 33 parts). It's the reliable Q1–Q3 slot — *"~30 marks reliably available; the De Moivre pipeline is the harder end"* per the exam-trends note.
- **No 2024–25 surge — steady weighting.** 2024 had 4 parts and 2025 had 3 parts, within 1 of the historical mean. Plan for the same shape in 2026, not a heavier hit.
- **Cross-strand reach:** Conjugate Root Theorem closes Algebra 12 Scenario 3 (cubics with non-real roots); polar form leans entirely on **page 13 reference angles** from Trigonometry's unit circle; De Moivre's theorem is one of the five P1 named proofs (tested 2018) and feeds the proof of `sin 3A` / `cos 3A` (tested 2025).

**The takeaway.** Complex Numbers is a small strand by part-count but **the most regularly examined slot in Section A**. The whole strand is mechanical — once the polar-form quadrant rules and the four-step De Moivre pipeline are reflexive, ~30 marks are routine.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Polar form + quadrant rules** | 20 min | CN 10 — **15 P1 citations** (most-cited tutorial in the strand); the single highest-error step in the whole strand |
| **The four-step De Moivre pipeline** | 15 min | CN 13 — 12 citations; tested 2016, 2017, 2018, 2020, 2022, 2023, 2024, plus three deferreds |
| **Multi-valued nth roots (add `2πk`, iterate)** | 15 min | CN 14 — 9 citations; tested 2015, 2019, 2021, 2023, 2025 + every recent deferred |
| **Rectangular arithmetic + `i² = −1`** | 10 min | CN 2 — 10 citations; the foundation, tested every year |
| **Conjugate-pair theorem on quadratics/cubics** | 10 min | CN 8 + CN 9 — 7 citations; tested 2016, 2019, 2023, 2024, 2025 DF |
| **Quick-fire:** modulus, division by conjugate, equating coefficients, rotations | 15 min | CN 3 / CN 4 / CN 6 / CN 7 — formula-sheet driven; rotations growing in 2023–25 |

---

## 📊 Top tutorials by exam frequency (P1 main + deferred, 11 years)

| Rank | Tutorial | P1 citations | What it tests |
|---|---|---|---|
| 1 | `complex-numbers-10` Introduction to Polar Form | **15** | Quadrant-adjusted argument; `R(cos θ + i sin θ)` |
| 2 | `complex-numbers-13` Polar + De Moivre pipeline | **12** | The full 4-step `(a+bi)ⁿ` recipe |
| 3 | `complex-numbers-12` De Moivre's Theorem | **11** | `[R(cos θ + i sin θ)]ⁿ = Rⁿ(cos nθ + i sin nθ)` |
| 4 | `complex-numbers-2` Addition/Subtraction/Multiplication | **10** | `i² = −1`; rectangular arithmetic |
| 5 | `complex-numbers-14` De Moivre — multiple answers | **9** | Add `2πk`, iterate `k = 0, ..., n−1` |
| 6 | `complex-numbers-8` Quadratic Equations | **7** | Conjugate-pair theorem (real coefficients only) |
| 7 | `complex-numbers-3` Division and Conjugates | 6 | Multiply top + bottom by conjugate |
| 8 | `complex-numbers-4` Argand Plane and Modulus | 5 | `\|z\| = √(a²+b²)`; geometric viewpoint |
| 9 | `complex-numbers-5` Modulus and Conjugates | 5 | `z · z̄ = a² + b²` identity |
| 10 | `complex-numbers-7` Rotations | 4 | Multiplying by `i` = 90° rotation; growing in deferreds |

> **Read this as:** if you only have 90 minutes, tutorials 1–3 (polar form + De Moivre + the pipeline) account for **38 cited appearances across Paper 1**. Do not skip them.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 20** | `[r(cos θ + i sin θ)]ⁿ = rⁿ(cos nθ + i sin nθ)` | De Moivre's theorem (and its proof if asked) |
| **p. 13** | Reference angles: `tan⁻¹(1) = 45°`, `tan⁻¹(1/√3) = 30°`, `tan⁻¹(√3) = 60°` | Polar-form argument lookup — Paul cites page 13 six times in CN 10 alone |
| **p. 21** | Index laws | Pre-simplifying `(a+bi)ⁿ · (a+bi)ᵐ` before applying De Moivre |
| **p. 20** | Quadratic formula `x = (−b ± √(b² − 4ac))/(2a)` | Quadratics with non-real coefficients (where conjugate-pair fails) |

> **🎯 The argument θ is NOT given on the log tables.** You compute the reference angle from page 13, then apply the quadrant adjustment from memory. The reference table doesn't tell you which quadrant you're in — that's on you.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. The four quadrant-adjustment rules

| Quadrant | Sign of `(a, b)` | Argument θ (degrees) | Argument θ (radians) |
|---|---|---|---|
| **Q1** | `(+, +)` | `θ = ref` | `θ = ref` |
| **Q2** | `(−, +)` | `θ = 180° − ref` | `θ = π − ref` |
| **Q3** | `(−, −)` | `θ = 180° + ref` | `θ = π + ref` |
| **Q4** | `(+, −)` | `θ = 360° − ref` | `θ = 2π − ref` |

> Drill until you can write the four rules in 20 seconds without thinking. The reference angle from `tan⁻¹` is always 0°–90°; the argument lives in 0°–360°. Forgetting the adjustment is *the* most common student error in this strand.

### 2. The four-step De Moivre pipeline (`(a+bi)ⁿ`)

```
1. Convert    (a+bi)         → R(cos θ + i sin θ)         [CN 10]
2. Restate    [...]ⁿ
3. De Moivre  → Rⁿ(cos nθ + i sin nθ)                     [CN 12, page 20]
4. Simplify   → a' + b'i      (rectangular form)
```

> **Default deliverable: rectangular form.** Paul at CN 12 [00:56]: *"in these questions it's assumed that you will simplify this further and that you will write your answer in rectangular form."*

### 3. Sum-and-product → reconstruct the quadratic

Given two roots `α` and `β` (in a CN strand question, you usually KNOW the roots and need the quadratic — the inverse direction of the algebra strand):

```
z² − (α + β)z + (αβ) = 0
```

For a real-coefficient quadratic with complex root `2 + 3i`: conjugate is `2 − 3i`; sum `= 4`, product `= 2² + 3² = 13`; quadratic is `z² − 4z + 13 = 0`.

### 4. The "p + qi" form rule

Always write the final answer as `p + qi`, even when `p = 0`. Marking-scheme deduction (*"Full Credit −1"*) for writing `5832i` instead of `0 + 5832i`. Tested 2022 DF, 2024.

---

## 🚨 LOAD-BEARING — the five things that win or lose the complex-numbers question

### 1. `i² = −1` substitution

Every rectangular multiplication question. `(a + bi)(c + di) = ac + adi + bci + bdi² = (ac − bd) + (ad + bc)i`. The `bd` term flips sign because of `i² = −1`.

> 🚨 This is the foundation. Tested every single year 2015–2025 — it's the entry point of every Q1/Q2 complex-numbers part. (CN 2.)

### 2. Quadrant adjustment of polar arguments

The reference angle from `tan⁻¹` is always 0°–90°. The argument θ lives in 0°–360°. The quadrant of `(a, b)` determines the adjustment. From CN 10:

> 🚨 **This is THE most common student error in polar form.** Paul at CN 10 [03:36]: *"You always join it to the horizontal line"* — never to the imaginary axis. Form the right-angle triangle to the real axis, find the reference angle, then quadrant-adjust. Provide both degrees AND radians where context allows (exams split 50/50). Tested 2015, 2018, 2020, 2022, 2022 DF, 2024.

### 3. The four-step De Moivre pipeline

For any `(a + bi)ⁿ` with `n ≥ 3`, binomial expansion is painful. The pipeline turns it into one line of arithmetic:

```
(a + bi)ⁿ  →  R(cos θ + i sin θ)  →  Rⁿ(cos nθ + i sin nθ)  →  rectangular
```

> 🚨 **Pipeline mandatory for `n ≥ 3`.** Tested 2016, 2017, 2018, 2020, 2022, 2023, 2024 + 2023 DF, 2024 DF, 2025 DF. The recurrence is the highest of any technique in the strand.

### 4. Multi-valued nth roots — add `2πk` before applying De Moivre

For fractional powers `1/n`:

```
[R(cos θ + i sin θ)]^(1/n) = R^(1/n) [cos((θ + 360°k)/n) + i sin((θ + 360°k)/n)]
                              for k = 0, 1, ..., n − 1
```

The `n` roots are evenly spaced around a circle of radius `R^(1/n)` — the vertices of a regular `n`-gon.

> 🚨 Paul flags CN 14 as the **hardest video in the strand**. The two failure modes: (a) forgetting `2πk` (you only get one of the `n` roots), (b) stopping at the wrong `k` (iterate `k = 0` to `k = n − 1`, not `k = 1` to `k = n`).
>
> **Sketch the n-gon to verify.** If your roots aren't evenly spaced, you've made a mistake. Tested 2015, 2019, 2021, 2023, 2025 + 2023 DF, 2024 DF, 2025 DF — **every recent deferred sitting**.

### 5. Conjugate-Root Theorem requires REAL coefficients

> If `z² + az + b = 0` has **all-real coefficients** and `α = p + qi` is a root, then `ᾱ = p − qi` is also a root. **If any coefficient is non-real, conjugate-pair fails — use the `−b` formula directly.**

Extends to cubics: a real-coefficient cubic with one complex root has its conjugate as a second root AND one real root (parity argument: 3 roots total; non-real roots come in pairs).

> 🚨 Paul at CN 8 [content warning #1]: *"the first half of the video … all have real a, b, c — conjugate-pair applies. The last section … has non-real coefficients — conjugate-pair fails."* Tested 2017, 2019, 2023 DF (full 3-step recipe), 2024. The 2025 DF cubic-with-complex-root question closes the loop on Algebra 12 Scenario 3.

---

## 🎯 The 7 techniques you must execute without thinking

1. **Equating real and imaginary parts** — one complex equation becomes TWO real equations. Paul at CN 6 [01:09]: *"don't move terms across the equals sign before splitting."* Split first, then solve the two-equation system.
2. **Multiply numerator and denominator by the conjugate** to rationalise a complex division. The conjugate of `a + bi` is `a − bi` — only the imaginary sign flips. (CN 3.)
3. **Single-imaginary denominator** (e.g. `4i`): multiply top and bottom by `4i` itself, not by its conjugate. `(4i)² = −16` is real. (CN 8.)
4. **Sum-and-product to form a quadratic** from given roots: `z² − (sum)z + (product) = 0`. Faster than expanding `(z − α)(z − β)`.
5. **Sketch the n-gon** of the `n` nth roots — vertices of a regular `n`-gon, radius `R^(1/n)`, first vertex at angle `θ/n`. Visual sanity check.
6. **Reference angle on page 13** — `tan(ref) = |b|/|a|`. Paul reads it straight off the maths tables; don't compute by hand.
7. **Rotation by multiplying by `i`** — `iz` rotates `z` by 90° anti-clockwise around the origin. `iⁿ` cycles through `1, i, −1, −i`. (CN 7 — growing in 2023–25 deferreds.)

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Computing the reference angle but forgetting the quadrant adjustment | Always sketch the Argand diagram; identify the quadrant from sign of `(a, b)` |
| Applying conjugate-pair theorem when coefficients are not all real | Check `a, b, c ∈ ℝ` first; if not, use the `−b` formula |
| Writing `5832i` instead of `0 + 5832i` | Always `p + qi` form, even when `p = 0` — MS deducts a full credit |
| Joining the complex number to the imaginary axis (vertical) when finding the reference angle | Always join to the HORIZONTAL axis. Paul, CN 10 [09:50] |
| Conjugate of `a + bi` written as `−a − bi` (both signs flipped) | Only the imaginary sign flips: conjugate is `a − bi` |
| For `n`th roots, stopping at `k = n` instead of `k = n − 1` | `k = n` gives the same root as `k = 0` — stop at `n − 1` |
| Only finding one nth root (forgetting `2πk` entirely) | Multi-valued De Moivre requires `2πk`; iterate `k = 0, ..., n − 1` |
| Cubic with all-real coefficients listing only two roots | Three roots: one real + one conjugate pair — list all three |
| Mixing degrees and radians mid-question | Pick one and stick with it; convert only at the end if needed |
| Expanding `(a+bi)ⁿ` by binomial when `n ≥ 3` | Use the four-step pipeline — binomial is painful and error-prone |
| `tan⁻¹` interpreted directly as the argument | `tan⁻¹` returns `(−90°, 90°)` only; reference angle ≠ argument until quadrant-adjusted |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Express `z` in the form `a + bi`"* | Rectangular-form deliverable; finish with Step 4 of the pipeline |
| *"Express `z` in polar form"* | Stop after Step 1 — `R(cos θ + i sin θ)` with quadrant-adjusted θ |
| *"Use De Moivre's theorem to evaluate `(a+bi)ⁿ`"* | Four-step pipeline (CN 13) |
| *"Find all values of `z` such that `zⁿ = w`"* | Multi-valued (CN 14): add `2πk`, iterate `k = 0, ..., n − 1` |
| *"Prove De Moivre's theorem by induction"* | Named P1 proof (CN 16) — 4-step induction structure |
| *"`α` is one root of the quadratic … find the others"* | Conjugate-pair theorem (if real coefficients); then sum-and-product or quadratic formula |
| *"Solve the cubic given that `α` is a root"* | Conjugate gives root #2; then factor out `(z − α)(z − ᾱ)` quadratic; linear factor → real root |
| *"Show that `\|z₁ · z₂\| = \|z₁\| · \|z₂\|`"* | Modulus identities; expand via `z · z̄ = a² + b²` |
| *"Investigate / describe the rotation"* | Multiplying by `i` = +90°; multiplying by `−i` = −90°; multiplying by `cos α + i sin α` = +α |

---

## 💡 Three exam-day tips that move the needle

1. **Sketch the Argand diagram for every polar-form question.** Five seconds spent placing `(a, b)` on the plane identifies the quadrant and prevents the #1 strand error. The diagram is also a method mark in its own right.

2. **Use the log tables for `[r(cos θ + i sin θ)]ⁿ` (page 20) and reference angles (page 13).** Don't waste working memory on either. Page 13 is open in front of you — write the reference-angle lookup directly from the table.

3. **For any `n`th-root question, write `k = 0`, `k = 1`, …, `k = n − 1` as headings BEFORE solving each.** Auto-mark structure; the `n` roots become a single mechanical drill instead of a search.

---

## 🔗 Cross-strand connections (where else Complex Numbers fires)

- **Complex Numbers ↔ Algebra (§4.2)** — Conjugate Root Theorem closes Algebra 12 Scenario 3 (cubics with non-real roots). Every cubic-with-complex-root question is a CN-strand question wearing an algebra hat. Tested 2025 DF P1.
- **Complex Numbers ↔ Trigonometry (unit circle)** — Polar form *is* the unit circle dressed up. Quadrant rules (Q2: 180°−ref; Q3: 180°+ref; Q4: 360°−ref) come straight from unit-circle symmetry. Page 13 reference-angle lookups are the single most-fired cross-strand bridge in CN.
- **Complex Numbers ↔ Trigonometry compound angles** — Proof of `sin 3A` and `cos 3A` via De Moivre's theorem (CN 17). Tested 2025 P1 — the cross-strand proof that closes the De Moivre arc.
- **Complex Numbers ↔ Induction** — Proof of De Moivre's theorem by induction (CN 16). Tested 2018 P1.
- **Complex Numbers ↔ Coordinate Geometry** — `|z|` is the distance formula in disguise (page 18). The Argand plane is the coordinate plane with `Re` for `x` and `Im` for `y`.

> Complex Numbers is the most algebra-flavoured of the P2-style strands — it lives on P1 because the operations are essentially algebraic. The quadrant rules are the only part that's geometric.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| `i² = −1` rectangular multiplication | CN 2 | every year, 2015–2025 |
| Quadrant adjustment in polar form | CN 10 | 2015, 2018, 2020, 2022, 2022 DF, 2024 |
| Four-step De Moivre pipeline | CN 13 | 2016, 2017, 2018, 2020, 2022, 2023, 2024 + 3 deferreds |
| Multi-valued nth roots (add `2πk`) | CN 14 | 2015, 2019, 2021, 2023, 2025 + 2023 DF, 2024 DF, 2025 DF |
| Conjugate-pair theorem on quadratics | CN 8 | 2017, 2019, 2023, 2024 |
| Conjugate-pair on cubics (real + pair) | CN 9 | 2025 DF (full 3-step recipe) |
| De Moivre's theorem proof by induction | CN 16 | 2018 |
| Proof of `sin 3A` / `cos 3A` via De Moivre | CN 17 | 2025 |
| `p + qi` form when `p = 0` | CN 2 / CN 13 | 2022 DF, 2024 (MS deduction) |

> If you've internalised everything in this row, you've insured ~85% of the complex-numbers marks on the next paper.
