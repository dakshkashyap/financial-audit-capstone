# FinMR benchmark

**Dataset plumbing and baselines for the real-filing benchmark everything else is
evaluated on.**

FinMR is the mathematical-reasoning task of FinAuditing
([arXiv:2510.08886](https://arxiv.org/abs/2510.08886)): 332 test items built from
real SEC XBRL filings, with violations labeled by official **DQC** (Data Quality
Committee) rules.

## Why this dataset

AuditBench errors are *injected*, so ground truth is perfect but synthetic — a
system could learn the injection pattern rather than the accounting. FinMR errors
are real, and the labels come from published validation rules that real filers are
actually checked against. That makes the ground truth an institutional artifact
rather than anyone's opinion.

Critically, FinMR gives **root-cause** ground truth, not just a pass/fail label.
Each item's answer is:

```json
{"extracted_value": "-1284", "calculated_value": "1284"}
```

The reported value and the value the calculation relationships imply. That names
the offending fact and the correct answer, which is what makes exact-match scoring
possible with no judge model involved.

## Three rule families

| Rule | Checks | Items |
|---|---|---|
| `DQC_US_0015` | Sign consistency — element must not be negative | 110 |
| `DQC_US_0117` | Dimensional aggregation | 120 |
| `DQC_US_0126` | Calculation-tree consistency | 102 |

The same three AuditFlow evaluates on, which keeps our numbers comparable.

## Files

| File | Purpose |
|---|---|
| `download_finmr.py` | Fetch from HuggingFace into `data/finmr/` (parquet + normalized JSON) |
| `finmr_loader.py` | Load and index the benchmark |
| `finmr_eval.py` | Deterministic verifier baseline — joint extract + calculate accuracy |
| `eval_finmr.py` | LLM baseline on FinMR (expensive: prompts are 17k–167k chars) |
| `finmr_auditbench_format.py` | Convert FinMR into AuditBench shape for shared tooling |
| `finmr_taxonomy_citations.py` | Attach taxonomy citations to FinMR concepts |

Record parsing and rule checking are shared, so they live in
`core/finmr_parser.py` and `core/finmr_verifier.py`.

## Run it

```bash
python -m approaches.finmr_benchmark.download_finmr        # ~85 MB into data/finmr/
python -m approaches.finmr_benchmark.finmr_eval            # deterministic baseline
python -m approaches.finmr_benchmark.finmr_taxonomy_citations
python -m approaches.finmr_benchmark.eval_finmr --n 20     # LLM baseline, needs a key
```

## Scoring convention

A prediction counts as correct only when **both** `extracted_value` and
`calculated_value` match — AuditFlow's "Joint ACC". Partial credit would overstate
performance, since getting the reported value right while miscomputing the correct
one is useless to an auditor.

## Cost warning

Each FinMR query stuffs an entire XBRL instance into one prompt, 17k to 167k
characters. A full 332-item run against a frontier model is expensive; `eval_finmr.py`
defaults to a small sample and truncates the instance, and reports an
`answerable%` diagnostic so you can tell a truncation artifact from a real
verifier failure.

Related: [docs/research/FINMR_AUCKLAND_ANALYSIS.md](../../docs/research/FINMR_AUCKLAND_ANALYSIS.md)
and [docs/results/finmr_manual_review.md](../../docs/results/finmr_manual_review.md).
