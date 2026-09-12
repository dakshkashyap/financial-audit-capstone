"""Run FinMR through every applicable approach/stage and report what works.

FinMR records are real XBRL filings with DQC ground truth. Many approaches in
this repo were built for AuditBench text tables, so this harness:

  • runs every stage that can consume FinMR natively
  • scores relevant metrics against DQC ground truth
  • marks stages that cannot apply (and why)

Usage:
    python scripts/eval_finmr_all_stages.py            # n=40 quick
    python scripts/eval_finmr_all_stages.py --n 332    # full set
    python scripts/eval_finmr_all_stages.py --write    # also write RESULTS markdown
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from datasets import load_dataset

from core.finmr_parser import parse_record
from core.finmr_verifier import predict, _to_float
from core.paths import RESULTS_DIR
from approaches.finmr_benchmark.finmr_eval import score_record
from approaches.audit_patch_repair.finmr_repair import repair_record
from approaches.citation_mcp_agent.tools import TaxonomyTools
from approaches.full_pipeline.run_audit import run_audit


# ── approach applicability (honest) ───────────────────────────────────────────

APPLICABILITY = [
    {
        "approach": "finmr_benchmark",
        "applies": True,
        "role": "DETECT / VERIFY",
        "why": "Native FinMR verifier — Joint ACC against DQC ground truth",
    },
    {
        "approach": "audit_patch_repair",
        "applies": True,
        "role": "LOCALIZE → REPAIR → REVALIDATE → CITE → CERTIFY",
        "why": "Native FinMR repair pipeline with certificates",
    },
    {
        "approach": "stage1_taxonomy_citation",
        "applies": True,
        "role": "CITE (lookup)",
        "why": "FinMR already has us-gaap concepts; taxonomy lookup applies directly",
    },
    {
        "approach": "citation_mcp_agent",
        "applies": True,
        "role": "CITE (tool-locked pick + validate)",
        "why": "TaxonomyTools run on FinMR concepts (no LLM needed for heuristic pick)",
    },
    {
        "approach": "full_pipeline",
        "applies": True,
        "role": "DETECT + CITE (unified)",
        "why": "run_audit(..., source='finmr') detect+cite path",
    },
    {
        "approach": "stage0_deterministic_gate",
        "applies": False,
        "role": "DETECT (AuditBench tables)",
        "why": "Expects AuditBench text tables; FinMR detect is handled by finmr_benchmark",
    },
    {
        "approach": "stage1_concept_mapping",
        "applies": False,
        "role": "label → concept",
        "why": "FinMR facts are already tagged with us-gaap concepts by the filer",
    },
    {
        "approach": "baseline_auditbench",
        "applies": False,
        "role": "end-to-end LLM audit",
        "why": "AuditBench prompt + text tables; different input format and metrics",
    },
    {
        "approach": "stage2_llm_audit",
        "applies": False,
        "role": "focused LLM on abstain",
        "why": "Built for AuditBench evidence packets; no FinMR Stage-2 adapter yet",
    },
]


@dataclass
class StageCounters:
    n: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    notes: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record(self, status: str, note: str = "") -> None:
        self.n += 1
        if status == "pass":
            self.passed += 1
        elif status == "fail":
            self.failed += 1
        else:
            self.skipped += 1
        if note:
            self.notes[note] += 1

    def rate(self) -> Optional[float]:
        denom = self.passed + self.failed
        return (self.passed / denom) if denom else None

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "pass_rate_among_scored": self.rate(),
            "notes": dict(self.notes),
        }


def _values_equal(a, b) -> bool:
    fa, fb = _to_float(a), _to_float(b)
    if fa is None or fb is None:
        return False
    return abs(fa - fb) <= 1e-6


def evaluate(n: Optional[int] = 40) -> dict:
    print(f"Loading FinMR test split…")
    ds = load_dataset("TheFinAI/FinMR", split="test")
    total = len(ds) if n is None else min(n, len(ds))
    print(f"Evaluating {total} of {len(ds)} records\n")

    tools = TaxonomyTools()  # loads taxonomy once

    stages = {
        "1_PARSE": StageCounters(),
        "2_DETECT": StageCounters(),          # finmr_benchmark / Joint ACC pieces
        "3_CONCEPT_READY": StageCounters(),   # concept present (mapping N/A)
        "4_CITE_LOOKUP": StageCounters(),     # stage1_taxonomy_citation
        "5_CITE_VALIDATE": StageCounters(),   # citation_mcp tools
        "6_REPAIR": StageCounters(),          # audit_patch propose
        "7_REVALIDATE": StageCounters(),      # audit_patch accept
        "8_UNIFIED_AUDIT": StageCounters(),   # full_pipeline.run_audit
    }

    # Approach-level metrics
    finmr_labels: List[str] = []
    by_rule: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"n": 0, "A": 0, "E": 0, "C": 0, "S": 0}
    )
    repair = {
        "gt_violations": 0,
        "detection_agree": 0,
        "patches_proposed": 0,
        "exact_match": 0,
        "no_regression": 0,
        "citations_grounded": 0,
        "abstain": 0,
        "consistent": 0,
        "accepted": 0,
        "rejected": 0,
    }
    cite = {
        "concepts": 0,
        "with_candidates": 0,
        "validated_pick": 0,
        "invented": 0,  # always 0 by construction for tool path
    }
    unified = {
        "error_detected": 0,
        "has_citation": 0,
        "detection_agree_with_gt": 0,
    }

    t0 = time.time()
    errors: List[dict] = []

    for i in range(total):
        row = ds[i]
        if (i + 1) % 20 == 0 or i == 0:
            print(f"  [{i+1}/{total}] …", flush=True)

        try:
            # ── 1. PARSE ──────────────────────────────────────────────────
            parsed = parse_record(row)
            q = parsed.question
            parse_ok = q is not None and bool(q.concept_bare)
            stages["1_PARSE"].record(
                "pass" if parse_ok else "fail",
                "ok" if parse_ok else "no_question",
            )
            if not parse_ok:
                continue

            concept = q.concept_bare
            gt_ext, gt_calc = parsed.gt_extracted, parsed.gt_calculated
            gt_is_violation = not _values_equal(gt_ext, gt_calc)

            # ── 2. DETECT (finmr_benchmark) ───────────────────────────────
            pred = predict(parsed)
            label = score_record(pred, gt_ext, gt_calc)
            finmr_labels.append(label)
            by_rule[parsed.dqc_rule]["n"] += 1
            by_rule[parsed.dqc_rule][label] += 1

            detect_ok = label == "A"
            stages["2_DETECT"].record(
                "pass" if detect_ok else "fail",
                label,
            )

            # ── 3. CONCEPT READY ─────────────────────────────────────────
            # FinMR already carries the filer's us-gaap tag — mapping not needed.
            stages["3_CONCEPT_READY"].record(
                "pass" if concept else "fail",
                "already_tagged" if concept else "missing",
            )

            # ── 4. CITE LOOKUP (taxonomy) ─────────────────────────────────
            cands = tools.get_candidates(concept).get("candidates", [])
            cite["concepts"] += 1
            has_cands = len(cands) > 0
            if has_cands:
                cite["with_candidates"] += 1
            stages["4_CITE_LOOKUP"].record(
                "pass" if has_cands else "fail",
                f"n={len(cands)}" if has_cands else "no_candidates",
            )

            # ── 5. CITE VALIDATE (MCP tools, heuristic pick) ──────────────
            if has_cands:
                # Prefer subject-matter over presentation/industry (same rank as repair)
                def rank(c):
                    topic = str(c.get("topic") or "")
                    try:
                        t = int(topic)
                    except ValueError:
                        t = 0
                    presentation = topic in {"205", "210", "220", "230"}
                    industry = t >= 900 or topic == "852"
                    return (0 if industry else 1, 0 if presentation else 1, -len(c["asc"]))

                pick = sorted(cands, key=rank, reverse=True)[0]["asc"]
                check = tools.validate_citation(concept, pick)
                valid = bool(check.get("valid"))
                if valid:
                    cite["validated_pick"] += 1
                stages["5_CITE_VALIDATE"].record(
                    "pass" if valid else "fail",
                    "validated" if valid else check.get("reason", "invalid"),
                )
                # Sanity: inventing a fake ASC must fail validation
                fake = tools.validate_citation(concept, "999-99-99-9")
                if fake.get("valid"):
                    cite["invented"] += 1
            else:
                stages["5_CITE_VALIDATE"].record("skip", "no_candidates")

            # ── 6–7. REPAIR + REVALIDATE (audit_patch) ────────────────────
            rep = repair_record(parsed, tools=tools)
            if gt_is_violation:
                repair["gt_violations"] += 1
                # Detection agreement: we also see a mismatch
                if rep.violation or rep.status in {"accepted", "rejected"}:
                    repair["detection_agree"] += 1

            if rep.status == "abstain":
                repair["abstain"] += 1
                stages["6_REPAIR"].record("skip", "abstain")
                stages["7_REVALIDATE"].record("skip", "abstain")
            elif rep.status == "consistent":
                repair["consistent"] += 1
                stages["6_REPAIR"].record("skip", "already_consistent")
                stages["7_REVALIDATE"].record("skip", "already_consistent")
            else:
                repair["patches_proposed"] += 1
                stages["6_REPAIR"].record("pass", "proposed")

                cleared = bool(
                    rep.certificate.get("revalidation", {})
                    .get("rule_satisfied_after_patch")
                )
                if cleared:
                    repair["no_regression"] += 1
                    stages["7_REVALIDATE"].record("pass", "cleared")
                else:
                    stages["7_REVALIDATE"].record("fail", "still_violates")

                if rep.status == "accepted":
                    repair["accepted"] += 1
                else:
                    repair["rejected"] += 1

                # Exact match vs DQC GT calculated value
                if rep.patch and _values_equal(rep.patch.get("new_value"), gt_calc):
                    repair["exact_match"] += 1

                cit = rep.certificate.get("citation") or {}
                if cit.get("grounded"):
                    repair["citations_grounded"] += 1

            # ── 8. UNIFIED AUDIT (full_pipeline) ──────────────────────────
            ua = run_audit(row, source="finmr")
            if ua.get("error_detected"):
                unified["error_detected"] += 1
            if ua.get("citation"):
                unified["has_citation"] += 1
            # Agree with GT on whether a violation exists
            agree = bool(ua.get("error_detected")) == gt_is_violation
            if agree:
                unified["detection_agree_with_gt"] += 1
            stages["8_UNIFIED_AUDIT"].record(
                "pass" if (agree and (ua.get("citation") or not has_cands)) else "fail",
                "ok" if agree else "detection_mismatch",
            )

        except Exception as e:
            errors.append({"index": i, "error": f"{type(e).__name__}: {e}"})
            for s in stages.values():
                # don't inflate n inconsistently — already partially recorded
                pass
            if len(errors) <= 3:
                traceback.print_exc()

    elapsed = time.time() - t0

    # ── aggregate approach metrics ────────────────────────────────────────
    n_labels = len(finmr_labels) or 1
    counts = {k: finmr_labels.count(k) for k in "ASEC"}
    approach_metrics = {
        "finmr_benchmark": {
            "n": len(finmr_labels),
            "Joint_ACC_%": round(100.0 * counts.get("A", 0) / n_labels, 2),
            "SER_%": round(100.0 * counts.get("S", 0) / n_labels, 2),
            "EER_%": round(100.0 * counts.get("E", 0) / n_labels, 2),
            "CER_%": round(100.0 * counts.get("C", 0) / n_labels, 2),
            "counts": counts,
            "by_rule": {r: dict(v) for r, v in by_rule.items()},
        },
        "audit_patch_repair": {
            "n": total,
            "gt_violations": repair["gt_violations"],
            "detection_agreement_pct": round(
                100.0 * repair["detection_agree"] / max(repair["gt_violations"], 1), 2
            ),
            "patches_proposed": repair["patches_proposed"],
            "exact_patch_match": repair["exact_match"],
            "exact_patch_match_pct_of_patched": round(
                100.0 * repair["exact_match"] / max(repair["patches_proposed"], 1), 2
            ),
            "no_regression_pct_of_patched": round(
                100.0 * repair["no_regression"] / max(repair["patches_proposed"], 1), 2
            ),
            "citations_grounded": repair["citations_grounded"],
            "citation_grounded_pct_of_patched": round(
                100.0 * repair["citations_grounded"] / max(repair["patches_proposed"], 1), 2
            ),
            "status_counts": {
                "accepted": repair["accepted"],
                "rejected": repair["rejected"],
                "abstain": repair["abstain"],
                "consistent": repair["consistent"],
            },
        },
        "stage1_taxonomy_citation": {
            "n": cite["concepts"],
            "candidate_coverage_pct": round(
                100.0 * cite["with_candidates"] / max(cite["concepts"], 1), 2
            ),
        },
        "citation_mcp_agent": {
            "n": cite["concepts"],
            "validated_pick_pct_when_candidates": round(
                100.0 * cite["validated_pick"] / max(cite["with_candidates"], 1), 2
            ),
            "invented_citations_accepted": cite["invented"],
        },
        "full_pipeline": {
            "n": total,
            "error_detected_pct": round(
                100.0 * unified["error_detected"] / max(total, 1), 2
            ),
            "has_citation_pct": round(
                100.0 * unified["has_citation"] / max(total, 1), 2
            ),
            "detection_agree_with_gt_pct": round(
                100.0 * unified["detection_agree_with_gt"] / max(total, 1), 2
            ),
        },
    }

    return {
        "dataset": "TheFinAI/FinMR",
        "n": total,
        "elapsed_sec": round(elapsed, 1),
        "date": date.today().isoformat(),
        "applicability": APPLICABILITY,
        "stages": {k: v.to_dict() for k, v in stages.items()},
        "approach_metrics": approach_metrics,
        "errors": errors,
    }


def print_report(r: dict) -> None:
    print("\n" + "=" * 72)
    print(f"  FinMR × all stages   n={r['n']}   {r['elapsed_sec']}s")
    print("=" * 72)

    print("\n── Which approaches apply to FinMR ──\n")
    print(f"  {'Approach':32s}  {'Applies':7s}  Role")
    print("  " + "-" * 68)
    for a in r["applicability"]:
        flag = "YES" if a["applies"] else "no"
        print(f"  {a['approach']:32s}  {flag:7s}  {a['role']}")
        if not a["applies"]:
            print(f"  {'':32s}           ↳ {a['why']}")

    print("\n── Stage pass rates (among scored) ──\n")
    print(f"  {'Stage':22s}  {'pass':>5}  {'fail':>5}  {'skip':>5}  {'rate':>7}  notes")
    print("  " + "-" * 70)
    for name, s in r["stages"].items():
        rate = s["pass_rate_among_scored"]
        rate_s = f"{100*rate:5.1f}%" if rate is not None else "   n/a"
        top_notes = ", ".join(
            f"{k}={v}" for k, v in sorted(s["notes"].items(), key=lambda kv: -kv[1])[:3]
        )
        print(
            f"  {name:22s}  {s['passed']:5d}  {s['failed']:5d}  "
            f"{s['skipped']:5d}  {rate_s:>7}  {top_notes}"
        )

    m = r["approach_metrics"]
    print("\n── Approach metrics on FinMR ──\n")

    fb = m["finmr_benchmark"]
    print(f"  finmr_benchmark (DETECT)")
    print(f"    Joint ACC  {fb['Joint_ACC_%']}%   "
          f"EER {fb['EER_%']}%   CER {fb['CER_%']}%   n={fb['n']}")

    ap = m["audit_patch_repair"]
    print(f"\n  audit_patch_repair (REPAIR)")
    print(f"    detection agreement     {ap['detection_agreement_pct']}%")
    print(f"    patches proposed        {ap['patches_proposed']}")
    print(f"    exact match vs DQC GT   {ap['exact_patch_match']}  "
          f"({ap['exact_patch_match_pct_of_patched']}% of patched)")
    print(f"    no regressions          {ap['no_regression_pct_of_patched']}% of patched")
    print(f"    grounded citations      {ap['citation_grounded_pct_of_patched']}% of patched")
    print(f"    status                  {ap['status_counts']}")

    st = m["stage1_taxonomy_citation"]
    print(f"\n  stage1_taxonomy_citation (CITE lookup)")
    print(f"    candidate coverage      {st['candidate_coverage_pct']}%")

    cm = m["citation_mcp_agent"]
    print(f"\n  citation_mcp_agent (CITE validate)")
    print(f"    validated pick rate     {cm['validated_pick_pct_when_candidates']}%")
    print(f"    invented citations OK   {cm['invented_citations_accepted']}  (must be 0)")

    fp = m["full_pipeline"]
    print(f"\n  full_pipeline.run_audit (DETECT+CITE)")
    print(f"    detection↔GT agreement  {fp['detection_agree_with_gt_pct']}%")
    print(f"    has citation            {fp['has_citation_pct']}%")

    if r["errors"]:
        print(f"\n  !! {len(r['errors'])} record errors (showing up to 5):")
        for e in r["errors"][:5]:
            print(f"     [{e['index']}] {e['error']}")

    print()


def write_markdown(r: dict, path: str) -> None:
    lines = [
        "# FinMR × all stages — evaluation report",
        "",
        f"Generated by `python scripts/eval_finmr_all_stages.py` on **{r['date']}**.",
        f"Dataset: `{r['dataset']}` · **n={r['n']}** · {r['elapsed_sec']}s",
        "",
        "## Does each approach apply to FinMR?",
        "",
        "| Approach | Applies? | Role on FinMR | Notes |",
        "|---|---|---|---|",
    ]
    for a in r["applicability"]:
        flag = "yes" if a["applies"] else "**no**"
        lines.append(
            f"| `{a['approach']}` | {flag} | {a['role']} | {a['why']} |"
        )

    lines += [
        "",
        "## Stage pass rates",
        "",
        "Each FinMR record is walked through the stages below. "
        "`skip` means the stage correctly abstained (e.g. no candidates, "
        "already consistent) — not a failure.",
        "",
        "| Stage | What “pass” means | Pass | Fail | Skip | Rate |",
        "|---|---|---:|---:|---:|---:|",
    ]
    meanings = {
        "1_PARSE": "XBRL query parsed; concept found",
        "2_DETECT": "Joint ACC — both extracted + calculated match DQC GT",
        "3_CONCEPT_READY": "us-gaap concept already present (mapping not needed)",
        "4_CITE_LOOKUP": "taxonomy has ≥1 ASC candidate for the concept",
        "5_CITE_VALIDATE": "tool-locked pick validates; invented ASC rejected",
        "6_REPAIR": "minimal patch proposed (abstain/consistent = skip)",
        "7_REVALIDATE": "patch clears the rule; 0 new violations",
        "8_UNIFIED_AUDIT": "run_audit detection agrees with GT on violation?",
    }
    for name, s in r["stages"].items():
        rate = s["pass_rate_among_scored"]
        rate_s = f"{100*rate:.1f}%" if rate is not None else "n/a"
        lines.append(
            f"| `{name}` | {meanings.get(name, '')} | "
            f"{s['passed']} | {s['failed']} | {s['skipped']} | {rate_s} |"
        )

    m = r["approach_metrics"]
    fb, ap = m["finmr_benchmark"], m["audit_patch_repair"]
    st, cm, fp = (
        m["stage1_taxonomy_citation"],
        m["citation_mcp_agent"],
        m["full_pipeline"],
    )

    lines += [
        "",
        "## Approach metrics",
        "",
        "### `finmr_benchmark` — detect / verify",
        "",
        f"- Joint ACC: **{fb['Joint_ACC_%']}%**",
        f"- Extraction error rate: {fb['EER_%']}%",
        f"- Calculation error rate: {fb['CER_%']}%",
        "",
        "### `audit_patch_repair` — localize / repair / revalidate / certify",
        "",
        f"- Detection agreement with GT: **{ap['detection_agreement_pct']}%**",
        f"- Patches proposed: {ap['patches_proposed']}",
        f"- Exact match vs DQC GT: **{ap['exact_patch_match']} "
        f"({ap['exact_patch_match_pct_of_patched']}% of patched)**",
        f"- No regressions: **{ap['no_regression_pct_of_patched']}% of patched**",
        f"- Grounded citations: {ap['citation_grounded_pct_of_patched']}% of patched",
        f"- Status counts: `{ap['status_counts']}`",
        "",
        "### `stage1_taxonomy_citation` — cite lookup",
        "",
        f"- Candidate coverage: **{st['candidate_coverage_pct']}%**",
        "",
        "### `citation_mcp_agent` — cite validate",
        "",
        f"- Validated pick when candidates exist: **{cm['validated_pick_pct_when_candidates']}%**",
        f"- Invented citations accepted: **{cm['invented_citations_accepted']}** (must be 0)",
        "",
        "### `full_pipeline` — unified detect + cite",
        "",
        f"- Detection agreement with GT: **{fp['detection_agree_with_gt_pct']}%**",
        f"- Has a citation: {fp['has_citation_pct']}%",
        "",
        "## What this means",
        "",
        "FinMR is an XBRL + DQC dataset. Approaches built for AuditBench text",
        "tables (`baseline_auditbench`, `stage0_deterministic_gate`,",
        "`stage1_concept_mapping`, `stage2_llm_audit`) do not consume FinMR",
        "records as-is — that is expected, not a silent failure.",
        "",
        "The stages that *do* apply form the repair path:",
        "**parse → detect → cite → repair → revalidate → certify**.",
        "",
        "Machine-readable output: `results/finmr_all_stages.json`.",
        "",
    ]
    open(path, "w").write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="FinMR through all applicable stages")
    ap.add_argument("--n", type=int, default=40, help="records to evaluate (default 40; use 332 for full)")
    ap.add_argument("--write", action="store_true", help="also write docs/results/FINMR_ALL_STAGES.md")
    args = ap.parse_args()

    report = evaluate(n=args.n)
    print_report(report)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_json = os.path.join(RESULTS_DIR, "finmr_all_stages.json")
    with open(out_json, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {out_json}")

    if args.write:
        md = os.path.join(REPO, "docs", "results", "FINMR_ALL_STAGES.md")
        write_markdown(report, md)
        print(f"Wrote {md}")


if __name__ == "__main__":
    main()
