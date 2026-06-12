"""
Stage 3 — Evaluator + results tabulator.
 
Reads prediction files from runner.py, computes all five-stage metrics
(BERTScore batched once per split), and prints Tables 1/2/3 alongside the
paper's numbers.
 
FIX vs. original: BLEU now uses extract_corrected_table() — ONE corrected
table per sample, not a join across errors (which duplicated the table and
crushed BLEU to ~0.50 on multi-error).
"""
 
import argparse
import json
import os
import sys
from typing import Dict
 
from metrics import (
    em_general_judgment, em_error_type, em_error_entry,
    em_standards_topk, bleu_table_revision, success_rate,
    bertscore_batch, extract_pred_errors, extract_corrected_table,
)
 
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
 
 
def evaluate_file(pred_path: str) -> Dict[str, float]:
    with open(pred_path, encoding="utf-8") as f:
        records = json.load(f)
    n = len(records)
    print(f"\n  Evaluating {os.path.basename(pred_path)} ({n} samples) ...")
 
    em_gj, em_ty, em_en = [], [], []
    s1, s5, bleu = [], [], []
    bert_preds, bert_refs = [], []
 
    for rec in records:
        parsed = rec.get("parsed") or {}
        meta = rec.get("item_meta", {})
        gt_errors = meta.get("errors", [])
        gt_judg = meta.get("general_judgement", "Incorrect")
        gt_table = meta.get("gt_table", "")
 
        pred_judg = parsed.get("General Judgment", parsed.get("General Judgement", ""))
        em_gj.append(em_general_judgment(pred_judg, gt_judg))
 
        pred_errors = extract_pred_errors(parsed)
        em_ty.append(em_error_type(pred_errors, gt_errors))
        em_en.append(em_error_entry(pred_errors, gt_errors))
 
        p_res = " ".join(e.get("resolution", "") or "" for e in pred_errors).strip() or "N/A"
        g_res = " ".join(e.get("error_resolution", "") or "" for e in gt_errors).strip() if gt_errors else "N/A"
        bert_preds.append(p_res); bert_refs.append(g_res)
 
        p_cit = " ".join(e.get("citation", "") or "" for e in pred_errors)
        g_cit = " ".join(e.get("standards_citation", "") or "" for e in gt_errors)
        s1.append(em_standards_topk(p_cit, g_cit, k=1))
        s5.append(em_standards_topk(p_cit, g_cit, k=5))
 
        # FIX: one corrected table per sample
        p_corr = extract_corrected_table(parsed)
        bleu.append(bleu_table_revision(p_corr, gt_table))
 
    print("    Computing BERTScore (batched) ...", flush=True)
    bert = bertscore_batch(bert_preds, bert_refs)
 
    all_scores = []
    for i in range(n):
        s = {"em_general_judgment": em_gj[i], "em_error_type": em_ty[i],
             "em_error_entry": em_en[i], "bertscore": bert[i],
             "standards_top1": s1[i], "standards_top5": s5[i], "bleu": bleu[i]}
        s["success_rate"] = success_rate(s)
        all_scores.append(s)
 
    avg = {k: round(sum(s[k] for s in all_scores)/n, 4) for k in all_scores[0]}
    parse_ok = sum(1 for r in records if r.get("parsed"))
    avg["parse_rate"] = round(parse_ok / n, 4)
    scored = pred_path.replace("_predictions.json", "_scores.json")
    with open(scored, "w", encoding="utf-8") as f:
        json.dump({"averages": avg, "per_sample": all_scores}, f, indent=2)
    print(f"    Scores -> {scored}")
    return avg
 
 
PAPER_RESULTS = {
    ("gpt-3.5-turbo-0125", "single_error"): (1.000, 0.764, 0.418, 0.869, 0.137, 0.360, 0.707, 0.025),
    ("gpt-4-0613",         "single_error"): (1.000, 0.899, 0.737, 0.878, 0.262, 0.515, 0.783, 0.041),
    ("gpt-3.5-turbo-0125", "multi_error"):  (1.000, 0.482, 0.349, 0.637, 0.086, 0.265, 0.680, 0.012),
    ("gpt-4-0613",         "multi_error"):  (1.000, 0.752, 0.587, 0.792, 0.193, 0.396, 0.742, 0.030),
    ("gpt-3.5-turbo-0125", "correct"):      (1.000, None, None, None, None, None, None, None),
    ("gpt-4-0613",         "correct"):      (1.000, None, None, None, None, None, None, None),
}
LABELS = [("em_general_judgment","Gen.Judg"),("em_error_type","ErrType"),
          ("em_error_entry","ErrEntry"),("bertscore","BERTScore"),
          ("standards_top1","Std T1†"),("standards_top5","Std T5†"),
          ("bleu","BLEU"),("success_rate","SR"),("parse_rate","Parse%")]
NOTE = ("[+] Standards Citation (Std T1/T5) uses regex FASB-ID extraction, NOT the "
        "paper's private retriever+DB. Not comparable to the paper's Standards columns.")

_SPLIT_SUFFIXES = ("_single_error", "_multi_error", "_correct")

def _model_from_key(key: str) -> str:
    """'claude-sonnet-4-6_single_error' → 'claude-sonnet-4-6' (model ids may
    themselves contain underscores, so strip known split suffixes only)."""
    for suf in _SPLIT_SUFFIXES:
        if key.endswith(suf):
            return key[: -len(suf)]
    return key


def print_comparison_table(all_avg):
    w = 11
    # Collect all unique model names from results + paper
    all_models = list(dict.fromkeys(
        [_model_from_key(k) for k in all_avg] +
        ["gpt-3.5-turbo-0125", "gpt-4-0613"]
    ))
    for split in ["correct", "single_error", "multi_error"]:
        title = {"correct":"Table 1 — Correct","single_error":"Table 2 — Single Error",
                 "multi_error":"Table 3 — Multiple Errors"}[split]
        print(f"\n{'='*105}\n  {title}  (paper: GPT-3.5/GPT-4 on 150 random samples)\n{'='*105}")
        hdr = f"{'Model':<26}{'Src':<9}" + "".join(f"{c[1]:>{w}}" for c in LABELS)
        print(hdr); print("-"*len(hdr))
        for tag in all_models:
            key = f"{tag}_{split}"
            if key in all_avg:
                sc = all_avg[key]
                label = tag[:24]
                print(f"{label:<26}{'[yours]':<9}" + "".join(f"{sc.get(c[0],float('nan')):>{w}.3f}" for c in LABELS))
            pr = PAPER_RESULTS.get((tag, split))
            if pr:
                row = list(pr) + [None] * (len(LABELS) - len(pr))   # pad new columns
                print(f"{'':<26}{'[paper]':<9}" + "".join(f"{v:>{w}.3f}" if v is not None else f"{'—':>{w}}" for v in row))
    print("\n" + NOTE)
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions"); ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    all_avg = {}
    if args.all or not args.predictions:
        files = sorted(f for f in os.listdir(RESULTS_DIR) if f.endswith("_predictions.json"))
        if not files:
            print("No prediction files in results/. Run main.py first."); sys.exit(0)
        for fn in files:
            all_avg[fn.replace("_predictions.json","")] = evaluate_file(os.path.join(RESULTS_DIR, fn))
    else:
        fn = os.path.basename(args.predictions).replace("_predictions.json","")
        all_avg[fn] = evaluate_file(args.predictions)
    print_comparison_table(all_avg)
 
 
if __name__ == "__main__":
    main()