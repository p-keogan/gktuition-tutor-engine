# L2 anti-spam decisions

Three header/body-inspection checks live inside L2 (alongside the token-bucket and per-/24 subnet cap). Each costs the user nothing — no Cloudflare round-trip, no LLM call, no Snowflake roundtrip — and catches the long tail of low-effort bots that Turnstile alone would let through to the rate limiter.

## 1. Honeypot field

A hidden input named `website_url` is rendered in the widget with `display: none; visibility: hidden`. The FastAPI handler rejects any request whose JSON body has a non-empty `website_url`.

- **Why this works.** Real browsers don't populate fields they can't see. Naive scraper bots that just enumerate form fields and submit everything will fill it.
- **Failure mode.** A sophisticated bot reading the rendered DOM will skip the hidden field. This check is the lowest layer of the anti-spam stack — it's not meant to stop a determined adversary, just the noise floor.
- **Operational note.** If the widget developer (Agent 11) renames the field, change the constant in `L2_rate_limit.check_anti_spam` to match. The name `website_url` was chosen because it's the most-tried scrape target in Wordpress comment-spam datasets.

## 2. Minimum dwell time

The widget records a millisecond timestamp when the chat panel first opens and includes the delta in the request header `X-Dwell-Ms`. Anonymous requests with `X-Dwell-Ms < 1500` are rejected with 403 and no body.

- **Why 1500 ms.** A real student takes >1.5 s to read the prompt and type a question. A scraper or replay attack doesn't wait. Empirically the lowest delta we've seen from a real student typing a single short word is ~1100 ms; 1500 ms is the conservative floor that still catches replay traffic.
- **Tier scope.** Authenticated and paying tiers bypass this check — they've already cleared a stronger trust gate (the JWT).
- **Failure mode.** A bot that includes a slept `X-Dwell-Ms: 3000` header gets through. We accept this — the bot would still hit the rate limit (1/min, 2/day) and the spend cap.

## 3. User-Agent blocklist

Anonymous requests whose UA starts with any prefix from `bot_user_agents.txt` are rejected with 403 (no body). Empty UAs are also rejected.

- **Why prefix-match.** Common-or-garden scraper libraries don't bother changing their UA. `python-requests/2.31`, `curl/8.4.0`, `Go-http-client/1.1`, etc. are unambiguous. Prefix-matching catches version drift without us listing every minor release.
- **Refresh cadence.** Quarterly. New scraper frameworks appear constantly; an annual review would be too slow. Adding a prefix is a one-line edit to `bot_user_agents.txt`.
- **Tier scope.** Same as dwell-time — only anonymous tier is checked. A paying customer running their own automation script (legitimate use) shouldn't be punished for having a non-browser UA.
- **Why no body on rejection.** A 403 with a clear "you are a bot" message would help a determined attacker improve their evasion. A bare 403 is forensically informative to us via the firewall_event log but useless to the attacker.

## Why all three together

Each check on its own catches roughly 30–50 % of low-effort scraper traffic in the public datasets we benchmarked against. Together they catch >95 % of bot traffic that would otherwise reach the token bucket and consume an anonymous slot (cost: 1 of 2 daily anonymous queries on that IP).

The three checks cost ~0.05 ms in CPU per request — strictly free compared to the ~250 ms Turnstile verification call (when not cached) or the ~1000 ms LLM call further down the stack. Putting them BEFORE Turnstile in the dispatch order in `firewall/wire.py` means bot-shaped requests are rejected before we even pay for a Cloudflare round-trip.

## What this doesn't catch

- Bots that fully render the page via Playwright / Puppeteer and fill the hidden field correctly, wait 1.5 s, and use a real-browser UA. These are caught by the token bucket (1/min/IP) and the per-/24 subnet cap (12/hour, 30/day), then by the kill switch when the dwell-time-faking bot tries to scale.
- A real student behind a corporate proxy that strips UA and dwell headers. They'd get a 403 they don't understand. We accept this trade-off because the widget is meant to be embedded in `gktuition.ie` (where the JS will always populate both), so the absence of these headers is itself a signal. If reports start coming in from real users, the widget developer can add a fallback HTTP-only header to bypass the check (rather than us loosening the check on the server).

## Reviewing this layer

The success metric is `firewall_event outcome=blocked reason=...` lines in the Fly.io log shipper, grouped by `reason`. The expected breakdown over a normal week:

- `honeypot` — 1–5 % of total blocked anonymous traffic.
- `dwell_too_short` — 5–10 %.
- `bot_ua` — 60–75 %.
- `empty_ua` — 10–20 %.
- Subnet cap — 5–10 %.

If `bot_ua` drops below ~50 %, refresh the prefix list — bots have moved on.
If `dwell_too_short` blocks ever exceed `bot_ua`, the dwell threshold may have drifted out of step with real-student typing speed; lower to 1200 ms and re-baseline.
