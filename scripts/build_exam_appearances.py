#!/usr/bin/env python3
"""Build corpus/exam_appearances.json from the source tutorial frontmatter.

The engine image ships only strand summaries, not full tutorials, so the
curated ``exam_appearances`` can't be read at runtime. This extracts them into
one compact JSON (slug -> [appearance]) that IS shipped (under corpus/) and
loaded by api/orchestrator/exam_refs.py.

Run from the engine repo root, pointing at the source corpus:

    python scripts/build_exam_appearances.py \
        --src ../career-transition-2026/tutorials \
        --out corpus/exam_appearances.json
"""
from __future__ import annotations

import argparse
import glob
import json
import re

import yaml


def build(src: str) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for path in glob.glob(f"{src}/LCHL_*/*.md"):
        if "/_" in path:
            continue
        txt = open(path, encoding="utf-8", errors="ignore").read()
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", txt, re.S)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1))
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        slug, apps = fm.get("slug"), fm.get("exam_appearances")
        if not slug or not isinstance(apps, list):
            continue
        clean = []
        for a in apps:
            if not isinstance(a, dict):
                continue
            try:
                year, paper, marks = int(a["year"]), int(a["paper"]), int(a.get("marks", 0))
            except Exception:
                continue
            if not (2000 <= year <= 2099 and 1 <= paper <= 3 and 0 <= marks <= 100):
                continue
            clean.append(
                {
                    "year": year,
                    "paper": paper,
                    "question": str(a.get("question", "")),
                    "level": str(a.get("level", "LCHL")),
                    "marks": marks,
                    "note": a.get("note") or None,
                }
            )
        if clean:
            idx[slug] = clean
    return idx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../career-transition-2026/tutorials")
    ap.add_argument("--out", default="corpus/exam_appearances.json")
    args = ap.parse_args()
    idx = build(args.src)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=0)
    total = sum(len(v) for v in idx.values())
    print(f"wrote {args.out}: {len(idx)} tutorials, {total} appearances")


if __name__ == "__main__":
    main()
