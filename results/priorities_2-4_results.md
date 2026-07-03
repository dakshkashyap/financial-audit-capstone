# Priorities 2–4 — implementation + measured results (2026-06-26)

Built before the team starts Stage 2 (LLM). All deterministic, seed=42, n=150.

---

## Priority 4 — end-to-end harness + Stage-0-gate ablation  ✅ (the keystone)

New: **`pipeline.py`** (the single integration point Stage 2 plugs into) and
**`pipeline_eval.py`** (the architecture ablation). The harness emits one
`AuditRecord` per item: judgment, localized error + corrected value, the grounded
citation candidate set (`asc_candidates`), a positive `verified_consistent`
signal, and the evidence trail.

**Ablation result (uses the existing Opus-4.6 run as "LLM alone" — no new API calls).
Config A reproduces summary.json exactly (50.0 / 97.3 / 99.3), confirming alignment.**

| Config | clean General Judgment | single_error | multi_error |
|---|---|---|---|
| A — LLM alone | 50.0% (FP 50%) | 97.3% | 99.3% |
| B — Stage 0 alone (deterministic) | **100.0% (FP 0%)** | 38.0% (gate fires) | 36.0% |
| A+veto — LLM + deterministic veto | **71.3% (FP 28.7%)** | 85.3% | 86.7% |

**Headline:** the deterministic layer **cuts the LLM's clean-table false alarms in
half (50% → 28.7%)** by vetoing LLM "Incorrect" verdicts on tables it has *verified
consistent* (32 of 75 false alarms removed, zero new tools, zero LLM calls).

**Honest tradeoff (also a finding):** the hard veto costs error-split recall
(97.3% → 85.3%) because ~13% of error tables still pass `verified_consistent` —
their error (pure misclassification / no-trace deletion) leaves no arithmetic
signal. Arithmetic consistency is *necessary but not sufficient* for "correct" —
which is exactly the boundary where the Stage-2 LLM earns its place. The sound use
is **evidence-to-LLM** (tell the LLM "arithmetic verified; only weigh
missing/redundant/misclassification"), not a blunt override.

Also reported: gate fire rate 38% (= **38% of LLM calls saved**), abstention 62%,
citation faithfulness 1.0 by construction.

---

## Priority 2 — EDGAR mapper

### 2b. Live SEC EDGAR XBRL filer-tag route  ✅ (new `edgar_xbrl.py`)
Recovers each company's own us-gaap tags via the SEC `companyfacts` API
(company → ticker → CIK → facts, cached under `.cache/edgar/`). Reduces the FinSM
mapping space from ~18,000 concepts to the ~300–1,000 a company actually filed.
Wired into `edgar_mapper.map_statement(item, use_edgar_xbrl=True)`;
`edgar_mapper_eval.py --edgar-xbrl`.

**Result (correct split, n=150):** concept coverage **77.9% → 81.7%**; **367 rows
(11.9%) mapped from filers' own tags** (exact 56 / token 249 / fuzzy 62); unmapped
22.2% → 18.3%.

**Honest limit:** AuditBench uses companies' *custom* presentation labels;
companyfacts exposes *standard* labels, so custom↔standard matching is the residual
challenge (token/fuzzy matching is imperfect). The candidate-restriction idea is
proven; **embedding retrieval (bge-large) over the recovered concept set is the
documented next step** to reach the design doc's 80–95% — and it's the concrete
FinAuditing / FinSM collaboration deliverable. Error splits strip company names, so
this route mainly serves the correct split today.

### 2a. Static concept-map expansion
Deferred in favour of 2b: hand-labelling dozens of concept entries without
domain verification is error-prone; the live-XBRL route closes part of the gap
deterministically and is more defensible. The unmapped backlog is printed by
`edgar_mapper_eval.py` for whoever curates it next.

---

## Priority 3 — Stage 0 coverage  ⚠️ attempted, reverted (a finding in itself)

Tried fuzzy transaction↔table label matching to lift missing-row / numerical
recall. **Measured regression:** coverage rose 0.38 → 0.49 but **precision
collapsed** — Type-EM-among-fired 0.947 → 0.662, and false-positive rate
0.000 → 0.007. On error splits the row indices shift when a row is added/removed,
so only a *strict* label match proves "same row"; fuzzy matching locks onto similar
neighbours and mislabels redundant/missing rows as numerical errors. **Reverted.**

**Takeaway (defensible design decision):** Stage 0 keeps coverage low *on purpose*.
Its value is precision (0% FP, ~95% type accuracy when it fires); the abstain set is
deliberately handed to the LLM. Chasing deterministic recall trades away the
headline. Stage 0 is at its correct operating point.

---

## Files

New: `pipeline.py`, `pipeline_eval.py`, `edgar_xbrl.py`.
Edited: `edgar_mapper.py` (`--edgar-xbrl` route), `edgar_mapper_eval.py`,
`stage0_common.py` (kept `fuzzy_core_match` helper), `stage0a.py` (strict guard +
rationale comment).
Artifacts: `results/pipeline_ablation.json`, `results/edgar_mapper_eval_xbrl.json`.
