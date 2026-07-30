"""
finmr_taxonomy_citations.py — Run the TaxonomyGraph against every target concept
in TheFinAI/FinMR to demonstrate citation coverage on real XBRL filings.

IMPORTANT: FinMR has no ground-truth "Standards Citation" field, so this is NOT
a benchmark score. It is a coverage report showing:
  - % of FinMR target concepts that resolve to a FASB ASC citation
  - Whether the citation came from a direct taxonomy hit or parent fallback
  - Which ASC topics are assigned, broken down by DQC rule

The TaxonomyGraph itself is unchanged; we feed it the bare local concept names
(e.g. "NetCashProvidedByUsedInOperatingActivities") stripped of the us-gaap:
prefix.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from datasets import load_dataset

from finmr_parser import parse_record
from taxonomy_graph import TaxonomyGraph

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def _topic_of(asc: Optional[str]) -> Optional[str]:
    """Extract ASC topic number from a citation like '230-10-45-5'."""
    if not asc:
        return None
    asc = asc.replace("FASB ASC ", "")
    parts = asc.split("-")
    return parts[0] if parts else None


def _topic_name(topic: str) -> str:
    """Friendly names for common ASC presentation topics."""
    names = {
        "210": "Balance Sheet",
        "220": "Income Statement",
        "230": "Cash Flows",
        "235": "Notes / SEC Reporting",
        "250": "Changes in Financial Position",
        "260": "Earnings Per Share",
        "270": "Interim Reporting",
        "275": "Risks and Uncertainties",
        "280": "Segment Reporting",
        "305": "Cash and Cash Equivalents",
        "310": "Receivables",
        "320": "Investments — Debt Securities",
        "330": "Inventory",
        "340": "Debt Financing",
        "350": "Intangibles",
        "360": "Property Plant and Equipment",
        "410": "Asset Retirement and Env Obligations",
        "420": "Exit or Disposal Cost Obligations",
        "430": "Deferred Revenue",
        "440": "Commitments",
        "450": "Contingencies",
        "460": "Guarantees",
        "470": "Debt",
        "480": "Legal Proceedings",
        "505": "Equity",
        "605": "Revenue Recognition",
        "705": "Cost of Sales and Services",
        "710": "Compensation — General",
        "712": "Compensation — Nonretirement Postemployment",
        "715": "Compensation — Retirement Benefits",
        "718": "Compensation — Stock Compensation",
        "720": "Other Expenses",
        "730": "Research and Development",
        "740": "Income Taxes",
        "810": "Contractor Accounting",
        "815": "Derivatives and Hedging",
        "820": "Fair Value Measurement",
        "825": "Financial Instruments",
        "830": "Interest",
        "835": "Interest — Capitalization",
        "840": "Leases",
        "845": "Nonmonetary Transactions",
        "850": "Related Party Disclosures",
        "855": "Subsequent Events",
        "860": "Transfers and Servicing",
        "946": "Financial Services — Investment Companies",
    }
    return names.get(topic, f"Topic {topic}")


def main() -> None:
    ds = load_dataset("TheFinAI/FinMR", split="test")
    graph = TaxonomyGraph()

    # Map each unique target concept -> records that use it
    concept_records: Dict[str, List[int]] = defaultdict(list)
    concept_rule: Dict[str, str] = {}
    concept_asc: Dict[str, Optional[str]] = {}

    for i, row in enumerate(ds):
        rec = parse_record(row)
        if rec.question is None:
            continue
        bare = rec.question.concept_bare
        concept_records[bare].append(i)
        if bare not in concept_rule:
            concept_rule[bare] = rec.dqc_rule

    unique_concepts = sorted(concept_records)
    print(f"Unique FinMR target concepts: {len(unique_concepts)}")

    results: List[dict] = []
    covered = 0
    parent_fallback = 0
    topic_counter = Counter()
    topic_by_rule: Dict[str, Counter] = defaultdict(Counter)

    for concept in unique_concepts:
        detail = graph.get_fasb_citation_detail(concept)
        asc = detail["asc_primary"]
        topic = _topic_of(asc)
        rule = concept_rule[concept]

        if asc:
            covered += 1
            topic_counter[topic] += 1
            topic_by_rule[rule][topic] += 1
            if detail["source"] == "parent_fallback":
                parent_fallback += 1

        results.append({
            "concept": concept,
            "dqc_rule": rule,
            "asc": asc,
            "topic": topic,
            "source": detail["source"],
            "matched_concept": detail["matched_concept"],
            "record_ids": concept_records[concept],
        })

    # ── summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("TaxonomyGraph Citation Coverage on FinMR Target Concepts")
    print("=" * 70)
    total = len(unique_concepts)
    print(f"  Unique target concepts: {total}")
    print(f"  With ASC citation       : {covered} ({100*covered/total:.1f}%)")
    print(f"  Direct taxonomy hit     : {covered - parent_fallback} ({100*(covered-parent_fallback)/total:.1f}%)")
    print(f"  Parent fallback hit     : {parent_fallback} ({100*parent_fallback/total:.1f}%)")
    print(f"  No citation             : {total - covered} ({100*(total-covered)/total:.1f}%)")

    print("\n  Top ASC topics assigned:")
    for topic, count in topic_counter.most_common(15):
        print(f"    ASC {topic:>3} — {_topic_name(topic):42s} : {count} concepts")

    print("\n  Topic distribution by DQC rule:")
    for rule in sorted(topic_by_rule):
        print(f"\n    {rule}:")
        for topic, count in topic_by_rule[rule].most_common(10):
            print(f"      ASC {topic:>3} {_topic_name(topic):40s}: {count}")

    print("\n  Sample citations (first 20):")
    for r in results[:20]:
        asc = r["asc"] or "—"
        src = "taxonomy" if r["source"] == "taxonomy" else r["source"]
        print(f"    {r['concept'][:55]:55s} → {asc:20s} ({src})")

    print("=" * 70)

    # ── write JSON ───────────────────────────────────────────────────────────────
    out_path = os.path.join(RESULTS_DIR, "finmr_taxonomy_citations.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_concepts": total,
            "coverage": {
                "with_citation": covered,
                "direct": covered - parent_fallback,
                "parent_fallback": parent_fallback,
                "no_citation": total - covered,
            },
            "topic_counts": dict(topic_counter.most_common()),
            "topic_by_rule": {r: dict(c.most_common()) for r, c in topic_by_rule.items()},
            "concepts": results,
        }, f, indent=2)
    print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
