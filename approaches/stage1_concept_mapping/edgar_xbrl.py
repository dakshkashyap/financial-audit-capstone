"""
edgar_xbrl.py — live SEC EDGAR XBRL concept resolver (Strategy 3 from the design
doc; the FinAuditing FinSM tie-in).

Idea (the novel, reproducible mapping route)
--------------------------------------------
Every AuditBench company already filed XBRL with the SEC, where each line item is
tagged with its us-gaap concept *by the filer's own accountants*. Recovering that
filing collapses the FinSM mapping problem (text label → concept over an
18k-concept space, where the best LLMs score 9–13%) into a lookup over the ~300–600
concepts the company actually uses.

Pipeline per company:
  company name → ticker (company_tickers.json) → CIK (SEC ticker file)
              → companyfacts JSON (cached) → {standard label → us-gaap concept}
A row label is then matched within *that company's* concept set (exact → fuzzy),
so the candidate space is tiny and filer-authoritative.

Honesty / limits
----------------
  * AuditBench error splits strip the company name → this route only fires where a
    company is recoverable (the whole `correct` split; some error items).
  * AuditBench tables use the companies' *custom* presentation labels; companyfacts
    exposes the *standard* us-gaap label. So custom↔standard still needs fuzzy
    matching — but over ~500 concepts, not 18,000.
  * Network + disk cache under .cache/edgar/. Fully offline after first fetch;
    degrades gracefully (returns None) when offline.
"""
from __future__ import annotations

import difflib
import json
import os
import time
import urllib.request
from typing import Dict, Optional, Tuple

from core.stage0_common import norm_label

from core.paths import CACHE_DIR as _REPO_CACHE

_HERE      = os.path.dirname(os.path.abspath(__file__))   # package-local assets
_CACHE_DIR = os.path.join(_REPO_CACHE, "edgar")
_TICKERMAP = os.path.join(_HERE, "company_tickers.json")
_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_UA = {"User-Agent": "IntelliAudit Research (SFU capstone; research@sfu.ca)"}

_FUZZY_CUTOFF = 0.86   # strict — these are matches *within one company's concepts*
_STOP = {"and", "of", "the", "in", "for", "to", "a", "net", "total", "other"}


def _tokens(norm: str) -> frozenset:
    return frozenset(t for t in norm.split() if t not in _STOP)


# ── low-level cached fetch ────────────────────────────────────────────────────
def _get_json(url: str, cache_path: str, ttl_ok: bool = True) -> Optional[dict]:
    if ttl_ok and os.path.isfile(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        time.sleep(0.12)   # be polite to SEC (<10 req/s)
        return data
    except Exception:
        return None


# ── ticker → CIK ──────────────────────────────────────────────────────────────
class _Resolver:
    """Resolves an AuditBench company name to a 10-digit CIK."""
    def __init__(self) -> None:
        self._name2ticker: Dict[str, str] = {}
        if os.path.isfile(_TICKERMAP):
            with open(_TICKERMAP, encoding="utf-8") as f:
                self._name2ticker = {k: v for k, v in json.load(f).items()
                                     if not k.startswith("_")}
        self._ticker2cik: Dict[str, str] = {}
        self._title2cik:  Dict[str, str] = {}
        self._loaded = False

    def _load_sec(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        data = _get_json(_SEC_TICKERS_URL,
                         os.path.join(_CACHE_DIR, "sec_company_tickers.json"))
        if not data:
            return
        for row in data.values():
            cik = str(row["cik_str"]).zfill(10)
            self._ticker2cik[row["ticker"].upper()] = cik
            self._title2cik[norm_label(row["title"])] = cik

    def cik(self, company_name: str) -> Optional[str]:
        if not company_name:
            return None
        self._load_sec()
        # 1. repo hand-map: name → ticker → CIK
        tk = self._name2ticker.get(company_name)
        if tk and tk.upper() in self._ticker2cik:
            return self._ticker2cik[tk.upper()]
        # 2. direct SEC title match (exact, then fuzzy over titles)
        nl = norm_label(company_name)
        if nl in self._title2cik:
            return self._title2cik[nl]
        if self._title2cik:
            hit = difflib.get_close_matches(nl, self._title2cik.keys(), n=1, cutoff=0.92)
            if hit:
                return self._title2cik[hit[0]]
        return None


_RESOLVER: Optional[_Resolver] = None
def _resolver() -> _Resolver:
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = _Resolver()
    return _RESOLVER


# ── company concept index (cached per CIK) ────────────────────────────────────
_CONCEPT_INDEX: Dict[str, Dict[str, str]] = {}   # cik → {norm label → concept}


def _concept_index(cik: str) -> Dict[str, str]:
    if cik in _CONCEPT_INDEX:
        return _CONCEPT_INDEX[cik]
    facts = _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                      os.path.join(_CACHE_DIR, f"facts_{cik}.json"))
    index: Dict[str, str] = {}
    if facts:
        for concept, body in facts.get("facts", {}).get("us-gaap", {}).items():
            label = body.get("label") or ""
            if label:
                index.setdefault(norm_label(label), f"us-gaap:{concept}")
    _CONCEPT_INDEX[cik] = index
    return index


# ── public API ────────────────────────────────────────────────────────────────
def map_label(company_name: str, row_norm: str
              ) -> Tuple[Optional[str], str, float]:
    """Map a normalized row label to the filer's own us-gaap concept.

    Returns (concept | None, strategy, confidence).
    strategy ∈ {"edgar_xbrl_exact", "edgar_xbrl_fuzzy", "none"}.
    """
    cik = _resolver().cik(company_name)
    if not cik:
        return None, "none", 0.0
    index = _concept_index(cik)
    if not index:
        return None, "none", 0.0
    if row_norm in index:
        return index[row_norm], "edgar_xbrl_exact", 1.0

    # Token-containment: the standard us-gaap label usually *extends* the row
    # label with qualifiers ("cash and cash equivalents" → "... at carrying
    # value"). So accept a concept whose token set contains all of the row's
    # significant tokens, preferring the tightest (highest Jaccard) such label.
    rt = _tokens(row_norm)
    if len(rt) >= 2:
        best_concept, best_jac = None, 0.0
        for label, concept in index.items():
            lt = _tokens(label)
            if rt <= lt:                                   # full containment
                jac = len(rt) / len(rt | lt)
                if jac > best_jac:
                    best_jac, best_concept = jac, concept
        if best_concept and best_jac >= 0.34:
            return best_concept, "edgar_xbrl_token", round(best_jac, 3)

    # Last resort: strict character-level fuzzy within this company's concepts.
    hit = difflib.get_close_matches(row_norm, index.keys(), n=1, cutoff=_FUZZY_CUTOFF)
    if hit:
        score = difflib.SequenceMatcher(None, row_norm, hit[0]).ratio()
        return index[hit[0]], "edgar_xbrl_fuzzy", round(score, 3)
    return None, "none", 0.0


def available() -> bool:
    """True if the SEC ticker file is reachable/cached (so the route can fire)."""
    r = _resolver()
    r._load_sec()
    return bool(r._ticker2cik)


# ── CLI smoke test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [("Apple", "cash and cash equivalents"),
             ("Coca-Cola", "inventories"),
             ("Home Depot", "merchandise inventories"),
             ("FedEx", "accounts receivable")]
    print("SEC reachable:", available())
    for co, lbl in tests:
        concept, strat, conf = map_label(co, norm_label(lbl))
        print(f"  {co:14s} | {lbl:30s} → {concept}  [{strat} {conf}]")
