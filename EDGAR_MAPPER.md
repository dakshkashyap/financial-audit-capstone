# EDGAR Mapper — Stage 1 Documentation

**Author:** Irvin  
**Branch:** `irvin/edgar-mapper`  
**Date:** June 2026  
**Part of:** IntelliAudit · SFU Computing Science Capstone

---

## 1. What Is This and Why Does It Exist

The AuditBench paper gave GPT-4 a financial statement and asked it to cite the exact FASB
accounting rule that was broken — things like "ASC 210-10-45-1" or "ASC 230-10-45-28".
GPT-4 only got this right **26.2% of the time**, because it was trying to recall legal rule
numbers from memory. That is unreliable by design.

The IntelliAudit design doc's solution (Section 4):

> *"The language model should never be the part of the system responsible for citation.
> The graph provides the citation. The model only explains."*

The EDGAR Mapper is the piece that makes this possible. It reads each row label from a
financial statement and **looks up** its official US-GAAP concept name and FASB rule number
— deterministically, with no LLM, in milliseconds.

---

## 2. Where It Fits in the Pipeline

```
AuditBench item
(table + transactions)
        │
        ▼
┌───────────────────┐
│  Stage 0 (Daksh)  │  Arithmetic gate — catches ~40% of errors for free
│  stage0a / 0b     │  SymPy + accounting identities
└────────┬──────────┘
         │ abstains on remaining ~60%
         ▼
┌───────────────────┐
│  Stage 1 (Irvin)  │  ◄── THIS FILE
│  edgar_mapper.py  │  Maps every row → US-GAAP concept + FASB citation
└────────┬──────────┘
         │ MappedStatement
         ▼
┌───────────────────┐
│  Stage 2 (Manish) │  Arelle taxonomy validation + focused LLM
│  Arelle + LLM     │  LLM explains, confirms, rewrites — never guesses a citation
└───────────────────┘
```

**Stage 1 outputs a `MappedStatement`** — a structured object with every row
linked to its concept and citation. Stage 2 consumes this directly.

---

## 3. Files Created

| File | Purpose |
|------|---------|
| `edgar_mapper.py` | Core mapper — the main module |
| `edgar_mapper_eval.py` | Evaluation harness — measures how well the mapper works |
| `xbrl_concept_map.json` | The lookup table — 180+ label → concept + ASC mappings |
| `company_tickers.json` | 48 AuditBench companies → SEC ticker symbols |
| `results/edgar_mapper_eval.json` | Saved evaluation results |

---

## 4. How to Run It

No API key needed. No internet. Fully deterministic.

```bash
# Quick demo — maps 5 sample items and prints results
python edgar_mapper.py

# Full evaluation — all 3 splits, 150 samples each (~35 seconds)
python edgar_mapper_eval.py --split all --n 150

# Single split
python edgar_mapper_eval.py --split correct --n 150
python edgar_mapper_eval.py --split single_error --n 150

# Full dataset
python edgar_mapper_eval.py --split single_error --n 1484
```

---

## 5. How It Works — Step by Step

Given one AuditBench item (a financial statement in `[row n]` format):

### Step 1 — Parse the table
Reuses Daksh's `build_table()` from `stage0_common.py`. Turns the raw
`[row n]: Label | $Value` text into structured typed rows (header / leaf / subtotal).

### Step 2 — Infer statement type
Reads keywords from the `Sheet_type` field or the table header:
- "balance sheet" → `balance_sheet`
- "income", "earnings", "profit/loss" → `income_statement`
- "cash flow" → `cash_flow`

### Step 3 — Parse the reporting period
Extracts the date from `[Time]: September 30, 2023` → `"2023-09-30"`.
Falls back to quarter (`Q3 2023`) or bare year (`2023`).

### Step 4 — Look up each row (three-strategy pipeline)

For every valued row in the table:

```
Normalized label: "cash and cash equivalents"
        │
        ├─► Strategy 1: Exact match
        │   Check xbrl_concept_map.json[statement_type][normalized_label]
        │   ✓ Hit → confidence 1.0
        │
        ├─► Strategy 2: Stem exact match
        │   Try simplified variants:
        │     "total current assets" → "current assets"
        │     "net cash used in investing" → "investing activities"
        │   ✓ Hit → confidence 0.90
        │
        └─► Strategy 3: Fuzzy match
            difflib.SequenceMatcher across all ~180 known labels
            Accept if score ≥ 0.75
            ✓ Hit → confidence = similarity score (e.g. 0.83)
            ✗ Miss → unmapped (recorded for backlog)
```

### Step 5 — Attach ASC citations
Each matched concept carries its FASB citations:
```python
"cash and cash equivalents" → {
    "concept":     "us-gaap:CashAndCashEquivalentsAtCarryingValue",
    "asc_primary": "210-10-45-1",
    "asc_refs":    ["210-10-45", "210-10-45-1"],
    "section":     "current_assets"
}
```

---

## 6. The Output — `MappedStatement`

```python
from edgar_mapper import map_statement

mapped = map_statement(item)

# Top-level info
mapped.company         # "Apple"
mapped.ticker          # "AAPL"
mapped.statement_type  # "balance_sheet"
mapped.period          # "2023-09-30"
mapped.coverage        # 0.838 (83.8% of rows mapped)

# Each row
row = mapped.rows[1]
row.label         # "Cash and cash equivalents"         (original text)
row.norm          # "cash and cash equivalents"          (normalized)
row.value         # 29965.0
row.concept       # "us-gaap:CashAndCashEquivalentsAtCarryingValue"
row.asc_primary   # "210-10-45-1"
row.asc_refs      # ["210-10-45", "210-10-45-1"]
row.asc_title     # "Balance Sheet"
row.section       # "current_assets"
row.strategy      # "exact"
row.confidence    # 1.0
row.mapped        # True
```

---

## 7. The Citation Function (for Stage 2)

When Stage 2 finds a broken row and needs its citation:

```python
from edgar_mapper import map_statement, get_citation_for_error

mapped = map_statement(item)

# e.g. Stage 0 found that row 5 has an error
broken_row = next(r for r in mapped.rows if r.row_idx == 5)

asc_primary, asc_refs = get_citation_for_error("misclassification", broken_row)
# → ("210-10-45-1", ["210-10-45", "210-10-45-1"])

# Pass this directly into the LLM prompt:
# "The violated standard is ASC 210-10-45-1 (Balance Sheet).
#  Explain why classifying this row here is incorrect."
```

**Priority logic:**
1. If the broken row was mapped → use its concept's specific ASC (most precise)
2. If the row was unmapped → fall back to error-type-level ASC from dataset evidence
3. Never returns blank — always gives the LLM something grounded

**Error-type ASC fallbacks** (derived empirically from 1,484 dataset citations):

| Error Type | Primary ASC | Meaning |
|------------|-------------|---------|
| Misclassification | ASC 210-10-45-1 | Current vs non-current classification |
| Missing Row | ASC 230-10-45-28 | Required line items in cash flow |
| Numerical Error | ASC 310-10-35 | Correct measurement of receivables/assets |
| Redundant Row | ASC 210-10-50-1 | No redundant disclosures |

---

## 8. Evaluation Results

**Command:** `python edgar_mapper_eval.py --split all --n 150`

### Overall coverage

| Split | Items | Valued Rows | Mapped | Coverage |
|-------|-------|-------------|--------|----------|
| Correct | 150 | 3,069 | 2,390 | **77.9%** |
| Single error | 150 | 3,079 | 2,397 | **77.8%** |
| Multi error | 150 | 3,161 | 2,394 | **75.7%** |

### By statement type (correct split)

| Statement | Items | Mapped | Coverage |
|-----------|-------|--------|----------|
| Balance Sheet | 46 | 927 / 1,106 | **83.8%** |
| Income Statement | 90 | 1,386 / 1,837 | **75.4%** |
| Cash Flow | 14 | 77 / 126 | **61.1%** |

### Strategy breakdown (correct split)

| Strategy | Rows | Share | Meaning |
|----------|------|-------|---------|
| Exact match | 1,758 | 57.3% | Label found verbatim in concept map |
| Fuzzy match | 368 | 12.0% | Close enough match (≥75% similarity) |
| Stem exact | 264 | 8.6% | Simplified label matched exactly |
| Unmapped | 679 | 22.1% | Company-specific lines (backlog) |

### Ticker and period lookup

| Metric | Correct split | Error splits |
|--------|--------------|--------------|
| Ticker lookup | **100%** | 0%* |
| Period parse | **100%** | **100%** |

*The error splits do not include company names — they were stripped during error injection.
This is expected behaviour, not a bug.

---

## 9. What the ~22% Unmapped Rows Are

These are **not bugs** — they are genuinely company-specific line items that go beyond
standard US-GAAP taxonomy labels. Examples:

| Label | Company | Why it's hard |
|-------|---------|---------------|
| "Purchased transportation" | FedEx | Industry-specific operating cost |
| "Restricted security deposits held for customers" | Lyft / Airbnb | Business-model-specific |
| "Machinery energy transportation" | Caterpillar | Segment-level disclosure |
| "Federal funds sold and securities purchased under resale agreements" | JPMorgan | Banking-specific |
| "Leaf tobacco" | Philip Morris | Commodity-specific inventory |

These rows exist in real XBRL filings under custom or extension concepts, not core US-GAAP.
They are the natural ceiling for string-matching strategies.

**To raise coverage above 78%:** implement the SEC EDGAR XBRL lookup stub
(`edgar_xbrl_lookup()` in `edgar_mapper.py`), which retrieves the filer's own tags directly
from their EDGAR filing — this is "Strategy 3" from the design doc and the strongest
academic approach.

---

## 10. The SEC EDGAR XBRL Stub (Strategy 3 from Design Doc)

The design doc calls this the preferred route:

> *"Use the filers' own us-gaap tags from the original public filings.
> Reproducible ground truth, not hardcoding — the strongest academic position."*

It is scaffolded but not yet implemented:

```python
# In edgar_mapper.py, find edgar_xbrl_lookup() and implement:
# 1. GET https://data.sec.gov/submissions/{CIK}.json  →  resolve ticker to CIK
# 2. GET https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json  →  all XBRL tags
# 3. Match the concept + reporting period
# 4. Return {"concept": "us-gaap:<tag>", "asc_primary": ..., "asc_refs": [...]}
```

When implemented, this would provide **ground-truth accuracy** for companies whose tags
are in EDGAR — which includes every S&P 500 company in the dataset.

---

## 11. The `xbrl_concept_map.json` Structure

The lookup table has five sections:

```json
{
  "balance_sheet":    { "<normalized_label>": { "concept", "asc_primary", "asc_refs", "section" } },
  "income_statement": { ... },
  "cash_flow":        { ... },
  "_error_type_asc":  { "<error_type>": { "asc_primary", "asc_refs", "rationale" } },
  "_asc_titles":      { "<topic_number>": "<human readable title>" }
}
```

Adding a new concept is straightforward — just add a JSON entry:

```json
"salaries and employee benefits": {
  "concept": "us-gaap:LaborAndRelatedExpense",
  "asc_primary": "225-10-45",
  "asc_refs": ["225-10-45"],
  "description": "Salaries, wages and related benefits",
  "section": "operating_expenses"
}
```

The key must be the **normalized form** of the label — lowercase, no punctuation,
collapsed whitespace. Use `stage0_common.norm_label(raw_label)` to generate it.

---

## 12. Key Design Decisions

### Why reuse `stage0_common.build_table()`?
Daksh's parser already handles the edge cases in AuditBench table parsing (HTML noise,
quoted numbers, parenthetical negatives). Re-implementing would introduce divergence.

### Why fuzzy match at 0.75 cutoff?
Below 0.75, short labels start matching wrong concepts (e.g. "other" → "other assets"
even on a cash flow statement). 0.75 keeps precision high while still catching variants
like "Total shareholders' equity" → "total stockholders equity".

### Why statement-type scoping?
"Depreciation and amortization" appears on both income statements (expense line) and
cash flow statements (non-cash add-back). Same label, different XBRL concepts. Scoping
to statement type picks the right one.

### Why empirical error-type ASC fallbacks?
The fallback table in `_error_type_asc` was derived by running regex extraction over
all 1,484 Standards Citation strings in `wrong_table_data.json` and counting which ASC
topics appear most often per error type. It is data-driven, not hand-waved.

---

## 13. What Manish Needs from This (Handoff)

The integration is one import:

```python
from edgar_mapper import map_statement, get_citation_for_error

# At the start of Stage 2, map the item
mapped = map_statement(item)

# When you know which row is broken (from Stage 0 or Arelle):
broken_row_idx = finding.problematic_entry  # from stage0_common.Finding
broken_row = next((r for r in mapped.rows if r.row_idx == broken_row_idx), None)

asc_primary, asc_refs = get_citation_for_error(finding.error_type, broken_row)

# Build the LLM prompt with grounded citation — never ask the model to recall it
prompt = f"""
The following row in the financial statement is incorrect:
  Row {broken_row_idx}: {broken_row.label} = {broken_row.value}

The violated accounting standard is: ASC {asc_primary}
  ({mapped_row.asc_title if broken_row else 'Financial Reporting'})

Error type: {finding.error_type}
Correct value: {finding.correct_value}

Please explain why this violates ASC {asc_primary} and write the corrected row.
"""
```

The LLM's job is now just **confirmation and explanation** — not recall.
That is why the design doc predicts citation accuracy jumps from 26% to 70–85%.

---

*EDGAR Mapper · irvin/edgar-mapper branch · June 2026*
