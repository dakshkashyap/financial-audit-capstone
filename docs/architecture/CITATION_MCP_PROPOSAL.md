# Citation MCP Agent Proposal

**For:** Team — next demo / professor presentation  
**Branch reviewed:** `stage1-citation-improvements`  
**Scope:** AI + MCP **only for citation** — not the whole audit pipeline

---

## 1. What Manish’s branch already has

After checking out `stage1-citation-improvements`, the repo has a working Stage 1 stack:

| Piece | File | Job |
|-------|------|-----|
| EDGAR Mapper | `edgar_mapper.py` | Row label → `us-gaap:` concept + static ASC |
| Taxonomy graph | `taxonomy_graph.py` | Concept → FASB citation from real US-GAAP XML |
| Stage 1 glue | `stage1_arelle.py` | Enrich mapper rows with taxonomy citations |
| Citation eval | `stage1_citation_eval.py` | Score vs AuditBench GT |
| FinMR path | `finmr_*.py` | Real XBRL filings + taxonomy coverage |

**Measured today (deterministic Stage 1 only):**

```
AuditBench single_error (n=150):
  Coverage (broken row has a citation):  ~93%
  Citation topic match (strict):         ~24%   ← ~parity with GPT-4’s 26%
  Candidate-set ceiling:                 ~28%

FinMR taxonomy coverage (100 concepts):
  With any citation:  89%
  Direct hit:         85%
  Parent fallback:     4%
```

**Gap:** The graph almost always *returns* a citation, but often the **wrong kind** (presentation topic like ASC 210/220/230 instead of subject-matter like ASC 330/350/606). A single deterministic pick cannot fix ambiguity. That is where an **iterative citation agent** helps.

---

## 2. Your task (focused)

> Propose a better citation solution using an MCP server + AI agent,  
> show it works better than graph-only,  
> and keep the agent **only on citation** (Stage 0 math stays deterministic).

Do **not** rebuild the whole multi-agent audit. Prove one thing:

**Can an MCP-backed agent pick a better FASB citation than `taxonomy_graph` alone, by iterating over candidates?**

---

## 3. Proposed architecture (citation-only)

```
Broken row + us-gaap concept
        │
        ▼
┌─────────────────────────────────────┐
│  TAXONOMY MCP SERVER                │
│  Tools (deterministic, no LLM):     │
│                                     │
│  get_candidates(concept)            │
│    → list of ASC citations from     │
│      taxonomy_graph                 │
│                                     │
│  validate_citation(asc)             │
│    → {valid: true/false}            │
│      (must exist in FASB linkbase)  │
│                                     │
│  get_concept_info(concept)          │
│    → label, parents, topic family   │
│                                     │
│  store_pick(item_id, citation, why) │
│    → shared state for the demo      │
└──────────────────┬──────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│  CITATION AGENT (LLM)               │
│                                     │
│  Loop (max 2–3 iterations):         │
│   1. call get_candidates            │
│   2. pick ONE citation from list    │
│   3. call validate_citation         │
│   4. if invalid → try next          │
│   5. if valid → store_pick + stop   │
│                                     │
│  Cannot invent ASC codes —          │
│  only choose from tool results.     │
└─────────────────────────────────────┘
```

**Baseline to beat:** single best pick from `taxonomy_graph.get_fasb_citation()`  
**Agent version:** select from `get_candidate_citations()` with validate + retry

---

## 4. Why iteration helps

| Round | What happens |
|-------|----------------|
| 1 | Agent sees candidates `[210-10-S99, 330-10-35, 852-…]`, picks `330` (inventory subject-matter) |
| 2 | If pick fails `validate_citation` → forced to pick another candidate |
| Stop | First valid pick that agent can justify from concept label + statement type |

Without MCP, the model might output `ASC 999-99-99` (hallucination).  
With MCP, **invalid citations are rejected by the tool** before output.

---

## 5. How to show “it works better”

Run the same 50–150 AuditBench single-error items three ways:

| Config | Method | Metric |
|--------|--------|--------|
| A | Graph single pick (current Stage 1) | Topic EM ~24% |
| B | Agent picks from candidates **once** (no retry) | Topic EM |
| C | Agent + validate + **iterate** until valid | Topic EM |

**Success for the presentation:**

1. **Hallucination rate = 0%** on B and C (every citation passes `validate_citation`)
2. **C ≥ B ≥ A** on topic EM (or at least C ≥ A)
3. Show 2–3 live traces: tool call → pick → validate → (retry) → final

If EM does not beat A much, still win on **grounding**: “we match or beat accuracy *and* cannot invent codes.”

---

## 6. Built — run it

Package: `citation_mcp/`

```bash
source .venv/bin/activate

# Live traces (no API key)
python -m citation_mcp.demo

# A vs C on AuditBench (heuristic agent)
python -m citation_mcp.eval_agent --n 50

# Ceiling (oracle picks GT topic if in candidates)
python -m citation_mcp.eval_agent --mode oracle --n 50

# LLM agent
python -m citation_mcp.eval_agent --mode llm --model claude/claude-3-5-haiku --n 20

# MCP server for Cursor
python -m citation_mcp.server
```

See `citation_mcp/README.md`.

---

## 7. Setup commands (Manish’s instructions)

```bash
git clone https://github.com/dakshkashyap/financial-audit-capstone.git
cd financial-audit-capstone
git checkout stage1-citation-improvements

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Useful checks on this branch:

```bash
python stage1_arelle.py --n 3
python stage1_citation_eval.py   # if args match README / file docstring
python finmr_taxonomy_citations.py
```

Your EDGAR live client stays on `irvin/edgar-mapper` under `edgar-xbrl/`.  
Citation MCP work should live on top of **this** Stage 1 branch (uses Manish’s graph).

---

## 8. One-line pitch for the team / professor

> “Stage 1’s taxonomy graph gives high coverage but weak single picks.  
> We wrap that graph in an MCP server and let a citation agent **select and re-validate** from the candidate set — same grounded source, iterative choice, zero hallucinated ASC codes — and we measure the lift against graph-only.”

---

*CITATION_MCP_PROPOSAL.md · branch: stage1-citation-improvements · SFU Capstone*
