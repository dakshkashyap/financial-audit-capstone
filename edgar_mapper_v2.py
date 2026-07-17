"""
EDGAR Mapper v2 — Improved concept mapping for IntelliAudit Stage 1.

Replaces the single dictionary/fuzzy layer with a four-layer cascade.
Each layer only runs when the layer above it fails to find a match.

  Layer 1: Dictionary + stem + fuzzy (v1 logic, ~77.9% coverage)
  Layer 2: Live SEC EDGAR XBRL lookup (company's own filed tags)
  Layer 3: Embedding semantic similarity (sentence-transformers)
  Layer 4: LLM constrained selection from top-5 candidates (last resort)

Why each layer exists:
  Layer 1 is fast and precise — it handles the ~78% of labels that are
  standard enough to appear in a curated dictionary.

  Layer 2 gives ground truth for known companies: every S&P 500 company
  files their XBRL tags with the SEC. Recovering their own tag is better
  than any model guess. Only works when the company name is available
  (stripped on error splits by the AuditBench injector).

  Layer 3 closes the 22% gap by matching on meaning rather than spelling.
  "Purchased transportation" does not look like "FreightCosts" but a
  sentence embedding sees them as semantically close. This is the approach
  FinAuditing showed was necessary to reach the 18,000-concept space.

  Layer 4 adds LLM reasoning over the top-5 embedding candidates. The
  model cannot invent a concept — it must pick from the shortlist. This
  is the "constrained oracle" pattern from VERAFI and the design doc.

Drop-in replacement for edgar_mapper.py:
  from edgar_mapper_v2 import map_statement, MappedRow, MappedStatement

Optional heavy dependencies (layers 3 and 4 degrade gracefully without them):
  pip install sentence-transformers       # Layer 3
  pip install openai                      # Layer 4 (uses OPENAI_API_KEY)
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── reuse Daksh's shared layer ────────────────────────────────────────────────
from stage0_common import build_table, norm_label, rows_of

logger = logging.getLogger(__name__)

# ── resource paths ────────────────────────────────────────────────────────────
_HERE = os.path.dirname(__file__)
_CONCEPT_MAP_PATH = os.path.join(_HERE, "xbrl_concept_map.json")
_TICKERS_PATH = os.path.join(_HERE, "company_tickers.json")

# ── load resources once ───────────────────────────────────────────────────────
with open(_CONCEPT_MAP_PATH, encoding="utf-8") as _f:
    _RAW_MAP = json.load(_f)

with open(_TICKERS_PATH, encoding="utf-8") as _f:
    _TICKERS: Dict[str, str] = {
        k: v for k, v in json.load(_f).items() if not k.startswith("_")
    }

_STMT_MAPS: Dict[str, Dict] = {
    k: v for k, v in _RAW_MAP.items()
    if not k.startswith("_") and isinstance(v, dict)
}
_ERROR_ASC: Dict[str, dict] = _RAW_MAP.get("_error_type_asc", {})
_ASC_TITLES: Dict[str, str] = _RAW_MAP.get("_asc_titles", {})

# All (normalized label → entry) pairs from the concept map — used as the
# embedding corpus in Layer 3.
_CORPUS_LABELS: List[str] = []
_CORPUS_ENTRIES: List[dict] = []
for _stype, _cmap in _STMT_MAPS.items():
    for _label, _entry in _cmap.items():
        _CORPUS_LABELS.append(_label)
        _CORPUS_ENTRIES.append(_entry)

FUZZY_CUTOFF = 0.75     # Layer 1 fuzzy threshold
EMBED_CUTOFF = 0.55     # Layer 3 cosine similarity threshold (0–1)
EMBED_TOP_K  = 5        # candidates passed to Layer 4 LLM

# ── lazy singletons ───────────────────────────────────────────────────────────
_embed_model = None       # sentence-transformers model
_corpus_vecs = None       # pre-computed corpus embeddings


# ══════════════════════════════════════════════════════════════════════════════
# DATACLASSES  (same schema as v1 — fully backward compatible)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MappedRow:
    row_idx: int
    label: str
    norm: str
    value: Optional[float]
    kind: str

    concept: Optional[str]    = None
    asc_primary: Optional[str] = None
    asc_refs: List[str]       = field(default_factory=list)
    asc_title: Optional[str]  = None
    section: Optional[str]    = None
    strategy: str             = "none"   # exact | stem_exact | fuzzy | edgar_xbrl
                                          # embedding | llm_constrained | none
    confidence: float         = 0.0

    @property
    def mapped(self) -> bool:
        return self.concept is not None

    def to_dict(self) -> dict:
        return {
            "row_idx": self.row_idx, "label": self.label, "norm": self.norm,
            "value": self.value, "kind": self.kind, "concept": self.concept,
            "asc_primary": self.asc_primary, "asc_refs": self.asc_refs,
            "asc_title": self.asc_title, "section": self.section,
            "strategy": self.strategy, "confidence": self.confidence,
            "mapped": self.mapped,
        }


@dataclass
class MappedStatement:
    company: Optional[str]
    ticker: Optional[str]
    statement_type: str
    period: Optional[str]
    rows: List[MappedRow]  = field(default_factory=list)

    n_valued_rows: int     = 0
    n_mapped: int          = 0
    coverage: float        = 0.0

    def to_dict(self) -> dict:
        return {
            "company": self.company, "ticker": self.ticker,
            "statement_type": self.statement_type, "period": self.period,
            "n_valued_rows": self.n_valued_rows, "n_mapped": self.n_mapped,
            "coverage": round(self.coverage, 4),
            "rows": [r.to_dict() for r in self.rows],
        }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — Dictionary + stem + fuzzy  (v1 logic, unchanged)
# ══════════════════════════════════════════════════════════════════════════════

_STMT_KEYWORDS = {
    "balance_sheet":    ["balance sheet", "balance", "financial position"],
    "income_statement": ["income", "earnings", "operations", "profit", "loss",
                         "comprehensive income"],
    "cash_flow":        ["cash flow", "cash flows", "cash and cash equiv"],
}

_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05",     "june": "06",     "july": "07",  "august": "08",
    "september": "09","october": "10", "november": "11","december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}


def infer_statement_type(sheet_type: str, table: str = "") -> str:
    combined = (sheet_type + " " + table[:300]).lower()
    for stype, keywords in _STMT_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return stype
    tab_m = re.search(r'\[Tab\]\s*(.*?)(?:\[SEP\]|$)', table[:400], re.IGNORECASE)
    if tab_m:
        result = infer_statement_type(tab_m.group(1))
        if result != "unknown":
            return result
    row_labels = re.findall(r'\[row\s*\d+\]\s*:\s*([^|[]+?)(?:\s*\||\s*\[SEP\])', table)
    row_text = " ".join(row_labels[:10]).lower()
    bs_signals = ["assets","liabilities","equity","stockholders","shareholders",
                  "current assets","current liabilities","retained earnings",
                  "accounts payable","accounts receivable"]
    cf_signals = ["operating activities","investing activities","financing activities",
                  "cash flows","capital expenditures","short-term borrowings"]
    is_signals = ["revenue","revenues","net sales","cost of","gross profit",
                  "gross margin","operating income","net income","net loss",
                  "operating expenses","selling","research and development"]
    bs  = sum(1 for s in bs_signals if s in row_text)
    cf  = sum(1 for s in cf_signals if s in row_text)
    iis = sum(1 for s in is_signals if s in row_text)
    best = max(bs, cf, iis)
    if best == 0:
        return "unknown"
    if bs == best:   return "balance_sheet"
    if cf == best:   return "cash_flow"
    return "income_statement"


def parse_period(table_str: str) -> Optional[str]:
    m = re.search(r'\[Time\]\s*:\s*([^\[]+)', table_str, re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).strip().rstrip('[SEP]').strip()
    year_m = re.search(r'\b(20\d{2}|19\d{2})\b', raw)
    year = year_m.group(1) if year_m else None
    full_m = re.search(r'(\w+)\s+(\d{1,2}),?\s*(20\d{2}|19\d{2})', raw, re.IGNORECASE)
    if full_m:
        month = _MONTH_MAP.get(full_m.group(1).lower())
        if month:
            return f"{full_m.group(3)}-{month}-{full_m.group(2).zfill(2)}"
    q_m = re.search(r'Q(\d)\s*(20\d{2})', raw, re.IGNORECASE)
    if q_m:
        return f"{q_m.group(2)}-{{'1':'03','2':'06','3':'09','4':'12'}.get(q_m.group(1),'12')}"
    return year


def _exact_lookup(norm: str, stype: str) -> Optional[dict]:
    if stype in _STMT_MAPS and norm in _STMT_MAPS[stype]:
        return _STMT_MAPS[stype][norm]
    for other, cmap in _STMT_MAPS.items():
        if other != stype and norm in cmap:
            return cmap[norm]
    return None


def _stem_variants(norm: str) -> List[str]:
    variants = []
    if norm.startswith("total "): variants.append(norm[6:])
    if norm.startswith("net "):   variants.append(norm[4:])
    if " and " in norm:
        parts = norm.split(" and ", 1)
        variants.extend(parts)
    words = norm.split()
    if len(words) > 2: variants.append(" ".join(words[-2:]))
    if len(words) > 3: variants.append(" ".join(words[-3:]))
    return variants


def _fuzzy_lookup(norm: str, stype: str,
                  cutoff: float = FUZZY_CUTOFF) -> Tuple[Optional[dict], float]:
    candidates: List[Tuple[str, dict]] = []
    priority = [stype] + [s for s in _STMT_MAPS if s != stype]
    for st in priority:
        if st in _STMT_MAPS:
            candidates.extend(_STMT_MAPS[st].items())
    best_key, best_score = None, 0.0
    for key, _ in candidates:
        score = difflib.SequenceMatcher(None, norm, key).ratio()
        if score > best_score:
            best_score, best_key = score, key
    if best_score >= cutoff and best_key is not None:
        for st in priority:
            if st in _STMT_MAPS and best_key in _STMT_MAPS[st]:
                return _STMT_MAPS[st][best_key], best_score
    return None, best_score


def _layer1(norm: str, stype: str) -> Tuple[Optional[dict], str, float]:
    """Dictionary + stem + fuzzy — the existing v1 approach."""
    entry = _exact_lookup(norm, stype)
    if entry:
        return entry, "exact", 1.0
    for variant in _stem_variants(norm):
        entry = _exact_lookup(variant, stype)
        if entry:
            return entry, "stem_exact", 0.90
    entry, score = _fuzzy_lookup(norm, stype)
    if entry:
        return entry, "fuzzy", round(score, 3)
    return None, "none", 0.0


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Live SEC EDGAR XBRL lookup
# ══════════════════════════════════════════════════════════════════════════════

# Cache: ticker → {concept_label: us-gaap:ConceptName}
_edgar_cache: Dict[str, Dict[str, str]] = {}


def _get_cik(ticker: str) -> Optional[str]:
    """Resolve a ticker symbol to a zero-padded CIK using SEC's public JSON."""
    try:
        import urllib.request
        url = "https://data.sec.gov/files/company_tickers.json"
        req = urllib.request.Request(url, headers={"User-Agent": "IntelliAudit research@sfu.ca"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
    except Exception as exc:
        logger.debug("CIK lookup failed for %s: %s", ticker, exc)
    return None


def _fetch_companyfacts(cik: str) -> Dict[str, str]:
    """Fetch all us-gaap concept labels used by a filer from SEC companyfacts.

    Returns {normalized_label: "us-gaap:ConceptName"} from the filer's own filings.
    """
    try:
        import urllib.request
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "IntelliAudit research@sfu.ca"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        facts = data.get("facts", {}).get("us-gaap", {})
        result: Dict[str, str] = {}
        for concept_name, concept_data in facts.items():
            label = concept_data.get("label", concept_name)
            result[norm_label(label)] = f"us-gaap:{concept_name}"
        return result
    except Exception as exc:
        logger.debug("companyfacts fetch failed for CIK %s: %s", cik, exc)
    return {}


def _layer2(norm: str, ticker: Optional[str]) -> Tuple[Optional[dict], str, float]:
    """SEC EDGAR lookup — returns the company's own filed concept if available."""
    if not ticker:
        return None, "none", 0.0

    # Load (and cache) this company's concept map from SEC
    if ticker not in _edgar_cache:
        cik = _get_cik(ticker)
        _edgar_cache[ticker] = _fetch_companyfacts(cik) if cik else {}

    company_concepts = _edgar_cache[ticker]
    if not company_concepts:
        return None, "none", 0.0

    # Try exact match first
    if norm in company_concepts:
        concept = company_concepts[norm]
        # Build a minimal entry compatible with MappedRow schema
        entry = {
            "concept": concept,
            "asc_primary": None,  # Stage 1 taxonomy graph will fill this in
            "asc_refs": [],
            "section": None,
        }
        return entry, "edgar_xbrl", 0.95

    # Try fuzzy match against the company's own label set (higher cutoff — these
    # are raw taxonomy labels which can be verbose)
    best_key, best_score = None, 0.0
    for label in company_concepts:
        score = difflib.SequenceMatcher(None, norm, label).ratio()
        if score > best_score:
            best_score, best_key = score, label
    if best_score >= 0.80 and best_key:
        concept = company_concepts[best_key]
        entry = {"concept": concept, "asc_primary": None, "asc_refs": [], "section": None}
        return entry, "edgar_xbrl_fuzzy", round(best_score, 3)

    return None, "none", 0.0


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — Embedding semantic similarity
# ══════════════════════════════════════════════════════════════════════════════

def _get_embed_model():
    """Lazy-load the sentence-transformers model (only once per process)."""
    global _embed_model, _corpus_vecs
    if _embed_model is not None:
        return _embed_model

    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        logger.warning(
            "sentence-transformers not installed. Layer 3 (embedding) disabled.\n"
            "  Install with: pip install sentence-transformers"
        )
        return None

    # bge-large-en is the FinAuditing/ICD-10 SOTA choice but requires ~1.3GB.
    # all-MiniLM-L6-v2 is 80MB and scores ~90% of bge quality — good default.
    model_name = os.environ.get("INTELLIAUDIT_EMBED_MODEL", "all-MiniLM-L6-v2")
    logger.info("Loading embedding model: %s", model_name)
    _embed_model = SentenceTransformer(model_name)

    # Pre-compute corpus embeddings (only done once)
    _corpus_vecs = _embed_model.encode(
        _CORPUS_LABELS, normalize_embeddings=True, show_progress_bar=False
    )
    logger.info("Corpus embedded: %d concepts", len(_CORPUS_LABELS))
    return _embed_model


def _layer3(norm: str, top_k: int = EMBED_TOP_K
            ) -> Tuple[Optional[dict], str, float, List[Tuple[str, dict, float]]]:
    """Embedding similarity against the full concept corpus.

    Returns:
      (best_entry, strategy, confidence, top_k_candidates)
      top_k_candidates is a list of (label, entry, score) for Layer 4.
    """
    model = _get_embed_model()
    if model is None:
        return None, "none", 0.0, []

    try:
        import numpy as np
        query_vec = model.encode([norm], normalize_embeddings=True)[0]
        scores = (_corpus_vecs @ query_vec).tolist()  # cosine similarity via dot on normed vecs

        # Top-k indices by score
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        candidates = [(
            _CORPUS_LABELS[i], _CORPUS_ENTRIES[i], round(score, 3)
        ) for i, score in ranked]

        best_label, best_entry, best_score = candidates[0]
        if best_score >= EMBED_CUTOFF:
            return best_entry, "embedding", best_score, candidates

        return None, "none", best_score, candidates
    except Exception as exc:
        logger.debug("Embedding lookup error: %s", exc)
        return None, "none", 0.0, []


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — LLM constrained selection (last resort)
# ══════════════════════════════════════════════════════════════════════════════

def _layer4(norm: str, stype: str,
            candidates: List[Tuple[str, dict, float]]) -> Tuple[Optional[dict], str, float]:
    """Ask the LLM to pick the best concept from the top-k embedding candidates.

    The model CANNOT invent a new concept — it must return one of the labels
    from the candidate list (VERAFI constrained-oracle pattern).
    If the API is unavailable or fails, returns None gracefully.
    """
    if not candidates:
        return None, "none", 0.0

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("No API key found — Layer 4 (LLM) skipped.")
        return None, "none", 0.0

    # Build the candidate menu
    menu_lines = []
    for i, (label, entry, score) in enumerate(candidates, 1):
        concept = entry.get("concept", "")
        menu_lines.append(f"  {i}. \"{label}\" → {concept}  (similarity: {score:.2f})")
    menu = "\n".join(menu_lines)

    prompt = (
        f"You are mapping a financial statement row label to a US-GAAP XBRL concept.\n\n"
        f"Row label: \"{norm}\"\n"
        f"Statement type: {stype}\n\n"
        f"Choose the best match from the following candidates (reply with the number only):\n"
        f"{menu}\n\n"
        f"If none of these are a good match, reply with 0.\n"
        f"Reply with a single digit and nothing else."
    )

    try:
        # Try OpenAI first, then Anthropic
        if os.environ.get("OPENAI_API_KEY"):
            import openai
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0,
            )
            choice_str = response.choices[0].message.content.strip()
        else:
            import anthropic
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-20240307",
                max_tokens=5,
                messages=[{"role": "user", "content": prompt}],
            )
            choice_str = response.content[0].text.strip()

        choice = int(choice_str)
        if 1 <= choice <= len(candidates):
            label, entry, score = candidates[choice - 1]
            return entry, "llm_constrained", score
    except Exception as exc:
        logger.debug("Layer 4 LLM call failed: %s", exc)

    return None, "none", 0.0


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CASCADE
# ══════════════════════════════════════════════════════════════════════════════

def match_concept_v2(
    norm: str,
    stype: str,
    ticker: Optional[str] = None,
    use_embedding: bool = True,
    use_llm: bool = False,      # off by default — costs money and time
) -> Tuple[Optional[dict], str, float]:
    """Four-layer cascade. Returns (entry, strategy, confidence).

    strategy ∈ {
      "exact", "stem_exact", "fuzzy",       # Layer 1
      "edgar_xbrl", "edgar_xbrl_fuzzy",     # Layer 2
      "embedding",                           # Layer 3
      "llm_constrained",                    # Layer 4
      "none"
    }
    """
    # Layer 1: dictionary
    entry, strategy, conf = _layer1(norm, stype)
    if entry:
        return entry, strategy, conf

    # Layer 2: SEC EDGAR filer tags (only when ticker is known)
    if ticker:
        entry, strategy, conf = _layer2(norm, ticker)
        if entry:
            return entry, strategy, conf

    # Layer 3: embedding similarity
    if use_embedding:
        entry, strategy, conf, top_k = _layer3(norm)
        if entry:
            return entry, strategy, conf

        # Layer 4: LLM over top-k candidates (if enabled and we have candidates)
        if use_llm and top_k:
            entry, strategy, conf = _layer4(norm, stype, top_k)
            if entry:
                return entry, strategy, conf

    return None, "none", 0.0


# ══════════════════════════════════════════════════════════════════════════════
# MAP STATEMENT  (same interface as v1)
# ══════════════════════════════════════════════════════════════════════════════

def map_statement(
    item: dict,
    use_embedding: bool = True,
    use_llm: bool = False,
) -> MappedStatement:
    """Map an AuditBench item to a MappedStatement using the four-layer cascade.

    Drop-in replacement for edgar_mapper.map_statement().
    """
    table_str   = item.get("table", item.get("Table", ""))
    company_raw = (item.get("company") or item.get("Company") or
                   _extract_company_from_table(table_str) or "")
    sheet_type  = item.get("sheet_type", item.get("Sheet_type", ""))

    ticker    = _TICKERS.get(company_raw)
    stmt_type = infer_statement_type(sheet_type, table_str)
    period    = parse_period(table_str)

    try:
        df = build_table(table_str)
    except Exception:
        return MappedStatement(
            company=company_raw, ticker=ticker,
            statement_type=stmt_type, period=period,
        )

    mapped_rows: List[MappedRow] = []
    for row in rows_of(df):
        entry, strategy, conf = match_concept_v2(
            row.norm, stmt_type, ticker=ticker,
            use_embedding=use_embedding, use_llm=use_llm,
        )
        mr = MappedRow(
            row_idx=row.idx, label=row.label, norm=row.norm,
            value=row.value, kind=row.kind,
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

    valued   = [r for r in mapped_rows if r.value is not None]
    n_valued = len(valued)
    n_mapped = sum(1 for r in valued if r.mapped)
    coverage = (n_mapped / n_valued) if n_valued else 0.0

    return MappedStatement(
        company=company_raw, ticker=ticker,
        statement_type=stmt_type, period=period,
        rows=mapped_rows, n_valued_rows=n_valued,
        n_mapped=n_mapped, coverage=coverage,
    )


def get_citation_for_error(
    error_type: str, mapped_row: Optional[MappedRow] = None
) -> Tuple[Optional[str], List[str]]:
    """Same interface as v1 — used by Stage 2 to get a grounded citation."""
    if mapped_row and mapped_row.mapped:
        return mapped_row.asc_primary, mapped_row.asc_refs
    fallback = _ERROR_ASC.get(error_type.lower().strip())
    if fallback:
        return fallback.get("asc_primary"), fallback.get("asc_refs", [])
    return None, []


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _extract_company_from_table(table_str: str) -> Optional[str]:
    m = re.search(r'from\s+([A-Z][^[\n\r]+?)(?:\s+\[|\s*$)', table_str[:300], re.IGNORECASE)
    return m.group(1).strip() if m else None


def coverage_report(statement: MappedStatement) -> str:
    """Human-readable coverage summary broken down by strategy."""
    from collections import Counter
    valued = [r for r in statement.rows if r.value is not None]
    by_strategy = Counter(r.strategy for r in valued)
    lines = [
        f"Company : {statement.company} ({statement.ticker})",
        f"Type    : {statement.statement_type}  Period: {statement.period}",
        f"Coverage: {statement.n_mapped}/{statement.n_valued_rows} = {statement.coverage:.1%}",
        "Strategy breakdown:",
    ]
    for strat in ["exact", "stem_exact", "fuzzy",
                  "edgar_xbrl", "edgar_xbrl_fuzzy",
                  "embedding", "llm_constrained", "none"]:
        count = by_strategy.get(strat, 0)
        if count:
            lines.append(f"  {strat:20s}: {count}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# CLI DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from parser import load_correct

    # Run with embeddings on, LLM off by default.
    # Set INTELLIAUDIT_USE_LLM=1 to enable Layer 4.
    use_llm = os.environ.get("INTELLIAUDIT_USE_LLM", "0") == "1"

    items = load_correct(seed=42, n=5)
    print(f"EDGAR Mapper v2 — demo on {len(items)} items\n")
    print(f"Layers: [1] dict  [2] SEC EDGAR  [3] embedding  [4] LLM={use_llm}\n")

    for i, item in enumerate(items):
        ms = map_statement(item, use_embedding=True, use_llm=use_llm)
        print(coverage_report(ms))
        # Show a few unmapped rows (these are what layers 2–4 are meant to catch)
        unmapped = [r for r in ms.rows if r.value is not None and not r.mapped]
        if unmapped:
            print(f"  Unmapped labels ({len(unmapped)}):")
            for r in unmapped[:4]:
                print(f"    - \"{r.label}\"")
        print()
