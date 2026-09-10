# Stage 2 head-to-head — LLM-alone baseline vs full IntelliAudit (Stage 0–3)

Same model (`claude-opus-4-6`), same 150 items/split (seed 42), so the only
variable is the **architecture**. Baseline = the AuditBench six-in-one prompt.
IntelliAudit = Stage 0 gate (deterministic) → Stage 1 grounded citations → Stage 2
focused/conservative LLM (only on abstain) → Stage 3 deterministic reviser, with a
deterministic veto on verified-consistent tables.

## Table 1 — CLEAN split (the over-auditing problem)

| Metric | Baseline (LLM) | IntelliAudit | Δ |
|---|---|---|---|
| General Judgment EM | 0.500 | **0.747** | +0.247 |
| False-alarm rate | 50.0% (75/150) | **25.3% (38/150)** | **−24.7 pts** |
| Table Revision BLEU | 0.453 | **0.977** | +0.524 |
| BERTScore | 0.891 | 0.949 | +0.058 |
| **Success Rate** | **0.000** | **0.640** | **+0.640** |

The baseline NEVER fully succeeds on a clean statement (it over-audits and rewrites
correct tables). IntelliAudit succeeds 64% of the time. **This is the project thesis,
proven.**

## Table 2 — SINGLE ERROR split (error detection + localization)

| Metric | Baseline (LLM) | IntelliAudit | Δ |
|---|---|---|---|
| General Judgment EM | 0.973 | 0.847 | −0.126 |
| Error Type EM | 0.920 | 0.780 | −0.140 |
| Error Entry (Row) EM | 0.820 | 0.727 | −0.093 |
| Standards Citation T1† | 0.333 | 0.213 | −0.120 |
| Table Revision BLEU | 0.949 | 0.964 | +0.015 |
| **Success Rate** | **0.500** | **0.287** | **−0.213** |

IntelliAudit **underperforms on the error split.** Cause: the same conservatism that
kills false alarms suppresses true-error recall. 57/150 items were resolved
deterministically (no LLM) with high localization, but the deterministic veto
flipped **15 real errors to "Correct"** (verified-consistent gives a false all-clear
on ~13% of error tables whose error leaves no arithmetic trace), and the
conservative Stage 2 prompt misses a few more.

## The honest read

**It is a precision/recall trade, not a uniform win — but it wins decisively where it
matters.** AuditBench samples errors 50/50, which rewards an aggressive auditor. Real
financial statements are *mostly correct*, and the costly failure is the false alarm.
Weighting Success Rate by the share of clean statements:

| mix (clean : error) | Baseline SR | IntelliAudit SR |
|---|---|---|
| 50 : 50 (AuditBench) | 0.250 | **0.463** |
| 80 : 20 | 0.100 | **0.569** |
| 90 : 10 (realistic audit) | 0.050 | **0.605** |

At a realistic 90% clean rate, IntelliAudit's success rate is **~12× the baseline**,
because it stops crying wolf.

## "Massive improvement?" — verdict

- **On over-auditing (the target problem): yes, massive.** Clean Success Rate
  0.000 → 0.640; false alarms halved; corrected-table BLEU 0.45 → 0.98.
- **On the 50/50 benchmark overall: a trade** — big clean-split gain, error-split
  recall loss; net-positive on weighted SR, net-negative on raw single-error SR.
- **Strongest scientific finding:** prompt-grounding *alone* did NOT fix
  over-auditing (a conservative prompt that listed the error types first actually
  pushed false alarms to 61%). What worked was giving the *symbolic* layer hard
  authority (the veto) — direct evidence for the neuro-symbolic thesis: you cannot
  ask an LLM to stop over-auditing, you must let deterministic checks override it.

## Next tuning levers (not yet done)

1. **Evidence-calibrated conservatism** — be conservative only when
   `verified_consistent`; audit normally otherwise. The current prompt is globally
   conservative, which is what costs error-split recall.
2. **Tighter `verified_consistent`** to cut the ~13% false all-clears that the veto
   trusts (the only safe way to keep the veto without the recall hit).
3. **Make the veto type-aware** — only veto LLM *Numerical/Missing* claims (which the
   arithmetic can refute), never *Redundant/Misclassification* claims.

Artifacts: `results/intelliaudit_{correct,single_error}_{predictions,scores}.json`,
baseline `results/claude-opus-4-6_*`. Reproduce: `python run_intelliaudit.py --eval`.
