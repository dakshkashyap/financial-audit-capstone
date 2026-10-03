"""
stage2_llm.py — IntelliAudit Stage 2: the focused, evidence-grounded LLM.

Unlike the AuditBench baseline (one six-in-one prompt that makes the model do
arithmetic, recall citations, AND hunt for the row), Stage 2 is called ONLY when
the deterministic gate abstains, and it is handed the gate's evidence:

  * a verified-consistent flag  — "the math already checks out, don't invent a
    numerical error" (this is the anti-over-auditing lever);
  * any subtotal footing mismatches the gate did find;
  * a per-row GROUNDED CITATION set — candidate ASC topics from Stage 1; the model
    SELECTS from these, it never invents a citation (citation = retrieval).

Output is the AuditBench JSON schema, so evaluate.py scores it unchanged.

The model id matches the baseline (claude-opus-4-6) so the ONLY variable between
"LLM alone" and "IntelliAudit" is the architecture, not the model.
"""
from __future__ import annotations

import json
from typing import Optional

from approaches.full_pipeline.intelliaudit_runner import (
    _make_client, _extract_json, TEMPERATURE, PROVIDERS)
from core.metrics import _norm_type, extract_pred_errors, citation_codes
from core.frameworks import resolve_framework

# Arithmetic claims are the only ones a verified-consistent table can refute.
# Redundant / Misclassification can be real even when every subtotal foots.
_ARITHMETIC_TYPES = {"numerical error", "missing row"}
_STRUCTURAL_TYPES = {"redundant row", "misclassification"}

_ROLE = (
    "You are a careful financial-statement auditor verifying whether a statement is "
    "faithfully prepared from its supporting transactions.\n\n"
    "The four error kinds are:\n"
    "  - Numerical Error  : a single reported value was changed.\n"
    "  - Missing Row      : a row that belongs was deleted.\n"
    "  - Redundant Row    : an extra, unsupported row was inserted.\n"
    "  - Misclassification: a real row was placed in the wrong section.\n\n"
    "A deterministic arithmetic engine has ALREADY recomputed the totals and checked "
    "the accounting identities. TRUST that evidence. Do not re-derive the math. "
    "When you flag a row, cite its standard ONLY from the candidate ASC "
    "paragraphs given for that row. Prefer the full paragraph "
    "(ASC 230-10-45-13) over a vague topic (ASC 230)."
)

_ROLE_IFRS = (
    "You are a careful financial-statement auditor verifying whether an IFRS statement is "
    "faithfully prepared from its supporting transactions. Do not apply US GAAP.\n\n"
    "The four error kinds are:\n"
    "  - Numerical Error  : a single reported value was changed.\n"
    "  - Missing Row      : a row that belongs was deleted.\n"
    "  - Redundant Row    : an extra, unsupported row was inserted.\n"
    "  - Misclassification: a real row was placed in the wrong section.\n\n"
    "A deterministic arithmetic engine has ALREADY recomputed the totals and checked "
    "the accounting identities. TRUST that evidence. Do not re-derive the math. "
    "When you flag a row, cite its standard ONLY from the candidate IAS/IFRS standards "
    "given for that row. Do not cite an ASC topic."
)

_WHEN_CONSISTENT = (
    "\n\nThe engine found no anomaly in the arithmetic checks it could perform. "
    "This is partial evidence, not a certificate that every value or missing row "
    "is correct. Assess unsupported rows and the remaining evidence. Return "
    "'Incorrect' only when you can identify a specific supported defect."
)

_WHEN_ANOMALY = (
    "\n\nThe engine found real footing or identity mismatches, listed below. Do NOT "
    "default to 'Correct'. Investigate those rows first: a Numerical Error or a "
    "Missing Row is likely. Flag the row the evidence points to. Do not invent a "
    "second error on a row the engine did not flag."
)

_WHEN_UNVERIFIED = (
    "\n\nThe engine could not fully verify this statement. Audit it from the "
    "supporting transactions. Do not assume an error is present, and do not ignore "
    "a row the transactions cannot support."
)


def system_for(record, framework: str = "us-gaap") -> str:
    """Conservative only when the arithmetic is verified clean.

    A globally conservative prompt suppressed real errors on tables the gate
    could not certify. Calibration follows the evidence block, not a default.
    """
    if getattr(record, "verified_consistent", False):
        policy = _WHEN_CONSISTENT
    elif getattr(record, "footing", None) or getattr(record, "equations", None):
        policy = _WHEN_ANOMALY
    else:
        policy = _WHEN_UNVERIFIED
    role = _ROLE_IFRS if framework == "ifrs" else _ROLE
    return role + policy


def claimed_error_types(parsed: dict | None) -> list[str]:
    if not parsed:
        return []
    return [_norm_type(e.get("Error Type", "")) for e in extract_pred_errors(parsed)]


def apply_consistency_veto(parsed: dict | None, *, verified_consistent: bool,
                           original_table: str,
                           verified_error_absence: bool = False) -> tuple[dict | None, bool]:
    """Veto only with an additional complete error-absence certificate.

    Returns ``(parsed, vetoed)``. A Redundant or Misclassification claim is left
    in place: those defects leave the subtotals footing, so the arithmetic
    certificate does not refute them. An Incorrect verdict with no named type
    is retained. Passing some checkable identities alone does not certify all
    cells, so legacy callers providing only verified_consistent do not veto.
    """
    if not parsed or not verified_consistent or not verified_error_absence:
        return parsed, False
    judgment = str(parsed.get("General Judgment",
                              parsed.get("General Judgement", ""))).strip().lower()
    if judgment != "incorrect":
        return parsed, False
    types = [t for t in claimed_error_types(parsed) if t]
    if not types:
        return parsed, False
    if any(t in _STRUCTURAL_TYPES for t in types):
        return parsed, False
    if types and any(t not in _ARITHMETIC_TYPES for t in types):
        return parsed, False
    return {
        "General Judgment": "Correct",
        "Corrected Statements": original_table,
    }, True

_OUTPUT_SPEC_IFRS = (
    'Respond with ONLY a JSON object in EXACTLY this schema:\n'
    '{\n'
    '  "General Judgment": "Correct" | "Incorrect",\n'
    '  "Information for error 1": {\n'
    '    "Error Identification": {"Error Type": "<one of the four types>", '
    '"Problematic Entry": "Row <n>"},\n'
    '    "Error Resolution": "<one or two sentences>",\n'
    '    "Standards Citation": "IAS <n> or IFRS <n> from the candidates for that row"\n'
    '  },\n'
    '  "Corrected Statements": "<the full corrected table, or the original if Correct>"\n'
    '}\n'
    'If "General Judgment" is "Correct", omit the "Information for error" blocks. '
    'For multiple errors add "Information for error 2", etc. '
    'Cite one applicable IAS/IFRS paragraph from that row\'s candidate list. '
    'A standard alone is not a paragraph citation. If the evidence does not '
    'establish an applicable paragraph, set "Standards Citation" to null and explain why.'
)

_OUTPUT_SPEC = (
    'Respond with ONLY a JSON object in EXACTLY this schema:\n'
    '{\n'
    '  "General Judgment": "Correct" | "Incorrect",\n'
    '  "Information for error 1": {\n'
    '    "Error Identification": {"Error Type": "<one of the four types>", '
    '"Problematic Entry": "Row <n>"},\n'
    '    "Error Resolution": "<one or two sentences>",\n'
    '    "Standards Citation": "ASC <full paragraph from that row\'s list, '
    'e.g. ASC 230-10-45-13 — never a topic-only code like ASC 230>"\n'
    '  },\n'
    '  "Corrected Statements": "<the full corrected table, or the original if Correct>"\n'
    '}\n'
    'If "General Judgment" is "Correct", omit the "Information for error" blocks. '
    'For multiple errors add "Information for error 2", etc. '
    'Cite one applicable full paragraph copied from that row\'s candidate list '
    '(ASC xxx-xx-xx-x). Reference membership alone does not establish applicability. '
    'If nothing fits or only a topic is available, set "Standards Citation" to null '
    'and explain why. Do not invent or guess a paragraph.'
)


def _evidence_block(record, statement) -> str:
    lines = ["DETERMINISTIC ARITHMETIC EVIDENCE (from the Stage 0 engine):"]
    if record.verified_consistent:
        lines.append(
            "  The engine found no anomaly in its checkable subtotals and "
            "identities. Checks may have incomplete coverage. This does not "
            "prove the absence of numerical, missing-row, recognition or "
            "measurement defects.")
    elif record.footing:
        lines.append("  ⚠ Subtotal footing mismatches the engine found "
                     "(these are real arithmetic anomalies — investigate them):")
        for f in record.footing[:6]:
            lines.append(f"      row {f.get('idx')} '{f.get('label')}': "
                         f"stated {f.get('stated')}, expected {f.get('correct')}")
    else:
        lines.append(
            "  The engine could not fully verify this statement (limited "
            "transaction coverage). Audit it carefully but do not assume an error.")
    if record.equations:
        lines.append("  Accounting-identity violations:")
        for e in record.equations[:4]:
            lines.append(f"      {e.get('identity')}: lhs {e.get('lhs')} vs rhs {e.get('rhs')}")
    return "\n".join(lines)


def _framework_of(statement, item: Optional[dict] = None) -> str:
    if item and item.get("framework"):
        return resolve_framework(None, item.get("framework"))
    fw = getattr(statement, "framework", None)
    if fw:
        return resolve_framework(None, fw)
    for row in getattr(statement, "rows", []) or []:
        if (getattr(row, "concept", None) or "").startswith("ifrs-full:"):
            return "ifrs"
    return "us-gaap"


def _row_codes(row) -> list:
    codes = list(getattr(row, "asc_candidates", None) or [])
    if getattr(row, "asc_primary", None):
        codes = [row.asc_primary] + codes
    # already unique-ish; keep order, cap display
    seen, out = set(), []
    for c in codes:
        key = str(c).replace("ASC ", "").strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
        if len(out) >= 8:
            break
    return out


def _citation_block(statement, framework: str = "us-gaap") -> str:
    rows = [r for r in statement.rows if r.value is not None and _row_codes(r)]
    if not rows:
        return "CITATION CANDIDATES: none available."
    if framework == "ifrs":
        lines = ["IAS/IFRS reference candidates (reference membership alone does not prove applicability):"]
        for r in rows[:40]:
            lines.append(f"  Row {r.row_idx} ({r.label[:38]}): {', '.join(_row_codes(r))}")
        return "\n".join(lines)
    lines = ["ASC reference candidates (reference membership alone does not prove applicability):"]

    for r in rows[:40]:
        codes = ", ".join("ASC " + c for c in _row_codes(r))
        lines.append(f"  Row {r.row_idx} ({r.label[:38]}): {codes}")
    return "\n".join(lines)


def apply_citation_snap(parsed: dict | None, statement, error_type=None) -> dict | None:
    """Validate each raw pick against its row; never substitute another code.

    The historical function name remains for callers. Invalid or incomplete
    picks abstain, with the raw citation and validation reason preserved.
    Candidate membership certifies retrieval provenance only.
    """
    if not parsed or not isinstance(parsed, dict):
        return parsed
    import re
    result = dict(parsed)
    keys = [key for key in parsed if re.fullmatch(r"Information for error \d+", key)]
    if not keys and "Error Identification" in parsed:
        keys = [None]
    framework = _framework_of(statement)
    for key in keys:
        original = parsed if key is None else parsed[key]
        if not isinstance(original, dict):
            continue
        info = dict(original)
        eid = info.get("Error Identification") or {}
        raw = info.get("Standards Citation")
        row_match = re.search(r"\d+", str(eid.get("Problematic Entry") or ""))
        row_n = int(row_match.group()) if row_match else None
        hit = next((row for row in getattr(statement, "rows", [])
                    if row.row_idx == row_n), None)
        candidates = _row_codes(hit) if hit is not None else []
        allowed = {code for cand in candidates for code in citation_codes(cand, "full")}
        picked = citation_codes(raw, "identifier")
        expected = (lambda code: not code.startswith("ASC ")) if framework == "ifrs" else (lambda code: code.startswith("ASC "))
        accepted = len(picked) == 1 and picked[0] in allowed and expected(picked[0])
        reason = ("candidate_member" if accepted else "model_abstained" if not raw
                  else "row_not_available" if hit is None
                  else "no_paragraph_candidates" if not allowed
                  else "citation_not_in_row_candidates")
        info.setdefault("Raw Standards Citation", raw)
        info["Standards Citation"] = picked[0] if accepted else None
        info["Citation Validation"] = {"accepted": accepted, "reason": reason}
        if key is None:
            result.update(info)
        else:
            result[key] = info
    return result


def build_user(item: dict, record, statement) -> str:
    framework = _framework_of(statement, item)
    spec = _OUTPUT_SPEC_IFRS if framework == "ifrs" else _OUTPUT_SPEC
    return (
        f"FINANCIAL STATEMENT (rows may contain one injected error):\n{item['table']}\n\n"
        f"SUPPORTING TRANSACTIONS (the ground-truth source of each value):\n"
        f"{item.get('transaction_data','')}\n\n"
        f"{_evidence_block(record, statement)}\n\n"
        f"{_citation_block(statement, framework)}\n\n"
        f"{spec}"
    )


def audit_item(item: dict, record, statement, model: str = "claude-opus-4-6",
               provider: str = "anthropic") -> dict:
    """Call the focused LLM. Returns {raw_text, parsed, error}."""
    import openai
    client = _make_client(provider)
    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system_for(record, _framework_of(statement, item))},
                  {"role": "user", "content": build_user(item, record, statement)}],
        temperature=TEMPERATURE,
    )
    if PROVIDERS[provider]["max_tokens"]:
        kwargs["max_tokens"] = PROVIDERS[provider]["max_tokens"]
    try:
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content or ""
        parsed = apply_citation_snap(_extract_json(raw), statement,
                                    getattr(record, "error_type", None))
        return {"raw_text": raw, "parsed": parsed, "error": None}
    except Exception as e:
        return {"raw_text": "", "parsed": None, "error": str(e)}
