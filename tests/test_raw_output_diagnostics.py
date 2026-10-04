"""Secondary diagnostics never repair or replace the primary protocol."""
import copy
import json
import unittest

from research.diagnose_raw_outputs import diagnostic_output_path, field_outcomes, inspect_response, normalize_complete_object, repair_schema
from research.harness import parse_prediction, ResponseError
from tests.test_research_harness import gold, prediction


class RawOutputDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.case = {"statement_text": "[row 1]: Cash | $100", "transaction_data": "Cash movement +80"}

    def response(self, value, finish="stop"):
        return {"status": "ok", "content": json.dumps(value), "finish_reason": finish}

    def test_missing_reason_can_have_field_agreement_but_remains_primary_failure(self):
        value = prediction()
        del value["reason"]
        diagnostic = inspect_response(self.response(value), "invalid_response", self.case)
        self.assertEqual(diagnostic["primary_status"], "invalid_response")
        self.assertEqual(diagnostic["format_class"], "complete_json_response_format_failure")
        self.assertFalse(diagnostic["strict_schema_valid"])
        self.assertIn("reason", diagnostic["normalized_fields"]["missing_fields"])
        result = field_outcomes(gold(), diagnostic["normalized_fields"])
        self.assertEqual(result["raw_field_judgement_accuracy"], 1)
        self.assertEqual(result["raw_field_joint_detection_type_row_full_citation"], 1)
        with self.assertRaises(ResponseError):
            parse_prediction(json.dumps(value))

    def test_truncated_json_is_never_reconstructed(self):
        response = {"status": "ok", "content": '{"judgement":"incorrect","citation":"ASC 330-10-35-1B",', "finish_reason": "length"}
        result = inspect_response(response, "invalid_response", self.case)
        self.assertEqual(result["format_class"], "truncation")
        self.assertFalse(result["complete_json"])
        self.assertEqual(field_outcomes(gold(), result["normalized_fields"])["raw_field_unvalidated_full_citation_agreement"], 0)

    def test_complete_json_at_length_finish_is_not_discarded(self):
        result = inspect_response(self.response(prediction(), "length"), "ok", self.case)
        self.assertTrue(result["complete_json"])
        self.assertTrue(result["strict_schema_valid"])
        self.assertEqual(result["finish_reason"], "length")

    def test_two_objects_and_array_are_rejected(self):
        for content in [json.dumps(prediction()) + json.dumps(prediction()), json.dumps([prediction()])]:
            result = inspect_response({"status": "ok", "content": content, "finish_reason": "stop"}, "invalid_response", self.case)
            self.assertFalse(result["complete_json"])
            self.assertEqual(result["format_class"], "invalid_json")

    def test_wrong_judgement_cannot_pass_citable_joint(self):
        fields = normalize_complete_object(prediction(judgement="correct"))
        result = field_outcomes(gold(), fields)
        self.assertEqual(result["raw_field_unvalidated_full_citation_agreement"], 1)
        self.assertEqual(result["raw_field_citable_judgement_full_citation_agreement"], 0)
        self.assertEqual(result["raw_field_joint_detection_type_row_full_citation"], 0)

    def test_missing_or_invalid_specific_fields_are_not_inferred(self):
        for changes in [{"citation": ["ASC 330-10-35-1B"]}, {"citation": "ASC 330-10-35-1B or ASC 210-10-45-1"}, {"row": True}, {"error_type": "numerical error"}]:
            result = field_outcomes(gold(), normalize_complete_object(prediction(**changes)))
            self.assertEqual(result["raw_field_joint_detection_type_row_full_citation"], 0)
        absent = prediction()
        del absent["citation"]
        result = field_outcomes(gold(citable=False), normalize_complete_object(absent))
        self.assertEqual(result["raw_field_noncitable_citation_abstention"], 0)

    def test_provider_failure_and_missing_response_are_zeros_in_denominator(self):
        for response in [None, {"status": "api_error", "content": None}]:
            result = inspect_response(response, "api_error", self.case)
            self.assertEqual(field_outcomes(gold(), result["normalized_fields"])["raw_field_judgement_accuracy"], 0)

    def test_explanation_never_supplies_a_missing_decision_or_quote(self):
        value = prediction()
        del value["judgement"]
        value["reason"] = "The judgement is incorrect and quote Cash movement +100 is true."
        value["evidence"] = [{"source": "transactions", "quote": "Cash movement +100", "row": 1}]
        result = inspect_response(self.response(value), "invalid_response", self.case)
        self.assertFalse(result["normalized_fields"]["judgement_valid"])
        self.assertEqual(result["quote_verification"]["verified"], 0)

    def test_input_response_and_primary_status_are_not_mutated(self):
        response = self.response(prediction())
        original = copy.deepcopy(response)
        result = inspect_response(response, "invalid_response", self.case)
        self.assertEqual(response, original)
        self.assertEqual(result["primary_status"], "invalid_response")

    def test_repair_spec_requires_explanation_and_complete_output(self):
        schema = repair_schema()
        self.assertIn("reason", schema["required"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["evidence"]["maxItems"], 4)

    def test_diagnostic_output_cannot_replace_primary_or_budget_ledger(self):
        for path in ["/tmp/prepared/report.json", "/tmp/prepared/scoring_only.jsonl", "/tmp/api_ledger.jsonl", "/tmp/prepared/responses/call.json"]:
            with self.assertRaises(ValueError):
                diagnostic_output_path("/tmp/prepared", path)


if __name__ == "__main__":
    unittest.main()
