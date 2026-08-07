# FinMR dataset (local copy)

Source: [TheFinAI/FinMR](https://huggingface.co/datasets/TheFinAI/FinMR)  
Paper: [FinAuditing (arXiv:2510.08886)](https://arxiv.org/abs/2510.08886)

## What’s here

| File | Contents |
|------|----------|
| `test.jsonl` | Full test split (332 rows) |
| `test.parquet` | Same data, parquet |
| `summary.json` | Split stats + sample preview |

Columns per row: `id`, `query`, `dqc_id`, `answer`

Example ground truth in `answer`:
```json
{"extracted_value": "-1284", "calculated_value": "1284"}
```
→ reported value ≠ calculated value (DQC numerical inconsistency).

## Reload from HuggingFace

```bash
source .venv/bin/activate
python -c "from datasets import load_dataset; ds=load_dataset('TheFinAI/FinMR'); print(len(ds['test']))"
```

Or use the repo parser:

```python
from datasets import load_dataset
from finmr_parser import parse_record

ds = load_dataset("TheFinAI/FinMR", split="test")
rec = parse_record(ds[0])
print(rec.dqc_rule, rec.question.concept_bare, rec.gt_extracted, rec.gt_calculated)
```

## Related FinAuditing sets (optional)

```python
load_dataset("TheFinAI/FinSM")  # semantic tag mismatches
load_dataset("TheFinAI/FinRE")  # relationship errors
```
