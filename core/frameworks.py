"""
Accounting-framework registry for the audit pipeline.

US GAAP is the default. IFRS is a second framework with its own concept
namespace (``ifrs-full``), its own citation grammar (``IAS 2.36``,
``IFRS 15.31``), and its own dataset under ``data/ifrs/``. The generator
that builds that dataset lives in the IntelliAudit repo; this module is the
pipeline side of the same split.

Citation identifiers are paragraph numbers only. Standards text is licensed
and is not stored here.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

FRAMEWORKS: Dict[str, dict] = {
    "us-gaap": {
        "namespace": "us-gaap",
        "citation": "ASC",
        "forms": ("10-K",),
        "rulebook": None,
        "exam_dir": ("data", "intelliaudit"),
    },
    "ifrs": {
        "namespace": "ifrs-full",
        "citation": "IFRS",
        "forms": ("20-F", "40-F"),
        "rulebook": ("data", "ifrs", "rulebook_ifrs.json"),
        "exam_dir": ("data", "ifrs", "benchmark"),
    },
}

_IFRS_NAMES = ("IAS", "IFRS", "IFRIC", "SIC")

# Same grammar as IntelliAudit's citation_resolver.ifrs_paragraph_of.
# 'IAS 1 paragraph 66(a)' / 'IAS 1.66' / 'IFRS 9.5.5.15' all parse.
_IFRS_RE = re.compile(
    r"\b(IAS|IFRS|IFRIC|SIC)\s*(\d{1,2})"
    r"(?:\s*(?:\.|,?\s*para(?:graph|\.)?\s*)\s*"
    r"([0-9]+(?:\.[0-9]+)*[A-Z]{0,2}))?"
    r"(?:\s*\(([a-z]{1,4}|[ivx]+)\))?",
    re.I,
)

_ASC_ID_RE = re.compile(
    r"(?:FASB\s+)?(?:ASC|SFAC|SAB|FAS|APB|SOP)\s*[\d][\d\-\.]*",
    re.I,
)


def get(name: str) -> dict:
    key = (name or "").strip().lower()
    if key in ("ifrs-full", "ifrs"):
        key = "ifrs"
    try:
        return FRAMEWORKS[key]
    except KeyError:
        raise ValueError(
            f"unknown framework {name!r}; expected one of {sorted(FRAMEWORKS)}"
        )


def bare_concept(concept: Optional[str]) -> str:
    """'ifrs-full:Inventories' or 'us-gaap:InventoryNet' -> the local name."""
    text = (concept or "").strip()
    if ":" in text:
        return text.split(":", 1)[1]
    return text


def resolve_framework(concept: Optional[str] = None,
                      framework: Optional[str] = None) -> str:
    """Explicit framework wins. Otherwise an ``ifrs-full:`` concept selects IFRS."""
    if framework:
        key = framework.strip().lower()
        if key in ("ifrs", "ifrs-full"):
            return "ifrs"
        if key in ("us-gaap", "usgaap", "gaap"):
            return "us-gaap"
        raise ValueError(
            f"unknown framework {framework!r}; expected 'us-gaap' or 'ifrs'"
        )
    if (concept or "").startswith("ifrs-full:"):
        return "ifrs"
    return "us-gaap"


def ifrs_code_from_parts(parts: Union[Sequence[Tuple[str, str]], dict]) -> Optional[str]:
    """Reference-linkbase parts -> 'IAS 1.66(a)' or 'IFRS 15.31'.

    Returns None when the parts are not an IFRS/IAS/IFRIC/SIC standard.
    """
    d = dict(parts)
    name = (d.get("Name") or "").strip()
    number = (d.get("Number") or "").strip()
    if name not in _IFRS_NAMES or not number:
        return None
    code = f"{name} {number}"
    paragraph = (d.get("Paragraph") or "").strip()
    if paragraph:
        code += f".{paragraph}"
        sub = (d.get("Subparagraph") or "").strip().strip("()")
        if sub:
            code += f"({sub})"
    return code


def ifrs_paragraph_of(text: Optional[str]) -> Optional[str]:
    """'IAS 1 paragraph 66(a)' / 'IAS 1.66' -> 'IAS 1.66'.

    A standard with no paragraph ('IAS 1') returns None. Subparagraph
    markers are dropped; the scored code stops at the paragraph.
    """
    m = _IFRS_RE.search(str(text or ""))
    if not m or not m.group(3):
        return None
    return f"{m.group(1).upper()} {int(m.group(2))}.{m.group(3).upper()}"


def ifrs_standard_of(text: Optional[str]) -> Optional[str]:
    """'under IFRS 15.31' -> 'IFRS 15'. A standard alone is enough."""
    m = _IFRS_RE.search(str(text or ""))
    if not m:
        return None
    return f"{m.group(1).upper()} {int(m.group(2))}"


def format_citation(code: Optional[str]) -> str:
    """Display form. IFRS codes stay 'IAS 2.9'. Bare ASC codes gain an ASC prefix."""
    if not code:
        return ""
    text = str(code).strip()
    if ifrs_standard_of(text):
        return ifrs_paragraph_of(text) or ifrs_standard_of(text) or text
    if re.match(r"(?i)^(FASB\s+)?(ASC|SFAC|SAB|FAS|APB|SOP)\b", text):
        return text
    return f"ASC {text}"


def ifrs_ids(text: str) -> List[str]:
    """Paragraph id, then standard id, for each IFRS citation in ``text``."""
    out: List[str] = []
    seen = set()
    for m in _IFRS_RE.finditer(str(text or "")):
        standard = f"{m.group(1).upper()} {int(m.group(2))}"
        ids = []
        if m.group(3):
            ids.append(f"{standard}.{m.group(3).upper()}")
        ids.append(standard)
        for ident in ids:
            if ident not in seen:
                seen.add(ident)
                out.append(ident)
    return out


def citation_ids(text: str) -> List[str]:
    """FASB ids and IFRS ids, in appearance order, for overlap scoring."""
    raw_asc = _ASC_ID_RE.findall(str(text or ""))
    asc = [re.sub(r"\s+", " ", r.strip().upper()) for r in raw_asc]
    return asc + ifrs_ids(text)
