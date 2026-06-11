"""
AuditBench — main entry point.
 
Confirmed settings (Rushi Wang email, June 2026):
  Models      : gpt-3.5-turbo-0125  and  gpt-4-0613
  Temperature : 1.0
  Sample seed : NOT saved by authors → run FULL dataset (--n large)
 
Usage:
  python verify_data.py                                # free preflight
  python main.py --dry-run --n 8                       # free plumbing test
  export OPENAI_API_KEY=sk-...
  python main.py --model gpt-3.5-turbo-0125 --split single_error --n 10   # small test
  python main.py                                       # full run, all models/splits
  python main.py --n 1484 --split single_error         # full single-error set
  python main.py --eval-only                           # re-score existing predictions
"""
 
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
 
from parser import load_correct, load_single_error, load_multi_error
from runner import run_split
from evaluate import evaluate_file, print_comparison_table
from model_backends import MODEL_CONFIGS, list_available_models
 
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
SEED = 42
N    = 150   # paper used 150; authors say full dataset is fine too
 
# Default models (original paper baseline)
DEFAULT_MODELS = ["gpt-3.5-turbo-0125", "gpt-4-0613", "gemini-2.0-flash", "gemini-1.5-pro"]

# All available models from model_backends.py
ALL_MODELS = sorted(MODEL_CONFIGS.keys())
 
SPLITS = {
    "correct":      load_correct,
    "single_error": load_single_error,
    "multi_error":  load_multi_error,
}
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model",     type=str, default="all",
                    help=f"Model to use. Use 'all' for default models, 'all-available' for all models, or specify model name (e.g., gpt-4, ollama/llama3, qwen/qwen-turbo)")
    ap.add_argument("--split",     choices=list(SPLITS) + ["all"], default="all")
    ap.add_argument("--dry-run",   action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--seed",      type=int, default=SEED)
    ap.add_argument("--n",         type=int, default=N,
                    help="Samples per split. Use 1484/372/371 for full dataset.")
    args = ap.parse_args()
 
    if not args.dry_run and not args.eval_only:
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if not openai_key and not gemini_key:
            print("\nERROR: set OPENAI_API_KEY or GEMINI_API_KEY, or use --dry-run.\n"); sys.exit(1)
 
    models = MODELS if args.model == "all" else [args.model]
    splits = list(SPLITS) if args.split == "all" else [args.split]
 
    print(f"\nLoading datasets (seed={args.seed}, n={args.n}) …")
    datasets = {s: SPLITS[s](seed=args.seed, n=args.n) for s in splits}
    for s, items in datasets.items():
        print(f"  {s}: {len(items)} samples")
 
    pred_paths = {}
    if not args.eval_only:
        for mdl in models:
            for s, items in datasets.items():
                print(f"\n── {mdl}/{s} ({'DRY' if args.dry_run else 'LIVE'}, temp=1.0) ──")
                run_split(mdl, s, items, args.seed, dry_run=args.dry_run)
                pred_paths[f"{mdl}_{s}"] = os.path.join(
                    RESULTS_DIR, f"{mdl.replace('/','_')}_{s}_predictions.json")
    else:
        for mdl in models:
            for s in splits:
                p = os.path.join(RESULTS_DIR,
                                 f"{mdl.replace('/','_')}_{s}_predictions.json")
                if os.path.exists(p):
                    pred_paths[f"{mdl}_{s}"] = p
 
    print("\n" + "="*50 + "\nEVALUATION\n" + "="*50)
    all_avg = {}
    for k, p in pred_paths.items():
        if os.path.exists(p):
            all_avg[k] = evaluate_file(p)
 
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "summary.json"), "w") as f:
        json.dump({"seed": args.seed, "n": args.n,
                   "dry_run": args.dry_run, "results": all_avg}, f, indent=2)
    print_comparison_table(all_avg)
 
 
if __name__ == "__main__":
    main()
 