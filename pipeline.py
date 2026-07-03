"""
pipeline.py — IntelliAudit end-to-end deterministic pipeline (Stage 0 → 1).

The single integration point the LLM stage (Stage 2) plugs into. For one
AuditBench item it runs:

    Stage 0A (arithmetic) + 0B (equation)  → combine_findings → verdict
    EDGAR mapper + Stage 1 taxonomy         → broken-row citation + candidate set

and returns one structured ``AuditRecord`` carrying everything Stage 2/3 need:
the deterministic judgment, the localized error (+ corrected value), the grounded
citation candidate set, a *positive* "verified-consistent" signal, and the
evidence trail.

Two things Stage 2 should consume:
  * record.abstained        — True ⇒ Stage 0 had no proof; route to the LLM.
  * record.verified_consistent — True ⇒ every checkable subtotal foots and every
    accounting identity holds. This is the deterministic anti-over-auditing
    signal: if the LLM wants to flag an arithmetic error on a verified-consistent
    table, it is almost certainly hallucinating (see pipeline_eval.py veto).

Handoff:
    from pipeline import run_pipeline
    from taxonomy_graph import TaxonomyGraph
    rec = run_pipeline(item, TaxonomyGraph())
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import stage0a
import stage0b
from stage0_common import (
    build_table, build_transactions, combine_findings,
    rows_of, subtotal_expected_map,
)
from stage1_arelle import run_stage1
from taxonomy_graph import TaxonomyGraph


@dataclass
class AuditRecord:
    # ── verdict ──────────────────────────────────────────────────────────────
    judgment: str = "Unverified"          # "Incorrect" once Stage 0 proves an error
    abstained: bool = True                 # Stage 0 produced no finding
    verified_consistent: bool = False      # positive clean signal (all checks pass)
    deterministic: bool = False            # Stage 0 resolved it → LLM can be skipped

    # ── localized error (present when judgment == "Incorrect") ───────────────
    error_type: Optional[str] = None
    problematic_entry: Optional[int] = None
    correct_value: Optional[float] = None
    stated_value: Optional[float] = None
    source: str = "none"                   # "0A" | "0B" | "none"

    # ── grounded citation for the flagged row (for Stage 2 to confirm/select) ─
    citation_primary: Optional[str] = None
    citation_candidates: List[str] = field(default_factory=list)
    citation_source: Optional[str] = None

    # ── evidence trail ───────────────────────────────────────────────────────
    n_subtotals_checked: int = 0
    n_identities_checked: int = 0
    footing: List[dict] = field(default_factory=list)
    equations: List[dict] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "judgment": self.judgment, "abstained": self.abstained,
            "verified_consistent": self.verified_consistent,
            "deterministic": self.deterministic,
            "error_type": self.error_type, "problematic_entry": self.problematic_entry,
            "correct_value": self.correct_value, "stated_value": self.stated_value,
            "source": self.source,
            "citation_primary": self.citation_primary,
            "citation_candidates": self.citation_candidates,
            "citation_source": self.citation_source,
            "n_subtotals_checked": self.n_subtotals_checked,
            "n_identities_checked": self.n_identities_checked,
            "detail": self.detail,
        }


def _consistency(a, b, df, tx) -> tuple:
    """(verified_consistent, n_subtotals_checked, n_identities_checked).

    Verified-consistent requires (i) no anomaly of any kind from either stage,
    (ii) at least some real verification happened — a clean table we could not
    check against the oracle is *unverified*, not *verified clean* — and
    (iii) no transaction-described leaf is fully absent from the table. Condition
    (iii) is what keeps a *missing-row* error (which leaves no checkable subtotal
    anomaly, so passes (i)) from being mis-certified as clean: if the narrative
    describes a row whose label-core AND value are both gone, the table is NOT
    verified even though the arithmetic we *can* see foots."""
    from stage0_common import TOL, values_match
    n_sub = sum(1 for v in subtotal_expected_map(df, tx).values() if v is not None)
    n_id  = len(b.equations) + _identities_checkable(df)

    table_cores  = {r.core for r in rows_of(df) if r.value is not None}
    table_values = [r.value for r in rows_of(df) if r.value is not None]
    unmatched_tx = any(
        (not e.is_subtotal) and e.value is not None and abs(e.value) > TOL
        and e.core not in table_cores
        and not any(values_match(e.value, tv) for tv in table_values)
        for e in tx.entries
    )

    no_anomaly = not (a.reconciliation or a.footing or a.missing
                      or b.redundant or b.misclassification or b.equations
                      or a.primary or b.primary or a.weak)
    verified = no_anomaly and (not unmatched_tx) and (n_sub + n_id) >= 2
    return verified, n_sub, n_id


def _identities_checkable(df) -> int:
    """How many accounting identities had all their rows present (so were tested)."""
    from stage0b import _check_identities
    # _check_identities only returns *violations*; to count *checked* identities we
    # re-detect presence cheaply via the same _find calls it uses.
    from stage0b import _find
    checked = 0
    if _find(df, "total", "assets") and (
        (_find(df, "total", "liabilities") and any(
            "equity" in r.norm and r.norm.startswith("total") for r in rows_of(df, "subtotal")))
        or any("equity" in r.norm and "liabilities" in r.norm for r in rows_of(df, "subtotal"))):
        checked += 1
    if (_find(df, "total", "net", "sales") or _find(df, "total", "sales")) and \
       _find(df, "total", "cost", "sales") and _find(df, "gross", "margin"):
        checked += 1
    op = _find(df, "cash", "operating", "activities")
    if op and _find(df, "investing", "activities") and _find(df, "financing", "activities") \
       and (_find(df, "increase", "cash") or _find(df, "decrease", "cash")):
        checked += 1
    return checked


def run_pipeline(item: dict, graph: Optional[TaxonomyGraph] = None) -> AuditRecord:
    """Full deterministic pipeline for one AuditBench item."""
    if graph is None:
        graph = TaxonomyGraph()

    # ── Stage 0 ──
    a = stage0a.verify(item)
    b = stage0b.check(item)
    finding = combine_findings(a, b)

    df = build_table(item["table"])
    tx = build_transactions(item.get("transaction_data", "") or "")
    verified, n_sub, n_id = _consistency(a, b, df, tx)

    rec = AuditRecord(
        abstained=finding is None,
        verified_consistent=verified,
        n_subtotals_checked=n_sub,
        n_identities_checked=n_id,
        footing=a.footing,
        equations=b.equations,
    )

    # ── Stage 1 citation (always available; used for the flagged row) ──
    s1 = run_stage1(item, graph)

    def _cite_for(idx):
        row = next((r for r in s1.statement.rows if r.row_idx == idx), None)
        if row is None:
            return None, [], None
        return row.asc_primary, row.asc_candidates, s1.citation_sources.get(idx)

    if finding is not None:
        rec.judgment          = "Incorrect"
        rec.deterministic     = True
        rec.error_type        = finding.error_type
        rec.problematic_entry = finding.problematic_entry
        rec.correct_value     = finding.correct_value
        rec.stated_value      = finding.stated_value
        rec.source            = finding.source
        rec.detail            = finding.detail
        cp, cc, cs = _cite_for(finding.problematic_entry)
        rec.citation_primary, rec.citation_candidates, rec.citation_source = cp, cc, cs

    return rec


# ── CLI demo ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse, json
    from parser import load_single_error

    ap = argparse.ArgumentParser(description="IntelliAudit pipeline demo")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    graph = TaxonomyGraph(); _ = graph.available
    items = load_single_error(seed=args.seed, n=args.n)
    for i, item in enumerate(items):
        rec = run_pipeline(item, graph)
        print(f"[{i}] judgment={rec.judgment:10s} abstained={rec.abstained} "
              f"verified={rec.verified_consistent}  "
              f"{rec.error_type or '-'} row={rec.problematic_entry} "
              f"cite={rec.citation_primary} cands={rec.citation_candidates}")
