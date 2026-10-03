import json
from pathlib import Path
import tempfile
import unittest

from research.comparison_table import resource_summary, subtopic_agreement


class ComparisonReportingTests(unittest.TestCase):
    def test_subtopic_credit_requires_eligible_valid_prediction(self):
        def case(code, status="ok", eligible=True):
            return {"gold_citable": eligible, "gold_citation": "ASC 606-10-25-23",
                    "status": status, "prediction": {"citation": code}}
        result = subtopic_agreement([
            case("ASC 606-10-25-30"),  # Same subtopic, distinct paragraph.
            case("ASC 606-20-25-23"), case("ASC 606-10-25-23", "invalid_response"),
            case("ASC 606-10-25-23", eligible=False)])
        self.assertEqual((result["numerator"], result["denominator"]), (1, 3))

    def test_staged_usage_is_summed_and_incomplete_usage_is_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for call, value in {
                "a": {"usage": {"prompt_tokens": 100, "completion_tokens": 20}, "elapsed_seconds": 2},
                "b": {"usage": {"prompt_tokens": 150, "completion_tokens": 30}, "elapsed_seconds": 3},
                "c": {"usage": None, "elapsed_seconds": 1},
            }.items():
                (root / (call + ".json")).write_text(json.dumps(value))
            summary = resource_summary([{"trace": ["a", "b"]}, {"trace": ["a", "c"]}], root)
            self.assertEqual(summary["input_tokens"], {"mean": 250, "n_cases_with_complete_measurement": 1})
            self.assertEqual(summary["output_tokens"]["mean"], 50)
            self.assertEqual(summary["latency"], {"mean": 4, "n_cases_with_complete_measurement": 2})
            self.assertEqual(summary["calls"], 4)

    def test_absent_response_is_not_a_free_instant_call(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = resource_summary([{"trace": ["missing"]}], Path(directory))
            for metric in ("input_tokens", "output_tokens", "latency"):
                self.assertIsNone(summary[metric]["mean"])
                self.assertEqual(summary[metric]["n_cases_with_complete_measurement"], 0)


if __name__ == "__main__":
    unittest.main()
