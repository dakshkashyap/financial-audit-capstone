"""
Live demo: show tool calls + iteration on a few concepts.

  python -m citation_mcp.demo
  python -m citation_mcp.demo --mode llm --model claude/claude-3-5-haiku
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from citation_mcp.tools import TaxonomyTools
from citation_mcp.agent import CitationAgent

EXAMPLES = [
    {
        "concept": "Goodwill",
        "label": "Goodwill",
        "statement_type": "bs",
        "error_type": "value_error",
        "note": "Graph often picks 210; agent should pick subject-matter 350",
    },
    {
        "concept": "PropertyPlantAndEquipmentNet",
        "label": "Property and equipment, net",
        "statement_type": "bs",
        "error_type": "value_error",
        "note": "Graph may pick industry 852; agent should prefer 360",
    },
    {
        "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "label": "Net sales",
        "statement_type": "is",
        "error_type": "value_error",
        "note": "Subject-matter ASC 606",
    },
    {
        "concept": "CashAndCashEquivalentsAtCarryingValue",
        "label": "Cash and cash equivalents",
        "statement_type": "bs",
        "error_type": "value_error",
        "note": "ASC 230 is often correct here",
    },
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="heuristic", choices=["heuristic", "llm", "oracle"])
    ap.add_argument("--model", default="claude/claude-haiku-4-5")
    args = ap.parse_args()

    tools = TaxonomyTools()
    agent = CitationAgent(tools=tools, mode=args.mode, model=args.model)

    print()
    print("Citation MCP demo — grounded tools + iterative pick")
    print(f"mode={args.mode}")
    print("-" * 60)

    for i, ex in enumerate(EXAMPLES):
        print(f"\n[{i+1}] {ex['concept']}")
        print(f"    note: {ex['note']}")
        info = tools.get_concept_info(ex["concept"])
        print(f"    graph single pick : {info['graph_single_pick']}  ({info['graph_source']})")
        print(f"    candidates        : {info['n_candidates']}  topics={info['candidate_topics']}")
        print(f"    subject-matter    : {info['subject_matter_topics']}")

        res = agent.cite(
            ex["concept"],
            item_id=f"demo_{i}",
            label=ex["label"],
            statement_type=ex["statement_type"],
            error_type=ex["error_type"],
        )
        print(f"    agent pick        : {res.citation}  topic={res.topic}")
        print(f"    validated={res.validated}  iterations={res.iterations}  "
              f"hallucinated_attempts={res.hallucinated_attempts}")
        print(f"    rationale         : {res.rationale}")
        for step in res.trace:
            print(f"      → {json.dumps(step, default=str)[:160]}")

    print()
    print("Done. MCP server:  python -m citation_mcp.server")
    print("A vs C eval:       python -m citation_mcp.eval_agent --n 50")
    print()


if __name__ == "__main__":
    main()
