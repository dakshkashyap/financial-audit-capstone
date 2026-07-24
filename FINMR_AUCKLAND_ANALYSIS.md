# FinMR (Auckland) — Paper Analysis

**Paper:** FinMR: A Knowledge-Intensive Multimodal Benchmark for Advanced Financial Reasoning  
**Conference:** ICAIF 2025 (ACM International Conference on AI in Finance)  
**Authors:** University of Auckland + Nanyang Technological University  
**DOI:** 10.1145/3768292.3770365

---

## ⚠️ Important Naming Confusion

There are **two completely different datasets** both called "FinMR":

| | This paper (Auckland) | The one we need (TheFinAI) |
|-|----------------------|---------------------------|
| Task | CFA/FRM exam questions with charts and images | XBRL auditing, verify reported numbers |
| Format | Multiple choice questions + financial images | Raw XBRL filing + taxonomy |
| Source | CFA/FRM past exam papers | Real SEC company filings |
| Ground truth | Correct exam answer (A/B/C/D) | DQC rule engine (deterministic) |
| Relevance to us | Low | High |
| HuggingFace | Not publicly available | `TheFinAI/FinMR` |

**We want TheFinAI's FinMR, not this one.**

---

## What This Paper Actually Is

The authors collected 3,200 past exam questions from CFA (Chartered Financial Analyst) and FRM (Financial Risk Management) certification programs — the hardest finance certifications in the world. Each question comes with a financial chart, table, diagram, or graph, and requires the model to reason across both the visual and the text to pick the right answer.

**15 topics covered:** Investment, Quantitative Methods, Valuation, Portfolio Management, Fixed Income, Credit Risk, Derivatives, Economics, and more.

**Two types of questions:**
- 67% Expertise — requires deep financial knowledge (e.g. "What does this portfolio allocation imply about risk tolerance?")
- 33% Math — requires multi-step calculations with financial formulas (e.g. "Calculate the Sharpe ratio from this data")

**Human expert baseline:** A CFA-certified expert scored 91%, FRM expert scored 86%. Average: 88.5%. This is how good a professional human does on this benchmark.

---

## How Well Do AI Models Do?

Best model: **Gemini-2.5-Pro at 54.76%** — only 60% of human expert performance.

| Model | Overall | Math | Expertise |
|-------|---------|------|-----------|
| Human experts | 88.5% | — | — |
| Gemini-2.5-Pro | 54.76% | 54.28% | 55.11% |
| Claude-3.7-Sonnet | 53.91% | 42.91% | 61.83% |
| GPT-4o | 50.00% | 47.25% | 50.68% |
| Deepseek-R1 (text only) | 44.84% | 42.20% | 48.51% |
| Open source (best) | ~37% | ~31% | ~42% |

Every model falls well short of human expert performance. The gap is largest on math reasoning.

---

## What Goes Wrong (Error Analysis)

The paper analyzed why models fail. The breakdown:

- **73% of errors: Image recognition failure** — the model simply cannot read or interpret the financial chart correctly. It cannot extract the right numbers from a graph or understand what a diagram is showing.
- **Question misunderstanding** — models misread the intent of domain-specific questions
- **Wrong formula** — model knows the topic but applies the wrong financial formula
- **Answer not found** — some models get stuck in repetitive reasoning loops and never output a final answer

The image problem is by far the dominant failure. Financial charts (time series, yield curves, option payoff diagrams) require domain-specific visual literacy that current models lack.

---

## What Is Good About This Paper

1. **High quality data** — questions come from real professional certification exams written by domain experts, not scraped from the internet
2. **Human baseline established** — 88.5% is a clear target to aim for
3. **Detailed error categories** — the five error types give a clear roadmap for what to improve
4. **Wide topic coverage** — 15 topics across all major areas of finance
5. **Both image and text** — tests the full multimodal capability

---

## What Is Not Good

1. **The data URL is fake** — the paper says code and data are at `https://FinMR/Code&Data`. That is a placeholder, not a real URL. The dataset is not freely downloadable in a standard way.
2. **Source is student uploads on studocu.com** — the questions were scraped from a student resource site where people upload their past exam papers. Copyright of CFA/FRM exam questions is owned by CFA Institute and GARP, which raises legal questions about redistribution.
3. **Not auditing** — this benchmark has nothing to do with financial statement auditing, error detection, or FASB citations. It is a reading comprehension + exam performance task.
4. **Multiple choice only** — the models just pick A/B/C/D. There is no open-ended generation, no table correction, no citation output.

---

## Can We Use This For Our Project?

**Directly: No.**

Our task is: given a financial statement with an injected error, find the error and cite the FASB accounting rule that was violated. This paper is about: given a CFA exam question with a chart, pick the right answer.

Different input format, different output, different ground truth, different task entirely.

**Indirectly: Marginally.**

The error analysis (especially the 73% image recognition failure rate) reinforces our project's argument that LLMs cannot reliably handle structured financial data without deterministic assistance. But this is a supporting point, not core evidence.

The paper that actually matters for us is **FinAuditing** (arXiv:2510.08886) by TheFinAI group, which has the XBRL auditing dataset on HuggingFace.

---

## Where Is The Data?

**This paper's data:** The URL in the paper is a broken placeholder. The dataset may be available by emailing the authors at sden118@aucklanduni.ac.nz, but it is not freely accessible like TheFinAI's datasets.

**The data we actually want:**
- `https://huggingface.co/datasets/TheFinAI/FinMR` — XBRL auditing FinMR (332 rows)
- `https://huggingface.co/datasets/TheFinAI/FinMR_Sub` — competition subset

---

## One-Line Summary

This FinMR is a CFA/FRM exam question benchmark with images — the best AI model scores 55%, a human expert scores 88%, and the dominant failure is that models cannot read financial charts. Interesting paper, wrong task for our project.

---

*FINMR_AUCKLAND_ANALYSIS.md · irvin/edgar-mapper branch · SFU CS Capstone · July 2026*
