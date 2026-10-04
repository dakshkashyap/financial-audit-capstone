"""Recorded data replays offline and mutation does not silently change a score."""
from pathlib import Path
import copy
import tempfile
import socket
import unittest
from unittest.mock import patch
from research import reproduce


class ReproductionTests(unittest.TestCase):
    def test_full_saved_snapshot_reproduces_without_connections(self):
        result=reproduce.reproduce()
        self.assertTrue(result['reproduction_passed'])
        self.assertEqual(result['primary']['cases'],48)
        self.assertEqual(result['primary']['companies'],8)
        self.assertEqual(result['primary']['regenerated_primary_stage_prompts'],195)
        self.assertEqual(result['professor_source_receipt']['source_files_checked'],212)

    def test_tampered_valid_prediction_is_rejected(self):
        original=reproduce.read_jsonl
        def altered(path):
            rows=list(original(path))
            if Path(path).name=='opus_direct.jsonl':
                rows[0]['prediction']['reason']='Changed after the run'
            return iter(rows)
        with patch.object(reproduce,'read_jsonl',altered):
            with self.assertRaisesRegex(ValueError,'parsed response differs'):
                reproduce.verify_primary()

    def test_recorded_hashes_do_not_hide_wrong_case_prompt(self):
        inputs,manifest=reproduce.inference_inputs(reproduce.ROOT/'artifacts/pilot')
        altered=copy.deepcopy(inputs);altered[0]['statement_text']='A different financial statement'
        with patch.object(reproduce,'inference_inputs',return_value=(altered,manifest)):
            with self.assertRaisesRegex(ValueError,'regenerated prompt differs'):
                reproduce.verify_primary()

    def test_staged_analysis_must_match_raw_extraction(self):
        original=reproduce.read_jsonl
        def altered(path):
            rows=list(original(path))
            if Path(path).name=='qwen30_evidence.jsonl':
                staged=next(row for row in rows if len(row['trace'])==2)
                staged['extraction']['uncertainty']='Changed after the run'
            return iter(rows)
        with patch.object(reproduce,'read_jsonl',altered):
            with self.assertRaisesRegex(ValueError,'stored extraction differs'):
                reproduce.verify_primary()

    def test_network_guard_is_restored_and_blocks_connections(self):
        connection=socket.create_connection
        with reproduce.offline():
            with self.assertRaises(RuntimeError):socket.create_connection(('example.com',443))
            with self.assertRaises(RuntimeError):socket.socket()
        self.assertIs(socket.create_connection,connection)

    def test_output_cannot_overwrite_primary_report(self):
        from unittest import mock
        with mock.patch('sys.argv',['reproduce','--output',str(reproduce.ROOT/'artifacts/pilot/report.json')]):
            with self.assertRaises(SystemExit) as error:reproduce.main()
            self.assertEqual(error.exception.code,2)
