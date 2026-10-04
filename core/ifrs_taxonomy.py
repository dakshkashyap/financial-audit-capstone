"""
IFRS reference-linkbase reader.

The US-GAAP ``TaxonomyGraph`` finds concepts by a ``loc_<Concept>`` label.
The IFRS Accounting Taxonomy does not use that label convention: locators
are ``xlink:href`` fragments such as ``ifrs-full_Inventories``. This module
resolves those fragments and reads IAS/IFRS reference parts
(Name, Number, Paragraph) instead of Topic-SubTopic-Section-Paragraph.

Nothing is downloaded. Point ``IFRS_TAXONOMY_ZIP`` at a local IFRS
Accounting Taxonomy zip, or drop ``data/ifrs/ifrs_ref_cache.json``
(concept -> paragraph ids) produced by IntelliAudit's
``scripts/build_ifrs_ref_cache.py``. Without either, ``available`` is
False and Stage 1 falls back to the IFRS subject and presentation rules.
"""
from __future__ import annotations

import json
import os
import zipfile
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

from core.frameworks import bare_concept, ifrs_code_from_parts, ifrs_paragraph_of
from core.paths import DATA_DIR

_CACHE = os.path.join(DATA_DIR, "ifrs", "ifrs_ref_cache.json")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _attr(elem: ET.Element, name: str) -> Optional[str]:
    for key, value in elem.attrib.items():
        if _local(key) == name:
            return value
    return None


def _parse_linkbase(xml_bytes: bytes, index: Dict[str, List[dict]]) -> None:
    """Fill ``index[concept]`` with {code, role} dicts from one linkbase."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return
    for link in root.iter():
        if _local(link.tag) != "referenceLink":
            continue
        locs: Dict[str, str] = {}
        refs: Dict[str, List[tuple]] = {}
        roles: Dict[str, str] = {}
        arcs = []
        for child in link:
            kind = _local(child.tag)
            label = _attr(child, "label") or ""
            if kind == "loc":
                href = _attr(child, "href") or ""
                frag = href.split("#", 1)[1] if "#" in href else href
                concept = frag.split("_", 1)[1] if "_" in frag else frag
                locs[label] = concept
            elif kind == "reference":
                refs[label] = [(_local(part.tag), (part.text or "").strip()) for part in child]
                role = _attr(child, "role") or ""
                roles[label] = role.rstrip("/").rsplit("/", 1)[-1]
            elif kind == "referenceArc":
                arcs.append((_attr(child, "from"), _attr(child, "to")))
        for src, dst in arcs:
            concept = locs.get(src or "")
            parts = refs.get(dst or "")
            if not concept or not parts:
                continue
            code = ifrs_code_from_parts(parts)
            if not code:
                continue
            index.setdefault(concept, []).append({
                "code": code,
                "role": roles.get(dst or "", ""),
            })


class IfrsTaxonomyGraph:
    """Concept -> IAS/IFRS paragraphs. Empty until ``load_*`` succeeds."""

    def __init__(self) -> None:
        self._index: Optional[Dict[str, List[dict]]] = None

    @property
    def available(self) -> bool:
        return bool(self._index)

    def load_xml_bytes(self, xml_bytes: bytes) -> None:
        index: Dict[str, List[dict]] = {}
        _parse_linkbase(xml_bytes, index)
        self._index = index

    def load_zip(self, zip_path: str) -> None:
        index: Dict[str, List[dict]] = {}
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.endswith(".xml"):
                    continue
                raw = zf.read(name)
                if b"referenceLink" in raw:
                    _parse_linkbase(raw, index)
        self._index = index

    def load_cache(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        concepts = payload.get("concepts", payload)
        index: Dict[str, List[dict]] = {}
        for concept, codes in concepts.items():
            if concept.startswith("_"):
                continue
            index[bare_concept(concept)] = [
                {"code": code, "role": ""} for code in codes if code
            ]
        self._index = index

    def citations(self, concept_id: str) -> List[str]:
        """Deduped IAS/IFRS codes in linkbase order. Empty when not loaded."""
        if not self._index:
            return []
        seen = set()
        out: List[str] = []
        for entry in self._index.get(bare_concept(concept_id), []):
            code = entry.get("code")
            if code and code not in seen:
                seen.add(code)
                out.append(code)
        return out

    def get_candidate_citations(self, concept_id: str) -> List[dict]:
        """{'citation', 'standard', 'role'} for each attached paragraph."""
        from core.frameworks import ifrs_standard_of
        if not self._index:
            return []
        seen = set()
        out = []
        for entry in self._index.get(bare_concept(concept_id), []):
            code = entry.get("code")
            if not code or code in seen:
                continue
            seen.add(code)
            out.append({
                "citation": code,
                "standard": ifrs_standard_of(code),
                "role": entry.get("role") or "",
            })
        return out

    def paragraph_verified(self, concept_id: str, code: str) -> bool:
        """True only when the linkbase attaches this exact paragraph."""
        want = ifrs_paragraph_of(code)
        if want is None:
            return False
        return any(ifrs_paragraph_of(cited) == want for cited in self.citations(concept_id))


_DEFAULT: Optional[IfrsTaxonomyGraph] = None


def default_ifrs_graph() -> IfrsTaxonomyGraph:
    """Zip from ``IFRS_TAXONOMY_ZIP``, else the JSON cache, else empty."""
    global _DEFAULT
    if _DEFAULT is not None:
        return _DEFAULT
    graph = IfrsTaxonomyGraph()
    zip_path = os.environ.get("IFRS_TAXONOMY_ZIP", "")
    if zip_path and os.path.isfile(zip_path):
        graph.load_zip(zip_path)
    elif os.path.isfile(_CACHE):
        graph.load_cache(_CACHE)
    _DEFAULT = graph
    return graph


def reset_default_graph() -> None:
    """Test hook. The default graph caches the first successful lookup."""
    global _DEFAULT
    _DEFAULT = None
