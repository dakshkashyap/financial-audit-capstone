"""Synthetic, unvalidated evidence-acquisition prototype; no accounting gold.

Run ``python -m research.evidence_budget --output research/artifacts``.
The demonstration uses deterministic code over observable structured facts, not
an LLM. Its scores establish software behavior, not audit ability or novelty.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


VERSION = "synthetic-evidence-budget-v0.1"
DEFINITIVE = frozenset({"recognition_issue", "supported_recognition"})
CONCLUSIONS = DEFINITIVE | {"suspicious", "insufficient_evidence"}
DISCLAIMER = (
    "Synthetic software prototype with unvalidated contractual criteria. "
    "No real company, filing, accountant gold, fraud finding, model experiment, "
    "or verified novelty claim. Budget units are arbitrary, not API dollars."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _opaque(namespace: str, value: str) -> str:
    return namespace + "_" + hashlib.sha256(value.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Fact:
    fact_id: str
    kind: str
    fields: dict[str, Any]
    text: str


@dataclass(frozen=True)
class Document:
    document_id: str
    document_type: str
    title: str
    cost: int
    facts: tuple[Fact, ...]

    def catalog_entry(self) -> dict[str, Any]:
        return {"document_id": self.document_id,
                "document_type": self.document_type,
                "title": self.title, "cost": self.cost}


@dataclass(frozen=True)
class PublicCase:
    """Observable corpus only. The model starts with initial_view(), not documents."""

    case_id: str
    company_alias: str
    initial_facts: tuple[Fact, ...]
    documents: tuple[Document, ...]

    def initial_view(self) -> dict[str, Any]:
        return {
            "version": VERSION, "case_id": self.case_id,
            "company_alias": self.company_alias,
            "status": "synthetic_unvalidated",
            "task": (
                "Assess this recorded year-end revenue entry under the stated "
                "synthetic contract: control passes on its specified event. "
                "The invoice, contract, and linked delivery record must all "
                "refer to this entry. This simplification is not ASC/IFRS gold "
                "and does not establish fraud or intent. Cite acquired fact "
                "IDs and the provenance links supporting your conclusion."
            ),
            "allowed_conclusions": sorted(CONCLUSIONS),
            "initial_facts": [asdict(f) for f in self.initial_facts],
            "catalog": [d.catalog_entry() for d in self.documents],
        }

    def public_record(self) -> dict[str, Any]:
        """Open corpus export; a budgeted runner must NOT preload documents."""
        return {**self.initial_view(),
                "documents": [asdict(d) for d in self.documents]}


@dataclass(frozen=True)
class PrivateGold:
    """Evaluator-only; never returned by initial_view() or request_document()."""

    case_id: str
    pair_id: str
    conclusion: str
    required_nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    required_paths: tuple[tuple[str, ...], ...]
    required_document_ids: tuple[str, ...]
    required_cost: int


def generate_suite(seed: int = 20261002, companies: int = 8
                   ) -> tuple[list[PublicCase], list[PrivateGold]]:
    """Generate paired issue/control cases with identical initial observations.

    This is a unit-test fixture generator, not a validated dataset generator.
    Companies are synthetic clusters. Seeds and private gold must be withheld
    from inference; deterministic published seeds can otherwise be reconstructed.
    """
    if isinstance(companies, bool) or not isinstance(companies, int) or companies < 1:
        raise ValueError("companies must be a positive integer")
    rng = random.Random(seed)
    cases: list[PublicCase] = []
    gold: list[PrivateGold] = []
    for company_index in range(companies):
        company_nonce = rng.getrandbits(128)
        alias = _opaque("Company", str(company_nonce))
        pair_id = _opaque("pair", str(company_nonce))
        amount = 100_000 + rng.randrange(1, 90) * 1_000
        invoice_id = _opaque("INV", str(company_nonce))
        contract_id = _opaque("CTR", str(company_nonce))
        logistics_ref = _opaque("LOG", str(company_nonce))
        receipt_ids = {
            name: _opaque("RCPT", f"{company_nonce}:{name}")
            for name in ("early", "crossing", "late")
        }
        customer = _opaque("Customer", str(company_nonce))
        # Every variant contains the same chronological early, crossing, and late
        # deliveries. Only the target shipment-to-receipt join changes. Without
        # joining its reference, the event register cannot identify the label.
        transfer_basis = ("dispatch" if company_index % 2 else "customer_acceptance")
        depth = 2 + company_index % 3
        variants = [False, True]
        rng.shuffle(variants)
        for issue in variants:
            case_nonce = rng.getrandbits(128)
            case_id = _opaque("case", str(case_nonce))

            def fact(kind: str, fields: dict[str, Any], text: str,
                     key: str | None = None) -> Fact:
                return Fact(_opaque("fact", f"{case_nonce}:{key or kind}"), kind, fields, text)

            target_receipt = ("late" if issue else "crossing") if transfer_basis == "dispatch" \
                else ("crossing" if issue else "early")
            receipt_id = receipt_ids[target_receipt]
            journal = fact("journal", {
                "invoice_id": invoice_id, "recognition_date": "2025-12-31",
                "period_end": "2025-12-31", "debit_account": "Accounts receivable",
                "credit_account": "Revenue", "debit": amount, "credit": amount,
                "currency": "USD", "customer": customer,
            }, f"At year-end, debit accounts receivable and credit revenue USD {amount:,} "
               f"for {invoice_id}. The entry balances. The customer is new in Q4; "
               "receivables grew and collection occurs after year-end.")
            invoice = fact("invoice", {
                "invoice_id": invoice_id, "contract_id": contract_id,
                "logistics_ref": logistics_ref, "customer": customer, "amount": amount,
            }, f"Invoice {invoice_id} names contract {contract_id}, shipment reference "
               f"{logistics_ref}, customer {customer}, and amount USD {amount:,}.")
            contract = fact("contract", {
                "contract_id": contract_id, "customer": customer,
                "transfer_basis": transfer_basis,
            }, f"The synthetic experimental contract {contract_id} transfers control "
               f"on {transfer_basis}; other events are not its transfer trigger.")
            shipment = fact("shipment", {
                "logistics_ref": logistics_ref, "receipt_id": receipt_id,
                "customer": customer,
            }, f"Shipment reconciliation {logistics_ref} links customer {customer} "
               f"to event register {receipt_id}.")
            event_records: dict[str, Fact] = {}
            for name, dispatched, accepted in (
                ("early", "2025-12-28", "2025-12-30"),
                ("crossing", "2025-12-30", "2026-01-03"),
                ("late", "2026-01-02", "2026-01-03"),
            ):
                rid = receipt_ids[name]
                event_records[name] = fact("receipt_events", {
                    "receipt_id": rid, "customer": customer,
                    "dispatch": dispatched, "customer_acceptance": accepted,
                    "collection_date": "2026-01-15",
                }, f"Delivery event register {rid}: dispatch {dispatched}; customer "
                   f"acceptance {accepted}; collection 2026-01-15. Multiple deliveries "
                   "for this customer occur around year-end; join the shipment reference.",
                   key=f"receipt_events:{rid}")
            events = event_records[target_receipt]
            # Opaque ID ordering prevents a positional early/crossing/late label.
            all_event_records = tuple(sorted(event_records.values(), key=lambda f: f.fact_id))

            def document(kind: str, title: str, cost: int,
                         facts: tuple[Fact, ...]) -> Document:
                return Document(_opaque("doc", f"{case_nonce}:{kind}"),
                                kind, title, cost, facts)

            if depth == 2:
                relevant = [
                    document("invoice_contract", "Invoice and contract packet", 1,
                             (invoice, contract)),
                    document("shipment_receipt", "Shipment and customer event register", 2,
                             (shipment, *all_event_records)),
                ]
            elif depth == 3:
                relevant = [
                    document("invoice", "Invoice register", 1, (invoice,)),
                    document("contract", "Contract extract", 1, (contract,)),
                    document("shipment_receipt", "Shipment and customer event register", 2,
                             (shipment, *all_event_records)),
                ]
            else:
                relevant = [
                    document("invoice", "Invoice register", 1, (invoice,)),
                    document("contract", "Contract extract", 1, (contract,)),
                    document("shipment", "Shipment reconciliation", 1, (shipment,)),
                    document("receipt", "Customer event register", 2, all_event_records),
                ]
            distractors: list[Document] = []
            for kind, title in [("payroll", "Payroll reconciliation"),
                                ("depreciation", "Depreciation schedule"),
                                ("cash", "Office expenditure register")]:
                unrelated = fact(kind, {"amount": amount, "period_end": "2025-12-31"},
                                 f"Routine {kind} entry, USD {amount:,}, reviewed at year-end.")
                distractors.append(document(kind, title, 1, (unrelated,)))
            docs = relevant + distractors
            rng.shuffle(docs)
            cases.append(PublicCase(case_id, alias, (journal,), tuple(docs)))
            fids = tuple(f.fact_id for f in (journal, invoice, contract, shipment, events))
            j, i, c, s, e = fids
            gold.append(PrivateGold(
                case_id, pair_id, "recognition_issue" if issue else "supported_recognition",
                fids, ((j, i), (i, c), (c, e), (i, s), (s, e)),
                ((j, i, c, e), (j, i, s, e)),
                tuple(d.document_id for d in relevant), sum(d.cost for d in relevant),
            ))
    rng.shuffle(cases)
    # The order of gold need not mirror the public corpus, preventing index joins.
    rng.shuffle(gold)
    return cases, gold


class EvidenceSession:
    """Server-owned tool state; the API accepts document IDs only.

    This Python object is not a sandbox against hostile code. A deployed runner
    must retain this object on the server and expose initial_view/request_document
    alone; evaluation and gold belong in a separate process after the run.
    """

    def __init__(self, case: PublicCase, budget: int):
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            raise ValueError("budget must be a nonnegative integer")
        self.case = case
        self.budget = budget
        self.spent = 0
        self._documents = {d.document_id: d for d in case.documents}
        if len(self._documents) != len(case.documents):
            raise ValueError("duplicate document IDs")
        if any(isinstance(d.cost, bool) or not isinstance(d.cost, int) or d.cost < 1
               for d in case.documents):
            raise ValueError("document costs must be positive integers")
        all_ids = [f.fact_id for f in case.initial_facts]
        all_ids.extend(f.fact_id for d in case.documents for f in d.facts)
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("duplicate fact IDs")
        self._acquired: set[str] = set()
        self._trace: list[dict[str, Any]] = []

    def initial_view(self) -> dict[str, Any]:
        return copy.deepcopy({**self.case.initial_view(),
                              "budget": self.budget, "spent": self.spent})

    def request_document(self, document_id: str) -> dict[str, Any]:
        if not isinstance(document_id, str):
            raise ValueError("document_id must be a string")
        document = self._documents.get(document_id)
        payload: dict[str, Any] = {}
        charge = 0
        if document is None:
            status = "unknown_document"
        elif document_id in self._acquired:
            status = "cached"
            payload["document"] = asdict(document)
        elif self.spent + document.cost > self.budget:
            status = "budget_exceeded"
        else:
            status = "acquired"
            charge = document.cost
            self.spent += charge
            self._acquired.add(document_id)
            payload["document"] = asdict(document)
        result = {
            "document_id": document_id, "status": status, "charged_cost": charge,
            "spent": self.spent, "remaining_budget": self.budget - self.spent, **payload,
        }
        self._trace.append({
            "step": len(self._trace) + 1, "action": "request_document",
            "document_id": document_id, "status": status, "charged_cost": charge,
            "spent": self.spent,
            "returned_fact_ids": [f.fact_id for f in document.facts]
                if status in {"acquired", "cached"} and document else [],
            "response_sha256": hashlib.sha256(canonical_json(result).encode()).hexdigest(),
        })
        return copy.deepcopy(result)

    @property
    def trace(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._trace)

    def _observed_ids(self) -> set[str]:
        ids = {f.fact_id for f in self.case.initial_facts}
        # Only successful, server-recorded retrievals establish observation.
        for event in self._trace:
            if event["status"] == "acquired":
                ids.update(f.fact_id for f in self._documents[event["document_id"]].facts)
        return ids


def evaluate(session: EvidenceSession, answer: dict[str, Any],
             gold: PrivateGold) -> dict[str, Any]:
    """Post-run evaluator. Model-supplied traces and labels establish no evidence."""
    if session.case.case_id != gold.case_id:
        raise ValueError("gold case mismatch")
    conclusion = answer.get("conclusion")
    if conclusion not in CONCLUSIONS:
        raise ValueError("invalid conclusion")
    claims = answer.get("cited_fact_ids", [])
    raw_links = answer.get("links", [])
    if not isinstance(claims, list) or any(not isinstance(x, str) for x in claims):
        raise ValueError("cited_fact_ids must be a list of strings")
    if not isinstance(raw_links, list) or any(
        not isinstance(edge, (list, tuple)) or len(edge) != 2
        or any(not isinstance(x, str) for x in edge) for edge in raw_links
    ):
        raise ValueError("links must be fact-ID pairs")
    claimed = set(claims)
    links = {tuple(edge) for edge in raw_links}
    observed = session._observed_ids()
    valid_claims = claimed & observed
    valid_links = {
        edge for edge in links if edge in set(gold.edges)
        and set(edge) <= valid_claims
    }
    path_complete = all(
        set(path) <= valid_claims and all((a, b) in valid_links
                                        for a, b in zip(path, path[1:]))
        for path in gold.required_paths
    )
    acquired_complete = set(gold.required_nodes) <= observed
    correct = conclusion == gold.conclusion
    clean_claims = claimed <= observed and links <= valid_links
    if conclusion in DEFINITIVE:
        outcome = ("supported_correct" if correct and path_complete and clean_claims else
                   "contaminated_correct" if correct and path_complete else
                   "correct_but_unsupported" if correct else
                   "supported_incorrect" if path_complete else "unsupported_incorrect")
    elif conclusion == "insufficient_evidence":
        outcome = "unnecessary_abstention" if acquired_complete else "justified_abstention"
    else:
        outcome = "suspicion_only"
    return {
        "case_id": gold.case_id, "conclusion": conclusion,
        "expected_conclusion": gold.conclusion, "outcome": outcome,
        "diagnosis_correct": correct,
        "supported_decision": correct and path_complete and clean_claims,
        "connected_paths_complete": path_complete,
        "acquired_required_evidence": acquired_complete,
        "evidence_precision": len(valid_claims) / len(claimed) if claimed else 0.0,
        "required_fact_recall": len(valid_claims & set(gold.required_nodes)) /
                                len(gold.required_nodes),
        "edge_precision": len(valid_links) / len(links) if links else 0.0,
        "unsupported_fact_ids": sorted(claimed - observed),
        "invalid_links": sorted([list(edge) for edge in links - valid_links]),
        "spent": session.spent, "budget": session.budget,
    }


def infer_from_observed(facts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Transparent rule baseline using public records and explicit reference joins.

    It has no gold, seed, pair label, expected-cost, or required-path access.
    Its joins reflect this fixture schema; performance is not LLM performance.
    """
    observed = list(facts)
    journals = [f for f in observed if f["kind"] == "journal"]
    if len(journals) != 1:
        raise ValueError("one target journal is required")
    journal = journals[0]

    def match(kind: str, field: str, value: Any) -> dict[str, Any] | None:
        candidates = [f for f in observed if f["kind"] == kind
                      and f["fields"].get(field) == value]
        return candidates[0] if len(candidates) == 1 else None

    invoice = match("invoice", "invoice_id", journal["fields"]["invoice_id"])
    contract = (match("contract", "contract_id", invoice["fields"]["contract_id"])
                if invoice else None)
    shipment = (match("shipment", "logistics_ref", invoice["fields"]["logistics_ref"])
                if invoice else None)
    events = (match("receipt_events", "receipt_id", shipment["fields"]["receipt_id"])
              if shipment else None)
    acquired = [f for f in (journal, invoice, contract, shipment, events) if f]
    answer = {"conclusion": "insufficient_evidence",
              "cited_fact_ids": [f["fact_id"] for f in acquired], "links": []}
    if invoice:
        answer["links"].append([journal["fact_id"], invoice["fact_id"]])
    if invoice and contract:
        answer["links"].append([invoice["fact_id"], contract["fact_id"]])
    if invoice and shipment:
        answer["links"].append([invoice["fact_id"], shipment["fact_id"]])
    if shipment and events:
        answer["links"].append([shipment["fact_id"], events["fact_id"]])
    if not all((invoice, contract, shipment, events)):
        return answer
    assert invoice and contract and shipment and events
    customer = journal["fields"]["customer"]
    if any(f["fields"].get("customer") != customer
           for f in (invoice, contract, shipment, events)):
        return answer
    if invoice["fields"]["amount"] != journal["fields"]["credit"]:
        return answer
    basis = contract["fields"]["transfer_basis"]
    if basis not in {"dispatch", "customer_acceptance"} or basis not in events["fields"]:
        return answer
    transfer_date = date.fromisoformat(events["fields"][basis])
    recorded_date = date.fromisoformat(journal["fields"]["recognition_date"])
    answer["links"].append([contract["fact_id"], events["fact_id"]])
    answer["conclusion"] = ("recognition_issue" if transfer_date > recorded_date
                            else "supported_recognition")
    return answer


def run_observable_policy(case: PublicCase, budget: int, policy: str
                          ) -> tuple[EvidenceSession, dict[str, Any]]:
    """Deterministic demonstration; no private gold is accepted here."""
    if policy not in {"catalog_order", "document_type_priority"}:
        raise ValueError("unknown policy")
    session = EvidenceSession(case, budget)
    initial = session.initial_view()
    catalog = initial["catalog"]
    if policy == "document_type_priority":
        priority = {"invoice_contract": 0, "invoice": 0, "contract": 1,
                    "shipment_receipt": 2, "shipment": 2, "receipt": 3}
        catalog = sorted(catalog,
                         key=lambda d: priority.get(d["document_type"], 10))
    facts = list(initial["initial_facts"])
    for entry in catalog:
        if entry["cost"] > session.budget - session.spent:
            continue
        result = session.request_document(entry["document_id"])
        if result["status"] == "acquired":
            facts.extend(result["document"]["facts"])
        answer = infer_from_observed(facts)
        if answer["conclusion"] in DEFINITIVE:
            return session, answer
    return session, infer_from_observed(facts)


def build_demo(cases: list[PublicCase], gold: list[PrivateGold]) -> dict[str, Any]:
    gold_by_id = {g.case_id: g for g in gold}
    results: list[dict[str, Any]] = []
    for policy in ("catalog_order", "document_type_priority"):
        for budget in (0, 2, 3, 4, 5, 8):
            records: list[dict[str, Any]] = []
            for case in cases:
                session, answer = run_observable_policy(case, budget, policy)
                score = evaluate(session, answer, gold_by_id[case.case_id])
                records.append({"company_alias": case.company_alias, "score": score,
                                "answer": answer, "trace": session.trace})
            results.append({
                "policy": policy, "budget": budget, "case_count": len(cases),
                "supported_decision_rate": sum(r["score"]["supported_decision"]
                                               for r in records) / len(records),
                "mean_spent": sum(r["score"]["spent"] for r in records) / len(records),
                "abstention_rate": sum(r["score"]["conclusion"] == "insufficient_evidence"
                                       for r in records) / len(records),
                "records": records,
            })
    return {"version": VERSION, "disclaimer": DISCLAIMER,
            "experiment_type": "deterministic_software_demonstration",
            "synthetic_company_count": len({c.company_alias for c in cases}),
            "case_count": len(cases), "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("research/artifacts"))
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--companies", type=int, default=8)
    args = parser.parse_args()
    cases, gold = generate_suite(args.seed, args.companies)
    args.output.mkdir(parents=True, exist_ok=True)
    private_dir = args.output / "private"
    private_dir.mkdir(exist_ok=True)
    (args.output / "evidence_budget_public.json").write_text(canonical_json({
        "version": VERSION, "disclaimer": DISCLAIMER,
        "cases": [c.public_record() for c in cases],
    }), encoding="utf-8")
    (private_dir / "evidence_budget_gold.json").write_text(canonical_json({
        "version": VERSION, "warning": "Evaluator only; do not supply to inference.",
        "seed": args.seed, "gold": [asdict(g) for g in gold],
    }), encoding="utf-8")
    demo = build_demo(cases, gold)
    (args.output / "evidence_budget_demo.json").write_text(canonical_json(demo), encoding="utf-8")
    print(canonical_json({"case_count": len(cases), "company_count": args.companies,
                          "output": str(args.output), "status": "synthetic_unvalidated"}), end="")


if __name__ == "__main__":
    main()
