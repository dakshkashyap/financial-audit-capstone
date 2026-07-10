# Taxonomy Knowledge Agent — MCP Design

**Component:** Individual knowledge agent for querying the US-GAAP accounting rules graph  
**Protocol:** Model Context Protocol (MCP)  
**SFU Capstone — IntelliAudit, July 2026**

---

## What This Is

A dedicated MCP server that wraps the FASB US-GAAP taxonomy graph and exposes it as callable tools. Any agent in the pipeline — Auditor, Defender, Judge — can call these tools to look up accounting rules without ever generating a citation from memory.

The agent does one job: answer questions about accounting rules from the official FASB source. It cannot reason. It cannot guess. It only reads from the graph.

---

## Architecture

```
  Auditor Agent ──┐
                  │
  Defender Agent ─┼──► TAXONOMY MCP SERVER ──► taxonomy_graph.py ──► FASB US-GAAP XML
                  │         (port 8001)              │
  Judge Agent ────┘                                  └──► concept_citation.py
                                                          (subject/presentation split)
```

Every agent calls the same server. The graph is loaded once at startup and shared across all calls. No agent touches the taxonomy file directly.

---

## MCP Server — Tools Exposed

```python
# Tool 1: get_citation
# ─────────────────────
# Input:  concept_id  (e.g. "us-gaap:InventoryNet")
#         statement_type  ("balance_sheet" | "income_statement" | "cash_flow")
# Output: {
#   "primary":    "ASC 330-10-35-1",       ← best single pick (version-fair)
#   "candidates": ["ASC 330", "ASC 210"],   ← full union set for Judge to select from
#   "source":     "fasb_linkbase",          ← always traceable
#   "hallucinated": false                   ← always false — guaranteed
# }
#
# How it works internally:
#   concept_citation.best_topic()      → subject-matter rule (330 Inventory)
#   concept_citation.candidate_topics()→ union of subject + presentation + graph arcs
#   Falls back to parent concept if leaf has no citation
#   Never returns a citation not in the FASB linkbase file


# Tool 2: get_concept_info
# ──────────────────────────
# Input:  concept_id  (e.g. "us-gaap:AccountsReceivableNetCurrent")
# Output: {
#   "label":       "Accounts Receivable, Net, Current",
#   "type":        "monetaryItemType",
#   "balance":     "debit",
#   "parent":      "us-gaap:ReceivablesNetCurrent",
#   "children":    [...],
#   "asc_topics":  ["ASC 310"]
# }
#
# Used by Auditor to understand what a concept is before citing it


# Tool 3: walk_to_rule
# ─────────────────────
# Input:  concept_id
#         error_type  ("Numerical" | "Missing" | "Redundant" | "Misclassification")
# Output: {
#   "violated_rule":  "ASC 330-10-35-1",
#   "rule_text":      "Inventory shall be measured at the lower of cost...",
#   "walk_path":      ["InventoryNet" → "Inventories" → "ASC 330"],
#   "confidence":     0.91
# }
#
# Traverses calculation and presentation edges from the broken concept
# up to the constraint that governs it


# Tool 4: validate_citation
# ──────────────────────────
# Input:  citation_string  (e.g. "ASC 330-10-35-1")
# Output: {
#   "valid":      true,
#   "normalized": "ASC 330-10-35",   ← version-normalized form
#   "exists_in":  "fasb_linkbase_2023"
# }
#
# Called by Judge before finalizing output
# Rejects anything not in the real FASB file
```

---

## How Agents Use It

```
AUDITOR AGENT
─────────────
1. Calls get_concepts() on EDGAR Mapper MCP → gets concept ID for broken row
2. Calls get_citation(concept_id) on Taxonomy MCP → gets citation candidates
3. Picks from candidates (does not generate from memory)
4. Calls store_finding() → saves {concept, citation_picked, reasoning}

DEFENDER AGENT
──────────────
1. Calls get_concept_info(concept_id) → understands what the concept is
2. Uses this to argue the row is correctly classified
3. Does not need to call get_citation() — it is not claiming a violation

JUDGE AGENT
───────────
1. Reads Auditor's picked citation from shared state
2. Calls validate_citation(citation) → confirms it is a real FASB node
3. If invalid → re-prompts Auditor with the violation message
4. If valid → includes in final output
```

---

## Server Setup

```python
# taxonomy_mcp_server.py

from mcp.server import MCPServer
from taxonomy_graph import TaxonomyGraph
from concept_citation import best_topic, candidate_topics, family

# Load the graph once at startup (downloads + caches FASB linkbase XML)
graph = TaxonomyGraph()

server = MCPServer(name="taxonomy-knowledge-agent", port=8001)

@server.tool("get_citation")
def get_citation(concept_id: str, statement_type: str) -> dict:
    primary   = best_topic(concept_id, statement_type, graph)
    candidates = candidate_topics(concept_id, statement_type, graph)
    return {
        "primary":     primary,
        "candidates":  candidates,
        "source":      "fasb_linkbase_2023",
        "hallucinated": False,
    }

@server.tool("get_concept_info")
def get_concept_info(concept_id: str) -> dict:
    return graph.get_concept_info(concept_id)

@server.tool("walk_to_rule")
def walk_to_rule(concept_id: str, error_type: str) -> dict:
    return graph.walk_to_violated_constraint(concept_id, error_type)

@server.tool("validate_citation")
def validate_citation(citation_string: str) -> dict:
    normalized = family(citation_string)  # maps old → current standard name
    exists = graph.citation_exists(normalized)
    return {"valid": exists, "normalized": normalized, "exists_in": "fasb_linkbase_2023"}

server.run()
```

---

## Why a Separate Server for This

The taxonomy graph is the one component every agent needs but none of them should own. If it lived inside any one agent, the others would need to ask that agent for information — coupling them together. As an MCP server it is:

- **Shared** — one graph loaded in memory, all agents query it
- **Isolated** — agents cannot modify the graph, only read from it
- **Auditable** — every tool call is logged with input and output
- **Guaranteed** — `validate_citation` makes hallucination physically impossible at the output layer

---

*TAXONOMY_MCP_AGENT.md · irvin/edgar-mapper branch · SFU CS Capstone · July 2026*
