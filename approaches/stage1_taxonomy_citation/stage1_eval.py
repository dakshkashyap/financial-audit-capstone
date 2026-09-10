"""
Stage 1 · Arelle — Evaluation harness.

Measures how much the taxonomy traversal improves FASB citation coverage
over the EDGAR Mapper's static xbrl_concept_map.json baseline.

Reported per split:
  * Taxonomy availability (hit cache vs download vs offline)
  * Before (EDGAR Mapper): valued rows with a citation / total valued rows
  * After  (Stage 1):      valued rows with a citation / total valued rows
  * Upgrade rate           — rows that had NO citation from static map
                              but now have one from the taxonomy
  * Source breakdown       — taxonomy / parent_fallback / static_map / none
  * Per-concept hit analysis (top unmapped concepts after Stage 1)

No API key needed. Purely deterministic.

Usage:
  python stage1_eval.py                             # correct split, n=150
  python stage1_eval.py --split single_error        # error split
  python stage1_eval.py --split all --n 200         # all three splits
  python stage1_eval.py --no-taxonomy --n 150       # edgar_mapper baseline only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Dict, List

pass  # repo root already on sys.path when run with -m

from core.parser import load_correct, load_single_error, load_multi_error
from approaches.stage1_concept_mapping.edgar_mapper import map_statement
from approaches.stage1_taxonomy_citation.stage1_arelle import (
    Stage1Result, enrich_with_taxonomy,
    SOURCE_TAXONOMY, SOURCE_PARENT_FALLBACK, SOURCE_STATIC_MAP, SOURCE_NONE,
)
from core.taxonomy_graph import TaxonomyGraph

from core.paths import RESULTS_DIR   # repo-root results/
LOADERS     = {
    "correct":      load_correct,
    "single_error": load_single_error,
    "multi_error":  load_multi_error,
}


# ── per-split evaluation ──────────────────────────────────────────────────────

def eval_split(
    items: List[dict],
    split_name: str,
    graph: TaxonomyGraph,
) -> dict:
    total_valued   = 0
    before_cited   = 0   # rows with a citation from edgar_mapper alone
    after_cited    = 0   # rows with a citation after Stage 1

    source_counter = Counter()
    upgraded_total = 0
    unmapped_total = 0

    concept_no_hit: Counter = Counter()   # concepts that had no taxonomy match

    samples: List[dict] = []

    for item in items:
        # ── edgar_mapper baseline (before Stage 1) ──
        mapped_before = map_statement(item)
        for row in mapped_before.rows:
            if row.value is not None:
                total_valued  += 1
                if row.asc_primary:
                    before_cited += 1

        # ── Stage 1 enrichment ──
        result: Stage1Result = enrich_with_taxonomy(
            map_statement(item),   # fresh copy so we can compare
            graph,
        )
        ms = result.statement

        upgraded_total += result.n_upgraded
        unmapped_total += result.n_unmapped

        for row in ms.rows:
            if row.value is None:
                continue
            src = result.citation_sources.get(row.row_idx, SOURCE_NONE)
            source_counter[src] += 1
            if src != SOURCE_NONE:
                after_cited += 1
            # Track concepts that remained unresolved even after Stage 1
            if src == SOURCE_NONE and row.concept:
                concept_no_hit[row.concept.replace("us-gaap:", "")] += 1

        if len(samples) < 5:
            sample_rows = []
            for row in ms.rows:
                if row.value is not None:
                    sample_rows.append({
                        "row_idx":   row.row_idx,
                        "label":     row.label[:50],
                        "concept":   row.concept,
                        "asc_primary": row.asc_primary,
                        "source":    result.citation_sources.get(row.row_idx, SOURCE_NONE),
                        "mapped":    row.mapped,
                    })
            samples.append({
                "company":        ms.company,
                "statement_type": ms.statement_type,
                "period":         ms.period,
                "rows":           sample_rows,
            })

    n = len(items)
    before_cov = before_cited / total_valued if total_valued else 0.0
    after_cov  = after_cited  / total_valued if total_valued else 0.0
    upgrade_rt = upgraded_total / total_valued if total_valued else 0.0

    top_no_hit = [
        {"concept": c, "count": cnt}
        for c, cnt in concept_no_hit.most_common(20)
    ]

    return {
        "split":             split_name,
        "n_items":           n,
        "total_valued_rows": total_valued,
        "taxonomy_available": graph.available,
        "before_stage1": {
            "cited_rows":    before_cited,
            "coverage":      round(before_cov, 4),
        },
        "after_stage1": {
            "cited_rows":    after_cited,
            "coverage":      round(after_cov, 4),
            "upgraded_rows": upgraded_total,
            "upgrade_rate":  round(upgrade_rt, 4),
        },
        "source_breakdown":    dict(source_counter),
        "unmapped_rows":       unmapped_total,
        "top_concepts_no_hit": top_no_hit,
        "samples":             samples,
    }


# ── pretty print ──────────────────────────────────────────────────────────────

def print_results(all_results: dict) -> None:
    def _bar(v: float, width: int = 30) -> str:
        filled = int(v * width)
        return "█" * filled + "░" * (width - filled)

    for split, r in all_results.items():
        print(f"\n{'='*65}")
        print(f" Stage 1 · Arelle — {split.upper()} (n={r['n_items']})")
        print(f"{'='*65}")

        tax = "✓ available" if r["taxonomy_available"] else "✗ offline (static-map fallback)"
        print(f"\n  Taxonomy:     {tax}")
        print(f"  Valued rows:  {r['total_valued_rows']}")

        b = r["before_stage1"]
        a = r["after_stage1"]
        print(f"\n  Citation coverage:")
        print(f"    Before (EDGAR Mapper): {b['coverage']:.1%}  "
              f"{_bar(b['coverage'])}  ({b['cited_rows']} rows)")
        print(f"    After  (Stage 1):      {a['coverage']:.1%}  "
              f"{_bar(a['coverage'])}  ({a['cited_rows']} rows)")
        delta = a["coverage"] - b["coverage"]
        sign  = "+" if delta >= 0 else ""
        print(f"    Δ improvement:         {sign}{delta:.1%}")
        print(f"    Upgraded rows:         {a['upgraded_rows']}  "
              f"(had no citation → now have one)")

        print(f"\n  Citation source breakdown:")
        total_s = sum(r["source_breakdown"].values()) or 1
        order   = [SOURCE_TAXONOMY, SOURCE_PARENT_FALLBACK, SOURCE_STATIC_MAP, SOURCE_NONE]
        for src in order:
            cnt = r["source_breakdown"].get(src, 0)
            pct = cnt / total_s
            print(f"    {src:22s}: {cnt:5d}  ({pct:.1%})  {_bar(pct, 20)}")

        print(f"\n  Unmapped rows (no concept from EDGAR Mapper): {r['unmapped_rows']}")

        if r["top_concepts_no_hit"]:
            print(f"\n  Top concepts with no taxonomy hit (Stage 1 backlog):")
            for i, entry in enumerate(r["top_concepts_no_hit"][:10], 1):
                print(f"    {i:2d}. {entry['count']:3d}x  {entry['concept']}")

        if r["samples"]:
            s = r["samples"][0]
            print(f"\n  Sample item: {s['company']} | {s['statement_type']} | {s['period']}")
            print(f"  {'idx':>3}  {'label':42s}  {'concept':35s}  {'ASC':18s}  source")
            print(f"  {'---':>3}  {'-'*42}  {'-'*35}  {'-'*18}  ------")
            for row in s["rows"][:8]:
                concept = (row["concept"] or "").replace("us-gaap:", "")[:33]
                asc     = row["asc_primary"] or ""
                src     = row["source"]
                print(f"  {row['row_idx']:3d}  {row['label'][:42]:42s}  "
                      f"{concept:35s}  {asc:18s}  {src}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate Stage 1 Arelle citation enrichment on AuditBench.")
    ap.add_argument("--split", choices=list(LOADERS) + ["all"], default="correct",
                    help="Which split to evaluate (default: correct)")
    ap.add_argument("--n",    type=int, default=150,
                    help="Samples per split (default: 150)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-taxonomy", action="store_true",
                    help="Skip taxonomy download; report edgar_mapper baseline only")
    ap.add_argument("--out", default=None,
                    help="Output JSON path (default: results/stage1_eval.json)")
    args = ap.parse_args()

    # Load taxonomy once (triggers download or cache read)
    graph = TaxonomyGraph()
    if not args.no_taxonomy:
        _ = graph.available   # trigger load now so the print appears before the progress bar
    else:
        graph._xml_content = ""   # force offline mode
        graph._available   = False

    splits_to_run = list(LOADERS) if args.split == "all" else [args.split]
    print(f"\nLoading {splits_to_run} (seed={args.seed}, n={args.n}) …")

    all_results: dict = {}
    for split_name in splits_to_run:
        items = LOADERS[split_name](seed=args.seed, n=args.n)
        print(f"  {split_name}: {len(items)} items  — running Stage 1…")
        all_results[split_name] = eval_split(items, split_name, graph)

    print_results(all_results)

    out_path = args.out or os.path.join(RESULTS_DIR, "stage1_eval.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {"seed": args.seed, "n": args.n,
             "taxonomy_available": graph.available,
             "splits": all_results},
            f, indent=2,
        )
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
