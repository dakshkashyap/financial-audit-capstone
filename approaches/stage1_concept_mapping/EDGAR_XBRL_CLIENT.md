# How the SEC EDGAR Call Works

**Folder:** `edgar-xbrl/`  
**Main script:** `edgar_api.py`  
**Purpose:** Pull a company’s official XBRL tags and numbers from the SEC — no API key.

---

## Why this exists (IntelliAudit)

IntelliAudit needs to map a financial statement row label to an official US-GAAP concept (e.g. `"Revenue"` → `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`).

- A hand-built dictionary covers many standard labels
- It fails on company-specific wording
- Every public company already filed those tags with the SEC

This script asks the SEC for the **filer’s own tags** — ground truth, not a guess. That concept then feeds Stage 1 (taxonomy graph → FASB citation).

---

## Important: there is no API key

`data.sec.gov` is public. You do **not** register for a token.

What the SEC requires instead:

1. A **User-Agent** header with your name and email  
2. No more than **10 requests per second**

```python
HEADERS = {
    "User-Agent": "Irvin Cardoza irvin.cardoza@sfu.ca",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}
```

This identifies your program so SEC can contact you if something goes wrong. It is **not** authentication.

---

## How one call works (end to end)

```
Ticker (e.g. AAPL)
        │
        ▼
①  GET company_tickers.json
    → find CIK (Apple = 320193 → pad to 0000320193)
        │
        ▼
②  GET companyfacts/CIK0000320193.json
    → all us-gaap concepts Apple ever filed
        │
        ▼
③  Pick a concept (e.g. RevenueFromContractWithCustomerExcludingAssessedTax)
    → filter to annual 10-K / FY rows
        │
        ▼
④  Save CSV: year → value (billions)
```

### Step ① — Ticker → CIK

```
GET https://www.sec.gov/files/company_tickers.json
```

Every filer has a Central Index Key (CIK). The API needs it zero-padded to 10 digits:

```
320193  →  0000320193
```

### Step ② — Download company facts

```
GET https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json
```

One JSON blob with every standardized XBRL concept the company reported (`facts → us-gaap → …`).

### Step ③ — Extract one concept

Inside that JSON:

```
facts["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]
  → label, description
  → units["USD"] → list of {end, val, form, filed, fp, …}
```

We keep rows where:

- `form` is `10-K` or `10-K/A` (annual report)
- `fp` is `FY` (full fiscal year)
- latest filing wins if the same period appears more than once

### Step ④ — Output

Demo run for Apple prints a table like:

| end | value_billions | form | filed |
|-----|----------------|------|-------|
| 2023-09-30 | 383.285 | 10-K | 2025-10-31 |
| 2024-09-28 | 391.035 | 10-K | 2025-10-31 |
| 2025-09-27 | 416.161 | 10-K | 2025-10-31 |

And saves:

`aapl_RevenueFromContractWithCustomerExcludingAssessedTax.csv`

---

## Other useful endpoints

| Goal | URL pattern |
|------|-------------|
| All facts for one company | `…/companyfacts/CIK{10-digit}.json` |
| One concept only | `…/companyconcept/CIK…/us-gaap/Assets.json` |
| Same concept across many companies | `…/frames/us-gaap/Assets/USD/CY2025Q4I.json` |
| Ticker list | `https://www.sec.gov/files/company_tickers.json` |

---

## How to run

```bash
cd edgar-xbrl
source venv/bin/activate          # macOS/Linux (already set up)

# Demo: one concept (Revenue), annual 10-K only
python edgar_api.py

# Full dump: EVERY us-gaap fact Apple filed — no filters
python edgar_api.py --all --ticker AAPL
# → aapl_all_companyfacts.csv  (~500 concepts, ~25k rows)
```

**Important:** `--all` is **not** a pretty balance sheet / income statement page.  
SEC companyfacts is a **flat database** of every tagged number across all filings and periods.  
A formatted “financial statement” is a *view* of a subset of those facts for one period.

---

## How to read the output

| Field | Meaning |
|-------|---------|
| `end` | Period end date (Apple FY ends late September) |
| `value_billions` | Dollar amount ÷ 1,000,000,000 |
| `form` | `10-K` = annual report |
| `filed` | When the company filed with the SEC |
| `accn` | Unique SEC accession / filing ID |

**Note:** Some rows can be partial periods that still carry an FY flag. Prefer the large full-year totals (e.g. ~$260B–$416B for Apple revenue) when summarizing annual results.

The “Revenue-related concepts” list shows every Apple tag whose name contains `"Revenue"`. Different companies may use `Revenues` or `SalesRevenueNet` instead of the ASC 606 tag — inspecting this list first avoids requesting a concept that company never filed.

---

## Where this sits in IntelliAudit

```
Stage 0 (SymPy)     → find arithmetic errors
EDGAR call (this)   → row / company → real us-gaap: concept
Stage 1 (taxonomy)  → concept → FASB ASC citation (no hallucination)
Stage 2 (LLM)       → explain using pre-verified facts
```

| Without this script | With this script |
|---------------------|------------------|
| Dictionary guesses the concept | Use the company’s filed tag |
| Company-specific labels often fail | Recover tags from real SEC filings |
| Citation starts from a guess | Citation starts from filer ground truth |

**Limitation:** needs a known company (ticker). AuditBench error splits strip company names, so those cases still use the dictionary / embedding fallback. Clean tables and real filings get the full EDGAR benefit.

---

*edgar-xbrl/README.md · IntelliAudit · SFU CS Capstone*
