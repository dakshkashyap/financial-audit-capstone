"""
Iterative citation agent.

Modes
-----
  heuristic  — no API key; scores candidates with subject-matter bias + concept hints
  llm        — asks a chat model to pick from candidates; Python validates & retries
  oracle     — if GT topic is in candidates, pick it (ceiling demo)

The agent never invents ASC codes: every accepted citation must pass
validate_citation (grounded in TaxonomyGraph candidates).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from core.paths import REPO_ROOT as _ROOT
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from approaches.citation_mcp_agent.tools import TaxonomyTools, dumps, _normalize_asc, _PRESENTATION_TOPICS

# Concept-name → preferred ASC topic (subject matter)
_CONCEPT_TOPIC_HINTS = [
    (re.compile(r"Inventory", re.I), "330"),
    (re.compile(r"Goodwill|Intangible", re.I), "350"),
    (re.compile(r"Revenue|ContractWithCustomer", re.I), "606"),
    (re.compile(r"Lease", re.I), "842"),
    (re.compile(r"PropertyPlant|Depreciation|PPE", re.I), "360"),
    (re.compile(r"IncomeTax|DeferredTax", re.I), "740"),
    (re.compile(r"Contingenc|LossContingency", re.I), "450"),
    (re.compile(r"Receivable|AllowanceFor", re.I), "310"),
    (re.compile(r"Debt|Borrowing|LongTermDebt", re.I), "470"),
    (re.compile(r"StockholdersEquity|CommonStock|TreasuryStock|ShareBased", re.I), "505"),
    (re.compile(r"Pension|Postretirement|Benefit", re.I), "715"),
    (re.compile(r"Derivative|Hedging", re.I), "815"),
    (re.compile(r"FairValue", re.I), "820"),
    (re.compile(r"CashAndCashEquivalents|CashFlow", re.I), "230"),
    (re.compile(r"BusinessCombination|Acquisition", re.I), "805"),
]


@dataclass
class CitationResult:
    concept: str
    citation: Optional[str]
    topic: Optional[str]
    mode: str
    iterations: int
    validated: bool
    hallucinated_attempts: int = 0
    rationale: str = ""
    baseline_citation: Optional[str] = None
    trace: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CitationAgent:
    def __init__(
        self,
        tools: Optional[TaxonomyTools] = None,
        mode: str = "heuristic",
        max_iterations: int = 3,
        model: str = "claude/claude-haiku-4-5",
    ) -> None:
        self.tools = tools or TaxonomyTools()
        self.mode = mode
        self.max_iterations = max_iterations
        self.model = model
        self._llm = None

    def cite(
        self,
        concept: str,
        *,
        item_id: str = "item",
        label: str = "",
        statement_type: str = "",
        error_type: str = "",
        gt_topic: Optional[str] = None,
    ) -> CitationResult:
        concept = (concept or "").replace("us-gaap:", "").strip()
        info = self.tools.get_concept_info(concept)
        baseline = info.get("graph_single_pick")

        if self.mode == "oracle":
            return self._oracle(concept, item_id, gt_topic, baseline)
        if self.mode == "llm":
            return self._llm_loop(
                concept, item_id, label, statement_type, error_type, baseline
            )
        return self._heuristic_loop(
            concept, item_id, label, statement_type, error_type, baseline
        )

    # ── heuristic ─────────────────────────────────────────────────────────────

    def _heuristic_loop(
        self,
        concept: str,
        item_id: str,
        label: str,
        statement_type: str,
        error_type: str,
        baseline: Optional[str],
    ) -> CitationResult:
        trace: List[Dict[str, Any]] = []
        cands_resp = self.tools.get_candidates(concept)
        cands = cands_resp["candidates"]
        trace.append({"tool": "get_candidates", "result_n": len(cands)})

        if not cands:
            return CitationResult(
                concept=concept, citation=None, topic=None, mode="heuristic",
                iterations=1, validated=False, baseline_citation=baseline,
                rationale="no_candidates", trace=trace,
            )

        ranked = sorted(
            cands,
            key=lambda c: self._score_candidate(c, concept, label, statement_type),
            reverse=True,
        )
        rejected: List[str] = []
        for i, cand in enumerate(ranked[: self.max_iterations], start=1):
            asc = cand["asc"]
            v = self.tools.validate_citation(concept, asc)
            trace.append({"tool": "validate_citation", "asc": asc, "valid": v["valid"]})
            if not v["valid"]:
                rejected.append(asc)
                continue
            final = v["asc"]
            store = self.tools.store_pick(
                item_id, final,
                rationale=f"heuristic_rank={i}; role={cand.get('role')}",
            )
            trace.append({"tool": "store_pick", "result": store})
            return CitationResult(
                concept=concept,
                citation=final,
                topic=final.split("-")[0],
                mode="heuristic",
                iterations=i,
                validated=True,
                baseline_citation=baseline,
                rationale=store.get("rationale", ""),
                trace=trace,
            )

        # Fallback: first candidate (should always validate)
        asc = ranked[0]["asc"]
        v = self.tools.validate_citation(concept, asc)
        return CitationResult(
            concept=concept,
            citation=v.get("asc") if v["valid"] else None,
            topic=(v.get("asc") or "").split("-")[0] or None,
            mode="heuristic",
            iterations=self.max_iterations,
            validated=bool(v.get("valid")),
            baseline_citation=baseline,
            rationale="fallback_top_candidate",
            trace=trace,
        )

    def _score_candidate(
        self,
        cand: Dict[str, Any],
        concept: str,
        label: str,
        statement_type: str,
    ) -> tuple:
        topic = str(cand.get("topic") or "")
        role = str(cand.get("role") or "")
        text = f"{concept} {label}"

        hint_bonus = 0
        for rx, hinted in _CONCEPT_TOPIC_HINTS:
            if rx.search(text) and topic == hinted:
                hint_bonus = 10
                break

        try:
            t_int = int(topic) if topic else 0
        except ValueError:
            t_int = 0

        # Prefer general subject-matter; demote face presentation + industry/reorg.
        if topic in _PRESENTATION_TOPICS:
            subject = 0
        elif t_int >= 900 or topic == "852":
            subject = -2  # industry / reorganizations — usually wrong for AuditBench
        else:
            subject = 3

        general = 2 if 0 < t_int < 900 else 0

        role_score = {
            "measurementRef": 4,
            "disclosureRef": 3,
            "presentationRef": 1,
            "definitionRef": 2,
            "exampleRef": 0,
        }.get(role, 0)

        # Cash / cash-flow: ASC 230 is often the right pick
        if topic == "230" and (
            statement_type.lower() in ("cf", "cash_flow", "cashflow")
            or re.search(r"Cash", concept + " " + label)
        ):
            subject = 4

        completeness = len(str(cand.get("asc") or "").split("-"))
        return (hint_bonus, subject, general, role_score, completeness)

    # ── LLM loop ──────────────────────────────────────────────────────────────

    def _llm_loop(
        self,
        concept: str,
        item_id: str,
        label: str,
        statement_type: str,
        error_type: str,
        baseline: Optional[str],
    ) -> CitationResult:
        trace: List[Dict[str, Any]] = []
        hallucinated = 0
        cands_resp = self.tools.get_candidates(concept)
        cands = cands_resp["candidates"]
        info = self.tools.get_concept_info(concept)
        trace.append({"tool": "get_candidates", "result_n": len(cands)})
        trace.append({"tool": "get_concept_info", "result": {
            "subject_matter_topics": info.get("subject_matter_topics"),
            "graph_single_pick": baseline,
        }})

        if not cands:
            return CitationResult(
                concept=concept, citation=None, topic=None, mode="llm",
                iterations=0, validated=False, baseline_citation=baseline,
                rationale="no_candidates", trace=trace,
            )

        allowed = [c["asc"] for c in cands]
        rejected: List[str] = []
        client = self._get_llm()

        for i in range(1, self.max_iterations + 1):
            prompt = _llm_pick_prompt(
                concept=concept,
                label=label,
                statement_type=statement_type,
                error_type=error_type,
                candidates=cands,
                rejected=rejected,
                baseline=baseline,
            )
            raw = client.generate(
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )["content"]
            pick = _parse_pick(raw)
            trace.append({"iteration": i, "llm_raw": raw[:500], "parsed": pick})

            if not pick:
                continue

            asc = _normalize_asc(pick.get("asc", ""))
            if asc not in {_normalize_asc(a) for a in allowed}:
                # Hallucination attempt — reject without accepting
                hallucinated += 1
                v = self.tools.validate_citation(concept, asc)
                trace.append({"tool": "validate_citation", "asc": asc, "valid": False,
                              "hallucination": True, "result": v})
                rejected.append(asc or pick.get("asc", "?"))
                continue

            v = self.tools.validate_citation(concept, asc)
            trace.append({"tool": "validate_citation", "asc": asc, "valid": v["valid"]})
            if not v["valid"]:
                rejected.append(asc)
                continue

            final = v["asc"]
            rationale = pick.get("rationale", "")
            store = self.tools.store_pick(item_id, final, rationale=rationale)
            trace.append({"tool": "store_pick", "result": store})
            return CitationResult(
                concept=concept,
                citation=final,
                topic=final.split("-")[0],
                mode="llm",
                iterations=i,
                validated=True,
                hallucinated_attempts=hallucinated,
                baseline_citation=baseline,
                rationale=rationale,
                trace=trace,
            )

        # Exhausted — fall back to heuristic top pick (still grounded)
        fallback = self._heuristic_loop(
            concept, item_id, label, statement_type, error_type, baseline
        )
        fallback.mode = "llm+heuristic_fallback"
        fallback.hallucinated_attempts = hallucinated
        fallback.trace = trace + fallback.trace
        return fallback

    def _get_llm(self):
        if self._llm is None:
            from core.model_backends import get_model_client
            self._llm = get_model_client(self.model)
        return self._llm

    # ── oracle ceiling ────────────────────────────────────────────────────────

    def _oracle(
        self,
        concept: str,
        item_id: str,
        gt_topic: Optional[str],
        baseline: Optional[str],
    ) -> CitationResult:
        cands = self.tools.get_candidates(concept)["candidates"]
        pick = None
        if gt_topic:
            for c in cands:
                if c.get("topic") == gt_topic:
                    pick = c["asc"]
                    break
        if pick is None and cands:
            pick = cands[0]["asc"]
        if pick is None:
            return CitationResult(
                concept=concept, citation=None, topic=None, mode="oracle",
                iterations=0, validated=False, baseline_citation=baseline,
                rationale="no_candidates",
            )
        v = self.tools.validate_citation(concept, pick)
        if v["valid"]:
            self.tools.store_pick(item_id, v["asc"], rationale=f"oracle_gt={gt_topic}")
        return CitationResult(
            concept=concept,
            citation=v.get("asc") if v["valid"] else None,
            topic=(v.get("asc") or "").split("-")[0] or None,
            mode="oracle",
            iterations=1,
            validated=bool(v.get("valid")),
            baseline_citation=baseline,
            rationale=f"oracle_gt={gt_topic}",
            trace=[{"tool": "validate_citation", "result": v}],
        )


_SYSTEM = (
    "You select FASB ASC citations for XBRL line items. "
    "You may ONLY choose an ASC code from the provided candidate list. "
    "Never invent a code. Prefer subject-matter topics (e.g. 330 inventory, "
    "350 goodwill, 606 revenue) over presentation topics (205/210/220/230) "
    "unless the item is clearly a cash-flow or face presentation item. "
    "Reply with JSON only: {\"asc\": \"...\", \"rationale\": \"...\"}"
)


def _llm_pick_prompt(
    concept: str,
    label: str,
    statement_type: str,
    error_type: str,
    candidates: List[Dict[str, Any]],
    rejected: List[str],
    baseline: Optional[str],
) -> str:
    return dumps({
        "task": "Pick the best ASC from candidates for this broken line item.",
        "concept": concept,
        "label": label,
        "statement_type": statement_type,
        "error_type": error_type,
        "graph_single_pick_baseline": baseline,
        "candidates": candidates,
        "previously_rejected": rejected,
        "response_format": {"asc": "exact string from candidates[].asc", "rationale": "one sentence"},
    })


def _parse_pick(raw: str) -> Optional[Dict[str, str]]:
    if not raw:
        return None
    text = raw.strip()
    # fenced json
    m = re.search(r"\{[^{}]+\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "asc" not in obj:
        return None
    return {"asc": str(obj["asc"]), "rationale": str(obj.get("rationale", ""))}
