"""
run_audit.py — Unified audit entry point.

Takes ANY financial statement input (AuditBench item, FinMR record, or raw
XBRL concept name), detects the error deterministically, and outputs the
governing FASB ASC citation — all in one call.

    result = run_audit(input)
    # result = {
    #     "error_detected":   True/False,
    #     "error_type":       "Numerical Error" | "Missing Row" | ...,
    #     "error_detail":     "Row 'Cash' stated 500 but should be 450",
    #     "correct_value":    450,
    #     "stated_value":     500,
    #     "concept":          "us-gaap:CashAndCashEquivalentsAtCarryingValue",
    #     "citation":         "FASB ASC 230-10-45-5",
    #     "citation_source":  "taxonomy" | "parent_fallback" | "static_map" | "none",
    #     "statement_type":   "balance_sheet" | "income_statement" | ...,
    # }

Supports three input formats:
  1. AuditBench item dict  → {"table": "...", "transaction_data": "...", ...}
  2. FinMR record dict     → {"query": "...", "answer": "...", "dqc_id": "..."}
  3. Raw concept name      → "CashAndCashEquivalentsAtCarryingValue"
                             (skip detection, just get the citation)

Usage:
    from run_audit import run_audit

    # AuditBench
    result = run_audit(auditbench_item)

    # FinMR
    result = run_audit(finmr_row, source="finmr")

    # Raw concept
    result = run_audit("CashAndCashEquivalentsAtCarryingValue", source="concept")

    # CLI
    python run_audit.py --auditbench-index 0
    python run_audit.py --finmr-index 110
    python run_audit.py --concept CashAndCashEquivalentsAtCarryingValue
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Optional, Union

# ── Stage 0 (detection) ───────────────────────────────────────────────────────
from stage0a import verify as stage0a_verify
from stage0b import check as stage0b_check
from stage0_common import combine_findings, Finding

# ── Stage 1 (concept mapping + citation) ──────────────────────────────────────
from edgar_mapper import map_statement, MappedStatement, MappedRow
from stage1_arelle import enrich_with_taxonomy
from taxonomy_graph import TaxonomyGraph

# ── FinMR adapter ─────────────────────────────────────────────────────────────
from finmr_parser import parse_record as finmr_parse
from finmr_verifier import predict as finmr_predict


# ── shared TaxonomyGraph (lazy-loaded singleton) ──────────────────────────────
_graph: Optional[TaxonomyGraph] = None


def _get_graph() -> TaxonomyGraph:
    global _graph
    if _graph is None:
        _graph = TaxonomyGraph()
    return _graph


# ── helpers ───────────────────────────────────────────────────────────────────

def _finding_to_dict(finding: Optional[Finding],
                     mapped_stmt: Optional[MappedStatement] = None
                     ) -> Dict[str, Any]:
    """Convert a Stage 0 Finding + Stage 1 MappedStatement into a unified
    result dict with the citation for the problematic row."""
    result: Dict[str, Any] = {
        "error_detected":  finding is not None,
        "error_type":      None,
        "error_detail":    None,
        "correct_value":   None,
        "stated_value":    None,
        "problematic_row": None,
        "concept":         None,
        "citation":        None,
        "citation_source": "none",
        "statement_type":  None,
    }

    if finding is None:
        # No error detected — still report statement type if available
        if mapped_stmt is not None:
            result["statement_type"] = mapped_stmt.statement_type
        return result

    result["error_type"]    = finding.error_type
    result["error_detail"]  = finding.detail
    result["correct_value"] = finding.correct_value
    result["stated_value"]  = finding.stated_value
    result["problematic_row"] = finding.problemable_entry if hasattr(finding, 'problemable_entry') else finding.problematic_entry

    # Look up the citation for the problematic row
    if mapped_stmt is not None:
        result["statement_type"] = mapped_stmt.statement_type
        row_idx = finding.problematic_entry
        # Find the mapped row for this index
        for row in mapped_stmt.rows:
            if row.row_idx == row_idx:
                result["concept"]         = row.concept
                result["citation"]        = row.asc_primary
                result["citation_source"] = row.strategy if row.strategy != "none" else "static_map"
                # If taxonomy enrichment gave a better citation, use that
                if row.asc_primary:
                    result["citation_source"] = "taxonomy" if row.strategy in ("exact", "stem_exact", "fuzzy") else "static_map"
                break

    return result


def _enrich_and_extract_citation(mapped_stmt: MappedStatement,
                                 finding: Optional[Finding]) -> Dict[str, Any]:
    """Run taxonomy enrichment on the mapped statement and extract the citation
    for the problematic row (if any)."""
    graph = _get_graph()
    enriched = enrich_with_taxonomy(mapped_stmt, graph)

    result: Dict[str, Any] = {
        "error_detected":  finding is not None,
        "error_type":      None,
        "error_detail":    None,
        "correct_value":   None,
        "stated_value":    None,
        "problematic_row": None,
        "concept":         None,
        "citation":        None,
        "citation_source": "none",
        "statement_type":  enriched.statement.statement_type,
        "citation_summary": enriched.summary(),
    }

    if finding is not None:
        result["error_type"]    = finding.error_type
        result["error_detail"]  = finding.detail
        result["correct_value"] = finding.correct_value
        result["stated_value"]  = finding.stated_value
        result["problematic_row"] = finding.problematic_entry

        # Find the enriched row for the problematic index
        row_idx = finding.problematic_entry
        for row in enriched.statement.rows:
            if row.row_idx == row_idx:
                result["concept"]  = row.concept
                if row.asc_primary:
                    result["citation"]        = f"FASB ASC {row.asc_primary}"
                    result["citation_source"] = "taxonomy"
                elif row.asc_refs:
                    result["citation"]        = f"FASB ASC {row.asc_refs[0]}"
                    result["citation_source"] = "taxonomy"
                break

    return result


# ── FinMR path ────────────────────────────────────────────────────────────────

def _audit_finmr(row: dict) -> Dict[str, Any]:
    """Run audit on a FinMR record.

    FinMR records contain XBRL instance documents with DQC rule violations.
    Detection = arithmetic verification (finmr_verifier).
    Citation  = TaxonomyGraph lookup on the target concept.
    """
    parsed = finmr_parse(row)
    pred = finmr_predict(parsed)

    graph = _get_graph()
    q = parsed.question

    # Determine error type from DQC rule + status
    error_type = None
    error_detail = None
    error_detected = False

    if q is not None:
        if pred["ext_status"] == "ok" and pred["calc_status"] == "ok":
            # Check if extracted != calculated (that's the error)
            from finmr_verifier import _to_float
            ext = _to_float(pred["extracted_value"])
            calc = _to_float(pred["calculated_value"])
            if ext is not None and calc is not None and abs(ext - calc) > 1e-6:
                error_detected = True
                error_type = f"DQC Violation ({parsed.dqc_rule})"
                error_detail = (
                    f"Reported value {pred['extracted_value']} does not match "
                    f"calculated value {pred['calculated_value']} per "
                    f"{parsed.dqc_rule}."
                )
        elif pred["ext_status"] != "ok":
            error_detail = f"Could not extract reported value ({pred['ext_status']})"
        elif pred["calc_status"] != "ok":
            error_detail = f"Could not calculate expected value ({pred['calc_status']})"

    # Get citation for the target concept
    concept = None
    citation = None
    citation_source = "none"

    if q is not None:
        concept = f"us-gaap:{q.concept_bare}"
        detail = graph.get_fasb_citation_detail(q.concept_bare)
        if detail["asc_primary"]:
            citation = f"FASB ASC {detail['asc_primary']}"
            citation_source = detail["source"]

    return {
        "error_detected":   error_detected,
        "error_type":       error_type,
        "error_detail":     error_detail,
        "correct_value":    pred["calculated_value"] if error_detected else None,
        "stated_value":     pred["extracted_value"] if error_detected else None,
        "concept":          concept,
        "citation":         citation,
        "citation_source":  citation_source,
        "statement_type":   None,  # FinMR doesn't classify by statement type
        "dqc_rule":         parsed.dqc_rule,
        "ext_status":       pred["ext_status"],
        "calc_status":      pred["calc_status"],
    }


# ── raw concept path ──────────────────────────────────────────────────────────

def _audit_concept(concept_name: str) -> Dict[str, Any]:
    """Look up the ASC citation for a single XBRL concept name.

    No error detection — just the citation lookup.
    """
    graph = _get_graph()
    # Strip us-gaap: prefix if present
    bare = concept_name.replace("us-gaap:", "").replace("us_gaap_", "")
    detail = graph.get_fasb_citation_detail(bare)

    citation = None
    if detail["asc_primary"]:
        citation = f"FASB ASC {detail['asc_primary']}"

    return {
        "error_detected":   False,
        "error_type":       None,
        "error_detail":     "No detection performed (concept-only lookup)",
        "correct_value":    None,
        "stated_value":     None,
        "concept":          f"us-gaap:{bare}",
        "citation":         citation,
        "citation_source":  detail["source"],
        "statement_type":   None,
        "matched_concept":  detail["matched_concept"],
    }


# ── AuditBench path ───────────────────────────────────────────────────────────

def _audit_auditbench(item: dict) -> Dict[str, Any]:
    """Run the full AuditBench pipeline on one item:
    Stage 0 (detect error) → Stage 1 (map to concept + get citation).

    Optimized: only looks up the taxonomy citation for the problematic row,
    not all rows — avoids ~20x unnecessary TaxonomyGraph calls per item.
    """
    # Stage 0: detect the error
    a = stage0a_verify(item)
    b = stage0b_check(item)
    finding = combine_findings(a, b)

    # Stage 1: map rows to XBRL concepts (fast — no taxonomy lookup)
    mapped = map_statement(item)

    result: Dict[str, Any] = {
        "error_detected":  finding is not None,
        "error_type":      None,
        "error_detail":    None,
        "correct_value":   None,
        "stated_value":    None,
        "problematic_row": None,
        "concept":         None,
        "citation":        None,
        "citation_source": "none",
        "statement_type":  mapped.statement_type,
    }

    if finding is not None:
        result["error_type"]    = finding.error_type
        result["error_detail"]  = finding.detail
        result["correct_value"] = finding.correct_value
        result["stated_value"]  = finding.stated_value
        result["problematic_row"] = finding.problematic_entry

        # Look up citation ONLY for the problematic row
        row_idx = finding.problematic_entry
        for row in mapped.rows:
            if row.row_idx == row_idx:
                result["concept"] = row.concept
                # Try static map citation first
                if row.asc_primary:
                    result["citation"] = f"FASB ASC {row.asc_primary}"
                    result["citation_source"] = "static_map"
                # Then try taxonomy graph for a better citation
                if row.concept:
                    graph = _get_graph()
                    bare = row.concept.replace("us-gaap:", "")
                    detail = graph.get_fasb_citation_detail(bare)
                    if detail["asc_primary"]:
                        result["citation"] = f"FASB ASC {detail['asc_primary']}"
                        result["citation_source"] = detail["source"]
                break

    return result


# ── public API ────────────────────────────────────────────────────────────────

def run_audit(
    data: Union[dict, str],
    source: str = "auto",
) -> Dict[str, Any]:
    """Unified audit entry point.

    Args:
        data:   The input to audit. Can be:
                - AuditBench item dict ({"table": ..., "transaction_data": ...})
                - FinMR record dict ({"query": ..., "answer": ..., "dqc_id": ...})
                - Raw concept name string ("CashAndCashEquivalentsAtCarryingValue")
        source: Input format. "auto" (default) infers from the data.
                Can be "auditbench", "finmr", or "concept".

    Returns:
        A dict with keys:
            error_detected   : bool
            error_type       : str | None
            error_detail     : str | None
            correct_value    : float | None
            stated_value     : float | None
            concept          : str | None   (e.g. "us-gaap:Cash...")
            citation         : str | None   (e.g. "FASB ASC 230-10-45-5")
            citation_source  : str          ("taxonomy" | "parent_fallback" | ...)
            statement_type   : str | None
    """
    # Auto-detect source
    if source == "auto":
        if isinstance(data, str):
            source = "concept"
        elif isinstance(data, dict):
            if "query" in data and "dqc_id" in data:
                source = "finmr"
            elif "table" in data:
                source = "auditbench"
            else:
                raise ValueError(
                    "Cannot auto-detect input format. "
                    "Pass source='auditbench', 'finmr', or 'concept'."
                )
        else:
            raise TypeError(f"Expected dict or str, got {type(data)}")

    if source == "auditbench":
        return _audit_auditbench(data)
    elif source == "finmr":
        return _audit_finmr(data)
    elif source == "concept":
        return _audit_concept(data)
    else:
        raise ValueError(f"Unknown source: {source}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    ap = argparse.ArgumentParser(description="Unified audit: detect + cite.")
    ap.add_argument("--auditbench-index", type=int, default=None,
                    help="Index into AuditBench single-error dataset")
    ap.add_argument("--finmr-index", type=int, default=None,
                    help="Index into FinMR test split")
    ap.add_argument("--concept", type=str, default=None,
                    help="Raw XBRL concept name to look up")
    ap.add_argument("--json", action="store_true",
                    help="Output as JSON instead of formatted text")
    args = ap.parse_args()

    result = None

    if args.auditbench_index is not None:
        from parser import load_single_error
        items = load_single_error()
        result = run_audit(items[args.auditbench_index], source="auditbench")
    elif args.finmr_index is not None:
        from datasets import load_dataset
        ds = load_dataset("TheFinAI/FinMR", split="test")
        result = run_audit(ds[args.finmr_index], source="finmr")
    elif args.concept is not None:
        result = run_audit(args.concept, source="concept")
    else:
        ap.error("Provide one of --auditbench-index, --finmr-index, or --concept")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print("AUDIT RESULT")
        print("=" * 60)
        print(f"  Error detected   : {result['error_detected']}")
        if result.get("error_type"):
            print(f"  Error type       : {result['error_type']}")
        if result.get("error_detail"):
            print(f"  Error detail     : {result['error_detail']}")
        if result.get("stated_value") is not None:
            print(f"  Stated value     : {result['stated_value']}")
        if result.get("correct_value") is not None:
            print(f"  Correct value    : {result['correct_value']}")
        if result.get("concept"):
            print(f"  XBRL concept     : {result['concept']}")
        if result.get("citation"):
            print(f"  FASB citation    : {result['citation']}")
            print(f"  Citation source  : {result['citation_source']}")
        if result.get("statement_type"):
            print(f"  Statement type   : {result['statement_type']}")
        if result.get("dqc_rule"):
            print(f"  DQC rule         : {result['dqc_rule']}")
        if result.get("citation_summary"):
            cs = result["citation_summary"]
            print(f"  Citation summary : coverage={cs['citation_coverage']:.1%} "
                  f"taxonomy={cs['taxonomy_hits']} "
                  f"fallback={cs['parent_fallback_hits']} "
                  f"static={cs['static_map_kept']}")
        print("=" * 60)


if __name__ == "__main__":
    _cli()
