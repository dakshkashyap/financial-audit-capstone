# AuditBench Reproduction

End-to-end reproduction of *Automating Financial Statement Audits with Large
Language Models* (arXiv:2506.17282v1), built on the released dataset — extended
with multi-provider support (Claude / OpenAI / Gemini / Groq / OpenRouter /
Together / local Ollama).

## Files
- `parser.py` — table format parser + the three data loaders (fixed seed).
- `auditor_prompt.py` — system + user prompt, **verbatim from the paper Appendix**.
- `runner.py` — provider routing, retries, crash-safe resume, hardened JSON extraction.
- `metrics.py` — the five-stage metrics (calibration knobs at the top).
- `evaluate.py` — scores predictions, prints your numbers next to the paper's.
- `verify_data.py` — preflight check; run this first, it's free.
- `main.py` — glue.

## Data (already in this repo)
- `Error_insertion/wrong_table_data.json` (1484 single-error tables → Table 2)
- `Error_insertion/wrong_table_data_multiple_errors.json` (372 multi-error tables → Table 3)
- `transaction_data/output_transaction_table_pair.json` (371 correct tables → Table 1)

The raw `Raw_table_data/subset1,2` folders are NOT needed — the paired JSON is
the processed input.

## Setup (Windows PowerShell)
```powershell
pip install --user -r requirements.txt

python verify_data.py            # 1. free preflight (no API key needed)
python main.py --dry-run --n 8   # 2. free plumbing test (scores trivially 1.0)
```

## Models & providers
The runner routes any model id to the right OpenAI-compatible endpoint
automatically (override with `--provider`):

| Provider   | Env var              | Example models                              | Cost |
|------------|----------------------|---------------------------------------------|------|
| anthropic  | `ANTHROPIC_API_KEY`  | `claude-sonnet-4-6`, `claude-haiku-4-5`, `claude-opus-4-8` | paid |
| groq       | `GROQ_API_KEY`       | `openai/gpt-oss-120b`, `llama-3.3-70b-versatile`, `moonshotai/kimi-k2-instruct`, `qwen/qwen3-32b` | free tier (30 RPM / ~6k TPM) |
| openrouter | `OPENROUTER_API_KEY` | any `:free` model id                        | free tier (daily caps) |
| gemini     | `GEMINI_API_KEY`     | `gemini-2.5-flash`, `gemini-2.5-pro`        | free tier |
| openai     | `OPENAI_API_KEY`     | `gpt-4.1`, `gpt-5` (paper's gpt-4-0613 is retired) | paid |
| together   | `TOGETHER_API_KEY`   | open-weight ids                             | paid/free |
| ollama     | — (local server)     | any local model                             | free |

## Run (PowerShell)
```powershell
# Claude — smoke test first, then the paper protocol (150 samples/split)
$env:ANTHROPIC_API_KEY="sk-ant-..."
python main.py --model claude-sonnet-4-6 --split single_error --n 10
python main.py --model claude-sonnet-4-6

# Free open-weight via Groq
$env:GROQ_API_KEY="gsk_..."
python main.py --model openai/gpt-oss-120b --split single_error
python main.py --model llama-3.3-70b-versatile

# Several models in one go / re-score existing predictions
python main.py --model claude-sonnet-4-6,openai/gpt-oss-120b
python main.py --eval-only

# Full dataset instead of the 150-sample draw
python main.py --model claude-sonnet-4-6 --split single_error --n 1484
python main.py --model claude-sonnet-4-6 --split multi_error  --n 372
```

Predictions are written to `results/<model>_<split>_predictions.json` after
every sample (crash-safe; reruns resume and verify each item's identity hash).
Scores land in `..._scores.json` and `results/summary.json`.

## What reproduces and what doesn't
- **Reproduces:** General Judgment, Error Type/Entry EM, Error Resolution
  (BERTScore), Table Revision (BLEU), Overall SR — and the qualitative story.
- **Does NOT reproduce:** Standards Citation (paper's FASB DB + retriever were
  not released; this repo uses a regex substitute, flagged with †).
- **Exact decimals won't match anyone:** unknown 150-sample draw + retired
  GPT snapshots. Run the full set and calibrate the BERTScore knobs in
  `metrics.py` (`BERTSCORE_RESCALE`) against the paper's numbers.
- The `Parse%` column shows the share of responses that produced valid JSON —
  if it is low, every EM metric is depressed mechanically; inspect `raw_text`
  in the predictions file before drawing conclusions about a model.
