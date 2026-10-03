# Recorded development experiment

This is exploratory closed-book agreement testing on unvalidated synthetic cases,
not a final benchmark or a claim of accounting correctness. The upstream source
is pinned in `SOURCES.json`. Selection uses SHA-256 ordering with seed 20261002,
eight firms, fiscal years 2020–2024, and six cases per firm: two clean controls,
two detection-only faults and two nominally citable faults. All 48 cases remain
in eligible denominators; only 16 cases enter full-citation agreement.

## Frozen primary protocol

The exact configuration is `config/pilot.json`, prompt version
`diagnostic-evidence-v2`. The primary conditions use the same public statement
and evidence strings, opaque IDs, temperature 0 and a 900-completion-token cap.
Qwen3-8B reasoning is explicitly disabled; the instruct Qwen condition has no
reasoning parameter; Opus uses the provider default. The evidence condition uses
two sequential calls to the same Qwen model and passes verified quotations and
untrusted hypotheses as user data. There is no standards-text retrieval corpus
in this experiment. The only frontier family used is Claude Opus 5.5.

```bash
python -m research.harness prepare --source ../IntelliAudit/data/benchmark --out research/artifacts/pilot
python -m research.harness run --prepared research/artifacts/pilot --condition opus_direct --catalog research/artifacts/model_catalog.json
python -m research.harness run --prepared research/artifacts/pilot --condition qwen8_direct --catalog research/artifacts/model_catalog.json
python -m research.harness run --prepared research/artifacts/pilot --condition qwen30_direct --catalog research/artifacts/model_catalog.json
python -m research.harness run --prepared research/artifacts/pilot --condition qwen30_evidence --catalog research/artifacts/model_catalog.json
python -m research.harness score --prepared research/artifacts/pilot
python -m research.diagnose_raw_outputs --prepared research/artifacts/pilot
python research/dashboard/build_dashboard.py
```

Set `OPENROUTER_API_KEY` outside the repository for paid runs. Root used a mode-600
key file under `/tmp`; it was removed after experiments. Reuse cached
predictions for reproduction instead of paying again. Preparation refuses a
nonempty target. Use a new directory for a new development cohort.

The global `artifacts/api_ledger.jsonl` reserves conservative byte-based input
cost plus bounded completions before each request and enforces a $5 cap. Do not
select another ledger to evade it. Requests serialize under its lock. Provider
price caps and exact returned-model checks prevent expensive or model-changing
fallbacks. Errors/timeouts retain reservations; no automatic retries occur.
Catalogue prices, requests and prompts are hashed in manifests; full API response
texts are retained without credentials. Reported actual USD and reserved upper
bounds are distinct. Missing usage costs are unknown, not zero.

## Protocol checks and format diagnostics

Three preflight requests are retained separately in `pilot_setup_smoke/` and
`pilot_protocol_smoke/`. One Qwen request returned HTTP 429, one Opus response
truncated, and one Qwen8 response parsed. No scores were used to select cases.
The final protocol then restricted quote count/length and froze FY2020–2024.
These calls are included in global spend, not final-condition comparisons.

Strict format failures are retained in primary results. The separate raw-output
diagnostic parses complete single JSON objects only, and reports field agreement
when reason/evidence-format compliance fails. It never repairs truncated JSON or
changes primary outcomes. Textual quote verification is an engineering check,
not accountant validation or evidence entailment.

The explicitly post-hoc Opus format diagnostic used the same planned 48 cases,
with a native schema, low reasoning effort and a 1,200-token completion cap.
It stopped at the first provider failure (HTTP 503): 37 attempted cases, 35 valid
responses, one invalid response and 11 unrequested cases. All 48 remain in their
eligible denominators. Its 11/16 full-label agreement and 13/16 clean specificity
cannot replace the primary baseline: settings changed and missingness follows
the fixed case order. The manifest includes a prospective planning flag; the
report's `execution_summary`, traces and ledger record actual execution.

A separate post-hoc Qwen8 extraction-plus-decision diagnostic used the same
inputs, disabled reasoning, a 900-token cap per call and one-second pacing. It
stopped on HTTP 429 after 11 attempted cases and 18 calls: seven valid decisions,
three invalid responses, one API error and 37 unrequested cases. Its 0/16
full-label agreement is an incomplete service-limited result, not evidence that
staged reasoning is intrinsically worse. Neither diagnostic retried failures.

The final ledger records $1.92078856970 in reported charges, 67 responses without
reported cost, zero unresolved reservations, and $4.230397654 in conservative
reservations across all runs and preflights. Reported charges are incomplete;
the reservations, including failures, remain below the $5 development ceiling.

```bash
python -m research.run_frontier_format_diagnostic --prepared research/artifacts/pilot --score
python -m research.run_qwen8_evidence_diagnostic --prepared research/artifacts/pilot --score
```

## Local pipeline transfer check

`legacy_local_offline` is the preserved original parser diagnostic; it abstained
on all 48 cases. `legacy_local_adapted` adds strict parsing of signed component
movements and detects 6/32 errors (4/32 correct type and row), abstaining on 42/48.
All 16 clean cases still abstain; this is not 100% clean certification. Both give
0/16 full-citation agreement and use zero model calls. Modern partial synthetic
evidence cannot certify a statement universally clean. These results establish
an interface repair, not realistic audit efficacy.

The final `legacy_local_adapted_verified_citation` condition preserves those
detection outcomes and explicitly abstains on citations in all 48 cases. It
requires `citation_applicability_verified` before a deterministic record can
assert a candidate paragraph. The prior adapted artifact is retained, including
its single unsupported default citation, so the repair does not rewrite history.

```bash
python -m research.eval_local_pipeline --prepared research/artifacts/pilot --condition a_new_local_condition
python -m research.evidence_budget --output /tmp/evidence-budget-rebuild
```

The latter is a synthetic software fixture, not an LLM experiment. Its paired
companies, gold graph and simulated acquisition units are separate from actual
filing-derived pilot companies and API dollars.

## Interpretation

Labels lack completed expert adjudication. Some source values combine different
SEC accessions; exact numeric matches do not establish original filing fidelity.
Synthetic movements can reconstruct injected faults. The pilot has 44 distinct
base tables across 48 cases and only eight company clusters. Inspect broad paired
intervals and every company outcome; do not report 48 independent filings or
claim that five to ten companies represent all financial audits. Final efficacy
requires validated source data, dated standards, acceptable alternatives,
independent accounting review and a new frozen company/event-disjoint test.
