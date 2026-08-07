"""
AuditPatch on FinMR — run and score against DQC ground truth.

  python -m audit_patch.run_finmr --n 100
  python -m audit_patch.run_finmr              # all 332
  python -m audit_patch.run_finmr --no-citation  # skip taxonomy MCP lookups

Scored against the FinMR record's own ground truth
(``extracted_value`` / ``calculated_value``), which comes from DQC rules.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from datasets import load_dataset

from finmr_parser import parse_record
from finmr_verifier import _to_float
from audit_patch.finmr_repair import repair_record

RESULTS = os.path.join(_ROOT, "results")


def _eq(a, b) -> bool:
    fa, fb = _to_float(str(a)) if a is not None else None, _to_float(str(b)) if b is not None else None
    return fa is not None and fb is not None and abs(fa - fb) <= 1e-6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--no-citation", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tools = None
    if not args.no_citation:
        from citation_mcp.tools import TaxonomyTools
        tools = TaxonomyTools()
        tools.graph.get_fasb_citation("Assets")  # warm the taxonomy cache

    ds = load_dataset("TheFinAI/FinMR", split="test")
    total = len(ds) if args.n is None else min(args.n, len(ds))

    records: List[Dict[str, Any]] = []
    by_rule = defaultdict(lambda: {"n": 0, "patched": 0, "exact": 0, "gt_violation": 0})

    n_gt_violation = 0
    n_patch = 0
    n_exact_patch = 0
    n_detect_agree = 0
    n_no_regression = 0
    n_cited = 0
    n_grounded = 0
    samples: List[Dict[str, Any]] = []

    for i in range(total):
        parsed = parse_record(ds[i])
        rep = repair_record(parsed, tools=tools)

        gt_ext, gt_calc = parsed.gt_extracted, parsed.gt_calculated
        gt_violation = not _eq(gt_ext, gt_calc)
        if gt_violation:
            n_gt_violation += 1

        rule = rep.dqc_rule
        by_rule[rule]["n"] += 1
        by_rule[rule]["gt_violation"] += int(gt_violation)

        # Detection agreement: did we flag a violation exactly when GT has one?
        if rep.status in ("accepted", "rejected", "consistent"):
            if rep.violation == gt_violation:
                n_detect_agree += 1

        exact = False
        if rep.patch is not None:
            n_patch += 1
            by_rule[rule]["patched"] += 1
            # Exact patch match: our repaired value equals the DQC-correct value
            exact = _eq(rep.patch["new_value"], gt_calc) and _eq(rep.reported, gt_ext)
            if exact:
                n_exact_patch += 1
                by_rule[rule]["exact"] += 1
            reval = rep.certificate.get("revalidation", {})
            if reval.get("rule_satisfied_after_patch"):
                n_no_regression += 1
            cit = rep.certificate.get("citation", {})
            if cit.get("asc"):
                n_cited += 1
            if cit.get("grounded"):
                n_grounded += 1

            if exact and len(samples) < 4:
                samples.append(rep.certificate)

        records.append({
            "id": rep.record_id,
            "rule": rule,
            "concept": rep.concept,
            "status": rep.status,
            "our_violation": rep.violation,
            "gt_violation": gt_violation,
            "reported": rep.reported,
            "expected": rep.expected,
            "gt_extracted": gt_ext,
            "gt_calculated": gt_calc,
            "exact_patch": exact,
            "citation": rep.certificate.get("citation", {}).get("asc"),
        })

    def pct(x: int, d: int) -> float:
        return round(100.0 * x / d, 2) if d else 0.0

    summary = {
        "dataset": "TheFinAI/FinMR (real XBRL + DQC ground truth)",
        "n_records": total,
        "gt_violations": n_gt_violation,
        "detection_agreement_pct": pct(n_detect_agree, total),
        "patches_proposed": n_patch,
        "exact_patch_match": n_exact_patch,
        "exact_patch_match_pct_of_patched": pct(n_exact_patch, n_patch),
        "no_regression_pct_of_patched": pct(n_no_regression, n_patch),
        "patch_size": 1,
        "citations_attached": n_cited,
        "citation_grounded_pct_of_patched": pct(n_grounded, n_patch),
        "by_rule": {k: dict(v) for k, v in sorted(by_rule.items())},
        "sample_certificates": samples,
    }

    print()
    print("=" * 66)
    print("  AuditPatch on FinMR — explainable repair with certificates")
    print("=" * 66)
    print(f"  records                      : {total}")
    print(f"  ground-truth violations      : {n_gt_violation}")
    print(f"  detection agreement with GT  : {summary['detection_agreement_pct']}%")
    print(f"  patches proposed (size 1)    : {n_patch}")
    print(f"  exact patch match vs DQC GT  : {n_exact_patch}"
          f"  ({summary['exact_patch_match_pct_of_patched']}% of patched)")
    print(f"  rule satisfied after patch   : {summary['no_regression_pct_of_patched']}%")
    print(f"  grounded citations attached  : {n_grounded}"
          f"  ({summary['citation_grounded_pct_of_patched']}% of patched)")
    print()
    print(f"  {'rule':14s} {'n':>4} {'gt_viol':>8} {'patched':>8} {'exact':>7}")
    for rule, v in summary["by_rule"].items():
        print(f"  {rule:14s} {v['n']:>4} {v['gt_violation']:>8} "
              f"{v['patched']:>8} {v['exact']:>7}")
    if samples:
        s = samples[0]
        print()
        print("  Example certificate (explainability):")
        print(f"    rule      : {s['dqc_rule']} — {s['rule_meaning']}")
        print(f"    root cause: {s['root_cause']['concept']} ({s['root_cause']['period']})")
        print(f"    equation  : {s['evidence']['equation'][:150]}")
        print(f"    patch     : {s['patch']['old_value']} → {s['patch']['new_value']}"
              f"  (size {s['patch']['patch_size']})")
        print(f"    revalidate: satisfied={s['revalidation']['rule_satisfied_after_patch']}"
              f"  new_violations={s['revalidation']['new_violations_introduced']}")
        print(f"    citation  : {s['citation'].get('asc')} (grounded={s['citation'].get('grounded')})")
    print("=" * 66)

    os.makedirs(RESULTS, exist_ok=True)
    out = args.out or os.path.join(RESULTS, f"audit_patch_finmr_{total}.json")
    with open(out, "w") as f:
        json.dump({"summary": summary, "records": records}, f, indent=2, default=str)
    print(f"Wrote {out}\n")


if __name__ == "__main__":
    main()
