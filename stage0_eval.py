"""
Stage 0 — Evaluation harness for the deterministic gate (Stage 0A + 0B).

Measures how well the *free, deterministic* stages localize and classify errors
on AuditBench, with no LLM involved. This is the evidence for the IntelliAudit
claim that arithmetic + equation checks alone recover most of the Error Row /
Error Type signal (Vault target: Error Row EM 0.737 -> ~0.92 on covered cases)
while barely touching clean statements (the over-auditing concern in todo.md).

Reported per split:
  * coverage           — fraction of items the gate fired on (non-abstain)
  * Error Row EM       — overall and among fired items
  * Error Type EM      — overall and among fired items
  * success            — fired AND type EM AND row EM
  * correct-value acc  — Numerical/Missing: computed value == ground truth
  * per-error-type breakdown (shows the 0A vs 0B division of labor)
  * correct split      — false-positive rate (gate should rarely fire)

Usage (PowerShell):
  python stage0_eval.py                       # single_error + correct, n=150
  python stage0_eval.py --split single_error --n 1484
  python stage0_eval.py --split all --n 150
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Optional

from parser import load_correct, load_multi_error, load_single_error
from metrics import _norm_type, _row_int

import stage0a
import stage0b
from stage0_common import (Finding, approx_eq, build_table, build_transactions,
                           combine_findings, rows_of)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

LOADERS = {
    "single_error": load_single_error,
    "multi_error": load_multi_error,
    "correct": load_correct,
}

ARITHMETIC_TYPES = {"numerical error", "missing row"}


# ── run the gate on one item ──────────────────────────────────────────────────
def run_gate(item: dict) -> Optional[Finding]:
    a = stage0a.verify(item)
    b = stage0b.check(item)
    return combine_findings(a, b)


def _gt_value_for(item: dict, finding: Finding) -> Optional[float]:
    """Look up the ground-truth correct value in gt_table for a Numerical/Missing
    finding (by matching the implicated row's label)."""
    if finding.error_type is None:
        return None
    gt_df = build_table(item.get("gt_table", "") or "")
    # the modified-table label at the implicated row (Numerical) or the missing
    # row's label carried in the finding detail isn't structured, so re-derive:
    if _norm_type(finding.error_type) == "numerical error":
        mod_df = build_table(item["table"])
        target = None
        for r in rows_of(mod_df):
            if r.idx == finding.problematic_entry:
                target = r.core
                break
        if target is None:
            return None
        for r in rows_of(gt_df):
            if r.core == target and r.value is not None:
                return r.value
    elif _norm_type(finding.error_type) == "missing row":
        # match the missing value directly against gt_table
        for r in rows_of(gt_df):
            if r.value is not None and approx_eq(r.value, finding.correct_value):
                return r.value
    return None


# ── single-error / clean evaluation ───────────────────────────────────────────
def eval_single(items: List[dict]) -> dict:
    n = len(items)
    fired = row_hits = type_hits = success = 0
    cv_total = cv_hits = 0
    per_type: Dict[str, dict] = defaultdict(
        lambda: {"n": 0, "fired": 0, "type_em": 0, "row_em": 0})
    confusion = defaultdict(int)
    samples = []

    for it in items:
        gt = it["errors"][0]
        gt_type = _norm_type(gt["error_type"])
        gt_row = _row_int(gt["problematic_entry"])
        bucket = per_type[gt_type]
        bucket["n"] += 1

        f = run_gate(it)
        did_fire = f is not None and f.error_type is not None
        type_ok = did_fire and _norm_type(f.error_type) == gt_type
        row_ok = did_fire and _row_int(f.problematic_entry) == gt_row

        fired += int(did_fire)
        row_hits += int(row_ok)
        type_hits += int(type_ok)
        success += int(type_ok and row_ok)
        bucket["fired"] += int(did_fire)
        bucket["type_em"] += int(type_ok)
        bucket["row_em"] += int(row_ok)
        confusion[(gt_type, _norm_type(f.error_type) if did_fire else "abstain")] += 1

        if did_fire and _norm_type(f.error_type) in ARITHMETIC_TYPES and row_ok:
            cv_total += 1
            cv_hits += int(approx_eq(f.correct_value, _gt_value_for(it, f)))

        if len(samples) < 8:
            samples.append({
                "gt_type": gt_type, "gt_row": gt_row,
                "pred_type": _norm_type(f.error_type) if did_fire else None,
                "pred_row": _row_int(f.problematic_entry) if did_fire else None,
                "pred_correct_value": f.correct_value if did_fire else None,
                "detail": f.detail if did_fire else "abstain",
            })

    return {
        "n": n,
        "coverage": round(fired / n, 4) if n else 0.0,
        "error_row_em": round(row_hits / n, 4) if n else 0.0,
        "error_type_em": round(type_hits / n, 4) if n else 0.0,
        "error_row_em_fired": round(row_hits / fired, 4) if fired else 0.0,
        "error_type_em_fired": round(type_hits / fired, 4) if fired else 0.0,
        "success_rate": round(success / n, 4) if n else 0.0,
        "correct_value_acc": round(cv_hits / cv_total, 4) if cv_total else None,
        "correct_value_n": cv_total,
        "per_type": {k: {
            "n": v["n"],
            "coverage": round(v["fired"] / v["n"], 4) if v["n"] else 0.0,
            "type_em": round(v["type_em"] / v["n"], 4) if v["n"] else 0.0,
            "row_em": round(v["row_em"] / v["n"], 4) if v["n"] else 0.0,
        } for k, v in sorted(per_type.items())},
        "confusion": {f"{g} -> {p}": c for (g, p), c in sorted(confusion.items())},
        "samples": samples,
    }


def eval_correct(items: List[dict]) -> dict:
    n = len(items)
    fired = 0
    by_type = defaultdict(int)
    samples = []
    for it in items:
        f = run_gate(it)
        if f is not None and f.error_type is not None:
            fired += 1
            by_type[_norm_type(f.error_type)] += 1
            if len(samples) < 8:
                samples.append({"pred_type": _norm_type(f.error_type),
                                "pred_row": _row_int(f.problematic_entry),
                                "detail": f.detail})
    return {
        "n": n,
        "false_positive_rate": round(fired / n, 4) if n else 0.0,
        "fired": fired,
        "false_positive_by_type": dict(by_type),
        "samples": samples,
    }


def eval_multi(items: List[dict]) -> dict:
    """Single-error gate on multi-error items: did the primary finding match ANY
    ground-truth error (type+row)?  Partial-credit coverage signal only."""
    n = len(items)
    fired = any_match = 0
    for it in items:
        gts = [( _norm_type(e["error_type"]), _row_int(e["problematic_entry"]))
               for e in it["errors"]]
        f = run_gate(it)
        if f is not None and f.error_type is not None:
            fired += 1
            if (_norm_type(f.error_type), _row_int(f.problematic_entry)) in gts:
                any_match += 1
    return {
        "n": n,
        "coverage": round(fired / n, 4) if n else 0.0,
        "any_error_match": round(any_match / n, 4) if n else 0.0,
        "any_error_match_fired": round(any_match / fired, 4) if fired else 0.0,
    }


# ── reporting ─────────────────────────────────────────────────────────────────
def _print_single(name: str, r: dict):
    print(f"\n{'='*78}\n  {name}  (n={r['n']})  —  deterministic Stage 0A+0B\n{'='*78}")
    print(f"  Coverage (fired)        : {r['coverage']:.3f}")
    print(f"  Error Row EM  (overall) : {r['error_row_em']:.3f}   "
          f"(among fired: {r['error_row_em_fired']:.3f})")
    print(f"  Error Type EM (overall) : {r['error_type_em']:.3f}   "
          f"(among fired: {r['error_type_em_fired']:.3f})")
    print(f"  Success (type & row)    : {r['success_rate']:.3f}")
    cv = r["correct_value_acc"]
    print(f"  Correct-value accuracy  : "
          f"{'n/a' if cv is None else f'{cv:.3f}'}  (n={r['correct_value_n']})")
    print(f"\n  Per ground-truth error type (owner: 0A=arith, 0B=semantic):")
    print(f"  {'type':<20}{'n':>5}{'coverage':>11}{'typeEM':>9}{'rowEM':>9}")
    print("  " + "-"*52)
    for t, v in r["per_type"].items():
        print(f"  {t:<20}{v['n']:>5}{v['coverage']:>11.3f}{v['type_em']:>9.3f}{v['row_em']:>9.3f}")
    print("\n  Confusion (gt -> predicted):")
    for k, c in r["confusion"].items():
        print(f"    {k:<44} {c}")


def _print_correct(r: dict):
    print(f"\n{'='*78}\n  CORRECT split  (n={r['n']})  —  false positives\n{'='*78}")
    print(f"  False-positive rate (any fire) : {r['false_positive_rate']:.3f}  "
          f"({r['fired']}/{r['n']})")
    if r["false_positive_by_type"]:
        print(f"  By predicted type              : {r['false_positive_by_type']}")


def _print_multi(r: dict):
    print(f"\n{'='*78}\n  MULTI-ERROR split  (n={r['n']})  —  primary vs any GT error\n{'='*78}")
    print(f"  Coverage (fired)            : {r['coverage']:.3f}")
    print(f"  Primary matches any GT error: {r['any_error_match']:.3f}  "
          f"(among fired: {r['any_error_match_fired']:.3f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=list(LOADERS) + ["all", "default"],
                    default="default",
                    help="'default' = single_error + correct; 'all' adds multi_error.")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.split == "default":
        splits = ["single_error", "correct"]
    elif args.split == "all":
        splits = ["single_error", "multi_error", "correct"]
    else:
        splits = [args.split]

    print(f"Stage 0 evaluation (seed={args.seed}, n={args.n})")
    report = {"seed": args.seed, "n": args.n, "splits": {}}
    for s in splits:
        items = LOADERS[s](seed=args.seed, n=args.n)
        if s == "correct":
            r = eval_correct(items)
            _print_correct(r)
        elif s == "multi_error":
            r = eval_multi(items)
            _print_multi(r)
        else:
            r = eval_single(items)
            _print_single(s.upper(), r)
        report["splits"][s] = r

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, "stage0_eval.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
