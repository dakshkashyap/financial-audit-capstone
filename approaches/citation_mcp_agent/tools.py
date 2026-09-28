"""
Deterministic citation tools wrapping TaxonomyGraph.

These are the same functions the MCP server exposes and the agent calls.
No LLM inside — every ASC returned comes from the FASB US-GAAP linkbase.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from core.paths import REPO_ROOT as _ROOT
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.taxonomy_graph import TaxonomyGraph, _parent_candidates  # noqa: E402

# Face-of-financials presentation topics — often wrong when GT wants subject-matter.
_PRESENTATION_TOPICS = {"205", "210", "220", "230"}


class TaxonomyTools:
    """In-process tool registry shared by the MCP server and the citation agent."""

    def __init__(self, graph: Optional[TaxonomyGraph] = None) -> None:
        self.graph = graph or TaxonomyGraph()
        self._store: Dict[str, Dict[str, Any]] = {}

    # ── tools ─────────────────────────────────────────────────────────────────

    def get_candidates(self, concept: str, framework: str = "") -> Dict[str, Any]:
        """Return grounded citation candidates for a concept.

        US GAAP returns FASB ASC arcs. ``framework="ifrs"`` or an
        ``ifrs-full:`` concept returns IAS/IFRS standards from the subject
        rules plus any loaded IFRS reference linkbase.
        """
        from core.frameworks import resolve_framework
        fw = resolve_framework(concept, framework or None)
        if fw == "ifrs":
            return _ifrs_candidates(concept)
        concept = _bare(concept)
        cands = self.graph.get_candidate_citations(concept)
        return {
            "concept": concept,
            "n": len(cands),
            "candidates": cands,
            "note": (
                "Pick ONE asc from this list. Do not invent codes. "
                "Prefer subject-matter topics over presentation (205/210/220/230) "
                "when the line item has a clear topic (inventory, goodwill, revenue…)."
            ),
        }

    def validate_citation(self, concept: str, asc: str, framework: str = "") -> Dict[str, Any]:
        """True only if `asc` appears in the grounded candidate set for `concept`."""
        from core.frameworks import ifrs_paragraph_of, ifrs_standard_of, resolve_framework
        fw = resolve_framework(concept, framework or None)
        if fw == "ifrs" or ifrs_standard_of(asc):
            return _validate_ifrs(concept, asc)
        concept = _bare(concept)
        asc_norm = _normalize_asc(asc)
        if not asc_norm:
            return {
                "valid": False,
                "reason": "could_not_parse_asc",
                "concept": concept,
                "asc": asc,
            }

        cands = self.graph.get_candidate_citations(concept)
        allowed = {_normalize_asc(c["asc"]) for c in cands}
        # Also accept topic-only / shorter prefixes that match a candidate prefix
        topic_ok = any(
            a == asc_norm or a.startswith(asc_norm + "-") or asc_norm.startswith(a + "-")
            for a in allowed if a
        )
        exact = asc_norm in allowed

        if exact or topic_ok:
            matched = next(
                (c["asc"] for c in cands
                 if _normalize_asc(c["asc"]) == asc_norm
                 or _normalize_asc(c["asc"]).startswith(asc_norm + "-")
                 or asc_norm.startswith(_normalize_asc(c["asc"]) + "-")),
                asc_norm,
            )
            return {
                "valid": True,
                "reason": "in_candidate_set",
                "concept": concept,
                "asc": matched,
                "topic": matched.split("-")[0] if matched else None,
            }

        return {
            "valid": False,
            "reason": "not_in_candidate_set",
            "concept": concept,
            "asc": asc_norm,
            "allowed_topics": sorted({c["topic"] for c in cands if c.get("topic")}),
            "hint": "Choose a different asc from get_candidates.",
        }

    def get_concept_info(self, concept: str, framework: str = "") -> Dict[str, Any]:
        """Concept metadata: single-pick baseline, parents, candidate count."""
        from core.frameworks import resolve_framework
        if resolve_framework(concept, framework or None) == "ifrs":
            payload = _ifrs_candidates(concept)
            standards = [c["standard"] for c in payload["candidates"] if c.get("standard")]
            return {
                "concept": payload["concept"],
                "framework": "ifrs",
                "subject_topic": payload.get("subject"),
                "n_candidates": payload["n"],
                "candidate_topics": sorted(set(standards)),
                "graph_single_pick": payload.get("subject") or (standards[0] if standards else None),
                "graph_source": "ifrs_rules",
            }
        concept = _bare(concept)
        detail = self.graph.get_fasb_citation_detail(concept)
        cands = self.graph.get_candidate_citations(concept)
        return {
            "concept": concept,
            "parents": _parent_candidates(concept)[:8],
            "graph_single_pick": detail.get("asc_primary"),
            "graph_source": detail.get("source"),
            "matched_concept": detail.get("matched_concept"),
            "n_candidates": len(cands),
            "candidate_topics": sorted({c["topic"] for c in cands if c.get("topic")}),
            "presentation_topics": sorted(
                t for t in {c["topic"] for c in cands if c.get("topic")}
                if t in _PRESENTATION_TOPICS
            ),
            "subject_matter_topics": sorted(
                t for t in {c["topic"] for c in cands if c.get("topic")}
                if t not in _PRESENTATION_TOPICS
                and _topic_int(t) < 900
                and t != "852"
            ),
        }

    def store_pick(
        self,
        item_id: str,
        citation: str,
        rationale: str = "",
    ) -> Dict[str, Any]:
        """Persist the agent's final pick for a demo / eval item."""
        from core.frameworks import ifrs_paragraph_of, ifrs_standard_of
        if ifrs_standard_of(citation):
            stored = ifrs_paragraph_of(citation) or ifrs_standard_of(citation)
        else:
            stored = _normalize_asc(citation)
        self._store[item_id] = {
            "citation": stored,
            "rationale": rationale,
        }
        return {
            "stored": True,
            "item_id": item_id,
            "citation": stored,
            "rationale": rationale,
        }

    def get_stored(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(item_id)

    # ── dispatch (agent + MCP share this) ─────────────────────────────────────

    def call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        fn = {
            "get_candidates": self.get_candidates,
            "validate_citation": self.validate_citation,
            "get_concept_info": self.get_concept_info,
            "store_pick": self.store_pick,
        }.get(name)
        if fn is None:
            return {"error": f"unknown_tool:{name}"}
        try:
            return fn(**arguments)
        except TypeError as exc:
            return {"error": f"bad_arguments:{exc}"}

    def tool_schemas(self) -> List[Dict[str, Any]]:
        """JSON schemas for LLM tool-calling / MCP listing."""
        return [
            {
                "name": "get_candidates",
                "description": (
                    "Return all FASB ASC citations grounded in the US-GAAP "
                    "taxonomy for a concept. You MUST pick from this list."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "concept": {
                            "type": "string",
                            "description": "Bare us-gaap concept name (no prefix)",
                        }
                    },
                    "required": ["concept"],
                },
            },
            {
                "name": "validate_citation",
                "description": (
                    "Check that an ASC citation is in the grounded candidate set. "
                    "Call this before store_pick. If invalid, pick another candidate."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "concept": {"type": "string"},
                        "asc": {
                            "type": "string",
                            "description": "ASC like 330-10-35-1 or FASB ASC 330-10-35-1",
                        },
                    },
                    "required": ["concept", "asc"],
                },
            },
            {
                "name": "get_concept_info",
                "description": (
                    "Metadata for a concept: graph single-pick baseline, parents, "
                    "presentation vs subject-matter topic split."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"concept": {"type": "string"}},
                    "required": ["concept"],
                },
            },
            {
                "name": "store_pick",
                "description": "Store the final validated citation for this item and stop.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "citation": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["item_id", "citation"],
                },
            },
        ]


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


def _bare(concept: str) -> str:
    return (concept or "").replace("us-gaap:", "").strip()


def _normalize_asc(asc: str) -> str:
    if not asc:
        return ""
    s = asc.strip()
    for prefix in ("FASB ASC ", "ASC ", "FASB ", "Codification "):
        if s.upper().startswith(prefix.upper()):
            s = s[len(prefix):]
            break
    # keep digits and hyphens only from the first ASC-looking token
    parts = []
    for ch in s:
        if ch.isdigit() or ch == "-":
            parts.append(ch)
        elif parts:
            break
    return "".join(parts).strip("-")


def _topic_int(topic: str) -> int:
    try:
        return int(topic)
    except (TypeError, ValueError):
        return 0


def _ifrs_candidates(concept: str) -> Dict[str, Any]:
    """Subject-rule standards plus any paragraphs on a loaded IFRS linkbase."""
    from approaches.stage1_taxonomy_citation.concept_citation import (
        candidate_topics, subject_topic,
    )
    from core.frameworks import bare_concept, ifrs_standard_of
    from core.ifrs_taxonomy import default_ifrs_graph

    bare = bare_concept(concept)
    tagged = concept if (concept or "").startswith("ifrs-full:") else f"ifrs-full:{bare}"
    graph = default_ifrs_graph()
    tax = graph.citations(bare) if graph.available else []
    standards = candidate_topics(
        tagged, None,
        taxonomy_topics=[ifrs_standard_of(c) for c in tax],
        framework="ifrs",
    )
    cands: List[Dict[str, Any]] = []
    seen = set()
    for code in tax:
        if code in seen:
            continue
        seen.add(code)
        cands.append({"citation": code, "standard": ifrs_standard_of(code), "role": "taxonomy"})
    for std in standards:
        if std in seen:
            continue
        seen.add(std)
        cands.append({"citation": std, "standard": std, "role": "rule"})
    return {
        "framework": "ifrs",
        "concept": tagged,
        "n": len(cands),
        "candidates": cands,
        "subject": subject_topic(tagged, framework="ifrs"),
        "note": (
            "Pick ONE IAS/IFRS standard from this list. Do not invent a code "
            "and do not cite an ASC topic."
        ),
    }


def _validate_ifrs(concept: str, code: str) -> Dict[str, Any]:
    from core.frameworks import bare_concept, ifrs_paragraph_of, ifrs_standard_of

    payload = _ifrs_candidates(concept)
    want_paragraph = ifrs_paragraph_of(code)
    want_standard = ifrs_standard_of(code)
    if not want_standard:
        return {
            "valid": False,
            "reason": "could_not_parse_ifrs",
            "framework": "ifrs",
            "concept": bare_concept(concept),
            "asc": code,
        }
    for cand in payload["candidates"]:
        cited = cand.get("citation") or ""
        if want_paragraph and ifrs_paragraph_of(cited) == want_paragraph:
            return {
                "valid": True,
                "reason": "in_candidate_set",
                "framework": "ifrs",
                "concept": payload["concept"],
                "asc": want_paragraph,
                "topic": want_standard,
            }
        if cand.get("standard") == want_standard:
            return {
                "valid": True,
                "reason": "in_candidate_set",
                "framework": "ifrs",
                "concept": payload["concept"],
                "asc": want_standard,
                "topic": want_standard,
            }
    return {
        "valid": False,
        "reason": "not_in_candidate_set",
        "framework": "ifrs",
        "concept": payload["concept"],
        "asc": code,
        "allowed_topics": sorted({c["standard"] for c in payload["candidates"] if c.get("standard")}),
        "hint": "Choose a different standard from get_candidates.",
    }
