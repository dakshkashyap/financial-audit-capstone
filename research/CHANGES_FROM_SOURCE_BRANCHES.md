# What changed from the two source branches

This comparison distinguishes inherited functionality, verified software repairs, and measured diagnostic outcomes. It does not establish that the repaired pipeline beats a frontier model or that provisional citation labels are accounting-valid.

## Exact source baselines

| Source | Pinned commit | Functionality retained |
|---|---|---|
| `daksh/ifrs-pipeline` | [`4a622e0`](https://github.com/dakshkashyap/financial-audit-capstone/commit/4a622e0bd39e19c3a0d6fe6033e14854b107d983) | IFRS framework registry, namespace-aware mapping, IFRS taxonomy loader, tools, prompt switching and original IFRS tests |
| `irvin/citation-full-asc` | [`159ae08`](https://github.com/dakshkashyap/financial-audit-capstone/commit/159ae080dcddedf4a9cee9c5f831bb624d113782) | ASC full-citation candidate selection and plumbing, blind exam entry point and preserved historical analyses |

The integration resolves the Stage 2 conflict by retaining IFRS-aware helpers and ASC candidate handling. Neither branch's historical scores were treated as independently verified accounting accuracy. The original `results/` artifacts remain unchanged.

## Repairs beyond either source snapshot

| Change | Previous behavior | Current behavior and code evidence | Verification |
|---|---|---|---|
| Paragraph scoring | Legacy substring/prefix overlap could count a topic or wrong IFRS paragraph as a citation match. | `core/metrics.py::citation_codes`, `em_citation_exact`, `em_citation_topic` separate full paragraphs from topic/standard agreement. Incomplete first predictions retain their rank. The historical helper remains explicitly labelled. | `CitationMetrics` tests cover wrong paragraphs, cross-framework matches and rank order. |
| Citation postprocessing | `apply_citation_snap` could substitute a heuristic candidate; only the first error was processed. Prompts required a citation even if no candidate fit. | `stage2_llm.py::apply_citation_snap` validates every error, preserves raw output, and abstains on invalid/missing/topic-only picks. Prompts permit null. Candidate membership establishes retrieval provenance only. | `CitationValidation` tests cover multiple errors, unavailable rows, invalid picks and IFRS exact codes. |
| Deterministic citation output | Arithmetic detection promoted `citation_primary` directly to a governing citation. | `AuditRecord.citation_applicability_verified` defaults false. `run_intelliaudit.py::_deterministic_parsed`, `run_iab_exam.py` and `run_audit.py::run_audit` retain reference hints while abstaining from actual citation unless applicability is separately established. No current deterministic checker establishes it. | Applicability regressions; final offline predictions abstain on citation in 48/48 cases. |
| Modern evidence parsing | Stage 0 required historical `[row n]` narratives and missed current `[Label]` component evidence. | `core/stage0_common.py::build_transactions` accepts strictly signed, well-formed component movements; `stage0a.py` reconciles unique labels without original row IDs. Decimal/sign discrepancies are preserved; ambiguous labels and reviewer prose are excluded. | Nine `ComponentEvidence` tests; frozen before/after diagnostic below. |
| Consistency and abstention | Partial arithmetic coverage could override a model's error finding; historical replay counted gate abstention as a clean judgment. | `stage2_llm.py::apply_consistency_veto` additionally requires a complete error-absence certificate. Current callers have none. `pipeline.py` excludes partial component narratives from the old consistency certificate. `pipeline_eval.py::eval_split` retains unverified outcomes. | Partial-coverage and historical-replay regressions. |
| Numeric repair | Global substitution could alter a repeated amount on the wrong row. | `run_intelliaudit.py::_revise` requires one localized row and verifies its full original numeric cell before changing it. | Repeated-value, absent-row and mismatched-value regressions. |
| IFRS paragraph preservation | IFRS enrichment collapsed retrieved paragraph codes into standard names; ASC-only normalization could discard IFRS candidates. | `stage1_arelle.py` retains exact IFRS linkbase codes; `pipeline.py::run_pipeline` bypasses ASC normalization for IFRS. | Existing IFRS tests plus exact-paragraph regression. |
| Legacy evaluation | Exam citation recall divided by all cases, including non-citable cases. Small requested sample sizes could be ignored. Historical replay aligned by order and shortened its denominator. | `run_iab_exam.py::score_preds` uses citable-only denominators, reports unsupported citations and joint detection, retains failures/unverified outcomes and raw Stage 2 outputs. `load_exam` respects sample size. Historical replay requires item-index/table-hash agreement and retains every selected case. | `ExamBoundary` and `HistoricalReplayBoundary` regressions. |

The fresh `research/` harness, manifests, budget ledger, source audits, evidence-acquisition prototype, dashboard and paper are new additions. The old exam runner already projected only statement, transactions, sheet type and company into inference; the current tests verify that existing boundary. Oracle analyses that use gold error type or concept remain historical diagnostics, not deployed model results.

## Measured software improvement and its limits

These are three preserved offline snapshots on the same 48 public inputs from eight companies: 32 injected cases and 16 controls, with 16 provisional citable labels. They use no model calls and a forced-offline static reference map.

| Frozen condition | Detected injected cases | Correct detection + type + row | Full citation agreement | Citation abstention |
|---|---:|---:|---:|---:|
| `legacy_local_offline` | 0/32 | 0/32 | 0/16 | 48/48 |
| `legacy_local_adapted` | 6/32 | 4/32 | 0/16 | 47/48 |
| `legacy_local_adapted_verified_citation` | 6/32 | 4/32 | 0/16 | 48/48 |

The parser repair gives a measured **6/32 versus 0/32 detection improvement** on this interface diagnostic. All 16 controls still receive decision abstentions, so this is not 100% clean accuracy. The intermediate adapted output emitted one unsupported static-map citation; the applicability guard removes it without changing detection. Full citation agreement did not improve. Synthetic amount reconstruction, partial evidence, unvalidated labels and only eight company clusters limit interpretation. These runs are not a paid evaluation of the complete repaired Stage 0/1/2 pipeline.

Artifacts: `research/artifacts/pilot/legacy_local_*_metrics.json` and matching prediction files. The final snapshot's prediction hash and every recorded source hash were checked against the saved files. All earlier snapshots remain available.

## Reconciliation with the user-supplied historical screenshot

The screenshot reports the following percentages. These are **user-supplied historical results, not reproduced results**:

| Model / setting | General | Error type | Error entry | Topic | Subtopic | Full |
|---|---:|---:|---:|---:|---:|---:|
| Opus 5.5 baseline | 99 | 99 | 98 | 100 | 100 | 80.5 |
| Opus 5.5 pipeline | 99 | 96 | 95 | 80.5 | 17.1 | 12.2 |
| GPT-4o baseline | 99 | 63 | 50 | 63.4 | 51.2 | 9.8 |
| GPT-4o pipeline | 99 | 58 | 57 | 56.1 | 31.7 | 12.2 |
| Llama 3.3 70B baseline | 96 | 56 | 45 | 41.5 | 34.1 | 9.8 |
| Llama 3.3 70B pipeline | 98 | 61 | 63 | 63.4 | 17.1 | 12.2 |
| DeepSeek V3.1 baseline | 92 | 66 | 50 | 75.6 | 73.2 | 22 |
| DeepSeek V3.1 pipeline | 97 | 63 | 61 | 75.6 | 29.3 | 12.2 |

The table is consistent with a shared citation bottleneck: every pipeline has 12.2% full citation agreement while detection and localization vary. Candidate restrictions, forced citation selection and postprocessing are plausible mechanisms visible in the source. The table alone does not identify which mechanism caused these particular scores.

I searched the two pinned source snapshots and the merged repository for matching result files/model identifiers. Each `results/` tree contains the same **40 byte-identical JSON artifacts**. Their model fields contain `claude-opus-4-6` in 750 records, one `claude/claude-haiku-4-5` entry and one `mistral` entry. No matching historical Opus 5.5/GPT-4o/Llama 3.3/DeepSeek V3.1 result artifact was found, and no numeric metric leaf matched 12.2%, 80.5%, 0.122 or 0.805. The new Opus 5.5 pilot files under `research/artifacts/` are separate experiments and do not reconstruct the screenshot.

The citation percentages are arithmetically compatible with **41 citable cases**: for example, 33/41 rounds to 80.5%, 7/41 to 17.1%, and 5/41 to 12.2%. Multiples and other rounding possibilities also fit; **41 is an inference, not a verified denominator**. Reproducing the screenshot requires its raw predictions, selected case IDs, exam/key versions, exact model and prompt/configuration, and scorer command. It would be incorrect to apply the older all-case denominator explanation as an established explanation of this screenshot.

## Verification

The final full repository suite passed **95 tests** with `/workspace/.auditbench/venv/bin/python -m unittest discover -s tests -v`; `git diff --check` passed. Verification involved no additional model calls. These tests establish software behavior, not accounting validity, novelty, or frontier-model superiority.

Changed implementation entry points: [citation metrics](../core/metrics.py), [component parser](../core/stage0_common.py), [pipeline](../approaches/full_pipeline/pipeline.py), [Stage 2 validation](../approaches/stage2_llm_audit/stage2_llm.py), [exam scorer](../approaches/full_pipeline/run_iab_exam.py), [historical replay](../approaches/full_pipeline/pipeline_eval.py), and [boundary tests](../tests/test_legacy_boundaries.py).

To inspect the exact implementation differences, run from the repository root:

```bash
git diff 4a622e0bd39e19c3a0d6fe6033e14854b107d983 -- core approaches tests research
git diff 159ae080dcddedf4a9cee9c5f831bb624d113782 -- core approaches tests research
```
