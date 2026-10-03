"""Behavioral tests for partial signed synthetic transaction evidence."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ComponentEvidence(unittest.TestCase):
    def test_signed_decimal_components_and_unicode_minus(self):
        from core.stage0_common import build_transactions
        tx = build_transactions("[Cash] receipts: +1,234.50 (increase); payment: −234.25 (decrease); adjustment: +0.05 (increase)")
        self.assertEqual(tx.evidence_format, "synthetic_signed_components")
        self.assertAlmostEqual(tx.entries[0].value, 1000.30)
        self.assertEqual(tx.entries[0].component_count, 3)
        self.assertIsNone(tx.entries[0].orig_index)

    def test_parenthesized_negative_component_keeps_its_sign(self):
        from core.stage0_common import build_transactions, entry_values_match
        tx = build_transactions("[Treasury stock] purchases: ($1,234.50) (decrease); reissue: +234.25 (increase)")
        self.assertEqual(tx.entries[0].value, -1000.25)
        self.assertTrue(entry_values_match(tx.entries[0], -1000.25))
        self.assertFalse(entry_values_match(tx.entries[0], 1000.25))

    def test_unknown_direction_or_partial_component_line_abstains(self):
        from core.stage0_common import build_transactions
        bodies = ["receipt: 100 (increase)", "receipt: +100 (decrease)",
                  "receipt: +12,34 (increase)", "receipt: +100 (increase); another: unknown",
                  "receipt: extra: +100 (increase)", "receipt: +100 (increase);",
                  "receipt: +100 (increase) but the total is 250"]
        for body in bodies:
            with self.subTest(body=body):
                tx = build_transactions("[Cash] " + body)
                self.assertEqual(tx.entries, [])
                self.assertEqual(tx.rejected_labels, ["Cash"])

    def test_totals_and_supporting_review_numbers_are_not_movements(self):
        from core.stage0_common import build_transactions
        tx = build_transactions(
            "Report 2024 says 1,000.\n[Total assets] total: +1,000 (increase)\n"
            "[Cash] collection: +100 (increase)\nSupporting facts (period-end reviews):\n"
            "- Inventory: NRV 40; carrying amount 70.\n[Inventory] reviewer: +70 (increase)")
        self.assertEqual([entry.label for entry in tx.entries], ["Cash"])
        self.assertTrue(tx.supporting_facts_present)

    def test_label_sum_localizes_a_value_error_without_original_row_id(self):
        from approaches.stage0_deterministic_gate.stage0a import verify
        item = {"table": "[row 4]: Cash | 140 [SEP] [row 9]: Inventory | 75 [SEP]",
                "transaction_data": "[Cash] receipts: +125 (increase); payments: −25 (decrease)\n"
                                    "[Inventory] receipts: +100 (increase); consumption: −25 (decrease)"}
        result = verify(item)
        self.assertEqual(result.primary.problematic_entry, 4)
        self.assertEqual(result.primary.correct_value, 100)

    def test_decimal_and_sign_errors_are_not_discarded_by_legacy_tolerance(self):
        from approaches.stage0_deterministic_gate.stage0a import verify
        for stated, supported in [(100.10, "+100.00 (increase)"), (100, "−100 (decrease)")]:
            with self.subTest(stated=stated):
                result = verify({"table": f"[row 1]: Cash | {stated} [SEP]",
                                 "transaction_data": "[Cash] movement: " + supported})
                self.assertIsNotNone(result.primary)

    def test_ambiguous_duplicate_labels_do_not_localize_by_coincidental_value(self):
        from approaches.stage0_deterministic_gate.stage0a import verify
        result = verify({"table": "[row 1]: Cash | 110 [SEP]",
                         "transaction_data": "[Cash] receipts: +100 (increase)\n[Cash] adjustment: +10 (increase)"})
        self.assertIsNone(result.primary)

    def test_legacy_explanation_format_keeps_historical_behavior(self):
        from core.stage0_common import build_transactions, entry_values_match
        tx = build_transactions("[contributing to row 3]: Cash\n[Explanation: $100 = $125 - $25]")
        self.assertEqual(tx.expected_for_index(3).value, 100)
        self.assertEqual(tx.evidence_format, "legacy")
        self.assertTrue(entry_values_match(tx.entries[0], -100))

    def test_partial_evidence_or_matching_amount_under_wrong_label_cannot_certify_clean(self):
        from approaches.full_pipeline.pipeline import run_pipeline
        from core.taxonomy_graph import TaxonomyGraph
        graph = TaxonomyGraph()
        graph._xml_content, graph._available = "", False
        table = ("[row 1]: Cash | 100 [SEP] [row 2]: Total assets | 100 [SEP] "
                 "[row 3]: Total liabilities | 60 [SEP] [row 4]: Total equity | 40 [SEP] "
                 "[row 5]: Total liabilities and equity | 100 [SEP]")
        narratives = ["[Different unsupported account] balance: +100 (increase)",
                      "[Cash] inflow: +200 (increase); outflow: −100 (decrease)\n"
                      "Supporting facts (period-end reviews):\n- Inventory: carrying 50; NRV 25; no write-down."]
        for narrative in narratives:
            with self.subTest(narrative=narrative):
                record = run_pipeline({"table": table, "transaction_data": narrative,
                                       "sheet_type": "balance sheet"}, graph)
                self.assertFalse(record.verified_consistent)


if __name__ == "__main__":
    unittest.main()
