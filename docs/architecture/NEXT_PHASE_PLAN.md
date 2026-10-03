# IntelliAudit — Next Phase Architecture

**Date:** July 2026 · SFU Capstone

---

## The Core Idea

AuditFlow showed that multi-agent + deterministic verification = 82% accuracy. We adapt that pattern — but instead of agents exploring independently, all agents share a central MCP server that holds the verified evidence. Agents communicate through tools, not through each other directly.

> *"LLMs guide the search. A symbolic environment performs verification. Agents cannot bypass the tools."*  
> — AuditFlow principle, adapted for IntelliAudit

---

## Full Architecture

```
INPUT: Financial Statement
(text table / XBRL / PDF)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     MCP SERVER (central hub)                        │
│                                                                     │
│  Tools every agent can call:                                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  stage0_verify() │  │  get_citation()  │  │  get_concepts()  │  │
│  │                  │  │                  │  │                  │  │
│  │  Runs SymPy math │  │  Queries FASB    │  │  EDGAR Mapper v2 │  │
│  │  Returns:        │  │  taxonomy graph  │  │  Returns concept │  │
│  │  • error_type    │  │  Returns:        │  │  candidates for  │  │
│  │  • broken_row    │  │  • citation list │  │  each row label  │  │
│  │  • correct_value │  │  • 0 hallucinate │  │  (4-layer lookup)│  │
│  │  • verified flag │  │                  │  │                  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  get_evidence()  │  │  store_finding() │  │  validate_out()  │  │
│  │                  │  │                  │  │                  │  │
│  │  Returns Stage 0 │  │  Persists agent  │  │  Pydantic check: │  │
│  │  findings +      │  │  findings to     │  │  citation = real │  │
│  │  transaction     │  │  shared state    │  │  FASB node?      │  │
│  │  oracle summary  │  │  for other agents│  │  error_type ∈ 4? │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                     │
└──────────────┬────────────────────────┬────────────────────────────┘
               │                        │
    ┌──────────▼──────────┐  ┌──────────▼──────────┐
    │    FAST PATH        │  │    SLOW PATH         │
    │  (no LLM, ~40%      │  │  (multi-agent,       │
    │   of cases)         │  │   abstained cases)   │
    └──────────┬──────────┘  └──────────┬───────────┘
               │                        │
               ▼                        ▼
         [Stage 3]              [Agent Debate Loop]
     Deterministic Reviser      (see below)
```

---

## Fast Path — No LLM

Handles ~40% of cases entirely in code. No agent is called.

```
Stage 0A (SymPy)         →  calls stage0_verify() on MCP server
Stage 0B (Python checks) →  calls stage0_verify() on MCP server
                                │
                    ┌───────────┴──────────────┐
                    │                          │
             Error found?               All checks pass?
                    │                          │
                    ▼                          ▼
            Stage 3 reviser            Return "Correct"
            applies fix +              with evidence trail
            SymPy recomputes
```

If Stage 0 finds a clear error with exact arithmetic proof → fix it deterministically, skip the agents entirely.

---

## Slow Path — Multi-Agent Debate

Only runs when Stage 0 abstains (case is ambiguous). Three agents, all talking to the same MCP server.

```
                  ┌──────────────────────────────────────┐
                  │           MCP SERVER                 │
                  │  (shared state across all 3 agents)  │
                  └───────┬──────────────┬───────────────┘
                          │              │
               ┌──────────▼──┐      ┌───▼────────────┐
               │   AUDITOR   │      │    DEFENDER    │
               │   AGENT     │      │    AGENT       │
               │             │      │                │
               │ Calls:      │      │ Calls:         │
               │ get_evidence│      │ get_evidence() │
               │ get_concepts│      │ stage0_verify()│
               │ get_citation│      │                │
               │             │      │ Task:          │
               │ Task:       │      │ Use transaction│
               │ Find the    │      │ oracle to argue│
               │ error, name │      │ the table is   │
               │ the row,    │      │ correct. Find  │
               │ pick the    │      │ transaction    │
               │ citation    │      │ support for    │
               │             │      │ every row.     │
               │ store_      │      │ store_         │
               │ finding()   │      │ finding()      │
               └──────┬──────┘      └───────┬────────┘
                      │                     │
                      └──────────┬──────────┘
                                 │
                                 ▼
                      ┌──────────────────────┐
                      │     JUDGE AGENT      │
                      │                      │
                      │ Reads both findings  │
                      │ from MCP shared state│
                      │                      │
                      │ Calls:               │
                      │ get_evidence()       │
                      │ validate_out()       │
                      │                      │
                      │ Rules (hard-coded):  │
                      │ • If verified_clean  │
                      │   + Auditor claims   │
                      │   arithmetic error → │
                      │   Defender wins      │
                      │                      │
                      │ • Citation must come │
                      │   from get_citation()│
                      │   not from memory    │
                      │                      │
                      │ • validate_out()     │
                      │   must pass before   │
                      │   output is returned │
                      └──────────┬───────────┘
                                 │
                                 ▼
                          Stage 3 Reviser
```

---

## Why MCP Is the Right Glue

Without MCP, agents either talk directly to each other (fragile, no shared state) or run completely independently (expensive, duplicates work). MCP gives us a third option: a shared tool server that all agents query.

```
Without MCP:
  Auditor → passes findings to Defender via prompt injection
  Defender → re-runs all checks from scratch
  Judge → re-reads all three full transcripts
  Problem: expensive, inconsistent, agents can contradict the evidence

With MCP:
  All three agents call the same stage0_verify() tool
  Stage 0 runs once, result is cached in server state
  Auditor stores finding → Defender reads it → Judge reads both
  Judge calls validate_out() → schema enforced before output
  Problem solved: one source of truth, no duplication, no hallucination
```

The MCP server also means every tool call is logged. You get a full evidence trail — which tool was called, with what input, what it returned — for every audit. This is the audit trail a real compliance system needs.

---

## How Each Stage Uses MCP

| Stage | MCP tools it calls | What it cannot do |
|-------|-------------------|-------------------|
| Stage 0 (fast path) | `stage0_verify()`, `store_finding()` | Cannot call LLM |
| EDGAR Mapper | `get_concepts()` | Cannot generate a concept from memory |
| Stage 1 (Taxonomy) | `get_citation()` | Cannot return a citation not in FASB file |
| Auditor Agent | `get_evidence()`, `get_concepts()`, `get_citation()`, `store_finding()` | Cannot skip `get_citation()` |
| Defender Agent | `get_evidence()`, `stage0_verify()`, `store_finding()` | Cannot override Stage 0 result |
| Judge Agent | `get_evidence()`, `validate_out()` | Cannot pick a citation not from `get_citation()` |
| Stage 3 (Reviser) | `stage0_verify()`, `validate_out()` | Cannot return output that fails validation |

---

## MCP Server Tools — What Each One Does

```python
# stage0_verify(table, transactions)
# → runs SymPy + accounting identity checks
# → returns {verified_consistent, error_type, broken_row, correct_value}
# → result is cached; subsequent calls by other agents reuse it

# get_citation(concept_id)
# → queries taxonomy_graph.py for the concept's FASB ASC citation
# → returns candidate list (subject-matter + presentation union)
# → 0% hallucination: every result traced to real FASB linkbase node

# get_concepts(row_label, statement_type, ticker)
# → calls EDGAR Mapper v2's 4-layer cascade
# → returns top concept matches with confidence scores

# get_evidence(item_id)
# → returns the full evidence bundle for this audit item:
#   Stage 0 findings, transaction oracle summary, all agent findings so far

# store_finding(item_id, agent_id, finding)
# → persists an agent's finding to shared state
# → other agents can read it via get_evidence()

# validate_out(output_dict)
# → Pydantic schema check:
#   error_type ∈ {Numerical, Missing, Redundant, Misclassification}
#   citation must match a known FASB node
#   corrected_value must match Stage 0's correct_value (if Numerical)
# → returns {valid: bool, violations: list}
```

---

## Output

Every audit returns the same structured object — unchanged from today:

```json
{
  "judgment":        "Incorrect",
  "error_type":      "Numerical Error",
  "error_row":       "Row 5: Accounts receivable, net",
  "correct_value":   52000,
  "citation":        "ASC 310-10-35-4",
  "citation_source": "taxonomy_graph",
  "explanation":     "The stated value of $42,000 is inconsistent with...",
  "corrected_table": "...",
  "evidence_trail":  { "stage0": {...}, "auditor": {...}, "defender": {...} }
}
```

---

*NEXT_PHASE_PLAN.md · irvin/edgar-mapper branch · SFU CS Capstone · July 2026*
