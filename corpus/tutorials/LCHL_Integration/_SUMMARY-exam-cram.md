# Integration — 90-Minute Exam Cram Summary

> **For students who already know this material.** This sheet is the triage map for your final 90 minutes on Integration before the exam. Read in 5 minutes, drill the priorities for 85.

---

## 🧭 Why Integration deserves the first 90 minutes

From the 11-year exam-trends analysis (2015–2025):

- **Integration appears in 11/11 years on Paper 1.** Total: **28 parts**. Average ≈ 2.5 parts per paper — lower-volume than Algebra or Differentiation, but **every year, without exception**.
- **Recent surge:** 2023 had 5 parts; 2025 had 5 parts; 2024 had 3 parts; 2024-deferred had 4 parts. The 2015–2022 average was ≈ 2 parts. Plan as if 2026 stays at the higher 3–5 range.
- **Section A vs B:** integration lives in **both** — basic mechanics in Section A (one-line integrals, definite integrals), and the spine of Section B average-value, kinematics, and area-between-curves questions.
- **The standalone trap:** Integration 11 (average value) is **not in the log tables.** Paul at `integration-11` [01:09]: *"it's not available in your maths table so you need to commit that to memory."* Tested 2017, 2020, 2023, 2024, 2024 DF, 2025 — six times in nine recent years.

**The takeaway.** Integration is the only "every year" P1 strand where one of the load-bearing formulas isn't given to you. That formula — `avg = (1/(b−a)) · ∫ₐᵇ f(x) dx` — is also the most-tested non-trivial integration application.

---

## 🧰 The applications of integration (Int 8–13)

If asked *"what are the applications of integration?"*, give the **full** set — not just find-`f(x)` and kinematics:

- **Finding `f(x)` from `f'(x)`** — anti-differentiate + pin `+ C` with an initial condition (Int 8)
- **Kinematics** — acceleration → velocity → position (Int 9)
- **Anti-derivatives** — differentiate-then-rearrange (Int 10)
- **Average (mean) value of a function** — `(1/(b−a))·∫ₐᵇ f(x) dx` (Int 11) — *not in the tables; memorise it*
- **Area between a curve and the x-axis** (Int 12) and **the y-axis** (Int 13)

> **Average value and area under a curve are core applications — never omit them.** Both are regularly examined (area every year; average value 6× in 9 recent years).

---

## ⏱ Suggested time split (90 min)

| Activity | Time | Why |
|---|---|---|
| Read this sheet | 5 min | Triage |
| **Definite integrals with limits + the `+ C` discipline** | 15 min | `integration-7` — **16 citations**, the most-cited integration tutorial. Tested 11/11 years. |
| **Average value — formula NOT in log tables** | 15 min | `integration-11` — 10 citations. Tested 2017, 2020, 2023, 2024, 2024 DF, 2025. |
| **Area between curve and x-axis (signed-area trap)** | 15 min | `integration-12` — 6 citations. The single biggest mark-loss point. Tested 2017, 2018, 2022, 2023, 2024, 2024 DF, 2025 DF. |
| **`∫eᵏˣ dx = (1/k)eᵏˣ` divide-by-derivative trick** | 10 min | `integration-3` — 6 citations. Tested 2017, 2020, 2023, 2024, 2025, 2025 DF. |
| **Power rule + algebraic simplification before integrating** | 10 min | `integration-1` — 10 citations. Most every-year integrals reduce to this. |
| **Kinematics: position → velocity → acceleration via integration** | 10 min | `integration-9` + `integration-8` — find `f(x)` from `f'(x)` with a boundary condition. Tested 2019, 2021, 2023, 2024 DF, 2025. |
| **Trig integration `∫sin x = −cos x` (sign discipline)** | 10 min | `integration-5` — tested 2015, 2018, 2022, 2024, 2024 DF. |

---

## 📊 Top integration tutorials by exam frequency (P1, 11 years)

| Rank | Tutorial | Citations | What it tests |
|---|---|---|---|
| 1 | `integration-7` Integration with Limits | **16** | Definite integrals — `F(b) − F(a)`; `+ C` cancels |
| 2 | `integration-1` Algebra (power rule) | **10** | `∫ xⁿ dx = xⁿ⁺¹/(n+1) + C`; simplify before integrating |
| 3 | `integration-11` Average Value | **10** | `avg = (1/(b−a)) · ∫ₐᵇ f(x) dx` — **NOT in log tables** |
| 4 | `integration-3` Exponentials | ~6 | `∫eˣ dx = eˣ + C`; divide by derivative of the power |
| 5 | `integration-12` Area between curve and x-axis | ~6 | Signed-area trap; split at interior roots |
| 6 | `integration-5` Trigonometry 1 | ~4 | `∫sin x = −cos x`, `∫cos x = sin x`; divide by derivative of angle |
| 7 | `integration-8` Finding f(x) given slope | ~4 | Pin `+ C` with an initial condition |
| 8 | `integration-9` Kinematics | ~2 | Velocity → distance via integration |

> **Read this as:** tutorials 1–4 account for ~42 cited appearances on Paper 1 across 11 years. Master the definite-integral mechanic (Int 7) and the average-value formula (Int 11) above all else.

---

## 📖 Log tables — the pages you'll actually flip to

| Page | Formula | When to use |
|---|---|---|
| **p. 26** | `∫ xⁿ dx = xⁿ⁺¹/(n+1) + C` (power rule), `∫ eˣ dx = eˣ + C`, `∫(1/x) dx = ln\|x\| + C`, `∫ sin x dx = −cos x + C`, `∫ cos x dx = sin x + C` | Every standard antiderivative. Flip here first. |
| **p. 26** | `∫ aˣ dx = aˣ/(ln a) + C` | Constant-to-power integrand (different from `∫eˣ`) |
| **p. 21** | Index laws | Simplify the integrand before integrating |
| **p. 15** | Product-to-sum identities | Trig integrals with `sin A · cos B` etc. (Int 6) |
| **p. 12** | Trapezoidal rule | Numerical estimate paired with exact integration (cross-strand AVM) |
| **(none)** | `avg = (1/(b−a)) · ∫ₐᵇ f(x) dx` | **Memorise — Paul drills this is NOT in the tables.** |

> **🎯 Most antiderivatives are on page 26.** Don't waste working memory on memorising them — *except* the average-value formula, which isn't there.

---

## 📚 Learning work — what must be in your head before you sit down

These are the items the log tables **don't** give you. Drill until they're automatic.

### 1. The average-value formula

```
                  1     ⌠ b
   Average  =  ─────── │   f(x) dx
                b − a  ⌡ a
```

> Paul at `integration-11` [01:09]: *"it's not available in your maths table so you need to commit that to memory."* The most common error: students compute the definite integral and call **that** the average. The `1/(b−a)` factor is what makes it an average, not a total. (2023 P1 Q7(d) MS explicit: *"If 1/5 is omitted, treat step 1 as not fully correct."*)

### 2. The divide-by-derivative-of-power trick

For `∫ e^(kx) dx` (where `k` is a constant):

```
   ⌠
   │  e^(kx) dx  =  (1/k) e^(kx)  +  C
   ⌡
```

Same pattern for trig: `∫ sin(kx) dx = −(1/k) cos(kx) + C`. The mechanic is the inverse of the chain rule from Diff 5. It is **load-bearing** when `k = −1` because the sign of the antiderivative flips.

### 3. `+ C` discipline — indefinite vs definite

> **Indefinite integrals: `+ C` is mandatory** (Paul reinforces this 30+ times in `integration-1` alone — it's the most common LC trap).
>
> **Definite integrals: `+ C` is gone.** `(F(b) + C) − (F(a) + C) = F(b) − F(a)` — the constants cancel. Writing `+ C` in a definite-integral answer typically costs 1 mark per occurrence.

### 4. There is NO product / quotient / chain rule for integration in LC

> Paul at `integration-1` [05:58]: *"there's no quotient rule or product rule or chain rule in integration in the Leaving Cert."*

If the integrand is a fraction with `x` in both numerator and denominator, you must **factorise and cancel** before integrating. If it's a product, you must **expand or simplify** first. There is no direct rule.

---

## 🚨 LOAD-BEARING — the five things that win or lose the integration question

### 1. The signed-area trap — split at every interior root

> Definite integration gives a **signed** quantity. Above-axis regions contribute positive; below-axis regions contribute negative. They can cancel.

Paul at `integration-12` [11:25] (delivered as a triple mantra at [08:02], [11:25], [12:06]): *"if I had integrated from 0 to 4 your answer would have ended up being 0."*

**The recipe** for area between `y = f(x)` and the x-axis between `x = a` and `x = b`:
1. **Sketch first** — mandatory. Identify where the curve crosses the x-axis between `a` and `b`.
2. **Split the integral at every interior root.** Each region gets its own integral.
3. **Take the absolute value** of each region's integral before summing.

> 🚨 This is the **single biggest mark-loss** in integration. The student integrates from `a` to `b` in one go, the positive and negative areas cancel, and the answer is zero or wildly wrong. Tested 2017, 2018, 2022, 2023, 2024, 2024 DF, 2025 DF.

### 2. The average-value formula — memorise it

> `avg = (1/(b−a)) · ∫ₐᵇ f(x) dx` — **not in the log tables**.

The two-step structure of the question is almost always:
1. Integrate `f(x)` from `a` to `b`.
2. **Divide by `(b−a)`.**

> 🚨 Paul at `integration-11` [01:09]: *"it's not available in your maths table so you need to commit that to memory."* The MS deducts marks specifically for omitting the `1/(b−a)` factor. Tested 2017, 2020, 2023 (avg speed via integration), 2024, 2024 DF, 2025.

### 3. `+ C` is mandatory for indefinite integrals; pinned by initial condition

Indefinite integrals must include `+ C`. When a question gives an initial condition (e.g. *"the curve passes through (1, 5)"*, or *"the particle has velocity 3 m/s at t = 0"*), **substitute to find `C`**, then write the full particular function.

**The applications-strand recipe** (Int 8): integrate the rate to get the function, then sub the boundary condition to pin `C`.

> 🚨 Tested every year. The two ways students lose marks: (a) forgetting `+ C` on an indefinite integral; (b) finding `C` but then forgetting to write the full pinned function. Tested 2019, 2021, 2024 DF, 2025.

### 4. Definite-integral mechanic — sub into the antiderivative, not the integrand

> `∫ₐᵇ f(x) dx = [F(x)]ₐᵇ = F(b) − F(a)`

Sub `a` and `b` into the **antiderivative** `F(x)`, not into the original `f(x)`. (Same pattern as the Diff 14/15 mark-losing trap, running in reverse.) For trig integrals with `π`-limits the calculator must be in **radian mode** — Paul at `integration-7` [04:02] flags this explicitly.

> 🚨 Tested 11/11 years — most-cited integration tutorial in the corpus (16 citations).

### 5. Simplify the integrand BEFORE you integrate

> There is no product, quotient, or chain rule in LC integration. If the integrand isn't a standard form on page 26, your first move is **algebraic simplification**.

Common simplifications:
- Split a fraction: `∫(x² + 3)/x dx = ∫(x + 3/x) dx = x²/2 + 3 ln|x| + C`.
- Expand a product: `∫(2x + 1)(x − 3) dx` → multiply out, then integrate term by term.
- Factor and cancel: `∫(x² − 9)/(x − 3) dx = ∫(x + 3) dx`.

> 🚨 Paul at `integration-1` [05:58]: *"there's no quotient rule or product rule or chain rule in integration in the Leaving Cert."* If the integrand looks complicated, simplify first. Tested every year.

---

## 🎯 The 8 techniques you must execute without thinking

1. **Power rule for integration**: `∫ xⁿ dx = xⁿ⁺¹/(n+1) + C` for `n ≠ −1`. Add one to the power; divide by the new power.
2. **The `n = −1` edge case**: `∫ (1/x) dx = ln|x| + C`. Not a power-rule result — a separate antiderivative.
3. **Exponential with linear inside**: `∫ e^(kx) dx = (1/k) e^(kx) + C`. The "divide by the derivative of the power" trick. (Int 3.)
4. **`∫ aˣ dx = aˣ/(ln a) + C`** for constant base `a ≠ e`. Different formula from `∫eˣ`. Page 26.
5. **Trig integration with linear inside**: `∫ sin(kx) dx = −(1/k) cos(kx) + C`; `∫ cos(kx) dx = (1/k) sin(kx) + C`. Same divide-by-derivative trick. (Int 5.)
6. **Product-to-sum before trig integration**: when integrating `sin A · cos B` etc., use the page-15 product-to-sum identities to convert to single-term sines/cosines first. (Int 6.)
7. **Definite-integral evaluation**: write the antiderivative in square brackets with the limits, then evaluate at upper minus lower. `[F(x)]ₐᵇ = F(b) − F(a)`. (Int 7.)
8. **Find f(x) from f'(x) + initial condition**: integrate, get `f(x) + C`, sub the initial point, solve for `C`. (Int 8.)

---

## ⚠ Common traps — where students lose marks

| Trap | Fix |
|---|---|
| Forgetting `+ C` on an indefinite integral | Always add `+ C`. Paul drills 30+ times in Int 1. |
| Writing `+ C` on a definite integral | The `C`s cancel: `(F(b) + C) − (F(a) + C) = F(b) − F(a)`. |
| Integrating across an interior root without splitting (signed-area trap) | Sketch first. Split at every crossing. Take absolute values. Sum. |
| Average-value answer = the integral (forgot to divide by `b − a`) | The `1/(b−a)` factor is mandatory. (2023 P1 Q7(d) MS: *"if 1/5 is omitted, treat step 1 as not fully correct."*) |
| Substituting limits into `f(x)` instead of `F(x)` | Sub into the **antiderivative**, not the integrand |
| Calculator in degrees for trig integrals with `π`-limits | Switch to **radians**. Paul flags at Int 7 [04:02]. |
| Wrong sign on `∫ sin x = +cos x` (should be `−cos x`) | `d/dx[cos x] = −sin x`, so reversing it: `∫ sin x dx = −cos x + C` |
| Forgetting the `(1/k)` on `∫ e^(kx) dx` | Divide by the derivative of the linear-in-x in the exponent. `k = −1` flips the sign. |
| Trying a quotient/product/chain rule on the integrand | There is no such rule. Factorise / expand / cancel first. |
| Wrong page-26 row: using `∫aˣ = aˣ/(ln a)` for `∫eˣ` | `∫eˣ = eˣ + C` — `ln e = 1` so the formulas agree; but don't write `ln e` in the denominator |
| Area answer left as a negative number | Area is positive. Take absolute value of any below-axis region. |
| Computing area between two curves with `∫(top − bottom)` when one is below the x-axis | When the curves are on opposite sides of the x-axis, compute each enclosed region separately and sum magnitudes. (Int 12 Q4.) |

---

## 📋 Question-type triage — reading the question wording

| Phrase | Strategy |
|---|---|
| *"Find the integral"* (no limits) | Indefinite — add `+ C` |
| *"Evaluate"* with `∫ₐᵇ` | Definite — `F(b) − F(a)`, no `+ C` |
| *"Find the average value of f over …"* | Int 11 formula — `(1/(b−a)) · ∫ₐᵇ f(x) dx`. Not in the tables. |
| *"Find the area enclosed between …"* | Sketch first. Split at roots. Sum magnitudes. |
| *"Show that the area is …"* | Method marks heavy — show every step including the sketch |
| *"Find f(x) given that f'(x) = … and f(a) = b"* | Int 8 recipe — integrate, sub the point, solve for `C` |
| *"Find the distance travelled / displacement …"* | Int 9 — `displacement = ∫ v(t) dt`. **Sign convention:** displacement can be negative; distance is the absolute total. |
| *"Average speed over the interval"* on P1 | Int 11 — same average-value formula applied to `v(t)`. **(Not the same as the P2 statistical mean.)** |
| *"Find the average"* on P2 | Statistical mean — sum / count. Paul at Int 11 [03:27] explicit. |
| *"Hence find …"* | Use a prior part's antiderivative — don't re-derive |

---

## 💡 Three exam-day tips that move the needle

1. **Sketch every area-under-the-curve question, no exceptions.** Without a sketch you cannot see whether the curve dips below the x-axis between your limits — and that is the single biggest mark-loss in integration. Paul drills this triple-mantra style in Int 12 [08:02], [11:25], [12:06] — when he repeats himself three times, it's exam-critical.

2. **The average-value formula is the one you must memorise.** Page 26 has every standard antiderivative; it does **not** have `avg = (1/(b−a)) · ∫ₐᵇ f(x) dx`. Write it from memory on the cover of your answer book as soon as the exam starts, before anything else.

3. **Indefinite ⇒ `+ C`; definite ⇒ no `+ C`.** Indefinite vs definite is the first thing to identify in every integration question. Indefinite always gets `+ C`. Definite never does. This binary choice catches 1–2 marks per paper on average.

---

## 🔗 Cross-strand connections (where else integration fires)

- **Integration ↔ Differentiation** — integration is anti-differentiation. Diff 14 (slope from `f'(x)`) inverts to Int 8 (`f(x)` from slope). Diff 18 (rates) inverts to Int 9 (kinematics).
- **Integration ↔ Algebra** — almost every integration question requires algebraic simplification of the integrand first (split fractions, expand brackets, factor and cancel). Paul's "no product / quotient / chain rule" forces the algebraic move.
- **Integration ↔ Indices and Logs** — `∫(1/x) dx = ln|x| + C` and `∫ eˣ dx = eˣ + C` make logs and exponentials integration-native. The 2017 P1 Q7 average-of-an-exponential-population is a canonical compound example.
- **Integration ↔ Trigonometry (§1.7, §2/3/4)** — `∫sin(kx) dx`, `∫cos(kx) dx`, and product-to-sum identities (Int 6 uses page 15).
- **Integration ↔ AVM (§6, §7)** — `avm-1-6` and `avm-1-7` are cross-references to Int 12 and Int 13. Area between a curve and an axis is canonically integration on the syllabus, listed under AVM on the GKTuition course.
- **Integration ↔ AVM Trapezoidal Rule** — Paul at `integration-12` [04:35]: *"it's probably worth your while going to the section on area and volume and watching the video on trapezoidal rule after you've watched this one."* The canonical 2015 P1 Q3 pattern: trapezoidal estimate + integration check + percentage error.
- **Integration ↔ Sequences & Series** — Section B Q7/Q8/Q9 in 2017, 2020, 2023, 2024 wraps an exponential population growth model around an integration step (average value) and a differentiation step (rate of change).

---

## 📅 Tested-year quick reference (per load-bearing rule)

| Load-bearing rule | Tutorial | Years tested on LCHL |
|---|---|---|
| Definite integral `[F(x)]ₐᵇ = F(b) − F(a)` | `integration-7` | 2015, 2016, 2017, 2018, 2020, 2022, 2023, 2024, 2024 DF, 2025, 2025 DF |
| Average-value formula (NOT in log tables) | `integration-11` | 2017, 2020, 2023, 2024, 2024 DF, 2025 |
| Area between curve and x-axis — split at roots | `integration-12` | 2017, 2018, 2022, 2023, 2024, 2024 DF, 2025 DF |
| Power-rule integration + algebraic simplification | `integration-1` | 2015, 2018, 2019, 2021, 2022, 2023, 2024 DF, 2025, 2025 DF |
| `∫ e^(kx) dx = (1/k) e^(kx)` (divide by derivative) | `integration-3` | 2017, 2020, 2023, 2024, 2025, 2025 DF |
| Trig integration `∫sin x = −cos x`, sign discipline | `integration-5` | 2015, 2018, 2022, 2024, 2024 DF |
| `f(x)` from `f'(x)` + initial condition | `integration-8` | 2019, 2021, 2024 DF |
| Kinematics — distance via `∫v(t) dt` | `integration-9` | 2025 |
| `∫aˣ dx = aˣ/(ln a)` (constant-to-power) | `integration-4` | 2022, 2022 DF, 2024 |

> If you've internalised the top four rows, you've insured most of the integration marks on the next paper.
