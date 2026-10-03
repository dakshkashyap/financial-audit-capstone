"""
AuditBench - main entry point with multi-model support.

Usage:
  # List all available models
  python main.py --model list

  # Run with Ollama (local, free)
  python main.py --model ollama/llama3 --split single_error --n 10
  
  # Run with multiple Ollama models
  python main.py --model ollama/llama3,ollama/qwen2.5 --split single_error --n 10
  
  # Run with Hugging Face (local, free)
  python main.py --model hf/Qwen/Qwen2.5-7B-Instruct --split single_error --n 10
  
  # Dry run (free test)
  python main.py --dry-run --n 8
  
  # Full dataset
  python main.py --model ollama/llama3 --split single_error --n 1484
"""

import argparse, json, os, sys
pass  # repo root already on sys.path when run with -m

from core.parser import load_correct, load_single_error, load_multi_error
from approaches.baseline_auditbench.runner import run_split
from approaches.baseline_auditbench.evaluate import evaluate_file, print_comparison_table
from core.model_backends import MODEL_CONFIGS, list_available_models

from core.paths import RESULTS_DIR   # repo-root results/
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
                    help="Model to use. Use 'list' to see all models, 'all' for default models, or specify model name (e.g., gpt-4, ollama/llama3, qwen/qwen-turbo). Use comma-separated for multiple models.")
    ap.add_argument("--split",     choices=list(SPLITS) + ["all"], default="all")
    ap.add_argument("--dry-run",   action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--seed",      type=int, default=SEED)
    ap.add_argument("--n",         type=int, default=N,
                    help="Samples per split. Use 1484/372/371 for full dataset.")
    args = ap.parse_args()

    # List available models
    if args.model == "list":
        print("\nAvailable models:")
        for backend, model_list in list_available_models().items():
            print(f"\n{backend}:")
            for m in model_list:
                print(f"  - {m}")
        print("\nUsage examples:")
        print("  python main.py --model ollama/llama3 --split single_error --n 10")
        print("  python main.py --model hf/Qwen/Qwen2.5-7B-Instruct --split single_error --n 10")
        print("  python main.py --model ollama/llama3,ollama/qwen2.5 --split single_error --n 10")
        sys.exit(0)

    # Determine which models to run
    if args.model == "all":
        models = DEFAULT_MODELS
    elif args.model == "all-available":
        models = ALL_MODELS
    elif "," in args.model:
        models = [m.strip() for m in args.model.split(",")]
    else:
        models = [args.model]
    
    splits = list(SPLITS) if args.split == "all" else [args.split]

    print(f"\nLoading datasets (seed={args.seed}, n={args.n}) ...")
    datasets = {s: SPLITS[s](seed=args.seed, n=args.n) for s in splits}
    for s, items in datasets.items():
        print(f"  {s}: {len(items)} samples")

    pred_paths = {}
    if not args.eval_only:
        for mdl in models:
            for s, items in datasets.items():
                print(f"\n-- {mdl}/{s} ({'DRY' if args.dry_run else 'LIVE'}, temp=1.0) --")
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
