# IntelliAudit — What We Are Building (Professor Brief)

**SFU Capstone · Clear methodology overview**

---

## The problem in one sentence

When a financial statement has an error, we need to **find the real cause**, **fix it safely**, and **show our work** — not guess with an opaque LLM answer.

---

## Our three goals

| Goal | What it means | How we do it |
|------|----------------|--------------|
| **1. Explainable** | Anyone can see *why* we flagged or fixed something | Every result includes a **proof trail** (checks, candidates, edits, re-check) |
| **2. Clear methodology** | A fixed pipeline, not “ask GPT and hope” | **Detect → Localize → Repair → Revalidate → Certificate** |
| **3. Root-cause ground truth** | We know which row is the real error (not just broken totals) | AuditBench labels the true bad row; we score against that |

---

## Methodology (the only pipeline to remember)

```text
1. DETECT      Find that something is wrong (deterministic Stage 0 checks)
2. LOCALIZE    Identify the root-cause row (not every cascading total)
3. REPAIR      Apply the smallest typed fix (e.g. correct one number)
4. REVALIDATE  Re-run checks on the patched statement
5. CERTIFY     Output a machine-readable certificate of what changed
```

**Authority rule:**  
An LLM may *suggest*. Only deterministic checks may *accept* a repair.

---

## Simple diagram

```mermaid
flowchart LR
    A[Broken statement] --> B[Detect]
    B --> C[Localize root cause]
    C --> D[Minimal repair]
    D --> E[Revalidate]
    E --> F[Proof certificate]

    style C fill:#fff3cd,stroke:#856404
    style D fill:#d4edda,stroke:#155724
    style F fill:#cce5ff,stroke:#004085
```

---

## What “root cause” means

A wrong leaf (e.g. Accounts Receivable) often breaks **many** totals:

```text
Wrong AR value
   → current assets wrong
   → total assets wrong
   → assets = liabilities + equity fails
```

A naive system reports 4 warnings.  
**We aim for 1 root cause** — the AR row — using AuditBench’s labeled `Problematic Entry` as ground truth.

---

## What is built today vs next

| Piece | Status |
|-------|--------|
| Stage 0 detection + corrected value (numerical) | **Built** |
| Root-cause row scoring vs AuditBench labels | **Built** |
| AuditPatch V0: patch one number → revalidate → certificate | **Built** |
| Citation tools (taxonomy candidates + validate) | **Built** |
| Full XBRL / DQC repair on real SEC filings | **Next** |
| LLM proposals for ambiguous semantic tags | **Next** (always verifier-gated) |

---

## Dataset we use for these goals

**AuditBench** (`Error_insertion/wrong_table_data.json`)

- Real-style financial tables with **one injected error** each  
- Labels: error type + **which row is the root cause**  
- Clean table + transaction narrative for the correct numbers  

This is ideal for goals 1–3.  
Later we add **FinMR / SEC XBRL** for real filing validation.

---

## One claim for the professor

> We are not building another black-box auditor.  
> We build an **explainable repair pipeline**: localize the true root cause, apply a minimal fix, prove the fix with revalidation, and record a certificate.  
> AuditBench root-cause labels let us measure that localization; certificates make every decision auditable.

---

## What we are *not* claiming

- Not “MCP alone is the research contribution”  
- Not “LLM edits filings without checks”  
- Not “we already fully repair real XBRL SEC filings” (that’s the next phase)

---

*PROFESSOR_BRIEF.md — use this as the single overview slide deck source*
