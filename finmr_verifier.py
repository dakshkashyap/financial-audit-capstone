"""
finmr_verifier.py — Deterministic XBRL arithmetic verifier for FinMR.

Reuses the same philosophy as stage0a.py (exact arithmetic, no hallucination)
but operates on XBRL instance + calculation linkbase instead of the
AuditBench [row n]: label|value format.

For each FinMR record:
  Q1 (extracted_value)  — find the fact for target concept + period in instance
  Q2 (calculated_value) — walk the calc arcs, sum child values × weights

Output: {"extracted_value": "...", "calculated_value": "..."}
matching the FinMR ground-truth format exactly.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from finmr_parser import CalcArc, FinMRParsed, FinMRQuestion, XBRLContext, XBRLFact


# ── number normalization (same logic as stage0_common.py) ─────────────────────

_STRIP_RE = re.compile(r'[,\s$]')


def _to_float(s: str) -> Optional[float]:
    """Parse a numeric string from an XBRL fact value or ground truth.
    Handles: '-1,284', '(157,000)', '-0.16', '48795405', etc.
    Returns None if unparseable.
    """
    s = _STRIP_RE.sub('', s.strip())
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _fmt(val: float, reference: str) -> str:
    """Format a float to match the number style of the reference string.

    FinMR ground truth uses the same style as the XBRL filing:
      • no decimal places for whole numbers (integers)
      • commas every 3 digits for large numbers
      • leading minus for negatives
    We mirror the reference's comma/decimal style.
    """
    use_commas = ',' in reference
    # Detect decimal places from reference
    if '.' in reference.replace(',', ''):
        dec_ref = reference.replace(',', '').split('.')[-1]
        decimals = len(dec_ref)
    else:
        decimals = 0

    if decimals == 0:
        int_val = int(round(val))
        if use_commas:
            return f"{int_val:,}"
        return str(int_val)
    else:
        fmt = f"{{:,.{decimals}f}}" if use_commas else f"{{:.{decimals}f}}"
        return fmt.format(val)


# ── context matching ───────────────────────────────────────────────────────────

def _ctx_matches(ctx: XBRLContext, q: FinMRQuestion) -> bool:
    """True when context period matches the question's target period."""
    if q.instant:
        return ctx.instant == q.instant
    return ctx.start_date == q.period_start and ctx.end_date == q.period_end


def _find_context_ids(contexts: Dict[str, XBRLContext],
                      q: FinMRQuestion) -> List[str]:
    """Return ALL context IDs whose period matches the question.
    (Non-dimensional preference is applied later, at the fact level.)
    """
    return [cid for cid, ctx in contexts.items() if _ctx_matches(ctx, q)]


# ── fact lookup ────────────────────────────────────────────────────────────────

def _prefer_non_dim(candidates: List[XBRLFact],
                    contexts: Optional[Dict[str, XBRLContext]]) -> XBRLFact:
    """Among candidates, return the first non-dimensional fact, else the first."""
    if contexts is not None:
        for f in candidates:
            ctx = contexts.get(f.ctx_ref)
            if ctx is not None and not ctx.has_dimension:
                return f
    return candidates[0]


def _find_fact(facts: List[XBRLFact],
               concept_bare: str,
               ctx_ids: List[str],
               contexts: Optional[Dict[str, XBRLContext]] = None,
               prefer_negative: bool = False) -> Optional[XBRLFact]:
    """Return the fact for concept+period.

    Selection among multiple facts (dimensional breakdowns) for the same
    concept+period:
      • prefer_negative=True (DQC_US_0015 sign check): the rule flags an
        improperly-negative value, so prefer a negative-valued fact.
      • otherwise prefer the consolidated (non-dimensional) fact.
    """
    ctx_set = set(ctx_ids)
    candidates = [f for f in facts
                  if f.concept == concept_bare and f.ctx_ref in ctx_set]
    if not candidates:
        return None

    if prefer_negative:
        neg = [f for f in candidates if (_to_float(f.value) or 0.0) < 0]
        if neg:
            return _prefer_non_dim(neg, contexts)

    return _prefer_non_dim(candidates, contexts)


# ── extraction (Q1) ───────────────────────────────────────────────────────────

def extract_reported_value(parsed: FinMRParsed) -> Tuple[Optional[str], str]:
    """Return (value_string, status) for the reported value.

    status: 'ok' | 'no_context' | 'no_fact'
    """
    q = parsed.question
    if q is None:
        return None, 'no_question'

    ctx_ids = _find_context_ids(parsed.contexts, q)
    if not ctx_ids:
        return None, 'no_context'

    prefer_neg = (parsed.dqc_rule == 'DQC_US_0015')
    fact = _find_fact(parsed.facts, q.concept_bare, ctx_ids, parsed.contexts,
                      prefer_negative=prefer_neg)
    if fact is None:
        return None, 'no_fact'

    return fact.value, 'ok'


# ── calculation (Q2) ──────────────────────────────────────────────────────────

def _sum_children(parsed: FinMRParsed, arcs: List[CalcArc],
                  ctx_ids: List[str], exclude: Optional[str] = None
                  ) -> Tuple[float, List[str]]:
    """Σ (weight × child value) over arcs, optionally excluding one child.
    Returns (total, missing_children)."""
    total = 0.0
    missing: List[str] = []
    for arc in arcs:
        if exclude is not None and arc.child_concept == exclude:
            continue
        cf = _find_fact(parsed.facts, arc.child_concept, ctx_ids, parsed.contexts)
        if cf is None:
            missing.append(arc.child_concept)
            continue
        v = _to_float(cf.value)
        if v is None:
            missing.append(arc.child_concept)
            continue
        total += arc.weight * v
    return total, missing


def compute_calculated_value(parsed: FinMRParsed,
                              extracted_raw: Optional[str]) -> Tuple[Optional[str], str]:
    """Compute the expected ("actual") value per the DQC rule's semantics.

    Each rule computes a different quantity:
      DQC_US_0015 (sign check)   expected = abs(reported value)
      DQC_US_0126 (roll-up)      target is a PARENT; expected = Σ(weight×child)
      DQC_US_0117 (imbalance)    target is a CHILD; expected =
                                 (parent − Σ other siblings) / target_weight

    status: 'ok' | 'no_arcs' | 'no_parent' | 'missing_children:N'
            | 'no_context' | 'no_extracted' | 'parse_error'
    """
    q = parsed.question
    if q is None:
        return None, 'no_question'

    ctx_ids = _find_context_ids(parsed.contexts, q)
    if not ctx_ids:
        return None, 'no_context'

    ref_str = extracted_raw or "0"

    # ── DQC_US_0015: sign check — expected = |reported| ───────────────────────
    if parsed.dqc_rule == 'DQC_US_0015':
        if extracted_raw is None:
            return None, 'no_extracted'
        v = _to_float(extracted_raw)
        if v is None:
            return None, 'parse_error'
        return _fmt(abs(v), extracted_raw), 'ok'

    # ── DQC_US_0117: target is a CHILD; solve parent = Σ(weight×child) ─────────
    #     expected_target = (parent − Σ other_siblings×weight) / target_weight
    if parsed.dqc_rule == 'DQC_US_0117':
        child_arcs = [a for a in parsed.calc_arcs
                      if a.child_concept == q.concept_bare]
        if not child_arcs:
            return None, 'no_arcs'
        arc = child_arcs[0]                    # first parent relationship
        parent = arc.parent_concept
        target_weight = arc.weight or 1.0

        parent_fact = _find_fact(parsed.facts, parent, ctx_ids, parsed.contexts)
        if parent_fact is None:
            return None, 'no_parent'
        parent_val = _to_float(parent_fact.value)
        if parent_val is None:
            return None, 'parse_error'

        siblings = [a for a in parsed.calc_arcs if a.parent_concept == parent]
        sib_sum, missing = _sum_children(parsed, siblings, ctx_ids,
                                          exclude=q.concept_bare)
        expected = (parent_val - sib_sum) / target_weight
        if missing:
            return _fmt(expected, ref_str), f'missing_children:{len(missing)}'
        return _fmt(expected, ref_str), 'ok'

    # ── DQC_US_0126: target is a PARENT; expected = Σ(weight×child) ────────────
    arcs = [a for a in parsed.calc_arcs if a.parent_concept == q.concept_bare]
    if not arcs:
        return None, 'no_arcs'
    total, missing = _sum_children(parsed, arcs, ctx_ids)
    if missing:
        return _fmt(total, ref_str), f'missing_children:{len(missing)}'
    return _fmt(total, ref_str), 'ok'


# ── top-level prediction for one record ──────────────────────────────────────

def predict(parsed: FinMRParsed) -> dict:
    """Run the full verifier on one FinMRParsed record.

    Returns:
        {
          "extracted_value": str,    # our prediction
          "calculated_value": str,   # our prediction
          "ext_status": str,         # diagnostic
          "calc_status": str,        # diagnostic
        }
    """
    extracted, ext_status  = extract_reported_value(parsed)
    calculated, calc_status = compute_calculated_value(parsed, extracted)

    return {
        "extracted_value":  extracted  or "0",
        "calculated_value": calculated or "0",
        "ext_status":       ext_status,
        "calc_status":      calc_status,
    }


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datasets import load_dataset
    from finmr_parser import parse_record

    ds = load_dataset("TheFinAI/FinMR", split="test")
    seen: dict = {}
    for row in ds:
        rule = row["dqc_id"].strip('"')
        if rule not in seen:
            seen[rule] = row
        if len(seen) == 3:
            break

    for rule, row in seen.items():
        rec  = parse_record(row)
        pred = predict(rec)
        print(f"\nDQC: {rec.dqc_rule}  id={rec.record_id}")
        print(f"  Predicted extracted  : {pred['extracted_value']:>20}  ({pred['ext_status']})")
        print(f"  GT extracted         : {rec.gt_extracted:>20}")
        print(f"  Predicted calculated : {pred['calculated_value']:>20}  ({pred['calc_status']})")
        print(f"  GT calculated        : {rec.gt_calculated:>20}")
        ext_match  = _to_float(pred['extracted_value'])  == _to_float(rec.gt_extracted)
        calc_match = _to_float(pred['calculated_value']) == _to_float(rec.gt_calculated)
        print(f"  extracted match: {ext_match}  |  calculated match: {calc_match}")
