"""Separate diagnostic keeps frozen baseline and global budget boundaries."""
import contextlib
import copy
import io
import json
import tempfile
import types
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path
from unittest import mock

from research.harness import BudgetError, FRONTIER, Ledger
from research.run_frontier_format_diagnostic import (execute, plan, request_body,
                                                     request_reservation, validate_settings)
from research.select_pilot import json_dump, select
from tests.test_research_harness import CONFIG as PILOT_CONFIG, prediction, source_fixture


CONFIG = json.loads((Path(__file__).resolve().parents[1] / "research/config/frontier_format_diagnostic.json").read_text())
ENTRY = {"id": FRONTIER, "pricing": {"prompt": "0.000004", "completion": "0.00002"},
         "context_length": 1000000, "supported_parameters": ["max_tokens", "temperature", "reasoning", "response_format", "structured_outputs"],
         "reasoning": {"mandatory": True, "supported_efforts": ["low", "high"]}}


class FrontierFormatDiagnosticTests(unittest.TestCase):
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
                                          key_file=str(self.key), ledger=str(self.ledger), limit=1)

    def tearDown(self):
        self.temp.cleanup()

    def test_only_same_frontier_and_supported_low_reasoning_schema(self):
        for key, value in [("model", "anthropic/claude-sonnet-5.5"), ("reasoning_effort", "high"), ("max_completion_tokens", 2000)]:
            changed = {**CONFIG, key: value}
            with self.assertRaises(ValueError):
                validate_settings(changed, ENTRY)
        changed = copy.deepcopy(ENTRY)
        changed["supported_parameters"].remove("structured_outputs")
        with self.assertRaises(ValueError):
            validate_settings(CONFIG, changed)

    def test_schema_bytes_included_in_reservation(self):
        case = {"case_id": "opaque", "metadata": {}, "statement_text": "Cash100", "transaction_data": ""}
        body = request_body(case, CONFIG, ENTRY)
        amount, upper = request_reservation(body, ENTRY)
        self.assertGreaterEqual(upper, len(json_dump(body).encode("utf-8")))
        messages_only = len(json_dump(body["messages"]).encode("utf-8"))
        self.assertGreater(upper, messages_only + 1024)
        self.assertEqual(amount, Decimal(upper) * Decimal(".000004") + Decimal(1200) * Decimal(".00002"))

    def test_whole_cohort_preflight_refuses_spend_if_any_cases_cannot_fit(self):
        with Ledger(self.ledger, "5") as ledger:
            ledger.reserve("previous", "3.90", condition="prior_test")
        with mock.patch("urllib.request.urlopen") as network:
            with self.assertRaises(BudgetError):
                execute(self.args, CONFIG)
            network.assert_not_called()

    def test_schema_endpoint_error_stops_after_one_and_cannot_auto_resume(self):
        error = urllib.error.HTTPError("https://openrouter.ai", 400, "Unsupported schema", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error) as network, contextlib.redirect_stdout(io.StringIO()):
            execute(self.args, CONFIG)
            self.assertEqual(network.call_count, 1)
            with self.assertRaises(RuntimeError):
                execute(self.args, CONFIG)
            self.assertEqual(network.call_count, 1)
        self.assertTrue((self.prepared / "frontier_format_diagnostic/halted.json").exists())

    def test_valid_structured_response_and_resume_do_not_change_baseline(self):
        public_before = (self.prepared / "public_inputs.jsonl").read_bytes()
        key_before = (self.prepared / "scoring_only.jsonl").read_bytes()
        requests = []
        def fake_urlopen(request, **kwargs):
            payload = json.loads(request.data)
            requests.append(payload)
            response = {"model": FRONTIER, "provider": "Test Provider", "usage": {"cost": .001},
                        "choices": [{"message": {"content": json.dumps(prediction())}, "finish_reason": "stop"}]}
            return contextlib.closing(io.BytesIO(json.dumps(response).encode()))
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), contextlib.redirect_stdout(io.StringIO()):
            execute(self.args, CONFIG)
            self.args.limit = 0
            execute(self.args, CONFIG)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["reasoning"], {"effort": "low"})
        self.assertEqual(requests[0]["response_format"]["type"], "json_schema")
        self.assertEqual((self.prepared / "public_inputs.jsonl").read_bytes(), public_before)
        self.assertEqual((self.prepared / "scoring_only.jsonl").read_bytes(), key_before)
        self.assertFalse((self.prepared / "predictions").exists())
        self.assertFalse((self.prepared / "report.json").exists())
        logged = self.ledger.read_text() + "".join(p.read_text() for p in (self.prepared / "frontier_format_diagnostic/responses").glob("*.json"))
        self.assertNotIn("not-real-test-token", logged)
        self.assertNotIn("Authorization", logged)

    def test_first_missing_reason_halts_structured_protocol_preflight(self):
        value = prediction()
        del value["reason"]
        response = {"model": FRONTIER, "usage": {"cost": .001},
                    "choices": [{"message": {"content": json.dumps(value)}, "finish_reason": "stop"}]}
        def fake_urlopen(*args, **kwargs):
            return contextlib.closing(io.BytesIO(json.dumps(response).encode()))
        self.args.limit = None
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen) as network, contextlib.redirect_stdout(io.StringIO()):
            execute(self.args, CONFIG)
            self.assertEqual(network.call_count, 1)
        self.assertTrue((self.prepared / "frontier_format_diagnostic/halted.json").exists())


if __name__ == "__main__":
    unittest.main()
