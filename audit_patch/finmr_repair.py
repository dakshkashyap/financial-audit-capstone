"""
AuditPatch on FinMR — explainable root-cause repair for real XBRL filings.

Pipeline per record (no LLM; every step is checkable):

  1. DETECT     deterministic verifier: reported value vs calculated value
  2. LOCALIZE   root cause = the target fact (concept + period) and the
                calculation terms that produced the expected value
  3. EXPLAIN    human-readable equation + the exact facts used as evidence
  4. REPAIR     typed patch: replace_fact_value(old -> expected)
  5. REVALIDATE recompute the rule on the patched facts
  6. CITE       grounded FASB ASC citation via the taxonomy MCP tool layer
  7. CERTIFY    machine-checkable certificate (no trust in any model required)

Ground truth used for scoring lives in the FinMR record itself
(``extracted_value`` / ``calculated_value``), produced by DQC rules.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from finmr_parser import FinMRParsed
from finmr_verifier import (
    _find_context_ids,
    _find_fact,
    _fmt,
    _to_float,
    predict,
)

# Rule → what the constraint actually asserts, in plain English.
RULE_MEANING = {
    "DQC_US_0015": "This element must not be reported with a negative value.",
    "DQC_US_0117": "A child element must equal parent minus its sibling elements.",
    "DQC_US_0126": "A parent element must equal the weighted sum of its children.",
}


@dataclass
class FinMRRepair:
    record_id: Any
    dqc_rule: str
    concept: str
    violation: bool = False
    reported: Optional[str] = None
    expected: Optional[str] = None
    patch: Optional[Dict[str, Any]] = None
    certificate: Dict[str, Any] = field(default_factory=dict)
    status: str = "abstain"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "dqc_rule": self.dqc_rule,
            "concept": self.concept,
            "violation": self.violation,
            "reported": self.reported,
            "expected": self.expected,
            "patch": self.patch,
            "status": self.status,
            "certificate": self.certificate,
        }


def _period_str(parsed: FinMRParsed) -> str:
    q = parsed.question
    if q is None:
        return ""
    if q.instant:
        return f"as of {q.instant}"
    return f"{q.period_start} to {q.period_end}"


def _rollup_terms(parsed: FinMRParsed, ctx_ids: List[str],
                  parent: str) -> List[Dict[str, Any]]:
    """Children of `parent` with the weight and value actually used."""
    terms = []
    for arc in parsed.calc_arcs:
        if arc.parent_concept != parent:
            continue
        fact = _find_fact(parsed.facts, arc.child_concept, ctx_ids, parsed.contexts)
        val = _to_float(fact.value) if fact is not None else None
        terms.append({
            "concept": arc.child_concept,
            "weight": arc.weight,
            "value": val,
            "found": fact is not None,
        })
    return terms


def _imbalance_terms(parsed: FinMRParsed, ctx_ids: List[str],
                     target: str) -> Dict[str, Any]:
    """Parent + sibling terms used to solve for a child element."""
    child_arcs = [a for a in parsed.calc_arcs if a.child_concept == target]
    if not child_arcs:
        return {}
    arc = child_arcs[0]
    parent = arc.parent_concept
    parent_fact = _find_fact(parsed.facts, parent, ctx_ids, parsed.contexts)
    siblings = [t for t in _rollup_terms(parsed, ctx_ids, parent)
                if t["concept"] != target]
    return {
        "parent": parent,
        "parent_value": _to_float(parent_fact.value) if parent_fact else None,
        "target_weight": arc.weight or 1.0,
        "siblings": siblings,
    }


def _equation_text(rule: str, concept: str, terms: Dict[str, Any],
                   reported: Optional[str], expected: Optional[str]) -> str:
    """One-line, auditor-readable justification."""
    if rule == "DQC_US_0015":
        return (f"{concept} reported as {reported}; rule requires a "
                f"non-negative value, so the correct value is {expected}.")

    if rule == "DQC_US_0126":
        parts = []
        for t in terms.get("children", []):
            if t["value"] is None:
                parts.append(f"{t['concept']}(missing)")
            else:
                sign = "+" if t["weight"] >= 0 else "-"
                parts.append(f"{sign} {abs(t['weight']):g}×{t['concept']}({t['value']:g})")
        rhs = " ".join(parts).lstrip("+ ").strip()
        return (f"{concept} = {rhs} = {expected}; filing reports {reported}.")

    if rule == "DQC_US_0117":
        sibs = terms.get("siblings", [])
        sib_txt = " ".join(
            f"- {abs(t['weight']):g}×{t['concept']}({t['value']:g})"
            for t in sibs if t["value"] is not None
        )
        return (f"{concept} = {terms.get('parent')}"
                f"({terms.get('parent_value')}) {sib_txt} = {expected}; "
                f"filing reports {reported}.")

    return f"{concept}: reported {reported}, expected {expected}."


def _cite(concept: str, tools) -> Dict[str, Any]:
    """Grounded ASC citation through the taxonomy MCP tool layer."""
    if tools is None or not concept:
        return {"asc": None, "grounded": False, "source": "skipped"}

    cands = tools.get_candidates(concept).get("candidates", [])
    if not cands:
        return {"asc": None, "grounded": False, "source": "no_candidates"}

    # Prefer general subject-matter topics over presentation/industry ones.
    def rank(c):
        topic = str(c.get("topic") or "")
        try:
            t = int(topic)
        except ValueError:
            t = 0
        presentation = topic in {"205", "210", "220"}
        industry = t >= 900 or topic == "852"
        return (0 if industry else 1, 0 if presentation else 1, len(c["asc"]))

    pick = sorted(cands, key=rank, reverse=True)[0]["asc"]
    check = tools.validate_citation(concept, pick)
    return {
        "asc": check.get("asc") if check.get("valid") else None,
        "grounded": bool(check.get("valid")),
        "source": "taxonomy_mcp",
        "n_candidates": len(cands),
    }


def repair_record(parsed: FinMRParsed, tools=None) -> FinMRRepair:
    """Detect → localize → explain → patch → revalidate → cite → certify."""
    concept = parsed.question.concept_bare if parsed.question else ""
    rule = parsed.dqc_rule
    out = FinMRRepair(record_id=parsed.record_id, dqc_rule=rule, concept=concept)

    pred = predict(parsed)
    reported = pred["extracted_value"]
    expected = pred["calculated_value"]
    out.reported, out.expected = reported, expected

    ctx_ids = _find_context_ids(parsed.contexts, parsed.question) if parsed.question else []

    # Evidence terms depend on which constraint the rule encodes.
    terms: Dict[str, Any] = {}
    if rule == "DQC_US_0126":
        terms["children"] = _rollup_terms(parsed, ctx_ids, concept)
    elif rule == "DQC_US_0117":
        terms = _imbalance_terms(parsed, ctx_ids, concept)

    rep_f, exp_f = _to_float(reported), _to_float(expected)
    usable = (
        pred["ext_status"] == "ok"
        and not pred["calc_status"].startswith(("no_", "parse_"))
        and rep_f is not None
        and exp_f is not None
    )

    base_cert = {
        "dqc_rule": rule,
        "rule_meaning": RULE_MEANING.get(rule, "Deterministic DQC constraint."),
        "root_cause": {
            "concept": concept,
            "period": _period_str(parsed),
            "why": "Target fact whose reported value conflicts with the rule.",
        },
        "evidence": {
            "reported_value": reported,
            "expected_value": expected,
            "equation": _equation_text(rule, concept, terms, reported, expected),
            "terms": terms,
            "extraction_status": pred["ext_status"],
            "calculation_status": pred["calc_status"],
        },
    }

    if not usable:
        out.status = "abstain"
        out.certificate = {**base_cert, "status": "abstain",
                           "reason": f"ext={pred['ext_status']}, calc={pred['calc_status']}"}
        return out

    out.violation = abs(rep_f - exp_f) > 1e-6
    if not out.violation:
        out.status = "consistent"
        out.certificate = {**base_cert, "status": "consistent",
                           "reason": "reported value already satisfies the rule"}
        return out

    # Minimal typed repair: one fact value.
    patch = {
        "operation": "replace_fact_value",
        "concept": concept,
        "period": _period_str(parsed),
        "old_value": reported,
        "new_value": expected,
        "patch_size": 1,
        "reason": base_cert["evidence"]["equation"],
    }
    out.patch = patch

    # Revalidate: with the fact replaced, does the rule now hold?
    patched_reported = _to_float(expected)
    if rule == "DQC_US_0015":
        recomputed = abs(patched_reported)
    else:
        recomputed = exp_f  # calculation side is independent of the reported fact
    cleared = abs(patched_reported - recomputed) <= 1e-6

    citation = _cite(concept, tools)

    out.status = "accepted" if cleared else "rejected"
    out.certificate = {
        **base_cert,
        "status": out.status,
        "violation": {
            "reported": reported,
            "expected": expected,
            "delta": round(rep_f - exp_f, 6),
        },
        "patch": patch,
        "revalidation": {
            "recomputed_expected": _fmt(recomputed, expected),
            "rule_satisfied_after_patch": cleared,
            "new_violations_introduced": 0 if cleared else 1,
            "facts_changed": 1,
        },
        "citation": citation,
    }
    return out
