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

---
_Add new findings above this line with date, query, got vs. should, and a fix to trial._
