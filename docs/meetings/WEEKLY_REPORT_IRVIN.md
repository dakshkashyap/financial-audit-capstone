# Weekly Report — Irvin

Github repo: https://github.com/dakshkashyap/financial-audit-capstone

> Source of truth for the `.docx` is `scripts/make_weekly_report_docx.py`.
> Edit the `MONTHS` list there and re-run to regenerate `Weekly_Report_Irvin.docx`.

---

## Month of May

| Week | Meeting Date | Meeting minutes | Description of work done during the week |
|---|---|---|---|
| Week 1 | May 15, 2026 | Shared my reading of the professor's paper and where I thought the biggest gap was | Read and analyzed **Automating Financial Statement Audits with Large Language Models** (AuditBench, arXiv:2506.17282), the paper provided by the professor<br>Focused on the weakest reported result — citing the correct accounting standard — and argued it is a design problem rather than a model problem, since the model is recalling rule numbers from memory instead of looking them up |
| Week 2 | May 22, 2026 | Group discussion on dataset collection and the planned meeting with the RBC Borealis engineer on their financial model ATOM | Researched related work in the LLM financial auditing space and the data sources available for real filings (SEC EDGAR)<br>Set up local environment and repo access |
| Week 3 | May 29, 2026 | | Studied retrieval-based and knowledge-graph approaches as a way to ground citations in an authoritative source instead of model memory |

---

## Month of June

| Week | Meeting Date | Meeting minutes | Description of work done during the week |
|---|---|---|---|
| Week 1 | Jun 5, 2026 | Met with Mohsen on Jun 4th | Reviewed the AuditBench replication the team had produced and agreed to take the label-to-concept mapping stage (Stage 1) |
| Week 2 | Jun 12, 2026 | | Studied how the baseline pipeline scores citations, and where an XBRL concept lookup could replace free-text generation |
| Week 3 | Jun 19, 2026 | | Designed the Stage 1 approach: map each statement line-item label to its official XBRL concept so downstream citation lookup has a grounded key to work from |
| Week 4 | Jun 26, 2026 | Took ownership of Stage 1 (label to XBRL concept mapping) | Built the EDGAR Mapper for Stage 1: maps a financial statement line-item label to its official XBRL concept, with an evaluation harness to score it [d2a1cb3](https://github.com/dakshkashyap/financial-audit-capstone/commit/d2a1cb3)<br>Fixed statement-type inference so error splits without a `Sheet_type` field are classified from content instead [0d34c06](https://github.com/dakshkashyap/financial-audit-capstone/commit/0d34c06)<br>Wrote full Stage 1 documentation covering the pipeline, file breakdown, eval results, and integration with Manish's stage [dc48d61](https://github.com/dakshkashyap/financial-audit-capstone/commit/dc48d61) |

---

## Month of July

| Week | Meeting Date | Meeting minutes | Description of work done during the week |
|---|---|---|---|
| Week 1 | Jul 3, 2026 | Shared my written research analysis with the team | Wrote `RESEARCH_ANALYSIS.md`, a professor-facing comparison of three papers against our approach: **AuditBench** (arXiv:2506.17282), **FinAuditing** (arXiv:2510.08886) and **AuditFlow** (arXiv:2606.03031) [7622f73](https://github.com/dakshkashyap/financial-audit-capstone/commit/7622f73)<br>Key takeaway carried into our design: AuditFlow's principle of separating LLM-guided search from deterministic verification, and FinAuditing's use of real XBRL filings with rule-based labels instead of model-written ones<br>Documented the gaps in our own architecture alongside the comparison rather than only the strengths |
| Week 2 | Jul 10, 2026 | | Designed the **Taxonomy Knowledge Agent**: an MCP server wrapping the FASB US-GAAP taxonomy graph so any agent in the pipeline can look up accounting rules through tools and never generate a citation from memory [8fd7d87](https://github.com/dakshkashyap/financial-audit-capstone/commit/8fd7d87)<br>Wrote the next-phase architecture plan adapting AuditFlow's verification principle — agents share a central MCP server holding the verified evidence and cannot bypass the tools [b848a8b](https://github.com/dakshkashyap/financial-audit-capstone/commit/b848a8b)<br>Documented how state is stored and shared across MCP tool calls [04d3f71](https://github.com/dakshkashyap/financial-audit-capstone/commit/04d3f71) |
| Week 3 | Jul 17, 2026 | | Released EDGAR Mapper v2 with its documentation and dataset links [591e5d7](https://github.com/dakshkashyap/financial-audit-capstone/commit/591e5d7)<br>Updated the July meeting notes and the taxonomy MCP agent design [e11f3a2](https://github.com/dakshkashyap/financial-audit-capstone/commit/e11f3a2) |
| Week 4 | Jul 24, 2026 | | Analyzed the FinMR benchmark and how its DQC-rule violations provide root-cause ground truth — a reported value and a calculated value per violation, rather than a pass/fail label [afa52aa](https://github.com/dakshkashyap/financial-audit-capstone/commit/afa52aa) |
| Week 5 | Jul 31, 2026 | Proposed using an MCP server with an AI agent for the citation stage, and how to define "works better" | Built a SEC EDGAR XBRL client to pull real company facts directly from the SEC API, no API key required [a0e8de7](https://github.com/dakshkashyap/financial-audit-capstone/commit/a0e8de7)<br>**Built the Citation MCP agent:** wrapped the TaxonomyGraph in an MCP server exposing `get_candidates`, `validate_citation`, `get_concept_info` and `store_pick`, so an AI agent can only choose from real taxonomy-grounded citations instead of generating them from memory [6a353c5](https://github.com/dakshkashyap/financial-audit-capstone/commit/6a353c5)<br>Wrote a Current vs Proposed architecture brief with diagrams for the professor, plus a diagram-first walkthrough of the TaxonomyGraph and MCP flow [5de40e4](https://github.com/dakshkashyap/financial-audit-capstone/commit/5de40e4) [34b28de](https://github.com/dakshkashyap/financial-audit-capstone/commit/34b28de)<br>Wired up Claude Haiku 4.5 and ran the citation experiment across three conditions — lookup only, AI tool-locked, and an oracle ceiling — on 42 items. Result: **0 invented citations**, 100% of accepted answers verified against the taxonomy, with a written rationale per pick [889922b](https://github.com/dakshkashyap/financial-audit-capstone/commit/889922b) |

---

## Month of August

| Week | Meeting Date | Meeting minutes | Description of work done during the week |
|---|---|---|---|
| Week 1 | Aug 7, 2026 | Presented the AuditPatch pipeline and the three deliverables: explainability, clear methodology, root-cause ground truth | **Built the AuditPatch repair pipeline on FinMR:** detect the rule violation, localize the single fact that caused it, generate a minimal one-value repair, revalidate the whole filing, attach a taxonomy-grounded ASC citation, and emit a machine-checkable certificate [7c43575](https://github.com/dakshkashyap/financial-audit-capstone/commit/7c43575)<br>Ran it on all **332 real SEC filings** in FinMR: 178 repairs proposed, **145 exactly matched ground truth (81.5%)**, **0 regressions**, 1 value changed per repair, 93% carrying a verified citation<br>Wrote a professor brief tying the results to the three deliverables [666bf62](https://github.com/dakshkashyap/financial-audit-capstone/commit/666bf62) and a beginner-friendly presentation walkthrough [6ee78aa](https://github.com/dakshkashyap/financial-audit-capstone/commit/6ee78aa)<br>Documented the LLM explainability experiment in the presentation, including the honest finding that tool-locking removed hallucination but accuracy stayed capped at the 26.2% candidate-list ceiling [ba87b20](https://github.com/dakshkashyap/financial-audit-capstone/commit/ba87b20)<br>Added a short architecture deck framing the six-stage pipeline as the settled contribution, with each stage's method as the part we iterate on [141a697](https://github.com/dakshkashyap/financial-audit-capstone/commit/141a697) |
| Week 2 | Aug 14, 2026 | Meeting cancelled due to unavailability. Met with Mohsen as a group on Aug 13th to share the overall progress and next steps | Prepared for final exams for other courses |
| Week 3 | Aug 21, 2026 | | Related-work review of models fine-tuned for audit and XBRL — AuditWen, FinLoRA, RKEFino1, FinTag, XBRL-Agent — to position our contribution. Finding: existing work reads and tags filings; none localize a root cause, propose a minimal repair, or revalidate it. XBRL-Agent (ICAIF 2024) is the closest precedent for our tool-grounding argument<br>Drafted an evaluation plan for the explanation layer: automatic faithfulness checks on every generated explanation, a reconstruction test as a proxy for usefulness, counterfactual sensitivity, and ablations across no-tools / tools / tools-plus-validation |
| Week 4 | Aug 28, 2026 | | |

---

## Summary of contributions

**Stage 1 — EDGAR Mapper.** Label-to-XBRL-concept mapper with its own evaluation harness and documentation.

**Research analysis.** Written comparison of AuditBench, FinAuditing and AuditFlow against our approach, including an honest section on the gaps in our own architecture.

**Citation MCP agent.** Wrapped the FASB US-GAAP taxonomy in an MCP server so an AI agent must pick from real, verified citations. Measured across three conditions: zero hallucinated citations, every accepted answer verified, and a written justification for each pick.

**AuditPatch pipeline.** End-to-end detect, localize, repair, revalidate, cite and certify on 332 real SEC filings, achieving 81.5% exact repair match with zero regressions.

**Documentation.** Architecture comparison, taxonomy and MCP flow walkthrough, professor brief, full presentation, and the short architecture deck.
