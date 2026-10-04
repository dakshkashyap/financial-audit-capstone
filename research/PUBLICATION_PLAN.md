# Publication plan: work beyond the accountant review

The deliverable is a defensible narrow benchmark and reproducible comparison. A
large accuracy increase is not required for a benchmark contribution; validity,
measured difficulty, unique task coverage and reusable artifacts are required.
The current work is an audited development study. The engineering changes below
prepare a research release; they do not automatically make the study ready for submission.

## Completed in this continuation

| Improvement | Artifact | Evidence |
|---|---|---|
| Offline, read-only reproduction from raw outputs and ledger | `reproduce.py`, `results/reproduction.json` | Primary metrics/resources match; 212 source hashes; fixture bytes match |
| Public input and connected split checks | `integrity.py`, `results/integrity.json` | Public payload passes; groups bind to CIKs; inspected pilot cannot become fresh test; missing final groups block certification |
| Trivial and other-company metadata baselines | `shortcut_baselines.py`, `results/shortcut_baselines.{json,md}` | Always-incorrect 32/48; other-company statement-type prior 7/16 citation agreement |
| Alternative-proof and evidence-acquisition scoring | `evidence_metrics.py`, `EVIDENCE_METRICS.md` | Tests reject unacquired/post-cutoff authority, incorrect citation assertions, wrong-but-flipping pairs, bad budgets and unsupported claims |
| Automated artifact checks | `.github/workflows/research.yml` | Portable local check commands; GitHub CI status must be checked after push |
| A prospective evaluation contract | `evaluation_contract.json` | Explicit nulls/blocked status prevent an unfinished plan being called frozen |

## Steps to take now, excluding accountant scheduling

| Order | Owner | Concrete action | Completion evidence |
|---|---|---|---|
| 1 | Data/provenance | For every final admitted numeric cell, reconstruct one original filing accession and context; record concept, start/end/instant period, unit, decimals, sign and derivation. Reconcile the two audited numeric mismatches and cross-accession conflicts. | Frozen cell/source manifest and exclusion log. Do not replace values from whichever restatement matches best. |
| 2 | Data/evidence | Build a narrow, internally balanced journal/subledger/document set with provenance; mark synthetic supplements. Validate genuine minimally changed clean/fault pairs and missing-evidence controls. | Accounting identities and provenance checks, nuisance-feature balance and documented pair interventions. Existing twenty review candidates are not already such a release. |
| 3 | Method/authority | Assemble an authorized, source-traceable corpus covering the issue, dated scope, conditions, exceptions and transitions. Implement/query issue-based retrieval using observable facts and date/framework. | Corpus/source hashes and retrieval diagnostics. Ten of sixteen old target codes are absent from the downloaded reference metadata; raising top-k alone is insufficient. Secondary handbooks are not silently promoted to canonical authority. |
| 4 | Methods/analysis | Freeze case inventory, reviewed alternatives, connected groups, model IDs, prompts, tools, retries, budgets and analysis before final predictions. Fill every required null in `evaluation_contract.json`. | Signed/dated team protocol and immutable hashes; external preregistration when feasible. Inspected cases remain development. |
| 5 | Evaluation | Resolve provider/schema failures on separate preflight cases. Run the required direct/retrieval/condition-gate ablations with one frontier family and cheap models, matched observable evidence/tool access and one cumulative spend ledger. | Complete intended-case traces, cost/failure reporting, per-company outcomes, joint supported success and selective risk/coverage. No favorable-prefix or best-prompt selection on the final test. |
| 6 | Literature/paper | Establish the precise task difference against AuditBench, FinAuditing, AuditFlow, AuditFraudBench and FinancialAuditBench; test the claimed mechanism with ablations. | Primary-source comparison and reproducible evidence for the claimed contribution. Graphs, tools, budgets and synthetic engagements alone are existing ideas. |
| 7 | Repository owners | Decide contributor permissions and explicit code/data/source licenses. Check public-redistribution rights for all evidence and standard material. | Rights register with source-specific permission/license references. MIT for new research code does not relicense inherited code/data. |
| 8 | Independent teammate | Reproduce a tagged commit in a fresh checkout and report discrepancies. | Consented reproduction log with environment, commands and hashes; author replay and CI are not independent reproduction. |
| 9 | Paper/PI | Finalize authorship/contributions, venue fit, ethics/data statements, limitations and reproducibility appendix; render and inspect the venue-formatted manuscript. | All claims match frozen evidence, target requirements verified, PDF compiled. Native compilation currently fails from an environment error. |

Steps 1–3 and licensing can proceed while review is arranged. Steps 4–5 require a
fully specified admitted corpus and annotation freeze before scored final execution.
No new paid experiment has been run during this continuation.
The full local suite passes 120 tests; this is software verification, not final efficacy.

## Scientific reporting decisions

Use **supported decision success** and clean specificity alongside judgment, citation
and joint localization. Report unsupported assertions, proof recovery, paired-both-
correct outcomes, acquisition units and actual API dollars separately. Include failures
in intended-case denominators. Conditional-on-valid accuracy must state its coverage.
Always-abstain and always-incorrect controls prevent misleading single-score victories.

Company-held-out priors are diagnostic estimates over the selected companies, not
population claims. Five to ten company clusters are a budget-conscious narrow study;
more variants from the same companies do not provide additional independent company
samples. Show per-company counts, sensitivity analyses and modest uncertainty claims.
Do not infer noninferiority from overlapping intervals or a nonsignificant difference.

Do not describe the old 48 cases as a new held-out split after relabeling them. Their
role remains development/retrospective re-evaluation. Keep final event/filing/variant
families together and preserve the original scores if labels are revised.

A novel candidate is the experimentally validated combination of incomplete evidence,
alternative sufficient proofs, dated authority and investigation cost. The new scorer
makes that combination measurable; it does not itself establish task novelty or model
improvement. Prefer a narrow claim with credible evidence to a broad fraud claim on
synthetic presentation errors.

## Current blockers

Excluding accountant review, source admission, a verified applicability corpus, a fresh
complete group manifest, final protocol freeze, matched final experiments, source rights,
independent reproduction and manuscript rendering remain incomplete. The current
integrity report deliberately gives no final-test certificate. A passing artifact replay
is a completed engineering result, not permission to label the benchmark gold-standard.
