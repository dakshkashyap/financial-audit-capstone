# Citation MCP Agent

Grounded FASB ASC citation selection via an MCP tool server + iterative agent.

**Scope:** citation only (Stage 0 math stays deterministic).

## Architecture

```
concept → get_candidates (TaxonomyGraph)
        → agent picks ONE asc
        → validate_citation  (reject if not in candidate set)
        → retry up to 3×
        → store_pick
```

The agent cannot invent ASC codes. Every accepted citation must pass `validate_citation`.

## Quick start

```bash
source .venv/bin/activate

# Live tool-call traces on sample concepts (no API key)
python -m citation_mcp.demo

# A (graph single pick) vs C (agent) on AuditBench
python -m citation_mcp.eval_agent --n 50

# Candidate-set ceiling (oracle)
python -m citation_mcp.eval_agent --mode oracle --n 50

# LLM agent (needs ANTHROPIC_API_KEY or OPENAI_API_KEY)
python -m citation_mcp.eval_agent --mode llm --model claude/claude-3-5-haiku --n 20
```

## MCP server (Cursor / Claude Desktop)

```bash
python -m citation_mcp.server
```

Example Cursor `mcp.json` entry:

```json
{
  "mcpServers": {
    "taxonomy-citation": {
      "command": "/path/to/financial-audit-capstone/.venv/bin/python",
      "args": ["-m", "citation_mcp.server"],
      "cwd": "/path/to/financial-audit-capstone"
    }
  }
}
```

### Tools

| Tool | Purpose |
|------|---------|
| `get_candidates` | All ASC refs for a us-gaap concept |
| `validate_citation` | Accept only if in candidate set |
| `get_concept_info` | Baseline single-pick + topic split |
| `store_pick` | Persist final choice |

## Modes

| Mode | Needs API? | Behavior |
|------|------------|----------|
| `heuristic` | No | Score candidates (subject-matter + concept hints), validate, iterate |
| `llm` | Yes | Model picks from list; Python validates & retries |
| `oracle` | No | If GT topic ∈ candidates, pick it (ceiling) |

## What “better” means

1. **Hallucination rate → 0** (invalid picks rejected by `validate_citation`)
2. **Topic EM ≥ graph single-pick (A)**, moving toward candidate recall ceiling
3. Show live traces where A picks presentation (210) and C picks subject-matter (330/350/606)
