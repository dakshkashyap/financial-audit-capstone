"""Regression checks for audited inference, citation and repair boundaries.

These tests perform no model calls and require no downloaded taxonomy.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def error(row, citation, error_type="Numerical Error"):
    return {"Error Identification": {"Error Type": error_type,
                                      "Problematic Entry": f"Row {row}"},
            "Standards Citation": citation}


class CitationMetrics(unittest.TestCase):
    def test_topic_credit_is_separate_from_paragraph_credit(self):
        from core.metrics import em_citation_exact, em_citation_topic, em_standards_topk
        self.assertEqual(em_standards_topk("ASC 210", "ASC 210-10-45-1"), 1)
        self.assertEqual(em_citation_topic("ASC 210", "ASC 210-10-45-1"), 1)
        self.assertEqual(em_citation_exact("ASC 210", "ASC 210-10-45-1"), 0)
        self.assertEqual(em_citation_exact("ASC 210-10-45-10", "ASC 210-10-45-1"), 0)
        self.assertEqual(em_citation_exact("FASB ASC 210-10-45-1", "ASC 210-10-45-1"), 1)

    def test_ifrs_wrong_paragraph_and_cross_framework_are_misses(self):
        from core.metrics import em_citation_exact, em_citation_topic
        self.assertEqual(em_citation_exact("IAS 36.90", "IAS 36.59"), 0)
        self.assertEqual(em_citation_topic("IAS 36.90", "IAS 36.59"), 1)
        self.assertEqual(em_citation_exact("IAS 36 paragraph 59", "IAS 36.59"), 1)
        self.assertEqual(em_citation_exact("ASC 360-10-35-17", "IAS 36.59"), 0)

    def test_top_one_keeps_appearance_order_across_frameworks(self):
        from core.metrics import em_citation_exact
        pred = "IAS 36.90 and ASC 210-10-45-1"
        self.assertEqual(em_citation_exact(pred, "ASC 210-10-45-1", k=1), 0)
        self.assertEqual(em_citation_exact(pred, "ASC 210-10-45-1", k=2), 1)
        self.assertEqual(em_citation_exact("ASC 210 and ASC 210-10-45-1",
                                          "ASC 210-10-45-1", k=1), 0)


class CitationValidation(unittest.TestCase):
    def test_arithmetic_fault_cannot_promote_the_same_reference_to_governing_citation(self):
        from approaches.full_pipeline.pipeline import AuditRecord
        from approaches.full_pipeline.run_intelliaudit import _deterministic_parsed
        record = AuditRecord(judgment="Incorrect", abstained=False, deterministic=True,
                             error_type="Numerical Error", problematic_entry=1,
                             stated_value=150, correct_value=100,
                             citation_primary="210-10-45-1", citation_candidates=["210-10-45-1"],
                             citation_source="taxonomy")
        item = {"table": "[row 1]: Cash | 150 [SEP]"}
        info = _deterministic_parsed(item, record)["Information for error 1"]
        self.assertIsNone(info["Standards Citation"])
        self.assertEqual(info["Citation Candidates"], ["ASC 210-10-45-1"])
        self.assertFalse(record.to_dict()["citation_applicability_verified"])
        # Model an explicitly supplied external verification decision, not a
        # capability of any current automatic checker.
        record.citation_applicability_verified = True
        self.assertEqual(_deterministic_parsed(item, record)["Information for error 1"]["Standards Citation"],
                         "ASC 210-10-45-1")

    def test_legacy_public_adapter_keeps_reference_hint_but_abstains_from_citation(self):
        from approaches.full_pipeline.run_audit import run_audit
        reference = {"citation": "FASB ASC 210-10-45-1", "citation_source": "taxonomy"}
        with patch("approaches.full_pipeline.run_audit._audit_concept", return_value=reference):
            result = run_audit("Cash", source="concept")
        self.assertIsNone(result["citation"])
        self.assertEqual(result["citation_candidate"], "FASB ASC 210-10-45-1")
        self.assertFalse(result["citation_applicability_verified"])

    def test_invalid_pick_abstains_preserving_original_for_every_error(self):
        from approaches.stage2_llm_audit.stage2_llm import apply_citation_snap
        statement = SimpleNamespace(framework="us-gaap", rows=[
            SimpleNamespace(row_idx=1, asc_primary="210-10-45-1",
                            asc_candidates=["210-10-45-1"]),
            SimpleNamespace(row_idx=2, asc_primary="330-10-35-1",
                            asc_candidates=["330-10-35-1"]),
        ])
        original = {"General Judgment": "Incorrect",
                    "Information for error 1": error(1, "ASC 999-99-99-9"),
                    "Information for error 2": error(2, "ASC 330-10-35-1")}
        untouched = copy.deepcopy(original)
        result = apply_citation_snap(original, statement)
        first = result["Information for error 1"]
        second = result["Information for error 2"]
        self.assertIsNone(first["Standards Citation"])
        self.assertEqual(first["Raw Standards Citation"], "ASC 999-99-99-9")
        self.assertEqual(second["Standards Citation"], "ASC 330-10-35-1")
        self.assertEqual(original, untouched)

    def test_absent_row_and_topic_only_cannot_invent_a_paragraph(self):
        from approaches.stage2_llm_audit.stage2_llm import apply_citation_snap
        statement = SimpleNamespace(framework="us-gaap", rows=[
            SimpleNamespace(row_idx=1, asc_primary="210", asc_candidates=["210"]),
        ])
        for row, citation in [(99, "ASC 210-10-45-1"), (1, "ASC 210")]:
            parsed = {"Information for error 1": error(row, citation)}
            result = apply_citation_snap(parsed, statement)
            self.assertIsNone(result["Information for error 1"]["Standards Citation"])

    def test_ifrs_exact_pick_keeps_ifrs_namespace(self):
        from approaches.stage2_llm_audit.stage2_llm import apply_citation_snap
        statement = SimpleNamespace(framework="ifrs", rows=[
            SimpleNamespace(row_idx=1, asc_primary="IAS 2.36", asc_candidates=["IAS 2.36", "IAS 2"]),
        ])
        parsed = {"Information for error 1": error(1, "IAS 2 paragraph 36")}
        result = apply_citation_snap(parsed, statement)
        self.assertEqual(result["Information for error 1"]["Standards Citation"], "IAS 2.36")

    def test_partial_consistency_cannot_erase_an_error_finding(self):
        from approaches.stage2_llm_audit.stage2_llm import apply_consistency_veto
        parsed = {"General Judgment": "Incorrect",
                  "Information for error 1": error(1, None)}
        result, vetoed = apply_consistency_veto(parsed, verified_consistent=True,
                                              original_table="original")
        self.assertFalse(vetoed)
        self.assertEqual(result, parsed)

    def test_ifrs_taxonomy_retains_exact_paragraph_candidates(self):
        from approaches.stage1_taxonomy_citation.stage1_arelle import run_stage1
        graph = SimpleNamespace(available=True, citations=lambda concept: ["IAS 2.36"]
                                if concept == "Inventories" else [])
        item = {"framework": "ifrs", "sheet_type": "statement of financial position",
                "table": "[row 1]: Inventories | 150 [SEP]"}
        result = run_stage1(item, graph=graph, framework="ifrs")
        row = result.statement.rows[0]
        self.assertEqual(row.asc_primary, "IAS 2.36")
        self.assertIn("IAS 2.36", row.asc_candidates)
        self.assertEqual(result.citation_sources[1], "taxonomy")


class LocalizedRepair(unittest.TestCase):
    def test_repeated_value_is_repaired_only_on_localized_row(self):
        from approaches.full_pipeline.run_intelliaudit import _revise
        table = "[row 1]: Cash | 100 [SEP] [row 2]: Inventory | 100 [SEP]"
        record = SimpleNamespace(error_type="Numerical Error", problematic_entry=2,
                                 stated_value=100., correct_value=75.)
        self.assertEqual(_revise(table, record),
                         "[row 1]: Cash | 100 [SEP] [row 2]: Inventory | 75 [SEP]")

    def test_missing_or_unverified_value_cell_is_not_mutated(self):
        from approaches.full_pipeline.run_intelliaudit import _revise
        table = "[row 1]: Assets [SEP] [row 2]: Inventory | 100 [SEP]"
        for row, stated in [(1, 100.), (2, 10.), (3, 100.)]:
            record = SimpleNamespace(error_type="Numerical Error", problematic_entry=row,
                                     stated_value=stated, correct_value=75.)
            self.assertEqual(_revise(table, record), table)


class ExamBoundary(unittest.TestCase):
    def test_inference_projection_ignores_answer_metadata_and_identifier(self):
        from approaches.full_pipeline.run_iab_exam import to_item
        exam = {"sample_id": "R01-answer-code", "statement_text": "statement",
                "transaction_data": "support", "metadata": {"statement_type": "BalanceSheet",
                "company": "Example", "rule_id": "R01", "answer": "ASC 210"}}
        first = to_item(exam)
        exam["sample_id"] = "different-answer-code"
        exam["metadata"]["rule_id"] = "R12"
        self.assertEqual(first, to_item(exam))
        self.assertEqual(set(first), {"table", "transaction_data", "sheet_type", "company"})

    def test_requested_small_sample_size_is_respected(self):
        from approaches.full_pipeline.run_iab_exam import load_exam
        with tempfile.TemporaryDirectory() as directory:
            bench = Path(directory)
            path = bench / "data/benchmark/exam.jsonl"
            path.parent.mkdir(parents=True)
            rows = [{"sample_id": f"{statement}-{index}",
                     "metadata": {"statement_type": statement}}
                    for statement in ["BalanceSheet", "IncomeStatement", "CashFlow"]
                    for index in range(4)]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            for n in [1, 2, 4, 5, 8, 10]:
                self.assertEqual(len(load_exam(bench, full=False, n=n, seed=42)), n)

    def test_citation_recall_excludes_non_citable_cases_and_reports_false_cites(self):
        from approaches.full_pipeline.run_iab_exam import score_preds, T
        scorer = SimpleNamespace(
            score_detection=lambda pred, key: {
                "em_general_judgment": int(pred["General Judgment"] == key["general_judgement"]),
                "em_error_type": int(pred["error_type"] == key["error_type"].lower()),
                "em_error_entry": int(pred["problematic_entry"] == key["row"])},
            score_citation=lambda pred, gt, **kwargs: None if not gt["citable"] else {
                "em_topic": int(pred == gt["asc_full"]), "em_subtopic": int(pred == gt["asc_full"]),
                "em_full": int(pred == gt["asc_full"])},
        )
        key = {str(index): {"error_type": "Numerical Error", "row": 1,
                "general_judgement": "Incorrect", "ground_truth_citations": {
                "citable": index != 2, "asc_full": "ASC 210-10-45-1"}}
                for index in range(1, 5)}
        preds = [{"sample_id": "1", "stage0_fired": True, "predicted_error_type": "Numerical Error",
                  "predicted_row": 1, "predicted_asc": "ASC 210-10-45-1"},
                 {"sample_id": "2", "predicted_asc": "ASC 210-10-45-1"},
                 {"sample_id": "3"},
                 {"sample_id": "4", "predicted_judgment": "Incorrect", "predicted_error_type": "Missing Row",
                  "predicted_row": 1, "predicted_asc": "ASC 210-10-45-1"}]
        old_path = list(sys.path)
        try:
            with patch.dict(sys.modules, {"scorer": scorer}), contextlib.redirect_stdout(io.StringIO()):
                result = score_preds(preds, key, Path("/tmp/no-external-benchmark-needed"), T(False))
        finally:
            sys.path[:] = old_path
        self.assertEqual(result["citable_n"], 3)
        self.assertAlmostEqual(result["full_r"], 100 * 2 / 3)
        self.assertEqual(result["noncitable_citations"], 1)
        self.assertEqual(result["joint_detection_em"], 25)


class HistoricalReplayBoundary(unittest.TestCase):
    def replay(self, items, predictions, record):
        from approaches.full_pipeline import pipeline_eval
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{pipeline_eval.PRED_MODEL}_correct_predictions.json"
            path.write_text(json.dumps(predictions))
            with patch.object(pipeline_eval, "RESULTS_DIR", directory), \
                    patch.dict(pipeline_eval.LOADERS, {"correct": lambda **kwargs: items}), \
                    patch.object(pipeline_eval, "run_pipeline", return_value=record):
                return pipeline_eval.eval_split("correct", None, len(items), 42)

    def test_clean_abstention_and_partial_consistency_do_not_create_accuracy(self):
        from approaches.full_pipeline.pipeline import AuditRecord
        from approaches.full_pipeline.intelliaudit_runner import _table_hash
        item = {"table": "[row 1]: Cash | 100 [SEP]", "general_judgement": "Correct"}
        parsed = {"General Judgment": "Incorrect",
                  "Information for error 1": error(1, None)}
        result = self.replay([item], [{"item_idx": 0, "table_hash": _table_hash(item),
                                      "parsed": parsed}], AuditRecord(verified_consistent=True))
        self.assertEqual(result["config_B_gen_judgment_em"], 0)
        self.assertEqual(result["config_Aveto_gen_judgment_em"], 0)
        self.assertEqual(result["vetoes_applied"], 0)
        self.assertEqual(result["fp_rate_veto"], 1)

    def test_missing_failed_and_misaligned_predictions_stay_in_denominator(self):
        from approaches.full_pipeline.pipeline import AuditRecord
        from approaches.full_pipeline.intelliaudit_runner import _table_hash
        items = [{"table": f"[row 1]: Cash | {amount} [SEP]", "general_judgement": "Correct"}
                 for amount in [100, 200, 300, 400]]
        predictions = [
            {"item_idx": 0, "table_hash": _table_hash(items[0]), "parsed": {"General Judgment": "Correct"}},
            {"item_idx": 1, "table_hash": _table_hash(items[1]), "parsed": {"General Judgment": "Correct"},
             "error": "provider_failure"},
            {"item_idx": 2, "table_hash": _table_hash(items[0]), "parsed": {"General Judgment": "Correct"}},
        ]
        result = self.replay(items, predictions, AuditRecord())
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["config_A_gen_judgment_em"], 0.25)
        self.assertEqual(result["llm_prediction_failures"], 3)

    def test_unparseable_answers_are_not_incorrect_predictions(self):
        from approaches.full_pipeline.pipeline_eval import _llm_judgment
        for parsed in [None, {}, [], "Incorrect", {"General Judgment": "maybe"}]:
            self.assertEqual(_llm_judgment(parsed), "Unverified")


if __name__ == "__main__":
    unittest.main()
