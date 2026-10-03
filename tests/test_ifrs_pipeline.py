"""IFRS path of the audit pipeline. US-GAAP behaviour is pinned in the same file."""
import io
import json
import os
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "data", "ifrs", "fixtures", "ifrs_ref_fixture.xml")
RULEBOOK = os.path.join(ROOT, "data", "ifrs", "rulebook_ifrs.json")


class Grammar(unittest.TestCase):
    def test_parts_and_paragraph_forms(self):
        from core.frameworks import (
            format_citation, ifrs_code_from_parts, ifrs_paragraph_of, ifrs_standard_of,
        )
        self.assertEqual(
            ifrs_code_from_parts([("Name", "IAS"), ("Number", "1"),
                                  ("Paragraph", "66"), ("Subparagraph", "a")]),
            "IAS 1.66(a)",
        )
        self.assertEqual(
            ifrs_code_from_parts([("Name", "IFRS"), ("Number", "15"), ("Paragraph", "31")]),
            "IFRS 15.31",
        )
        self.assertIsNone(ifrs_code_from_parts([("Name", "FASB"), ("Number", "1")]))
        for text in ("IAS 1.66", "IAS 1 paragraph 66(a)", "see IAS 1, para. 66", "IAS 01.66"):
            self.assertEqual(ifrs_paragraph_of(text), "IAS 1.66", text)
        self.assertIsNone(ifrs_paragraph_of("IAS 1"))
        self.assertEqual(ifrs_paragraph_of("IFRS 9.5.5.15"), "IFRS 9.5.5.15")
        self.assertEqual(ifrs_paragraph_of("IFRS 9 paragraph 4.1.2A(b)"), "IFRS 9.4.1.2A")
        self.assertEqual(ifrs_paragraph_of("IAS 36.59."), "IAS 36.59")
        self.assertEqual(ifrs_standard_of("under IFRS 15 control transfers"), "IFRS 15")
        self.assertEqual(format_citation("330"), "ASC 330")
        self.assertEqual(format_citation("IAS 2.9"), "IAS 2.9")
        self.assertEqual(format_citation("FASB ASC 210-10-45-1"), "FASB ASC 210-10-45-1")

    def test_us_gaap_subject_rules_unchanged(self):
        from approaches.stage1_taxonomy_citation.concept_citation import (
            best_topic, candidate_topics, presentation_citation, subject_topic,
        )
        self.assertEqual(subject_topic("us-gaap:InventoryNet"), "330")
        self.assertEqual(subject_topic("us-gaap:Goodwill"), "350")
        self.assertEqual(subject_topic("us-gaap:OperatingLeaseRightOfUseAsset"), "842")
        self.assertEqual(presentation_citation("balance_sheet"), "210-10-45")
        self.assertEqual(presentation_citation("cash_flow"), "230-10-45")
        self.assertEqual(best_topic("us-gaap:InventoryNet", "balance_sheet"), "330")
        cands = candidate_topics("us-gaap:InventoryNet", "balance_sheet")
        self.assertEqual(cands[0], "330")
        self.assertIn("210", cands)


class Axis(unittest.TestCase):
    def test_locked_rules_for_both_frameworks(self):
        from approaches.stage2_llm_audit.axis_stage2 import _self_check
        _self_check()


class Linkbase(unittest.TestCase):
    def test_fixture_href_not_loc_label(self):
        from core.ifrs_taxonomy import IfrsTaxonomyGraph
        graph = IfrsTaxonomyGraph()
        with open(FIXTURE, "rb") as fh:
            graph.load_xml_bytes(fh.read())
        self.assertEqual(graph.citations("Inventories"), ["IAS 1.54(g)", "IAS 2.36(b)"])
        self.assertTrue(graph.paragraph_verified("ifrs-full:Inventories", "IAS 2.36"))
        self.assertFalse(graph.paragraph_verified("ifrs-full:Inventories", "IAS 2.9"))
        # The locator label in the fixture is loc_1, not loc_Inventories.
        self.assertEqual(graph.citations("loc_1"), [])

    def test_zip_of_fixture(self):
        from core.ifrs_taxonomy import IfrsTaxonomyGraph
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.write(FIXTURE, "IFRSAT/full_ifrs/linkbases/ias_2/ref_ias_2.xml")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(buf.getvalue())
            path = tmp.name
        try:
            graph = IfrsTaxonomyGraph()
            graph.load_zip(path)
            self.assertIn("IAS 2.36(b)", graph.citations("Inventories"))
        finally:
            os.unlink(path)


class Mapping(unittest.TestCase):
    def test_ifrs_label_and_stage1_citation(self):
        from approaches.stage1_concept_mapping.edgar_mapper import map_statement, match_concept
        from approaches.stage1_taxonomy_citation.stage1_arelle import run_stage1
        entry, strategy, conf = match_concept("inventories", "balance_sheet", framework="ifrs")
        self.assertEqual(strategy, "exact")
        self.assertEqual(entry["concept"], "ifrs-full:Inventories")
        self.assertEqual(conf, 1.0)
        # The US map must not be searched for this call.
        us_entry, _, _ = match_concept("inventories", "balance_sheet")
        if us_entry:
            self.assertTrue(us_entry["concept"].startswith("us-gaap:"))

        item = {
            "framework": "ifrs",
            "sheet_type": "statement of financial position",
            "company": "Example SE",
            "table": "[row 1]: Inventories | 150 [SEP] [row 2]: Goodwill | 40 [SEP]",
            "transaction_data": "",
        }
        mapped = map_statement(item, framework="ifrs")
        self.assertEqual(mapped.framework, "ifrs")
        self.assertEqual(mapped.statement_type, "balance_sheet")
        by_label = {row.norm: row for row in mapped.rows}
        self.assertEqual(by_label["inventories"].concept, "ifrs-full:Inventories")
        self.assertEqual(by_label["goodwill"].concept, "ifrs-full:Goodwill")

        enriched = run_stage1(item, framework="ifrs")
        cited = {row.norm: row for row in enriched.statement.rows}
        self.assertEqual(cited["inventories"].asc_primary, "IAS 2")
        self.assertEqual(cited["goodwill"].asc_primary, "IAS 36")
        self.assertIn("IAS 1", cited["inventories"].asc_candidates)
        self.assertEqual(enriched.framework, "ifrs")
        self.assertNotIn("ASC", cited["inventories"].asc_primary)


class ScoringAndPrompts(unittest.TestCase):
    def test_metric_accepts_ifrs_and_still_scores_asc(self):
        from core.metrics import em_standards_topk
        self.assertEqual(em_standards_topk("IAS 36 paragraph 59 applies", "IAS 36.59"), 1.0)
        self.assertEqual(em_standards_topk("IAS 36.90", "IAS 36.59"), 1.0)
        self.assertEqual(em_standards_topk("ASC 360-10-35-17", "IAS 36.59"), 0.0)
        self.assertEqual(em_standards_topk("ASC 360-10-35-17", "ASC 360-10-35-17"), 1.0)

    def test_stage2_prompt_switches_with_framework(self):
        from approaches.stage2_llm_audit.stage2_llm import build_user, system_for

        class Rec:
            verified_consistent = True
            footing = []
            equations = []

        class Row:
            value = 150.0
            row_idx = 1
            label = "Inventories"
            asc_candidates = ["IAS 2", "IAS 1"]
            concept = "ifrs-full:Inventories"

        class Stmt:
            framework = "ifrs"
            rows = [Row()]

        text = build_user(
            {"table": "[row 1]: Inventories | 150", "framework": "ifrs", "transaction_data": ""},
            Rec(), Stmt(),
        )
        self.assertIn("IAS 2", text)
        self.assertNotIn("ASC <topic", text)
        self.assertIn("Do not apply US GAAP", system_for(Rec(), "ifrs"))
        self.assertIn("candidate ASC topics", system_for(Rec(), "us-gaap"))


class Rulebook(unittest.TestCase):
    def test_vendored_rulebook(self):
        from core.frameworks import ifrs_paragraph_of
        with open(RULEBOOK, encoding="utf-8") as fh:
            rb = json.load(fh)
        self.assertEqual(rb["_meta"]["framework"], "ifrs")
        flips = [r for r in rb["rules"] if r.get("framework_contrast")]
        self.assertGreaterEqual(len(flips), 4)
        for rule in rb["rules"]:
            asc = rule["citation"]["asc"]
            if asc:
                self.assertIsNotNone(ifrs_paragraph_of(asc), rule["rule_id"])
                self.assertNotIn("ASC", asc)
            for concept in rule.get("eligible_concepts") or []:
                self.assertTrue(
                    concept.startswith("ifrs-full:") or concept.startswith("*"),
                    concept,
                )

    def test_missing_exam_names_the_directory(self):
        from approaches.stage2_llm_audit.axis_stage2 import load_joined
        with self.assertRaises(FileNotFoundError) as ctx:
            load_joined(os.path.join(ROOT, "data", "ifrs", "benchmark"), framework="ifrs")
        self.assertIn("data/ifrs", str(ctx.exception))


class Tools(unittest.TestCase):
    def test_ifrs_candidates_do_not_query_fasb(self):
        from approaches.citation_mcp_agent.tools import TaxonomyTools
        tools = TaxonomyTools()
        payload = tools.get_candidates("ifrs-full:Inventories")
        self.assertEqual(payload["framework"], "ifrs")
        standards = {c["standard"] for c in payload["candidates"]}
        self.assertIn("IAS 2", standards)
        self.assertNotIn("330", standards)
        good = tools.validate_citation("ifrs-full:Inventories", "IAS 2.9")
        self.assertTrue(good["valid"])
        self.assertEqual(good["topic"], "IAS 2")
        bad = tools.validate_citation("ifrs-full:Inventories", "ASC 330-10-35-1")
        self.assertFalse(bad["valid"])
        stored = tools.store_pick("item-1", "IAS 2.9", "inventory measured above NRV")
        self.assertEqual(stored["citation"], "IAS 2.9")


if __name__ == "__main__":
    unittest.main()
