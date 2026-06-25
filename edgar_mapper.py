"""
EDGAR Mapper — Stage 1 of the IntelliAudit pipeline.

Converts an AuditBench item (table + transactions) into a structured
MappedStatement: each valued row is linked to its US-GAAP XBRL concept
and the FASB ASC citation(s) that govern it.

Architecture context (from design doc):
  Stage 0 (Daksh)  → deterministic arithmetic gate
  Stage 1 (irvin)  → THIS FILE — map rows to XBRL concepts + ASC citations
  Stage 2 (man-mad)→ Arelle taxonomy validation + focused LLM

Three mapping strategies (in priority order):
  1. Exact match      — normalized label matches a key in xbrl_concept_map.json
  2. Fuzzy match      — difflib SequenceMatcher (cutoff configurable)
  3. Stem match       — strip common suffixes and retry exact/fuzzy
                       (handles "total current assets" → "current assets" etc.)

The EDGAR XBRL route (Section 4.3 of design doc — Strategy 3, preferred for
accuracy studies) is scaffolded as edgar_xbrl_lookup() but left as a stub
pending live SEC EDGAR network access.  Its signature is the integration
point man-mad needs; replace the stub with real requests.get() calls when
a key is available or when running outside the sandbox.

Usage:
  python edgar_mapper.py                  # demo on one Apple balance sheet
  python edgar_mapper_eval.py --n 150    # full eval (no API key needed)

Handoff contract for man-mad (Stage 2 / Arelle):
  from edgar_mapper import map_statement, MappedStatement, MappedRow
  mapped = map_statement(item)
  # mapped.rows  → list[MappedRow]
  # each MappedRow has: row_idx, label, norm, value, concept, asc_primary,
  #                     asc_refs, section, strategy, confidence
"""

from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── reuse Daksh's shared layer ────────────────────────────────────────────────
from stage0_common import build_table, norm_label, rows_of

# ── resource paths ────────────────────────────────────────────────────────────
_HERE = os.path.dirname(__file__)
_CONCEPT_MAP_PATH  = os.path.join(_HERE, "xbrl_concept_map.json")
_TICKERS_PATH      = os.path.join(_HERE, "company_tickers.json")

# ── load resources once at import time ───────────────────────────────────────
with open(_CONCEPT_MAP_PATH, encoding="utf-8") as _f:
    _RAW_MAP = json.load(_f)

with open(_TICKERS_PATH, encoding="utf-8") as _f:
    _TICKERS: Dict[str, str] = {k: v for k, v in json.load(_f).items()
                                 if not k.startswith("_")}

# Concept maps per statement type (excludes meta keys starting with _)
_STMT_MAPS: Dict[str, Dict] = {
    k: v for k, v in _RAW_MAP.items()
    if not k.startswith("_") and isinstance(v, dict)
}
# Error-type fallback citations
_ERROR_ASC: Dict[str, dict] = _RAW_MAP.get("_error_type_asc", {})
# ASC topic titles for human-readable output
_ASC_TITLES: Dict[str, str] = _RAW_MAP.get("_asc_titles", {})

# Fuzzy match cutoff — 0.75 is conservative enough to avoid false positives
# on short labels; lower to ~0.65 to trade precision for recall.
FUZZY_CUTOFF = 0.75

# ── statement type inference ──────────────────────────────────────────────────
_STMT_KEYWORDS = {
    "balance_sheet":      ["balance sheet", "balance", "financial position"],
    "income_statement":   ["income", "earnings", "operations", "profit", "loss",
                           "comprehensive income"],
    "cash_flow":          ["cash flow", "cash flows", "cash and cash equiv"],
}


def infer_statement_type(sheet_type: str, table: str = "") -> str:
    """Infer statement type from Sheet_type string, table header, or row content.

    Three passes in priority order:
      1. Sheet_type field (present on correct split)
      2. [Tab] header line inside the table (present on correct split)
      3. Content-based: look at first 10 row labels for strong signal words
         (needed on error splits where Sheet_type is missing)
    """
    # Pass 1: Sheet_type field and table header combined
    combined = (sheet_type + " " + table[:300]).lower()
    for stype, keywords in _STMT_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return stype

    # Pass 2: [Tab] line
    tab_m = re.search(r'\[Tab\]\s*(.*?)(?:\[SEP\]|$)', table[:400], re.IGNORECASE)
    if tab_m:
        result = infer_statement_type(tab_m.group(1))
        if result != "unknown":
            return result

    # Pass 3: Content-based inference from row labels (error splits)
    # Extract the first 10 row labels and check for strong indicator words
    row_labels = re.findall(r'\[row\s*\d+\]\s*:\s*([^|[]+?)(?:\s*\||\s*\[SEP\])', table)
    row_text = " ".join(row_labels[:10]).lower()

    bs_signals  = ["assets", "liabilities", "equity", "stockholders", "shareholders",
                   "current assets", "current liabilities", "retained earnings",
                   "accounts payable", "accounts receivable"]
    cf_signals  = ["operating activities", "investing activities", "financing activities",
                   "cash flows", "capital expenditures", "short-term borrowings",
                   "long-term financing", "net short-term"]
    is_signals  = ["revenue", "revenues", "net sales", "cost of", "gross profit",
                   "gross margin", "operating income", "net income", "net loss",
                   "operating expenses", "selling", "research and development"]

    bs_score  = sum(1 for s in bs_signals if s in row_text)
    cf_score  = sum(1 for s in cf_signals if s in row_text)
    is_score  = sum(1 for s in is_signals if s in row_text)

    best = max(bs_score, cf_score, is_score)
    if best == 0:
        return "unknown"
    if bs_score == best:
        return "balance_sheet"
    if cf_score == best:
        return "cash_flow"
    return "income_statement"


# ── period parsing ────────────────────────────────────────────────────────────
_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05",      "june": "06",     "july": "07",  "august": "08",
    "september": "09","october": "10",  "november": "11","december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}


def parse_period(table_str: str) -> Optional[str]:
    """Extract reporting period from [Time]: ... as YYYY-MM-DD (best effort)."""
    m = re.search(r'\[Time\]\s*:\s*([^\[]+)', table_str, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).strip().rstrip('[SEP]').strip()

    # Try ISO-style "2023" or "FY 2023"
    year_m = re.search(r'\b(20\d{2}|19\d{2})\b', raw)
    year = year_m.group(1) if year_m else None

    # Try "September 30, 2023" → 2023-09-30
    full_m = re.search(
        r'(\w+)\s+(\d{1,2}),?\s*(20\d{2}|19\d{2})', raw, re.IGNORECASE)
    if full_m:
        month_str = full_m.group(1).lower()
        day = full_m.group(2).zfill(2)
        yr  = full_m.group(3)
        month = _MONTH_MAP.get(month_str)
        if month:
            return f"{yr}-{month}-{day}"

    # Try "Q3 2023" → 2023-09
    q_m = re.search(r'Q(\d)\s*(20\d{2})', raw, re.IGNORECASE)
    if q_m:
        q_ends = {"1": "03", "2": "06", "3": "09", "4": "12"}
        return f"{q_m.group(2)}-{q_ends.get(q_m.group(1), '12')}"

    return year  # bare year as fallback


# ── concept lookup ────────────────────────────────────────────────────────────
def _exact_lookup(norm: str, stype: str) -> Optional[dict]:
    """Exact match: check statement-specific map first, then other maps."""
    if stype in _STMT_MAPS and norm in _STMT_MAPS[stype]:
        return _STMT_MAPS[stype][norm]
    for other_stype, cmap in _STMT_MAPS.items():
        if other_stype != stype and norm in cmap:
            return cmap[norm]
    return None


def _fuzzy_lookup(norm: str, stype: str, cutoff: float = FUZZY_CUTOFF
                  ) -> Tuple[Optional[dict], float]:
    """Best fuzzy match across all statement-type maps.

    Returns (entry, score) or (None, 0.0).
    Uses difflib.SequenceMatcher for token-aware similarity.
    """
    # Prefer the statement-specific map for the first pass
    candidates: List[Tuple[str, dict]] = []
    priority = [stype] + [s for s in _STMT_MAPS if s != stype]
    for st in priority:
        if st in _STMT_MAPS:
            candidates.extend(_STMT_MAPS[st].items())

    best_key: Optional[str] = None
    best_score = 0.0
    for key, entry in candidates:
        score = difflib.SequenceMatcher(None, norm, key).ratio()
        if score > best_score:
            best_score = score
            best_key = key

    if best_score >= cutoff and best_key is not None:
        # Determine which map it came from
        for st in priority:
            if st in _STMT_MAPS and best_key in _STMT_MAPS[st]:
                return _STMT_MAPS[st][best_key], best_score
    return None, best_score


def _stem_variants(norm: str) -> List[str]:
    """Generate simplified variants to retry exact lookup.

    Examples:
      "total current assets" → "current assets"
      "net cash used in investing activities" → "investing activities"
      "basic earnings per share" → "basic"
    """
    variants = []
    # Strip leading "total "
    if norm.startswith("total "):
        variants.append(norm[6:])
    # Strip leading "net "
    if norm.startswith("net "):
        variants.append(norm[4:])
    # "X and Y" → try both halves
    if " and " in norm:
        parts = norm.split(" and ", 1)
        variants.extend(parts)
    # Last two words (catches "investing activities" from longer labels)
    words = norm.split()
    if len(words) > 2:
        variants.append(" ".join(words[-2:]))
    if len(words) > 3:
        variants.append(" ".join(words[-3:]))
    return variants


def match_concept(norm: str, stype: str) -> Tuple[Optional[dict], str, float]:
    """Return (concept_entry, strategy, confidence).

    strategy ∈ {"exact", "stem_exact", "fuzzy", "none"}
    confidence ∈ [0, 1]
    """
    # 1. Exact
    entry = _exact_lookup(norm, stype)
    if entry:
        return entry, "exact", 1.0

    # 2. Stem variants → exact retry
    for variant in _stem_variants(norm):
        entry = _exact_lookup(variant, stype)
        if entry:
            return entry, "stem_exact", 0.90

    # 3. Fuzzy
    entry, score = _fuzzy_lookup(norm, stype)
    if entry:
        return entry, "fuzzy", round(score, 3)

    return None, "none", 0.0


# ── SEC EDGAR XBRL lookup (stub — Strategy 3 from design doc) ────────────────
def edgar_xbrl_lookup(ticker: str, concept: str, period: Optional[str]) -> Optional[dict]:
    """Query the SEC EDGAR company facts API for the filer's own XBRL tag.

    This is Strategy 3 from the design doc:
      "Use the filers' own us-gaap tags from the original public filings.
       Reproducible ground truth, not hardcoding."

    Endpoint: https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json
    Requires: CIK lookup (ticker → CIK via https://data.sec.gov/submissions/{CIK}.json)

    Currently a STUB — uncomment and implement when network access is available.
    The return value should match the concept map entry schema:
      {"concept": ..., "asc_primary": ..., "asc_refs": [...], ...}
    """
    # TODO (irvin): implement live EDGAR lookup
    # 1. GET https://data.sec.gov/submissions/{CIK}.json to resolve ticker → CIK
    # 2. GET https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json
    # 3. Find the concept entry matching `concept` and `period`
    # 4. Return its us-gaap tag as {"concept": "us-gaap:<tag>", ...}
    return None


# ── dataclasses (the handoff contract for man-mad) ────────────────────────────
@dataclass
class MappedRow:
    row_idx: int
    label: str              # original label from table
    norm: str               # normalized label (stage0_common.norm_label)
    value: Optional[float]  # numeric value (None for headers)
    kind: str               # 'leaf' | 'subtotal' | 'header'

    # mapping outputs
    concept: Optional[str]  = None   # us-gaap:ConceptName
    asc_primary: Optional[str] = None  # e.g. "210-10-45-1"
    asc_refs: List[str]     = field(default_factory=list)  # all relevant ASC sections
    asc_title: Optional[str] = None  # human-readable topic title
    section: Optional[str]  = None   # e.g. "current_assets"
    strategy: str           = "none" # "exact" | "stem_exact" | "fuzzy" | "none"
    confidence: float       = 0.0

    @property
    def mapped(self) -> bool:
        return self.concept is not None

    def to_dict(self) -> dict:
        return {
            "row_idx": self.row_idx,
            "label": self.label,
            "norm": self.norm,
            "value": self.value,
            "kind": self.kind,
            "concept": self.concept,
            "asc_primary": self.asc_primary,
            "asc_refs": self.asc_refs,
            "asc_title": self.asc_title,
            "section": self.section,
            "strategy": self.strategy,
            "confidence": self.confidence,
            "mapped": self.mapped,
        }


@dataclass
class MappedStatement:
    company: Optional[str]
    ticker: Optional[str]
    statement_type: str         # "balance_sheet" | "income_statement" | "cash_flow" | "unknown"
    period: Optional[str]       # "YYYY-MM-DD" or "YYYY" or None
    rows: List[MappedRow]       = field(default_factory=list)

    # aggregate stats (computed in map_statement)
    n_valued_rows: int          = 0
    n_mapped: int               = 0
    coverage: float             = 0.0  # n_mapped / n_valued_rows

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "ticker": self.ticker,
            "statement_type": self.statement_type,
            "period": self.period,
            "n_valued_rows": self.n_valued_rows,
            "n_mapped": self.n_mapped,
            "coverage": round(self.coverage, 4),
            "rows": [r.to_dict() for r in self.rows],
        }


# ── main entry point ──────────────────────────────────────────────────────────
def map_statement(item: dict) -> MappedStatement:
    """Map an AuditBench item to a MappedStatement.

    item dict schema (AuditBench unified format from parser.py):
      table         : str   — [row n] formatted financial statement
      company       : str   — company name (may be missing on error splits)
      sheet_type    : str   — e.g. "Consolidated statments of balance sheet"
      transaction_data: str — unused here; passed through for downstream stages

    For single/multi error splits the company name is embedded in the table
    header ([Tab] line); we extract it as a best-effort fallback.
    """
    table_str   = item.get("table", item.get("Table", ""))
    company_raw = (item.get("company") or item.get("Company") or
                   _extract_company_from_table(table_str) or "")
    sheet_type  = item.get("sheet_type", item.get("Sheet_type", ""))

    ticker      = _TICKERS.get(company_raw)
    stmt_type   = infer_statement_type(sheet_type, table_str)
    period      = parse_period(table_str)

    # Parse table using Daksh's existing parser
    try:
        df = build_table(table_str)
    except Exception as exc:
        return MappedStatement(
            company=company_raw, ticker=ticker,
            statement_type=stmt_type, period=period,
        )

    mapped_rows: List[MappedRow] = []

    for row in rows_of(df):
        entry, strategy, conf = match_concept(row.norm, stmt_type)

        mr = MappedRow(
            row_idx=row.idx,
            label=row.label,
            norm=row.norm,
            value=row.value,
            kind=row.kind,
        )

        if entry:
            asc_refs = entry.get("asc_refs", [])
            topic = asc_refs[0].split("-")[0] if asc_refs else ""
            mr.concept     = entry["concept"]
            mr.asc_primary = entry.get("asc_primary")
            mr.asc_refs    = asc_refs
            mr.asc_title   = _ASC_TITLES.get(topic)
            mr.section     = entry.get("section")
            mr.strategy    = strategy
            mr.confidence  = conf

        mapped_rows.append(mr)

    # Stats on valued rows only (headers carry no financial value)
    valued = [r for r in mapped_rows if r.value is not None]
    n_valued = len(valued)
    n_mapped = sum(1 for r in valued if r.mapped)
    coverage = (n_mapped / n_valued) if n_valued else 0.0

    return MappedStatement(
        company=company_raw,
        ticker=ticker,
        statement_type=stmt_type,
        period=period,
        rows=mapped_rows,
        n_valued_rows=n_valued,
        n_mapped=n_mapped,
        coverage=coverage,
    )


def get_citation_for_error(error_type: str, mapped_row: Optional[MappedRow] = None,
                           ) -> Tuple[Optional[str], List[str]]:
    """Return (asc_primary, asc_refs) for a given error type and broken row.

    Priority:
      1. Row-level concept entry (from map_statement) — most specific
      2. Error-type fallback (from _error_type_asc in xbrl_concept_map.json)
      3. None
    This is the function Stage 2 calls to get a citation without hallucination.
    """
    # Row-level: prefer the concept's ASC if available
    if mapped_row and mapped_row.mapped:
        return mapped_row.asc_primary, mapped_row.asc_refs

    # Error-type fallback
    norm_type = error_type.lower().strip()
    fallback = _ERROR_ASC.get(norm_type)
    if fallback:
        return fallback.get("asc_primary"), fallback.get("asc_refs", [])

    return None, []


# ── helpers ───────────────────────────────────────────────────────────────────
def _extract_company_from_table(table_str: str) -> Optional[str]:
    """Pull company name from [Tab] Consolidated ... from <Company> line."""
    m = re.search(r'from\s+([A-Z][^[\n\r]+?)(?:\s+\[|\s*$)',
                  table_str[:300], re.IGNORECASE)
    return m.group(1).strip() if m else None


# ── CLI demo ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from parser import load_correct

    items = load_correct(seed=42, n=5)
    print(f"Demo: mapping {len(items)} sample items\n")

    for i, item in enumerate(items):
        ms = map_statement(item)
        print(f"[{i}] {ms.company} | {ms.statement_type} | {ms.period}")
        print(f"     Coverage: {ms.n_mapped}/{ms.n_valued_rows} rows = {ms.coverage:.1%}")
        # show first 3 mapped valued rows
        shown = 0
        for r in ms.rows:
            if r.value is not None and r.mapped:
                print(f"     row {r.row_idx:2d}: {r.label[:40]:40s} → {r.concept}")
                shown += 1
                if shown >= 3:
                    break
        # show up to 2 unmapped valued rows
        shown = 0
        for r in ms.rows:
            if r.value is not None and not r.mapped:
                print(f"     row {r.row_idx:2d}: {r.label[:40]:40s} → [UNMAPPED]")
                shown += 1
                if shown >= 2:
                    break
        print()
