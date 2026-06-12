# AuditBench Baseline — Results Analysis & Research Roadmap

Team reference document for the financial audit capstone (Phase 1 baseline + Phase 2 research direction).

**Baseline paper:** [Automating Financial Statement Audits with LLMs](https://arxiv.org/html/2506.17282) (AuditBench)  
**Dataset:** [Oppugno-Rushi/AuditBench-Benchmarking-LLMs-for-Financial-Auditing](https://github.com/Oppugno-Rushi/AuditBench-Benchmarking-LLMs-for-Financial-Auditing)  
**Latest run:** `claude-opus-4-6`, seed=42, n=150 per split, temperature=1.0 (paper-faithful)  
**Results file:** `results/summary.json`

---

## Executive Summary

**Claude Opus 4.6 is a strong AuditBench baseline** — especially on end-to-end success rate and semantic/table repair — but it has a serious **over-auditing problem** on clean tables. That asymmetry (aggressive on errors, noisy on clean data) is exactly where our Phase 2 research (IntelliAudit: Auditor–Defender–Judge + tools) should focus.

**Headline for the professor:**

> We reproduced AuditBench with Claude Opus 4.6 and achieved **12× and 5×** the paper's GPT-4 success rate on single- and multi-error splits, with better error localization and table revision — but **50% false alarms on clean financial statements**, which motivates our neuro-symbolic + multi-agent architecture.

---

## Full Results vs Paper (GPT-4 / GPT-3.5)

| Split | Metric | **Opus 4.6 (ours)** | **Paper GPT-4** | **Paper GPT-3.5** | Verdict |
|-------|--------|---------------------|-----------------|-------------------|---------|
| **Correct** | Gen Judgment | **0.500** | 1.000 | 1.000 | **Major weakness** |
| | Success Rate | 0.000 | — | — | All fail (false alarms) |
| | Parse Rate | 1.000 | — | — | Pipeline OK |
| **Single error** | Gen Judgment | 0.973 | 1.000 | 1.000 | Near match |
| | Err Type | **0.920** | 0.899 | 0.764 | **Beats GPT-4** |
| | Err Entry | **0.820** | 0.737 | 0.418 | **Beats GPT-4** |
| | BERTScore | 0.872 | 0.878 | 0.869 | Match |
| | BLEU | **0.949** | 0.783 | 0.707 | **Large win** |
| | **Success Rate** | **0.500** | 0.041 | 0.025 | **~12× GPT-4** |
| | Standards T1† | 0.333 | 0.262 | 0.137 | Directional only |
| **Multi error** | Gen Judgment | 0.993 | 1.000 | 1.000 | Near match |
| | Err Type | 0.687 | **0.752** | 0.482 | Slightly below GPT-4 |
| | Err Entry | **0.677** | 0.587 | 0.349 | **Beats GPT-4** |
| | BERTScore | **0.872** | 0.792 | 0.637 | **Beats GPT-4** |
| | BLEU | **0.858** | 0.742 | 0.680 | **Beats GPT-4** |
| | **Success Rate** | **0.153** | 0.030 | 0.012 | **~5× GPT-4** |
| | Standards T1† | 0.513 | 0.193 | 0.086 | High (regex metric) |

† **Standards Citation** uses regex FASB-ID extraction in our repo, **NOT** the paper's private retriever + FASB DB. Do **not** claim we beat the paper on Standards until we build a real retriever. See `metrics.py` and `evaluate.py`.

---

## What Is Working Well

### 1. End-to-end audit completion (Success Rate)

Success Rate requires **all five stages** to pass at once:
- General Judgment (exact match)
- Error Type (exact match)
- Error Entry (exact match)
- BERTScore ≥ 0.85
- BLEU ≥ 0.99

| Split | Perfect audits | Opus SR | Paper GPT-4 SR |
|-------|----------------|---------|----------------|
| Single error | 75 / 150 | **50.0%** | 4.1% |
| Multi error | 23 / 150 | **15.3%** | 3.0% |

This aligns with teammate Mixtral results (high SR) but Opus is even stronger on single-error completion.

### 2. Error localization (single-error)

- **Err Type 0.92** and **Err Entry 0.82** beat GPT-4 (0.899 / 0.737).
- Only **4/150** false negatives (said "Correct" when an error exists).
- Main gap: **~27/150** wrong row index — often off-by-one row numbering or reporting a cascading total row instead of the injected error row.

### 3. Table revision quality (BLEU)

- Single: **0.949** avg BLEU; **76/150** samples hit BLEU = 1.0.
- Multi: **0.858** vs GPT-4 **0.742**.
- Opus emits well-formed `[row n]` corrected tables; **Parse Rate = 100%** (JSON extraction works).

### 4. Semantic error explanation (BERTScore)

- **0.872** on both error splits — on par with or above GPT-4 on resolution text quality.

### 5. Multi-error detection

- Opus often finds real inconsistencies beyond the single injected error (helps BERTScore/BLEU).
- Can hurt **Err Type EM** on multi-error (0.687 vs GPT-4 0.752) when it misses one of several GT errors or mislabels one.

---

## Critical Weakness: Over-Auditing on Clean Tables

**Table 1 (correct split): Gen Judgment = 0.500**

- **75/150** tables labeled correct were flagged **Incorrect**.
- Paper GPT-4: **1.000** on this split.
- Success Rate on correct: **0.000** (any false alarm fails the full pipeline).

This is **not a pipeline bug**. Opus performs real reasoning (footing checks, transaction reconciliation) and finds values that look wrong (e.g. `US$ 2730,533` vs expected `730,533`) even when the benchmark marks the table "Correct."

**Research implication:** A production auditor must balance **recall** (find errors) vs **precision** (don't flag clean statements). Our IntelliAudit **Defender + Judge** architecture directly addresses this.

**Correct-split BLEU 0.453** is a side effect: when Opus says "Incorrect," it outputs a "Corrected Statements" string compared to the original GT table, so BLEU drops.

---

## Failure Mode Breakdown (Where Success Rate Is Lost)

### Single error (50% SR → improve the other 50%)

| Bottleneck | Approx. count | Fix direction |
|------------|---------------|---------------|
| Wrong row index | ~27 samples | Symbolic row alignment; constrain to one primary error |
| BLEU just under 0.99 | ~16 samples at 0.99x | Deterministic table rewrite from parsed rows |
| False "Correct" judgment | 4 samples | Lower priority |
| Err type mismatch | ~12 samples | Confusion: Numerical vs Missing Row vs Misclassification |

### Multi error (15.3% SR → 85% fail)

| Bottleneck | Pattern | Fix direction |
|------------|---------|---------------|
| Partial error recovery | Err Type/Entry ~0.68 avg | Multi-step agent: enumerate errors, verify each |
| Low BLEU | ~21 samples BLEU < 0.8 | Incomplete corrected table when many errors |
| Missing error types | 8 samples type ≤ 0.4 | Structured error list + checklist |

Success Rate is **multiplicative** — fixing entry localization alone could push single-error SR from 50% toward ~65–70%.

---

## Comparison to Teammate Mixtral Results

| Area | Mixtral (reported) | Opus 4.6 (ours) |
|------|-------------------|-----------------|
| Multi Error Resolution (BERTScore) | 0.855 | **0.872** |
| Single Error Success Rate | 0.180 | **0.500** |
| Error Type ID | 0.32–0.44 (weak) | **0.920** (strong) |
| Standards Citation | 0.12–0.14 | 0.33 single / **0.51 multi** |

Opus dominates Mixtral on **error type classification** and **success rate**. Mixtral may still win on **cost/latency** for open-weight deployment — run `llama-3.3-70b` / `gpt-oss-120b` on the **same seed=42, n=150** for a fair Pareto chart.

**Note:** Re-verify Mixtral numbers with **Parse Rate** visible — old Gemini run failed with 0% parse (empty API responses). Any baseline must show Parse Rate ≈ 1.0.

---

## Room for Improvement (Ranked by Research Impact)

### Tier 1 — Highest ROI (measurable on AuditBench, 2–4 weeks)

#### 1. Neuro-symbolic verification gate (precision fix for correct split)

Add tools the LLM must call before saying "Incorrect":
- Sum line items → compare to stated totals
- Reconcile transaction narrative → table row values
- Only flag if **deterministic check** fails

**Hypothesis:** Gen Judgment on correct split 0.50 → 0.85+ without hurting single-error recall much.

**Papers:** [AuditFlow](https://arxiv.org/html/2606.03031v1), Program-of-Thoughts / PAL.

#### 2. Structured error enumeration for multi-error

Replace one-shot JSON with a LangGraph loop:
1. List candidate errors
2. Match each to GT error types via transaction evidence
3. Merge into one corrected table

**Hypothesis:** Multi Err Type 0.687 → 0.80+, SR 0.15 → 0.25+.

#### 3. Row-index normalization

GT uses integer row indices; model outputs `"Row 16"`. Failures often from:
- Counting header rows differently
- Reporting downstream total (Row 10) instead of source line (Row 5)

Add post-processor: parse `[row n]` from input, map labels → canonical indices, pick row whose **value** changed vs transactions.

**Hypothesis:** Err Entry 0.82 → 0.90+.

#### 4. Conservative judgment / two-threshold policy

- Stage A: "Any material issue?" (high recall)
- Stage B: Judge confirms with evidence + standards

Maps to **Auditor → Defender → Judge**.

---

### Tier 2 — Domain knowledge (publication story)

#### 5. FASB ASC GraphRAG for Standards Citation

Paper's weakest GPT-4 metric; our regex scores are decent on Opus but not comparable to the paper. Building an **open FASB knowledge graph + retriever** is a **standalone contribution** the authors explicitly call for.

**Papers:** [ComplianceNLP](https://arxiv.org/html/2604.23585v1), [GraphCompliance](https://arxiv.org/pdf/2510.26309), [HybridRAG on finance data](https://aclanthology.org/2025.genaik-1.6.pdf).

#### 6. Error-type confusion analysis

Run confusion matrix over 4 types × 150 samples. Likely confusions:
- **Numerical Error** vs **Missing Row**
- **Misclassification** vs **Redundant Row**

Fine-tune prompts or add lightweight classifier on tool outputs.

---

### Tier 3 — Benchmark & evaluation rigor

#### 7. Full model matrix on seed=42

Same pipeline, n=150:
- [ ] `claude-sonnet-4-6`, `claude-haiku-4-5` (cost ladder)
- [ ] `openai/gpt-oss-120b`, `llama-3.3-70b-versatile` (free open-weight)
- [ ] Re-run Mixtral if API available

One table: **SR vs cost vs latency**.

#### 8. Full dataset (optional)

Authors said seed wasn't saved. For final numbers:
```powershell
python main.py --model claude-opus-4-6 --split single_error --n 1484
python main.py --model claude-opus-4-6 --split multi_error  --n 372
python main.py --model claude-opus-4-6 --split correct      --n 371
```

#### 9. Better table metric

BLEU on raw `[row n]` strings is brittle. Propose **cell-level F1** (row label + value match) using existing `parse_table()` in `parser.py`.

---

## Recommended Next Steps (Timeline)

### Week 1–2: Baseline science ✅ mostly done

- [x] Verify dataset (`python verify_data.py`)
- [x] Opus full run (450 samples, all 3 splits)
- [x] Multi-provider runner (Claude / Groq / OpenRouter / etc.)
- [ ] Error analysis notebook: sample 20 failed SR cases; tag failure (entry / type / bleu / judgment)
- [ ] Run Sonnet + one open-weight model on `--seed 42 --n 150`
- [ ] Write 1-page results memo for professor (use table above)

### Week 3–4: Minimal improvement (first research delta)

- [ ] Implement **TransactionSumTool** + **FootingTool** in LangGraph
- [ ] Re-run **correct split only** — target Gen Judgment > 0.85
- [ ] Ablation: tools on vs off on all 3 splits
- [ ] Document Δ metrics in `results/` and update this file

### Week 5–8: Multi-agent IntelliAudit prototype

- [ ] **Auditor** agent (current prompt + tools)
- [ ] **Defender** agent (argues table is correct; cites transactions)
- [ ] **Judge** agent (final judgment + structured trace)
- [ ] Persist reasoning traces (FastAPI + PostgreSQL per capstone spec)
- [ ] Re-evaluate on AuditBench; report **Δ SR** and **Δ false positive rate**

### Week 9+: Publication path

- [ ] FASB GraphRAG module + released artifact
- [ ] Optional: [FinAuditing](https://arxiv.org/abs/2510.08886) subset for generalization (real SEC XBRL)
- [ ] Target venues: **ICAIF**, **FinNLP workshop**, ACL Findings

---

## Thesis / Paper Angles (Backed by Our Numbers)

1. **"Precision-aware audit automation"** — Opus's 50% false alarm rate on clean tables proves raw LLM auditing is not production-ready without gating; our contribution is the gate + HITL trace.

2. **"Decomposed vs monolithic auditing"** — SR gains from Opus show capability exists; multi-agent decomposition should improve multi-error **type** recall without sacrificing single-error **BLEU**.

3. **"Open reproducibility"** — Release FASB retriever + AuditBench runner + model leaderboard (paper's standards DB was never released).

**Suggested title:** *Tool-Grounded Multi-Agent Auditing Reduces False Positives While Preserving AuditBench Success Rate*

---

## Related Papers (Do Not Confuse)

| Paper | What it is | Use for us? |
|-------|------------|-------------|
| [arXiv:2506.17282](https://arxiv.org/html/2506.17282) | **Our baseline** — financial statement AuditBench | ✅ Reproduce + improve |
| [arXiv:2602.22755](https://arxiv.org/abs/2602.22755) | **Different AuditBench** — AI alignment / hidden behaviors in LLMs | ❌ Not financial audit; useful only for investigator-agent methodology |
| [AuditFlow](https://arxiv.org/html/2606.03031v1) | XBRL + symbolic tools + multi-agent | ✅ Closest related work; position against it |
| [FinAuditing](https://arxiv.org/abs/2510.08886) | Real SEC XBRL benchmark | ✅ Generalization eval |
| [FinRegAgents](https://aixiv.science/abs/aixiv.260228.000002) | Multi-agent RAG + confidence gates | ✅ Architecture inspiration |

---

## How to Run (Quick Reference)

```powershell
pip install --user -r requirements.txt
python verify_data.py

$env:ANTHROPIC_API_KEY="sk-ant-..."
python main.py --model claude-opus-4-6 --split single_error --n 10   # smoke test
python main.py --model claude-opus-4-6                                 # full paper protocol

$env:GROQ_API_KEY="gsk_..."
python main.py --model openai/gpt-oss-120b --split single_error

python main.py --eval-only   # re-score without new API calls
```

Outputs: `results/<model>_<split>_predictions.json`, `_scores.json`, `summary.json`

---

## Meeting Talking Points

**Do say:**
- Reproduced AuditBench end-to-end; Parse Rate 100%
- Opus beats paper GPT-4 on Success Rate (~12× single, ~5× multi), Err Entry, Err Type (single), BLEU, BERTScore (multi)
- 50% false positives on clean tables → motivates Defender/Judge + symbolic tools

**Do not say:**
- We beat the paper on Standards Citation (regex ≠ their FASB DB)
- Mixtral/Gemini numbers without verifying Parse Rate
- arXiv:2602.22755 as financial audit related work

---

## Team Task Checklist

### Data & baseline
- [ ] Everyone runs `verify_data.py` locally
- [ ] One person owns `results/summary.json` updates after each model run
- [ ] Standardize on `--seed 42 --n 150` for all model comparisons

### Analysis
- [ ] Pull 10 single-error SR failures → categorize root cause
- [ ] Pull 10 correct-split false positives → document model reasoning
- [ ] Build confusion matrix for 4 error types

### Engineering (Phase 2)
- [ ] LangGraph scaffold + one deterministic tool (sum checker)
- [ ] Architecture diagram: Auditor / Defender / Judge (for professor meeting)
- [ ] API design sketch for reasoning traces (align with IntelliAudit capstone)

### Writing
- [ ] 1-page baseline results summary
- [ ] Related work section (AuditFlow, FinAuditing, baseline paper)
- [ ] Problem statement: precision vs recall in LLM auditing

---

*Last updated: June 2026 — after Claude Opus 4.6 full baseline run (seed=42, n=150).*
