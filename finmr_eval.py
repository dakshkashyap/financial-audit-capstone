"""
finmr_eval.py — Deterministic evaluation harness for TheFinAI/FinMR.

Replicates the official FinMR metric (ACC / SER / EER / CER) but WITHOUT an
LLM judge — comparison is exact numeric matching, which the official judge
prompt itself specifies ("-1,284" and "-1284" are equal).

Labels per record (same as the official evaluateFinMR.ipynb):
    A  accurate        — extracted AND calculated both match
    S  structural      — our output isn't a valid 2-key object (never happens
                          here since we always emit both keys, but kept for parity)
    E  extraction err  — extracted_value != ground truth
    C  calculation err — extracted OK, calculated_value != ground truth

Also reports diagnostics the official metric doesn't:
    • answerable rate  — fraction where the target fact was actually present
                          (exposes the 32 KB instance-truncation ceiling)
    • per-DQC-rule breakdown

Usage:
    .venv/bin/python3 finmr_eval.py                # all 332
    .venv/bin/python3 finmr_eval.py --n 150        # first 150
    .venv/bin/python3 finmr_eval.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Optional

from datasets import load_dataset

from finmr_parser import parse_record
from finmr_verifier import predict, _to_float

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


# ── scoring one record ────────────────────────────────────────────────────────

def score_record(pred: dict, gt_extracted: str, gt_calculated: str) -> str:
    """Return the FinMR label A/S/E/C for one prediction."""
    # Structural check — we always emit both keys, but verify anyway
    if "extracted_value" not in pred or "calculated_value" not in pred:
        return "S"

    pe = _to_float(pred["extracted_value"])
    ge = _to_float(gt_extracted)
    # Extraction check
    if pe is None or ge is None or abs(pe - ge) > 1e-6:
        return "E"

    pc = _to_float(pred["calculated_value"])
    gc = _to_float(gt_calculated)
    # Calculation check (zero tolerance per official prompt)
    if pc is None or gc is None or abs(pc - gc) > 1e-6:
        return "C"

    return "A"


# ── main evaluation loop ──────────────────────────────────────────────────────

def evaluate(n: Optional[int] = None) -> dict:
    ds = load_dataset("TheFinAI/FinMR", split="test")
    total = len(ds) if n is None else min(n, len(ds))

    labels: List[str] = []
    by_rule: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"A": 0, "S": 0, "E": 0, "C": 0, "n": 0,
                 "answerable": 0, "calc_ok": 0})
    diagnostics = {"no_fact": 0, "no_context": 0, "no_arcs": 0,
                   "missing_children": 0}
    misses: List[dict] = []
    answerable_total = 0     # records where the target fact was present
    answerable_acc = 0       # of those, how many scored A

    for i in range(total):
        row = ds[i]
        rec = parse_record(row)
        pred = predict(rec)
        label = score_record(pred, rec.gt_extracted, rec.gt_calculated)
        labels.append(label)

        rule = rec.dqc_rule
        by_rule[rule]["n"] += 1
        by_rule[rule][label] += 1

        # answerable = target fact was actually found (extraction succeeded)
        if pred["ext_status"] == "ok":
            by_rule[rule]["answerable"] += 1
        if pred["calc_status"] == "ok":
            by_rule[rule]["calc_ok"] += 1

        # diagnostics
        for key in diagnostics:
            if pred["ext_status"] == key or pred["calc_status"].startswith(key):
                diagnostics[key] += 1

        # record misses for inspection
        if label != "A" and len(misses) < 25:
            misses.append({
                "id": rec.record_id, "rule": rule, "label": label,
                "pred_ext": pred["extracted_value"], "gt_ext": rec.gt_extracted,
                "pred_calc": pred["calculated_value"], "gt_calc": rec.gt_calculated,
                "ext_status": pred["ext_status"], "calc_status": pred["calc_status"],
            })

    counts = {L: labels.count(L) for L in "ASEC"}

    def pct(x: int, d: int) -> float:
        return round(100.0 * x / d, 2) if d else 0.0

    result = {
        "total": total,
        "counts": counts,
        "ACC(%)": pct(counts["A"], total),
        "SER(%)": pct(counts["S"], total),
        "EER(%)": pct(counts["E"], total),
        "CER(%)": pct(counts["C"], total),
        "diagnostics": diagnostics,
        "by_rule": {r: dict(v) for r, v in by_rule.items()},
        "misses": misses,
    }
    return result


# ── pretty printer ────────────────────────────────────────────────────────────

def print_results(res: dict) -> None:
    n = res["total"]
    print("\n" + "=" * 64)
    print(f"FinMR Deterministic Evaluation — {n} records")
    print("=" * 64)
    print(f"  ACC (accurate)        : {res['ACC(%)']:5.2f}%   ({res['counts']['A']}/{n})")
    print(f"  EER (extraction err)  : {res['EER(%)']:5.2f}%   ({res['counts']['E']}/{n})")
    print(f"  CER (calculation err) : {res['CER(%)']:5.2f}%   ({res['counts']['C']}/{n})")
    print(f"  SER (structural err)  : {res['SER(%)']:5.2f}%   ({res['counts']['S']}/{n})")

    print("\n  Diagnostics (why extraction/calc failed):")
    for k, v in res["diagnostics"].items():
        print(f"    {k:20s}: {v}")

    print("\n  Per-DQC-rule breakdown:")
    print(f"    {'rule':14s} {'n':>4} {'ACC%':>6} {'answerable%':>12} {'calc_ok%':>9}")
    for rule, v in sorted(res["by_rule"].items()):
        nn = v["n"]
        acc = 100.0 * v["A"] / nn if nn else 0
        ans = 100.0 * v["answerable"] / nn if nn else 0
        cok = 100.0 * v["calc_ok"] / nn if nn else 0
        print(f"    {rule:14s} {nn:>4} {acc:>6.1f} {ans:>12.1f} {cok:>9.1f}")

    print("\n  Sample misses:")
    for m in res["misses"][:12]:
        print(f"    id={m['id']:>4} {m['rule']} [{m['label']}] "
              f"ext {m['pred_ext']}≠{m['gt_ext']} ({m['ext_status']}) | "
              f"calc {m['pred_calc']}≠{m['gt_calc']} ({m['calc_status']})")
    print("=" * 64)

    print("\n  Interpretation:")
    print("    • 'answerable%' = target fact was present in the (truncated) instance.")
    print("      A low value means the 32 KB dataset cap cut off the needed fact,")
    print("      not a failure of the verifier logic.")
    print("    • ACC% is the headline number, directly comparable to the FinMR paper.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None,
                    help="number of records (default: all 332)")
    ap.add_argument("--json", type=str, default=None,
                    help="optional path to write full JSON results")
    args = ap.parse_args()

    res = evaluate(n=args.n)
    print_results(res)

    out_path = args.json or os.path.join(RESULTS_DIR, "finmr_eval.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
