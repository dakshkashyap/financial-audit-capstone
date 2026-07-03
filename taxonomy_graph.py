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

# ASC industry topics (905–995) are specific to banks, insurers, real-estate,
# etc.  AuditBench tables are general-purpose S&P 500 statements, so a general
# topic is always the correct governing standard over an industry one.
_INDUSTRY_TOPIC_MIN = 900

# Reference-role priority: how authoritative each reference role is for
# locating the standard that governs a line item on the face of the
# financials.  Higher wins.  Roles appear as the last path segment of the
# xlink:role URI (e.g. ".../role/disclosureRef" -> "disclosureRef").
_ROLE_PRIORITY = {
    "presentationRef":   6,
    "disclosureRef":     5,
    "measurementRef":    4,
    "definitionRef":     3,
    "commonPracticeRef": 2,
    "exampleRef":        1,
    "legacyRef":         0,
}


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

        # ── in-memory indexes / memo caches (XML is immutable after load) ──
        self._indexed           = False
        self._arc_index: Dict[str, List[str]] = {}   # from_label -> [to_label]
        self._ref_index: Dict[str, str]        = {}   # ref_label  -> element text
        self._ref_parse_cache: Dict[str, Optional[Dict]] = {}  # ref_label -> parsed
        self._detail_cache:     Dict[str, Dict]          = {}  # concept   -> detail
        self._candidates_cache: Dict[str, List[Dict]]    = {}  # concept   -> candidates

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

    def _build_index(self) -> None:
        """Index the XML once: concept→reference arcs and label→reference element.

        The previous implementation re-scanned the entire ~30 MB linkbase for
        every concept lookup (O(arcs) per row), making a full-split eval take
        many minutes.  Building these two dicts a single time turns each
        subsequent lookup into an O(1) dict access.
        """
        if self._indexed:
            return
        xml = self._xml_content or ""

        # from_label ("loc_<Concept>") -> [reference-element labels]
        arc_index: Dict[str, List[str]] = {}
        for m in re.finditer(r"<link:referenceArc\b[^>]*/?>", xml):
            tag = m.group(0)
            fm = re.search(r'xlink:from=["\']([^"\']+)["\']', tag)
            tm = re.search(r'xlink:to=["\']([^"\']+)["\']', tag)
            if fm and tm:
                arc_index.setdefault(fm.group(1), []).append(tm.group(1))
        self._arc_index = arc_index

        # reference-element label -> full element text
        ref_index: Dict[str, str] = {}
        ref_re = re.compile(
            r"<link:reference\b[^>]*?xlink:label=[\"']([^\"']+)[\"'][^>]*>.*?</link:reference>",
            re.DOTALL,
        )
        for m in ref_re.finditer(xml):
            ref_index[m.group(1)] = m.group(0)
        self._ref_index = ref_index

        self._indexed = True

    def _refs_for_concept(self, concept_id: str) -> List[str]:
        """Return all xlink:to reference-element labels for `concept_id` (O(1))."""
        self._build_index()
        return self._arc_index.get(f"loc_{concept_id}", [])

    def _parse_ref_element(self, ref_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Find <link:reference xlink:label="ref_id"> and parse its FASB fields.

        Returns a dict with keys {publisher, topic, subtopic, section,
        paragraph, role} or None if the element is absent.  Unlike the earlier
        version this does NOT filter on Publisher==FASB, because the modern
        us-gaap codification references live under the <codification-part:*>
        namespace with no <ref:Publisher> element; filtering on FASB there
        would discard every real citation.
        """
        if ref_id in self._ref_parse_cache:
            return self._ref_parse_cache[ref_id]

        self._build_index()
        ref_text = self._ref_index.get(ref_id)
        if ref_text is None:
            self._ref_parse_cache[ref_id] = None
            return None

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

        # Reference role — last path segment of the xlink:role URI on the
        # opening tag (e.g. ".../role/disclosureRef" -> "disclosureRef").
        role = ""
        role_m = re.search(r"xlink:role=[\"']([^\"']+)[\"']", ref_text)
        if role_m:
            role = role_m.group(1).rstrip("/").rsplit("/", 1)[-1]

        parsed = {
            "publisher": _val("Publisher"),
            "topic":     _val("Topic"),
            "subtopic":  _val("SubTopic"),
            "section":   _val("Section"),
            "paragraph": _val("Paragraph"),
            "role":      role,
        }
        self._ref_parse_cache[ref_id] = parsed
        return parsed

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

    @staticmethod
    def _rank_key(parts: Dict[str, Optional[str]]) -> tuple:
        """Sort key for choosing among a concept's many reference arcs.

        A concept like us-gaap:InterestExpense carries 8 references spanning
        industry topics (946 Financial Services), segment disclosure (280),
        and the income-statement presentation topic (220).  Picking the
        "longest" string (the old heuristic) wrongly favoured deep,
        industry-specific paragraphs.  Instead we rank by, in order:

          1. general over industry topic        (topic < 900 preferred)
          2. authoritative role                  (presentation/disclosure > example/legacy)
          3. completeness                        (has subtopic/section/paragraph)
          4. lower topic number as a deterministic tie-break
             (ASC presentation/general topics 205-280 precede the asset/
              liability/expense topics, matching how face-of-statement line
              items are cited)

        Higher tuple = preferred (we select max).
        """
        try:
            topic_int = int(parts.get("topic") or 0)
        except ValueError:
            topic_int = 0
        # Topics that almost never govern a face-of-statement line item but show
        # up as reference arcs and used to win the pick: 852 Reorganizations,
        # 235 Notes to Financial Statements, 280 Segment Reporting.
        not_junk     = 0 if topic_int in (852, 235, 280) else 1
        # SEC-staff content (sections S99/S25/Sxx) is interpretive guidance, not
        # the authoritative ASC standard — demote below real codification refs.
        section_val  = (parts.get("section") or "").upper()
        not_sec      = 0 if section_val.startswith("S") else 1
        is_general   = 1 if 0 < topic_int < _INDUSTRY_TOPIC_MIN else 0
        role_pri     = _ROLE_PRIORITY.get(parts.get("role", ""), 0)
        completeness = sum(1 for k in ("subtopic", "section", "paragraph") if parts.get(k))
        return (not_junk, not_sec, is_general, role_pri, completeness, -topic_int)

    def _lookup_one(self, concept_id: str) -> Optional[str]:
        """Direct lookup: rank all of a concept's reference arcs and return the
        best citation, or None when no usable reference arc exists."""
        ref_ids = self._refs_for_concept(concept_id)
        best_parts: Optional[Dict[str, Optional[str]]] = None
        best_key: Optional[tuple] = None
        for ref_id in ref_ids:
            parts = self._parse_ref_element(ref_id)
            if parts is None or not parts.get("topic"):
                continue
            key = self._rank_key(parts)
            if best_key is None or key > best_key:
                best_key, best_parts = key, parts
        return self._build_citation(best_parts) if best_parts else None

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

    def get_candidate_citations(self, concept_id: str) -> List[Dict]:
        """Return ALL reference arcs for a concept, ranked best-first.

        Whereas get_fasb_citation_detail commits to a single best guess, this
        exposes the full candidate set the graph knows about.  Stage 2 (the
        focused LLM) uses this set + the error context to select the
        contextually correct citation — the LLM never invents one, it only
        picks from grounded candidates.

        Each entry: {"asc": "230-10-45-5", "topic": "230", "role": "disclosureRef"}.
        Falls back to parent concepts only if the leaf itself has no arcs.
        """
        self._load_taxonomy()
        if not self._available:
            return []

        def _collect(cid: str) -> List[Dict]:
            seen = set()
            ranked = []
            for ref_id in self._refs_for_concept(cid):
                parts = self._parse_ref_element(ref_id)
                if parts is None or not parts.get("topic"):
                    continue
                cit = self._build_citation(parts)
                if not cit:
                    continue
                asc = cit.replace("FASB ASC ", "")
                if asc in seen:
                    continue
                seen.add(asc)
                ranked.append((self._rank_key(parts), {
                    "asc":   asc,
                    "topic": parts.get("topic"),
                    "role":  parts.get("role", ""),
                }))
            ranked.sort(key=lambda x: x[0], reverse=True)
            return [r[1] for r in ranked]

        cands = _collect(concept_id)
        if cands:
            return cands
        for parent in _parent_candidates(concept_id):
            cands = _collect(parent)
            if cands:
                return cands
        return []


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
