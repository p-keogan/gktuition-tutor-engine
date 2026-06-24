# Answer-Quality Backlog — for weekly testing review

Issues found during staging testing where the tutor's answer is *not wrong* but
is below the standard Paul would teach. These are retrieval-breadth / synthesis-
prompt tuning items (NOT widget bugs — the 2-citation display cap does not limit
what the model reads).

## 1. "Applications of differentiation" — answer too thin (2026-06-24)
**Query:** "What are the applications of differentiation?"
**Got:** rates of change, optimisation, curve sketching (general, brief).
**Should cover:** slope / slope of a tangent; turning points; points of
inflection; increasing & decreasing curves; displacement → velocity →
acceleration; angle a line makes with the horizontal — i.e. the full LCHL list
Paul teaches, not a 3-item summary.
**Likely cause:** retrieval pulled only differentiation-18 / differentiation-20;
synthesis didn't enumerate. **Fix to trial:** broaden retrieval for
"applications/uses of X" queries and/or adjust the synthesis prompt to favour an
enumerated, comprehensive answer for this query shape.

## 2. "How do I prove a function is bijective?" — gives Plan B, not the method Paul teaches (2026-06-24)
**Query:** "how do i prove a function is bijective?"
**Got:** prove injective (horizontal-line test) AND surjective (every codomain
element is mapped). Correct, but it's the fallback method.
**Should lead with:** prove the **inverse of the function is itself a function**
(the approach in *Functions and Graphs 8 — Inverse Functions*); injective-AND-
surjective is the secondary/Plan-B route.
**Likely cause:** retrieval ranked functions-graphs-7 (bijective) above
functions-graphs-8 (inverse); synthesis followed the top chunk. **Fix to trial:**
ensure the inverse-is-a-function framing is surfaced first for "prove bijective"
queries (voice-anchor / slug-anchor or synthesis-prompt guidance).

## 3. ⭐ HIGH PRIORITY — "Bayes' rule" must become "conditional probability" everywhere (2026-06-24)
**Paul's instruction:** the tutor must NEVER say "Bayes' rule" / "Bayes' formula" /
"Bayes-style" — LCHL teaches this as **conditional probability**. Clean the
source corpus, then reload + re-embed so it never surfaces in answers.
**Scope:** 15 mentions across 7 files (`grep -ri bayes career-transition-2026/tutorials`):
- `LCHL_Maths_Exams/Solutions/2024_P2_solutions.md` (lines ~1230, 1417, 1479, 1481, 2734) — Q7(c)
- `LCHL_Maths_Exams/Solutions/2017_P2_solutions.md` (~1933 "apply Bayes' formula", ~1952 "Bayesian updating")
- `LCHL_Maths_Exams/Solutions/2025_P2_solutions.md` (~1964, 2032, 2726 "Bayes-style")
- `LCHL_Probability/probability-3-independent-events-conditional-probability.md` (~107)
**Watch out:** `2015_P2_solutions.md:280` mentions a "Bayesian/frequentist distinction"
in **confidence-interval interpretation** — that's a *different* concept; reword,
don't blind-swap to "conditional probability".
**After editing:** re-run `load_exam_parts.py` (+ `load_tutorials.py` for the
probability-3 file), then refresh `SOLUTIONS_SEARCH` / `TUTOR_SEARCH` so the
embeddings pick up the new wording.

## 4. Solution-lookup over-hedges ("I don't have the full text") (2026-06-24)
**Query:** "I'm stuck on 2024 P2 Q7(c)"
**Got:** a correct, complete worked solution — but prefaced with "I don't have
the full text of the question." The data is actually present (question_text=121
chars + solution_text=2,176 chars), so this is the model being over-cautious.
**Fix to trial:** synthesis-prompt tweak — when retrieval is an exact paper-match
(solution_lookup, confident score), instruct the model to present the official
worked solution directly and NOT add a "missing question" disclaimer.

## 5. ⭐ Retrieval miss on a multi-concept exam question (2026-06-24)
**Query (via photo upload, 2026 P1):** integrate g''(x)=30x−18, slope −2 at (−1,8),
find g'(x) then g(x).
**Got:** "evidence doesn't contain integration material" — retrieved circle-tangent
+ differentiation tutorials and declined (safe, but unhelpful).
**Should retrieve:** *Integration 1 — Algebra* (power rule + C) and *Integration 8
— Finding f(x) When Given the Slope* (pin C with an initial condition). Both exist
and are ideal.
**Cause:** surface terms (tangent/slope/point/curve/derivative) dominate the
embedding over the core "integration" task, so integration tutorials rank below
circle/diff ones.
**Fix to trial (headline retrieval item):** enable **query rewrite** —
`QUERY_REWRITE_ENABLED` and especially `QUERY_REWRITE_FALLBACK_ENABLED` (fallback
only fires on a low-score miss, so it can't regress already-good answers). Both
are off in fly.toml pending the eval gate. Run the eval, confirm net lift, then
flip. Also verify the rewrite LLM client is wired at startup.
**Good test cases for the pass:** this integration question; "applications of
differentiation"; "prove bijective".

## 6. ⭐ Photo/exam-question retrieval miss #2 — indices (2026-06-24)
**Query (photo, 2025 P1 Q5(a) + caption "help me with the first part"):** "Write
each of the following numbers in the form 4^r, where r ∈ Q. Numbers: 64, 1/16, 2."
**Got:** guardrail ("I'm not sure"), surfacing Sequences & Series 8 and Number
Theory 2.
**Should retrieve:** *Indices and Logs 1* (or 2) — 64 = 4³, 1/16 = 4⁻², 2 = 4^½.
**Cause:** same class as #5 — long `IMAGE_EXTRACTED` question; plain semantic
search on the full text is dominated by surface words ("numbers/form/∈ Q") and
misses the indices topic; score < floor → guardrail.
**Important finding:** the existing **query-rewrite fallback does NOT help here.**
`_should_rewrite_fallback` returns False unless `query_class == CONCEPT` and the
query is a short (≤6-token) bare-noun fragment with no domain symbols. Long
image-extracted exam questions are excluded by design. So enabling
`QUERY_REWRITE_FALLBACK_ENABLED` is a no-op for these.
**Real fix (headline build for the tuning pass):** add a **topic-extraction
retrieval step for IMAGE_EXTRACTED (and long) queries** — distil "what concept/
method is this testing?" (short phrase) and retrieve on that, before the
TUTOR_SEARCH call, rather than embedding the whole question. Validate with the
eval harness so it doesn't regress currently-good answers. Test cases: this
indices question (#6) and the integration question (#5).

---
_Add new findings above this line with date, query, got vs. should, and a fix to trial._
