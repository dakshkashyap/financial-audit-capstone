# Release and annotation policy

The new `research/` code is a development artifact. The merged `core/`,
`approaches/`, `docs/`, `data/`, and pre-existing `results/` retain historical
implementations and outputs. Their markdown descriptions are not evidence.
Use the independent reviews, source hashes and newly recorded predictions.

New research software is MIT-licensed under the scope in `LICENSING.md`; this does not grant rights to upstream-derived data. The upstream repositories have no declared license at inspection. Do not
describe their data or inherited implementation as an openly licensed dataset.
Agree code and dataset licensing with the contributors before the public release.
Publish original derived case annotations, scripts and provenance manifests
under explicit licenses; never redistribute proprietary ASC/IFRS paragraph text
without the relevant rights. Public SEC filings do not authenticate synthetic
transaction narratives. FinReflectKG is CC BY-NC 4.0, not an unrestricted source.

A final citation item needs one qualified accountant performing a blind first pass and documented reconciliation,
the governing standard's effective date, accounting framework, applicable
conditions, and the exact facts making the paragraph applicable. Store
acceptable alternatives and justified `no_governing_paragraph` decisions.
Reference-linkbase membership establishes a reference relation only. The canonical
IntelliAudit annotation protocol requires a delayed 10–20% repeat subset. Report
single-expert coverage and intra-rater stability; do not claim inter-rater
validation. Operational dashboard records must be curated into publication records
and pass the release gate; saving a review alone does not validate a case.

Keep full gold, evidence graphs and source-company split assignments outside the
inference interface. Log the inputs actually shown to each model. Hash and freeze
the release and preregister analysis before running a held-out evaluation. Treat
the pilot selected here as development data even when split by company; it is
not a final untouched test set after inspection and iteration.

Release gates: accountant adjudication; complete cell-level accession, period,
unit and transformations; internally consistent journal/subledger evidence;
clean and insufficient-evidence controls; paired counterfactuals; leakage and
memorization baselines; final frozen split; reproducible metrics and costs;
license/redistribution review; dataset card with verified claims only.
