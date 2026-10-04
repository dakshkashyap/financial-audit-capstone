"""
Stage 2 — governing-axis selection.

What AuditBench, FinAuditing, and AuditFlow do not decide
---------------------------------------------------------
AuditBench asks one model to detect, localize, explain, and *recall* an ASC
citation. Citation top-1 is 26%, and that single miss collapses success rate.
FinAuditing attaches the taxonomy's reference list to a concept; a concept has
many references, and the list does not say which one governs *this* defect.
AuditFlow lets a symbolic environment check numbers and rules, but it does not
score which paragraph governs the defect.

The missing decision is the axis:

  presentation  the amount may be fine, but the line is in the wrong place
                on the face of the statement (ASC 210 / 220 / 230; debt
                current vs non-current is ASC 470).
  subject       the amount is measured or recognized under the wrong model
                (inventory 330, goodwill 350, securities 320, revenue 606,
                lease classification 842).
  none          a wrong number, an extra row, a deleted row, a negative
                balance, or a total that does not foot, and neither axis
                above is what went wrong. No paragraph governs it.
                ASC 210-10-45-1 is not a default answer.

Once the defect type and the account are known, this is a function, not a
recall problem. Stage 2's job is to apply that function, or — when the
symbolic gate did not name the type — to name the axis and abstain when
no paragraph governs. The model is not allowed to invent a citation, and
it is not told the rule id.

The principle below was written from that accounting distinction. It does
not read rule ids. Topic-level match is the headline, because the benchmark's
paragraph labels are still marked expert-authored and unvalidated.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

# Repo root on path when executed as a file.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from approaches.stage1_taxonomy_citation.concept_citation import (  # noqa: E402
    IFRS_LEASE, IFRS_MEASUREMENT, governing_id, presentation_citation, subject_topic, topic_of,
)
from core.frameworks import bare_concept, ifrs_standard_of, resolve_framework  # noqa: E402

DATA_DIR = os.path.join(_ROOT, "data", "intelliaudit")
OUT_DIR = os.path.join(_ROOT, "results", "stage2_axis")

STMT_TO_PIPE = {
    "BalanceSheet": "balance_sheet",
    "IncomeStatement": "income_statement",
    "CashFlow": "cash_flow",
}
SHEET_LABEL = {
    "BalanceSheet": "balance sheet",
    "IncomeStatement": "income statement",
    "CashFlow": "cash flow statement",
}

# Numerical change on one of these accounts is a measurement/recognition
# question. A numerical change on any other account has no governing paragraph.
MEASUREMENT_TOPICS = {"330", "350", "320", "606"}
# Misclassification whose governing standard is the subject standard, not
# the statement-presentation topic.
LEASE_TOPIC = "842"
DEBT_TOPIC = "470"

_ASC_RE = re.compile(
    r"ASC\s*(\d{3})(?:-(\d{2,3}))?(?:-(\d+[A-Z]?))?(?:-(\d+[A-Z]?))?",
    re.I,
)


def _framework(rec: Optional[dict] = None, concept: Optional[str] = None) -> str:
    if rec and rec.get("framework"):
        return resolve_framework(concept or rec.get("concept"), rec.get("framework"))
    return resolve_framework(concept or (rec or {}).get("concept"))


def axis_decision(error_type: Optional[str], concept: Optional[str],
                  statement_type: Optional[str],
                  framework: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Return (axis, standard). Standard is '330' or 'IAS 2', or None when the axis is none.

    Locked rule, applied the same way to every record. Does not read rule_id.
    An ``ifrs-full:`` concept uses the IFRS rule. Pass ``framework`` to force one.
    """
    fw = resolve_framework(concept, framework)
    subj = subject_topic(concept, framework=fw)
    pres = governing_id(presentation_citation(statement_type, framework=fw), fw)
    if fw == "ifrs":
        return _ifrs_axis(error_type, concept, subj, pres)
    if error_type == "Misclassification":
        if subj == LEASE_TOPIC:
            return "subject", LEASE_TOPIC
        if subj == DEBT_TOPIC:
            return "presentation", DEBT_TOPIC
        return "presentation", pres
    if error_type == "Numerical Error" and subj in MEASUREMENT_TOPICS:
        return "subject", subj
    return "none", None


def _ifrs_axis(error_type: Optional[str], concept: Optional[str],
               subj: Optional[str], pres: Optional[str]) -> Tuple[str, Optional[str]]:
    """IFRS counterpart of the US-GAAP axis.

    Dividends paid may sit in operating or financing cash flows (IAS 7.34),
    so moving that line is not a violation. A missing lessee right-of-use
    asset or lease liability is IFRS 16, not an ungoverned missing row.
    """
    bare = bare_concept(concept)
    if error_type == "Misclassification" and bare and re.search(r"DividendsPaid", bare):
        return "none", None
    if error_type == "Misclassification":
        if subj == IFRS_LEASE:
            return "subject", IFRS_LEASE
        return "presentation", pres
    if error_type == "Missing Row" and subj == IFRS_LEASE:
        return "subject", IFRS_LEASE
    if error_type == "Numerical Error" and subj in IFRS_MEASUREMENT:
        return "subject", subj
    return "none", None


def _self_check() -> None:
    assert axis_decision("Misclassification", "us-gaap:InventoryNet", "balance_sheet") == ("presentation", "210")
    assert axis_decision("Numerical Error", "us-gaap:InventoryNet", "balance_sheet") == ("subject", "330")
    assert axis_decision("Numerical Error", "us-gaap:Goodwill", "balance_sheet") == ("subject", "350")
    assert axis_decision("Numerical Error", "us-gaap:CashAndCashEquivalentsAtCarryingValue", "balance_sheet") == ("none", None)
    assert axis_decision("Missing Row", "us-gaap:InventoryNet", "balance_sheet") == ("none", None)
    assert axis_decision("Redundant Row", "us-gaap:InventoryNet", "balance_sheet") == ("none", None)
    assert axis_decision("Misclassification", "us-gaap:OperatingLeaseRightOfUseAsset", "balance_sheet") == ("subject", "842")
    assert axis_decision("Misclassification", "us-gaap:LongTermDebtNoncurrent", "balance_sheet") == ("presentation", "470")
    assert axis_decision(
        "Misclassification", "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "cash_flow"
    ) == ("presentation", "230")
    assert axis_decision("Numerical Error", "us-gaap:DeferredTaxAssetsNet", "balance_sheet") == ("none", None)
    assert axis_decision("Misclassification", "ifrs-full:Inventories", "balance_sheet") == ("presentation", "IAS 1")
    assert axis_decision("Numerical Error", "ifrs-full:Inventories", "balance_sheet") == ("subject", "IAS 2")
    assert axis_decision("Numerical Error", "ifrs-full:Goodwill", "balance_sheet") == ("subject", "IAS 36")
    assert axis_decision("Numerical Error", "ifrs-full:Revenue", "income_statement") == ("subject", "IFRS 15")
    assert axis_decision("Numerical Error", "ifrs-full:TradeAndOtherCurrentReceivables", "balance_sheet") == ("subject", "IFRS 9")
    assert axis_decision("Numerical Error", "ifrs-full:DeferredTaxAssets", "balance_sheet") == ("subject", "IAS 12")
    assert axis_decision("Numerical Error", "ifrs-full:PropertyPlantAndEquipment", "balance_sheet") == ("subject", "IAS 36")
    assert axis_decision("Numerical Error", "ifrs-full:CashAndCashEquivalents", "balance_sheet") == ("none", None)
    assert axis_decision("Misclassification", "ifrs-full:RightofuseAssets", "balance_sheet") == ("subject", "IFRS 16")
    assert axis_decision("Missing Row", "ifrs-full:LeaseLiabilities", "balance_sheet") == ("subject", "IFRS 16")
    assert axis_decision("Missing Row", "ifrs-full:Inventories", "balance_sheet") == ("none", None)
    assert axis_decision("Misclassification", "ifrs-full:LongtermBorrowings", "balance_sheet") == ("presentation", "IAS 1")
    assert axis_decision(
        "Misclassification",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "cash_flow",
    ) == ("presentation", "IAS 7")
    assert axis_decision(
        "Misclassification",
        "ifrs-full:DividendsPaidClassifiedAsFinancingActivities",
        "cash_flow",
    ) == ("none", None)


def load_joined(data_dir: Optional[str] = None,
                framework: str = "us-gaap") -> List[dict]:
    framework = resolve_framework(None, framework)
    if data_dir is None:
        data_dir = (os.path.join(_ROOT, "data", "ifrs", "benchmark")
                    if framework == "ifrs" else DATA_DIR)
    exam_path = os.path.join(data_dir, "exam.jsonl")
    key_path = os.path.join(data_dir, "answer_key.jsonl")
    if not os.path.isfile(exam_path) or not os.path.isfile(key_path):
        raise FileNotFoundError(
            f"No exam at {data_dir}. US-GAAP exams live in data/intelliaudit. "
            "An IFRS exam is built by the IntelliAudit generator "
            "(see data/ifrs/IFRS_BUILD.md) and placed in data/ifrs/benchmark."
        )
    exam = {}
    with open(exam_path, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            exam[e["sample_id"]] = e
    rows = []
    with open(key_path, encoding="utf-8") as f:
        for line in f:
            k = json.loads(line)
            e = exam[k["sample_id"]]
            gt = k["ground_truth_citations"]
            meta = e["metadata"]
            if framework == "ifrs":
                topic = ifrs_standard_of(gt.get("asc_full") or "") if gt.get("citable") else None
            else:
                topic = topic_of((gt.get("asc_topic") or "").replace("ASC", "").strip()) if gt.get("citable") else None
                if gt.get("citable") and gt.get("asc_full"):
                    topic = topic_of(str(gt["asc_full"]).replace("ASC", " "))
            rows.append({
                "sample_id": k["sample_id"],
                "company": meta["company"],
                "cik": meta["cik"],
                "fiscal_year": meta["fiscal_year"],
                "statement": meta["statement_type"],
                "pipe_stmt": STMT_TO_PIPE[meta["statement_type"]],
                "statement_text": e["statement_text"],
                "transaction_data": e.get("transaction_data") or "",
                "judgment": k["general_judgement"],
                "rule_id": k["rule_id"],
                "rule": k["rule_id"].split("_")[0],
                "error_type": k["error_type"],
                "concept": (k["error_identification"] or {}).get("affected_xbrl_concept"),
                "label": (k["error_identification"] or {}).get("affected_label"),
                "rows_ok": {
                    (k["error_identification"] or {}).get("problematic_entry"),
                    (k["error_identification"] or {}).get("pre_inject_row"),
                    (k["error_identification"] or {}).get("post_inject_row"),
                } - {None},
                "citable": bool(gt.get("citable")),
                "asc_full": gt.get("asc_full"),
                "topic": topic,
                "tier": gt.get("citation_tier"),
                "framework": framework,
                "data_dir": data_dir,
            })
    return rows


def load_clean(joined: List[dict], data_dir: Optional[str] = None) -> List[dict]:
    """Clean statements. Transactions are taken from one sibling exam of the same filing."""
    if data_dir is None:
        data_dir = joined[0].get("data_dir") if joined else DATA_DIR
    sib = {}
    for r in joined:
        sid = f"{r['cik']}_{r['fiscal_year']}_{r['statement']}"
        sib.setdefault(sid, r["transaction_data"])
    out = []
    with open(os.path.join(data_dir, "statements_clean.jsonl"), encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            m = c["metadata"]
            sid = c["statement_id"]
            out.append({
                "sample_id": "CLEAN-" + sid,
                "company": m["company"],
                "fiscal_year": m["fiscal_year"],
                "statement": m["statement_type"],
                "pipe_stmt": STMT_TO_PIPE[m["statement_type"]],
                "statement_text": c["statement_text"],
                "transaction_data": sib.get(sid, ""),
                "judgment": "Correct",
                "rule": "CLEAN",
                "error_type": None,
                "concept": None,
                "citable": False,
                "topic": None,
                "rows_ok": set(),
                "is_clean": True,
                "framework": (joined[0].get("framework") if joined else "us-gaap"),
            })
    return out


def gold_axis(rec: dict) -> Tuple[str, Optional[str]]:
    if not rec.get("citable"):
        return "none", None
    topic = rec.get("topic")
    if topic == LEASE_TOPIC:
        return "subject", topic
    if topic == DEBT_TOPIC:
        return "presentation", topic
    if topic in {"210", "220", "230", "225"}:
        return "presentation", topic
    return "subject", topic


def topic_hit(pred_topic: Optional[str], rec: dict) -> Optional[int]:
    """1/0 on citable rows only. None when the row is not a citation question."""
    if not rec.get("citable"):
        return None
    return int(pred_topic is not None and pred_topic == rec.get("topic"))


def abstain_hit(pred_topic: Optional[str], rec: dict) -> Optional[int]:
    """1 if we correctly cited nothing on a non-citable / clean row."""
    if rec.get("citable"):
        return None
    return int(pred_topic is None)


def _rate(flags: List[Optional[int]]) -> Optional[float]:
    xs = [f for f in flags if f is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return max(0.0, centre - margin), min(1.0, centre + margin)


def majority_by(rows: List[dict], keyfn) -> Dict[tuple, Optional[str]]:
    buckets: Dict[tuple, Counter] = defaultdict(Counter)
    for r in rows:
        if not r["citable"] or not r["topic"]:
            continue
        buckets[keyfn(r)][r["topic"]] += 1
    return {k: c.most_common(1)[0][0] for k, c in buckets.items() if c}


def score_predictor(rows: List[dict], predict) -> dict:
    """predict(rec) -> topic or None."""
    t_flags, a_flags, axis_flags = [], [], []
    by_rule_t: Dict[str, List[int]] = defaultdict(list)
    by_rule_a: Dict[str, List[int]] = defaultdict(list)
    for r in rows:
        pred = predict(r)
        g_axis, _ = gold_axis(r)
        # Axis of a topic prediction: none if no topic, else gold's axis name
        # only matches when the topic matches. A wrong topic is a wrong axis
        # unless both are presentation or both are subject AND... we compare
        # the predicted axis implied by the principle-style bucket.
        th = topic_hit(pred, r)
        ah = abstain_hit(pred, r)
        t_flags.append(th)
        a_flags.append(ah)
        if th is not None:
            by_rule_t[r["rule"]].append(th)
        if ah is not None:
            by_rule_a[r["rule"]].append(ah)
        if r.get("is_clean"):
            axis_flags.append(int(pred is None))
        else:
            # predicted axis from whether we emitted the gold topic's family
            if not r["citable"]:
                axis_flags.append(int(pred is None))
            else:
                axis_flags.append(int(pred == r["topic"]))
    n_cit = sum(1 for f in t_flags if f is not None)
    k_cit = sum(f for f in t_flags if f is not None)
    n_abs = sum(1 for f in a_flags if f is not None)
    k_abs = sum(f for f in a_flags if f is not None)
    lo, hi = wilson(k_cit, n_cit)
    return {
        "n": len(rows),
        "citable_n": n_cit,
        "topic_accuracy": _rate(t_flags),
        "topic_wilson95": [lo, hi],
        "ungoverned_n": n_abs,
        "abstain_accuracy": _rate(a_flags),
        "false_citation_rate": (None if _rate(a_flags) is None else 1 - _rate(a_flags)),
        "by_rule_topic": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_rule_t.items())},
        "by_rule_abstain": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_rule_a.items())},
    }


def subject_first_topic(rec: dict) -> Optional[str]:
    """Current Stage-1 selector: subject topic if the account has one, else presentation."""
    fw = _framework(rec)
    subj = subject_topic(rec.get("concept"), framework=fw)
    if subj:
        return subj
    return governing_id(presentation_citation(rec.get("pipe_stmt"), framework=fw), fw)


def principle_topic(rec: dict) -> Optional[str]:
    _axis, topic = axis_decision(
        rec.get("error_type"), rec.get("concept"), rec.get("pipe_stmt"),
        framework=rec.get("framework"),
    )
    return topic


def analyze_full(rows: List[dict]) -> dict:
    citable = [r for r in rows if r["citable"]]
    by_stmt = majority_by(citable, lambda r: (r["statement"],))
    by_cell = majority_by(citable, lambda r: (r["error_type"], r["statement"]))

    def stmt_prior(r):
        if not r["citable"]:
            return None
        return by_stmt.get((r["statement"],))

    def cell_prior(r):
        if not r["citable"]:
            return None
        return by_cell.get((r["error_type"], r["statement"]))

    # Cell sizes, so the guessability number is interpretable.
    cell_n = Counter((r["error_type"], r["statement"]) for r in citable)
    cell_mode = {}
    for key, n in cell_n.items():
        mode = by_cell[key]
        hit = sum(1 for r in citable if (r["error_type"], r["statement"]) == key and r["topic"] == mode)
        cell_mode[f"{key[0]} | {key[1]}"] = {
            "n": n, "majority_topic": mode, "majority_share": round(hit / n, 3),
        }

    principle = score_predictor(rows, principle_topic)
    subject = score_predictor(rows, subject_first_topic)
    # Majority priors are only defined as citation guesses. On ungoverned rows
    # they have nothing to say; do not treat "no prediction" as a virtuous abstention.
    cell = score_predictor(citable, cell_prior)
    stmt = score_predictor(citable, stmt_prior)

    # Coverage: is the gold topic in {subject(account), presentation(statement)}?
    cover = 0
    for r in citable:
        fw = _framework(r)
        cands = {
            subject_topic(r["concept"], framework=fw),
            governing_id(presentation_citation(r["pipe_stmt"], framework=fw), fw),
        } - {None}
        extras = {IFRS_LEASE} if fw == "ifrs" else {LEASE_TOPIC, DEBT_TOPIC}
        if r["topic"] in cands or r["topic"] in extras:
            cover += 1
    return {
        "n_records": len(rows),
        "n_citable": len(citable),
        "n_ungoverned": len(rows) - len(citable),
        "candidate_coverage": round(cover / len(citable), 4) if citable else None,
        "cells": cell_mode,
        "statement_majority": stmt,
        "error_x_statement_majority": cell,
        "subject_first_selector": subject,
        "axis_principle": principle,
    }


def stratified_sample(rows: List[dict], clean: List[dict], per_rule: int,
                      n_clean: int, seed: int) -> List[dict]:
    rng = random.Random(seed)
    by_rule = defaultdict(list)
    for r in rows:
        by_rule[r["rule"]].append(r)
    chosen = []
    for rule in sorted(by_rule):
        by_co = defaultdict(list)
        for r in by_rule[rule]:
            by_co[r["company"]].append(r)
        companies = list(by_co)
        rng.shuffle(companies)
        picks = []
        guard = 0
        while len(picks) < min(per_rule, len(by_rule[rule])) and guard < 100:
            co = companies[guard % len(companies)]
            pool = [x for x in by_co[co] if x not in picks]
            if pool:
                picks.append(rng.choice(pool))
            guard += 1
        chosen.extend(picks)
    # Clean: distinct companies, rotating statement types.
    by_stmt = defaultdict(list)
    for c in clean:
        by_stmt[c["statement"]].append(c)
    clean_picks = []
    stmts = list(by_stmt)
    rng.shuffle(stmts)
    used_co = set()
    i = 0
    while len(clean_picks) < n_clean and i < n_clean * 8:
        stmt = stmts[i % len(stmts)]
        pool = [c for c in by_stmt[stmt] if c["company"] not in used_co]
        if not pool:
            pool = list(by_stmt[stmt])
        if pool:
            pick = rng.choice(pool)
            clean_picks.append(pick)
            used_co.add(pick["company"])
        i += 1
    for c in clean_picks:
        c["is_clean"] = True
    for r in chosen:
        r["is_clean"] = False
    return chosen + clean_picks


def stage0_on(rec: dict) -> dict:
    """Run the symbolic gate. Returns type/row if it fires, else abstain."""
    from approaches.stage0_deterministic_gate import stage0a, stage0b
    from core.stage0_common import combine_findings
    item = {"table": rec["statement_text"], "transaction_data": rec.get("transaction_data") or ""}
    try:
        a = stage0a.verify(item)
        b = stage0b.check(item)
        finding = combine_findings(a, b)
    except Exception as exc:
        return {"fired": False, "error": str(exc)[:200], "footing": [], "equations": []}
    footing = []
    for f in (getattr(a, "footing", None) or [])[:4]:
        footing.append(f"row {f.get('idx')} '{f.get('label')}': stated {f.get('stated')}, "
                       f"transactions support {f.get('correct')}")
    equations = []
    for e in (getattr(b, "equations", None) or [])[:3]:
        equations.append(f"{e.get('identity')}: {e.get('lhs')} vs {e.get('rhs')}")
    if finding is None:
        return {"fired": False, "error_type": None, "row": None,
                "footing": footing, "equations": equations}
    return {
        "fired": True,
        "error_type": finding.error_type,
        "row": finding.problematic_entry,
        "detail": finding.detail,
        "footing": footing,
        "equations": equations,
    }


def mapped_concept_at(rec: dict, row_idx: Optional[int]) -> Optional[str]:
    from approaches.stage1_concept_mapping.edgar_mapper import map_statement
    fw = _framework(rec)
    item = {
        "table": rec["statement_text"],
        "sheet_type": SHEET_LABEL.get(rec["statement"], ""),
        "company": "",  # withheld: mega-cap names are memorizable
        "framework": fw,
    }
    ms = map_statement(item, framework=fw)
    if row_idx is None:
        return None
    for row in ms.rows:
        if row.row_idx == row_idx and row.concept:
            return row.concept
    return None


def candidate_block(rec: dict) -> str:
    from approaches.stage1_concept_mapping.edgar_mapper import map_statement
    fw = _framework(rec)
    item = {
        "table": rec["statement_text"],
        "sheet_type": SHEET_LABEL.get(rec["statement"], ""),
        "company": "",
        "framework": fw,
    }
    ms = map_statement(item, framework=fw)
    pres = presentation_citation(rec["pipe_stmt"], framework=fw) or "none"
    if fw == "ifrs":
        lines = [f"Statement form: {rec['statement']}. Presentation standard for this form: {pres}."]
        lines.append("Closed candidate list. Cite only from the row you flag, or cite nothing.")
        n = 0
        for row in ms.rows:
            if row.value is None:
                continue
            subj = subject_topic(row.concept, framework="ifrs") if row.concept else None
            bits = [f"Row {row.row_idx} | {row.label[:48]}"]
            if row.concept:
                bits.append(f"account {bare_concept(row.concept)}")
            bits.append(f"presentation {pres}")
            if subj:
                bits.append(f"subject {subj}")
            lines.append("  " + " | ".join(bits))
            n += 1
            if n >= 28:
                lines.append("  … remaining rows omitted")
                break
        if n == 0:
            lines.append("  (no valued row mapped)")
        return "\n".join(lines)
    lines = [f"Statement form: {rec['statement']}. Presentation standard for this form: ASC {pres}."]
    lines.append("Closed candidate list. Cite only from the row you flag, or cite nothing.")
    n = 0
    for row in ms.rows:
        if row.value is None:
            continue
        subj = subject_topic(row.concept) if row.concept else None
        bits = [f"Row {row.row_idx} | {row.label[:48]}"]
        if row.concept:
            bits.append(f"account {row.concept.replace('us-gaap:', '')}")
        bits.append(f"presentation ASC {pres}")
        if subj:
            bits.append(f"subject ASC {subj}")
        lines.append("  " + " | ".join(bits))
        n += 1
        if n >= 28:
            lines.append("  … remaining rows omitted")
            break
    if n == 0:
        lines.append("  (no valued row mapped)")
    return "\n".join(lines)


SYSTEM_STAGE2 = """You are Stage 2 of an audit pipeline. A symbolic checker may already have flagged arithmetic. A concept map has listed the standards that could apply to each line. You are not told which error was injected. You do not invent a standard that is not in the candidate list.

Every defect is governed along exactly one axis:

- presentation: the amount may be fine, but the line sits in the wrong section of the statement (current vs non-current, or the wrong section of the cash-flow statement). Cite the presentation standard for that statement. Exception: if the misplaced line is debt, the classification standard is ASC 470, not the generic balance-sheet topic.
- subject: the line is an inventory, goodwill, available-for-sale security, revenue, or lease line, AND what went wrong is how that item is measured or classified as a lease (operating vs finance). Cite that line's subject standard.
- none: the defect is a wrong number on an ordinary line, an extra row, a deleted row, a negative balance, or a total that does not foot, and the two cases above do not apply. Cite nothing. Do not use ASC 210 as a default.

Changing a number is not automatically a measurement error. Cite a subject standard only when the line is one of those accounts. A lease line that was relabeled between operating and finance is a subject defect even though it looks like a classification change.

Respond with only this JSON object:
{
  "general_judgment": "Correct" or "Incorrect",
  "error_type": "Numerical Error" or "Missing Row" or "Redundant Row" or "Misclassification" or null,
  "problematic_entry": "Row <n>" or null,
  "governing_axis": "presentation" or "subject" or "none",
  "standards_citation": "ASC <topic from that row's candidates>" or null,
  "evidence": "one sentence naming the row and the fact that supports the axis"
}"""

SYSTEM_BLIND = """You are an independent auditor. One financial statement is below. It may be correct, or it may contain a single error. Supporting transactions are the evidence for the amounts.

Identify whether the statement is correct. If it is not, name the error type (Numerical Error, Missing Row, Redundant Row, or Misclassification), the row, and the single FASB ASC reference that governs the error. If no paragraph governs the error, set the citation to null. Do not use ASC 210 as a default for a wrong number or a broken total.

Respond with only this JSON object:
{
  "general_judgment": "Correct" or "Incorrect",
  "error_type": "Numerical Error" or "Missing Row" or "Redundant Row" or "Misclassification" or null,
  "problematic_entry": "Row <n>" or null,
  "governing_axis": "presentation" or "subject" or "none",
  "standards_citation": "ASC ..." or null,
  "evidence": "one sentence"
}"""

SYSTEM_STAGE2_IFRS = """You are Stage 2 of an audit pipeline. A symbolic checker may already have flagged arithmetic. A concept map has listed the standards that could apply to each line. You are not told which error was injected. You do not invent a standard that is not in the candidate list. This statement is prepared under IFRS, not US GAAP.

Every defect is governed along exactly one axis:

- presentation: the amount may be fine, but the line sits in the wrong section of the statement. Cite IAS 1 for a balance sheet or income statement, or IAS 7 for a cash-flow statement. Borrowings in the wrong current or non-current section are still IAS 1.
- subject: the line is inventory (IAS 2), goodwill or impaired property, plant and equipment (IAS 36), a financial asset or receivable (IFRS 9), revenue (IFRS 15), deferred tax (IAS 12), research and development (IAS 38), or a lease (IFRS 16), AND what went wrong is how that item is measured or recognised, or a lessee lease that was left off the statement. Cite that line's subject standard.
- none: the defect is a wrong number on an ordinary line, an extra row, a deleted row that is not a lessee right-of-use asset or lease liability, a negative balance, or a total that does not foot, and the two cases above do not apply. Cite nothing. Do not use IAS 1 as a default. Dividends paid may be classified in operating or financing cash flows; that choice is not a violation.

Changing a number is not automatically a measurement error. Cite a subject standard only when the line is one of those accounts.

Respond with only this JSON object:
{
  "general_judgment": "Correct" or "Incorrect",
  "error_type": "Numerical Error" or "Missing Row" or "Redundant Row" or "Misclassification" or null,
  "problematic_entry": "Row <n>" or null,
  "governing_axis": "presentation" or "subject" or "none",
  "standards_citation": "IAS <n> or IFRS <n> from that row's candidates" or null,
  "evidence": "one sentence naming the row and the fact that supports the axis"
}"""

SYSTEM_BLIND_IFRS = """You are an independent auditor. One IFRS financial statement is below. It may be correct, or it may contain a single error. Supporting transactions are the evidence for the amounts. Do not apply US GAAP.

Identify whether the statement is correct. If it is not, name the error type (Numerical Error, Missing Row, Redundant Row, or Misclassification), the row, and the single IAS or IFRS standard that governs the error. If no paragraph governs the error, set the citation to null. Do not use IAS 1 as a default for a wrong number or a broken total. Dividends paid may be shown in operating or financing cash flows.

Respond with only this JSON object:
{
  "general_judgment": "Correct" or "Incorrect",
  "error_type": "Numerical Error" or "Missing Row" or "Redundant Row" or "Misclassification" or null,
  "problematic_entry": "Row <n>" or null,
  "governing_axis": "presentation" or "subject" or "none",
  "standards_citation": "IAS ..." or "IFRS ..." or null,
  "evidence": "one sentence"
}"""


def build_user(rec: dict, gate: Optional[dict], with_candidates: bool) -> str:
    parts = []
    if gate is not None:
        if gate.get("fired"):
            parts.append(
                "SYMBOLIC GATE: it fired.\n"
                f"  proposed type: {gate.get('error_type')}\n"
                f"  proposed row: {gate.get('row')}\n"
                "This is a lead, not a verdict. Override it when the statement disagrees."
            )
        else:
            parts.append("SYMBOLIC GATE: it abstained. It did not prove an error.")
        if gate.get("footing"):
            parts.append("Footing gaps the gate found:\n  " + "\n  ".join(gate["footing"]))
        if gate.get("equations"):
            parts.append("Identity gaps:\n  " + "\n  ".join(gate["equations"]))
    if with_candidates:
        parts.append(candidate_block(rec))
    parts.append("STATEMENT:\n" + rec["statement_text"][:7000])
    tx = rec.get("transaction_data") or ""
    parts.append("TRANSACTIONS:\n" + (tx[:5000] if tx else "(none)"))
    return "\n\n".join(parts)


def extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def pred_topic_from_obj(obj: Optional[dict], framework: str = "us-gaap") -> Optional[str]:
    if not obj:
        return None
    axis = str(obj.get("governing_axis") or "").strip().lower()
    cit = obj.get("standards_citation")
    if cit is None or str(cit).strip().lower() in {"", "null", "none"}:
        return None
    if axis == "none":
        return None
    if framework == "ifrs":
        return ifrs_standard_of(str(cit))
    m = _ASC_RE.search(str(cit))
    if not m:
        # bare topic
        m2 = re.search(r"\b(\d{3})\b", str(cit))
        return m2.group(1) if m2 else None
    return m.group(1)


def score_llm_obj(obj: Optional[dict], rec: dict) -> dict:
    topic = pred_topic_from_obj(obj, rec.get("framework") or "us-gaap")
    judg = ""
    etype = ""
    row_ok = 0
    if obj:
        judg = str(obj.get("general_judgment") or obj.get("General Judgment") or "")
        etype = str(obj.get("error_type") or "")
        m = re.search(r"\d+", str(obj.get("problematic_entry") or ""))
        if m and int(m.group()) in (rec.get("rows_ok") or set()):
            row_ok = 1
    gold_j = rec.get("judgment") or "Incorrect"
    if rec.get("is_clean"):
        det = int(judg.strip().lower() == "correct")
        type_ok = None
        row_score = None
        false_alarm = int(judg.strip().lower() == "incorrect")
    else:
        det = int(judg.strip().lower() == gold_j.strip().lower())
        type_ok = int(etype.strip().lower() == str(rec.get("error_type") or "").strip().lower())
        row_score = row_ok
        false_alarm = None
    return {
        "pred_topic": topic,
        "topic_hit": topic_hit(topic, rec),
        "abstain_hit": abstain_hit(topic, rec),
        "judgment_hit": det,
        "type_hit": type_ok,
        "row_hit": row_score,
        "false_alarm": false_alarm,
        "axis": (obj or {}).get("governing_axis") if obj else None,
    }


def load_openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(_ROOT, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            raw = line.strip()
            if raw.startswith("#"):
                raw = raw.lstrip("#").strip()
            if raw.startswith("OPENROUTER_API_KEY="):
                key = raw.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    os.environ["OPENROUTER_API_KEY"] = key
                    return key
    raise EnvironmentError("OPENROUTER_API_KEY is not set")


def list_models(key: str) -> List[dict]:
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("data", [])


def choose_models(catalog: List[dict]) -> List[dict]:
    """One frontier closed model, one small open-weight model."""
    ids = {m["id"]: m for m in catalog}

    def pick(cands: List[str]) -> Optional[dict]:
        for c in cands:
            if c in ids:
                return ids[c]
        return None

    frontier = pick([
        "anthropic/claude-sonnet-5",
        "anthropic/claude-sonnet-4.6",
        "anthropic/claude-sonnet-4.5",
        "anthropic/claude-4.5-sonnet",
        "anthropic/claude-sonnet-4",
    ])
    if frontier is None:
        sonnets = [m for m in catalog if "sonnet" in m["id"].lower() and "anthropic" in m["id"].lower()]
        frontier = sonnets[-1] if sonnets else None
    open_w = pick([
        "qwen/qwen3-8b",
        "qwen/qwen3-8b:free",
        "qwen/qwen-2.5-7b-instruct",
    ])
    if open_w is None:
        qw = [m for m in catalog if "qwen3-8b" in m["id"].lower()]
        open_w = qw[0] if qw else None
    chosen = [m for m in (frontier, open_w) if m is not None]
    if not chosen:
        raise RuntimeError("Could not find a Sonnet or Qwen3-8B model on OpenRouter")
    return chosen


def price_of(model: dict) -> Tuple[float, float]:
    """USD per token (prompt, completion). OpenRouter quotes per-token strings."""
    p = model.get("pricing") or {}
    try:
        return float(p.get("prompt") or 0), float(p.get("completion") or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0


def call_model(client, model_id: str, system: str, user: str) -> dict:
    last = "max_retries"
    for attempt in range(6):
        try:
            resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0,
                max_tokens=500,
                extra_body={"usage": {"include": True}},
            )
            msg = resp.choices[0].message
            raw = msg.content or ""
            if not raw:
                dumped = msg.model_dump() if hasattr(msg, "model_dump") else {}
                raw = dumped.get("reasoning") or dumped.get("content") or ""
            usage = {}
            if resp.usage is not None:
                usage = resp.usage.model_dump() if hasattr(resp.usage, "model_dump") else dict(resp.usage)
            return {"raw": raw, "parsed": extract_json(raw), "usage": usage, "error": None}
        except Exception as exc:
            last = str(exc)[:400]
            # Free-tier keys reject a call while a prior reservation is still held.
            wait = 20 if "402" in last else 3 * (attempt + 1)
            time.sleep(wait)
    return {"raw": "", "parsed": None, "usage": {}, "error": last}


def _usage_tokens(usage: dict) -> Tuple[int, int, Optional[float]]:
    pin = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    pout = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    cost = usage.get("cost")
    if cost is None and isinstance(usage.get("cost_details"), dict):
        cost = usage["cost_details"].get("upstream_inference_cost")
    try:
        cost_f = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_f = None
    return pin, pout, cost_f


def summarize_llm(records: List[dict], pop_counts: Dict[str, int]) -> dict:
    def mean(key):
        xs = [r[key] for r in records if r.get(key) is not None]
        return (sum(xs) / len(xs) if xs else None), len(xs), int(sum(xs)) if xs else 0

    out = {}
    for key in ("topic_hit", "abstain_hit", "judgment_hit", "type_hit", "row_hit"):
        avg, n, k = mean(key)
        lo, hi = wilson(k, n)
        out[key] = {"rate": avg, "n": n, "k": k, "wilson95": [lo, hi]}
    alarms = [r["false_alarm"] for r in records if r.get("false_alarm") is not None]
    out["false_alarm"] = {
        "rate": (sum(alarms) / len(alarms) if alarms else None),
        "n": len(alarms),
        "k": int(sum(alarms)) if alarms else 0,
    }
    # Post-stratified topic accuracy on citable rules present in the sample.
    by_rule = defaultdict(list)
    for r in records:
        if r.get("topic_hit") is not None:
            by_rule[r["rule"]].append(r["topic_hit"])
    num = den = 0.0
    var = 0.0
    for rule, flags in by_rule.items():
        N = pop_counts.get(rule, 0)
        if N <= 0 or not flags:
            continue
        p = sum(flags) / len(flags)
        w = N
        num += w * p
        den += w
        var += (w ** 2) * p * (1 - p) / len(flags)
    if den:
        est = num / den
        # N is the citable population of sampled rules; scale weights were N not N/total.
        # var above used w=N, so divide by den^2.
        se = (var / (den ** 2)) ** 0.5
        out["topic_poststrat"] = {
            "rate": est,
            "se": se,
            "approx95": [max(0.0, est - 1.96 * se), min(1.0, est + 1.96 * se)],
            "rules": {k: {"n": len(v), "rate": sum(v) / len(v)} for k, v in sorted(by_rule.items())},
        }
    pin = sum(r.get("prompt_tokens") or 0 for r in records)
    pout = sum(r.get("completion_tokens") or 0 for r in records)
    costs = [r["cost_usd"] for r in records if r.get("cost_usd") is not None]
    out["tokens"] = {
        "prompt": pin,
        "completion": pout,
        "per_case_prompt": round(pin / len(records), 1) if records else None,
        "per_case_completion": round(pout / len(records), 1) if records else None,
        "cost_usd": round(sum(costs), 4) if costs else None,
        "cost_per_case": round(sum(costs) / len(costs), 5) if costs else None,
    }
    return out


def render_html(report: dict) -> str:
    d = report["full"]
    p = d["axis_principle"]
    s = d["subject_first_selector"]
    cell = d["error_x_statement_majority"]
    stmt = d["statement_majority"]

    def pct(x):
        return "—" if x is None else f"{100 * x:.1f}%"

    def row(label, block, topic_key="topic_accuracy", abs_key="abstain_accuracy"):
        return (
            f"<tr><td>{label}</td><td>{pct(block.get(topic_key))}</td>"
            f"<td>{pct(block.get(abs_key))}</td>"
            f"<td>{pct(block.get('false_citation_rate'))}</td></tr>"
        )

    cell_rows = ""
    for name, info in sorted(d["cells"].items(), key=lambda kv: -kv[1]["n"]):
        cell_rows += (
            f"<tr><td>{name}</td><td>{info['n']}</td><td>ASC {info['majority_topic']}</td>"
            f"<td>{pct(info['majority_share'])}</td></tr>"
        )
    model_rows = ""
    for mid, block in report.get("models", {}).items():
        sm = block["summary"]
        model_rows += (
            f"<tr><td>{mid}<div class='sub'>{block['condition']}</div></td>"
            f"<td>{pct((sm.get('judgment_hit') or {}).get('rate'))}</td>"
            f"<td>{pct((sm.get('type_hit') or {}).get('rate'))}</td>"
            f"<td>{pct((sm.get('topic_hit') or {}).get('rate'))}</td>"
            f"<td>{pct((sm.get('topic_poststrat') or {}).get('rate'))}</td>"
            f"<td>{pct((sm.get('abstain_hit') or {}).get('rate'))}</td>"
            f"<td>{pct((sm.get('false_alarm') or {}).get('rate'))}</td>"
            f"<td>{(sm.get('tokens') or {}).get('cost_usd')}</td>"
            f"<td>{(sm.get('tokens') or {}).get('per_case_prompt')}</td></tr>"
        )
    gate = report.get("stage0_principle") or {}
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Stage 2 — governing axis</title>
<style>
  body {{ font: 15px/1.45 Georgia, "Iowan Old Style", serif; color: #1c1917; background: #fafaf9; margin: 0; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 40px 24px 80px; }}
  h1 {{ font-weight: 500; font-size: 30px; letter-spacing: -0.02em; margin: 0 0 8px; }}
  h2 {{ font-weight: 500; font-size: 20px; margin: 36px 0 8px; }}
  p.lead {{ font-size: 18px; max-width: 68ch; }}
  .meta {{ color: #57534e; font-family: ui-sans-serif, system-ui, sans-serif; font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; background: white; font-family: ui-sans-serif, system-ui, sans-serif; font-size: 13.5px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #e7e5e4; vertical-align: top; }}
  th {{ color: #57534e; font-weight: 600; font-size: 12px; letter-spacing: 0.02em; }}
  .sub {{ color: #78716c; font-size: 12px; }}
  .call {{ background: white; border: 1px solid #e7e5e4; padding: 14px 16px; max-width: 72ch; }}
  code {{ font-family: ui-monospace, monospace; font-size: 12.5px; }}
</style>
</head>
<body>
<main>
  <p class="meta">IntelliAudit v0.3 · {d['n_records']} injected cases · Stage 2 smoke test · {report.get('generated','')}</p>
  <h1>The citation problem is an axis, not a memory test</h1>
  <p class="lead">AuditBench asks a model to recall a standard (26% top-1). FinAuditing lists every reference hanging off a concept. AuditFlow checks the numbers. None of them decides whether the defect is about <em>where the line sits</em>, <em>how the amount is measured</em>, or <em>neither</em>.</p>
  <div class="call">
    On all {d['n_citable']} citable cases the right topic is already in the candidate pair
    {{account subject, statement presentation}} <strong>{pct(d['candidate_coverage'])}</strong> of the time.
    Always preferring the account's subject topic, which is what Stage 1 does today, scores
    <strong>{pct(s['topic_accuracy'])}</strong> and still cites a standard on every ungoverned case.
    It scores <strong>{pct(s['by_rule_topic'].get('R01'))}</strong> on current/non-current asset moves
    and <strong>{pct(s['by_rule_topic'].get('R08'))}</strong> on cash-flow section moves, because those
    are presentation defects sitting on a subject account (inventory, PP&amp;E).
    The axis rule — presentation for a misplaced line, subject only for a measurement account, otherwise no citation —
    matches the citable key at topic level on <strong>{pct(p['topic_accuracy'])}</strong> of cases.
    That is the generator's own function, written down. It is not a model result.
    It abstains on <strong>{pct(p['abstain_accuracy'])}</strong> of ungoverned cases.
    The misses are real: an arbitrary number change (R05) or a negative balance (R12) sometimes lands on
    inventory, goodwill, or revenue, and the rule cannot tell those apart from the measurement rules
    without the hidden rule id. R05 abstain {pct(p['by_rule_abstain'].get('R05'))},
    R12 abstain {pct(p['by_rule_abstain'].get('R12'))}.
  </div>

  <h2>Full benchmark, no model</h2>
  <p class="meta">Topic accuracy is exact-match on the 3-digit ASC topic, citable cases only. Abstain accuracy is the share of ungoverned cases where the system cited nothing. The two majority rows are properties of the answer key, not systems: they peek at the labels inside each cell.</p>
  <table>
    <thead><tr><th>System</th><th>Topic accuracy</th><th>Abstain on ungoverned</th><th>False citations</th></tr></thead>
    <tbody>
      {row("Majority topic for the statement type", stmt)}
      {row("Majority topic for (error type × statement)", cell)}
      {row("Stage 1 as it stands: subject topic, else presentation", s)}
      {row("Axis rule, given the true defect and the true account", p)}
    </tbody>
  </table>

  <h2>Why (error type × statement) is no longer enough</h2>
  <p class="meta">Share of the most common topic inside each citable cell. Cells far from 100% are where the account, not the statement, picks the standard.</p>
  <table>
    <thead><tr><th>Cell</th><th>N</th><th>Majority topic</th><th>Majority share</th></tr></thead>
    <tbody>{cell_rows}</tbody>
  </table>

  <h2>Symbolic gate on this benchmark</h2>
  <p>{gate.get("narrative", "Not run.")}</p>
  <p class="meta">IntelliAudit v0.3 writes component movements as <code>[row n] label: +amount (increase)</code> and never prints the line total. The gate sums those signed components. Coverage is a random subset, so a row with no transactions is not evidence of a missing line.</p>

  <h2>Smoke test — frontier model vs open-weight model</h2>
  <p class="meta">{report.get("sample_note","")} Company names were withheld. Temperature 0. Intervals in the JSON are Wilson 95% on the pooled sample and a stratified standard error for the post-stratified topic rate. Eight companies means those intervals are still too narrow if read as a clustered sample.</p>
  <table>
    <thead><tr><th>Model</th><th>Judgment</th><th>Error type</th><th>Topic (sample)</th><th>Topic (post-stratified)</th><th>Abstain</th><th>False alarms on clean</th><th>Cost USD</th><th>Prompt tokens / case</th></tr></thead>
    <tbody>{model_rows or "<tr><td colspan='9'>Model run not included in this file.</td></tr>"}</tbody>
  </table>

  <h2>What this is not</h2>
  <ul>
    <li>Paragraph-level labels are still <code>expert-authored-UNVALIDATED</code> except a handful of linkbase matches. The number above is the topic.</li>
    <li>The axis rule is scored with the true defect and the true account. That is the ceiling. The model rows are the blind test.</li>
    <li>Eight mega-cap filers, no banks or insurers. A model can still recognize a filing from the figures alone.</li>
    <li>R09 (revenue timing) and R11 (inventory NRV) change a number and name a subject standard, but the filing contains no contract and no NRV. Agreeing with those labels is not evidence the model saw a measurement fact.</li>
  </ul>
</main>
</body>
</html>
"""


def write_report(report: dict) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "report.json")
    # sets are not in the report; sample records may contain sets — strip them
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    html = os.path.join(OUT_DIR, "dashboard.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write(render_html(report))
    return html


def run_models(sample: List[dict], pop_counts: Dict[str, int], conditions: List[str],
               model_ids: Optional[List[str]] = None,
               framework: str = "us-gaap") -> dict:
    import openai
    key = load_openrouter_key()
    catalog = list_models(key)
    by_id = {m["id"]: m for m in catalog}
    if model_ids:
        models = []
        for mid in model_ids:
            if mid not in by_id:
                raise RuntimeError(f"OpenRouter has no model {mid}")
            models.append(by_id[mid])
    else:
        models = choose_models(catalog)
    client = openai.OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", max_retries=0)
    # Blind ablation only on the frontier model; both models get Stage 2.
    frontier_id = models[0]["id"]
    out = {}
    gate_cache: Dict[str, dict] = {}
    cache_path = os.path.join(OUT_DIR, "predictions.jsonl")
    done = set()
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                done.add((rec["model"], rec["condition"], rec["sample_id"]))
    os.makedirs(OUT_DIR, exist_ok=True)
    for model in models:
        mid = model["id"]
        pin_price, pout_price = price_of(model)
        for condition in conditions:
            if condition == "blind" and mid != frontier_id:
                continue
            if framework == "ifrs":
                system = SYSTEM_STAGE2_IFRS if condition == "stage2" else SYSTEM_BLIND_IFRS
            else:
                system = SYSTEM_STAGE2 if condition == "stage2" else SYSTEM_BLIND
            by_id = {}
            # A 402 on the free tier is not a result. Retry those. Keep the
            # last successful row if the file has both.
            if os.path.exists(cache_path):
                with open(cache_path, encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        rec = json.loads(line)
                        if rec["model"] == mid and rec["condition"] == condition and not rec.get("error"):
                            by_id[rec["sample_id"]] = rec
            scored = list(by_id.values())
            have = set(by_id)
            pending = [r for r in sample if r["sample_id"] not in have]
            print(f"\n{mid} [{condition}] {len(have)} cached, {len(pending)} to run", flush=True)
            for i, rec in enumerate(pending, 1):
                if condition == "stage2":
                    if rec["sample_id"] not in gate_cache:
                        gate_cache[rec["sample_id"]] = stage0_on(rec)
                    gate = gate_cache[rec["sample_id"]]
                else:
                    gate = None
                user = build_user(rec, gate, with_candidates=(condition == "stage2"))
                result = call_model(client, mid, system, user)
                sc = score_llm_obj(result["parsed"], rec)
                ptok, ctok, cost = _usage_tokens(result["usage"])
                if cost is None and (ptok or ctok):
                    cost = ptok * pin_price + ctok * pout_price
                parsed = result["parsed"] or {}
                row = {
                    "model": mid,
                    "condition": condition,
                    "sample_id": rec["sample_id"],
                    "rule": rec.get("rule"),
                    "citable": rec.get("citable"),
                    "is_clean": bool(rec.get("is_clean")),
                    "gold_topic": rec.get("topic"),
                    "gold_type": rec.get("error_type"),
                    "error": result["error"],
                    "citation": parsed.get("standards_citation"),
                    "evidence": (parsed.get("evidence") or "")[:240],
                    "prompt_tokens": ptok,
                    "completion_tokens": ctok,
                    "cost_usd": cost,
                    **sc,
                }
                if result["error"] is None:
                    scored.append(row)
                with open(cache_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
                time.sleep(3)
                mark = "ok" if result["error"] is None else "ERR"
                print(f"  [{i}/{len(pending)}] {rec['sample_id'][:42]:<42} {mark} "
                      f"topic={sc['pred_topic']} hit={sc['topic_hit']}", flush=True)
            summary = summarize_llm(scored, pop_counts)
            out[f"{mid}::{condition}"] = {
                "model": mid,
                "condition": condition,
                "summary": summary,
                "n": len(scored),
            }
            th = summary.get("topic_hit", {})
            print(f"  topic {th.get('rate')}  abstain {summary.get('abstain_hit',{}).get('rate')}  "
                  f"cost {summary.get('tokens',{}).get('cost_usd')}", flush=True)
    return out


def stage0_principle_full(rows: List[dict], limit: Optional[int] = None) -> dict:
    """Deployable system: symbolic gate names the defect, mapper names the account, axis rule cites."""
    use = rows if limit is None else rows[:limit]
    t_flags, a_flags = [], []
    fired = 0
    type_ok = []
    t0 = time.time()
    for i, rec in enumerate(use):
        gate = stage0_on(rec)
        if gate.get("fired"):
            fired += 1
            type_ok.append(int(gate.get("error_type") == rec.get("error_type")))
            concept = mapped_concept_at(rec, gate.get("row"))
            _axis, topic = axis_decision(
                gate.get("error_type"), concept, rec.get("pipe_stmt"),
                framework=rec.get("framework"),
            )
        else:
            topic = None
        th = topic_hit(topic, rec)
        ah = abstain_hit(topic, rec)
        if th is not None:
            t_flags.append(th)
        if ah is not None:
            a_flags.append(ah)
        if (i + 1) % 100 == 0:
            print(f"  stage0 {i+1}/{len(use)}", flush=True)
    elapsed = time.time() - t0
    n_t, k_t = len(t_flags), sum(t_flags)
    n_a, k_a = len(a_flags), sum(a_flags)
    return {
        "n": len(use),
        "seconds": round(elapsed, 1),
        "fire_rate": fired / len(use) if use else None,
        "type_accuracy_when_fired": (sum(type_ok) / len(type_ok) if type_ok else None),
        "topic_accuracy": (k_t / n_t if n_t else None),
        "topic_n": n_t,
        "abstain_accuracy": (k_a / n_a if n_a else None),
        "false_citation_rate": (1 - k_a / n_a if n_a else None),
        "narrative": (
            f"On {len(use)} cases the symbolic gate fired on {fired / len(use):.1%} and, when it fired, "
            f"named the right error type { (sum(type_ok) / len(type_ok) if type_ok else 0):.1%} of the time. "
            f"Feeding that type and the mapped account into the axis rule yields topic accuracy "
            f"{(k_t / n_t if n_t else 0):.1%} on the citable cases it was scored on, and abstains on "
            f"{(k_a / n_a if n_a else 0):.1%} of ungoverned cases. "
            f"Runtime {elapsed:.0f}s. No model was called."
        ),
    }


def main():
    _self_check()
    ap = argparse.ArgumentParser(description="Stage 2 governing-axis evaluation")
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--stage0-full", action="store_true",
                    help="Score the symbolic gate on all 1,231 cases (slow).")
    ap.add_argument("--per-rule", type=int, default=2)
    ap.add_argument("--n-clean", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--conditions", default="stage2,blind",
                    help="comma list: stage2, blind")
    ap.add_argument("--models", default="",
                    help="comma-separated OpenRouter model ids")
    ap.add_argument("--framework", choices=["us-gaap", "ifrs"], default="us-gaap",
                    help="us-gaap reads data/intelliaudit; ifrs reads data/ifrs/benchmark")
    ap.add_argument("--data-dir", default="",
                    help="exam directory (exam.jsonl + answer_key.jsonl). "
                         "Default follows --framework.")
    args = ap.parse_args()

    rows = load_joined(args.data_dir or None, framework=args.framework)
    print(f"loaded {len(rows)} records", flush=True)
    full = analyze_full(rows)
    print("\n=== full benchmark, no model ===", flush=True)
    print(f"coverage of gold topic in {{subject, presentation}}: {full['candidate_coverage']}", flush=True)
    for name in ("statement_majority", "error_x_statement_majority",
                 "subject_first_selector", "axis_principle"):
        b = full[name]
        print(f"{name:32} topic {b['topic_accuracy']}  "
              f"abstain {b['abstain_accuracy']}  false-cite {b['false_citation_rate']}", flush=True)

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "full": full,
        "sample_note": "",
        "models": {},
    }
    if args.stage0_full:
        print("\n=== stage 0 + axis rule on the full set ===", flush=True)
        report["stage0_principle"] = stage0_principle_full(rows)
        print(report["stage0_principle"]["narrative"], flush=True)

    if args.analyze_only:
        html = write_report(report)
        print("wrote", html, flush=True)
        return

    clean = load_clean(rows)
    sample = stratified_sample(rows, clean, args.per_rule, args.n_clean, args.seed)
    pop_counts = Counter(r["rule"] for r in rows if r["citable"])
    report["sample_note"] = (
        f"Stratified sample: {args.per_rule} cases per rule, rotating companies, "
        f"plus {args.n_clean} clean statements. Seed {args.seed}. "
        f"N = {sum(1 for r in sample if not r.get('is_clean'))} error cases + "
        f"{sum(1 for r in sample if r.get('is_clean'))} clean."
    )
    print("\n" + report["sample_note"], flush=True)
    print("scoring symbolic gate + axis rule on the sample", flush=True)
    report["stage0_principle"] = stage0_principle_full(sample)
    print(report["stage0_principle"]["narrative"], flush=True)
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    wanted = [m.strip() for m in args.models.split(",") if m.strip()]
    models = run_models(sample, pop_counts, conditions, wanted or None,
                        framework=args.framework)
    report["models"] = models
    html = write_report(report)
    print("\nwrote", html, flush=True)


if __name__ == "__main__":
    main()
