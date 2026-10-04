# Building the IFRS edition (runbook)

The IFRS edition is a separate dataset: `configs/ifrs.json` → `data/ifrs/clean/`,
`data/ifrs/benchmark/`, rulebook `rulebook_ifrs.json`. It shares only the code with
US GAAP. Nothing has been built from real IFRS filings yet; the steps below produce it.

## 1. On a machine with internet (once)
```bash
# SEC files for the approved IFRS filers (trimmed to annual 20-F/40-F facts)
python3 scripts/fetch_raw.py --config configs/ifrs.json --tickers BCE SU VOD NVS \
    --years 2021 2022 2023 --user-agent "Your Name you@university.edu"

# IFRS Accounting Taxonomy: download the zip from ifrs.org yourself, then
python3 scripts/build_ifrs_ref_cache.py ~/Downloads/IFRSAT-<release>.zip
```
Commit `data/raw_snapshot/` and `data/reference/ifrs_ref_cache.json`. Do **not** commit the
taxonomy zip: the cache holds only paragraph identifiers, which is all the build needs, and
the zip's licence and size make it a poor thing to redistribute.

## 2. Anywhere (no network needed)
```bash
python3 scripts/build_benchmark.py      --config configs/ifrs.json --companies BCE SU VOD NVS --years 2021 2022 2023
python3 scripts/split_dataset.py        --config configs/ifrs.json
python3 scripts/check_triviality.py     --config configs/ifrs.json
python3 scripts/make_validation_report.py --config configs/ifrs.json
```
`data/ifrs/benchmark/summary.json` records every targeted company and why any was skipped
(fetch failure, CIK/entity mismatch, no statement buildable). `validation_report.json`
recomputes the counts from the files and records the gate result.

## What to expect, honestly
- Balance sheets only (the IS/CF builders are US-GAAP templates).
- 13 of 23 IFRS rules are `ready`; the rest need IFRS-worded facts or new ops.
- IFRS filers use more company-specific extension concepts than US filers, so expect more
  residual lines; the gate reports the filler share.
- The first run is the first test of the IFRS builder against real filings. Expect to fix
  things (role names, anchors) before the numbers are worth quoting.

## Claims you can and cannot make
- Can: values are SEC-filed IFRS facts; no LLM is used to generate data or ground truth;
  citations marked `linkbase-verified` match a paragraph the IFRS Taxonomy attaches to the
  concept.
- Cannot (until done): "all IFRS citations were cross-checked against the taxonomy". Only
  those tagged `linkbase-verified` were; the rest are `expert-authored-UNVALIDATED` and need
  an accountant.
- Quote company and statement counts from `validation_report.json`, never from a plan.
