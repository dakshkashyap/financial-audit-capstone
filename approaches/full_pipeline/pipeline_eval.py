"""
pipeline_eval.py — IntelliAudit ablation: what does the deterministic
architecture add to the LLM, at FIXED model?

Compares, per split (seed=42, n=150), three configurations using the EXISTING
Claude Opus-4.6 predictions (no new API calls):

  Config A  — LLM alone           : the baseline run's General Judgment verdict.
  Config B  — Stage 0 alone        : the deterministic gate as sole judge
                                     (fires on proof, abstains otherwise).
  Config A+veto — legacy output label retained for compatibility. A veto now
                 requires an explicit complete error-absence certificate;
                 current checkers do not provide one. Partial arithmetic
                 consistency alone never changes the model's judgment.

Headline metric: General Judgment EM, especially on the CLEAN split, where the
LLM's over-auditing shows up as false positives.

Abstention remains unverified, including on clean controls. Missing, failed or
misaligned model records remain in the denominator. Existing predictions must
match both the item index and table hash. Coverage of arithmetic checks is not
a complete clean-statement certificate; taxonomy membership is not citation
applicability. The legacy calls-saved field concerns detection only.

Usage:
  python pipeline_eval.py                 # all splits with an Opus prediction file
  python pipeline_eval.py --split correct
"""
from __future__ import annotations

import argparse
import json
import os
import sys

pass  # repo root already on sys.path when run with -m

from core.parser import load_correct, load_single_error, load_multi_error
from approaches.full_pipeline.pipeline import run_pipeline
from core.taxonomy_graph import TaxonomyGraph
from core.metrics import _norm_type, _row_int
from approaches.full_pipeline.intelliaudit_runner import _table_hash
from approaches.stage2_llm_audit.stage2_llm import apply_consistency_veto

from core.paths import RESULTS_DIR   # repo-root results/
LOADERS = {"correct": load_correct, "single_error": load_single_error,
           "multi_error": load_multi_error}
PRED_MODEL = "claude-opus-4-6"   # the existing baseline run used as "LLM alone"


def _llm_judgment(parsed) -> str:
    if not isinstance(parsed, dict):
        return "Unverified"
    judgment = parsed.get("General Judgment", parsed.get("General Judgement", ""))
    return judgment if str(judgment).strip().lower() in {"correct", "incorrect"} else "Unverified"


def _norm_judg(s: str) -> str:
    return str(s).strip().lower()


def eval_split(split: str, graph: TaxonomyGraph, n: int, seed: int) -> dict:
    pred_path = os.path.join(RESULTS_DIR, f"{PRED_MODEL}_{split}_predictions.json")
    have_llm = os.path.exists(pred_path)
    preds = []
    if have_llm:
        with open(pred_path, encoding="utf-8") as handle:
            preds = json.load(handle)

    items = LOADERS[split](seed=seed, n=n)
    # Never infer record identity from array order. A changed sampling seed or
    # partial file must not silently score another case's answer.
    indexed = {}
    duplicates = set()
    for prediction in preds:
        index = prediction.get("item_idx")
        if type(index) is not int:
            continue
        if index in indexed:
            duplicates.add(index)
        indexed[index] = prediction

    N = len(items)
    gj_llm = gj_det = gj_veto = 0          # General Judgment correct counts
    fp_llm = fp_veto = 0                    # false positives on clean split
    llm_says_incorrect = 0
    fired = abstained = verified = 0
    veto_applied = 0
    prediction_failures = 0
    # error-split localization (Stage 0 as judge)
    type_hits = row_hits = fired_err = 0

    for i in range(N):
        item = items[i]
        rec  = run_pipeline(item, graph)
        gt_judg = _norm_judg(item.get("general_judgement", "Incorrect"))
        is_clean = (gt_judg == "correct")

        if rec.abstained:
            abstained += 1
        else:
            fired += 1
        if rec.verified_consistent:
            verified += 1

        # ── Config B: Stage 0 as sole judge ──
        det_judg = "incorrect" if not rec.abstained else "unverified"
        gj_det += int(det_judg == gt_judg)

        # error-split localization quality (only where the gate fired on an error)
        if not is_clean and not rec.abstained and item.get("errors"):
            fired_err += 1
            gt = item["errors"][0]
            if _norm_type(rec.error_type or "") == _norm_type(gt.get("error_type", "")):
                type_hits += 1
            if rec.problematic_entry is not None and \
               rec.problematic_entry == _row_int(gt.get("problematic_entry")):
                row_hits += 1

        # ── Config A and A+veto (need the LLM prediction) ──
        if have_llm:
            prediction = indexed.get(i)
            matched = (prediction is not None and i not in duplicates
                       and prediction.get("table_hash") == _table_hash(item)
                       and not prediction.get("error"))
            parsed = prediction.get("parsed") if matched else None
            llm_judg = _norm_judg(_llm_judgment(parsed))
            prediction_failures += int(llm_judg == "unverified")
            gj_llm += int(llm_judg == gt_judg)
            if is_clean and llm_judg == "incorrect":
                fp_llm += 1
            # No current checker supplies a complete absence certificate.
            guarded, vetoed = apply_consistency_veto(
                parsed, verified_consistent=rec.verified_consistent,
                original_table=item["table"],
            )
            veto_judg = _norm_judg(_llm_judgment(guarded))
            veto_applied += int(vetoed)
            gj_veto += int(veto_judg == gt_judg)
            if is_clean and veto_judg == "incorrect":
                fp_veto += 1
            if llm_judg == "incorrect":
                llm_says_incorrect += 1

    out = {
        "split": split, "n": N, "is_clean_split": split == "correct",
        "have_llm": have_llm,
        "gate_fire_rate":      round(fired / N, 4) if N else 0,
        "abstention_rate":     round(abstained / N, 4) if N else 0,
        "verified_consistent_rate": round(verified / N, 4) if N else 0,
        "config_B_gen_judgment_em": round(gj_det / N, 4) if N else 0,
        "llm_calls_saved":     round(fired / N, 4) if N else 0,
        "scope": "historical_prediction_replay; abstention retained; detection-only call savings",
    }
    if have_llm:
        out.update({
            "config_A_gen_judgment_em":    round(gj_llm / N, 4) if N else 0,
            "config_Aveto_gen_judgment_em": round(gj_veto / N, 4) if N else 0,
            "vetoes_applied":              veto_applied,
            "llm_prediction_failures":     prediction_failures,
            "prediction_records":         len(preds),
        })
        if split == "correct":
            out.update({
                "fp_rate_llm":  round(fp_llm / N, 4) if N else 0,
                "fp_rate_veto": round(fp_veto / N, 4) if N else 0,
                "fp_corrected": fp_llm - fp_veto,
            })
    if split != "correct":
        out.update({
            "gate_localization_type_em_among_fired": round(type_hits / fired_err, 4) if fired_err else 0,
            "gate_localization_row_em_among_fired":  round(row_hits / fired_err, 4) if fired_err else 0,
        })
    return out


def print_results(results: dict) -> None:
    for split, r in results.items():
        print(f"\n{'='*68}\n  ABLATION — {split.upper()} (n={r['n']})\n{'='*68}")
        print(f"  Gate fire rate           : {r['gate_fire_rate']:.1%}  "
              f"(LLM calls saved: {r['llm_calls_saved']:.1%})")
        print(f"  Abstention rate          : {r['abstention_rate']:.1%}")
        print(f"  Verified-consistent rate : {r['verified_consistent_rate']:.1%}")
        if r["is_clean_split"] and r["have_llm"]:
            print(f"\n  CLEAN-SPLIT GENERAL JUDGMENT (higher = fewer false alarms):")
            print(f"    Config A  (LLM alone)        : {r['config_A_gen_judgment_em']:.1%}")
            print(f"    Config B  (Stage 0 alone)    : {r['config_B_gen_judgment_em']:.1%}")
            print(f"    Config A+veto (LLM+det. veto): {r['config_Aveto_gen_judgment_em']:.1%}")
            print(f"    → false-positive rate {r['fp_rate_llm']:.1%} → {r['fp_rate_veto']:.1%} "
                  f"({r['fp_corrected']} of {int(r['fp_rate_llm']*r['n'])} false alarms vetoed)")
        else:
            if r["have_llm"]:
                print(f"\n  General Judgment EM (error split):")
                print(f"    Config A  (LLM alone)        : {r['config_A_gen_judgment_em']:.1%}")
                print(f"    Config B  (Stage 0 alone)    : {r['config_B_gen_judgment_em']:.1%}")
                print(f"    Config A+veto                : {r['config_Aveto_gen_judgment_em']:.1%}  "
                      f"(vetoes applied: {r.get('vetoes_applied',0)})")
            if "gate_localization_type_em_among_fired" in r:
                print(f"\n  Stage 0 localization (among fired):")
                print(f"    Type EM : {r['gate_localization_type_em_among_fired']:.1%}")
                print(f"    Row EM  : {r['gate_localization_row_em_among_fired']:.1%}")


def main():
    ap = argparse.ArgumentParser(description="IntelliAudit Stage-0-gate ablation.")
    ap.add_argument("--split", choices=list(LOADERS) + ["all"], default="all")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    graph = TaxonomyGraph(); _ = graph.available
    splits = list(LOADERS) if args.split == "all" else [args.split]
    print(f"\nAblation over {splits} (seed={args.seed}, n={args.n}); "
          f"LLM baseline = {PRED_MODEL} predictions in results/ …")

    results = {}
    for s in splits:
        print(f"  running {s} …")
        results[s] = eval_split(s, graph, args.n, args.seed)

    print_results(results)
    out_path = args.out or os.path.join(RESULTS_DIR, "pipeline_ablation.json")
    json.dump({"seed": args.seed, "n": args.n, "splits": results},
              open(out_path, "w", encoding="utf-8"), indent=2)
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
