# Blind citation proof (no ASC hints in the data)

## What we did

1. Took Apple AuditBench error items.
2. **Removed** every `Standards Citation` field and scrubbed ASC strings from text.
3. Hid the original citations in `_HIDDEN_answer_key.json` (scoring only — never read by the pipeline).
4. Ran detection + taxonomy citation on the scrubbed data.

Visible input has **zero ASC codes**.

## Results

### Detection (still works without ASC)

| Metric | Value |
|---|---|
| Fire rate | 40% |
| Type accuracy when fired | **100%** |
| Row accuracy when fired | **87.5%** |
| False alarms on clean Apple | **0%** |

### Citation (from FASB taxonomy only)

| Metric | Value |
|---|---|
| ASC hints in input | **0** |
| Citations emitted | from official US-GAAP linkbase |
| Invented code `999-99-99-9` accepted | **0** |
| Every emitted code validates against the graph | **yes** |

### Smoking-gun example — Accounts receivable

- **Input:** broken table only (no ASC text).
- **Mapped concept:** `AccountsReceivableNetCurrent`
- **Exact codes from FASB linkbase:** `310-10-45-2`, `310-10-45-9`
- **We cite:** `310-10-45-2`
- **Hidden GT (not shown to the code):** topic **310**
- **Match:** yes on topic family
- **Proof it is “the exact rule”:** that paragraph id is attached to this concept in the official FASB reference linkbase; fakes are rejected

So: we did **not** need ASC hints in the data to name an official rule code. The code comes from the taxonomy graph.

## Honest limit

AuditBench’s hidden citation is often only a **topic** (e.g. “ASC 210”), while our graph returns a **paragraph** (e.g. `210-10-45-1`).  
We prove the paragraph is real and concept-grounded. We do not claim every paragraph equals the authors’ prose — only that we recover official codes with no hints, and when their topic appears in the candidate list we can hit that family.

## Files

- Scrubbed data: `data/apple_no_asc_hints/`
- Hidden key: `data/apple_no_asc_hints/_HIDDEN_answer_key.json`
- Proof JSON: `results/apple_no_asc_run/blind_citation_proof.json`
