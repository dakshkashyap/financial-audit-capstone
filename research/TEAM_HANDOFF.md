# Team handoff: benchmark-first research

Status: 4 October 2026 (Pacific). Continue on `research/evidence-audit-2026`.
The [IntelliAudit review branch](https://github.com/manmad-web/IntelliAudit/tree/codex/accountant-review-dashboard)
at commit `99d2fa2514eac1f1d17f7a7b58ad36f7e7e7cb08` is the canonical home for dataset construction, blind accountant review, annotation
schema and release gates. This repository owns methods, evaluation, results and paper.

## What is completed

- Both original ASC/IFRS branches are integrated; strict citation scoring, inference
  boundaries, paragraph preservation and localized numerical repairs were corrected.
- Source/data/pipeline audits and a frozen 48-case, eight-company development comparison
  are recorded. All claims use explicit denominators, abstentions and provider failures.
- The latest offline reference audit finds provisional-key coverage 2/16 in the gold-row
  top-eight set, 3/16 in the displayed all-row union, and 6/16 anywhere in the complete
  downloaded 2023 reference linkbase. The gold-row number is an oracle diagnostic.
  This is reference coverage, not authoritative validity. See `artifacts/phase2/candidate_audit_v3/`.
- IntelliAudit now has a twenty-case/five-company review pilot, default blind dashboard,
  preserved initial judgments, explicit reveal/reconciliation and an annotation release gate.

## What is not completed

No accountant reviews, expert-validated benchmark, final held-out efficacy study,
verified novelty claim, or cheap-model win is established. The wider synthetic
acquisition fixture is a software prototype. The unfinished phase-two method runner
is archived as design material; **no phase-two model calls have run**.

The phase-two 36-case selection (24 inspected development, 12 from two previously
unevaluated companies) is preparation only. It is not the twenty-case accountant
pilot or a validated test set. Do not inspect the replication labels during method
development; custodian-only integrity checks cannot supply prompt/rule hints.

## Results the team may quote

Primary development strict full-citation label agreement: Opus 5.5 11/16,
Qwen3-8B 0/16, Qwen3-30B direct 3/16, Qwen3-30B evidence-first 0/16. Conditions
share 48 cases, but Qwen30 conditions suffer severe provider failures. These are
agreements with provisional keys, not verified accounting correctness. Diagnostic
reruns/settings are separate and cannot replace the primary results.

The ledger contains 253 calls, $1.92078856970 provider-reported charges, 67 unpriced
responses, and $4.230397654 conservative reservations against the original $5
engineering ceiling. Reported charges are not an exact account debit. New paid
runs are paused until accountant review informs a frozen design and cumulative
cost envelope. Only one frontier family is allowed; other model arms must be cheap.

## Next work, in order

1. Dataset custodian and accountant execute the IntelliAudit blind pilot. Lock all
   initial judgments before any proposal reveal; preserve revisions and ambiguity.
2. Data owner resolves accession/units/periods and evidence realism. Annotation owner
   records dated authority, acceptable citations and sufficient proof alternatives.
3. Method owner freezes issue-conditioned authority retrieval and condition-checking
   ablations, matched tool access, exact model IDs, provider preflights and budget.
4. Analysis owner freezes group-disjoint cases and metrics before predictions. A case
   seen during design remains development even if assigned a new split name.
5. Teammate reproduces the tagged artifact; paper and licensing review close release gates.

One accountant gives single-expert review, not inter-rater validation. A delayed
10–20% repeat subset can measure intra-rater consistency only. Five to ten companies
keep work affordable but cannot establish broad accounting generalization.

## Team reading order

`README.md` → this handoff → upstream `docs/ANNOTATION_PROTOCOL.md` →
`NEXT_EXPERIMENT.md` → `DECEMBER_PLAN.md` → `RELEASE_POLICY.md` →
`paper/draft.md`. Use `results/comparison_table.md` / `comparison.png` for measured
results and `CHANGES_FROM_SOURCE_BRANCHES.md` for code changes. Historical source
READMEs and screenshot percentages are not current validated evidence.

`REVIEW_WORKFLOW_SOURCE.json` pins the new review toolkit and hashes. Historical
experiment `SOURCES.json` remains pinned to its original source; do not rewrite
old provenance to the new review commit.
