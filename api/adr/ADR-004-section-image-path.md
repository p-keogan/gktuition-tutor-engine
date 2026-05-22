# ADR-004 — §X. The image-query path

> Standalone ADR section produced by Agent 06. Agent 08 will merge this into
> the consolidated ADR-004 document.

## Context

ADR-003 (§ "Decision item 5") commits to a two-tier text-only routing
contract for `/query`. The architecture review surfaced a target query type
that the text-only contract cannot serve: students "sending a screenshot of
their homework". This section describes the preprocessing path that fills
that gap without modifying the existing text path.

## Decision

Add a new endpoint, `POST /image_query`, that accepts an image upload,
extracts the maths question via a Claude Sonnet 4 vision call, and then
forwards the extracted text into the existing `/query` internal handler.
The text path defined in ADR-003 is untouched.

The call stack for an image query is fixed at exactly:

    Sonnet 4 vision (extraction)  ->  text  ->  existing RAG pipeline

There is no local OCR fallback. There is no path in which the extracted text
skips the RAG pipeline.

## Sub-decisions

### 1. Sonnet 4, not Haiku 4.5

Haiku 4.5's vision is good enough for clean digital screenshots, but the
target use case is dominated by **handwritten homework photographed on a
phone**. On that material, Sonnet 4 makes materially fewer transcription
errors — particularly on small digits, signs (- vs +), exponents drawn close
to the base, and fraction layouts. The cost premium (Sonnet 4 is roughly
3–4× a Haiku 4.5 vision call) is rational when the alternative is a wrong
extraction silently corrupting the downstream RAG answer. An image query
that produces the wrong question is worse than an image query that fails
loudly, because the student will accept and learn from the confident but
incorrect tutor answer.

### 2. Paying-tier only

Image queries cost roughly 10–50× a text query at the wholesale level (image
input tokens dominate, then we pay again for the RAG call). At the projected
anonymous-tier volumes this would break the unit economics that ADR-003 set
up. Gating the endpoint to `tier=paying` is enforced server-side via JWT
claim; the WordPress widget should hide the upload button for non-paying
users as a UX courtesy, but the auth gate is the load-bearing line.

Free-tier users hitting the endpoint receive HTTP 403 with body
`{"error": "image queries require a paid subscription"}`, deliberately worded
to be the headline of an upsell modal on the frontend.

### 3. The extraction prompt returns JSON, not prose

The prompt at `prompts/extract_maths_question_from_image.md` instructs the
vision model to return a single JSON object. The API parses with
`json.loads` and rejects anything else as a vision error. We chose JSON over
prose for three reasons:

1. **Branching on outcome.** The endpoint has four legitimate outcomes —
   one extracted question, multiple questions, no maths, low clarity — and
   each maps to a different HTTP status and response shape. JSON lets us
   read the signal without regex-parsing English.
2. **No ambiguity at the boundary.** If the vision model wants to surface
   uncertainty ("I think this says 3x but it might be 8x"), it has a
   structured place to put it (`low_clarity`, `what_was_visible`) rather
   than embedding hedge phrases into the extracted question that the RAG
   pipeline would then take literally.
3. **Failure is parseable.** When the model goes off-script — returns
   markdown, returns prose, returns an apology — `json.loads` fails fast
   and we return 502 instead of forwarding garbage to the RAG pipeline.

### 4. Failure modes are each their own response, not a silent fallback

Each of the following is a distinct user-visible response, not a soft
recovery:

| Outcome                       | HTTP | Why surfaced explicitly                                                                                                    |
| ----------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------- |
| `no_maths_detected`           | 422  | The student photographed the wrong thing. Telling them so is faster than letting the RAG pipeline answer a non-question.   |
| `low_clarity`                 | 422  | The photo is unreadable. Telling them "retake it with better lighting" produces a usable image on attempt two.             |
| `multiple_questions_present`  | 200  | A worksheet photo. We return the parsed list and let the student pick one — silently picking the first would be wrong half the time. |
| `vision_error` (parse / API)  | 502  | The model failed us. The student gets "try again", and the row is logged so we can debug a pattern.                        |

The principle: we never silently substitute a guess. Every degraded path is
either the student's problem to fix (retake, pick one) or our problem to
fix (vision_error pattern in the logs).

### 5. €5/day kill switch — image queries count twice

ADR-003 specifies a daily Anthropic spend kill switch. Image queries hit
Anthropic **twice per request** — once for the Sonnet 4 vision extraction,
once for the RAG-pipeline LLM call. Both calls must be attributed to the
same shared spend counter that the kill switch reads from. When the switch
trips, `/image_query` returns the same kill-switch response that `/query`
returns; the auth gate runs first, so paying users get the same degraded
experience as everyone else.

This means a paying user can be cut off by anonymous-tier spend exhausting
the daily budget. That's accepted: the alternative is per-tier budgets,
which adds complexity disproportionate to the current scale.

## Consequences

**Positive.**

- The text path of `/query` is unchanged. No risk to the ADR-003 contract.
- Extraction failure modes are observable in `RAW.QUERY_LOG.extraction_outcome`
  — we can see, week over week, how often the model returns `low_clarity`
  on phone photos vs. textbook screenshots, and tune the UX (e.g. add a
  client-side flatness check) where the data points.
- The vision-extraction service is a pure function of (image, prompt). It
  can be swapped (different model, different prompt, different vendor)
  without touching the route or the RAG pipeline.

**Negative.**

- Cost-per-image-query is meaningfully higher than cost-per-text-query.
  Paid-tier pricing must absorb this; the spreadsheet from the Anchor build
  section assumes ~3% of paying-tier queries are image queries.
- A vision-extraction failure (parse error or API error) burns the
  extraction cost without producing a billable answer. Logged but not yet
  separately budgeted.
- The two-step call stack roughly doubles end-to-end latency vs. a text
  query (vision call dominates). UX needs a visible "reading your image…"
  state on the frontend.

## Out of scope

- Cost monitoring beyond logging — handled by the cost-dashboard concern.
- Frontend integration — handled by the React widget agent.
- A local-OCR fallback — explicitly rejected. Reliability is worth the cost.
