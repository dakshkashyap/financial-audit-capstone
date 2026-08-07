# AuditPatch V0

Minimal **detect → patch → revalidate → certificate** loop for numerical errors.

```
Stage 0 finding (row + correct_value)
        ↓
replace_fact_value on that row
        ↓
re-run Stage 0 in a sandbox
        ↓
accept only if violation clears / root row no longer flagged
        ↓
proof certificate (JSON)
```

No LLM in V0. Hybrid LLM proposals come later for semantic tags.

## Run

```bash
source .venv/bin/activate
python -m audit_patch.run_v0 --n 80
```

## Datasets (what we use when)

| Phase | Dataset | Why |
|-------|---------|-----|
| **V0 (now)** | **AuditBench** `Error_insertion/wrong_table_data.json` via `parser.load_single_error` | Local, has injected errors + Stage 0 already computes exact `correct_value` |
| **V1** | **TheFinAI/FinMR** (HuggingFace) | Real XBRL + DQC rules (0015/0117/0126) — repair vs validator |
| **V1b** | Clean SEC companyfacts / Arelle filings + **controlled perturbations** | Known repair target (restore original) |
| Later | Official DQC conformance tests | Deterministic oracle |

V0 does **not** need ASC ground truth. Success = patch accepted + Stage 0 clears.
