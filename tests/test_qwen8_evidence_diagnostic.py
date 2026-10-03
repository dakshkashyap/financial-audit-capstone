"""Public-only, bounded two-call Qwen8 diagnostic and provider-stop boundaries."""
import contextlib
import io
import json
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from research.harness import BudgetError, EXTRACT_SYSTEM, Ledger
from research.run_qwen8_evidence_diagnostic import CONDITION, execute, plan, public_prepare
from research.select_pilot import select
from tests.test_research_harness import CONFIG as PILOT_CONFIG, prediction, source_fixture


CONFIG = json.loads((Path(__file__).resolve().parents[1] / "research/config/qwen8_evidence_diagnostic.json").read_text())
ENTRY = {"id": "qwen/qwen3-8b", "pricing": {"prompt": "0.000000117", "completion": "0.000000455"},
         "context_length": 131072, "supported_parameters": ["max_tokens", "temperature", "reasoning"]}


class Qwen8EvidenceDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.directory = Path(self.temp.name)
        source = self.directory / "source"
        source_fixture(source)
        self.prepared = self.directory / "prepared"
        select(source, self.prepared, PILOT_CONFIG)
        self.catalog = self.directory / "catalog.json"
        self.catalog.write_text(json.dumps({"data": [ENTRY]}))
        self.key = self.directory / "credential"
        self.key.write_text("not-real-test-token")
        self.ledger = self.directory / "ledger.jsonl"
        self.args = types.SimpleNamespace(prepared=str(self.prepared), catalog=str(self.catalog),
                                          key_file=str(self.key), ledger=str(self.ledger), limit=1, reserve_other_usd="0")

    def tearDown(self):
        self.temp.cleanup()

    def fake_provider(self, oversized=False):
        requests = []
        def fake_urlopen(request, **kwargs):
            body = json.loads(request.data)
            requests.append(body)
            if body["messages"][0]["content"] == EXTRACT_SYSTEM:
                content = {"evidence": prediction()["evidence"], "observations": ["x" * 10000 if oversized else "Cash discrepancy"],
                           "possible_faults": ["Numerical issue"], "uncertainty": "Synthetic evidence"}
            else:
                content = prediction()
            response = {"model": ENTRY["id"], "usage": {"cost": .0001}, "choices": [{"message": {"content": json.dumps(content)}, "finish_reason": "stop"}]}
            return contextlib.closing(io.BytesIO(json.dumps(response).encode()))
        return requests, fake_urlopen

    def test_inference_preparation_has_no_key_and_same_opaque_cases(self):
        target = self.prepared / "public-only"
        cases, manifest = public_prepare(self.prepared, target)
        self.assertEqual(len(cases), 48)
        self.assertEqual((target / "public_inputs.jsonl").read_bytes(), (self.prepared / "public_inputs.jsonl").read_bytes())
        self.assertFalse((target / "scoring_only.jsonl").exists())
        self.assertEqual([r["case_id"] for r in cases], manifest["case_ids"])

    def test_whole_cohort_plan_includes_bounded_second_call(self):
        result = plan(self.prepared, CONFIG, self.catalog, self.ledger, "2.569704")[0]
        self.assertEqual(result["n_cases"], 48)
        self.assertTrue(result["whole_cohort_fits_5_usd_cap"])
        self.assertEqual(len(result["per_case_reservations"]), 48)
        self.assertGreater(float(result["full_cohort_upper_bound_usd"]), .04)

    def test_whole_cohort_budget_preflight_even_when_limit_is_one(self):
        with Ledger(self.ledger, "5") as ledger:
            ledger.reserve("previous", "4.99", condition="test_prior")
        with mock.patch("urllib.request.urlopen") as network:
            with self.assertRaises(BudgetError):
                execute(self.args, CONFIG)
            network.assert_not_called()

    def test_two_calls_reasoning_disabled_paced_and_baseline_untouched(self):
        requests, provider = self.fake_provider()
        with mock.patch("urllib.request.urlopen", side_effect=provider), mock.patch("time.sleep") as sleep, contextlib.redirect_stdout(io.StringIO()):
            execute(self.args, CONFIG)
        self.assertEqual(len(requests), 2)
        self.assertTrue(sleep.called)
        self.assertTrue(all(r["reasoning"] == {"enabled": False} for r in requests))
        self.assertFalse((self.prepared / "predictions").exists())
        self.assertFalse((self.prepared / "report.json").exists())
        target = self.prepared / CONDITION
        self.assertFalse((target / "scoring_only.jsonl").exists())
        predictions = [json.loads(line) for line in (target / "predictions" / (CONDITION + ".jsonl")).read_text().splitlines()]
        self.assertEqual(predictions[0]["status"], "ok")

    def test_oversized_model_analysis_is_not_billed_as_a_decision(self):
        requests, provider = self.fake_provider(oversized=True)
        with mock.patch("urllib.request.urlopen", side_effect=provider), mock.patch("time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            execute(self.args, CONFIG)
        self.assertEqual(len(requests), 1)
        rows = [json.loads(line) for line in (self.prepared / CONDITION / "predictions" / (CONDITION + ".jsonl")).read_text().splitlines()]
        self.assertEqual(rows[0]["status"], "invalid_response")
        self.assertIn("6000-byte", rows[0]["error"])

    def test_first_provider_error_halts_without_retry_or_next_case(self):
        error = urllib.error.HTTPError("https://openrouter.ai", 429, "Rate limited", {}, None)
        self.args.limit = None
        with mock.patch("urllib.request.urlopen", side_effect=error) as network, contextlib.redirect_stdout(io.StringIO()):
            execute(self.args, CONFIG)
            self.assertEqual(network.call_count, 1)
            with self.assertRaises(RuntimeError):
                execute(self.args, CONFIG)
            self.assertEqual(network.call_count, 1)


if __name__ == "__main__":
    unittest.main()
