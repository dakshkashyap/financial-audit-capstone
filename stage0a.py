"""
Stage 0A — Arithmetic Verifier (deterministic, free, $0).

Tooling: SymPy (exact symbolic arithmetic) + pandas (row structuring).

What it does, per the IntelliAudit architecture:
  1. Recomputes every subtotal/total from the transaction oracle and flags any
     row whose stated value disagrees ("footing" evidence).
  2. Cross-references each *leaf* row against the transaction records to find a
     single changed value  → **Numerical Error** (+ the computed correct value).
  3. Detects a row described by the transactions but absent from the table
     → **Missing Row** (+ the value and the position it belongs at).

It owns the two arithmetic error types (Numerical Error, Missing Row). Semantic
errors (Redundant Row, Misclassification) are Stage 0B's job.

SymPy is used to *prove* the subtotal equation exactly and to *solve* for a
corrected value, honoring the paper's "symbolic, cannot-hallucinate" framing.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional

import sympy as sp

from stage0_common import (
    TOL,
    Finding,
    Stage0AResult,
    Transactions,
    approx_eq,
    build_table,
    build_transactions,
    infer_groups,
    rows_of,
    subtotal_expected_map,
    values_match,
)


def _sym_sum(values: List[float]) -> sp.Expr:
    """Exact symbolic sum of the member values."""
    if not values:
        return sp.Integer(0)
    return sp.Add(*[sp.Rational(str(round(v, 2))) for v in values])


def _reconcile_leaves(df, tx: Transactions) -> List[dict]:
    """Leaf rows whose stated value disagrees with the transaction oracle.

    Three precision guards (→ ~0 false positives on clean tables):
      * matched by *original index* with a label guard (a shifted position has a
        different label, so it's skipped — no false flags on structural errors),
      * the label must be unique in the table (ambiguous repeats like 'Basic'/
        'Diluted' EPS-vs-shares can collide at the same index),
      * magnitude-aware comparison (sign-only differences are a narration
        convention the transactions use, not a value error)."""
    core_counts = Counter(r.core for r in rows_of(df, "leaf"))
    out = []
    for r in rows_of(df, "leaf"):
        if core_counts[r.core] != 1:  # ambiguous label → can't trust index match
            continue
        exp = tx.expected_for_index(r.idx)
        if exp is None or exp.value is None:
            continue
        # Strict core-label guard: on error splits the row indices shift when a
        # row is added/removed, so an exact label match is what proves this is the
        # *same* row and not a fuzzily-similar neighbour. Relaxing it to a fuzzy
        # match was measured to halve precision (Type-EM-among-fired 0.95→0.66,
        # FP 0→0.7%) — Stage 0 keeps coverage low ON PURPOSE and defers the rest
        # to the LLM, so this guard stays strict.
        if exp.core != r.core:        # position shifted → not the same row
            continue
        if values_match(r.value, exp.value):
            continue
        out.append({"idx": r.idx, "label": r.label,
                    "stated": r.value, "correct": exp.value})
    return out


def _check_footing(df, tx: Transactions) -> List[dict]:
    """Subtotal rows whose stated value disagrees with the transaction oracle.
    Pure evidence/cascade — does not by itself decide the error type."""
    out = []
    for r in rows_of(df, "subtotal"):
        hit = tx.unique_by_core(r.core)
        if hit is None or hit.value is None:
            continue
        # SymPy exact equality of the two scalars (ceremony + robustness).
        if sp.simplify(sp.Rational(str(round(r.value, 2)))
                       - sp.Rational(str(round(hit.value, 2)))) != 0:
            out.append({"idx": r.idx, "label": r.label,
                        "stated": r.value, "correct": hit.value})
    return out


def _detect_missing(df, tx: Transactions) -> List[dict]:
    """Transaction leaf entries that have no matching row in the table.

    A row is a candidate when *both* its label-core and its value are absent
    from the table (a deleted row leaves no trace of either) AND some subtotal is
    off by exactly its value (the corroboration in `_subtotal_anomaly_magnitudes`
    — see below). Redundant/Misclassified rows are still present (same
    value/label) so produce zero candidates here.

    `problematic_entry` is the modified-table index of the missing row's
    successor — the position the row should be re-inserted at (matches the
    AuditBench GT convention)."""
    table_cores = {r.core for r in rows_of(df) if r.value is not None}
    table_values = [r.value for r in rows_of(df) if r.value is not None]
    anomalies = _subtotal_anomaly_magnitudes(df, tx)
    out = []
    for e in tx.entries:
        if e.is_subtotal or e.value is None or abs(e.value) <= TOL:
            continue  # skip $0/nil rows — their absence is meaningless
        if e.core in table_cores:
            continue
        if any(values_match(e.value, tv) for tv in table_values):
            continue  # value is present (up to sign) under another label
        # Corroboration: deleting a row leaves a subtotal off by exactly its
        # value — either against the oracle (subtotal was recomputed) or against
        # the sum of its present members (subtotal left unchanged). Clean
        # statements have no such anomaly, keeping false positives at zero.
        if not any(approx_eq(m, abs(e.value)) for m in anomalies):
            continue
        out.append({"label": e.label, "value": e.value, "entry": e,
                    "successor_idx": _successor_index(df, tx, e)})
    return out


def _subtotal_anomaly_magnitudes(df, tx: Transactions) -> List[float]:
    """Every way a table subtotal is 'off': its magnitude of disagreement with
    the transaction oracle, and its internal footing gap (stated minus the sum
    of its present member leaves). A missing row shows up as one of these."""
    expmap = subtotal_expected_map(df, tx)
    groups = infer_groups(df)
    by_idx = {r.idx: r for r in rows_of(df)}
    mags: List[float] = []
    for s in rows_of(df, "subtotal"):
        exp = expmap.get(s.idx)
        if exp is not None:
            mags.append(abs(abs(exp) - abs(s.value)))
        members = [by_idx[m].value for m in groups.get(s.idx, [])
                   if by_idx[m].value is not None]
        if members:
            mags.append(abs(s.value - float(_sym_sum(members))))
    return [m for m in mags if m > TOL]


def _detect_subtotal_tamper(df, tx: Transactions) -> List[dict]:
    """Numerical errors injected directly on a subtotal/total row (leaves intact).

    A genuinely tampered subtotal fails its *own* footing: the sum of the leaf
    rows in its group no longer equals its stated value. Cascade parents still
    foot (their members were re-summed), so this isolates the origin row.
    SymPy proves the group equation and solves for the corrected value."""
    groups = infer_groups(df)
    expmap = subtotal_expected_map(df, tx)
    by_idx = {r.idx: r for r in rows_of(df)}
    out = []
    for sub_idx, members in groups.items():
        if not members:
            continue  # grand total over subtotals — skip (no direct leaves)
        sub = by_idx[sub_idx]
        leaf_vals = [by_idx[m].value for m in members if by_idx[m].value is not None]
        if len(leaf_vals) != len(members):
            continue
        computed = float(_sym_sum(leaf_vals))
        if approx_eq(computed, sub.value):
            continue  # this subtotal foots fine
        # Strong gate: the leaves are intact (their sum equals the transaction-
        # expected subtotal) and ONLY the stated subtotal is wrong. This is what
        # separates a tampered subtotal from a missing/redundant/misclassified
        # leaf (which would also break the sum, but with intact-leaf-sum != exp).
        exp = expmap.get(sub_idx)
        if exp is None:
            continue
        if approx_eq(computed, exp) and not approx_eq(sub.value, exp):
            out.append({"idx": sub_idx, "label": sub.label,
                        "stated": sub.value, "correct": exp})
    return out


def _successor_index(df, tx: Transactions, missing: "object") -> Optional[int]:
    """Modified-table index of the first row that follows `missing` in the
    original transaction order and is present in the table."""
    table_by_core = {}
    for r in rows_of(df):
        table_by_core.setdefault(r.core, r.idx)
    after = False
    for e in tx.entries:
        if e is missing:
            after = True
            continue
        if after and e.core in table_by_core:
            return table_by_core[e.core]
    # nothing after it → append at the end
    idxs = [r.idx for r in rows_of(df)]
    return (max(idxs) + 1) if idxs else None


def _pick_missing(cands: List[dict]) -> Optional[dict]:
    """Choose the single corroborated missing row to report, or abstain when
    several survive (single-error statements drop exactly one row)."""
    if len(cands) == 1:
        return cands[0]
    return None


def verify(item: dict) -> Stage0AResult:
    """Run Stage 0A on one parser item ({'table', 'transaction_data', ...})."""
    df = build_table(item["table"])
    tx = build_transactions(item.get("transaction_data", "") or "")

    res = Stage0AResult()
    res.reconciliation = _reconcile_leaves(df, tx)
    res.footing = _check_footing(df, tx)
    res.missing = _detect_missing(df, tx)

    # 1. Numerical Error on a leaf wins: a single changed leaf, reported with its
    #    correct value. The footing mismatches on the enclosing subtotal/grand-
    #    total are the arithmetic cascade of that one leaf, collapsed away here.
    if res.reconciliation:
        best = min(res.reconciliation, key=lambda d: d["idx"])
        res.primary = Finding(
            error_type="Numerical Error",
            problematic_entry=best["idx"],
            correct_value=best["correct"],
            stated_value=best["stated"],
            source="0A",
            detail=f"'{best['label']}' stated {best['stated']}, "
                   f"transactions imply {best['correct']}.",
        )
        res.flagged = True
        return res

    # 2. Missing Row: a transaction-described leaf vanished (core+value absent)
    #    and a subtotal is off by exactly its value. One clean candidate → take
    #    it; several survivors (label/sign noise, common on cash flow) → abstain
    #    rather than guess.
    m = _pick_missing(res.missing)
    if m is not None:
        res.primary = Finding(
            error_type="Missing Row",
            problematic_entry=m["successor_idx"],
            correct_value=m["value"],
            source="0A",
            detail=f"'{m['label']}' (value {m['value']}) is described by the "
                   f"transactions but absent from the statement.",
        )
        res.flagged = True
        return res

    # 3. Numerical Error injected on a subtotal itself (leaves intact): the only
    #    row that fails its own footing. This is a *weak* signal — the combiner
    #    only uses it if Stage 0B (Redundant/Misclassification) also abstains,
    #    since those semantic errors can break a subtotal too.
    tamper = _detect_subtotal_tamper(df, tx)
    if len(tamper) == 1:
        t = tamper[0]
        res.weak = Finding(
            error_type="Numerical Error",
            problematic_entry=t["idx"],
            correct_value=t["correct"],
            stated_value=t["stated"],
            source="0A",
            detail=f"Subtotal '{t['label']}' stated {t['stated']}, its leaf "
                   f"rows sum to {t['correct']}.",
        )
        res.flagged = True

    return res
