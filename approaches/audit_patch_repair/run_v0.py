"""
AuditPatch V0 eval on AuditBench single_error.

Usage:
  python -m audit_patch.run_v0
  python -m audit_patch.run_v0 --n 150
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from core.paths import REPO_ROOT as _ROOT
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.parser import load_single_error
from approaches.audit_patch_repair.pipeline import repair_item

RESULTS = os.path.join(_ROOT, "results")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    items = load_single_error(seed=args.seed, n=args.n)
    rows = []
    n_fired = 0
    n_repairable = 0
    n_accepted = 0
    n_cleared = 0
    n_num = 0
    samples = []

    for i, item in enumerate(items):
        gt = item["errors"][0]
        gt_type = (gt.get("error_type") or "").lower()
        res = repair_item(item)
        fired = res.before_finding is not None
        repairable = (
            fired
            and res.before_finding.get("correct_value") is not None
            and res.before_finding.get("problematic_entry") is not None
        )
        if fired:
            n_fired += 1
        if repairable:
            n_repairable += 1
        if "numerical" in gt_type:
            n_num += 1
        if res.repaired:
            n_accepted += 1
        if res.certificate.get("target_rule_status") == "cleared":
            n_cleared += 1

        rec = {
            "i": i,
            "gt_type": gt.get("error_type"),
            "gt_row": gt.get("problematic_entry"),
            "repaired": res.repaired,
            "status": res.certificate.get("status"),
            "before": res.before_finding,
            "after": res.after_finding,
            "cascade_before": res.cascade_before,
            "cascade_after": res.cascade_after,
            "patch": res.patch,
        }
        rows.append(rec)
        if res.repaired and len(samples) < 5:
            samples.append({
                "label": (res.patch or {}).get("label"),
                "old": (res.patch or {}).get("old_value"),
                "new": (res.patch or {}).get("new_value"),
                "cascade": f"{res.cascade_before}→{res.cascade_after}",
                "cleared": res.certificate.get("target_rule_status"),
            })

    summary = {
        "dataset": "AuditBench single_error",
        "n": len(items),
        "stage0_fire_rate": round(n_fired / len(items), 4) if items else 0,
        "repairable_with_correct_value": n_repairable,
        "patches_accepted": n_accepted,
        "accept_rate_among_repairable": (
            round(n_accepted / n_repairable, 4) if n_repairable else None
        ),
        "fully_cleared_after_patch": n_cleared,
        "gt_numerical_in_sample": n_num,
        "metric_primary": (
            "share of repairable Stage-0 findings whose patch clears/reduces "
            "violations with patch_size=1"
        ),
        "samples": samples,
    }

    print()
    print("=" * 60)
    print("  AuditPatch V0 — AuditBench numerical repair")
    print("=" * 60)
    print(f"  n={summary['n']}  Stage0 fire={summary['stage0_fire_rate']:.1%}")
    print(f"  repairable (has correct_value): {n_repairable}")
    print(f"  patches accepted:               {n_accepted}"
          f"  ({summary['accept_rate_among_repairable']})")
    print(f"  fully cleared after patch:      {n_cleared}")
    if samples:
        print("  examples:")
        for s in samples:
            print(f"    • {s['label']}: {s['old']} → {s['new']}  "
                  f"cascade {s['cascade']}  {s['cleared']}")
    print("=" * 60)

    os.makedirs(RESULTS, exist_ok=True)
    out = os.path.join(RESULTS, f"audit_patch_v0_{args.n}.json")
    with open(out, "w") as f:
        json.dump({"summary": summary, "records": rows}, f, indent=2, default=str)
    print(f"Wrote {out}\n")


if __name__ == "__main__":
    main()
