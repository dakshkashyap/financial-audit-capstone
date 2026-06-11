# AuditBench Reproduction

End-to-end reproduction of *Automating Financial Statement Audits with Large
Language Models* (arXiv:2506.17282v1), built on the released dataset.

## Files
- `parser.py` — table format parser + the three data loaders (fixed seed).
- `auditor_prompt.py` — system + user prompt, **verbatim from the paper Appendix**.
- `runner.py` — calls the model per sample, logs the exact model snapshot, crash-safe resume.
- `metrics.py` — the five-stage metrics (calibration knobs at the top).
- `evaluate.py` — scores predictions, prints your numbers next to the paper's.
- `verify_data.py` — preflight check; run this first, it's free.
- `main.py` — glue.

## Data (put these 3 files in one folder)
- `wrong_table_data.json`              (1484 single-error tables → Table 2)
- `wrong_table_data_multiple_errors.json` (372 multi-error tables → Table 3)
- `output_transaction_table_pair.json` (371 correct tables → Table 1)

The raw `Raw_table_data/subset1,2` folders are NOT needed — the paired JSON is
the processed input.

## Run
```bash
pip install -r requirements.txt
export AUDITBENCH_DATA=/path/to/folder/with/the/3/jsons

python verify_data.py            # 1. free preflight
python main.py --dry-run --n 8   # 2. free plumbing test (scores trivially 1.0)

export OPENAI_API_KEY=sk-...
python main.py                   # 3. real run: 2 models x 3 splits x 150 samples
# or remove sampling variance entirely:
python main.py --split single_error --n 1484
python main.py --split multi_error  --n 372
```

## What reproduces and what doesn't
- **Reproduces:** General Judgment, Error Type/Entry EM, Error Resolution
  (BERTScore), Table Revision (BLEU), Overall SR — and the qualitative story.
- **Does NOT reproduce:** Standards Citation (paper's FASB DB + retriever were
  not released; this repo uses a regex substitute, flagged with †).
- **Exact decimals won't match anyone:** unknown 150-sample draw + retired
  mid-2025 GPT-4 snapshot. Run the full set and calibrate the BERTScore knobs
  in `metrics.py` (`BERTSCORE_RESCALE`) against the paper's numbers.

## Cost
~$15–35 total for the full six runs, mostly GPT-4. Budget $50.
```
