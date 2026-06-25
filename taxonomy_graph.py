"""
TaxonomyGraph — Stage 1 · Arelle component.

Downloads (once) the FASB US-GAAP 2023 reference linkbase ZIP, extracts
the concept-reference linkbase XML, and traverses concept→reference arcs
to produce deterministic FASB ASC citations.

Cannot hallucinate: every citation is read verbatim from FASB's own
published taxonomy metadata.

Parent fallback: if a leaf concept has no direct reference arc, we
progressively strip trailing CamelCase tokens and retry, so the nearest
ancestor concept that carries a citation is returned instead.

Disk cache: the raw XML is written to .cache/us-gaap-ref-2023.xml on
first load; subsequent imports are instant and require no network.

Usage (standalone):
    from taxonomy_graph import TaxonomyGraph
    g = TaxonomyGraph()
    print(g.get_fasb_citation("CashAndCashEquivalentsAtCarryingValue"))
    # → "FASB ASC 230-10-45-5"  (or similar)

Handoff note for stage1_arelle.py:
    Use get_fasb_citation_detail(concept_id) to obtain the structured dict
    {"asc_primary", "asc_refs", "source", "matched_concept"} consumed by
    the Stage 1 enrichment layer.
"""

from __future__ import annotations

import io
import os
import re
import urllib.request
import zipfile
from typing import Dict, List, Optional

_HERE       = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR  = os.path.join(_HERE, ".cache")
_CACHE_XML  = os.path.join(_CACHE_DIR, "us-gaap-ref-2023.xml")

_TAXONOMY_ZIP_URL = "https://xbrl.fasb.org/us-gaap/2023/us-gaap-2023.zip"
_REF_FILE_IN_ZIP  = "us-gaap-2023/elts/us-gaap-ref-2023.xml"

# Split "CashAndCashEquivalentsAtCarryingValue" into component words
_CAMEL_RE = re.compile(r"[A-Z][a-z0-9]*")


# ── parent-concept candidate generation ───────────────────────────────────────

def _camel_words(concept_id: str) -> List[str]:
    return _CAMEL_RE.findall(concept_id)


def _parent_candidates(concept_id: str) -> List[str]:
    """Progressively shorter parent concept names by stripping trailing words.

    Example:
        "CashAndCashEquivalentsAtCarryingValue"
        → ["CashAndCashEquivalentsAtCarrying",
           "CashAndCashEquivalentsAt",
           "CashAndCashEquivalents",
           "CashAndCash",
           "Cash"]
    """
    words = _camel_words(concept_id)
    return ["".join(words[:n]) for n in range(len(words) - 1, 0, -1)]


# ── main class ────────────────────────────────────────────────────────────────

class TaxonomyGraph:
    """Lazy-loading US-GAAP reference linkbase traverser.

    The taxonomy XML is loaded once (from disk cache or network) and kept
    in memory for the lifetime of the instance.  All public methods are
    read-only after loading, so the same instance can be shared across the
    entire eval run.
    """

    def __init__(self, cache_path: str = _CACHE_XML) -> None:
        self._cache_path   = cache_path
        self._xml_content: Optional[str] = None
        self._available    = False   # set True once XML is loaded

    # ── loading ───────────────────────────────────────────────────────────────

    def _load_taxonomy(self) -> None:
        """Load XML from disk cache, or download + cache from FASB (once)."""
        if self._xml_content is not None:
            return

        # Fast path: disk cache already exists
        if os.path.isfile(self._cache_path):
            try:
                with open(self._cache_path, encoding="utf-8") as f:
                    self._xml_content = f.read()
                self._available = True
                return
            except OSError:
                pass  # fall through to download

        # Network download
        print("Downloading US-GAAP 2023 taxonomy reference linkbase (one-time, ~100 MB)…")
        headers = {
            "User-Agent": "AuditBench-Research/1.0 (academic; contact: research@example.com)"
        }
        try:
            req = urllib.request.Request(_TAXONOMY_ZIP_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read()
        except Exception as exc:
            print(f"  [TaxonomyGraph] Download failed: {exc}")
            print("  Stage 1 will fall back to static xbrl_concept_map.json citations.")
            self._xml_content = ""
            self._available   = False
            return

        # Extract just the reference linkbase from the zip
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                # Flexible: find the ref file regardless of top-level folder name
                ref_name = _REF_FILE_IN_ZIP
                if ref_name not in z.namelist():
                    candidates = [n for n in z.namelist() if n.endswith("us-gaap-ref-2023.xml")]
                    if not candidates:
                        raise KeyError(f"{ref_name!r} not found in ZIP")
                    ref_name = candidates[0]
                xml = z.read(ref_name).decode("utf-8")
        except Exception as exc:
            print(f"  [TaxonomyGraph] ZIP extraction failed: {exc}")
            self._xml_content = ""
            self._available   = False
            return

        # Persist to disk cache
        os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                f.write(xml)
        except OSError:
            pass  # cache write failure is non-fatal

        self._xml_content = xml
        self._available   = True
        print(f"  Taxonomy loaded ({len(xml):,} chars).  Cached to {self._cache_path}")

    @property
    def available(self) -> bool:
        """True after a successful load (cache hit or download)."""
        self._load_taxonomy()
        return self._available

    # ── internal arc + reference element parsing ──────────────────────────────

    def _refs_for_concept(self, concept_id: str) -> List[str]:
        """Return all xlink:to reference-element labels for `concept_id`.

        Scans every <link:referenceArc .../> element and collects those
        whose xlink:from attribute equals "loc_<concept_id>".  Attribute
        order within the element is not assumed.
        """
        from_label = f"loc_{concept_id}"
        arc_re     = re.compile(r"<link:referenceArc\b[^>]*/?>", re.DOTALL)
        result: List[str] = []
        for m in arc_re.finditer(self._xml_content):
            tag = m.group(0)
            # Use string-in-string for the from-label (faster than regex on
            # the whole file for per-arc checks)
            if (f'xlink:from="{from_label}"' not in tag and
                    f"xlink:from='{from_label}'" not in tag):
                continue
            to_m = re.search(r'xlink:to=["\']([^"\']+)["\']', tag)
            if to_m:
                result.append(to_m.group(1))
        return result

    def _parse_ref_element(self, ref_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Find <link:reference xlink:label="ref_id"> and parse its FASB fields.

        Returns a dict with keys {publisher, topic, subtopic, section, paragraph}
        or None if the element is absent or belongs to a non-FASB publisher.
        """
        pat = re.compile(
            r"<link:reference\b[^>]*xlink:label=[\"']"
            + re.escape(ref_id)
            + r"[\"'][^>]*>.*?</link:reference>",
            re.DOTALL,
        )
        m = pat.search(self._xml_content)
        if not m:
            return None
        ref_text = m.group(0)

        def _val(tag_name: str) -> Optional[str]:
            """Extract text of <*:tag_name> regardless of namespace prefix."""
            hit = re.search(
                r"<(?:[a-z][a-z0-9-]*:)?"
                + re.escape(tag_name)
                + r"\b[^>]*>([^<]+)</(?:[a-z][a-z0-9-]*:)?"
                + re.escape(tag_name)
                + r">",
                ref_text,
            )
            return hit.group(1).strip() if hit else None

        pub = _val("Publisher")
        if pub != "FASB":
            return None

        return {
            "publisher": pub,
            "topic":     _val("Topic"),
            "subtopic":  _val("SubTopic"),
            "section":   _val("Section"),
            "paragraph": _val("Paragraph"),
        }

    @staticmethod
    def _build_citation(parts: Dict[str, Optional[str]]) -> Optional[str]:
        """Assemble 'FASB ASC T-ST-S-P' from parsed parts, omitting None tail."""
        t  = parts.get("topic")
        st = parts.get("subtopic")
        s  = parts.get("section")
        p  = parts.get("paragraph")
        if not t:
            return None
        components = [c for c in [t, st, s, p] if c]
        return "FASB ASC " + "-".join(components)

    def _lookup_one(self, concept_id: str) -> Optional[str]:
        """Direct lookup: returns the most-specific FASB citation for the concept,
        or None when no FASB reference arc exists for it."""
        ref_ids = self._refs_for_concept(concept_id)
        best: Optional[str] = None
        for ref_id in ref_ids:
            parts = self._parse_ref_element(ref_id)
            if parts is None:
                continue
            citation = self._build_citation(parts)
            if citation and (best is None or len(citation) > len(best)):
                best = citation
        return best

    # ── public API ────────────────────────────────────────────────────────────

    def get_fasb_citation(self, concept_id: str) -> Optional[str]:
        """Return a FASB ASC citation string for `concept_id`, or None.

        Tries the concept directly, then progressively shorter parent names
        (parent fallback) until a citation is found or candidates are exhausted.
        """
        self._load_taxonomy()
        if not self._available:
            return None

        citation = self._lookup_one(concept_id)
        if citation:
            return citation

        for parent in _parent_candidates(concept_id):
            citation = self._lookup_one(parent)
            if citation:
                return citation

        return None

    def get_fasb_citation_detail(self, concept_id: str) -> Dict:
        """Structured version of get_fasb_citation.

        Returns:
            {
                "asc_primary":      str | None,   # e.g. "230-10-45-5"
                "asc_refs":         list[str],     # topic-subtopic-section
                "source":           str,           # "taxonomy" | "parent_fallback" | "none"
                "matched_concept":  str | None,    # which concept produced the hit
            }
        """
        self._load_taxonomy()
        empty = {
            "asc_primary": None, "asc_refs": [],
            "source": "none",    "matched_concept": None,
        }
        if not self._available:
            return empty

        def _to_detail(citation: str, source: str, matched: str) -> Dict:
            asc = citation.replace("FASB ASC ", "")
            parts = asc.split("-")
            section_ref = "-".join(parts[:3]) if len(parts) >= 3 else asc
            return {
                "asc_primary": asc,
                "asc_refs":    [section_ref],
                "source":      source,
                "matched_concept": matched,
            }

        # Direct
        citation = self._lookup_one(concept_id)
        if citation:
            return _to_detail(citation, "taxonomy", concept_id)

        # Parent fallback
        for parent in _parent_candidates(concept_id):
            citation = self._lookup_one(parent)
            if citation:
                return _to_detail(citation, "parent_fallback", parent)

        return empty


# ── CLI smoke test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    graph = TaxonomyGraph()
    test_concepts = [
        "CashAndCashEquivalentsAtCarryingValue",
        "Assets",
        "Liabilities",
        "StockholdersEquity",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "NetIncomeLoss",
        "AccountsReceivableNetCurrent",
        "InventoryNet",
    ]
    print(f"Taxonomy available: {graph.available}\n")
    for concept in test_concepts:
        result = graph.get_fasb_citation_detail(concept)
        src   = result["source"]
        asc   = result["asc_primary"] or "[none]"
        match = result["matched_concept"] or ""
        suffix = f"  (via parent: {match})" if src == "parent_fallback" else ""
        print(f"  us-gaap:{concept}")
        print(f"    → {asc}  [{src}]{suffix}")
