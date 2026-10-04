# Reproduce and verify the development artifact

Python 3.12; no credentials or downloads are needed for the recorded artifact replay.
Clone this branch and use a fresh report path:

```bash
git clone --branch research/evidence-audit-2026 https://github.com/dakshkashyap/financial-audit-capstone.git
cd financial-audit-capstone
python -m research.reproduce --output /tmp/audit-reproduction.json
python -m research.integrity --out /tmp/audit-integrity.json
python -m research.shortcut_baselines --output /tmp/audit-shortcuts.json
```

The replay checks 212 committed source hashes, all four primary conditions' raw
valid outputs, regenerated prompts from actual public cases and raw intermediate
extractions, prompt/condition identity, case/stage/request identity, parsed answers,
quote checks, denominators, reported statuses, resource summaries and cumulative
ledger accounting. It also rebuilds the sixteen-case synthetic fixture in memory
and compares its public/private/demo bytes, and checks candidate-reference hashes.
The command refuses to overwrite an existing report and disables socket creation
while replaying. It does not change predictions, scores, costs or old reports.
A failed check returns a nonzero exit code and a machine-readable reason.

This establishes consistency with the committed development snapshot, not cryptographic
proof of authorship or accounting validity. It does not regenerate unavailable SEC
source filings or proprietary standards. Source URLs/hashes are recorded; full
original-accession reconstruction remains a separate admission prerequisite.

`.github/workflows/research.yml` runs the replay, standard-library research tests and
shortcut/integrity reports on branch pushes and relevant PR changes. It receives no
model keys and invokes no model endpoint. A successful CI run does not certify a
held-out split: the present split gate is expected to fail because all 48 cases are
inspected development data without complete filing/event/variant identities. Group
company IDs must match public CIKs; the recorded pilot input hash blocks relabelling
these inspected cases as a fresh test. Other exposure histories still need verification.

To render the professor table, install Matplotlib separately and run
`python -m research.build_professor_brief`. Plotting is not required for artifact
verification. The full inherited pipeline test suite also needs its `requirements.txt`
dependencies (notably pandas/tqdm); the CI artifact job deliberately exercises the
portable research subset and does not claim the full inherited dependency environment.
The current full local suite passes 120 tests; the portable CI subset has 70 tests.

## Independent reproduction record

A teammate must reproduce a tagged commit in a fresh checkout, independently of the
main author's environment. Record commit, Python/OS, exact commands, output hashes,
failures and fixes. This has **not** been completed by the author's repeat replay.
Store the consented reproduction log under `research/results/` before release.
Do not mark this requirement complete based on an automatically generated CI run.
