# Trigonometry 2 (Unit Circle) — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on the Unit Circle strand before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Trig 2 deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025):

- **Trig 2 is a P2 strand** — 11 P2 main-sitting parts across 8 of 11 years (2015, 2018, 2019, 2020, 2021, 2023, 2024, 2025). Average ≈ 1 part per P2 paper; concentrated when it appears (3 parts in 2023, 2 in 2021).
- **The bigger story is cross-strand on P1.** Trig 2 contributes **7 P1 parts** as well — `d/dx[sin 2x]`, `∫ cos 3x dx`, definite integrals with `π`-limits all depend on knowing the unit circle. Tested 2015, 2017, 2020, 2022 on P1.
- **Counting both papers + deferred sittings, the unit-circle technique was tested in 15 of the 30 LCHL papers** in the dataset — including 2024 P2 and 2025 P2/DF. There is no year since 2015 that didn't touch it somewhere.
- **The most-cited Trig 2 tutorial is `trigonometry-2-4`** (more than two answers / multi-revolution domains) — **11 citations** across 11 years. It's the engine of every `sin A = k` and `cos A = k` question that asks for more than one answer.

**The takeaway.** Trig 2 isn't a heavy-weight Section B strand on its own, but the unit-circle routine is required infrastructure for every trig integral, every trig derivative, and every `sin 2x = k` / `cos 3x = k` equation. Marks here are reliably 5–10 per paper between both papers.

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Reference angle + CAST + quadrant formulas (the core routine)** | 20 min | `trigonometry-2-2` — the engine the rest of the strand inherits from |
| **Multi-revolution domains (`[0, 720°]`, `[0, 1080°]`, etc.)** | 15 min | `trigonometry-2-4` — 11 citations, tested almost every year |
| **Coefficient-in-front-of-the-angle scaling (`sin 2A`, `cos 3A`)** | 15 min | `trigonometry-2-5` — 7 citations, the scale-the-domain rule |
| **Calculator inverse for non-special angles + `cos² A = k`** | 10 min | `trigonometry-2-9` — 4 citations, the precision-rounding trap |
| **Radian-domain re-skin (`0 ≤ A ≤ 2π`)** | 10 min | `trigonometry-2-3` — 4 citations, calculator-mode trap |
| **Edge cases (`sin A = 0/±1`, `cos A = 0/±1`)** | 5 min | `trigonometry-2-7` — the off-axis routine breaks; read off the four axis points |
| **Degrees ↔ radians ↔ DMS conversion** | 5 min | `trigonometry-2-8` — rare standalone, but blocks downstream |
| **Quick-fire:** the unit-circle definition `(x, y) = (cos A, sin A)`, ASTC mnemonic | 5 min | `trigonometry-2-1` — the foundational identification |

---

## 📊 Top Trig 2 tutorials by exam frequency

| Rank | Tutorial | Citations | What it tests |
|---|---|---|---|
| 1 | `trigonometry-2-4` More Than Two Answers | **11** | Multi-revolution domains; "domain width ÷ 360° = number of revolutions" |
| 2 | `trigonometry-2-5` Coefficient in front of angle | **7** | `sin nA = k`: scale the domain by `n` first, divide answers by `n` at the end |
| 3 | `trigonometry-2-3` Radians and the Unit Circle | **4** | `0 ≤ A ≤ 2π` domain notation; radian-mode calculator |
| 4 | `trigonometry-2-9` Calculator reference angle | **4** | `sin⁻¹` / `cos⁻¹` / `tan⁻¹` when not a special angle; `cos² A = k` ⇒ ± |
| 5 | `trigonometry-2-2` Intro to Unit Circle | **2** | Reference angle + ASTC + quadrant formulas |
| 6 | `trigonometry-2-1` Deriving the Unit Circle | 1 | The `(x, y) = (cos A, sin A)` identification |
| 7 | `trigonometry-2-8` Degrees / Radians / DMS | 1 | The two-identity calculus + base-60 arithmetic |
| 8 | `trigonometry-2-6` / `2-7` | 0 each | General solution `+ 360n`; edge cases (rare standalone) |

> **Read this as:** the two tutorials that compound across every other strand are `2-4` (more than two answers) and `2-5` (coefficient scaling). If you can run those two procedures cold, the rest of the strand follows.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | What's there | When to use |
|---|---|---|
| **p. 13** | Unit circle diagram with `(cos A, sin A)` labelled; special-angle table (`sin/cos/tan` of 0°, 30°, 45°, 60°, 90°, …) in **degrees AND radians** | Read off reference angles for special values; check radian equivalents |
| **p. 13** | The four axis-intersection points: `(1, 0)`, `(0, 1)`, `(−1, 0)`, `(0, −1)` | Edge cases `sin A = 0/±1` and `cos A = 0/±1` |
| **p. 9** | `Arc length = rθ`, `Sector area = ½r²θ` | Sector questions where θ is in **radians** (most cross-strand fires) |
| (mental) | **ASTC / CAST diagram** — not in tables | Sign of `sin`, `cos`, `tan` per quadrant — must memorise |
| (mental) | **The four quadrant formulas** — not in tables | `Q1: ref`, `Q2: 180 − ref`, `Q3: 180 + ref`, `Q4: 360 − ref` (and radian counterparts with `π`, `2π`) |

> **🎯 The CAST diagram and the four quadrant formulas are NOT printed.** You must commit them to memory. Everything else can be flipped to.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. The CAST mnemonic — which functions are positive in which quadrant

```
       Q2: Sin             Q1: All
            S                 A
        ─────────┼─────────
            T                 C
       Q3: Tan             Q4: Cos
```

> Reading `C-A-S-T` anticlockwise starting from Q4. The letter in each quadrant identifies which function is *positive* there (`A` = all three). Paul at `trigonometry-2-1` [11:06]: *"there's only four letters. So it's easy enough to remember anyway, and you're going to use it so much that you'll get used to it."*

### 2. The four quadrant formulas

| Quadrant | Degrees | Radians |
|---|---|---|
| Q1 | `0 + ref` | `0 + ref` |
| Q2 | `180° − ref` | `π − ref` |
| Q3 | `180° + ref` | `π + ref` |
| Q4 | `360° − ref` | `2π − ref` |

> Used to convert a reference angle (always positive, between 0° and 90°) into the actual angle in the right quadrant. These four formulas are memorised once and reused for every unit-circle equation in the strand.

### 3. The unit-circle identification `(x, y) = (cos A, sin A)`

> For any point on the unit circle, the coordinates *are* `(cos A, sin A)`. Page 13 shows the diagram with this labelling. From this single identification, the four-quadrant signs follow directly from the signs of `x` and `y`.

### 4. The reference angle is ALWAYS positive — drop the sign before taking the calculator inverse

> Paul at `trigonometry-2-2` [05:50]: *"If you're looking for your reference angle using your calculator you ignore the minus."*

If the equation is `sin A = −√3/2`, the *reference angle* is `sin⁻¹(√3/2) = 60°`. The minus sign tells you which **quadrants** to use (Q3 and Q4 for sin negative), not what the reference angle is.

---

## 🚨 LOAD-BEARING — the five things that win or lose the unit-circle question

### 1. The standard routine — reference angle + sign-of-RHS picks quadrants + per-quadrant formula

> Two independent decisions:
> - **Sign of the given ratio** ⇒ which two quadrants (via CAST).
> - **Magnitude of the given ratio** ⇒ the reference angle.
>
> Then apply the per-quadrant formula in each of the two quadrants.

| Given | Sign | Quadrants (via CAST) | Formulas |
|---|---|---|---|
| `sin A = k > 0` | + | Q1, Q2 | `ref`, `180° − ref` |
| `sin A = k < 0` | − | Q3, Q4 | `180° + ref`, `360° − ref` |
| `cos A = k > 0` | + | Q1, Q4 | `ref`, `360° − ref` |
| `cos A = k < 0` | − | Q2, Q3 | `180° − ref`, `180° + ref` |
| `tan A = k > 0` | + | Q1, Q3 | `ref`, `180° + ref` |
| `tan A = k < 0` | − | Q2, Q4 | `180° − ref`, `360° − ref` |

> 🚨 Two independent decisions — students confuse them. The sign picks quadrants; the magnitude gives the reference angle. Tested every year on P2 and most years on P1.

### 2. Multi-revolution domains — domain width tells you how many answers

> If the original `[0, 360°]` domain gives 2 answers, then `[0, 720°]` gives 4, `[0, 1080°]` gives 6. The shortcut: **find the first-revolution answers, then keep adding 360°** until you exceed the upper bound.

Paul at `trigonometry-2-4` [04:29] flags the add-360° shortcut. **Critical edge case** — if the domain is not a whole number of revolutions (e.g. `[0, 900°]` = 2.5 revolutions), some candidate answers will *exceed* the upper bound and must be **dropped**. Q1(iii) of the tutorial: domain `[0, 900°]` gives **five** answers, not six.

> 🚨 Tested 2015 P1+P2, 2017 P1, 2018 P2, 2020 P2, 2021 P2, 2022 DF P2, 2022 P1, 2023 P2, 2025 P2/DF — the most-cited Trig 2 tutorial.

### 3. Coefficient-in-front-of-the-angle — scale the domain FIRST

> For `sin(nA) = k` on `0 ≤ A ≤ D`: **scale the domain by `n`**, work in the scaled domain `0 ≤ nA ≤ nD`, find all values of `nA` using the standard routine, then **divide by `n` at the very last line**.

Paul at `trigonometry-2-5` [00:28]: *"if there's a coefficient in front of the a, the very first thing that you should do is change your domain."*

For example, `sin 2A = 1/2` on `[0°, 360°]` ⇒ scale to `[0°, 720°]` for `2A` ⇒ four answers for `2A` ⇒ divide each by 2 ⇒ four answers for `A` in the original domain. (For `sin(A/3) = k`, divide the domain by 3 and multiply answers by 3 — same idea with the reciprocal.)

> 🚨 Forgetting to scale the domain misses 50% of answers for `n = 2`, 67% for `n = 3`. Tested 2015 P2, 2017 P1, 2018 P2, 2020 P2, 2021 P2, 2024 P2, 2025 DF P2.

### 4. Calculator-mode trap — DEG vs RAD

> If the domain is `0 ≤ A ≤ 360°`, calculator in **DEG** mode. If the domain is `0 ≤ A ≤ 2π`, calculator in **RAD** mode.

Paul at `trigonometry-2-3` [03:30]: *"you can get cos inverse of a half, but only if your calculator is in radians, if there's a little R on the top of your calculator."* The same `sin⁻¹(1/2)` returns `30` in DEG mode and `0.524…` (= π/6) in RAD mode — same maths, different unit, **no error message**.

> 🚨 The domain notation IS the unit signal. `0 ≤ A ≤ 2π` means radian answers; `0 ≤ A ≤ 360°` means degree answers. Tested in every radian-domain question (2024 DF P2, 2025 DF P2 explicit).

### 5. Precision rule — don't round the reference angle mid-solve when there's a coefficient

> Paul at `trigonometry-2-9` [06:25]: *"because there's a coefficient in front of the A and my answer needs to be to the nearest degree you cannot round this one to the nearest degree now. We have to wait."*

When `tan 3A = √2`, `tan⁻¹(√2) ≈ 54.7356°`. **Write `54.7°`, not `55°`**, and propagate through the quadrant additions and revolutions. The eventual divide-by-3 compounds rounding errors into wrong final answers.

> 🚨 Tested implicitly every time a coefficient meets a calculator-inverse reference angle. 2024 P2, 2025 P2 explicit examples.

---

## 🎯 The 7 techniques you must execute without thinking

1. **Read the reference angle off page 13** when the RHS is a special value (`1/2`, `√3/2`, `1/√2`, `1`, `√3`). The page lists `sin`, `cos`, `tan` at 0°, 30°, 45°, 60°, 90°, … and their radian equivalents.
2. **Use the calculator** `sin⁻¹` / `cos⁻¹` / `tan⁻¹` when the RHS is not a special value. Drop the sign first; result is the reference angle.
3. **ASTC + sign of RHS** ⇒ which two quadrants. Apply the four per-quadrant formulas.
4. **Multi-revolution domain** ⇒ find the first-revolution answers, then add 360° (or 2π) until you exceed the upper bound. Drop any that overshoot.
5. **Coefficient on the angle** (`sin nA = k`) ⇒ scale the domain by `n` *first*; work in the scaled domain; divide answers by `n` *last*.
6. **Edge case `sin/cos = 0, ±1`** ⇒ skip CAST entirely; read the answers off the four axis-intersection points of the unit circle (page 13 diagram). Endpoint inclusion matters: `0 ≤ A ≤ 360°` for `sin A = 0` gives **three** answers (0°, 180°, 360°), not two.
7. **`cos² A = k` or `sin² A = k`** ⇒ take the square root with `±`. Both signs fire ⇒ all four quadrants ⇒ expect 4 answers in `[0°, 360°]`.

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Reference angle taken with the negative sign | Always strip the sign before `sin⁻¹` / `cos⁻¹` / `tan⁻¹`. The reference angle is always between 0° and 90°. |
| Forgetting to scale the domain when there's a coefficient (`sin 2A = k`) | Scale FIRST, divide at the END. Otherwise you miss half the answers. |
| Solving in degrees when domain is in radians (or vice versa) | The domain notation `[0, 2π]` vs `[0, 360°]` IS the unit signal. Match calculator mode to the domain. |
| Counting answers as `2 × revolutions` when domain isn't a whole number of revolutions | Some candidates exceed the upper bound. Drop them. (`[0, 900°]` = 5 answers, not 6.) |
| `sin² A = k` solved as `sin A = +√k` only | The `±` is mandatory. Both signs ⇒ all four quadrants ⇒ 4 answers. |
| Rounding the reference angle to the nearest degree mid-solve with a coefficient | Keep one extra decimal place through the quadrant + revolution arithmetic. Round only on the final line. |
| Using CAST routine for `sin A = 0`, `cos A = ±1`, etc. | The reference angle is 0° or 90° (a boundary) — read off the axis-intersection points instead. |
| Treating `0 ≤ A ≤ 360°` as exclusive on either end | Inclusive on both. `sin A = 0` on this domain has **three** answers: 0°, 180°, 360°. |
| Forgetting the per-quadrant formula for Q4 (`360° − ref`, not `360° + ref`) | Re-derive on the page from a unit-circle sketch if you blank — drop a vertical from the Q4 angle and read off the geometry |
| Confusing the unit-circle angle convention (anticlockwise from positive x-axis) | All angles are measured anticlockwise from the positive x-axis. Q1 is upper-right; Q2 upper-left; Q3 lower-left; Q4 lower-right. |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Solve for A ∈ [0°, 360°]"* | Standard one-revolution routine: reference angle + ASTC + two quadrant formulas |
| *"Solve for A ∈ [0, 2π]"* | Same routine in radians. Calculator in RAD mode. |
| *"Solve for A ∈ [0°, 720°]"* (or 1080°, etc.) | Multi-revolution — add 360° per extra revolution |
| *"sin 2A = …"* or *"cos 3A = …"* | Scale the domain by the coefficient first |
| *"sin² A = …"* or *"cos² A = …"* | Square-root with ± ⇒ all four quadrants ⇒ four answers |
| *"to the nearest degree"* with a coefficient | Keep one extra decimal place through working; round only at the end |
| *"correct to two decimal places"* on a radian answer | Calculator in RAD mode; round only on the final line |
| *"Express in degrees, minutes, seconds"* | Trig 2.8 — base-60 conversion routine |
| *"General solution"* (no domain) | Trig 2.6 — answer as `θ = ref + 360n` (or `π + 2πn`, etc.) for integer `n` |
| *"sin A = 0"* / *"cos A = 1"* | Edge case — read off the axis-intersection points; count endpoints carefully |

---

## 💡 Three exam-day tips that move the needle

1. **Domain notation IS the unit signal — set the calculator mode before you write anything.** A `[0, 2π]` domain is the universal radian flag; `[0, 360°]` is the degree flag. The exam answer must be in the same unit as the domain. Getting this wrong gives a numerically plausible but wrong-unit answer with no calculator warning.

2. **For multi-revolution / coefficient questions, write the scaled domain on the page before solving.** "Domain for `2A` is `[0°, 720°]`" written explicitly at the top of your working forces the discipline of finding *all* answers in the scaled domain before dividing by 2 at the end. Skipping this written step is the most common way 4-answer questions become 2-answer questions.

3. **Drop the sign, look up the reference angle, THEN handle the sign via CAST.** Two independent decisions in this order. Students who try to do both at once (e.g. compute `sin⁻¹(−1/2) = −30°` on the calculator and try to work with that) end up with negative reference angles that don't map onto any of the quadrant formulas.

---

## 🔗 Cross-strand connections (where else unit-circle fires)

- **Trig 2 ↔ Differentiation** — `d/dx[sin nx] = n cos nx`, `d/dx[cos nx] = −n sin nx`. The cross-strand fire that explains 7 P1 Trig 2 citations (2015, 2017, 2020, 2022 P1).
- **Trig 2 ↔ Integration** — `∫ sin x dx = −cos x + C`; `∫ cos(kx) dx = (1/k) sin(kx) + C`. Definite integrals with `π`-limits *require* radian-mode + unit-circle special-angle values.
- **Trig 2 ↔ Trig 3 (identities)** — every identity proof or simplification rests on `cos² + sin² = 1` plus quadrant-sign awareness from CAST.
- **Trig 2 ↔ Trig 4 (compound angles)** — `sin(A + B)` / `cos(A + B)` / `tan(2A)` etc. produce equations like `sin 2A = k` that route back through Trig 2.5.
- **Trig 2 ↔ Trig 1 (sine rule / cosine rule)** — the sine rule produces `sin A = …` where the answer can be obtuse (Q2) as well as acute (Q1). Two possible triangles per angle — same routine.
- **Trig 2 ↔ Complex Numbers** — polar form `r(cos θ + i sin θ)` and De Moivre's Theorem rely on the unit-circle identification. Page 19/20 references.
- **Trig 2 ↔ The Circle (P2)** — angles measured from a centre; sector questions use `s = rθ` with radian θ from Trig 2.3.

> The unit-circle routine is required infrastructure for half the P2 paper and several P1 questions. Even when the question isn't labelled "Trig 2", the last step often is.

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Multi-revolution domain (`[0, 720°]`, `[0, 1080°]`, etc.) | `trigonometry-2-4` | 2015 P1+P2, 2017 P1, 2018 P2, 2020 P2, 2021 P2, 2022 P1, 2022 DF P2, 2023 P2, 2025 P2, 2025 DF P2 |
| Coefficient-in-front-of-angle (scale domain by `n`) | `trigonometry-2-5` | 2015 P2, 2017 P1, 2018 P2, 2020 P2, 2021 P2, 2024 P2, 2025 DF P2 |
| Reference angle + CAST + quadrant formulas | `trigonometry-2-2` | 2023 P2, 2024 DF P2 (explicit citations); implicit foundation for all of the above |
| Radian-domain re-skin / calculator RAD mode | `trigonometry-2-3` | 2015 P1, 2017 P1, 2022 P1, 2024 DF P2 |
| Calculator inverse for non-special angle + `cos² A = k` ± | `trigonometry-2-9` | 2017 P1, 2020 P2, 2022 P1, 2025 P2 |
| Unit-circle derivation `(x, y) = (cos A, sin A)` | `trigonometry-2-1` | 2020 P1 (foundation for many others) |
| Degrees / Radians / DMS conversion | `trigonometry-2-8` | 2019 P2 |

> If you've internalised the top three rows, you've insured most of the unit-circle marks on the next paper — *and* the prerequisite for every trig integral and trig derivative on Paper 1.
