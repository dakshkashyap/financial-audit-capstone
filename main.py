"""
AuditBench — main entry point.

Paper-faithful settings (Rushi Wang email, June 2026):
  Paper models : gpt-3.5-turbo-0125 and gpt-4-0613 (both retired by OpenAI)
  Temperature  : 1.0
  Sample seed  : NOT saved by authors → run FULL dataset (--n large) or fixed seed 42

Usage (PowerShell):
  python verify_data.py                                  # free preflight
  python main.py --dry-run --n 8                         # free plumbing test

  $env:ANTHROPIC_API_KEY="sk-ant-..."
  python main.py --model claude-sonnet-4-6 --split single_error --n 10   # smoke test
  python main.py --model claude-sonnet-4-6                               # all 3 splits, n=150

  $env:GROQ_API_KEY="gsk_..."                            # free open-weight models
  python main.py --model openai/gpt-oss-120b --split single_error
  python main.py --model llama-3.3-70b-versatile --split multi_error

  python main.py --model claude-sonnet-4-6,openai/gpt-oss-120b   # several at once
  python main.py --eval-only                             # re-score existing predictions
  python main.py --n 1484 --split single_error           # full single-error set
"""

import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))

# Windows consoles often default to cp1252, which cannot print some characters
# that models/metrics emit — never let printing crash a paid run.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

from parser import load_correct, load_single_error, load_multi_error
from runner import run_split, detect_provider, PROVIDERS, _safe_name
from evaluate import evaluate_file, print_comparison_table

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
SEED = 42
N    = 150   # paper used 150; authors say full dataset is fine too

# Default suite for --model all: Claude (paid key) + free open-weight via Groq.
# Any other model id also works, e.g.:
#   claude-opus-4-8, claude-haiku-4-5, moonshotai/kimi-k2-instruct,
#   qwen/qwen3-32b, deepseek-r1-distill-llama-70b, gemini-2.5-flash
DEFAULT_MODELS = [
    "claude-sonnet-4-6",           # anthropic
    "claude-haiku-4-5",            # anthropic (cheap)
    "openai/gpt-oss-120b",         # groq / openrouter (open-weight)
    "llama-3.3-70b-versatile",     # groq (open-weight)
]

SPLITS = {
    "correct":      load_correct,
    "single_error": load_single_error,
    "multi_error":  load_multi_error,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="all",
                    help="Model id, comma-separated list, or 'all' "
                         f"(default suite: {', '.join(DEFAULT_MODELS)})")
    ap.add_argument("--provider", choices=list(PROVIDERS), default=None,
                    help="Force a provider instead of auto-detecting from the model id.")
    ap.add_argument("--split",     choices=list(SPLITS) + ["all"], default="all")
    ap.add_argument("--dry-run",   action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--seed",      type=int, default=SEED)
    ap.add_argument("--n",         type=int, default=N,
                    help="Samples per split. Use 1484/372/371 for full dataset.")
    ap.add_argument("--sleep",     type=float, default=None,
                    help="Seconds between API calls (default: per-provider).")
    args = ap.parse_args()

    models = DEFAULT_MODELS if args.model == "all" else \
             [m.strip() for m in args.model.split(",") if m.strip()]
    splits = list(SPLITS) if args.split == "all" else [args.split]

    # Resolve provider per model and check keys BEFORE spending time/money.
    if not args.dry_run and not args.eval_only:
        runnable = []
        for mdl in models:
            prov = args.provider or detect_provider(mdl)
            env = PROVIDERS[prov]["env"]
            if env and not os.environ.get(env, ""):
                msg = (f"  SKIP {mdl}: provider '{prov}' needs {env} "
                       f"(PowerShell:  $env:{env}=\"...\")")
                if args.model != "all":
                    print(f"\nERROR{msg[6:]}\n"); sys.exit(1)
                print(msg)
            else:
                runnable.append((mdl, prov))
        if not runnable:
            print("\nERROR: no API key found for any requested model. "
                  "Set one of: " + ", ".join(v["env"] for v in PROVIDERS.values() if v["env"])
                  + ", or use --dry-run.\n")
            sys.exit(1)
        models_provider = runnable
    else:
        models_provider = [(m, args.provider or detect_provider(m)) for m in models]

    print(f"\nLoading datasets (seed={args.seed}, n={args.n}) ...")
    datasets = {s: SPLITS[s](seed=args.seed, n=args.n) for s in splits}
    for s, items in datasets.items():
        print(f"  {s}: {len(items)} samples")

    pred_paths = {}
    if not args.eval_only:
        for mdl, prov in models_provider:
            for s, items in datasets.items():
                print(f"\n-- {mdl} [{prov}] / {s} ({'DRY' if args.dry_run else 'LIVE'}, temp=1.0) --")
                try:
                    run_split(mdl, s, items, args.seed, dry_run=args.dry_run,
                              provider=prov, sleep=args.sleep)
                except RuntimeError as e:   # fatal API error (bad key / bad model id)
                    print(f"\nFATAL: {e}\n")
                    sys.exit(1)
                pred_paths[f"{_safe_name(mdl)}_{s}"] = os.path.join(
                    RESULTS_DIR, f"{_safe_name(mdl)}_{s}_predictions.json")
    else:
        for mdl, _ in models_provider:
            for s in splits:
                p = os.path.join(RESULTS_DIR, f"{_safe_name(mdl)}_{s}_predictions.json")
                if os.path.exists(p):
                    pred_paths[f"{_safe_name(mdl)}_{s}"] = p
        if not pred_paths:   # nothing matched → score every predictions file present
            for fn in sorted(os.listdir(RESULTS_DIR)):
                if fn.endswith("_predictions.json"):
                    pred_paths[fn[:-len("_predictions.json")]] = os.path.join(RESULTS_DIR, fn)

    print("\n" + "="*50 + "\nEVALUATION\n" + "="*50)
    all_avg = {}
    for k, p in pred_paths.items():
        if os.path.exists(p):
            all_avg[k] = evaluate_file(p)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": args.seed, "n": args.n,
                   "dry_run": args.dry_run, "results": all_avg}, f, indent=2)
    print_comparison_table(all_avg)


if __name__ == "__main__":
    main()
