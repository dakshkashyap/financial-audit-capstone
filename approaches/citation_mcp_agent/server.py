"""
Taxonomy Citation MCP Server.

Exposes grounded FASB ASC tools over MCP stdio. Wire into Cursor / any MCP
client, or run the in-process agent (citation_mcp.agent) against the same tools.

Usage
-----
  python -m citation_mcp.server

Cursor mcp.json example:
  {
    "mcpServers": {
      "taxonomy-citation": {
        "command": "python",
        "args": ["-m", "citation_mcp.server"],
        "cwd": "/path/to/financial-audit-capstone"
      }
    }
  }
"""

from __future__ import annotations

import json
import os
import sys

from core.paths import REPO_ROOT as _ROOT
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mcp.server.mcpserver import MCPServer

from approaches.citation_mcp_agent.tools import TaxonomyTools

_tools = TaxonomyTools()

server = MCPServer(
    name="taxonomy-citation",
    instructions=(
        "Grounded FASB ASC citation tools backed by the US-GAAP taxonomy. "
        "Never invent ASC codes — call get_candidates, pick one, then "
        "validate_citation before store_pick."
    ),
)


@server.tool()
def get_candidates(concept: str) -> str:
    """Return all FASB ASC citations grounded in the US-GAAP taxonomy for a concept."""
    return json.dumps(_tools.get_candidates(concept), indent=2)


@server.tool()
def validate_citation(concept: str, asc: str) -> str:
    """Check that an ASC citation is in the grounded candidate set for the concept."""
    return json.dumps(_tools.validate_citation(concept, asc), indent=2)


@server.tool()
def get_concept_info(concept: str) -> str:
    """Concept metadata: graph single-pick, parents, presentation vs subject-matter topics."""
    return json.dumps(_tools.get_concept_info(concept), indent=2)


@server.tool()
def store_pick(item_id: str, citation: str, rationale: str = "") -> str:
    """Store the final validated citation for an item."""
    return json.dumps(_tools.store_pick(item_id, citation, rationale), indent=2)


def main() -> None:
    # Ensure taxonomy cache is warm before serving
    _tools.graph.get_fasb_citation("Assets")
    server.run()


if __name__ == "__main__":
    main()
