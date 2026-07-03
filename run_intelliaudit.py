"""
run_intelliaudit.py — run the FULL IntelliAudit pipeline and emit AuditBench-format
predictions (so evaluate.py scores it head-to-head against the LLM-alone baseline).

Per item:
  Stage 0 fires (deterministic proof)  → build the verdict from the gate (NO LLM):
        judgment=Incorrect, type/row/correct-value from the finding, citation from
        Stage 1's grounded pick, corrected table via a tiny deterministic reviser.
  Stage 0 abstains                      → call Stage 2 (focused, evidence-grounded
        LLM) with the verified-consistent flag + per-row candidate citations.

Writes results/intelliaudit_<split>_predictions.json (resumable). The model id
matches the baseline run, so the comparison isolates ARCHITECTURE, not model.

Usage (PowerShell):
  $env:ANTHROPIC_API_KEY="sk-ant-..."
  python run_intelliaudit.py --split correct --n 150          # over-auditing test
  python run_intelliaudit.py --split single_error --n 150
  python run_intelliaudit.py --split all --n 50               # cheaper sample
  python run_intelliaudit.py --eval                            # score + compare
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

from parser import load_correct, load_single_error, load_multi_error
from pipeline import run_pipeline
from stage1_arelle import run_stage1
from taxonomy_graph import TaxonomyGraph
from runner import _meta, _table_hash, _safe_name
import stage2_llm
from tqdm import tqdm

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
LOADERS = {"correct": load_correct, "single_error": load_single_error,
           "multi_error": load_multi_error}
MODEL = "claude-opus-4-6"


# ── tiny deterministic reviser (Stage 3 stub) ─────────────────────────────────
def _revise(table: str, record) -> str:
    """Apply the gate's fix to the table string when it's a clean substitution.
    Numerical Error → swap the stated value for the correct one; otherwise return
    the table unchanged (full structural revision is Stage 3's job)."""
    if (record.error_type == "Numerical Error" and record.stated_value is not None
            and record.correct_value is not None):
        import re
        def fmt(v):
            return str(int(v)) if abs(v - round(v)) < 1e-6 else str(v)
        # replace the first occurrence of the stated number (comma-formatted too)
        for cand in (f"{int(record.stated_value):,}", fmt(record.stated_value),
                     str(record.stated_value)):
            if cand and cand in table:
                return table.replace(cand, fmt(record.correct_value), 1)
    return table


def _deterministic_parsed(item: dict, record) -> dict:
    parsed = {"General Judgment": "Incorrect",
              "Information for error 1": {
                  "Error Identification": {
                      "Error Type": record.error_type,
                      "Problematic Entry": f"Row {record.problematic_entry}"},
                  "Error Resolution": record.detail or "",
                  "Standards Citation": f"ASC {record.citation_primary}"
                                        if record.citation_primary else ""},
              "Corrected Statements": _revise(item["table"], record)}
    return parsed


def run_split(split: str, graph: TaxonomyGraph, n: int, seed: int) -> dict:
    items = LOADERS[split](seed=seed, n=n)
    out_path = os.path.join(RESULTS_DIR, f"intelliaudit_{split}_predictions.json")

    existing = {}
    if os.path.exists(out_path):
        for rec in json.load(open(out_path, encoding="utf-8")):
            existing[rec["item_idx"]] = rec
        print(f"  resuming: {len(existing)} records in {os.path.basename(out_path)}")

    records, n_det, n_llm, n_err = [], 0, 0, 0
    for idx, item in enumerate(tqdm(items, desc=f"intelliaudit/{split}", unit="smpl")):
        prev = existing.get(idx)
        if prev is not None and prev.get("error") is None and \
           prev.get("table_hash") == _table_hash(item):
            records.append(prev)
            n_det += int(prev.get("route") == "deterministic")
            n_llm += int(str(prev.get("route", "")).startswith("llm"))
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            continue

        record = run_pipeline(item, graph)
        if not record.abstained:
            parsed = _deterministic_parsed(item, record)
            raw = json.dumps(parsed)
            route, err = "deterministic", None
            n_det += 1
        else:
            statement = run_stage1(item, graph).statement
            r = stage2_llm.audit_item(item, record, statement, model=MODEL)
            parsed, raw, err = r["parsed"], r["raw_text"], r["error"]
            route = "llm"
            n_llm += 1
            if err:
                n_err += 1
            # Deterministic veto: when the engine has VERIFIED the table consistent,
            # the arithmetic is provably clean — override an LLM "Incorrect" that
            # rests on a (non-existent) numerical/missing error. Sound on truly
            # clean tables; documented to cost a little recall on the ~13% of error
            # tables whose error leaves no arithmetic trace.
            if (parsed and record.verified_consistent and
                    str(parsed.get("General Judgment", "")).strip().lower() == "incorrect"):
                parsed = {"General Judgment": "Correct",
                          "Corrected Statements": item["table"]}
                route = "llm+veto"

        records.append({"item_idx": idx, "table_hash": _table_hash(item),
                        "model_used": MODEL, "route": route, "raw_text": raw,
                        "parsed": parsed, "error": err, "item_meta": _meta(item)})
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    print(f"  {split}: {len(records)} items  | deterministic {n_det}  | LLM {n_llm}"
          + (f"  | LLM errors {n_err}" if n_err else ""))
    return {"n": len(records), "deterministic": n_det, "llm": n_llm, "llm_errors": n_err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=list(LOADERS) + ["all"], default="all")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval", action="store_true",
                    help="Score the IntelliAudit predictions (and the baseline) and compare.")
    args = ap.parse_args()

    if args.eval:
        from evaluate import evaluate_file, print_comparison_table
        all_avg = {}
        for fn in sorted(os.listdir(RESULTS_DIR)):
            if fn.startswith(("intelliaudit_", f"{_safe_name(MODEL)}_")) and \
               fn.endswith("_predictions.json"):
                all_avg[fn[:-len("_predictions.json")]] = evaluate_file(
                    os.path.join(RESULTS_DIR, fn))
        print_comparison_table(all_avg)
        return

    graph = TaxonomyGraph(); _ = graph.available
    splits = list(LOADERS) if args.split == "all" else [args.split]
    print(f"\nIntelliAudit full pipeline (model={MODEL}, seed={args.seed}, n={args.n})")
    print(f"splits: {splits}\n")
    stats = {}
    for s in splits:
        stats[s] = run_split(s, graph, args.n, args.seed)
    print("\nRoute summary:", json.dumps(stats, indent=2))
    print("\nNow score + compare:  python run_intelliaudit.py --eval")


if __name__ == "__main__":
    main()
