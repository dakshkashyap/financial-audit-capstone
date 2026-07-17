# IntelliAudit — Automated Financial Statement Auditing

**Builds on:** *Automating Financial Statement Audits with Large Language Models* (arXiv:2506.17282)  
**Our contribution:** A multi-stage neuro-symbolic pipeline that replaces LLM guesswork with deterministic code for math and citation, achieving 3–5× improvement in citation accuracy.

---

## How the Input Works — JSON Today, PDF Tomorrow

### Current input format (AuditBench JSON)

The system currently reads from the AuditBench dataset — financial statements stored as structured JSON files. Each entry contains a financial statement table in a tokenized text format:

```
[Tab] Consolidated Balance Sheet from Apple [SEP]
[Time]: September 30, 2023 [SEP]
[row 1]: Cash and cash equivalents | 28,408 [SEP]
[row 2]: Short-term investments    | 31,590 [SEP]
[row 3]: Accounts receivable, net  | 29,508 [SEP]
```

To run the pipeline on this format:
```bash
python stage0_eval.py          # Step 1 — arithmetic verification
python edgar_mapper_eval.py    # Step 2 — concept + citation mapping
python stage1_arelle.py        # Step 3 — taxonomy citation upgrade
```

### How to extend to PDF input

To audit a real PDF financial statement instead of a JSON entry, the only piece that needs to change is the **data ingestion layer** — everything from Stage 0 onward is format-agnostic.

**Step 1 — Extract the table from the PDF:**
```python
import pdfplumber

def pdf_to_auditbench_item(pdf_path: str, statement_type: str) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        # Find the page with the financial statement
        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                table = tables[0]  # take the first table found
                break

    # Convert to AuditBench [row n] format
    rows = []
    for i, row in enumerate(table):
        label = row[0] or ""
        value = row[-1] or ""       # last column = most recent year
        rows.append(f"[row {i+1}]: {label.strip()} | {value.strip()}")

    table_str = f"[Tab] {statement_type} [SEP]\n" + " [SEP]\n".join(rows)

    return {
        "Table": table_str,
        "Sheet_type": statement_type,
        "Company": "",   # extract from PDF header if available
    }
```

**Step 2 — Feed into the existing pipeline (no changes needed):**
```python
from stage0_common import build_table
from edgar_mapper import map_statement

# Works exactly the same as with JSON input
item = pdf_to_auditbench_item("apple_10k.pdf", "Consolidated Balance Sheet")
mapped = map_statement(item)

print(f"Coverage: {mapped.coverage:.1%}")
for row in mapped.rows:
    if row.mapped:
        print(f"  Row {row.row_idx}: {row.label} → {row.concept} | ASC {row.asc_primary}")
```

**What changes:** Only `pdf_to_auditbench_item()` — a ~20-line adapter.  
**What stays the same:** Stage 0, EDGAR Mapper, Stage 1 Arelle, everything downstream.

### Recommended PDF libraries

| Library | Best for | Install |
|---------|----------|---------|
| `pdfplumber` | Tables with clear cell borders | `pip install pdfplumber` |
| `camelot` | Complex multi-column layouts | `pip install camelot-py[cv]` |
| `tabula-py` | Java-backed, high accuracy | `pip install tabula-py` |

For most clean 10-K PDFs, `pdfplumber` is sufficient.

---

## Files

- `parser.py` — table format parser + the three data loaders (fixed seed).
- `auditor_prompt.py` — system + user prompt, **verbatim from the paper Appendix**.
- `runner.py` — provider routing, retries, crash-safe resume, hardened JSON extraction.
- `metrics.py` — the five-stage metrics (calibration knobs at the top).
- `evaluate.py` — scores predictions, prints your numbers next to the paper's.
- `verify_data.py` — preflight check; run this first, it's free.
- `main.py` — glue.

**Stage 0 — deterministic pre-LLM gate (no API key, $0):**
- `stage0_common.py` — shared layer: typed table DataFrame + transaction "oracle" + subtotal alignment + the `Finding` schema and `combine_findings`.
- `stage0a.py` — **Arithmetic Verifier** (SymPy): Numerical Error + Missing Row.
- `stage0b.py` — **Equation Checker** (pure Python): Redundant Row + Misclassification.
- `stage0_eval.py` — offline harness → `results/stage0_eval.json`.

**Stage 1 — EDGAR Mapper + Taxonomy (no API key, $0):**
- `edgar_mapper.py` — maps every row label to its US-GAAP XBRL concept + FASB ASC citation.
- `edgar_mapper_eval.py` — evaluation harness → `results/edgar_mapper_eval.json`.
- `xbrl_concept_map.json` — 216-entry lookup dictionary (label → concept + ASC).
- `company_tickers.json` — 50 company names → SEC ticker symbols.
- `stage1_arelle.py` — upgrades citations using the real FASB taxonomy XML.
- `taxonomy_graph.py` — downloads + parses FASB reference linkbase, traverses concept graph.
- `stage1_citation_eval.py` — citation accuracy harness → `results/stage1_citation_eval.json`.

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

---

## Next Phase — FinMR / AuditFlow Dataset

The team has decided to move beyond AuditBench for the next evaluation phase.
AuditBench's citations were generated by GPT-4 and are internally inconsistent —
the same error type gets different citation numbers across samples.

**Better data is publicly available right now:**

| Dataset | Source | Size | Quality |
|---------|--------|------|---------|
| FinMR | `huggingface.co/datasets/TheFinAI/FinMR` | 332 rows | Real XBRL filings, machine-generated ground truth |
| FinMR_Sub | `huggingface.co/datasets/TheFinAI/FinMR_Sub` | 332 rows | Competition subset |
| AuditFlow test cases | Subset of FinMR + SEC EDGAR re-download | 67 cases | Same data AuditFlow used for its 82% result |

**Download FinMR in one line:**
```python
from datasets import load_dataset
ds = load_dataset("TheFinAI/FinMR")
```

**Reconstruct AuditFlow's 67 cases:**
AuditFlow does not distribute a separate dataset. It uses FinMR metadata (ticker,
audit query, target concept, reporting period) and re-fetches the raw XBRL filing
from SEC EDGAR for each case. No API key required — SEC EDGAR is free and public.

```python
# For each FinMR row, fetch the company's real XBRL filing:
# GET https://data.sec.gov/api/xbrl/companyfacts/CIK{number}.json
```

**Why this matters:** FinMR ground truth is produced by a deterministic DQC
validator, not by a human or GPT-4. The citation answers are consistent. Running
IntelliAudit on this dataset and comparing against AuditFlow's published 82%
is the clearest head-to-head comparison available.
