# eval/cache — AGENT_33 hosted-librarian caches (Snowflake-exit Phase-0 v4)

Committed so the v4 result reproduces **offline + free** (no Voyage key needed
after a one-time bounded populate pass).

Layout:

* `voyage_embed/<model>/{index.json,vectors.npy}` — cached Voyage embedding
  vectors, keyed by `sha1(input_type + "\0" + text)`. `input_type` is part of
  the key (document vs query embed the same text differently).
* `hosted_rerank.json` — cached rerank results, keyed by
  `sha1(model | eval_id | sorted-candidate-slugs)`.
* `results/<backend>.jsonl` — per-row top-20 `(slug,score)` checkpoints the
  parity harness replays (`report` / `recall` phases).

**State at AGENT_33 hand-off:** EMPTY. The spike environment had no
`VOYAGE_API_KEY`, so per dispatch rule 4(d) nothing was fabricated. Populate
with the bounded operator one-liner in
`docs/SNOWFLAKE_EXIT_PHASE0_REPORT_V4.md` §Verification, after which all scoring
is offline.
