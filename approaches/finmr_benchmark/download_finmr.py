"""
download_finmr.py — fetch the FinMR benchmark (FinAuditing paper) from HuggingFace
and write it to data/finmr/ in both parquet (raw) and a normalized JSON form.

FinMR = the Mathematical-Reasoning task of FinAuditing (arXiv:2510.08886):
332 test items built from real XBRL filings + official DQC error checks.
Each item: a long auditor prompt (schema/presentation/calculation/definition/
label/instance + US-GAAP taxonomy context) and a ground-truth answer
{extracted_value, calculated_value}. This is also the dataset AuditFlow
(arXiv:2606.03031) evaluates on (a 67-instance subset of it).

Usage:
    python download_finmr.py            # downloads + writes data/finmr/
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter

import sys

from datasets import load_dataset

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

from core.paths import DATA_DIR

OUT_DIR = os.path.join(DATA_DIR, "finmr")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Downloading TheFinAI/FinMR (332 rows, ~5 MB)…")
    ds = load_dataset("TheFinAI/FinMR", split="test")

    # Raw parquet copy for reproducibility
    pq_path = os.path.join(OUT_DIR, "finmr_test.parquet")
    ds.to_parquet(pq_path)
    print(f"  wrote {pq_path}")

    # Normalized JSON: parse the answer field and pull light metadata out of
    # the query so downstream code doesn't have to re-scan 100k-char prompts.
    items, dqc_counts, qlens = [], Counter(), []
    for rec in ds:
        q = rec["query"]
        qlens.append(len(q))
        dqc_counts[rec["dqc_id"]] += 1

        ans = rec["answer"]
        if isinstance(ans, str):
            try:
                ans = json.loads(ans)
            except json.JSONDecodeError:
                ans = {"raw": ans}

        # Best-effort metadata extraction (concept + period often named in the query)
        concept = None
        m = re.search(r"us-gaap[:_][A-Za-z0-9]+", q)
        if m:
            concept = m.group(0)

        items.append({
            "id": rec["id"],
            "dqc_id": rec["dqc_id"],
            "query_chars": len(q),
            "concept_hint": concept,
            "answer": ans,
            # full query stays in the parquet; keep JSON light
            "query_head": q[:600],
        })

    json_path = os.path.join(OUT_DIR, "finmr_test_index.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    print(f"  wrote {json_path}")

    print("\n-- FinMR exploration --")
    print(f"  items:            {len(items)}")
    print(f"  DQC rule families: {dict(dqc_counts)}")
    print(f"  query length:     min {min(qlens):,} / median {sorted(qlens)[len(qlens)//2]:,} / max {max(qlens):,} chars")
    n_concept = sum(1 for it in items if it["concept_hint"])
    print(f"  items with a us-gaap concept in query: {n_concept}/{len(items)}")
    sample = items[0]
    print(f"\n  sample answer format: {sample['answer']}")
    print(f"  sample query head:\n    {sample['query_head'][:300]}…")


if __name__ == "__main__":
    main()
