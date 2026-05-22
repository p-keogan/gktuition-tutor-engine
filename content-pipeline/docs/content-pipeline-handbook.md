# Content pipeline — operator's handbook

This document is the README for `content-pipeline/`. It answers the five
questions an operator (Paul, today; future maintainers later) has when
something either works or doesn't work in the content-edit propagation
loop.

If you ever change the loaders, the schema, or the Cortex Search
services, also read `loader-code-change-runbook.md` next door — it
specifically covers the case where the *pipeline* changed under
the corpus, which carries different risks than a content edit.

---

## The three-sentence summary

A tutorial edit you make in Cursor reaches a student on `gktuition.ie`
in three steps: (a) a pre-commit hook validates the YAML frontmatter so
malformed authoring never reaches `origin/main`, (b) a GitHub Action
fires on push, runs only the loaders whose categories changed, and
appends one audit row to `RAW.CONTENT_CHANGE_LOG`, and (c) the Cortex
Search Service re-embeds within its 1-day `TARGET_LAG` — or sooner if
the workflow's refresh gate fires (a summary file changed, or >3 files
moved, or you passed `force_cortex_refresh=true` to the manual
dispatch). End-to-end median latency on a typo fix is about 25 seconds
to MERGE plus whatever you ask of the refresh; default end-to-end is
"by tomorrow morning", forced end-to-end is "within two minutes".

---

## "I edited a tutorial in Cursor. What happens?"

The pre-commit hook (`content-pipeline/validators/pre-commit-hook.sh`)
runs `yaml_frontmatter.py --staged` on every `git commit`. Four
classes of mistake will block the commit before it even hits your
local branch:

1. **Malformed YAML** — unclosed quotes, indentation drift, tab
   characters. Reported as `file:line:column`.
2. **Missing required field** in a tutorial: `slug`, `video_id`, or
   `title` (the three NOT-NULL columns in `RAW.TUTORIALS`).
3. **Placeholder values in load-breaking fields** — `TBD`, `???`,
   `TODO` in numeric fields (`duration_seconds`, `paper`,
   `sequence_number`, `syllabus.strand`). This is the regression that
   broke the DAY_26 first load; the validator catches it at commit
   time so it never gets a second chance.
4. **Duplicate slug** across the corpus — every walked file's `slug`
   must be unique.

You'll see ERROR diagnostics in the terminal; fix the offending file
and re-run `git commit`. The validator also emits WARN diagnostics for
softer problems (dead `xref` links, missing-but-recommended fields,
placeholder strings in nullable columns). Warnings don't block —
they're authoring nudges.

If your edit clears the hook, the commit lands; on `git push`, the
GitHub Action picks up the change and:

* Runs the validator over the **full** corpus (catches cross-file
  problems the staged check can't see — a slug renamed in file A but
  still referenced as a prerequisite in file B).
* Calls `detect_changes.py` to classify what moved.
* Calls `run_loaders.py`, which dispatches `load_tutorials.py`,
  `load_exam_parts.py`, and/or `load_summaries.py` — only the ones
  whose category was touched, in the order tutorials → solutions →
  summaries (because solutions and summaries cite tutorial slugs).
* Writes one row to `GKTUITION_TUTOR.RAW.CONTENT_CHANGE_LOG` with the
  commit SHA, files changed, loaders run, row counts, and duration.
* Maybe fires a Cortex Search REFRESH (see the next question).
* Posts a commit comment with the run summary so you see the
  outcome in your git UI without having to open the Actions tab.

The whole loop, end-to-end, is about 25 seconds for a single-tutorial
edit and 2–3 minutes if `_SUMMARY-*` files moved (the bigger refresh
takes longer to settle).

---

## "I want to ship the change in 2 minutes, not 24 hours. What command do I run?"

The default `TARGET_LAG` on every Cortex Search Service is 1 day —
overnight re-embeds are right for normal cadence. To force an
immediate refresh:

### From your laptop

```bash
cd gktuition-tutor-engine
python content-pipeline/sync/refresh_cortex.py \
    --services TUTOR_SEARCH,SOLUTIONS_SEARCH,SUMMARY_SEARCH
```

Requires the `SNOWFLAKE_*` env vars (same set the loaders use). The
script blocks until `last_refreshed_on` advances or the per-service
10-minute timeout elapses. If you only changed one document type,
pass just that service — refreshing all three is wasted compute.

### From the GitHub Action

Push the commit, then under the repo's Actions tab → content-sync →
"Run workflow", set `force_cortex_refresh = true`. Same outcome, no
local credentials needed.

### When NOT to force a refresh

* You're in the middle of an eval-set re-score. The baseline depends
  on a stable index; refreshing mid-score moves the goalposts.
* You're making a series of edits — wait until the burst is done and
  refresh once at the end. Each REFRESH consumes warehouse credits.

---

## "Something broke. How do I roll back?"

The pipeline never deletes rows — every loader is an idempotent MERGE
on a stable key (slug / part_id / summary_id). So "rolling back" means
either (a) reverting the source commit and pushing the revert, which
the next sync run will MERGE back to the previous state, or (b) hand-
editing the offending file and pushing that.

### Diagnosis order

1. **Open the run in the Actions tab.** The failed step is highlighted
   red; click it for the log. Most common causes: missing
   `SNOWFLAKE_*` secret, network blip on the sibling-repo checkout,
   the validator catching a regression you missed locally.

2. **Find the audit row.** Even on failure, the run writes one:

   ```sql
   SELECT *
     FROM RAW.CONTENT_CHANGE_LOG
    WHERE git_commit_sha = '<sha>';
   ```

   The `notes` column carries `FAILURES: load_tutorials(exit=1)` on a
   partial failure — that tells you which loader broke without
   reading the CI log.

3. **Inspect the manifest artefact.** The workflow uploads
   `manifest.json` and `content-pipeline/last-run.json` on every run
   (success or failure) — download from the Actions tab and you can
   replay the same call locally:

   ```bash
   python content-pipeline/sync/run_loaders.py \
       --manifest /path/to/manifest.json \
       --audit-only-local
   ```

   `--audit-only-local` keeps the dry replay off the audit table.

### Rollback procedure (full revert)

```bash
# Identify the bad commit.
git log --oneline -- tutorials/

# Revert it.
git revert <sha>
git push origin main
```

The next workflow run will MERGE the previous-state row back into
Snowflake. There's no "undo button" because there doesn't need to be
one — MERGE on `slug` is the undo button.

### Rollback procedure (partial — one tutorial)

Edit the offending `.md` file, commit, push. Same loop fires; the
single row updates in place.

---

## "How do I see what changed in the last week?"

```sql
SELECT triggered_at,
       triggered_by,
       files_changed,
       loaders_run,
       rows_inserted,
       rows_updated,
       cortex_refresh_triggered,
       notes
  FROM GKTUITION_TUTOR.RAW.CONTENT_CHANGE_LOG
 WHERE triggered_at >= DATEADD(day, -7, CURRENT_TIMESTAMP())
 ORDER BY triggered_at DESC;
```

Other useful patterns:

```sql
-- "Did this push make it through?"
SELECT *
  FROM RAW.CONTENT_CHANGE_LOG
 WHERE git_commit_sha = '<sha>';

-- "What have I been failing on?"
SELECT triggered_at, notes, files_changed
  FROM RAW.CONTENT_CHANGE_LOG
 WHERE notes ILIKE 'FAILURES%'
 ORDER BY triggered_at DESC
 LIMIT 50;

-- "Which files churn the most?"
SELECT f.value::VARCHAR AS path, COUNT(*) AS edits
  FROM RAW.CONTENT_CHANGE_LOG,
       LATERAL FLATTEN(input => files_changed) f
 WHERE triggered_at >= DATEADD(day, -30, CURRENT_TIMESTAMP())
 GROUP BY path
 ORDER BY edits DESC
 LIMIT 20;
```

The table is append-only. There's no clean-up cadence in v1 — it's
small (one row per push) and the data is genuinely useful for
"how is the corpus evolving" questions.

---

## "I'm renaming a slug. What's the procedure?"

Slug renames are the single most-disruptive content edit because every
tutorial's `prerequisites`, `forward_links`, and `xref` arrays carry
slugs verbatim, and every solution file's `cross_references` block
lists slugs. A rename without follow-through leaves dead links
everywhere.

Procedure:

1. **Rename the file.** `git mv tutorials/LCHL_<strand>/old-slug.md
   tutorials/LCHL_<strand>/new-slug.md`. The on-disk filename matters
   downstream (it's part of `source_path` in `RAW.TUTORIALS`).

2. **Update the slug inside the file.** Edit the YAML's `slug:` field.

3. **Search-and-replace across the corpus.** From the corpus root:

   ```bash
   grep -rl 'old-slug' tutorials/ | xargs sed -i '' 's|old-slug|new-slug|g'
   ```

   (On Linux, drop the `''` after `-i`.) This catches references in
   `prerequisites`, `forward_links`, `xref`, the solutions
   crossref blocks, and any prose mentions.

4. **Re-run the exam-parts loader's crossref rewrite** so the
   solution files' machine-readable blocks pick up the new slug name:

   ```bash
   cd gktuition-tutor-engine
   python snowflake/load_exam_parts.py --dry-run \
       --solutions-dir ../career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions
   ```

   Inspect the diff. If the cross-references look right, drop
   `--dry-run` and run for real.

5. **Validate.** `python content-pipeline/validators/yaml_frontmatter.py
   --all` — the xref-graph check warns on every dead link. The dead-
   link count should be exactly zero after the search-and-replace.

6. **Re-score the eval set.** Slug renames change row identities in
   `RAW.EVAL_GOLDEN_SET` (which references slugs). Re-run
   `eval/build_eval_set.py` to refresh the slug column, then re-run
   `eval/score_against_cortex_search.py`. The DAY_26 baseline is
   `precision@1 = 0.710`; the rename should not move precision by
   more than ±0.005 if it's purely cosmetic. A larger move means the
   rename also changed something semantic (e.g. you collapsed two
   tutorials into one).

7. **Commit + push.** The GitHub Action will MERGE the new slug,
   leaving the old slug's row in `RAW.TUTORIALS` as an orphan. Open
   one cleanup query in a worksheet to DELETE the orphan row by hand:

   ```sql
   DELETE FROM GKTUITION_TUTOR.RAW.TUTORIALS WHERE slug = 'old-slug';
   ```

   This step is intentionally manual — the pipeline doesn't
   auto-delete rows because a rename is hard to tell apart from a
   refactor that splits one tutorial into two. The orphan row is
   discoverable via:

   ```sql
   SELECT slug FROM RAW.TUTORIALS
   MINUS
   SELECT DISTINCT slug FROM (
       SELECT VALUE::VARCHAR AS slug
         FROM (SELECT files_changed FROM RAW.CONTENT_CHANGE_LOG
                WHERE triggered_at >= DATEADD(day, -30, CURRENT_TIMESTAMP())),
              LATERAL FLATTEN(input => files_changed)
   );
   ```

   …though "which tutorials no longer exist on disk" is cheaper to
   answer with `ls tutorials/LCHL_*/*.md` than with SQL.

---

## File-by-file map

```
content-pipeline/
├── validators/
│   ├── yaml_frontmatter.py    — the validator (pre-commit + CI)
│   └── pre-commit-hook.sh     — installer script for the local hook
├── sync/
│   ├── detect_changes.py      — git diff → JSON manifest
│   ├── run_loaders.py         — manifest → loader subprocesses + audit row
│   ├── refresh_cortex.py      — ALTER ... REFRESH on the three services
│   └── bootstrap_content_change_log.sql
│                              — one-shot DDL for the audit table
└── docs/
    ├── content-pipeline-handbook.md   (this file)
    └── loader-code-change-runbook.md  — what to do if the loaders changed
```

The GitHub Action lives at `.github/workflows/content-sync.yml` in the
repo root — it's not technically inside `content-pipeline/` but it's
the runner that fires every piece in this folder.
