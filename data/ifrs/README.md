# IFRS dataset used by the pipeline

These files are the IFRS edition of the IntelliAudit benchmark, copied from
`manmad-web/IntelliAudit` branch `claude/relaxed-brahmagupta-bx70xy`.
The audit pipeline reads them; it does not generate filings.

| File | Role |
| --- | --- |
| `rulebook_ifrs.json` | 23 draft rules. Citations are `IAS 1.66`, `IFRS 15.31`, never ASC. |
| `config.json` | SEC 20-F/40-F filers and years for a future build. |
| `fixtures/ifrs_ref_fixture.xml` | Tiny IFRS reference linkbase used by the offline tests. |
| `IFRS_BUILD.md` | How to build a real exam once a taxonomy zip and SEC facts are available. |

A built exam is not in git. After `scripts/build_benchmark.py` and
`scripts/split_dataset.py` in the IntelliAudit repo, copy
`exam.jsonl`, `answer_key.jsonl`, and `statements_clean.jsonl` into
`data/ifrs/benchmark/`. Then:

```
python -m approaches.stage2_llm_audit.axis_stage2 --framework ifrs --analyze-only
```

Until that exam exists, the pipeline still maps IFRS line labels, selects
IAS/IFRS standards, and reads a reference linkbase from `IFRS_TAXONOMY_ZIP`
or `data/ifrs/ifrs_ref_cache.json`. US-GAAP runs do not read this folder.
