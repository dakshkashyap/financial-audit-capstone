# Documentation index

Everything written up, grouped by what you want it for.

---

## Start here

| Document | What it gives you |
|---|---|
| [architecture/ARCHITECTURE_OVERVIEW.md](architecture/ARCHITECTURE_OVERVIEW.md) | The short deck: the six-stage architecture we have settled on, and which parts are still moving |
| [presentations/PRESENTATION.md](presentations/PRESENTATION.md) | Full beginner-friendly walkthrough — problem, method, results, the LLM's role |
| [research/RESEARCH_ANALYSIS.md](research/RESEARCH_ANALYSIS.md) | Where we sit against AuditBench, FinAuditing and AuditFlow, including our own gaps |

---

## Research and related work

| Document | Contents |
|---|---|
| [research/RESEARCH_ANALYSIS.md](research/RESEARCH_ANALYSIS.md) | Three-paper comparison: AuditBench ([2506.17282](https://arxiv.org/abs/2506.17282)), FinAuditing ([2510.08886](https://arxiv.org/abs/2510.08886)), AuditFlow ([2606.03031](https://arxiv.org/abs/2606.03031)), plus an honest gap analysis of our own architecture |
| [research/FINMR_AUCKLAND_ANALYSIS.md](research/FINMR_AUCKLAND_ANALYSIS.md) | Why FinMR's DQC labels give root-cause ground truth, and how that differs from pass/fail detection labels |

**Other models in this space** (reviewed, not used): AuditWen
([2410.10873](https://arxiv.org/abs/2410.10873)) is Chinese government auditing on
scraped text with GPT-4-generated labels. FinLoRA
([2505.19819](https://arxiv.org/abs/2505.19819)), RKEFino1
([2506.05700](https://arxiv.org/abs/2506.05700)) and FinTag fine-tune on XBRL for
tagging and extraction. XBRL-Agent (ICAIF 2024) is the closest precedent for our
argument — it adds a retriever and calculator to a base model rather than
retraining. None of them localize a root cause, propose a repair, or revalidate
it.

---

## Architecture and design

| Document | Contents |
|---|---|
| [architecture/ARCHITECTURE_OVERVIEW.md](architecture/ARCHITECTURE_OVERVIEW.md) | Six-stage architecture; fixed questions vs swappable methods |
| [architecture/ARCHITECTURE_COMPARISON.md](architecture/ARCHITECTURE_COMPARISON.md) | Current vs proposed, diagram-led, built for slides |
| [architecture/NEXT_PHASE_PLAN.md](architecture/NEXT_PHASE_PLAN.md) | Multi-agent design with a central MCP server holding verified evidence |
| [architecture/TAXONOMY_MCP_AGENT.md](architecture/TAXONOMY_MCP_AGENT.md) | Design of the taxonomy knowledge agent and its tools |
| [architecture/TAXONOMY_MCP_FLOW.md](architecture/TAXONOMY_MCP_FLOW.md) | Beginner-friendly single-flow walkthrough of the same |
| [architecture/MCP_STORAGE_EXPLAINED.md](architecture/MCP_STORAGE_EXPLAINED.md) | How state is shared across MCP tool calls |
| [architecture/CITATION_MCP_PROPOSAL.md](architecture/CITATION_MCP_PROPOSAL.md) | The original citation-MCP proposal and build plan |
| [architecture/EDGAR_MAPPER.md](architecture/EDGAR_MAPPER.md) | Stage 1 concept mapper: pipeline, files, evaluation |
| [architecture/EDGAR_MAPPER_V2.md](architecture/EDGAR_MAPPER_V2.md) | Second iteration |

---

## Results

| Document | Contents |
|---|---|
| [results/FINMR_RESULTS.md](results/FINMR_RESULTS.md) | **AuditPatch on 332 real filings: 81.5% exact repair, 0 regressions** |
| [results/pipeline_eval_n150.md](results/pipeline_eval_n150.md) | Ablation: what the deterministic gate adds at a fixed model |
| [results/stage2_comparison.md](results/stage2_comparison.md) | Focused Stage 2 LLM vs the baseline prompt |
| [results/priorities_2-4_results.md](results/priorities_2-4_results.md) | Results across the mid-project priorities |
| [results/finmr_manual_review.md](results/finmr_manual_review.md) | Hand review of FinMR items and label quality |

Machine-readable output for every run is in the repo-root [`results/`](../results/)
directory.

---

## Presentations

| Document | Audience |
|---|---|
| [presentations/PRESENTATION.md](presentations/PRESENTATION.md) | Full walkthrough, assumes no accounting or AI background |
| [presentations/PROFESSOR_BRIEF.md](presentations/PROFESSOR_BRIEF.md) | Short brief on the three deliverables: explainability, methodology, root-cause ground truth |
| [presentations/IntelliAudit_Report.md](presentations/IntelliAudit_Report.md) | Written project report |
| [presentations/IntelliAudit_Slides.html](presentations/IntelliAudit_Slides.html) | Slide deck (open in a browser) |

---

## Meetings and planning

| Document | Contents |
|---|---|
| [meetings/WEEKLY_REPORT_IRVIN.md](meetings/WEEKLY_REPORT_IRVIN.md) | Weekly progress log with commit links (`.docx` alongside for Google Docs) |
| [meetings/MEETING_NOTES_JULY2026.md](meetings/MEETING_NOTES_JULY2026.md) | July meeting notes |
| [meetings/MEETING_BRIEF_2026-06-26.md](meetings/MEETING_BRIEF_2026-06-26.md) | Brief prepared for the June 26 meeting |
| [meetings/MEETING_REPORT_2026-07-17.md](meetings/MEETING_REPORT_2026-07-17.md) | Report for the July 17 meeting |
| [meetings/todo.md](meetings/todo.md) | Team roadmap and task list |

Regenerate the weekly report `.docx` after editing:

```bash
python scripts/make_weekly_report_docx.py
```

---

## Setup

| Document | Contents |
|---|---|
| [setup/SETUP_FREE_MODELS.md](setup/SETUP_FREE_MODELS.md) | Running against free local models (Ollama, Qwen, Llama) instead of paid APIs |
| [setup/quick_start.sh](setup/quick_start.sh) | Environment bootstrap script |
