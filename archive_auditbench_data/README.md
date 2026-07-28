# Archived AuditBench data (baseline only)

**Archived:** July 2026  
**Reason:** Primary evaluation moves to **FinMR** ([TheFinAI/FinMR](https://huggingface.co/datasets/TheFinAI/FinMR), FinAuditing arXiv:2510.08886). AuditBench remains the *historical baseline* used for Stage 0 / over-auditing ablations.

## Contents

| Path | Original role |
|------|----------------|
| `Error_insertion/wrong_table_data.json` | 1484 single-error tables |
| `Error_insertion/wrong_table_data_multiple_errors.json` | 372 multi-error tables |
| `transaction_data/output_transaction_table_pair.json` | 371 clean tables |
| `Raw_table_data/` | Raw S&P-500 company extracts (not required for loaders) |

## How loaders find this

`parser.py` prefers `archive_auditbench_data/` when that directory exists:

```python
_DATA_ROOT = archive_auditbench_data/   # if present
# else project root (legacy layout)
```

Re-run AuditBench evals as before:

```powershell
python stage0_eval.py --n 150
python main.py --model claude-opus-4-6 --split single_error --n 10
```

## Why archive (not delete)

- Stage 0 precision story (clean-split FP ≈ 0–2%) was measured here.
- Paper-vs-paper comparisons in the capstone report still cite these numbers.
- AuditBench citations are GPT-4-generated and version-inconsistent — fine for baseline, **not** for a production citation claim.
