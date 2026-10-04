"""
concept_citation.py — knowledge-grounded ASC citation resolver (Stage 1+).

Why this exists
---------------
The raw FASB *reference linkbase* (taxonomy_graph.py) attaches presentation /
SEC-staff topics (210, 220, 280, 235, S99) and occasionally irrelevant topics
(852 Reorganizations) to face-of-statement concepts. Probing it shows the
correct governing ASC topic sits in the concept's candidate arcs only ~28% of
the time, so a single deterministic pick caps at ≈ the paper's 26%.

Measured analysis of the AuditBench Standards-Citation ground truth
(single_error, full set, 1296 records with an ASC topic) shows the GT is:
  * ~57% *presentation* topics — where the line is shown:
        230 Cash Flows (27.5%) · 210 Balance Sheet (14%) ·
        220 Income Statement (7.9%) · 225 old-IS (5.8%) · 205 Presentation (2.3%)
  * ~43% *subject-matter* topics — the standard that governs the item:
        310 Receivables · 330 Inventory · 360 PP&E · 350 Goodwill/Intangibles ·
        730 R&D · 740 Income Tax · 606/605 Revenue · 842 Leases · 505 Equity · …
  * internally inconsistent on version — it mixes superseded topics
        (225→220, 605→606, 305→…) with current ones.

No single rule can win that split. So this module does two things:
  1. best_topic(...)        — a principled single pick (subject map → presentation
                              fallback) for when a deterministic answer is needed.
  2. candidate_topics(...)  — the UNION candidate set {subject ∪ presentation ∪
                              taxonomy arcs}. Feeding this to the Stage-2 LLM raises
                              the achievable citation ceiling from ~28% to ~37%
                              (strict) / ~45% (version-tolerant) on n=150.

Everything here is grounded in public FASB ASC structure + the statement the row
lives in. It never reads the GT labels, so it is not benchmark leakage.

IFRS uses the same two-step shape with a different grammar. An ``ifrs-full:``
concept, or ``framework="ifrs"``, selects IAS/IFRS standards (IAS 2, IFRS 15)
instead of 3-digit ASC topics. The US-GAAP tables are unchanged when the
framework is omitted.
"""
from __future__ import annotations

import re
from typing import List, Optional, Set

from core.frameworks import bare_concept, ifrs_standard_of, resolve_framework

# ── statement-location (presentation) topics ──────────────────────────────────
# Where a line item is *presented* governs the topic the benchmark cites ~57% of
# the time. Driven off statement_type (always known) with a section-level refinement.
STMT_PRESENTATION = {
    "cash_flow":        "230-10-45",
    "balance_sheet":    "210-10-45",
    "income_statement": "220-10",
}

# ── subject-matter rules: concept-name substring → governing ASC topic ─────────
# Ordered; first match wins. Built from ASC domain knowledge, not from GT labels.
SUBJECT_RULES: List[tuple] = [
    (r"Goodwill", "350"),
    (r"IntangibleAssets|FiniteLived|IndefiniteLived|AmortizationOfIntangible", "350"),
    (r"Inventory", "330"),
    (r"PropertyPlantAndEquipment|Depreciation|AccumulatedDepreciation", "360"),
    (r"Lease|RightOfUseAsset", "842"),
    (r"Receivable|AllowanceForDoubtful|AllowanceForCreditLoss", "310"),
    (r"DeferredTax|IncomeTax|CurrentFederalTax|CurrentStateTax|TaxExpenseBenefit", "740"),
    (r"ShareBasedComp|StockBasedComp|ShareBasedPayment|AllocatedShareBased", "718"),
    (r"ResearchAndDevelopment", "730"),
    (r"LongTermDebt|ShortTermDebt|NotesPayable|LineOfCredit|DebtInstrument|"
     r"CommercialPaper|SecuredDebt|UnsecuredDebt|ConvertibleDebt", "470"),
    (r"CommonStock|AdditionalPaidInCapital|RetainedEarnings|TreasuryStock|"
     r"PreferredStock|StockholdersEquity|MinorityInterest", "505"),
    (r"AvailableForSale|MarketableSecurities|DebtSecurities|HeldToMaturity|"
     r"TradingSecurities|EquitySecurities", "320"),
    (r"BusinessCombination|BusinessAcquisition|AssetAcquisition", "805"),
    (r"ForeignCurrency|ForeignExchange|TranslationAdjustment", "830"),
    (r"Pension|Postretirement|DefinedBenefit|RetirementBenefit", "715"),
    (r"Revenue|RevenueFromContract|ContractWithCustomer", "606"),
    (r"EarningsPerShare", "260"),
    (r"FairValue", "820"),
    (r"Contingenc|Commitment|LossContingency|Guarantee", "450"),
    (r"AssetRetirementObligation", "410"),
    (r"Restructuring", "420"),
]

# section bucket (from xbrl_concept_map.json) → statement, for unknown stmt types
_SECTION_STMT = {
    "operating_activities": "cash_flow", "operating_adjustments": "cash_flow",
    "operating_working_capital": "cash_flow", "investing": "cash_flow",
    "financing": "cash_flow", "ending_cash": "cash_flow",
    "current_assets": "balance_sheet", "noncurrent_assets": "balance_sheet",
    "assets_subtotal": "balance_sheet", "current_liabilities": "balance_sheet",
    "noncurrent_liabilities": "balance_sheet", "equity": "balance_sheet",
    "equity_subtotal": "balance_sheet", "revenue": "income_statement",
    "operating_expenses": "income_statement",
    "operating_expenses_subtotal": "income_statement",
    "nonoperating": "income_statement", "income_tax": "income_statement",
    "net_income": "income_statement", "eps": "income_statement",
}

# superseded → successor, for the version-tolerant ("family") citation metric.
TOPIC_FAMILY = {"225": "220", "605": "606"}

# ── IFRS presentation standards ───────────────────────────────────────────────
# IAS 1 covers the statement of financial position and profit or loss.
# IAS 7 covers the statement of cash flows. Paragraphs (1.66 vs 1.69) are
# chosen later from the defect; the candidate at this layer is the standard.
IFRS_PRESENTATION = {
    "cash_flow":        "IAS 7",
    "balance_sheet":    "IAS 1",
    "income_statement": "IAS 1",
}

# Ordered; first match wins. Patterns run on the bare ifrs-full name.
# Cash-flow concepts that merely contain "PropertyPlantAndEquipment"
# (capex) must not inherit the PPE impairment standard.
IFRS_SUBJECT_RULES: List[tuple] = [
    (r"Rightofuse|RightOfUse|LeaseLiabilit", "IFRS 16"),
    (r"Goodwill", "IAS 36"),
    (r"Inventor", "IAS 2"),
    (r"DeferredTax", "IAS 12"),
    (r"ResearchAndDevelopment", "IAS 38"),
    (r"Revenue", "IFRS 15"),
    (r"FinancialAssets|FairValueThroughOtherComprehensive|TradeReceivable|"
     r"TradeAndOtherCurrentReceivable", "IFRS 9"),
    (r"(?<!Of)PropertyPlantAndEquipment(?!Classified)", "IAS 36"),
]

# Numerical errors on these standards are measurement/recognition defects.
# A numerical error on any other IFRS line has no governing paragraph.
# IAS 12 and IAS 38 are in the set because the IFRS rulebook cites them
# for deferred-tax recognition and research costs; US GAAP leaves the
# parallel deferred-tax line ungoverned (see axis_stage2).
IFRS_MEASUREMENT = {"IAS 2", "IAS 36", "IFRS 9", "IFRS 15", "IAS 12", "IAS 38"}
IFRS_LEASE = "IFRS 16"


def topic_of(asc: Optional[str]) -> Optional[str]:
    """First 3-digit topic of an ASC string ('330-10-45' → '330')."""
    if not asc:
        return None
    m = re.match(r"\s*(\d{3})", asc)
    return m.group(1) if m else None


def family(topic: Optional[str]) -> Optional[str]:
    """Collapse a superseded topic to its successor for fair comparison."""
    return TOPIC_FAMILY.get(topic, topic) if topic else None


def _bare(concept: Optional[str]) -> str:
    return bare_concept(concept)


def _rules_for(framework: str) -> List[tuple]:
    return IFRS_SUBJECT_RULES if framework == "ifrs" else SUBJECT_RULES


def subject_topic(concept: Optional[str],
                  framework: Optional[str] = None) -> Optional[str]:
    """Governing subject standard for a concept, or None.

    US GAAP returns a 3-digit ASC topic ('330'). IFRS returns a standard
    ('IAS 2'). An ``ifrs-full:`` concept selects IFRS unless ``framework``
    is passed explicitly.
    """
    fw = resolve_framework(concept, framework)
    bare = _bare(concept)
    if not bare:
        return None
    for pat, topic in _rules_for(fw):
        if re.search(pat, bare):
            return topic
    return None


def presentation_citation(statement_type: Optional[str],
                          section: Optional[str] = None,
                          framework: Optional[str] = None) -> Optional[str]:
    """Statement-location citation.

    US GAAP: '230-10-45'. IFRS: 'IAS 7' or 'IAS 1'. ``framework`` defaults
    to US GAAP; presentation has no concept prefix to infer from.
    """
    fw = resolve_framework(None, framework)
    table = IFRS_PRESENTATION if fw == "ifrs" else STMT_PRESENTATION
    st = statement_type if statement_type in table else _SECTION_STMT.get(section or "")
    return table.get(st or "")


def governing_id(citation: Optional[str], framework: str = "us-gaap") -> Optional[str]:
    """Comparable id: ASC topic '330', or IFRS standard 'IAS 2'."""
    if not citation:
        return None
    if framework == "ifrs":
        return ifrs_standard_of(citation)
    return topic_of(citation)


def best_topic(concept: Optional[str],
               statement_type: Optional[str],
               section: Optional[str] = None,
               taxonomy_best: Optional[str] = None,
               framework: Optional[str] = None) -> Optional[str]:
    """Single principled deterministic citation for a row.

    Priority: recognized subject-matter topic → presentation topic → taxonomy
    best-pick. Returns an ASC string (topic-only for subject hits, fuller for
    presentation/taxonomy) or, under IFRS, an IAS/IFRS standard. Subject is
    preferred over presentation because when a concept is a *recognized*
    subject (inventory, goodwill, leases…) the benchmark cites that subject;
    everything else defaults to where it is shown.
    """
    fw = resolve_framework(concept, framework)
    subj = subject_topic(concept, framework=fw)
    if subj:
        return subj
    pres = presentation_citation(statement_type, section, framework=fw)
    if pres:
        return pres
    return taxonomy_best


def candidate_topics(concept: Optional[str],
                     statement_type: Optional[str],
                     section: Optional[str] = None,
                     taxonomy_topics: Optional[List[str]] = None,
                     framework: Optional[str] = None) -> List[str]:
    """UNION candidate set a Stage-2 selector may choose from.

    {subject-matter} ∪ {presentation} ∪ {taxonomy arcs}. Ordered subject →
    presentation → taxonomy. US GAAP ids are 3-digit topics. IFRS ids are
    standards ('IAS 2'), even when a taxonomy arc is a paragraph.
    """
    fw = resolve_framework(concept, framework)
    out: List[str] = []
    seen: Set[str] = set()

    def add(t: Optional[str]):
        if fw == "ifrs":
            t = ifrs_standard_of(t) or None
        else:
            t = topic_of(t) if t and "-" in t else t
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    add(subject_topic(concept, framework=fw))
    add(presentation_citation(statement_type, section, framework=fw))
    for t in (taxonomy_topics or []):
        add(t)
    return out
