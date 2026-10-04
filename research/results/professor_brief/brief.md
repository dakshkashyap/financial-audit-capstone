# Professor briefing: verified development results

**Meeting message:** We completed a reproducible development audit and identified concrete evaluation, retrieval and evidence-validity bottlenecks. We have not demonstrated cheap-model superiority or completed accountant validation.

## 1. Main results table

All four primary conditions attempted the same 48 cases from eight companies (FY2020–2024): 16 clean, 16 detection-only and 16 provisionally citable. Figures use the original strict scoring contract and a 900-completion-token cap per call. Direct conditions are closed-book for standards; the two-call evidence condition extracts supplied evidence before deciding and adds no standards corpus.

| Model | Setup | Valid / 48 | General / 48 | Clean / 16 | Error type / 32 | Error entry / 32 | Topic / 16 | Subtopic / 16 | Full citation / 16 | Input tokens | Output tokens | API latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Opus 5.5 | Direct | 29/48 | 60.4% (29/48) | 25.0% (4/16) | 78.1% (25/32) | 75.0% (24/32) | 68.8% (11/16) | 68.8% (11/16) | 68.8% (11/16) | 1,985 (n=48) | 712 (n=48) | 8.3s (n=48) |
| Qwen3-8B | Direct | 47/48 | 64.6% (31/48) | 0.0% (0/16) | 50.0% (16/32) | 15.6% (5/32) | 0.0% (0/16) | 0.0% (0/16) | 0.0% (0/16) | 1,385 (n=48) | 260 (n=48) | 4.7s (n=48) |
| Qwen3-30B-A3B | Direct | 16/48 | 22.9% (11/48) | 0.0% (0/16) | 21.9% (7/32) | 6.2% (2/32) | 18.8% (3/16) | 18.8% (3/16) | 18.8% (3/16) | 1,391 (n=17) | 447 (n=17) | 1.8s (n=48) |
| Qwen3-30B-A3B | Evidence → decision | 3/48 | 2.1% (1/48) | 0.0% (0/16) | 3.1% (1/32) | 3.1% (1/32) | 6.2% (1/16) | 6.2% (1/16) | 0.0% (0/16) | 1,637 (n=15) | 329 (n=15) | 1.3s (n=48) |

**Definitions:** General = correct overall judgment on all 48 cases. Clean = valid correct judgments on the 16 clean controls. Error type and error entry each require an incorrect judgment and the matching field, on 32 injected cases. Topic/subtopic/full citation require a schema-valid prediction and a full-code prediction matching the respective key level, on 16 citable cases. Full-citation agreement alone does not require joint judgment/type/row correctness. Joint judgment/type/row/full-citation scores are Opus 11/16, Qwen8 0/16, Qwen30 direct 2/16 and Qwen30 evidence 0/16.

**All errors remain visible:** Opus has 29 valid, 18 format-invalid and one empty response. Qwen8 has 47 valid and one invalid. Qwen30 direct has 16 valid, 31 API errors and one invalid. Qwen30 evidence has three valid, 33 API errors and twelve invalid. All 48 cases were attempted in each primary condition; completed data collection includes recorded failures.

**Do not rank model capability from the General column:** an always-incorrect rule gets 32/48 = 66.7% general agreement and 0/16 clean specificity. Qwen8 flags all clean controls; its 64.6% general score is not evidence that it outperforms Opus. Opus primary scores are also depressed by format failures. The Qwen30 rows describe a heavily service-limited run.

**Resource definitions:** tokens are mean summed usage over requested stages per case with complete usage; n is the measured-case count. API latency is summed request duration per attempted case, including fast failures; it excludes pacing/local processing. Do not interpret Qwen30 rate-limit failures as a speed advantage. No resource value is imputed as zero.

**Scientific scope:** scores measure agreement with provisional author labels on synthetic supporting evidence. They do not establish standards applicability, real audit performance or a population ranking. With 16 citation cases, one case changes the displayed score by 6.25 percentage points. Eight company clusters provide limited uncertainty evidence. The old screenshot has different unverified provenance and cannot serve as a before/after comparison.

## 2. Completed engineering result

| Same offline 48-case diagnostic | Original interface | Parser repair + applicability safeguard |
|---|---:|---:|
| Injected errors detected | 0.0% (0/32) | 18.8% (6/32) |
| Joint judgment + type + row | 0.0% (0/32) | 12.5% (4/32) |
| Full citation agreement | 0.0% (0/16) | 0.0% (0/16) |
| Decision abstention | 100.0% (48/48) | 87.5% (42/48) |
| Citation abstention | 100.0% (48/48) | 100.0% (48/48) |

This verifies a parser/interface repair at zero API cost. It uses synthetic component evidence, offline taxonomy and no Stage 2 LLM. It is not an end-to-end model-versus-pipeline comparison. All sixteen clean cases remain decision abstentions; zero emitted false alarms here is not a clean-specificity success. The final citation safeguard withholds every unverified citation; paragraph agreement remains zero.

## 3. Completed retrieval diagnosis

| Candidate source | Provisional target labels present |
|---|---:|
| Gold-row top-eight candidates (oracle diagnostic) | 2/16 (12.5%) |
| Displayed candidate union across all observable rows | 3/16 (18.8%) |
| Unbounded candidate union across all observable rows | 3/16 (18.8%) |
| Anywhere in the complete downloaded 2023 reference linkbase | 6/16 (37.5%) |

The observable-row candidate cache was saved before joining the answer key. Gold-row analysis is explicitly an oracle diagnostic. Broadening top-k alone did not improve coverage in this sample. Ten of sixteen targets are absent from this specific reference metadata; they are not thereby absent from the Codification or invalid. Linkbase presence also does not prove paragraph applicability. This motivates an issue-conditioned, dated authority corpus and evidence applicability checks; the proposed method remains to be tested.

## 4. Demonstration and next measurable milestone

Demo the IntelliAudit blind dashboard: initial judgment → preserved submission → explicit proposal reveal → separate reconciliation. A deterministic twenty-case/five-company revenue-cutoff review pilot is prepared, including ten evidence-withheld variants. Zero accountant reviews are claimed. Source clean/fault pairs are not validated minimal counterfactuals; missing one fact does not prove undecidability.

For actual review, collect all initial judgments and a preselected delayed repeat of 2–4 cases before any proposal reveal. One accountant supports single-expert review and intra-rater repeat consistency. Source accession/unit/period, authority dates/applicability, acceptable proof alternatives and ambiguity must be resolved before freezing gold. The current publication gate correctly blocks all twenty cases.

Next acceptance criterion: every proposed release item has a documented review and disposition; source and authority issues are resolved or explicitly excluded before seeing final model performance. Then freeze a fresh grouped test and compare one frontier family with cheap models under matched evidence/tool access. Keep this inspected 48-case sample as development data.

## Suggested 60-second explanation

> We now have a reproducible 48-case development study with strict metrics and all failures accounted for. Opus agrees with 11 of 16 provisional paragraph labels; the small Qwen model agrees with none and fails every clean control. We repaired an interface defect that now detects six errors in a separate offline diagnostic, but citation performance has not improved. We also found that the entire downloaded reference linkbase contains only six of the sixteen target labels, so candidate reranking alone cannot resolve the current mismatch. We have built a blind, versioned review workflow and twenty narrow review cases. The next milestone is to validate evidence sufficiency and dated accounting applicability with our accountant, then run a frozen matched comparison.

## Questions to expect

- **Have we beaten Opus?** No. No recorded experiment establishes that claim.
- **Is 68.8% an improvement over the old 12.2% pipeline result?** No. It is an Opus direct score on a different verified cohort and metric contract.
- **Why is General so low?** It includes format/API failures, and clean controls expose overcalling. Validity and delivery reliability both affect these system scores.
- **Can we show the 81.25% Opus figure?** Only as an explicitly post-hoc field-level format diagnostic, alongside its original 11/16 strict result. It is not a new pipeline gain.
- **Why not use the structured Opus and Qwen8 follow-ups as headline rows?** Both stopped early after provider errors and changed settings/method. They remain in the existing comparison appendix with missing cases counted.
- **What is novel?** The candidate contribution is evidence sufficiency, alternative acceptable proofs and dated authority under a cost budget. Novelty and effectiveness are still hypotheses; graphs/tools/budgets alone are already in prior work.
- **What can be finished by December?** A defensible narrow reviewed release, reproducible experiments and submission-ready preprint are goals; review completion and venue acceptance remain external dependencies.

## Reproduction and budget

Run `python -m research.build_professor_brief` from the repository root. The builder checks frozen input/key hashes, recomputes every primary metric count from saved predictions, checks table/resource equivalence against recorded traces, and verifies candidate-cache hashes. Matplotlib renders PNG/SVG; no API calls are made. `verification.json` lists exact source hashes. Existing raw outputs and primary reports are preserved.

The recorded ledger subtotal is $1.92078856970, with 67 unpriced responses and $4.230397654 conservatively booked against the $5 development ceiling. The reported subtotal is incomplete and is not an exact account debit. No new model spending was required for this briefing.

Software verification previously recorded: capstone 95 tests; IntelliAudit 85 tests; deterministic pilot rebuild and live desktop/mobile review workflow pass. These are engineering checks. Accountant validation remains pending.

Source map: `../comparison_table.json`; `../../artifacts/pilot/report.json` and predictions/responses; `../../artifacts/phase2/candidate_audit_v3/`. For current IntelliAudit delivery, see `../../handoff/README.md`; its exact review commit is bundled because direct upstream push was rejected.
