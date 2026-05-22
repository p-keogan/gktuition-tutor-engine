# Widget contract deltas vs. the Agent-09 contract

Open notes on places where the brief and the as-shipped Pydantic contract diverge. The widget conforms to the **as-shipped contract** (the Python source of truth), so anything in this file is either documenting a derivation the widget does locally or flagging a question for you / Agent 09.

## 1. Citation URLs — `youtube_url` + `gktuition_url`

**Brief said:** "every citation has a `youtube_url` + `gktuition_url` in the JSON contract".

**Contract actually says:** `Citation` has `slug`, `title`, `timestamp_seconds`, `score` — no URL fields.

**What the widget does:** derives `gktuition_url` locally as `https://gktuition.ie/topic/<slug>/[?t=<seconds>]` (URL convention observed at e.g. `gktuition.ie/topic/the-line-4-area-of-triangle/`). The same URL doubles as the `youtube_url` because the WordPress topic page embeds the YouTube player and honours `?t=` for the timestamp seek. The widget does not link to `youtube.com` directly because the YouTube video ID is not present on the citation — it lives in the per-tutorial YAML frontmatter (see `tutorials/SCHEMA.md`) and would need to be plumbed through the orchestrator to surface here.

**Open question:** should `Citation` grow a `youtube_video_id` (or `youtube_url`) field? Pro: removes the widget-side guess and supports a future "open in YouTube app" deep-link. Con: hand-curation cost is non-zero, and the topic-page hop is a pedagogically useful detour anyway (it surfaces the rest of the tutorial alongside the video). My read: do NOT add the field yet. If we later want a direct-to-YouTube path, the swap is one helper function in `src/utils/citations.ts`.

## 2. Tier endpoint path — `/tier` vs. `/token`

**Brief says:** the WP REST endpoint is `/wp-json/gktuition/v1/tier`.

**`api/auth/jwt.py` docstring says:** the WP REST endpoint is `/wp-json/gktuition/v1/token`.

**What Stack A implements:** `/wp-json/gktuition/v1/tier` (per the brief, which is the more recent of the two specs).

**Open question:** update the docstring in `api/auth/jwt.py` to match? It's prose-only — the decoder doesn't actually care about the path — but the inconsistency will trip up the next person reading the code.

## 3. `query_class = "ambiguous"`

The contract enumerates six values. The brief listed five in the Definition-of-done sentence ("concept, solution_lookup, summary_request, analytical, image_extracted, ambiguous" — wait, that's six). The widget handles all six in its progress-hint map; the mock E2E suite exercises all six.

Nothing to flag — this is a no-op note for completeness.

## 4. JWT TTL

Both ADR-003 and the brief specify v1 TTL = 3600 seconds (60 min). Phase 3 hardening drops it to 300 s. The plugin reads `GKTUITION_JWT_TTL_SECONDS` from `wp-config.php` with a default of 3600 — when the Phase 3 cut happens you change one line in `wp-config.php`, no plugin redeploy.

## 5. CORS — dev port

`api/main.py` per Agent 09's note allows `localhost:5173` in `GKTUITION_ENV=dev`. Vite's default dev port is 5173, so the widget's `npm run dev` works against a locally-running uvicorn without any CORS tweak. Documented here so we don't forget it.
