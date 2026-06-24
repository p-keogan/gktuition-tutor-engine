# LCHL Corpus Edit Playbook

How to change tutor content **and propagate the change everywhere it needs to
go** so the live AI tutor actually reflects it. Use this while stress-testing
the tutor and fixing answers.

---

## 1. Mental model — where content lives and how it reaches the tutor

**Source of truth (edit these):** `career-transition-2026/tutorials/`
- `LCHL_<Strand>/<slug>.md` — tutorial files: YAML frontmatter (`title`, `slug`,
  `topic`, `sequence_number`, `prerequisites`, `forward_links`,
  `exam_appearances`, `learning_work`) + the teaching body.
- `LCHL_Maths_Exams/Solutions/<year>_P<n>_solutions.md` — worked exam solutions
  (parsed into ~1,213 "parts": `question_text`, `solution_text`,
  `common_pitfalls`, `tutorials_referenced`, marks, etc.).
- `LCHL_<Strand>/_SUMMARY-exam-cram.md` and `_voice.md` — strand cram summaries
  and Paul's voice rules.

**How content reaches the live tutor — two routes:**

| Route | What it serves | Lives in | Updated by |
|---|---|---|---|
| **Snowflake Cortex Search (LIVE)** | the actual answers/retrieval | `RAW.TUTORIALS`→`TUTOR_SEARCH`, `RAW.EXAM_PARTS`→`SOLUTIONS_SEARCH`, `RAW.SUMMARIES`→`SUMMARY_SEARCH` | loaders + re-index (NO engine redeploy — read live) |
| **Baked into the engine image** | exam-reference chips + voice-anchor prompt | `gktuition-tutor-engine/corpus/exam_appearances.json`, `corpus/tutorials/**/_SUMMARY-exam-cram.md`, `_voice.md` | regenerate file → **`flyctl deploy`** |

Key consequence: **most content fixes are reload + re-index, with NO engine
redeploy.** Only `exam_appearances` and strand summaries/voice are baked into the
image and need a redeploy.

---

## 2. Propagation matrix — what to run for each kind of edit

| You edited… | 1. Reload table | 2. Re-index | 3. Regenerate + `flyctl deploy` | 4. Widget |
|---|---|---|---|---|
| Tutorial **teaching body / wording** | `load_tutorials.py` | refresh `TUTOR_SEARCH` | — | — |
| Exam **solution text / pitfalls / refs** | `load_exam_parts.py` | refresh `SOLUTIONS_SEARCH` | — | — |
| A tutorial's **`exam_appearances`** block | `load_tutorials.py` (if other fields changed) | refresh `TUTOR_SEARCH` | `scripts/build_exam_appearances.py` → **deploy** | — |
| **Strand summary / `_voice.md`** | `load_summaries.py` | refresh `SUMMARY_SEARCH` | `scripts/sync_corpus.sh` → **deploy** (voice anchor) | — |
| **New tutorial or changed `slug`** | `load_tutorials.py` | refresh `TUTOR_SEARCH` | (exam json if it carries appearances) | regenerate `widget/src/utils/slugMap.ts`, rebuild + redeploy widget; add the WP topic page |

**Re-index command (preferred):**
```bash
python content-pipeline/sync/refresh_cortex.py        # ALTER … REFRESH; preserves grants
```
`refresh_cortex.py` uses `ALTER CORTEX SEARCH SERVICE … REFRESH`, which re-pulls
only changed rows and **keeps the `GKTUITION_APP_RW` grant intact**. Or, if
it's not urgent, do nothing — `TARGET_LAG = '1 day'` re-indexes automatically
overnight.

⚠️ **Do NOT use `CREATE OR REPLACE CORTEX SEARCH SERVICE` for a content refresh.**
It drops the service's grants, and the engine (role `GKTUITION_APP_RW`) loses
access until you re-grant:
```sql
GRANT USAGE ON CORTEX SEARCH SERVICE GKTUITION_TUTOR.CORTEX.<SERVICE> TO ROLE GKTUITION_APP_RW;
```

---

## 3. Loader commands (run from `gktuition-tutor-engine/snowflake/`)

First set Snowflake env vars (don't commit the password):
```bash
export SNOWFLAKE_ACCOUNT="VFUSMXI-YS47680"
export SNOWFLAKE_USER="pkeogan"
export SNOWFLAKE_PASSWORD="<password>"
export SNOWFLAKE_ROLE="ACCOUNTADMIN"
export SNOWFLAKE_WAREHOUSE="WH_TUTOR"
export SNOWFLAKE_DATABASE="GKTUITION_TUTOR"
export SNOWFLAKE_SCHEMA="RAW"
```
Then (idempotent MERGEs; `--dry-run` parses without writing):
```bash
python load_tutorials.py  --tutorials-root ../../career-transition-2026/tutorials
python load_exam_parts.py --no-write-crossrefs --solutions-dir ../../career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions
python load_summaries.py  --tutorials-root ../../career-transition-2026/tutorials
```
The whole detect-changes-then-load pipeline can also run via
`content-pipeline/sync/run_loaders.py` (it only fires the loaders whose source
files changed).

Regenerate the baked-in exam-reference index (only when `exam_appearances` changed):
```bash
python scripts/build_exam_appearances.py --src ../career-transition-2026/tutorials --out corpus/exam_appearances.json
cd .. && flyctl deploy        # ships the new JSON in the image
```

---

## 4. Operating rules (today's hard-won lessons)

- **Batch your edits.** Re-indexing/embedding costs Snowflake credits. Collect a
  batch of content fixes, then reload + refresh once — don't do it per typo.
- **Mind the cost cap.** A reindexing batch can hit `RM_DAILY_BUDGET` (default 2
  credits/day) and suspend `WH_TUTOR`. For a heavy batch, raise it first
  (`ALTER RESOURCE MONITOR RM_DAILY_BUDGET SET CREDIT_QUOTA = 5;`) and set it back
  after.
- **Semantic cache.** After fixing content, a previously-asked question may still
  return the cached answer. The cache key includes the retrieved slugs + model,
  so changed content usually misses — but to be sure, re-test with slightly
  different phrasing.
- **Run multi-line SQL in a Snowflake worksheet, not a terminal heredoc** — the
  terminal drops characters from pasted heredocs (lost a chunk of tonight to
  `GRANUSAGE`-style corruption).
- **Engine reads Snowflake live** → no redeploy for tutorial/solution/summary
  *content*. Redeploy only for `exam_appearances.json` or summary/voice changes
  (baked in the image).
- **Verify before moving on:** smoke-test the service, then ask the tutor.
  ```sql
  SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW('GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH',
    '{"query":"<your test>","columns":["part_id","topic"],"limit":3}');
  ```
- **Commit** the edited `.md` source + any regenerated `exam_appearances.json` /
  synced summaries / `slugMap.ts` to git (clear stale locks first if needed:
  `rm -f .git/*.lock .git/refs/heads/*.lock && git reset && git add -A && git commit`).

---

## 5. Suggested daily workflow while testing

1. Keep a running log of issues (query → what's wrong → what it should say →
   which source file). `docs/QUALITY_TESTING_NOTES.md` is the template.
2. At the end of a testing block, hand the batch to a helper agent (prompt
   below) or work through it yourself.
3. Edit the **source `.md`** files only.
4. Run the matrix steps for the edit types you touched (reload → refresh →
   regenerate/deploy if needed).
5. Verify (smoke test + ask the tutor).
6. Commit.

---

## 6. Prompt to enlist a helper agent

Paste this to a fresh agent, then describe the content issues. It starts cold,
so everything it needs is here.

> You are helping Paul Keogan maintain the **LCHL Maths AI tutor** content. When
> Paul reports a problem with a tutor answer, your job is to fix the **source
> corpus** and identify + carry out **every propagation step** so the change
> reaches the live tutor — not just edit one file.
>
> **Repos (all under `/Users/paul/code/`):**
> - `career-transition-2026/tutorials/` — SOURCE content (edit here):
>   `LCHL_<Strand>/<slug>.md` tutorials (frontmatter + body),
>   `LCHL_Maths_Exams/Solutions/*.md` worked solutions,
>   `LCHL_<Strand>/_SUMMARY-exam-cram.md` + `_voice.md`.
> - `gktuition-tutor-engine/` — FastAPI engine, Snowflake loaders
>   (`snowflake/load_*.py`), re-index script
>   (`content-pipeline/sync/refresh_cortex.py`), and baked-in
>   `corpus/exam_appearances.json` + `corpus/tutorials/**/_SUMMARY*.md`.
> - `gktuition-prod/wordpress-plugin/gktuition-ai-tutor/` — the WP plugin + built
>   widget (`dist/`).
>
> **How content reaches the tutor:** tutorial/solution/summary CONTENT is served
> LIVE from Snowflake Cortex Search (`TUTOR_SEARCH`, `SOLUTIONS_SEARCH`,
> `SUMMARY_SEARCH`) — so it needs a loader reload + a Cortex refresh, but NO
> engine redeploy. EXCEPTIONS that ARE baked into the engine image and need
> `flyctl deploy`: `exam_appearances` (regenerate `corpus/exam_appearances.json`
> via `scripts/build_exam_appearances.py`) and strand summaries/`_voice.md`
> (resync via `scripts/sync_corpus.sh`).
>
> **Propagation matrix:**
> - Tutorial body/wording → `load_tutorials.py` → refresh `TUTOR_SEARCH`.
> - Exam solution text/pitfalls/tutorials_referenced → `load_exam_parts.py` →
>   refresh `SOLUTIONS_SEARCH`.
> - `exam_appearances` frontmatter → `load_tutorials.py` + regenerate
>   `exam_appearances.json` → `flyctl deploy`.
> - Strand summary / voice → `load_summaries.py` → refresh `SUMMARY_SEARCH` +
>   `sync_corpus.sh` → `flyctl deploy`.
> - New tutorial / changed slug → `load_tutorials.py` + refresh + regenerate
>   `widget/src/utils/slugMap.ts` (corpus-slug → WP-slug) + rebuild & redeploy
>   the widget + add the WP topic page.
>
> **Re-index with `python content-pipeline/sync/refresh_cortex.py`
> (`ALTER … REFRESH`). NEVER `CREATE OR REPLACE` a Cortex Search service for a
> content refresh — it drops the `GKTUITION_APP_RW` grant and the tutor loses
> access.** If a service is ever recreated, re-grant:
> `GRANT USAGE ON CORTEX SEARCH SERVICE GKTUITION_TUTOR.CORTEX.<svc> TO ROLE GKTUITION_APP_RW;`
>
> **Division of labour:** YOU make the source-file edits (and can regenerate
> derived files like `exam_appearances.json` and `slugMap.ts`). PAUL runs the
> commands that need his credentials — the Snowflake loaders/refresh
> (`SNOWFLAKE_ACCOUNT=VFUSMXI-YS47680`, `USER=pkeogan`, `ROLE=ACCOUNTADMIN`,
> `WAREHOUSE=WH_TUTOR`, `DATABASE=GKTUITION_TUTOR`), `flyctl deploy`, and the
> widget deploy (base64-over-ssh to WP Engine staging). So: make the edits, then
> give Paul the exact, copy-paste commands for his terminal, grouped and in order.
>
> **Operating rules:** batch edits (re-indexing costs Snowflake credits); the
> daily cap is `RM_DAILY_BUDGET` (raise to 5 for a big batch, reset to 2 after);
> give multi-line SQL as something to paste into a Snowflake **worksheet** (the
> terminal corrupts pasted heredocs); after changes, provide a `SEARCH_PREVIEW`
> smoke test and have Paul re-ask the tutor (note the semantic cache may need a
> reworded retest); finish by committing the edited source + regenerated files
> to git.
>
> **Voice/style rules for any content you write:** match Paul's teaching voice,
> use LCHL terminology (e.g. say "conditional probability", never "Bayes' rule"),
> reference the log tables where relevant, and keep worked solutions complete and
> step-by-step.
>
> Start by asking Paul to paste his batch of issues (query → what's wrong → what
> it should say). For each, tell him which source file(s) you'll edit and the
> full propagation plan before doing it.
