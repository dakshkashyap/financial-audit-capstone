# Results on FinMR (Real XBRL Filings)

**Dataset:** [TheFinAI/FinMR](https://huggingface.co/datasets/TheFinAI/FinMR) — 332 real XBRL filing cases, ground truth from official **DQC** rules  
**Run:** `python -m audit_patch.run_finmr`  
**Output:** `results/audit_patch_finmr_332.json`

---

## What we ran

```text
1. DETECT      reported value vs value implied by the calculation rules
2. LOCALIZE    root cause = the one fact (concept + period) that conflicts
3. EXPLAIN     write the equation and list the facts used as evidence
4. REPAIR      one typed edit: replace_fact_value(old → expected)
5. REVALIDATE  re-check the rule on the patched fact
6. CITE        grounded FASB ASC citation from the taxonomy MCP tools
7. CERTIFY     emit a machine-checkable certificate
```

No LLM anywhere in this run. Every number is reproducible.

---

## Headline numbers

| Metric | Result |
|--------|--------|
| Records evaluated | **332** |
| Cases where we proposed a repair | **178** |
| **Exact repair match vs DQC ground truth** | **145 / 178 = 81.5%** |
| Rule satisfied after patch (no regression) | **100%** |
| Patch size (facts changed) | **1** |
| Grounded citations attached | **166 / 178 = 93.3%** |
| Abstained (evidence incomplete) | 147 |

We **abstain instead of guessing** when the needed fact or calculation arc is
missing from the filing excerpt — that is a deliberate precision-first choice.

---

## Per-rule breakdown

| DQC rule | What it checks | Cases | Repaired | Exact match |
|----------|----------------|-------|----------|-------------|
| `DQC_US_0015` | Element must not be negative | 110 | 59 | **50 (85%)** |
| `DQC_US_0117` | Child = parent − siblings | 120 | 33 | 12 (36%) |
| `DQC_US_0126` | Parent = weighted sum of children | 102 | 86 | **83 (97%)** |

**Honest reading:** roll-up (`0126`) and sign (`0015`) repairs are strong.
Imbalance (`0117`) is our weakest case — solving for a child requires the
parent *and* every sibling to be present, and the dataset's filing excerpts
often truncate them.

---

## Deliverable 1 — Explainable model

Every repair emits a certificate a human can read and a machine can re-check:

```json
{
  "dqc_rule": "DQC_US_0015",
  "rule_meaning": "This element must not be reported with a negative value.",
  "root_cause": {
    "concept": "PaymentsToAcquirePropertyPlantAndEquipment",
    "period": "2021-09-01 to 2021-11-30"
  },
  "evidence": {
    "reported_value": "-1284",
    "expected_value": "1284",
    "equation": "PaymentsToAcquirePropertyPlantAndEquipment reported as -1284; rule requires a non-negative value, so the correct value is 1284."
  },
  "patch": { "operation": "replace_fact_value", "old_value": "-1284", "new_value": "1284", "patch_size": 1 },
  "revalidation": { "rule_satisfied_after_patch": true, "new_violations_introduced": 0 },
  "citation": { "asc": "230-10-45-13", "grounded": true, "source": "taxonomy_mcp" }
}
```

For roll-up rules the equation lists each child with its weight and value, so a
reviewer can verify the arithmetic by hand.

---

## Deliverable 2 — Methodology

One fixed pipeline, with a strict authority boundary:

> The system may **propose** a repair. Only the deterministic checks may **accept** it.

A patch is accepted only if it removes the violation, changes exactly one fact,
and introduces no new violation. That held for **100%** of accepted patches.

---

## Deliverable 3 — Root-cause ground truth

FinMR's ground truth comes from **DQC rules**, not from a language model:

- `extracted_value` — what the filing reported  
- `calculated_value` — what the rule says it should be  

We score our repaired value directly against `calculated_value`, which gives a
true **exact repair match** metric (81.5%) rather than a similarity score.

---

## Deliverable 4 — MCP server

The citation step calls the taxonomy MCP tool layer (`citation_mcp/`):

- `get_candidates(concept)` — every ASC code the US-GAAP taxonomy links to that concept  
- `validate_citation(concept, asc)` — accept only codes in that list  

**93.3%** of repairs carry a citation, and **every** attached citation passed
validation, so zero ASC codes were invented.

---

## How to reproduce

```bash
source .venv/bin/activate
python -m audit_patch.run_finmr              # all 332
python -m audit_patch.run_finmr --n 40       # quick run
python -m audit_patch.run_finmr --no-citation
```

---

## Limitations we state openly

1. Filing excerpts are truncated, so 147 cases lack the facts needed to repair — we abstain rather than guess.
2. `DQC_US_0117` needs better sibling recovery.
3. Only three DQC rules are covered; semantic retagging and structural arc repair are not yet implemented.
4. This run is fully deterministic; LLM-assisted proposals for ambiguous semantic cases remain future work, and would still be gated by the same validator.
