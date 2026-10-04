# Apple-only AuditBench slice

Extracted from Oppugno-Rushi/AuditBench-Benchmarking-LLMs-for-Financial-Auditing
for a quick end-to-end run of our pipeline on one company.

| Split | Count |
|---|---|
| correct (clean statements) | 8 |
| single_error | 20 |
| multi_error | 6 |

Point the loaders here:

```bash
export AUDITBENCH_DATA="$(pwd)/data/apple_only"
```
