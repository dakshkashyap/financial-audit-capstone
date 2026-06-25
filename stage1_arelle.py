"""
Stage 1 · Arelle — US-GAAP Taxonomy Citation Enrichment.

Sits between the EDGAR Mapper (irvin) and the focused LLM (Stage 2 / man-mad).

What it does
------------
For every MappedRow that has an XBRL concept (from edgar_mapper.map_statement):
  1. Query TaxonomyGraph for the concept's FASB ASC citation from the live
     US-GAAP reference linkbase (direct or parent-fallback traversal).
  2. If the taxonomy returns a citation, upgrade the row's asc_primary / asc_refs
     fields (taxonomy is more specific than the static xbrl_concept_map.json).
  3. If the taxonomy has no entry AND the row already has a static-map citation,
     keep it unchanged.
  4. Track the citation source for every row in Stage1Result.citation_sources.

Rows NOT mapped by edgar_mapper (concept is None) are untouched.

Cannot hallucinate: every citation either comes from FASB's own published
taxonomy XML (TaxonomyGraph) or from irvin's hand-curated static map.

Architecture context
--------------------
  Stage 0A/0B (Daksh)  → deterministic arithmetic gate
  EDGAR Mapper (irvin) → row label → us-gaap:ConceptName + static ASC
  Stage 1 (man-mad)    → THIS FILE — taxonomy graph traversal → authoritative ASC
  Stage 2 (man-mad)    → focused LLM with citations injected into prompt
  Stage 3 (man-mad)    → SymPy + Pydantic deterministic reviser

Handoff contract for Stage 2
-----------------------------
  from stage1_arelle import run_stage1, Stage1Result
  from taxonomy_graph import TaxonomyGraph

  graph  = TaxonomyGraph()          # singleton; lazy-loaded on first call
  result = run_stage1(item, graph)  # item = AuditBench dict from parser.py

  # result.statement  → MappedStatement with enriched asc_primary / asc_refs
  # result.citation_sources[row_idx]
  #     → "taxonomy" | "parent_fallback" | "static_map" | "error_type_fallback" | "none"
  # result.taxonomy_available  → bool; False when offline (graceful fallback)
  #
  # To retrieve the best citation for a specific error row (for Stage 2 prompt):
  #   from edgar_mapper import get_citation_for_error
  #   asc_primary, asc_refs = get_citation_for_error(error_type, mapped_row)

Usage (standalone)
------------------
  python stage1_arelle.py              # demo on 3 correct items
  python stage1_arelle.py --n 5        # demo on 5 items
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

from edgar_mapper import MappedRow, MappedStatement, map_statement
from taxonomy_graph import TaxonomyGraph

# Shared singleton — callers may pass their own; run_stage1 falls back to this.
_DEFAULT_GRAPH: Optional[TaxonomyGraph] = None


def _get_default_graph() -> TaxonomyGraph:
    global _DEFAULT_GRAPH
    if _DEFAULT_GRAPH is None:
        _DEFAULT_GRAPH = TaxonomyGraph()
    return _DEFAULT_GRAPH


# ── result dataclass ──────────────────────────────────────────────────────────

# Citation source labels (in priority order, highest first)
SOURCE_TAXONOMY        = "taxonomy"
SOURCE_PARENT_FALLBACK = "parent_fallback"
SOURCE_STATIC_MAP      = "static_map"
SOURCE_ERROR_FALLBACK  = "error_type_fallback"
SOURCE_NONE            = "none"


@dataclass
class Stage1Result:
    """Output of Stage 1 enrichment.

    Wraps the (now-enriched) MappedStatement plus per-row provenance so
    Stage 2 can make informed decisions about which citations to trust.
    """
    statement:         MappedStatement

    # row_idx → source label for every valued row
    citation_sources: Dict[int, str] = field(default_factory=dict)

    # aggregate counters
    n_taxonomy_hits:   int = 0   # direct taxonomy lookups that succeeded
    n_parent_hits:     int = 0   # parent-fallback hits
    n_static_kept:     int = 0   # rows already had static-map citation (kept)
    n_upgraded:        int = 0   # rows with concept but no prior ASC → got one from taxonomy
    n_no_citation:     int = 0   # rows with concept but no citation from any source
    n_unmapped:        int = 0   # rows without a concept (edgar_mapper gave up)
    taxonomy_available: bool = False

    def summary(self) -> dict:
        total = (self.n_taxonomy_hits + self.n_parent_hits +
                 self.n_static_kept   + self.n_no_citation + self.n_unmapped)
        return {
            "taxonomy_available":  self.taxonomy_available,
            "total_valued_rows":   total,
            "taxonomy_hits":       self.n_taxonomy_hits,
            "parent_fallback_hits": self.n_parent_hits,
            "static_map_kept":     self.n_static_kept,
            "no_citation":         self.n_no_citation,
            "unmapped_rows":       self.n_unmapped,
            "upgraded":            self.n_upgraded,
            "citation_coverage":   round(
                (self.n_taxonomy_hits + self.n_parent_hits + self.n_static_kept) / total, 4
            ) if total else 0.0,
        }


# ── core enrichment logic ─────────────────────────────────────────────────────

def enrich_with_taxonomy(
    mapped_stmt: MappedStatement,
    graph: TaxonomyGraph,
) -> Stage1Result:
    """Enrich every MappedRow that has a concept with a taxonomy citation.

    Taxonomy citations (direct or parent-fallback) override the static
    xbrl_concept_map.json citations because they are more specific.
    Rows already having a static citation but no taxonomy match are kept.
    """
    result = Stage1Result(
        statement=mapped_stmt,
        taxonomy_available=graph.available,
    )

    for row in mapped_stmt.rows:
        if row.value is None:
            continue   # header rows carry no financial value; skip

        if not row.mapped:
            # edgar_mapper could not find a concept — nothing Stage 1 can do
            result.n_unmapped += 1
            result.citation_sources[row.row_idx] = SOURCE_NONE
            continue

        # Strip the "us-gaap:" prefix so TaxonomyGraph receives the bare name
        concept_bare = row.concept.replace("us-gaap:", "") if row.concept else ""

        had_citation = bool(row.asc_primary)

        if graph.available and concept_bare:
            detail = graph.get_fasb_citation_detail(concept_bare)
            src    = detail["source"]  # "taxonomy" | "parent_fallback" | "none"

            if src in (SOURCE_TAXONOMY, SOURCE_PARENT_FALLBACK):
                # Upgrade the row's citation fields
                row.asc_primary = detail["asc_primary"]
                row.asc_refs    = detail["asc_refs"]
                # asc_title remains from static map (human-readable topic name)

                if src == SOURCE_TAXONOMY:
                    result.n_taxonomy_hits += 1
                    result.citation_sources[row.row_idx] = SOURCE_TAXONOMY
                else:
                    result.n_parent_hits += 1
                    result.citation_sources[row.row_idx] = SOURCE_PARENT_FALLBACK

                if not had_citation:
                    result.n_upgraded += 1
                continue

        # Taxonomy unavailable or concept not in taxonomy
        if had_citation:
            # Keep the static-map citation irvin already provided
            result.n_static_kept += 1
            result.citation_sources[row.row_idx] = SOURCE_STATIC_MAP
        else:
            result.n_no_citation += 1
            result.citation_sources[row.row_idx] = SOURCE_NONE

    return result


# ── top-level entry point (called by Stage 2 and eval harness) ────────────────

def run_stage1(
    item: dict,
    graph: Optional[TaxonomyGraph] = None,
) -> Stage1Result:
    """Full Stage 1 pipeline for one AuditBench item.

    1. EDGAR Mapper: table rows → XBRL concepts + static ASC citations
    2. Taxonomy enrichment: XBRL concepts → authoritative FASB ASC citations

    Returns a Stage1Result whose .statement has the enriched MappedRow objects.
    """
    if graph is None:
        graph = _get_default_graph()

    mapped_stmt = map_statement(item)
    return enrich_with_taxonomy(mapped_stmt, graph)


# ── CLI demo ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from parser import load_correct

    ap = argparse.ArgumentParser(description="Stage 1 Arelle demo")
    ap.add_argument("--n",    type=int, default=3, help="Number of items to demo")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    graph = TaxonomyGraph()
    print(f"Taxonomy available: {graph.available}\n")

    items = load_correct(seed=args.seed, n=args.n)
    for i, item in enumerate(items):
        result = run_stage1(item, graph)
        ms     = result.statement
        summ   = result.summary()

        print(f"[{i}] {ms.company} | {ms.statement_type} | {ms.period}")
        print(f"     EDGAR coverage : {ms.n_mapped}/{ms.n_valued_rows} rows")
        print(f"     Stage 1 summary: "
              f"taxonomy={result.n_taxonomy_hits}  "
              f"parent={result.n_parent_hits}  "
              f"static_kept={result.n_static_kept}  "
              f"upgraded={result.n_upgraded}  "
              f"no_citation={result.n_no_citation}")
        print(f"     Citation coverage after Stage 1: {summ['citation_coverage']:.1%}")

        print(f"     {'idx':>3}  {'label':42s}  {'concept':40s}  {'ASC':20s}  source")
        print(f"     {'---':>3}  {'-'*42}  {'-'*40}  {'-'*20}  ------")
        for row in ms.rows:
            if row.value is None:
                continue
            concept = (row.concept or "").replace("us-gaap:", "")[:38]
            asc     = row.asc_primary or ""
            src     = result.citation_sources.get(row.row_idx, SOURCE_NONE)
            print(f"     {row.row_idx:3d}  {row.label[:42]:42s}  "
                  f"{concept:40s}  {asc:20s}  {src}")
        print()
