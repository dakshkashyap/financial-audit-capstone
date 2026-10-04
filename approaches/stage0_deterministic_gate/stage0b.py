"""
Stage 0B — Equation Checker (deterministic, free, $0).

Tooling: pure-Python rule-based checks (no model, no SymPy needed).

Two responsibilities:
  1. Verify structural accounting identities that are definitionally true and
     therefore can only ever be violated by a real error:
        * Total assets = Total liabilities + Total equity
        * Total liabilities and shareholders' equity = Total assets
        * Income statement chain: net sales − cost of sales = gross margin,
          gross margin − operating expenses = operating income, … = net income
        * Cash-flow: operating + investing + financing = change in cash
     A violation is recorded as evidence (a guaranteed structural error).
  2. Localize the two *semantic* error types that arithmetic alone misses:
        * **Redundant Row** — a valued row the transactions never describe,
          whose value exactly inflates its enclosing subtotal.
        * **Misclassification** — a row whose value is correct but which sits in
          the wrong section (its original section, per the transaction order,
          differs from where it now appears).

It owns Redundant Row + Misclassification. Cross-statement and year-over-year
identities are noted as best-effort: the dataset items are single statements, so
sibling statements aren't guaranteed to be available at audit time.
"""

from __future__ import annotations

from typing import List, Optional

from core.stage0_common import (
    TOL,
    Finding,
    Stage0BResult,
    Transactions,
    approx_eq,
    build_table,
    build_transactions,
    infer_groups,
    next_subtotal_after,
    rows_of,
    subtotal_expected_map,
)


# ── identity helpers ──────────────────────────────────────────────────────────
def _find(df, *substrings) -> Optional["object"]:
    """First row whose normalized label contains all given substrings."""
    for r in rows_of(df):
        if r.value is not None and all(s in r.norm for s in substrings):
            return r
    return None


def _check_identities(df) -> List[dict]:
    """Definitional accounting identities, each guarded by row presence."""
    out = []

    def add(name, lhs, rhs):
        if lhs is not None and rhs is not None and not approx_eq(lhs, rhs):
            out.append({"identity": name, "lhs": lhs, "rhs": rhs,
                        "delta": round(lhs - rhs, 2)})

    ta = _find(df, "total", "assets")
    tl = _find(df, "total", "liabilities")
    # equity row, but not the combined "liabilities and ... equity" line
    te = None
    tle = None
    for r in rows_of(df, "subtotal"):
        if "equity" in r.norm and "liabilities" in r.norm:
            tle = r
        elif "equity" in r.norm and r.norm.startswith("total"):
            te = r
    # Balance sheet
    if ta and tl and te:
        add("assets = liabilities + equity", ta.value, tl.value + te.value)
    if ta and tle:
        add("assets = liabilities and equity total", ta.value, tle.value)

    # Income statement chain
    sales = _find(df, "total", "net", "sales") or _find(df, "total", "sales")
    cogs = _find(df, "total", "cost", "sales")
    gm = _find(df, "gross", "margin")
    opex = _find(df, "total", "operating", "expenses")
    opinc = _find(df, "operating", "income")
    ni = _find(df, "net", "income")
    if sales and cogs and gm:
        add("gross margin", gm.value, sales.value - cogs.value)
    if gm and opex and opinc:
        add("operating income", opinc.value, gm.value - opex.value)

    # Cash flow
    op = _find(df, "cash", "operating", "activities")
    inv = _find(df, "investing", "activities")
    fin = _find(df, "financing", "activities")
    chg = _find(df, "increase", "cash") or _find(df, "decrease", "cash")
    if op and inv and fin and chg:
        add("change in cash", chg.value, op.value + inv.value + fin.value)

    return out


# ── semantic error localization ───────────────────────────────────────────────
def _detect_section_anomalies(df, tx: Transactions):
    """Localize Redundant Row and Misclassification by comparing each section
    subtotal to the transaction oracle (positionally aligned).

    Over-statement (a section contains an extra it shouldn't):
      a leaf whose enclosing subtotal is over by exactly that row's value.
        * row NOT described by any transaction → **Redundant Row**
        * row IS described (real line, wrong place) → **Misclassification**

    Under-statement (a section is missing a row it should contain): a subtotal
    short by exactly V, where a transaction-described leaf of magnitude V sits in
    a *different* group → that leaf was **Misclassified** out of this section.
    This catches moves inside a grand total (e.g. current→non-current assets),
    where the enclosing subtotal is unchanged so the over-statement test alone
    would miss it.

    The 'subtotal off by exactly this value' test is the corroboration: clean
    statements foot against the oracle, so nothing fires."""
    expmap = subtotal_expected_map(df, tx)
    groups = infer_groups(df)
    leaves = rows_of(df, "leaf")
    redundant, misclass = [], []

    # over-statement
    for r in leaves:
        if r.value is None or abs(r.value) <= TOL:
            continue
        sub = next_subtotal_after(df, r.idx)
        if sub is None or expmap.get(sub.idx) is None:
            continue
        over = abs(sub.value) - abs(expmap[sub.idx])
        if over <= TOL or not approx_eq(over, abs(r.value)):
            continue
        if tx.value_present(r.core):
            misclass.append({"idx": r.idx, "label": r.label, "section": sub.label})
        else:
            redundant.append({"idx": r.idx, "label": r.label, "value": r.value,
                              "subtotal": sub.label})

    # under-statement → misclassified out of a short section
    flagged = {d["idx"] for d in misclass}
    for sub in rows_of(df, "subtotal"):
        exp = expmap.get(sub.idx)
        if exp is None:
            continue
        short = abs(exp) - abs(sub.value)
        if short <= TOL:
            continue
        members = set(groups.get(sub.idx, []))
        cand = [r for r in leaves
                if r.idx not in members and r.idx not in flagged
                and r.value is not None and approx_eq(abs(r.value), short)
                and tx.value_present(r.core)]
        if len(cand) == 1:                    # unambiguous relocation
            r = cand[0]
            misclass.append({"idx": r.idx, "label": r.label, "section": sub.label})
            flagged.add(r.idx)

    return redundant, misclass


def check(item: dict) -> Stage0BResult:
    """Run Stage 0B on one parser item ({'table', 'transaction_data', ...})."""
    df = build_table(item["table"])
    tx = build_transactions(item.get("transaction_data", "") or "")

    res = Stage0BResult()
    res.equations = _check_identities(df)
    res.redundant, res.misclassification = _detect_section_anomalies(df, tx)

    if res.redundant:
        d = min(res.redundant, key=lambda x: x["idx"])
        res.primary = Finding(
            error_type="Redundant Row",
            problematic_entry=d["idx"],
            stated_value=d["value"],
            source="0B",
            detail=f"'{d['label']}' ({d['value']}) is not supported by any "
                   f"transaction and inflates '{d['subtotal']}'.",
        )
        res.flagged = True
        return res

    if res.misclassification:
        d = min(res.misclassification, key=lambda x: x["idx"])
        res.primary = Finding(
            error_type="Misclassification",
            problematic_entry=d["idx"],
            source="0B",
            detail=f"'{d['label']}' is reported under '{d['section']}' but its "
                   f"value is not part of that section per the transactions.",
        )
        res.flagged = True
        return res

    return res
