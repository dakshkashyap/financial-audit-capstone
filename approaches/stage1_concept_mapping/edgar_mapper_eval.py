"""
EDGAR Mapper — Evaluation harness.

Runs map_statement() over a sample of AuditBench items and reports:
  * Overall coverage (% valued rows that got a concept)
  * Per-statement-type coverage
  * Per-strategy breakdown (exact / stem_exact / fuzzy / none)
  * Top unmapped normalized labels (your backlog for the concept map)
  * Ticker lookup success rate
  * Period parse success rate
  * Sample mapped rows for inspection

No API key needed. Purely deterministic.

Usage:
  python edgar_mapper_eval.py                         # correct split, n=150
  python edgar_mapper_eval.py --split single_error    # error split
  python edgar_mapper_eval.py --split all --n 200     # all splits
  python edgar_mapper_eval.py --n 1484 --split single_error  # full set
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
from approaches.stage1_concept_mapping.edgar_mapper import map_statement, MappedStatement

from core.paths import RESULTS_DIR   # repo-root results/
LOADERS = {
    "correct":      load_correct,
    "single_error": load_single_error,
    "multi_error":  load_multi_error,
}


# ── per-split evaluation ──────────────────────────────────────────────────────
def eval_split(items: List[dict], split_name: str) -> dict:
    total_valued     = 0
    total_mapped     = 0
    strategy_counter = Counter()
    stype_stats: Dict[str, dict] = defaultdict(
        lambda: {"n": 0, "valued": 0, "mapped": 0})
    unmapped_labels  = Counter()
    ticker_hits      = 0
    period_hits      = 0
    samples          = []

    for item in items:
        ms: MappedStatement = map_statement(item)

        total_valued += ms.n_valued_rows
        total_mapped += ms.n_mapped
        if ms.ticker:
            ticker_hits += 1
        if ms.period:
            period_hits += 1

        st = ms.statement_type
        stype_stats[st]["n"] += 1
        stype_stats[st]["valued"] += ms.n_valued_rows
        stype_stats[st]["mapped"] += ms.n_mapped

        for row in ms.rows:
            if row.value is None:
                continue
            strategy_counter[row.strategy] += 1
            if not row.mapped:
                unmapped_labels[row.norm] += 1

        # Keep first 5 samples for inspection
        if len(samples) < 5:
            sample_rows = []
            for r in ms.rows:
                if r.value is not None:
                    sample_rows.append({
                        "row_idx": r.row_idx,
                        "label": r.label[:50],
                        "concept": r.concept,
                        "asc_primary": r.asc_primary,
                        "strategy": r.strategy,
                        "confidence": r.confidence,
                        "mapped": r.mapped,
                    })
            samples.append({
                "company": ms.company,
                "ticker": ms.ticker,
                "statement_type": ms.statement_type,
                "period": ms.period,
                "coverage": round(ms.coverage, 4),
                "rows": sample_rows,
            })

    n = len(items)
    coverage = total_mapped / total_valued if total_valued else 0.0

    stype_summary = {}
    for st, stat in stype_stats.items():
        cov = stat["mapped"] / stat["valued"] if stat["valued"] else 0.0
        stype_summary[st] = {
            "n_items": stat["n"],
            "valued_rows": stat["valued"],
            "mapped_rows": stat["mapped"],
            "coverage": round(cov, 4),
        }

    top_unmapped = [
        {"label": lbl, "count": cnt}
        for lbl, cnt in unmapped_labels.most_common(25)
    ]

    return {
        "split": split_name,
        "n_items": n,
        "total_valued_rows": total_valued,
        "total_mapped_rows": total_mapped,
        "coverage": round(coverage, 4),
        "ticker_lookup_rate": round(ticker_hits / n, 4) if n else 0.0,
        "period_parse_rate": round(period_hits / n, 4) if n else 0.0,
        "strategy_breakdown": dict(strategy_counter),
        "by_statement_type": stype_summary,
        "top_unmapped_labels": top_unmapped,
        "samples": samples,
    }


# ── pretty print ─────────────────────────────────────────────────────────────
def print_results(results: dict) -> None:
    def _bar(v: float, width: int = 30) -> str:
        filled = int(v * width)
        return "█" * filled + "░" * (width - filled)

    for split, r in results.items():
        print(f"\n{'='*60}")
        print(f" EDGAR Mapper — {split.upper()} (n={r['n_items']})")
        print(f"{'='*60}")

        cov = r["coverage"]
        print(f"\n  Overall Coverage:    {cov:.1%}  {_bar(cov)}")
        print(f"  Valued rows:         {r['total_valued_rows']}")
        print(f"  Mapped rows:         {r['total_mapped_rows']}")
        print(f"  Ticker lookup rate:  {r['ticker_lookup_rate']:.1%}")
        print(f"  Period parse rate:   {r['period_parse_rate']:.1%}")

        print(f"\n  Strategy breakdown:")
        total_s = sum(r["strategy_breakdown"].values()) or 1
        for strat, cnt in sorted(r["strategy_breakdown"].items(),
                                  key=lambda x: -x[1]):
            pct = cnt / total_s
            print(f"    {strat:12s}: {cnt:5d}  ({pct:.1%})  {_bar(pct, 20)}")

        print(f"\n  Coverage by statement type:")
        for stype, stat in sorted(r["by_statement_type"].items()):
            c = stat["coverage"]
            print(f"    {stype:20s}: {c:.1%}  "
                  f"({stat['mapped_rows']}/{stat['valued_rows']} rows, "
                  f"{stat['n_items']} items)  {_bar(c, 20)}")

        print(f"\n  Top unmapped labels (concept map backlog):")
        for i, entry in enumerate(r["top_unmapped_labels"][:15], 1):
            print(f"    {i:2d}. {entry['count']:4d}x  {entry['label']}")

        print(f"\n  Sample item:")
        if r["samples"]:
            s = r["samples"][0]
            print(f"    {s['company']} ({s['ticker']}) | {s['statement_type']} | {s['period']}")
            print(f"    Coverage: {s['coverage']:.1%}")
            print(f"    {'idx':>3}  {'label':42s}  {'concept':50s}  {'ASC':15s}  strat")
            print(f"    {'---':>3}  {'-'*42}  {'-'*50}  {'-'*15}  -----")
            for row in s["rows"][:8]:
                concept = row["concept"] or "[unmapped]"
                asc     = row["asc_primary"] or ""
                strat   = row["strategy"]
                print(f"    {row['row_idx']:3d}  {row['label']:42s}  {concept:50s}  {asc:15s}  {strat}")


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate EDGAR mapper coverage on AuditBench splits.")
    ap.add_argument("--split", choices=list(LOADERS) + ["all"], default="correct",
                    help="Which split to evaluate (default: correct)")
    ap.add_argument("--n", type=int, default=150,
                    help="Samples per split (default: 150)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None,
                    help="Output JSON path (default: results/edgar_mapper_eval.json)")
    args = ap.parse_args()

    splits_to_run = list(LOADERS) if args.split == "all" else [args.split]
    print(f"Loading {splits_to_run} (seed={args.seed}, n={args.n}) …")

    all_results: dict = {}
    for split_name in splits_to_run:
        items = LOADERS[split_name](seed=args.seed, n=args.n)
        print(f"  {split_name}: {len(items)} items")
        all_results[split_name] = eval_split(items, split_name)

    print_results(all_results)

    # Write JSON
    out_path = args.out or os.path.join(RESULTS_DIR, "edgar_mapper_eval.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"seed": args.seed, "n": args.n, "splits": all_results},
                  f, indent=2)
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
