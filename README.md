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

**Stage 0 — deterministic pre-LLM gate (IntelliAudit Phase 2, no API key, $0):**
- `stage0_common.py` — shared layer: typed table DataFrame + transaction "oracle" + subtotal alignment + the `Finding` schema and `combine_findings`.
- `stage0a.py` — **Arithmetic Verifier** (SymPy): Numerical Error + Missing Row.
- `stage0b.py` — **Equation Checker** (pure Python): Redundant Row + Misclassification.
- `stage0_eval.py` — offline harness → `results/stage0_eval.json`.

**Stage 1 — Arelle taxonomy citation enrichment (no API key, $0):**
- `edgar_mapper.py` — EDGAR/XBRL row → concept → static ASC citation mapping.
- `stage1_arelle.py` — taxonomy traversal + section-based parent fallback.
- `taxonomy_graph.py` — cached FASB taxonomy graph.
- `stage1_eval.py` / `stage1_citation_eval.py` — offline citation harnesses.
- `model_backends.py` — optional local-model backends (Ollama, Hugging Face, etc.).

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

## Stage 0 — deterministic pre-LLM gate (IntelliAudit Phase 2)

Two **free, deterministic, no-LLM** stages that localize errors directly from the
parsed table + transaction narrative. They run *before* the LLM and exist to fix
the baseline's **over-auditing problem** (50% false alarms on clean tables): on
clean statements the gate abstains ~98% of the time, and when it fires it is
right ~92% of the time — so it can short-circuit the expensive LLM on the cases
it covers and defer the rest. The existing LLM pipeline is **unchanged**.

- **Stage 0A (`stage0a.py`, SymPy):** recomputes/cross-references values against
  the transaction oracle → **Numerical Error** (with the corrected value) and
  **Missing Row** (with the value + re-insertion position).
- **Stage 0B (`stage0b.py`, pure Python):** accounting identities
  (Assets = Liab + Equity, IS chain, cash-flow sums) + section-anomaly
  localization → **Redundant Row** and **Misclassification**.

```powershell
python stage0_eval.py                         # single_error + correct, n=150 (no API key)
python stage0_eval.py --split single_error --n 1484
python stage0_eval.py --split all --n 400     # adds multi_error
```

Writes `results/stage0_eval.json` and prints coverage, Error Row/Type EM,
correct-value accuracy, a per-error-type breakdown, and the **false-positive
rate** on the clean split.

**Headline (n=400, seed=42):** false-positive rate **0.019**, correct-value
accuracy **0.99**, and among the cases it fires on, **Type EM 0.92 / Row EM
0.86**. Coverage is intentionally partial (~40% of single-error items); the
remainder is left for the later LLM stage. See `todo.md` → *Phase 2 Progress*
for the full breakdown, design rationale, known limitations, and the handoff
contract for downstream stages.

## Stage 1 — Arelle taxonomy citation enrichment (IntelliAudit Phase 2)

Deterministic FASB/ASC citation enrichment on top of the EDGAR Mapper's static
`xbrl_concept_map.json`. No LLM, no API key.

- `edgar_mapper.py` — maps table rows to XBRL concepts and static ASC citations.
- `stage1_arelle.py` — Arelle taxonomy traversal + section-based parent fallback.
- `taxonomy_graph.py` — cached taxonomy graph for concept lookup.
- `stage1_eval.py` — offline harness → `results/stage1_eval.json`.
- `stage1_citation_eval.py` — citation-specific metrics → `results/stage1_citation_eval.json`.
- `enhance_predictions.py` — post-process LLM predictions (error-type normalization).

```powershell
python stage1_eval.py                         # correct split, n=150 (no API key)
python stage1_eval.py --split all --n 200
python stage1_citation_eval.py
```

See `SETUP_FREE_MODELS.md` for optional local-model backends (`model_backends.py`,
`main_original.py`).
