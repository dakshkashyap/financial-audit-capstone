# IntelliAudit — Meeting report (week of 2026-07-17)

**Audience:** Prof. Tayebi + team  
**Status:** AuditBench archived as baseline; FinMR online; taxonomy MCP server wired; thesis recommendation below.

---

## 1. Action-item status

| Action | Status | Artifact |
|--------|--------|----------|
| Archive AuditBench data (`Error_insertion`, `Raw_table_data`, `transaction_data`) | **Done** | `archive_auditbench_data/` (+ README). `parser.py` still loads from the archive for baseline runs. |
| Locate / download FinMR | **Done** | [TheFinAI/FinMR](https://huggingface.co/datasets/TheFinAI/FinMR) → `data/finmr/finmr_test.parquet` (332 rows) + index JSON. Scripts: `download_finmr.py`, `finmr_loader.py`. |
| Verify AuditFlow dataset availability | **Clarified** | AuditFlow does **not** ship a separate public dump of 67 filings. It uses a **67-instance subset of FinMR**, then **re-downloads the corresponding XBRL packages from SEC EDGAR** and parses US-GAAP taxonomy independently ([arXiv:2606.03031](https://arxiv.org/html/2606.03031v1)). Availability = FinMR metadata ✅ + SEC EDGAR public API ✅ (User-Agent required; no paid key for basic filing download). |
| Taxonomy-graph MCP server | **Done (v1)** | `taxonomy_mcp_server.py` + `.cursor/mcp.json`. Tools smoke-tested: `get_citation`, `get_concepts`, `validate_citation`, `stage0_verify`, `store_finding` / `get_evidence`. Design aligns with `irvin/edgar-mapper:TAXONOMY_MCP_AGENT.md` / `NEXT_PHASE_PLAN.md`. |
| Modern LLM on existing / FinMR data | **Harness ready; API run blocked** | `eval_finmr.py` ready. `ANTHROPIC_API_KEY` was **not set** in this environment → wrote manual review sheet instead (`results/finmr_manual_review.md`). Re-run: `$env:ANTHROPIC_API_KEY="…"; python eval_finmr.py --n 10 --dqc DQC_US_0015`. |
| Manual audit of predictions vs GT | **Started (GT patterns)** | See §3. Full model-vs-GT audit after the smoke run. |
| Short report for next meeting | **This document** | Plus research-direction §5. |

Useful docs already on `origin/irvin/edgar-mapper` (pulled into planning): `NEXT_PHASE_PLAN.md`, `TAXONOMY_MCP_AGENT.md`, `MCP_STORAGE_EXPLAINED.md`, `RESEARCH_ANALYSIS.md`, `EDGAR_MAPPER.md`. Code on that branch for EDGAR mapping is largely already merged / superseded by current `edgar_mapper.py` + `edgar_xbrl.py`; the **architecture docs** are the high-value part.

---

## 2. FinMR — what we actually have

| Field | Content |
|-------|---------|
| Size | **332** test items (~5 MB parquet) |
| Task | Mathematical reasoning on real XBRL context (FinAuditing **FinMR**) |
| Labels | Official **DQC** rule failures (not GPT-4 fiction) |
| Answer format | `{"extracted_value": "…", "calculated_value": "…"}` — **both** must match (Joint ACC) |
| DQC families | `DQC_US_0015` 110 · `DQC_US_0117` 120 · `DQC_US_0126` 102 |
| Query size | ~17k–167k chars of filing + taxonomy text **already inlined** in the HuggingFace row |

**Pattern scan (all 332):** a large share of `DQC_US_0015` cases are clean **sign flips** (`extracted ≈ −calculated`). `0117` / `0126` are aggregation / calculation-tree mismatches — closer to real arithmetic verification work.

**Cost warning:** naive “stuff the whole FinMR query into Claude” is expensive and *not* how AuditFlow evaluates. AuditFlow uses FinMR for tickers/queries/GT, then verifies over **raw SEC XBRL + taxonomy graphs via tools**. Our `eval_finmr.py` is intentionally the naive baseline so we can quantify that gap.

**AuditFlow reference numbers (same task family):** Joint ACC **82.09%** with symbolic env; **17.91%** with LLM-only (deterministic checks removed). That ablation is the single strongest published evidence for our architecture thesis.

---

## 3. Manual / failure-pattern notes (pre-LLM)

From GT + query heads (`results/finmr_manual_review.md`):

1. **Sign consistency (0015)** — model must notice debit/credit / negated presentation; easy to “almost get” if it only copies the reported number and forgets the calc-side sign.
2. **Dimensional aggregation (0117)** — needs axis/member awareness; text-only LLMs fail without a filing graph.
3. **Calculation tree (0126)** — needs parent←children weights from the calculation linkbase; this is exactly Stage-0-style SymPy work, not prose reasoning.
4. **Context length** — middle of the filing gets truncated in any practical single-prompt baseline → silent misses. Tool-using agents avoid this by *fetching* facts, not swallowing the whole filing.

**Implication:** re-labeling AuditBench citations with a newer LLM (~10% lift) does **not** move us toward a product. FinMR’s labels are already DQC-grounded; the bottleneck is **verification machinery**, not label quality.

---

## 4. What the `irvin/edgar-mapper` branch contributes

| Asset | Useful? | How we use it |
|-------|---------|----------------|
| `NEXT_PHASE_PLAN.md` | **Yes — primary** | MCP hub + fast path (Stage 0) / slow path (Auditor–Defender–Judge) |
| `TAXONOMY_MCP_AGENT.md` / `MCP_STORAGE_EXPLAINED.md` | **Yes** | Tool contracts + shared agent state |
| `RESEARCH_ANALYSIS.md` | **Yes** | Paper-by-paper speaking script; gaps list |
| `EDGAR_MAPPER.md` + mapper code | **Partially** | Concepts already in-repo; live XBRL route still the FinSM lever |
| Claiming “4-layer EDGAR mapper solves FinSM” | **Not yet proven** | Current coverage ~78–82% on AuditBench labels; FinMR FinSM is a different (harder) task |

MCP v1 in this repo already exposes: grounded citation, concept map, citation validation, Stage 0 verify, shared findings. Missing vs. the plan: filing-graph tools (`get_fact`, `traverse_calculation`, `check_dqc_rule`) needed for FinMR/AuditFlow-style verification.

---

## 5. Honest research direction (thesis)

### How the papers should sit in the story

| Paper | Role for us | Do **not** treat it as… |
|-------|-------------|-------------------------|
| **AuditBench** (AAAI / arXiv:2506.17282) | *Motivation + baseline.* Proved LLM over-auditing and citation memory failure on simplified tables. Our Stage 0 / veto story lives here. | The dataset to ship a product against. GT citations are GPT-4-generated and version-inconsistent. |
| **FinAuditing** (arXiv:2510.08886) | *Harder, real-world evaluation surface.* FinMR (and FinSM) define what “good” means on real XBRL. | Something we must fully reproduce all three tasks before we have a thesis. |
| **AuditFlow** (arXiv:2606.03031) | ***Architectural baseline / blueprint.*** Symbolic env + multi-agent + typed tools; 82% vs 18% ablation. | A paper we need to “beat on their 67” next week. We should *adapt* the principle, not clone their stack. |

### Recommended thesis (one sentence)

> **IntelliAudit:** a tool-grounded (MCP) neuro-symbolic auditor that verifies real financial reports by separating *search* (agents) from *verification* (taxonomy + filing graphs + deterministic math), targeting **precision on clean filings** and **DQC-style numerical consistency** on FinMR — with PDF support as a later ingestion layer, not the first research bet.

### What to focus on for a *tool* that audits real reports accurately

**Near-term (capstone-credible, 2–4 weeks):**

1. **Eval on FinMR, AuditFlow-style** — metadata from HF; facts from SEC XBRL (`edgar_xbrl.py` / companyfacts + filing packages); score Joint ACC on a 20–67 item subset. Compare: naive LLM (`eval_finmr.py`) vs Stage-0-like calc check vs tool-using agent.
2. **Extend MCP** with filing tools: `get_fact(concept, period)`, `sum_children(concept)`, `dqc_check(rule_id)` — agents may only claim numbers those tools return.
3. **Keep Stage 0 precision story** as the AuditBench chapter (over-auditing fixed) — it is still your strongest original empirical result.
4. **Standards KB** — do not wait for a private FASB DB. Use what you already have: US-GAAP reference linkbase + `concept_citation.py` + `validate_citation`. For narrative ASC text later, add an open ASC retrieval index; until then, **topic-level grounded citation** is the honest claim.

**Do not prioritize (low ROI for the product thesis):**

- Re-labeling AuditBench citations with Claude as the main experiment.
- Chasing AuditBench Success Rate as the headline metric (multiplicative AND-gate + bad citation GT).
- Building PDF OCR / layout parsing **before** XBRL verification works end-to-end. PDF→tables is an ingestion problem; wrong numbers / wrong calc trees are the verification problem. Product path: **XBRL first → PDF via table extraction second**.

**Open questions — recommended answers:**

| Question | Recommendation |
|----------|----------------|
| FinMR vs AuditFlow data? | **FinMR full set for eval breadth; AuditFlow’s 67 as the “fair comparison” subset** once SEC re-download works. Same task family. |
| Missing standards KB? | Ship **linkbase-grounded topic citation** now; optional ASC paragraph RAG later. Don’t block on a closed database. |
| Manual review before trusting agent labels? | Spot-check **20 FinMR items** (mix of 0015/0117/0126) every milestone; DQC GT is already stronger than AuditBench. |
| Hybrid: re-label AuditBench then agent pipeline? | **No as main path.** Optional side study only. |

### Product framing (what you can demo to the professor)

```
PDF or XBRL filing
    → (PDF path later) structure extractor
    → MCP symbolic environment
         • taxonomy graph (static)
         • filing graph (dynamic)
         • stage0 / DQC math tools
    → Fast path: deterministic fix / “verified consistent”
    → Slow path: Auditor ↔ Defender → Judge (tool-bound)
    → Output: verdict + corrected values + grounded ASC topics + evidence trail
```

Success metric for the tool (not AuditBench SR): **precision on clean filings** + **Joint ACC on FinMR DQC cases** + **0% invented citations**.

---

## 6. Next week — concrete checklist

1. Set `ANTHROPIC_API_KEY` and run `python eval_finmr.py --n 10 --dqc DQC_US_0015` → report Joint ACC vs AuditFlow’s 17.9% LLM-only floor.
2. Pull 10 SEC filings for FinMR tickers (User-Agent + EDGAR) into `.cache/edgar/filings/`; prototype `get_fact` MCP tool.
3. Manually score those 10: tool-assisted calc vs GT `calculated_value`.
4. Freeze thesis wording above in `todo.md` / vault Home so the team stops oscillating between AuditBench citation chasing and product goals.
5. Optional: demo MCP tools live in Cursor (`get_citation InventoryNet`, `validate_citation ASC 330`).

---

*Artifacts: `data/finmr/`, `archive_auditbench_data/`, `taxonomy_mcp_server.py`, `eval_finmr.py`, `results/finmr_manual_review.md`, `presentation/IntelliAudit_Report.md`.*
