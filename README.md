# Financial audit research: verified development branch

This branch integrates the IFRS and ASC pipelines and adds a reproducible research workspace with code and source audits. **It is not a validated benchmark
release, and it does not establish that a cheap model beats Opus.**

**Current priority: benchmark first.** Start with [team handoff](research/TEAM_HANDOFF.md).
Paid experiments are paused while one accountant completes the blind pilot in
[IntelliAudit](https://github.com/manmad-web/IntelliAudit/tree/codex/accountant-review-dashboard).
The review implementation is committed locally; its push was blocked by GitHub
permissions. An authorized teammate can apply the [portable update](research/handoff/README.md).
That repository owns annotation and release gates; this one owns method evaluation
and the manuscript. Twenty review candidates are prepared; no expert review is claimed.

Start with `research/`: the source audits, isolated experiment harness, results
dashboard, evidence-acquisition prototype, manuscript draft, and December plan.
All measurements distinguish detection, strict paragraph label agreement,
abstention, clean controls, API failures and cost. Current gold labels are not
equivalent to accountant-verified applicability.

For the professor meeting, use the [verified briefing and talk track](research/results/professor_brief/brief.md)
and [shareable results table](research/results/professor_brief/table.png). Its builder
rechecks every primary metric count from saved predictions and makes no model calls.

Review the [measured comparison table](research/results/comparison_table.md),
[paper draft](research/paper/draft.md), and
[changes from both source branches](research/CHANGES_FROM_SOURCE_BRANCHES.md).
Download and open the self-contained [dashboard](research/dashboard/dist/index.html)
or [eight-slide briefing](research/slides.html) in a browser; neither makes
network requests or needs an API credential.

## Reproduce

The new research tools use Python 3.12+ and the standard library. The inherited
pipeline uses the separate dependencies in `requirements.txt`.

```bash
git clone https://github.com/dakshkashyap/financial-audit-capstone.git
cd financial-audit-capstone
git switch research/evidence-audit-2026
python -m unittest discover -s tests -v
python -m research.harness score --prepared research/artifacts/pilot
python -m research.run_frontier_format_diagnostic --prepared research/artifacts/pilot --score
python -m research.run_qwen8_evidence_diagnostic --prepared research/artifacts/pilot --score
python -m research.diagnose_raw_outputs --prepared research/artifacts/pilot
python -m research.comparison_table
python research/dashboard/build_dashboard.py
python research/dashboard/build_comparison.py
```

Install inherited dependencies before running the full test suite; the new
research tests run with the standard library alone. Scoring cached predictions
requires no model calls. See `research/EXPERIMENT.md` for the exact recorded
commands and model settings.

To independently reproduce selection, clone the source and use a new output
directory; preparation deliberately refuses to overwrite the recorded pilot:

```bash
git clone https://github.com/manmad-web/IntelliAudit.git ../IntelliAudit
git -C ../IntelliAudit checkout 72da89a9e6400bfd1da9041a742f9cdeb00470bc
python -m research.harness prepare --source ../IntelliAudit/data/benchmark --out /tmp/intelliaudit-selection-check
```

Model runs require `OPENROUTER_API_KEY` in the environment or a temporary key file
outside the repository. The new runner limits model IDs to one frontier model
and two cheap Qwen models, records every request, reserves worst-case cost before
each call, and stops at the global dollar cap. Never put credentials in a tracked
file. No results dashboard requires or receives the model API key.

## What was integrated and repaired

`core/` and `approaches/` retain both requested source branches, with explicit
framework handling. Repairs preserve IFRS paragraph candidates, prevent ASC
normalization from erasing IFRS candidates, prevent silent citation guessing,
target numerical repairs to the identified row, and correct citable-only metric
denominators. Strict paragraph scoring is separate from historical topic-prefix
scoring. Partial arithmetic consistency cannot certify error absence.

`research/SOURCES.json` pins exact commits and input hashes. The current upstream
exam differs substantially from the older embedded eight-company data. Do not
compare scores across those versions or extrapolate this development pilot to
financial auditing generally.

## Historical material

Pre-existing `docs/`, `results/`, and embedded `data/` are historical artifacts,
retained for traceability. Their descriptions and outputs may use different
datasets, models, oracle information or permissive metrics. They are not the
results of this study. `research/reviews/` records independently recomputed
findings and the limits of verification. Scripts under the inherited approaches
remain experimental; oracle evaluation modes are not deployment performance.

## Publication and release

The proposal evaluates evidence acquisition under cost, sufficient supporting
proof and citation applicability. Existing papers already cover synthetic audit
engagements, evidence graphs and multi-agent tools, so those alone are not novel.
The prototype is synthetic and has not been independently accountant-validated.

Read `research/RELEASE_POLICY.md` and `research/DECEMBER_PLAN.md`. New research software is MIT-licensed with the scope in `research/LICENSING.md`.
Source repositories had no declared licenses at inspection. Resolve inherited code/data licensing
and standards-text rights before describing this as an openly licensed release.
December is a target for validated artifacts and a submission-ready preprint;
conference acceptance is external to this project.
