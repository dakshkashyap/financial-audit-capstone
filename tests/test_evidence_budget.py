"""Safety and provenance invariants for the synthetic acquisition prototype."""
from dataclasses import asdict, replace
import unittest

from research.evidence_budget import (
    EvidenceSession, canonical_json, evaluate,
    generate_suite, infer_from_observed, run_observable_policy,
)


class EvidenceBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.gold = generate_suite()
        cls.gold_by_id = {g.case_id: g for g in cls.gold}

    def full_session(self, case=None):
        case = case or self.cases[0]
        session = EvidenceSession(case, 100)
        facts = session.initial_view()["initial_facts"]
        for document in case.documents:
            facts.extend(session.request_document(document.document_id)["document"]["facts"])
        return session, infer_from_observed(facts)

    def test_rebuild_is_byte_identical_and_clustered(self):
        cases, gold = generate_suite()
        self.assertEqual(canonical_json([c.public_record() for c in cases]),
                         canonical_json([c.public_record() for c in self.cases]))
        self.assertEqual(canonical_json([asdict(g) for g in gold]),
                         canonical_json([asdict(g) for g in self.gold]))
        self.assertEqual(len(cases), 16)
        self.assertEqual(len({c.company_alias for c in cases}), 8)
        self.assertEqual({len(g.required_document_ids) for g in gold}, {2, 3, 4})
        self.assertEqual({g.required_cost for g in gold}, {3, 4, 5})

    def test_counterfactuals_share_amounts_dates_motifs_and_balance(self):
        grouped = {}
        for case in self.cases:
            grouped.setdefault(case.company_alias, []).append(case)
        for pair in grouped.values():
            self.assertEqual(len(pair), 2)
            first, second = pair
            journal1, journal2 = first.initial_facts[0], second.initial_facts[0]
            self.assertEqual(journal1.fields, journal2.fields)
            self.assertEqual(journal1.text, journal2.text)
            self.assertEqual(journal1.fields["debit"], journal1.fields["credit"])
            self.assertEqual(sorted((d.document_type, d.cost) for d in first.documents),
                             sorted((d.document_type, d.cost) for d in second.documents))
            # Ignoring opaque IDs and textual reference copies, only the selected
            # shipment receipt differs. Every receipt timeline is identical.
            def content(case, kind):
                return sorted((canonical_json(f.fields) for d in case.documents
                               for f in d.facts if f.kind == kind))
            for kind in ("invoice", "contract", "receipt_events"):
                self.assertEqual(content(first, kind), content(second, kind))
            self.assertNotEqual(content(first, "shipment"), content(second, "shipment"))
            verdicts = {self.gold_by_id[c.case_id].conclusion for c in pair}
            self.assertEqual(verdicts, {"recognition_issue", "supported_recognition"})
        for case in self.cases:
            for document in case.documents:
                for fact in document.facts:
                    if fact.kind == "receipt_events":
                        self.assertLessEqual(fact.fields["dispatch"],
                                             fact.fields["customer_acceptance"])

    def test_tool_interface_has_no_private_gold(self):
        forbidden = {"pair_id", "required_nodes", "required_paths", "edges",
                     "required_cost", "required_document_ids", "expected_conclusion"}

        def check(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    check(child)
            elif isinstance(value, (tuple, list)):
                for child in value:
                    check(child)

        for case in self.cases:
            session = EvidenceSession(case, 100)
            initial = session.initial_view()
            self.assertNotIn("documents", initial)
            check(initial)
            for document in case.documents:
                check(session.request_document(document.document_id))

    def test_no_overrun_no_double_charge_and_denied_fetch_has_no_facts(self):
        case = self.cases[0]
        expensive = next(d for d in case.documents if d.cost == 2)
        session = EvidenceSession(case, 1)
        denied = session.request_document(expensive.document_id)
        self.assertEqual(denied["status"], "budget_exceeded")
        self.assertNotIn("document", denied)
        self.assertEqual(session.spent, 0)
        self.assertEqual(session.trace[0]["returned_fact_ids"], [])
        cheap = next(d for d in case.documents if d.cost == 1)
        self.assertEqual(session.request_document(cheap.document_id)["charged_cost"], 1)
        self.assertEqual(session.request_document(cheap.document_id)["status"], "cached")
        self.assertEqual(session.request_document(cheap.document_id)["charged_cost"], 0)
        self.assertEqual(session.spent, 1)
        self.assertEqual(session.request_document("unknown")["status"], "unknown_document")
        self.assertEqual(session.spent, 1)

    def test_invalid_budget_cost_and_duplicate_ids_rejected(self):
        for budget in (-1, True, 1.5, "5"):
            with self.assertRaises(ValueError):
                EvidenceSession(self.cases[0], budget)
        case = self.cases[0]
        for cost in (0, -1, True, 1.5):
            doc = replace(case.documents[0], cost=cost)
            with self.assertRaises(ValueError):
                EvidenceSession(replace(case, documents=(doc,)), 10)
        with self.assertRaises(ValueError):
            EvidenceSession(replace(case, documents=(case.documents[0], case.documents[0])), 10)

    def test_returned_objects_cannot_mutate_server_trace_or_evidence(self):
        case = self.cases[0]
        session = EvidenceSession(case, 10)
        initial = session.initial_view()
        initial["initial_facts"][0]["fields"]["credit"] = -99
        doc = case.documents[0]
        response = session.request_document(doc.document_id)
        response["document"]["facts"][0]["fields"].clear()
        trace = session.trace
        trace[0]["returned_fact_ids"].clear()
        self.assertTrue(session.trace[0]["returned_fact_ids"])
        self.assertTrue(session.request_document(doc.document_id)["document"]["facts"][0]["fields"])
        self.assertGreater(session.initial_view()["initial_facts"][0]["fields"]["credit"], 0)

    def test_guessed_correct_label_and_gold_ids_do_not_get_process_credit(self):
        case = self.cases[0]
        gold = self.gold_by_id[case.case_id]
        session = EvidenceSession(case, 0)
        answer = {"conclusion": gold.conclusion,
                  "cited_fact_ids": list(gold.required_nodes), "links": list(gold.edges)}
        score = evaluate(session, answer, gold)
        self.assertTrue(score["diagnosis_correct"])
        self.assertEqual(score["outcome"], "correct_but_unsupported")
        self.assertFalse(score["supported_decision"])
        self.assertEqual(len(score["unsupported_fact_ids"]), 4)
        self.assertAlmostEqual(score["evidence_precision"], 1 / 5)

    def test_observable_join_policy_recovers_all_gold_at_sufficient_budget(self):
        for case in self.cases:
            gold = self.gold_by_id[case.case_id]
            session, answer = run_observable_policy(case, gold.required_cost,
                                                   "document_type_priority")
            score = evaluate(session, answer, gold)
            self.assertEqual(score["outcome"], "supported_correct")
            self.assertEqual(session.spent, gold.required_cost)
            self.assertEqual(score["edge_precision"], 1)

    def test_missing_single_provenance_edge_blocks_supported_decision(self):
        session, answer = self.full_session()
        gold = self.gold_by_id[session.case.case_id]
        self.assertTrue(evaluate(session, answer, gold)["supported_decision"])
        answer["links"].pop()
        score = evaluate(session, answer, gold)
        self.assertTrue(score["acquired_required_evidence"])
        self.assertEqual(score["required_fact_recall"], 1)
        self.assertFalse(score["connected_paths_complete"])
        self.assertFalse(score["supported_decision"])

    def test_unacquired_claim_and_invalid_link_cannot_earn_credit(self):
        session, answer = self.full_session()
        gold = self.gold_by_id[session.case.case_id]
        answer["cited_fact_ids"].append("invented_fact")
        answer["links"].append([gold.required_nodes[0], "invented_fact"])
        score = evaluate(session, answer, gold)
        self.assertEqual(score["unsupported_fact_ids"], ["invented_fact"])
        self.assertLess(score["evidence_precision"], 1)
        self.assertLess(score["edge_precision"], 1)
        self.assertEqual(len(score["invalid_links"]), 1)
        self.assertFalse(score["supported_decision"])
        self.assertEqual(score["outcome"], "contaminated_correct")

    def test_all_pairs_graph_spam_does_not_earn_supported_decision(self):
        session, answer = self.full_session()
        gold = self.gold_by_id[session.case.case_id]
        observed = [f.fact_id for f in session.case.initial_facts]
        observed.extend(f.fact_id for d in session.case.documents for f in d.facts)
        answer["cited_fact_ids"] = observed
        answer["links"] = [[a, b] for a in observed for b in observed if a != b]
        score = evaluate(session, answer, gold)
        self.assertTrue(score["connected_paths_complete"])
        self.assertFalse(score["supported_decision"])
        self.assertEqual(score["outcome"], "contaminated_correct")
        self.assertGreater(len(score["invalid_links"]), 0)

    def test_abstention_separates_missing_evidence_from_unused_evidence(self):
        case = self.cases[0]
        gold = self.gold_by_id[case.case_id]
        session, answer = run_observable_policy(case, 0, "document_type_priority")
        self.assertEqual(evaluate(session, answer, gold)["outcome"], "justified_abstention")
        session, answer = self.full_session(case)
        answer["conclusion"] = "insufficient_evidence"
        self.assertEqual(evaluate(session, answer, gold)["outcome"], "unnecessary_abstention")
        answer["conclusion"] = "suspicious"
        score = evaluate(session, answer, gold)
        self.assertEqual(score["outcome"], "suspicion_only")
        self.assertFalse(score["supported_decision"])

    def test_receipt_document_alone_and_wrong_customer_cannot_establish_conclusion(self):
        case = self.cases[0]
        initial = [asdict(f) for f in case.initial_facts]
        events = [asdict(f) for d in case.documents for f in d.facts
                  if f.kind == "receipt_events"]
        self.assertEqual(infer_from_observed(initial + events)["conclusion"],
                         "insufficient_evidence")
        observed = initial + [asdict(f) for d in case.documents for f in d.facts]
        for fact in observed:
            if fact["kind"] == "contract":
                fact["fields"]["customer"] = "wrong_customer"
        self.assertEqual(infer_from_observed(observed)["conclusion"], "insufficient_evidence")

    def test_case_mismatch_and_malformed_answers_rejected(self):
        session, answer = self.full_session()
        other = next(g for g in self.gold if g.case_id != session.case.case_id)
        with self.assertRaises(ValueError):
            evaluate(session, answer, other)
        gold = self.gold_by_id[session.case.case_id]
        for bad in ({"conclusion": "fraud"},
                    {"conclusion": "suspicious", "cited_fact_ids": "invented"},
                    {"conclusion": "suspicious", "links": [["x"]]}):
            with self.assertRaises(ValueError):
                evaluate(session, bad, gold)


if __name__ == "__main__":
    unittest.main()
