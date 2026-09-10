"""
taxonomy_mcp_server.py — MCP server wrapping the IntelliAudit symbolic environment.

Implements the design in irvin/edgar-mapper:TAXONOMY_MCP_AGENT.md +
NEXT_PHASE_PLAN.md on top of the *real* modules in this repo:

    taxonomy_graph.py    — FASB US-GAAP 2023 reference-linkbase graph
    concept_citation.py  — subject/presentation split + version families
    edgar_mapper.py      — row label → us-gaap concept (dict + fuzzy + stem)
    stage0a/stage0b      — deterministic arithmetic + identity verification
    (shared state)       — store_finding / get_evidence for the agent loop

Any agent (Auditor / Defender / Judge — or Cursor itself) can call these tools.
No tool can hallucinate: every citation traces to the FASB linkbase or the
curated concept map, and stage0_verify is pure SymPy/Python.

Run (stdio transport, for Cursor / Claude Desktop / any MCP client):
    python taxonomy_mcp_server.py

Register in Cursor (.cursor/mcp.json):
    {"mcpServers": {"intelliaudit-taxonomy": {
        "command": "python",
        "args": ["c:/Users/daksh/Desktop/Capstone/financial-audit-capstone/taxonomy_mcp_server.py"]}}}
"""
from __future__ import annotations

import os
import sys
from typing import Optional

pass  # repo root already on sys.path when run with -m

from mcp.server.mcpserver import MCPServer

from core.taxonomy_graph import TaxonomyGraph
from approaches.stage1_taxonomy_citation.concept_citation import (
    best_topic, candidate_topics, family, subject_topic, topic_of,
)
from approaches.stage1_concept_mapping import edgar_mapper

mcp = MCPServer(name="intelliaudit-taxonomy")

_graph = TaxonomyGraph()
_state: dict = {}          # item_id -> {agent_id: finding}  (shared agent memory)

# Real FASB ASC topic numbers (codification master list). Anything outside this
# set is not a citable topic, full stop — this is what makes validate_citation
# a hard gate rather than a range heuristic.
_ASC_TOPICS = {
    # 100s General principles / presentation
    "105", "205", "210", "215", "220", "225", "230", "235", "250", "255",
    "260", "270", "272", "274", "275", "280",
    # 300s Assets
    "305", "310", "320", "321", "323", "325", "326", "330", "340", "350", "360",
    # 400s Liabilities
    "405", "410", "420", "430", "440", "450", "460", "470", "480",
    # 500s Equity
    "505",
    # 600s Revenue
    "605", "606", "610",
    # 700s Expenses
    "705", "710", "712", "715", "718", "720", "730", "740",
    # 800s Broad transactions
    "805", "808", "810", "815", "820", "825", "830", "832", "835", "840",
    "842", "845", "848", "850", "852", "853", "855", "860",
    # 900s Industry
    "905", "908", "910", "912", "915", "920", "922", "924", "926", "928",
    "930", "932", "940", "942", "944", "946", "948", "950", "952", "954",
    "958", "960", "962", "965", "970", "972", "974", "976", "978", "980",
    "985", "995",
}


def _bare(concept_id: str) -> str:
    return concept_id.replace("us-gaap:", "").strip()


# ── Tool 1: get_citation ──────────────────────────────────────────────────────
@mcp.tool()
def get_citation(concept_id: str, statement_type: str = "") -> dict:
    """Grounded FASB ASC citation for a us-gaap concept.

    Args:
        concept_id: e.g. "us-gaap:InventoryNet" (prefix optional).
        statement_type: "balance_sheet" | "income_statement" | "cash_flow" | "".

    Returns primary pick (subject-matter rule > presentation > taxonomy arc),
    the full UNION candidate set an agent may select from, and the source.
    Never invents a citation: every candidate traces to the FASB linkbase,
    the curated concept map, or the statement-presentation table.
    """
    bare = _bare(concept_id)
    detail = _graph.get_fasb_citation_detail(bare)
    tax_topics = [c.get("topic") for c in _graph.get_candidate_citations(bare)
                  if c.get("topic")]
    primary = best_topic(bare, statement_type or None,
                         taxonomy_best=detail.get("asc_primary"))
    cands = candidate_topics(bare, statement_type or None,
                             taxonomy_topics=tax_topics)
    return {
        "primary": primary,
        "candidates": cands,
        "taxonomy_pick": detail.get("asc_primary"),
        "taxonomy_source": detail.get("source"),
        "matched_concept": detail.get("matched_concept"),
        "source": "fasb_linkbase_2023+concept_rules",
        "hallucinated": False,
    }


# ── Tool 2: get_concept_info ─────────────────────────────────────────────────
@mcp.tool()
def get_concept_info(concept_id: str) -> dict:
    """What is this us-gaap concept? Label words, subject-matter topic, and all
    reference arcs (topic + role) the FASB linkbase attaches to it."""
    import re
    bare = _bare(concept_id)
    arcs = _graph.get_candidate_citations(bare)
    return {
        "concept": f"us-gaap:{bare}",
        "label_words": re.findall(r"[A-Z][a-z0-9]*", bare),
        "subject_topic": subject_topic(bare),
        "reference_arcs": arcs[:15],
        "n_arcs": len(arcs),
    }


# ── Tool 3: get_concepts (EDGAR mapper) ──────────────────────────────────────
@mcp.tool()
def get_concepts(row_label: str, statement_type: str = "balance_sheet") -> dict:
    """Map a financial-statement row label to its us-gaap concept.

    Args:
        row_label: e.g. "Accounts receivable, net".
        statement_type: "balance_sheet" | "income_statement" | "cash_flow".

    Uses the deterministic 3-strategy cascade (exact / stem / fuzzy) against
    the curated 216-entry concept map. Returns the match, the strategy that
    produced it, and a confidence score. FinSM-style task, no LLM involved.
    """
    from core.stage0_common import norm_label
    norm = norm_label(row_label)
    entry, strategy, confidence = edgar_mapper.match_concept(norm, statement_type)
    if entry is None:
        return {"mapped": False, "row_label": row_label, "strategy": "none",
                "confidence": 0.0, "concept": None}
    return {
        "mapped": True,
        "row_label": row_label,
        "concept": entry.get("concept"),
        "asc_primary": entry.get("asc_primary"),
        "asc_refs": entry.get("asc_refs", []),
        "section": entry.get("section"),
        "strategy": strategy,
        "confidence": confidence,
    }


# ── Tool 4: validate_citation ────────────────────────────────────────────────
@mcp.tool()
def validate_citation(citation: str) -> dict:
    """Validate a proposed ASC citation before it reaches any output.

    Args:
        citation: e.g. "ASC 330-10-35-1" or "330".

    Normalizes superseded topics to their successor (225→220, 605→606) and
    checks the topic appears in the FASB linkbase / known-topic tables.
    A Judge agent should reject any citation where valid is false.
    """
    import re
    cleaned = re.sub(r"(?i)^\s*(fasb\s+)?asc\s*", "", citation.strip())
    topic = topic_of(cleaned) or cleaned
    normalized = family(topic)
    valid = normalized in _ASC_TOPICS
    return {
        "input": citation,
        "topic": topic,
        "normalized_topic": normalized,
        "valid": bool(valid),
        "superseded": topic != normalized,
        "grounding": "FASB ASC codification topic list",
    }


# ── Tool 5: stage0_verify ────────────────────────────────────────────────────
@mcp.tool()
def stage0_verify(table: str, transaction_data: str = "") -> dict:
    """Run the deterministic Stage 0 gate (SymPy arithmetic + accounting
    identities) on a `[row n]: Label | $value [SEP]` table.

    Args:
        table: the statement in AuditBench row format.
        transaction_data: optional transaction narrative (the value oracle).

    Returns the verdict: a proven Finding (error type, row, correct value),
    or abstain, plus the verified_consistent flag (True = every checkable
    subtotal foots and every identity holds — an LLM claiming a numerical
    error on such a table is almost certainly hallucinating).
    """
    from approaches.stage0_deterministic_gate import stage0a
    from approaches.stage0_deterministic_gate import stage0b
    from core.stage0_common import combine_findings
    from approaches.full_pipeline.pipeline import _consistency
    from core.stage0_common import build_table, build_transactions

    item = {"table": table, "transaction_data": transaction_data}
    a = stage0a.verify(item)
    b = stage0b.check(item)
    finding = combine_findings(a, b)
    df = build_table(table)
    tx = build_transactions(transaction_data or "")
    verified, n_sub, n_id = _consistency(a, b, df, tx)

    out = {
        "fired": finding is not None,
        "verified_consistent": verified,
        "n_subtotals_checked": n_sub,
        "n_identities_checked": n_id,
        "footing_mismatches": a.footing[:6],
        "identity_violations": b.equations[:4],
    }
    if finding is not None:
        out.update({
            "error_type": finding.error_type,
            "problematic_entry": finding.problematic_entry,
            "correct_value": finding.correct_value,
            "stated_value": finding.stated_value,
            "source": finding.source,
            "detail": finding.detail,
        })
    return out


# ── Tools 6+7: shared agent state ────────────────────────────────────────────
@mcp.tool()
def store_finding(item_id: str, agent_id: str, finding: str) -> dict:
    """Persist an agent's finding (free-form JSON/text) to shared state so other
    agents (Defender, Judge) can read it via get_evidence."""
    _state.setdefault(item_id, {})[agent_id] = finding
    return {"stored": True, "item_id": item_id,
            "agents_with_findings": sorted(_state[item_id])}


@mcp.tool()
def get_evidence(item_id: str) -> dict:
    """Everything stored for an audit item: each agent's finding so far.
    A Judge reads this instead of re-running the other agents."""
    return {"item_id": item_id, "findings": _state.get(item_id, {})}


if __name__ == "__main__":
    # Warm the graph before serving so first tool call isn't a 100 MB download.
    _ = _graph.available
    mcp.run()
