# Taxonomy Graph & MCP Citation Flow

**IntelliAudit — how citations are grounded and queried**  
*Diagram-first brief for demos and design review*

---

## 1. Big picture

```mermaid
flowchart LR
    ROW[Broken line item] --> MAP[EDGAR Mapper]
    MAP --> CON[us-gaap concept]
    CON --> TG[TaxonomyGraph]
    TG --> MCP[MCP Server<br/>tools]
    MCP --> AG[AI Agent]
    AG --> ASC[FASB ASC citation]

    style TG fill:#cce5ff,stroke:#004085
    style MCP fill:#fff3cd,stroke:#856404
    style AG fill:#d4edda,stroke:#155724
```

| Layer | Job |
|-------|-----|
| **TaxonomyGraph** | Read FASB’s US-GAAP XML; list ASC links for a concept |
| **MCP Server** | Expose that graph as tools an agent can call |
| **AI Agent** | Pick one ASC from tool results; never invent codes |

---

## 2. What the TaxonomyGraph is (internally)

FASB publishes a **US-GAAP taxonomy ZIP**. Inside it is a **reference linkbase** XML: edges from concepts → ASC reference elements.

```mermaid
flowchart TB
    ZIP[FASB us-gaap-2023.zip] --> XML[us-gaap-ref-2023.xml<br/>reference linkbase]
    XML --> CACHE[.cache/us-gaap-ref-2023.xml<br/>disk cache]
    CACHE --> IDX[In-memory indexes]

    subgraph IDX2["TaxonomyGraph indexes"]
        A[concept label → reference arcs]
        B[reference id → ASC parts<br/>topic / subtopic / section / paragraph]
    end

    IDX --> IDX2
    IDX2 --> API[Public API]
```

### Graph shape (conceptual)

```mermaid
flowchart LR
    subgraph Concepts
        G[Goodwill]
        PPE[PropertyPlantAndEquipmentNet]
        REV[RevenueFromContractWithCustomer…]
    end

    subgraph ASC_Refs["ASC reference nodes"]
        R210[210-10-S99-1]
        R350[350-20-45-1]
        R360[360-10-50-1]
        R606[606-10-50-5]
        R852[852-10-55-10]
    end

    G --> R210
    G --> R350
    G --> R852
    PPE --> R360
    PPE --> R852
    REV --> R606
```

One concept → **many** ASC edges. That ambiguity is why a single automatic pick can be wrong.

---

## 3. How TaxonomyGraph answers a query (no MCP yet)

### Current Stage 1 path — single pick

```mermaid
sequenceDiagram
    participant S1 as stage1_arelle
    participant TG as TaxonomyGraph
    participant XML as US-GAAP XML cache

    S1->>TG: get_fasb_citation_detail("Goodwill")
    TG->>XML: load / use indexes
    TG->>TG: collect all reference arcs
    TG->>TG: rank arcs (role, general vs industry, …)
    TG-->>S1: ONE winner e.g. 210-10-S99-1
```

```mermaid
flowchart TB
    C[concept: Goodwill] --> L[Load taxonomy if needed]
    L --> A[Find all reference arcs]
    A --> R[Rank each arc]
    R --> W[Winner = max score]
    W --> O["Return single ASC<br/>get_fasb_citation_detail()"]

    style W fill:#f8d7da,stroke:#721c24
    style O fill:#f8d7da,stroke:#721c24
```

If the leaf concept has no arcs → **parent fallback** (strip CamelCase tokens and retry).

---

## 4. How the MCP server wraps the graph

We do **not** upload the XML into MCP. We wrap the **same Python object** behind tool functions.

```mermaid
flowchart TB
    subgraph Python["Python process"]
        TG[(TaxonomyGraph<br/>singleton)]
        TT[TaxonomyTools<br/>citation_mcp/tools.py]
        SV[MCP Server<br/>citation_mcp/server.py]
        TT --> TG
        SV --> TT
    end

    CLIENT[AI client<br/>Cursor / citation agent] <-->|MCP stdio<br/>JSON tool calls| SV

    style TG fill:#cce5ff,stroke:#004085
    style SV fill:#fff3cd,stroke:#856404
    style CLIENT fill:#d4edda,stroke:#155724
```

### Tool ↔ graph method map

| MCP tool | Calls on TaxonomyGraph | Returns |
|----------|------------------------|---------|
| `get_candidates(concept)` | `get_candidate_citations()` | **All** ASC links for the concept |
| `get_concept_info(concept)` | `get_fasb_citation_detail()` + candidates | Baseline single pick + topic split |
| `validate_citation(concept, asc)` | candidates again; membership check | `{valid: true/false}` |
| `store_pick(item_id, citation, …)` | (agent state only) | Saved final choice |

```mermaid
flowchart LR
    subgraph MCP_Tools["MCP tools"]
        T1[get_candidates]
        T2[validate_citation]
        T3[get_concept_info]
        T4[store_pick]
    end

    subgraph Graph_API["TaxonomyGraph API"]
        G1[get_candidate_citations]
        G2[get_fasb_citation_detail]
    end

    T1 --> G1
    T2 --> G1
    T3 --> G2
    T3 --> G1
    T4 --> ST[(in-memory store)]
```

### Start the server

```bash
python -m citation_mcp.server
```

Cursor (or any MCP client) launches that process and calls tools over stdio.

---

## 5. How an AI agent queries citations (full loop)

This is the **proposed** citation path: agent + MCP + same graph.

```mermaid
sequenceDiagram
    participant User as Audit pipeline
    participant Agent as AI Citation Agent
    participant MCP as MCP Server
    participant TG as TaxonomyGraph

    User->>Agent: concept=Goodwill, label=Goodwill
    Agent->>MCP: get_candidates("Goodwill")
    MCP->>TG: get_candidate_citations(...)
    TG-->>MCP: [210-…, 350-…, 852-…]
    MCP-->>Agent: candidate list

    Agent->>Agent: Choose one ASC from list only<br/>(e.g. 350-20-45-1)

    Agent->>MCP: validate_citation("Goodwill", "350-20-45-1")
    MCP->>TG: candidates ∩ pick
    TG-->>MCP: in set
    MCP-->>Agent: valid=true

    alt invalid
        Agent->>Agent: Pick next candidate (retry)
        Agent->>MCP: validate_citation(...)
    end

    Agent->>MCP: store_pick(item_id, "350-20-45-1", rationale)
    MCP-->>Agent: stored
    Agent-->>User: FASB ASC 350-20-45-1
```

### Decision flow (agent view)

```mermaid
flowchart TB
    START[Receive us-gaap concept] --> CAND[Tool: get_candidates]
    CAND --> EMPTY{Any candidates?}
    EMPTY -->|No| ABSTAIN[Abstain — no citation]
    EMPTY -->|Yes| PICK[Agent picks ONE from list]
    PICK --> VAL[Tool: validate_citation]
    VAL --> OK{valid?}
    OK -->|No| RETRY{Attempts left?}
    RETRY -->|Yes| PICK
    RETRY -->|No| FAIL[Fail closed / heuristic fallback<br/>still from candidates]
    OK -->|Yes| STORE[Tool: store_pick]
    STORE --> DONE[Emit grounded ASC]

    style CAND fill:#fff3cd,stroke:#856404
    style VAL fill:#fff3cd,stroke:#856404
    style STORE fill:#fff3cd,stroke:#856404
    style PICK fill:#d4edda,stroke:#155724
    style DONE fill:#d4edda,stroke:#155724
```

**Hard rule:** the agent never invents an ASC. If a code is not in `get_candidates`, `validate_citation` returns `valid=false`.

---

## 6. Current vs proposed (citation step only)

```mermaid
flowchart TB
    subgraph CUR["CURRENT — Stage 1 today"]
        direction LR
        C1[concept] --> C2[TaxonomyGraph<br/>rank → one pick] --> C3[ASC out]
    end

    subgraph PROP["PROPOSED — MCP + agent"]
        direction LR
        P1[concept] --> P2[TaxonomyGraph<br/>via MCP tools]
        P2 --> P3[candidate list]
        P3 --> P4[Agent select]
        P4 --> P5[validate]
        P5 -->|retry| P4
        P5 -->|ok| P6[ASC out]
    end
```

Same rule book (US-GAAP XML). Different decision process.

---

## 7. Example walkthrough: Goodwill

| Step | Who | What happens |
|------|-----|----------------|
| 0 | Mapper | Row “Goodwill” → concept `Goodwill` |
| 1 | Agent → MCP | `get_candidates("Goodwill")` |
| 2 | Graph | Returns e.g. `210`, `350`, `852`, `942`… |
| 3 | Agent | Prefers subject-matter → picks `350-20-45-1` |
| 4 | Agent → MCP | `validate_citation("Goodwill", "350-20-45-1")` → **valid** |
| 5 | Agent → MCP | `store_pick(...)` |
| 6 | Pipeline | Uses `FASB ASC 350-20-45-1` |

If the agent had guessed `ASC 330-10-35-1` (inventory) → validate **fails** → must retry from the real list.

---

## 8. Where this sits in the full audit

```mermaid
flowchart TB
    S0[Stage 0 — error detection<br/>NO MCP] --> M[Concept mapping<br/>NO MCP]
    M --> CIT[Citation layer]
    CIT --> OUT[ASC + optional explanation]

    subgraph CIT["Citation layer"]
        direction TB
        TG[TaxonomyGraph]
        MCP[MCP Server]
        AG[AI Agent]
        TG --- MCP --- AG
    end

    style CIT fill:#e8f5e9,stroke:#2e7d32
    style S0 fill:#f5f5f5,stroke:#9e9e9e
    style M fill:#f5f5f5,stroke:#9e9e9e
```

**MCP is only on citation.** Math checks and mapping stay outside.

---

## 9. File map

| File | Role |
|------|------|
| `taxonomy_graph.py` | Load XML, index arcs, single pick + candidate list |
| `citation_mcp/tools.py` | Thin wrappers over the graph |
| `citation_mcp/server.py` | MCP server (`@server.tool` → tools) |
| `citation_mcp/agent.py` | Iterative agent (heuristic / LLM) |
| `stage1_arelle.py` | Current production path: single pick only |

---

## 10. One-line summary

> **TaxonomyGraph** = FASB’s concept→ASC rule book in memory.  
> **MCP server** = USB port that exposes that book as tools.  
> **AI agent** = reads the tool menu, picks one ASC, and must pass validate before the citation counts.

---

*TAXONOMY_MCP_FLOW.md · IntelliAudit*
