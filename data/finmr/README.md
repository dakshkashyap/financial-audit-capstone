# FinMR (FinAuditing mathematical-reasoning task)

Source: [TheFinAI/FinMR](https://huggingface.co/datasets/TheFinAI/FinMR) · paper [arXiv:2510.08886](https://arxiv.org/abs/2510.08886)

| File | Description |
|------|-------------|
| `finmr_test.parquet` | Full 332-row HuggingFace test split (query + dqc_id + answer + id) |
| `finmr_test_index.json` | Light index (id, dqc_id, answer, query head) for exploration |

```powershell
python download_finmr.py          # re-fetch from HuggingFace
python finmr_loader.py            # sanity check
python eval_finmr.py --manual-only
$env:ANTHROPIC_API_KEY="…"
python eval_finmr.py --n 10 --dqc DQC_US_0015
```

AuditFlow ([arXiv:2606.03031](https://arxiv.org/abs/2606.03031)) evaluates a **67-instance subset** of this task after re-downloading XBRL from SEC EDGAR — not by trusting the inlined query text alone.
