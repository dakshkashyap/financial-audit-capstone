"""
Stage 1 · Arelle — Citation ACCURACY evaluation (vs. ground truth).

This is the metric that matters for the paper: does Stage 1 produce the
*correct* FASB ASC citation for the specific broken row?

Difference from stage1_eval.py
------------------------------
  stage1_eval.py          → coverage (how many rows got *a* citation)
  stage1_citation_eval.py → accuracy (does the broken row's citation match
                            the ground-truth Standards Citation topic?)

Why a dedicated script
----------------------
  results/stage1_eval.json stores only aggregate stats + 5 samples — it has
  no per-record, per-row citation keyed by the broken row. So we re-run
  Stage 1 live here and look up each record's broken row directly.

Methodology (per record)
-------------------------
  1. Load the exact evaluated sample via parser.load_single_error(seed, n).
     (parser uses random.sample(seed=42) — NOT shuffle — so this reproduces
      precisely the records stage1_eval.py scored.)
  2. Ground truth:
       - broken row index : errors[0]["problematic_entry"]   (an int)
       - GT citation topic: ASC topic (3-digit) parsed from
                            errors[0]["standards_citation"]
  3. Prediction:
       - run Stage 1 → find the MappedRow whose row_idx == broken row
       - extract the ASC topic from that row's asc_primary
  4. Score:
       - covered : we produced *a* citation for the broken row
       - hit     : our topic == GT topic  (Citation Topic EM)

Records whose GT citation has no ASC number (e.g. "FASB Conceptual
Framework") are excluded from the denominator — there is nothing in the
codification to match against.

Usage
-----
  python stage1_citation_eval.py                       # single_error, n=150
  python stage1_citation_eval.py --n 1484              # full single-error set
  python stage1_citation_eval.py --split multi_error   # multi-error split
  python stage1_citation_eval.py --level subtopic      # match 310-10 not just 310
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from typing import List, Optional

pass  # repo root already on sys.path when run with -m

from core.parser import load_single_error, load_multi_error
from approaches.stage1_taxonomy_citation.stage1_arelle import run_stage1
from core.taxonomy_graph import TaxonomyGraph

# Stage 0 (deterministic gate) — used only to obtain a PREDICTED error type
# per record, so we can report citation accuracy bucketed by the error type
# the real pipeline would actually have (vs the ground-truth error type).
# Imported directly (not via stage0_eval) to avoid pulling in heavy metrics deps.
from approaches.stage0_deterministic_gate import stage0a
from approaches.stage0_deterministic_gate import stage0b
from core.stage0_common import combine_findings


def _predict_error_type(item: dict) -> str:
    """Stage 0's predicted error type for an item, or 'unfired' if it abstains."""
    try:
        f = combine_findings(stage0a.verify(item), stage0b.check(item))
        return f.error_type if (f and f.error_type) else "unfired"
    except Exception:
        return "unfired"

from core.paths import RESULTS_DIR   # repo-root results/
PAPER_BASELINE = 0.262   # GPT-4 Standards Citation EM reported in AuditBench

LOADERS = {
    "single_error": load_single_error,
    "multi_error":  load_multi_error,
}


# ── ASC topic extraction ──────────────────────────────────────────────────────

# GT prose: "...FASB ASC 310-10...", "Accounting Standards Codification (ASC) 220-10..."
# Allow a few non-digit chars between "ASC" and the 3-digit topic so "(ASC) 220"
# and "ASC) 220" both resolve.
_GT_ASC_RE = re.compile(r"ASC[^\d]{0,8}(\d{3})")

# Our asc_primary is already normalized: "310-10-45-1" (no "ASC" prefix).
_PRED_ASC_RE = re.compile(r"^(\d{3})")


def extract_gt_topic(text: str) -> Optional[str]:
    if not text:
        return None
    m = _GT_ASC_RE.search(text)
    return m.group(1) if m else None


def extract_gt_subtopic(text: str) -> Optional[str]:
    """Return 'TTT-SS' if present in the GT prose, else just the topic."""
    if not text:
        return None
    m = re.search(r"ASC[^\d]{0,8}(\d{3})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return extract_gt_topic(text)


def extract_pred_topic(asc_primary: Optional[str]) -> Optional[str]:
    if not asc_primary:
        return None
    m = _PRED_ASC_RE.match(asc_primary.strip())
    return m.group(1) if m else None


def extract_pred_subtopic(asc_primary: Optional[str]) -> Optional[str]:
    if not asc_primary:
        return None
    parts = asc_primary.strip().split("-")
    if len(parts) >= 2 and re.match(r"\d{3}", parts[0]):
        return f"{parts[0]}-{parts[1]}"
    return extract_pred_topic(asc_primary)


# ── evaluation ────────────────────────────────────────────────────────────────

def _aggregate_by(records: List[dict], key: str) -> dict:
    """Bucket per-record results by `key` ('gt_et' or 'pred_et')."""
    bt = defaultdict(lambda: {"total": 0, "covered": 0, "hit": 0, "recall": 0})
    for r in records:
        s = bt[r[key]]
        s["total"]   += 1
        s["covered"] += int(r["covered"])
        s["hit"]     += int(r["hit"])
        s["recall"]  += int(r["recall"])
    out = {}
    for et, s in bt.items():
        out[et] = {
            "total":    s["total"],
            "covered":  s["covered"],
            "hit":      s["hit"],
            "coverage": round(s["covered"] / s["total"], 4) if s["total"] else 0.0,
            "topic_em": round(s["hit"] / s["total"], 4) if s["total"] else 0.0,
            "topic_em_among_covered": round(s["hit"] / s["covered"], 4) if s["covered"] else 0.0,
            "candidate_recall": round(s["recall"] / s["total"], 4) if s["total"] else 0.0,
        }
    return out


def eval_citations(items: List[dict], graph: TaxonomyGraph, level: str,
                   with_predicted: bool = True) -> dict:
    gt_extract   = extract_gt_subtopic   if level == "subtopic" else extract_gt_topic
    pred_extract = extract_pred_subtopic if level == "subtopic" else extract_pred_topic

    records: List[dict] = []   # one entry per usable (GT-ASC) error record
    no_asc_in_gt = 0           # GT had no ASC (Conceptual Framework etc.) — excluded
    row_missing  = 0           # broken row not found in parsed table (e.g. Missing Row)

    # Stage-0 firing diagnostics
    n_items = 0
    n_fired = 0
    n_type_correct = 0

    for item in items:
        n_items += 1
        pred_et = _predict_error_type(item) if with_predicted else "n/a"
        if pred_et != "unfired":
            n_fired += 1

        result = run_stage1(item, graph)

        for err in item["errors"]:
            gt_topic = gt_extract(err.get("standards_citation", ""))
            if not gt_topic:
                no_asc_in_gt += 1
                continue

            gt_et  = err.get("error_type", "?")
            gt_row = err.get("problematic_entry")
            try:
                gt_row = int(re.search(r"\d+", str(gt_row)).group())
            except (AttributeError, TypeError, ValueError):
                gt_row = None

            if with_predicted and pred_et == gt_et:
                n_type_correct += 1

            rec = {"gt_topic": gt_topic, "gt_et": gt_et, "pred_et": pred_et,
                   "gt_row": gt_row, "covered": False, "hit": False,
                   "recall": False, "row_found": False}

            row = next((r for r in result.statement.rows if r.row_idx == gt_row), None)
            if row is None:
                row_missing += 1
                records.append(rec)
                continue
            rec["row_found"] = True

            # Candidate-set recall (the Stage-2 ceiling)
            concept_bare = (row.concept or "").replace("us-gaap:", "")
            cand_topics = set()
            if concept_bare:
                for c in graph.get_candidate_citations(concept_bare):
                    cand_topics.add("-".join(c["asc"].split("-")[:2])
                                    if level == "subtopic" else c["topic"])
            rec["recall"] = gt_topic in cand_topics

            pred_topic = pred_extract(row.asc_primary)
            rec["covered"]    = bool(pred_topic)
            rec["hit"]        = bool(pred_topic) and pred_topic == gt_topic
            rec["pred_topic"] = pred_topic
            rec["concept"]    = row.concept
            rec["label"]      = row.label[:50]
            rec["source"]     = result.citation_sources.get(gt_row)
            records.append(rec)

    total      = len(records)
    covered    = sum(r["covered"] for r in records)
    hit        = sum(r["hit"]     for r in records)
    recall_hit = sum(r["recall"]  for r in records)

    misses = []
    for r in records:
        if r["hit"] or len(misses) >= 25:
            continue
        reason = ("row_not_in_table" if not r["row_found"]
                  else "no_citation_for_row" if not r["covered"]
                  else "topic_mismatch")
        misses.append({
            "error_type": r["gt_et"], "gt_row": r["gt_row"],
            "gt_topic": r["gt_topic"], "pred_topic": r.get("pred_topic"),
            "concept": r.get("concept"), "source": r.get("source"),
            "reason": reason,
        })

    out = {
        "level":               level,
        "taxonomy_available":  graph.available,
        "records_with_gt_asc": total,
        "gt_without_asc":      no_asc_in_gt,
        "broken_row_covered":  covered,
        "topic_hits":          hit,
        "row_not_in_table":    row_missing,
        "coverage":            round(covered / total, 4) if total else 0.0,
        "citation_topic_em":   round(hit / total, 4) if total else 0.0,
        "topic_em_among_covered": round(hit / covered, 4) if covered else 0.0,
        "candidate_recall":    round(recall_hit / total, 4) if total else 0.0,
        "candidate_recall_hits": recall_hit,
        "paper_baseline":      PAPER_BASELINE,
        "by_error_type_gt":    _aggregate_by(records, "gt_et"),
        "sample_misses":       misses,
    }
    if with_predicted:
        out["by_error_type_predicted"] = _aggregate_by(records, "pred_et")
        out["stage0_fire_rate"]   = round(n_fired / n_items, 4) if n_items else 0.0
        out["stage0_type_acc"]    = round(n_type_correct / total, 4) if total else 0.0
    return out


# ── pretty print ──────────────────────────────────────────────────────────────

def print_results(r: dict, split: str, n: int) -> None:
    def _bar(v: float, width: int = 30) -> str:
        return "█" * int(v * width) + "░" * (width - int(v * width))

    print(f"\n{'='*66}")
    print(f" Stage 1 Citation ACCURACY — {split.upper()} (n={n}, level={r['level']})")
    print(f"{'='*66}")
    tax = "✓ live taxonomy" if r["taxonomy_available"] else "✗ offline (static-map only)"
    print(f"\n  Taxonomy: {tax}")
    print(f"  Records with a usable GT ASC citation : {r['records_with_gt_asc']}")
    print(f"  GT citations without any ASC (excluded): {r['gt_without_asc']}")
    print(f"  Broken row missing from table          : {r['row_not_in_table']}")

    print(f"\n  Broken-row citation coverage : {r['coverage']:.1%}  "
          f"{_bar(r['coverage'])}  ({r['broken_row_covered']}/{r['records_with_gt_asc']})")
    em = r["citation_topic_em"]
    print(f"\n  CITATION TOPIC EM (single-pick) : {em:.1%}  {_bar(em)}  "
          f"({r['topic_hits']}/{r['records_with_gt_asc']})")
    print(f"  Topic EM among covered rows     : {r['topic_em_among_covered']:.1%}")
    rec = r["candidate_recall"]
    print(f"\n  CANDIDATE RECALL (Stage-2 ceiling): {rec:.1%}  {_bar(rec)}  "
          f"({r['candidate_recall_hits']}/{r['records_with_gt_asc']})")
    print(f"    → GT topic is present in the graph's candidate set this often;")
    print(f"      a context-aware Stage-2 selector can reach up to this.")
    print(f"\n  Paper GPT-4 baseline            : {r['paper_baseline']:.1%}")
    delta = em - r["paper_baseline"]
    sign  = "+" if delta >= 0 else ""
    print(f"  Δ single-pick vs paper          : {sign}{delta:.1%}")
    delta2 = rec - r["paper_baseline"]
    sign2  = "+" if delta2 >= 0 else ""
    print(f"  Δ ceiling vs paper              : {sign2}{delta2:.1%}")

    def _print_breakdown(title, table):
        print(f"\n  By error type — {title}:")
        print(f"    {'type':20s}  {'n':>4}  {'cover':>6}  {'topicEM':>8}  {'recall':>7}")
        print(f"    {'-'*20}  {'----':>4}  {'------':>6}  {'--------':>8}  {'-------':>7}")
        for et, s in sorted(table.items()):
            print(f"    {et:20s}  {s['total']:4d}  {s['coverage']:6.1%}  "
                  f"{s['topic_em']:8.1%}  {s['candidate_recall']:7.1%}")

    _print_breakdown("GROUND-TRUTH error type", r["by_error_type_gt"])
    if "by_error_type_predicted" in r:
        _print_breakdown("STAGE-0 PREDICTED error type", r["by_error_type_predicted"])
        print(f"\n  Stage 0 fire rate: {r['stage0_fire_rate']:.1%}  "
              f"(error-type accuracy vs GT: {r['stage0_type_acc']:.1%})")
        print(f"    NOTE: Fix #1 (section fallback) does not use error type, so the")
        print(f"    overall EM is identical in both views — only the bucketing differs.")
        print(f"    'unfired' = Stage 0 abstained; the realistic pipeline has no error")
        print(f"    type for those records (relevant once Fix #3 conditions on type).")

    if r["sample_misses"]:
        print(f"\n  Sample misses (first {min(10, len(r['sample_misses']))}):")
        for m in r["sample_misses"][:10]:
            concept = (m.get("concept") or "").replace("us-gaap:", "")[:30]
            print(f"    [{m['reason']:18s}] row {m['gt_row']}  "
                  f"GT={m['gt_topic']}  pred={m.get('pred_topic')}  "
                  f"{concept}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate Stage 1 citation ACCURACY vs ground-truth Standards Citation.")
    ap.add_argument("--split", choices=list(LOADERS), default="single_error")
    ap.add_argument("--n",    type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--level", choices=["topic", "subtopic"], default="topic",
                    help="Match at ASC topic (310) or subtopic (310-10) granularity")
    ap.add_argument("--no-taxonomy", action="store_true",
                    help="Skip taxonomy; score static-map citations only")
    ap.add_argument("--no-predicted", action="store_true",
                    help="Skip the Stage-0 predicted-error-type breakdown (faster)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    graph = TaxonomyGraph()
    if args.no_taxonomy:
        graph._xml_content = ""
        graph._available   = False
    else:
        _ = graph.available   # trigger load now

    print(f"\nLoading {args.split} (seed={args.seed}, n={args.n}) …")
    items = LOADERS[args.split](seed=args.seed, n=args.n)
    print(f"  {len(items)} items — scoring citations…")

    result = eval_citations(items, graph, args.level,
                            with_predicted=not args.no_predicted)
    print_results(result, args.split, args.n)

    out_path = args.out or os.path.join(RESULTS_DIR, "stage1_citation_eval.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"split": args.split, "seed": args.seed, "n": args.n, **result},
                  f, indent=2)
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
