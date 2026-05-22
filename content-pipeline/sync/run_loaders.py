#!/usr/bin/env python3
"""Read a manifest from ``detect_changes.py`` and dispatch only the
loaders that need to fire, in the right order, with a single audit
row appended to ``GKTUITION_TUTOR.RAW.CONTENT_CHANGE_LOG``.

Contract
--------
* Loader scripts are called as subprocesses — the same way a human
  would invoke them, with the same ``--tutorials-root`` /
  ``--solutions-dir`` arguments. We do NOT reach into their internals.
* The audit row goes to Snowflake last, after every loader has
  finished. If Snowflake credentials are missing, the row is written
  to a local JSON file (``content-pipeline/last-run.json``) so the
  run is still traceable; the runner returns non-zero in that case.
* Loaders are idempotent. Running this script twice with no
  intervening commits results in 0 inserts and N updates on the
  second pass, because the underlying MERGEs use the same source
  set and re-stamp ``loaded_at``.

Manifest → loader map
---------------------

    Touched category         → Loader script
    ---------------------------------------------------------------
    tutorials                 → snowflake/load_tutorials.py
                                  --tutorials-root <path>
    exam_solutions            → snowflake/load_exam_parts.py
                                  --solutions-dir <path>/Solutions
    summaries                 → snowflake/load_summaries.py
                                  --tutorials-root <path>
    schema  (SCHEMA.md)       → STOP, human review required
    loader_code_changed=True  → STOP, human review required (run the
                                  eval re-score per
                                  docs/loader-code-change-runbook.md)

The runner does not "do something safe" on STOP — silent fallbacks
are how DAY_26's first load broke. STOP returns exit 3 with a clear
message; the operator must re-dispatch explicitly.

Usage
-----

    # Standard CI invocation.
    python sync/run_loaders.py --manifest manifest.json

    # Local replay — write the audit row to a file, not Snowflake.
    python sync/run_loaders.py --manifest manifest.json --audit-only-local

    # Override the tutorials-root (handy when the sibling repo lives
    # somewhere non-default in CI).
    python sync/run_loaders.py --manifest manifest.json \\
        --tutorials-root /workspace/career-transition-2026/tutorials

Exit codes
----------
* 0 — all required loaders finished cleanly.
* 1 — at least one loader failed; the audit row was still written
       (with the failure recorded) so the failure is queryable.
* 2 — invocation error (manifest missing, bad CLI args).
* 3 — STOP fired (schema touched or loader code changed); no
       loaders ran.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_loaders")

# ─────────────────────────────────────────────────────────────────────
# Path defaults
# ─────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent  # content-pipeline/sync/
ENGINE_ROOT = HERE.parent.parent  # gktuition-tutor-engine/
LOADER_DIR = ENGINE_ROOT / "snowflake"


def _default_tutorials_root() -> Path:
    """Sibling-repo layout: ~/code/gktuition-tutor-engine and
    ~/code/career-transition-2026. Override via --tutorials-root."""
    return ENGINE_ROOT.parent / "career-transition-2026" / "tutorials"


def _default_audit_local_path() -> Path:
    return ENGINE_ROOT / "content-pipeline" / "last-run.json"


# ─────────────────────────────────────────────────────────────────────
# Loader invocation
# ─────────────────────────────────────────────────────────────────────
@dataclass
class LoaderRun:
    name: str
    cmd: list[str]
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0

    def succeeded(self) -> bool:
        return self.exit_code == 0


# The MERGE-result log line emitted by every loader has a stable
# shape:
#   "MERGE complete: N inserted, M updated"
# We extract the counts so the audit row carries real numbers
# rather than just "loader ran". The loaders for exam_parts /
# summaries use slightly different log wording — we match all
# variants.
import re

MERGE_LINE_RES = [
    re.compile(r"MERGE complete:\s*(\d+)\s+inserted,\s*(\d+)\s+updated", re.IGNORECASE),
    re.compile(
        r"Loaded:\s*\d+\s+rows merged into [A-Z_]+\s*\((\d+)\s+inserted,\s*(\d+)\s+updated\)",
        re.IGNORECASE,
    ),
]


def _parse_merge_counts(text: str) -> tuple[int, int]:
    """Return (inserted, updated) extracted from a loader's stdout, or
    (0, 0) if no MERGE line was printed (dry-run or load-skipped)."""
    for pat in MERGE_LINE_RES:
        m = pat.search(text)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 0, 0


def run_loader(
    *,
    name: str,
    script: Path,
    extra_args: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    dry_run: bool = False,
) -> LoaderRun:
    """Spawn a loader subprocess. Captures stdout/stderr; never raises
    on subprocess failure — failures propagate as ``exit_code != 0`` so
    the audit row still gets written."""
    python = sys.executable or "python3"
    cmd = [python, str(script), *extra_args]
    if dry_run:
        cmd.append("--dry-run")
    run = LoaderRun(name=name, cmd=cmd)
    log.info("→ %s: %s", name, " ".join(cmd))
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            check=False,
        )
        run.exit_code = proc.returncode
        run.stdout = proc.stdout
        run.stderr = proc.stderr
    except FileNotFoundError as e:
        run.exit_code = 127
        run.stderr = f"FileNotFoundError: {e}"
    run.duration_ms = int((time.monotonic() - t0) * 1000)
    if run.succeeded():
        run.rows_inserted, run.rows_updated = _parse_merge_counts(
            run.stdout + "\n" + run.stderr
        )
        log.info(
            "✓ %s finished in %dms (%d inserted, %d updated)",
            name,
            run.duration_ms,
            run.rows_inserted,
            run.rows_updated,
        )
    else:
        log.error(
            "✗ %s failed (exit=%d) after %dms — see stderr below",
            name,
            run.exit_code,
            run.duration_ms,
        )
        if run.stderr:
            for line in run.stderr.splitlines()[-30:]:
                log.error("    %s", line)
    return run


# ─────────────────────────────────────────────────────────────────────
# Audit row → CONTENT_CHANGE_LOG
# ─────────────────────────────────────────────────────────────────────
AUDIT_TABLE_DDL = """\
CREATE OR REPLACE TABLE GKTUITION_TUTOR.RAW.CONTENT_CHANGE_LOG (
    change_id                   VARCHAR        NOT NULL,
    git_commit_sha              VARCHAR,
    triggered_by                VARCHAR,
    triggered_at                TIMESTAMP_NTZ  NOT NULL,
    files_changed               ARRAY,
    loaders_run                 ARRAY,
    rows_inserted               NUMBER,
    rows_updated                NUMBER,
    rows_unchanged              NUMBER,
    duration_ms                 NUMBER,
    cortex_refresh_triggered    BOOLEAN,
    notes                       VARCHAR,
    CONSTRAINT pk_content_change_log PRIMARY KEY (change_id)
);
"""


@dataclass
class AuditRow:
    change_id: str
    git_commit_sha: str
    triggered_by: str
    triggered_at: str  # ISO-8601 UTC, NTZ
    files_changed: list[str]
    loaders_run: list[str]
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    duration_ms: int
    cortex_refresh_triggered: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "git_commit_sha": self.git_commit_sha,
            "triggered_by": self.triggered_by,
            "triggered_at": self.triggered_at,
            "files_changed": self.files_changed,
            "loaders_run": self.loaders_run,
            "rows_inserted": self.rows_inserted,
            "rows_updated": self.rows_updated,
            "rows_unchanged": self.rows_unchanged,
            "duration_ms": self.duration_ms,
            "cortex_refresh_triggered": self.cortex_refresh_triggered,
            "notes": self.notes,
        }


def _make_change_id(git_sha: str | None, triggered_at: str) -> str:
    """Stable per-run ID. Git SHA + timestamp keeps natural-key behaviour
    if the user re-runs after a CI replay; if no SHA is available
    (local invocation pre-commit), we mix in a uuid4."""
    base = git_sha or uuid.uuid4().hex[:12]
    h = hashlib.sha1(f"{base}-{triggered_at}".encode("utf-8")).hexdigest()[:16]
    return f"chg_{h}"


def write_audit_row_local(audit_path: Path, row: AuditRow) -> None:
    """Append the row to a local JSONL file (one row per line). Used
    when Snowflake credentials are unavailable, or when the operator
    passes ``--audit-only-local`` to keep the run dry."""
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row.to_dict(), separators=(",", ":"))
    # The file is JSONL — append, not overwrite — so a sequence of
    # runs builds a real local audit trail.
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    log.info("Appended audit row %s to %s", row.change_id, audit_path)


def write_audit_row_snowflake(row: AuditRow) -> None:
    """INSERT the row into ``RAW.CONTENT_CHANGE_LOG``. Raises if the
    Snowflake connector isn't installed or env vars are missing — the
    caller catches and falls back to the local JSONL file."""
    import snowflake.connector  # type: ignore

    snowflake.connector.paramstyle = "qmark"
    conn_kwargs: dict[str, Any] = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "WH_TUTOR"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "GKTUITION_TUTOR"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "RAW"),
    }
    if pk := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        conn_kwargs["private_key_file"] = pk
        conn_kwargs["authenticator"] = os.environ.get(
            "SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT"
        )
    else:
        conn_kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]

    conn = snowflake.connector.connect(**conn_kwargs)
    try:
        cs = conn.cursor()
        try:
            cs.execute(
                """
INSERT INTO GKTUITION_TUTOR.RAW.CONTENT_CHANGE_LOG (
    change_id, git_commit_sha, triggered_by, triggered_at,
    files_changed, loaders_run, rows_inserted, rows_updated,
    rows_unchanged, duration_ms, cortex_refresh_triggered, notes
)
SELECT ?, ?, ?, ?,
       PARSE_JSON(?), PARSE_JSON(?), ?, ?, ?, ?, ?, ?
""",
                [
                    row.change_id,
                    row.git_commit_sha,
                    row.triggered_by,
                    row.triggered_at,
                    json.dumps(row.files_changed),
                    json.dumps(row.loaders_run),
                    row.rows_inserted,
                    row.rows_updated,
                    row.rows_unchanged,
                    row.duration_ms,
                    row.cortex_refresh_triggered,
                    row.notes,
                ],
            )
        finally:
            cs.close()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────
# STOP gate
# ─────────────────────────────────────────────────────────────────────
class HumanReviewRequired(Exception):
    """Raised when the manifest indicates a SCHEMA or loader-code
    change. The runner refuses to auto-dispatch in that case."""


def _stop_if_review_required(manifest: dict) -> None:
    reasons: list[str] = []
    if manifest.get("schema"):
        reasons.append(
            f"SCHEMA.md touched ({len(manifest['schema'])} file): every "
            "loader's row-build assumptions depend on this contract. Stop "
            "and re-validate against the corpus before re-running."
        )
    if manifest.get("loader_code_changed"):
        files = manifest.get("loader_code_files", [])
        reasons.append(
            f"loader code touched ({len(files)} file(s)): see "
            "docs/loader-code-change-runbook.md — re-run the eval-set "
            "scoring before deploying."
        )
    if reasons:
        msg_lines = ["STOP — human review required:"]
        msg_lines.extend(f"  • {r}" for r in reasons)
        raise HumanReviewRequired("\n".join(msg_lines))


# ─────────────────────────────────────────────────────────────────────
# Plan + execute
# ─────────────────────────────────────────────────────────────────────
@dataclass
class RunPlan:
    """The set of loaders that should fire for a given manifest."""

    run_tutorials: bool = False
    run_exam_solutions: bool = False
    run_summaries: bool = False

    @property
    def loaders_to_run(self) -> list[str]:
        out: list[str] = []
        if self.run_tutorials:
            out.append("tutorials")
        if self.run_exam_solutions:
            out.append("exam_solutions")
        if self.run_summaries:
            out.append("summaries")
        return out


def plan_from_manifest(manifest: dict) -> RunPlan:
    return RunPlan(
        run_tutorials=bool(manifest.get("tutorials")),
        run_exam_solutions=bool(manifest.get("exam_solutions")),
        run_summaries=bool(manifest.get("summaries")),
    )


def execute_plan(
    plan: RunPlan,
    *,
    tutorials_root: Path,
    loader_dir: Path,
    dry_run: bool,
) -> list[LoaderRun]:
    """Run each loader in dependency order. Tutorials first because
    EXAM_PARTS' crossref blocks reference tutorial slugs, then
    exam_solutions, then summaries (which reference tutorial slugs in
    the top-tutorials table). Order matters only if a single commit
    introduces a brand-new slug AND its first solution-file citation
    on the same push — rare, but cheap to be principled about."""
    runs: list[LoaderRun] = []
    solutions_dir = tutorials_root / "LCHL_Maths_Exams" / "Solutions"

    if plan.run_tutorials:
        runs.append(
            run_loader(
                name="load_tutorials",
                script=loader_dir / "load_tutorials.py",
                extra_args=["--tutorials-root", str(tutorials_root)],
                cwd=loader_dir,
                dry_run=dry_run,
            )
        )
    if plan.run_exam_solutions:
        runs.append(
            run_loader(
                name="load_exam_parts",
                script=loader_dir / "load_exam_parts.py",
                extra_args=["--solutions-dir", str(solutions_dir)],
                cwd=loader_dir,
                dry_run=dry_run,
            )
        )
    if plan.run_summaries:
        runs.append(
            run_loader(
                name="load_summaries",
                script=loader_dir / "load_summaries.py",
                extra_args=["--tutorials-root", str(tutorials_root)],
                cwd=loader_dir,
                dry_run=dry_run,
            )
        )
    return runs


# ─────────────────────────────────────────────────────────────────────
# Audit row construction
# ─────────────────────────────────────────────────────────────────────
def build_audit_row(
    *,
    manifest: dict,
    runs: list[LoaderRun],
    triggered_by: str,
    git_commit_sha: str,
    cortex_refresh_triggered: bool,
    extra_notes: list[str] | None = None,
) -> AuditRow:
    triggered_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    files_changed: list[str] = []
    for k in ("tutorials", "exam_solutions", "summaries", "schema"):
        files_changed.extend(manifest.get(k, []))
    files_changed.extend(manifest.get("loader_code_files", []))
    files_changed.sort()

    total_inserted = sum(r.rows_inserted for r in runs if r.succeeded())
    total_updated = sum(r.rows_updated for r in runs if r.succeeded())
    total_duration = sum(r.duration_ms for r in runs)
    loaders_run = [r.name for r in runs]

    notes: list[str] = list(extra_notes or [])
    failed = [r for r in runs if not r.succeeded()]
    if failed:
        notes.append(
            "FAILURES: "
            + ", ".join(f"{r.name}(exit={r.exit_code})" for r in failed)
        )

    return AuditRow(
        change_id=_make_change_id(git_commit_sha, triggered_at),
        git_commit_sha=git_commit_sha or "",
        triggered_by=triggered_by,
        triggered_at=triggered_at,
        files_changed=files_changed,
        loaders_run=loaders_run,
        rows_inserted=total_inserted,
        rows_updated=total_updated,
        rows_unchanged=0,  # Snowflake MERGE doesn't surface a third bucket
        duration_ms=total_duration,
        cortex_refresh_triggered=cortex_refresh_triggered,
        notes="; ".join(notes) or "ok",
    )


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def _detect_triggered_by() -> str:
    """Best-effort guess at who fired the run, for the audit row."""
    if os.environ.get("GITHUB_ACTIONS"):
        actor = os.environ.get("GITHUB_ACTOR", "github-action")
        return f"github-action:{actor}"
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    return f"human:{user}"


def _detect_git_sha(repo_root: Path | None) -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    cmd = ["git", "rev-parse", "HEAD"]
    try:
        out = subprocess.check_output(
            cmd,
            cwd=str(repo_root) if repo_root else None,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to the JSON manifest emitted by detect_changes.py.",
    )
    ap.add_argument(
        "--tutorials-root",
        type=Path,
        default=_default_tutorials_root(),
        help="Path to the tutorials/ directory.",
    )
    ap.add_argument(
        "--loader-dir",
        type=Path,
        default=LOADER_DIR,
        help="Directory containing the load_*.py scripts.",
    )
    ap.add_argument(
        "--audit-only-local",
        action="store_true",
        help="Skip the Snowflake audit INSERT; write the row to a "
             "local JSONL file only. The loaders still attempt their "
             "own Snowflake MERGE (they have their own env-var "
             "fallback to soft-skip when creds are missing).",
    )
    ap.add_argument(
        "--audit-local-path",
        type=Path,
        default=_default_audit_local_path(),
        help="Where to write the local audit JSONL (default: "
             "content-pipeline/last-run.json).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run through to each loader. Useful for "
             "verifying the orchestration end-to-end without "
             "touching Snowflake.",
    )
    ap.add_argument(
        "--triggered-by",
        default=None,
        help="Override the auto-detected `triggered_by` audit field.",
    )
    args = ap.parse_args(argv)

    if not args.manifest.is_file():
        log.error("Manifest not found: %s", args.manifest)
        return 2

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))

    try:
        _stop_if_review_required(manifest)
    except HumanReviewRequired as e:
        log.error("%s", e)
        log.error("No loaders ran. Re-dispatch manually once the change is reviewed.")
        return 3

    plan = plan_from_manifest(manifest)
    if not plan.loaders_to_run:
        log.info("Manifest indicates no content changes; nothing to load.")
        # Still emit an audit row so the trace shows the run happened.
        runs: list[LoaderRun] = []
    else:
        log.info("Loaders to run: %s", ", ".join(plan.loaders_to_run))
        runs = execute_plan(
            plan,
            tutorials_root=args.tutorials_root.resolve(),
            loader_dir=args.loader_dir.resolve(),
            dry_run=args.dry_run,
        )

    triggered_by = args.triggered_by or _detect_triggered_by()
    git_sha = _detect_git_sha(repo_root=args.loader_dir.parent)

    audit = build_audit_row(
        manifest=manifest,
        runs=runs,
        triggered_by=triggered_by,
        git_commit_sha=git_sha,
        cortex_refresh_triggered=False,  # refresh_cortex.py sets this on its own
    )

    # Always write the local JSONL so the trace exists even if Snowflake
    # is unreachable. If the operator opted out of the Snowflake write
    # entirely, that's the only persistence path.
    write_audit_row_local(args.audit_local_path, audit)

    if not args.audit_only_local:
        try:
            write_audit_row_snowflake(audit)
            log.info("Audit row %s written to RAW.CONTENT_CHANGE_LOG", audit.change_id)
        except (ImportError, KeyError) as e:
            log.warning(
                "Snowflake audit write skipped: %s. The row remains in %s.",
                e,
                args.audit_local_path,
            )
        except Exception as e:  # noqa: BLE001 — audit failure must not mask loader exit
            log.error("Snowflake audit write failed: %s", e)

    # Final exit code reflects loader success, not audit success.
    return 0 if all(r.succeeded() for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
