#!/usr/bin/env python3
"""build_local_index.py — offline, idempotent LanceDB index builder.

Snowflake-exit Phase 1 (AGENT_29). Walks the LCHL tutorial corpus, embeds each
chunk with a LOCAL model (no API key, no network beyond a one-time model
download), and writes a LanceDB vector store under ``local_index/``. The store
is the candidate replacement for the Cortex ``TUTOR_SEARCH`` service, built and
measured entirely OFFLINE — never wired into the live app (that's Phase 2,
post-freeze).

Spike embedding model: BAAI/bge-small-en-v1.5 (384-dim, L2-normalised), via
fastembed. The PRODUCTION embedding choice (hosted vs local) is a separate
Phase-3 decision (docs/SNOWFLAKE_EXIT_PLAN.md §3) — this is the spike model
only and is swappable via --model.

Parity with Cortex: corpus parsing is REUSED verbatim from
snowflake/load_tutorials.py (same slug set, same title_plus_phrasings / body
construction, same skip rules), and the two searchable text columns
(title_plus_phrasings, body) are embedded independently — mirroring the
multi-field TUTOR_SEARCH index (create_tutor_search_service.sql).

Idempotent: a rerun overwrites the table cleanly and is deterministic given the
same corpus + model.

Usage
-----
    python scripts/build_local_index.py                 # full build, defaults
    python scripts/build_local_index.py --limit 50      # fast smoke build
    python scripts/build_local_index.py --model BAAI/bge-small-en-v1.5 --out local_index
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make the repo root importable so `local_retrieval` resolves when this script
# is run directly (python scripts/build_local_index.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from local_retrieval.bm25_index import build_bm25_index  # noqa: E402
from local_retrieval.corpus import DEFAULT_CORPUS_ROOT, load_tutorial_rows  # noqa: E402
from local_retrieval.embedding import DEFAULT_MODEL, embed_texts  # noqa: E402
from local_retrieval.store import TUTOR_TABLE, write_tutor_table  # noqa: E402


def _dir_size_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}TB"


def build(
    corpus_root: Path,
    out_dir: Path,
    model_name: str,
    limit: int | None,
    with_bm25: bool = False,
) -> dict:
    """Walk → embed → write. Returns a summary dict for the caller / delivery note."""
    t0 = time.perf_counter()

    print(f"[1/3] Walking corpus under {corpus_root} (reusing load_tutorials parser)…")
    rows, walk_summary = load_tutorial_rows(corpus_root)
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        raise SystemExit(
            f"No tutorial rows found under {corpus_root}. "
            f"Walk summary: {walk_summary}"
        )
    print(
        f"      walked={walk_summary['walked']} parsed={walk_summary['parsed']} "
        f"skipped(summary={walk_summary['skipped_summary']}, "
        f"readme={walk_summary['skipped_readme']}, "
        f"out_of_schema={walk_summary['skipped_out_of_schema']}) "
        f"parse_errors={walk_summary['parse_errors']}"
    )
    print(f"      indexing {len(rows)} chunk(s)"
          + (f" (--limit {limit})" if limit is not None else ""))

    # Mirror Cortex: embed title_plus_phrasings and body INDEPENDENTLY.
    # bge-small-en-v1.5 truncates inputs at 512 tokens (~2000 chars), so text
    # beyond that never reaches the embedding regardless. We pre-truncate the
    # body *for embedding only* — a no-op for the resulting vector but a big
    # speed/memory win on 4–6 kB transcript bodies. The FULL body is still
    # stored in the table (raw text) so a downstream reranker (AGENT_30) sees
    # everything.
    embed_char_cap = 2000
    phrasings = [str(r.get("title_plus_phrasings") or r.get("title") or "") for r in rows]
    bodies = [str(r.get("body") or "")[:embed_char_cap] for r in rows]

    print(f"[2/3] Embedding {len(rows)} chunk(s) x2 fields with {model_name} (offline)…")
    vec_phrasings = embed_texts(phrasings, model_name=model_name)
    vec_body = embed_texts(bodies, model_name=model_name)

    records = []
    for r, vp, vb in zip(rows, vec_phrasings, vec_body):
        records.append(
            {
                "slug": str(r.get("slug") or ""),
                "title": str(r.get("title") or ""),
                "topic": str(r.get("topic") or ""),
                "subtopic": str(r.get("subtopic") or ""),
                "title_plus_phrasings": str(r.get("title_plus_phrasings") or ""),
                "body": str(r.get("body") or ""),
                "vec_phrasings": vp.tolist(),
                "vec_body": vb.tolist(),
            }
        )

    print(f"[3/3] Writing LanceDB table '{TUTOR_TABLE}' under {out_dir} (overwrite)…")
    write_tutor_table(out_dir, records)

    bm25_summary: dict | None = None
    if with_bm25:
        print(f"[+]   Building BM25 lexical index under {out_dir}/bm25 (offline)…")
        bm25_summary = build_bm25_index(out_dir, rows)
        print(f"      BM25 indexed {bm25_summary['bm25_docs']} doc(s)")

    elapsed = time.perf_counter() - t0
    size_bytes = _dir_size_bytes(Path(out_dir))
    summary = {
        "chunks": len(records),
        "model": model_name,
        "out_dir": str(out_dir),
        "build_seconds": round(elapsed, 2),
        "index_bytes": size_bytes,
        "index_human": _human_bytes(size_bytes),
        "walk": walk_summary,
        "bm25": bm25_summary,
    }
    print(
        f"\nDONE: {summary['chunks']} chunks → {summary['out_dir']}/{TUTOR_TABLE} "
        f"in {summary['build_seconds']}s · index size {summary['index_human']}"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument(
        "--corpus-root",
        type=Path,
        default=DEFAULT_CORPUS_ROOT,
        help="Path to the tutorials/ directory (LCHL_*/ strand folders). "
             f"Default: {DEFAULT_CORPUS_ROOT}",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=_REPO_ROOT / "local_index",
        help="LanceDB database directory. Default: <repo>/local_index",
    )
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Local embedding model (fastembed). Default: {DEFAULT_MODEL}",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Index only the first N chunks (fast smoke build).",
    )
    ap.add_argument(
        "--with-bm25",
        action="store_true",
        help="Also build a BM25 lexical index under <out>/bm25 over the same "
             "chunks (for the hybrid retriever).",
    )
    args = ap.parse_args(argv)

    build(
        corpus_root=args.corpus_root.resolve(),
        out_dir=args.out.resolve(),
        model_name=args.model,
        limit=args.limit,
        with_bm25=args.with_bm25,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
