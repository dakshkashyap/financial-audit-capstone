# Stage 2 — Focused, evidence-grounded LLM

**Call the model only when the deterministic gate cannot decide, and hand it the
evidence rather than a blank page.**

The AuditBench baseline gives one prompt six jobs at once. Stage 2 is the opposite:
it runs only on items where [`stage0_deterministic_gate`](../stage0_deterministic_gate/)
abstained, and it arrives pre-loaded with what the deterministic stages already
established.

## What the model receives

Three things the baseline never had:

**A verified-consistent flag.** "The arithmetic already checks out." This is the
anti-over-auditing lever — it directly targets the baseline's 50% false-alarm rate
on clean statements by telling the model not to go hunting for a numerical error
that has already been ruled out.

**Any footing mismatches the gate did find.** Partial evidence, even when it was
not enough to fire.

**A per-row grounded citation set.** Candidate ASC topics from
[`stage1_taxonomy_citation`](../stage1_taxonomy_citation/). The model **selects**
from these. It never writes a citation freely, which is what makes citation a
retrieval step rather than a recall step.

## Why it exists

It isolates the question of what the model is actually good for. Once arithmetic
and citation lookup are handled deterministically, the remaining work is judgment
about wording, classification and explanation — the things language models are
genuinely suited to. This stage is where that division of labour is tested.

## Files

| File | Purpose |
|---|---|
| `stage2_llm.py` | The focused prompt and its evidence-grounded call path |
| `enhanced_auditor_prompt.py` | Drop-in richer prompt: few-shot error types, decision tree, standards table |
| `enhance_predictions.py` | Post-processing that normalizes error-type wording to canonical forms |

`enhanced_auditor_prompt.py` is an independent lever — it improves the *baseline*
prompt without changing the architecture, which makes it a useful control when
arguing that architecture rather than prompting is what matters.

## Run it

Stage 2 is normally driven through the pipeline rather than directly:

```bash
python -m approaches.full_pipeline.run_intelliaudit --model claude/claude-haiku-4-5 --n 150
```

Post-process an existing predictions file:

```bash
python -m approaches.stage2_llm_audit.enhance_predictions results/mistral_single_error_predictions.json
```

Requires an API key. See [docs/results/stage2_comparison.md](../../docs/results/stage2_comparison.md)
for measured results.
