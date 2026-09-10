"""
finmr_parser.py — Splits a FinMR query string into typed sections and
extracts the target concept + period from the two questions.

No LLM involved.  All parsing is deterministic regex / XML.

Sections present in every query (separated by ##Header lines):
  ##Schema document           — XSD, not used for arithmetic
  ##Presentation linkbase ... — not used for arithmetic
  ##Calculation linkbase ...  — WHERE the calc arcs live  ← key
  ##Definition linkbase ...   — not used
  ##Label linkbase ...        — not used
  ##Instance document         — WHERE the reported facts live  ← key
  [Concept Relations]         — text blob, not used
  Question1 / Question2       — target concept + period
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── section splitting ─────────────────────────────────────────────────────────

def _decode(s: str) -> str:
    """Unescape the FinMR query string.

    The dataset stores XML as a flat Python-repr-style string where:
      \\n  → real newline
      \\t  → real tab
      \\"  → "   (XML attribute quotes)
      \\'  → '   (XML attribute quotes)
    All four must be decoded before passing the text to an XML parser.
    """
    return (s
            .replace('\\"', '"')
            .replace("\\'", "'")
            .replace('\\n', '\n')
            .replace('\\t', '\t'))


def split_sections(query: str) -> Dict[str, str]:
    """Return a dict of section_name_lower → raw section text."""
    q = _decode(query)
    sections: Dict[str, str] = {}
    current_key = "_preamble"
    buf: List[str] = []

    for line in q.split('\n'):
        if line.startswith('##'):
            sections[current_key] = '\n'.join(buf)
            current_key = line[2:].strip().lower()
            buf = []
        else:
            buf.append(line)
    sections[current_key] = '\n'.join(buf)
    return sections


# ── question parsing ──────────────────────────────────────────────────────────

# Duration period: "for the period YYYY-MM-DD to YYYY-MM-DD"
_Q_CONCEPT_RE = re.compile(
    r'reported value of\s+([\w-]+:[\w]+)\b.*?'
    r'for the period\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})',
    re.DOTALL | re.IGNORECASE,
)
# Instant period: "for the period YYYY-MM-DD" or "for YYYY-MM-DD" (no 'to')
_Q_INSTANT_RE = re.compile(
    r'reported value of\s+([\w-]+:[\w]+)\b.*?'
    r'for(?:\s+the\s+period)?\s+(\d{4}-\d{2}-\d{2})',
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class FinMRQuestion:
    concept: str            # e.g. "us-gaap:NetCashProvidedByUsedInOperatingActivities"
    concept_bare: str       # e.g. "NetCashProvidedByUsedInOperatingActivities"
    period_start: Optional[str]  # e.g. "2020-10-01" (None for instant)
    period_end:   Optional[str]  # e.g. "2021-09-30"
    instant:      Optional[str]  # set when period is a single date


def parse_questions(query: str) -> Optional[FinMRQuestion]:
    """Extract the target concept and period from the Question1 text."""
    q = _decode(query)
    m = _Q_CONCEPT_RE.search(q)
    if m:
        concept = m.group(1)
        return FinMRQuestion(
            concept=concept,
            concept_bare=concept.split(':')[-1],
            period_start=m.group(2),
            period_end=m.group(3),
            instant=None,
        )
    m = _Q_INSTANT_RE.search(q)
    if m:
        concept = m.group(1)
        return FinMRQuestion(
            concept=concept,
            concept_bare=concept.split(':')[-1],
            period_start=None,
            period_end=None,
            instant=m.group(2),
        )
    return None


# ── instance document parsing ─────────────────────────────────────────────────

@dataclass
class XBRLContext:
    ctx_id:      str
    start_date:  Optional[str] = None
    end_date:    Optional[str] = None
    instant:     Optional[str] = None
    has_dimension: bool = False   # True if context has a segment/scenario member
    # Dimensional contexts hold segment breakdowns (e.g. by geography); the
    # consolidated reported value lives in the NON-dimensional context.


@dataclass
class XBRLFact:
    concept:    str    # local name, e.g. "NetCashProvidedByUsedInOperatingActivities"
    ns_prefix:  str    # e.g. "us-gaap"
    ctx_ref:    str
    value:      str    # raw string from filing


# ── regex patterns for truncated-XML fallback ─────────────────────────────────
# Instance documents are capped at ~32,768 chars in the dataset; the XML often
# ends mid-tag. regex is more resilient to incomplete documents.

# (?:[^:>\s]+:)? makes the namespace prefix optional — handles both
# <xbrli:context id="..."> and bare <context id="...">
_CTX_BODY_RE = re.compile(
    r'<(?:[^:>\s]+:)?context\b[^>]*?\bid=["\']([^"\']+)["\'][^>]*>'
    r'(.*?)</(?:[^:>\s]+:)?context>', re.DOTALL)
_SD_RE   = re.compile(r'<[^>]*startDate[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*<')
_ED_RE   = re.compile(r'<[^>]*endDate[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*<')
_INS_RE  = re.compile(r'<[^>]*instant[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*<')
# Facts: both namespaced <ns:Concept contextRef="..."> and bare <Concept contextRef="...">
_FACT_RE = re.compile(
    r'<(?:([\w-]+):)?([\w]+)\s[^>]*contextRef=["\']([^"\']+)["\'][^>]*/?>([^<]*)',
    re.DOTALL)


def _parse_instance_regex(xml: str) -> Tuple[Dict[str, XBRLContext], List[XBRLFact]]:
    """Regex fallback for truncated XBRL instance XML."""
    contexts: Dict[str, XBRLContext] = {}
    for m in _CTX_BODY_RE.finditer(xml):
        cid, body = m.group(1), m.group(2)
        ctx = XBRLContext(ctx_id=cid)
        sd = _SD_RE.search(body); ed = _ED_RE.search(body)
        ins = _INS_RE.search(body)
        if sd and ed:
            ctx.start_date, ctx.end_date = sd.group(1), ed.group(1)
        elif ins:
            ctx.instant = ins.group(1)
        # dimensional if it carries a segment/scenario member
        if ('explicitMember' in body or 'typedMember' in body
                or '<segment' in body or '<scenario' in body):
            ctx.has_dimension = True
        contexts[cid] = ctx

    facts: List[XBRLFact] = []
    seen: set = set()
    for m in _FACT_RE.finditer(xml):
        prefix  = m.group(1) or ""   # None when no namespace prefix
        local   = m.group(2)
        ctx_ref = m.group(3)
        value   = m.group(4).strip()
        if value and ctx_ref:
            key = (local, ctx_ref)
            if key not in seen:
                seen.add(key)
                facts.append(XBRLFact(
                    concept=local, ns_prefix=prefix,
                    ctx_ref=ctx_ref, value=value))
    return contexts, facts


def parse_instance(instance_xml: str) -> Tuple[Dict[str, XBRLContext], List[XBRLFact]]:
    """Parse XBRL instance XML into contexts and facts.
    Tries ElementTree first; falls back to regex for truncated documents.
    """
    ns_map: Dict[str, str] = {}
    for m in re.finditer(r'xmlns:(\w+)=["\']([^"\']+)["\']', instance_xml):
        ns_map[m.group(2)] = m.group(1)

    try:
        root = ET.fromstring(instance_xml)
    except ET.ParseError:
        return _parse_instance_regex(instance_xml)

    # ── contexts (ElementTree path) ───────────────────────────────────────────
    contexts: Dict[str, XBRLContext] = {}
    XBRLI = 'http://www.xbrl.org/2003/instance'
    for ctx_el in root.iter(f'{{{XBRLI}}}context'):
        cid = ctx_el.get('id', '')
        ctx = XBRLContext(ctx_id=cid)
        period = ctx_el.find(f'{{{XBRLI}}}period')
        if period is not None:
            sd  = period.find(f'{{{XBRLI}}}startDate')
            ed  = period.find(f'{{{XBRLI}}}endDate')
            ins = period.find(f'{{{XBRLI}}}instant')
            if sd is not None and ed is not None:
                ctx.start_date = sd.text.strip() if sd.text else None
                ctx.end_date   = ed.text.strip() if ed.text else None
            elif ins is not None:
                ctx.instant = ins.text.strip() if ins.text else None
        # dimensional if entity has a segment/scenario with members
        entity = ctx_el.find(f'{{{XBRLI}}}entity')
        seg = entity.find(f'{{{XBRLI}}}segment') if entity is not None else None
        scen = ctx_el.find(f'{{{XBRLI}}}scenario')
        if (seg is not None and len(seg)) or (scen is not None and len(scen)):
            ctx.has_dimension = True
        contexts[cid] = ctx

    # ── facts (ElementTree path) ──────────────────────────────────────────────
    facts: List[XBRLFact] = []
    for el in root:
        tag = el.tag
        if not tag.startswith('{'):
            continue
        uri_end = tag.index('}')
        ns_uri  = tag[1:uri_end]
        local   = tag[uri_end + 1:]
        prefix  = ns_map.get(ns_uri, ns_uri.split('/')[-1])
        ctx_ref = el.get('contextRef', '')
        value   = (el.text or '').strip()
        if value and ctx_ref:
            facts.append(XBRLFact(
                concept=local, ns_prefix=prefix,
                ctx_ref=ctx_ref, value=value,
            ))
    return contexts, facts


# ── calculation linkbase parsing ──────────────────────────────────────────────

@dataclass
class CalcArc:
    parent_concept: str   # bare local name
    child_concept:  str   # bare local name
    weight:         float


def parse_calc_linkbase(calc_xml: str) -> List[CalcArc]:
    """Parse XBRL calculation linkbase into (parent, child, weight) arcs."""
    try:
        root = ET.fromstring(calc_xml)
    except ET.ParseError:
        return []

    LINK = 'http://www.xbrl.org/2003/linkbase'
    XLINK = 'http://www.w3.org/1999/xlink'

    # Build label → concept map from <link:loc> elements
    label_to_concept: Dict[str, str] = {}
    for loc in root.iter(f'{{{LINK}}}loc'):
        label = loc.get(f'{{{XLINK}}}label', '')
        href  = loc.get(f'{{{XLINK}}}href', '')
        # href looks like "...us-gaap-2021-01-31.xsd#us-gaap_NetCashProvided..."
        if '#' in href:
            fragment = href.split('#')[-1]
            # fragment: "us-gaap_NetCashProvidedByUsedInOperatingActivities" or
            #           "loc_us-gaap_NetCash_uuid" — take part after last known prefix
            local = fragment.split('_', 1)[-1] if '_' in fragment else fragment
            # strip any UUID suffix (36-char hex with dashes)
            local = re.sub(r'_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
                           '', local, flags=re.IGNORECASE)
            label_to_concept[label] = local

    arcs: List[CalcArc] = []
    for arc in root.iter(f'{{{LINK}}}calculationArc'):
        from_lbl = arc.get(f'{{{XLINK}}}from', '')
        to_lbl   = arc.get(f'{{{XLINK}}}to',   '')
        weight   = float(arc.get('weight', '1'))
        parent   = label_to_concept.get(from_lbl)
        child    = label_to_concept.get(to_lbl)
        if parent and child:
            arcs.append(CalcArc(parent_concept=parent,
                                child_concept=child,
                                weight=weight))
    return arcs


# ── combined record ───────────────────────────────────────────────────────────

@dataclass
class FinMRParsed:
    record_id:  int
    dqc_rule:   str
    question:   Optional[FinMRQuestion]
    contexts:   Dict[str, XBRLContext]
    facts:      List[XBRLFact]
    calc_arcs:  List[CalcArc]
    gt_extracted:   str
    gt_calculated:  str


def parse_record(row: dict) -> FinMRParsed:
    """Full parse pipeline for one FinMR dataset row."""
    import json as _json
    sections = split_sections(row["query"])

    # Identify instance and calculation sections by key substring
    instance_xml = next(
        (v for k, v in sections.items() if 'instance' in k), ""
    )
    calc_xml = next(
        (v for k, v in sections.items() if 'calculation' in k), ""
    )

    contexts, facts = parse_instance(instance_xml)
    calc_arcs       = parse_calc_linkbase(calc_xml)
    question        = parse_questions(row["query"])

    ans = row["answer"]
    if isinstance(ans, str):
        try:
            ans = _json.loads(ans)
        except Exception:
            ans = {"extracted_value": "", "calculated_value": ""}

    return FinMRParsed(
        record_id=row["id"],
        dqc_rule=row["dqc_id"].strip('"'),
        question=question,
        contexts=contexts,
        facts=facts,
        calc_arcs=calc_arcs,
        gt_extracted=str(ans.get("extracted_value", "")),
        gt_calculated=str(ans.get("calculated_value", "")),
    )


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from datasets import load_dataset
    ds = load_dataset("TheFinAI/FinMR", split="test")
    seen = {}
    for row in ds:
        rule = row["dqc_id"].strip('"')
        if rule not in seen:
            seen[rule] = row
        if len(seen) == 3:
            break

    for rule, row in seen.items():
        rec = parse_record(row)
        print(f"\nDQC: {rec.dqc_rule}  id={rec.record_id}")
        print(f"  question : {rec.question}")
        print(f"  contexts : {len(rec.contexts)} parsed")
        print(f"  facts    : {len(rec.facts)} parsed")
        print(f"  calc arcs: {len(rec.calc_arcs)} parsed")
        print(f"  GT extracted  : {rec.gt_extracted}")
        print(f"  GT calculated : {rec.gt_calculated}")
        if rec.question:
            target = rec.question.concept_bare
            relevant_arcs = [a for a in rec.calc_arcs if a.parent_concept == target]
            print(f"  calc arcs for target: {len(relevant_arcs)}")
            for a in relevant_arcs[:5]:
                print(f"    child={a.child_concept}  weight={a.weight}")
