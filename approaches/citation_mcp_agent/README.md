# Citation MCP agent

**Expose the accounting rulebook as tools, so an AI agent can only pick citations
that actually exist.**

This is the same job as [`stage1_taxonomy_citation`](../stage1_taxonomy_citation/),
approached differently. Instead of a single deterministic pick from the taxonomy,
the whole candidate set is exposed over the **Model Context Protocol** and an agent
chooses from it — then its choice is validated against the taxonomy before anything
is accepted.

## Why it exists

Stage 1 measurement showed the correct ASC topic sits in a concept's candidate arcs
only ~28% of the time, so a single deterministic pick is capped near the paper's own
26%. If a single pick is capped, the useful move is to surface the whole candidate
set and let something with language understanding choose — while making it
structurally impossible to invent an answer.

## The tools

`server.py` exposes four tools over MCP stdio:

| Tool | What it does |
|---|---|
| `get_candidates(concept)` | Every ASC citation the taxonomy grounds for this concept |
| `validate_citation(concept, asc)` | Is this citation real and in the candidate set? |
| `get_concept_info(concept)` | Subject-matter vs presentation topic breakdown |
| `store_pick(item_id, citation, rationale)` | Record the choice with its written reason |

The agent loop is: get candidates → pick one → validate → if invalid, retry with
the rejection as feedback. An unvalidated pick is never stored.

## Three modes

| Mode | Who picks | Purpose |
|---|---|---|
| `heuristic` | Rule-based ranking (prefers subject-matter over presentation topics) | No-API-key baseline |
| `llm` | Claude, shown only the real candidate list | The actual experiment |
| `oracle` | Always picks ground truth if present in candidates | Measures the ceiling |

## Run it

```bash
# live trace of the tool calls, no API key
python -m approaches.citation_mcp_agent.demo

# baseline: deterministic single pick vs agent pick
python -m approaches.citation_mcp_agent.eval_agent --n 50

# the ceiling — a perfect chooser given the same candidates
python -m approaches.citation_mcp_agent.eval_agent --mode oracle --n 50

# the experiment
python -m approaches.citation_mcp_agent.eval_agent --mode llm \
    --model claude/claude-haiku-4-5 --n 50

# run as an MCP server for Cursor
python -m approaches.citation_mcp_agent.server
```

Cursor picks the server up from `.cursor/mcp.json` at the repo root.

## What the experiment found

Over 42 items (`results/citation_mcp_llm_50.json`):

| Measure | Lookup only | LLM, tool-locked | Ceiling |
|---|---|---|---|
| Correct topic | 19.0% | 19.0% | 26.2% |
| **Invented citations** | 0 | **0** | 0 |
| Accepted answers verified real | 100% | **100%** | 100% |
| Written rationale per pick | none | **every case** | none |
| Avg retries | — | 0.93 | — |

**The honest read.** Tool-locking eliminated hallucination completely and produced
a defensible justification for every choice, but it did not improve accuracy — and
the ceiling tells us why. A *perfect* chooser given the same candidate list scores
26.2%, so the correct answer was simply absent from the candidates most of the
time. The bottleneck is taxonomy coverage, not the model.

That result is what pushed the project toward
[`audit_patch_repair`](../audit_patch_repair/): stop treating the LLM as the thing
that decides, and use it to explain a decision that verified computation already
made.

## Two servers here

`server.py` is the citation-only server described above. `taxonomy_mcp_server.py`
is a broader server from the same design lineage that also exposes the Stage 0
verifiers and shared finding state, implementing
[docs/architecture/TAXONOMY_MCP_AGENT.md](../../docs/architecture/TAXONOMY_MCP_AGENT.md)
and [NEXT_PHASE_PLAN.md](../../docs/architecture/NEXT_PHASE_PLAN.md). Both are kept
because they answer different questions — one isolates the citation experiment, the
other is the multi-agent design.
