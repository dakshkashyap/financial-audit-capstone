# EDGAR Mapper v2

**File:** `edgar_mapper_v2.py`  
**Author:** Team  
**Replaces:** `edgar_mapper.py` (v1)  
**SFU Capstone — IntelliAudit, July 2026**

---

## What This File Does (Simple Version)

Every financial statement row has a label — "Accounts receivable, net", "Revenue", "Purchased transportation". To cite the correct accounting rule, you first need to know which official US-GAAP concept that label refers to. This file does that mapping.

v1 used a hand-built dictionary. If the label was in the dictionary, you got a match. If not, you got nothing. **22% of rows got nothing.**

v2 adds three more strategies after the dictionary fails. Each one tries harder to find the concept, and each one only runs when everything before it has already failed.

---

## Why We Needed a Better Approach

The research analysis (`RESEARCH_ANALYSIS.md`) identified three problems with v1:

**Problem 1 — Company-specific labels**

Companies invent their own names for line items. FedEx calls it "Purchased transportation." Philip Morris calls it "Leaf tobacco inventories." These labels do not exist in any standard dictionary. No amount of dictionary expansion will catch them all.

**Problem 2 — Fuzzy matching matches spelling, not meaning**

v1 used `difflib` to compare how similar two strings look character-by-character. "Other income" and "Other comprehensive income" look 87% similar — but they are completely different accounting concepts. The fuzzy matcher makes mistakes because it cannot understand what the words mean.

**Problem 3 — 9–13% FinSM accuracy ceiling**

FinAuditing proved that AI models asked to match labels to concepts over a full 18,000-concept space score 9–13%. If we rely on an unconstrained AI model for this step, we inherit that failure rate. The solution is to constrain the model: instead of asking "pick from 18,000," ask "pick from these 5 candidates I already shortlisted for you."

---

## The Four Layers

```
Row label: "Purchased transportation"
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — Dictionary                                    │
│                                                          │
│  Check the hand-built dictionary of 216 entries.        │
│  Try exact match, stem variants, and fuzzy spelling.    │
│  → Covers ~77.9% of AuditBench rows                    │
│                                                          │
│  "Purchased transportation" → NOT FOUND                 │
└──────────────────────────────┬──────────────────────────┘
                               │ failed
                               ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 2 — SEC EDGAR Live Lookup                         │
│                                                          │
│  If we know the company name (e.g. FedEx → ticker FDX): │
│  1. Ask SEC: what is FedEx's CIK number?                │
│  2. Download FedEx's own XBRL filing from the SEC       │
│  3. Find the exact concept tag FedEx used for this row  │
│                                                          │
│  This is ground truth — not a guess, their own answer.  │
│  Only works on clean-split tables (company name known). │
│  Error-split tables have the company name stripped.     │
└──────────────────────────────┬──────────────────────────┘
                               │ failed (or no company name)
                               ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 3 — Embedding Semantic Similarity                 │
│                                                          │
│  Convert the row label to a meaning vector using a      │
│  pre-trained language model (sentence-transformers).    │
│  Compare against all 216 concept vectors.               │
│  Return the top-5 closest by meaning (not spelling).    │
│                                                          │
│  "Purchased transportation"                             │
│  → meaning similar to "freight and delivery costs"      │
│  → returns top-5 candidates                             │
│                                                          │
│  If top match is confident enough (≥0.55), use it.     │
└──────────────────────────────┬──────────────────────────┘
                               │ ambiguous (low confidence)
                               ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 4 — LLM Constrained Selection (last resort)       │
│                                                          │
│  Show the LLM the row label and the top-5 candidates.   │
│  Ask: "which of these 5 is the correct match?"          │
│  The LLM must pick a number 1–5 (or 0 for none).       │
│  It CANNOT invent a new concept — only selects.         │
│                                                          │
│  Uses GPT-3.5 or Claude Haiku (cheapest available).     │
│  Only called if OPENAI_API_KEY or ANTHROPIC_API_KEY set. │
│  Disabled by default — set use_llm=True to enable.     │
└─────────────────────────────────────────────────────────┘
```

---

## What Each Layer Solves

| Layer | What it handles | Coverage added |
|-------|----------------|---------------|
| 1 — Dictionary | Standard labels that appear in every company's filings | ~77.9% |
| 2 — SEC EDGAR | Company-specific labels (FedEx, Philip Morris, etc.) — for clean split | +up to ~10% on clean split |
| 3 — Embedding | Labels that mean the same thing but use different words | Measured on next eval run |
| 4 — LLM pick | Ambiguous cases where embedding returns several plausible options | Last-resort safety net |

---

## How It Differs From v1

| | v1 (`edgar_mapper.py`) | v2 (`edgar_mapper_v2.py`) |
|-|----------------------|--------------------------|
| Dictionary | Yes | Yes (same) |
| SEC EDGAR live lookup | Stub only (returns None) | **Fully implemented** |
| Embedding matching | No | **Added (Layer 3)** |
| LLM selection | No | **Added (Layer 4, opt-in)** |
| Strategy reported | exact / stem_exact / fuzzy / none | + edgar_xbrl / edgar_xbrl_fuzzy / embedding / llm_constrained |
| Output schema | Same | **Identical — drop-in replacement** |

---

## How to Use It

### Basic usage (same as v1)

```python
from edgar_mapper_v2 import map_statement, MappedRow, MappedStatement

ms = map_statement(item)
# ms.coverage          → float (% of rows that got a concept)
# ms.rows              → list of MappedRow objects
# each MappedRow has:
#   .concept           → "us-gaap:AccountsReceivableNetCurrent" or None
#   .asc_primary       → "210-10-45-1" or None
#   .strategy          → which layer found it
#   .confidence        → 0.0 to 1.0
```

### With all layers enabled

```python
ms = map_statement(item, use_embedding=True, use_llm=True)
```

### Check layer breakdown

```python
from edgar_mapper_v2 import coverage_report
print(coverage_report(ms))
# Company : Apple (AAPL)
# Type    : balance_sheet  Period: 2023-09-30
# Coverage: 18/19 = 94.7%
# Strategy breakdown:
#   exact               : 12
#   stem_exact          : 3
#   edgar_xbrl          : 2
#   embedding           : 1
```

### Install dependencies

```bash
pip install sentence-transformers   # Layer 3 (embedding)
pip install openai                  # Layer 4 (LLM), optional
```

Layer 1 and Layer 2 work with no extra dependencies.  
Layer 3 and 4 degrade gracefully — if the library is missing, those layers are skipped and the system falls back to whatever the earlier layers found.

### Choosing the embedding model

The default model (`all-MiniLM-L6-v2`) is 80MB and fast. The recommended model for production is `bge-large-en` (1.3GB), which FinAuditing showed achieves the best results on financial label matching.

```bash
export INTELLIAUDIT_EMBED_MODEL=BAAI/bge-large-en-v1.5
```

### Enable Layer 4 (LLM)

```bash
export OPENAI_API_KEY=sk-...
python -c "from edgar_mapper_v2 import map_statement; ..."
```

Or pass `use_llm=True` to `map_statement()`. Layer 4 uses GPT-3.5-turbo (cheapest) or Claude Haiku and sends a 5-option multiple choice prompt — each call costs less than $0.001.

---

## Layer 2 — SEC EDGAR Lookup: How It Works

This is the most important new feature because it provides **ground truth** — the company's own answer — instead of a dictionary guess.

**What the SEC provides for free:**

Every public company files their financial statements with the SEC in XBRL format. This means every single row in their statement is tagged with an official `us-gaap:` concept name. The SEC publishes all of this at no cost via their public API.

**The lookup flow:**

```
1. Company name → ticker (from company_tickers.json)
   "Apple" → "AAPL"

2. Ticker → CIK number (from SEC's own index)
   GET https://data.sec.gov/files/company_tickers.json
   "AAPL" → CIK 0000320193

3. CIK → all concept labels (from SEC's companyfacts API)
   GET https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
   Returns: every us-gaap: concept Apple used, with labels

4. Match the row label against Apple's own concept labels
   "Cash and cash equivalents" → "us-gaap:CashAndCashEquivalentsAtCarryingValue"
   (this is the tag Apple themselves put on that row)
```

**The limitation:**

AuditBench's error-split tables have the company name removed by the error injector. Without the company name we cannot look up the ticker, so Layer 2 only helps on clean-split tables. For error splits, Layer 3 (embedding) is the main improvement.

---

## Layer 3 — Embedding Similarity: How It Works

A sentence embedding converts text into a list of numbers (a "vector") that captures its meaning. Two phrases with similar meanings will have vectors that point in the same direction, even if the words are completely different.

```
"Purchased transportation"   → [0.12, -0.43, 0.67, ...]
"freight and delivery costs" → [0.13, -0.41, 0.69, ...]
                                → very similar (cosine similarity ≈ 0.91)

"Other income"               → [0.31,  0.22, -0.14, ...]
"Other comprehensive income" → [-0.05, 0.61,  0.33, ...]
                                → less similar (cosine similarity ≈ 0.34)
```

Layer 3 pre-computes embeddings for all 216 concept labels in the dictionary (this happens once at startup). When a new label arrives, it is embedded and compared against all 216 — the top 5 closest are returned.

If the top match has cosine similarity ≥ 0.55, it is used directly. If it is below that threshold but we still need an answer, the top 5 are passed to Layer 4.

---

## Layer 4 — LLM Constrained Selection: How It Works

The LLM receives a short prompt:

```
Row label: "purchased transportation"
Statement type: income_statement

Choose the best match from the following candidates (reply with the number only):
  1. "freight and delivery costs" → us-gaap:FreightCosts  (similarity: 0.91)
  2. "transportation expenses"    → us-gaap:TransportationExpenses  (similarity: 0.87)
  3. "cost of transportation"     → us-gaap:ShippingHandlingCosts  (similarity: 0.81)
  4. "delivery expense"           → us-gaap:DeliveryExpense  (similarity: 0.76)
  5. "other operating expenses"   → us-gaap:OtherOperatingExpenses  (similarity: 0.61)

If none of these are a good match, reply with 0.
Reply with a single digit and nothing else.
```

The model replies `1`. We use candidate 1.

**Why this is better than asking the model to pick from 18,000 concepts:**  
FinAuditing showed that GPT-4o scores 9% when asked to pick from the full taxonomy (18,000 options). But picking from 5 pre-shortlisted, high-similarity candidates is a much easier task — the model is essentially confirming a near-match, not recalling from memory. This is the "constrained oracle" approach from the VERAFI paper.

---

## Integration With the Rest of the Pipeline

v2 is a drop-in replacement. The output schema (`MappedRow`, `MappedStatement`) is identical to v1. No other file needs to change.

```
Stage 0 (Daksh)              → verifies arithmetic, flags broken row
         │
         ▼
EDGAR Mapper v2 (Irvin)      → maps all rows to us-gaap: concepts
[Layer 1] dict               → handles standard labels
[Layer 2] SEC EDGAR          → handles company-specific labels (clean split)
[Layer 3] embedding          → handles synonym/paraphrase labels
[Layer 4] LLM constrained    → handles genuinely ambiguous labels
         │
         ▼
Stage 1 (Manish)             → taxonomy_graph.py takes the concept name
                               and looks up the governing FASB ASC citation
         │
         ▼
Stage 2 (LLM)                → writes explanation, selects from citation candidates
```

---

## Files

| File | Role |
|------|------|
| `edgar_mapper_v2.py` | This file — the four-layer mapper |
| `edgar_mapper.py` | v1 — kept for reference and backward compatibility |
| `xbrl_concept_map.json` | The 216-entry curated dictionary (used in Layer 1 and as corpus for Layer 3) |
| `company_tickers.json` | Company name → ticker symbol (used in Layer 2) |
| `stage0_common.py` | Shared utilities — `norm_label`, `build_table`, `rows_of` (unchanged) |

---

## Known Limitations

1. **Layer 2 only helps clean split** — company names are stripped from error-split tables by AuditBench's injector. Layer 3 (embedding) is the fix for error splits.

2. **Embedding corpus is only 216 entries** — Layer 3 searches the same 216 labels that Layer 1 uses. Adding the full US-GAAP taxonomy (~18,000 labels) as the embedding corpus would dramatically improve coverage but requires downloading and pre-embedding the full taxonomy (a one-time setup step).

3. **Layer 4 costs money and adds latency** — disabled by default. At ~$0.001/call it is cheap but adds ~1–2 seconds per unmapped row. Only enable it on the final evaluation run, not during development.

4. **Embedding model first load is slow** — the model downloads on first use (~80MB for MiniLM, ~1.3GB for bge-large). After that it is cached locally. Pre-warm with `python -c "from edgar_mapper_v2 import _get_embed_model; _get_embed_model()"` before a timed run.

---

*EDGAR_MAPPER_V2.md · irvin/edgar-mapper branch · SFU CS Capstone · July 2026*
