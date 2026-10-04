#!/usr/bin/env python3
"""Blind candidate generation, then scoring-only reference-coverage diagnosis.

Requires an existing FASB reference XML; never downloads or calls a model.
The candidate cache and manifest are written before the scoring key is opened.
All gold-conditional analyses are explicitly oracle diagnostics against an
unvalidated answer key, not evidence of paragraph applicability.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from approaches.stage1_concept_mapping.edgar_mapper import map_statement
from approaches.stage1_taxonomy_citation.stage1_arelle import run_stage1
from approaches.stage1_taxonomy_citation.citation_select import uniq_full, specificity, pick_primary
from approaches.stage2_llm_audit.stage2_llm import _row_codes, _citation_block
from core.metrics import citation_codes
from core.taxonomy_graph import TaxonomyGraph, _parent_candidates, _ROLE_PRIORITY

SHEETS = {"BalanceSheet": "balance sheet", "IncomeStatement": "income statement", "CashFlow": "cash flow"}
SOURCE_FILES = ["core/taxonomy_graph.py", "core/metrics.py", "core/stage0_common.py",
                "approaches/stage1_concept_mapping/edgar_mapper.py",
                "approaches/stage1_concept_mapping/xbrl_concept_map.json",
                "approaches/stage1_taxonomy_citation/stage1_arelle.py",
                "approaches/stage1_taxonomy_citation/citation_select.py",
                "approaches/stage2_llm_audit/stage2_llm.py", "research/phase2/audit_candidates.py"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def full(codes):
    # Taxonomy candidate strings can have bare ASC identifiers followed by
    # staff-reference parentheses. Prefix those before the shared parser;
    # its bare-code shortcut otherwise accepts only an entire bare string.
    texts = [str(value).strip() for value in codes if value]
    return list(dict.fromkeys(code for value in texts
                             for code in citation_codes("ASC " + value if value[:1].isdigit() else value, "full")))


def direct_arcs(graph, concept):
    result = []
    for ref_id in graph._refs_for_concept(concept):
        parts = graph._parse_ref_element(ref_id)
        if not parts or not parts.get("topic"):
            continue
        raw = graph._build_citation(parts)
        result.append({"reference_label": ref_id, "raw_citation": raw,
                       "full_codes": full([raw]), "role": parts.get("role") or "unknown",
                       "topic": parts.get("topic"), "rank_key": list(graph._rank_key(parts)),
                       "matched_concept": concept})
    return result


def concept_references(graph, concept):
    direct = direct_arcs(graph, concept) if concept else []
    parent = []
    if concept and not direct:
        for candidate in _parent_candidates(concept):
            parent = direct_arcs(graph, candidate)
            if parent:
                break
    return direct, parent


def prepare(public_path, taxonomy_path, output):
    output.mkdir(parents=True, exist_ok=True)
    cache = output / "candidate_cache.jsonl"
    if cache.exists():
        raise SystemExit("Candidate cache exists; choose a new output directory to preserve it.")
    if not taxonomy_path.is_file():
        raise SystemExit("Provide an existing local reference XML; implicit network access is disabled.")
    # Populate the lazy loader explicitly. Every graph method is now read-only.
    graph = TaxonomyGraph(cache_path=str(taxonomy_path))
    graph._xml_content = taxonomy_path.read_text()
    if "<link:reference" not in graph._xml_content:
        raise SystemExit("The supplied file is not a supported FASB reference linkbase.")
    graph._available = True
    graph._build_index()
    reference_inventory = []
    for label in graph._ref_index:
        parts = graph._parse_ref_element(label)
        if parts and parts.get("topic"):
            reference_inventory.append({"reference_label": label,
                                        "full_codes": full([graph._build_citation(parts)]),
                                        "role": parts.get("role") or "unknown"})
    inventory = {"full_codes": sorted({c for r in reference_inventory for c in r["full_codes"]}),
                 "roles": dict(Counter(r["role"] for r in reference_inventory)),
                 "reference_element_count": len(graph._ref_index),
                 "usable_reference_element_count": len(reference_inventory),
                 "concept_locator_count": len(graph._arc_index)}
    # Independent namespace-aware parser verifies that the inherited regex
    # index did not silently omit reference elements or explicit identifiers.
    et_refs = [element for element in ET.fromstring(graph._xml_content).iter()
               if element.tag.endswith("}reference")]
    et_codes = set()
    for element in et_refs:
        parts = {child.tag.split("}")[-1]: child.text or "" for child in element}
        if parts.get("Topic"):
            raw = "FASB ASC " + "-".join(parts[k] for k in ["Topic", "SubTopic", "Section", "Paragraph"] if parts.get(k))
            et_codes.update(full([raw]))
    if len(et_refs) != len(graph._ref_index) or et_codes != set(inventory["full_codes"]):
        raise RuntimeError("Independent XML parsing disagrees with inherited reference index.")
    inventory["independent_xml_parser_check"] = "reference count and exact paragraph-identifier universe agree"
    cases = []
    for case in jsonl(public_path):
        metadata = case["metadata"]
        # Only this whitelist reaches mapping/retrieval. IDs attach after it.
        item = {"table": case["statement_text"], "transaction_data": case.get("transaction_data") or "",
                "sheet_type": SHEETS[metadata["statement_type"]], "company": metadata.get("company") or ""}
        static = {row.row_idx: row for row in map_statement(item).rows}
        stage = run_stage1(item, graph)
        visible_ids = {row.row_idx for row in [r for r in stage.statement.rows
                       if r.value is not None and _row_codes(r)][:40]}
        rows = []
        for row in stage.statement.rows:
            concept = (row.concept or "").split(":")[-1]
            direct, parent = concept_references(graph, concept)
            refs = direct or parent
            displayed = _row_codes(row)
            raw_codes = [arc["raw_citation"] for arc in refs]
            counter = Counter(code for arc in refs for code in arc["full_codes"])
            roles_by_code = {code: sorted({arc["role"] for arc in refs if code in arc["full_codes"]})
                             for code in counter}
            before = static[row.row_idx]
            unbounded = uniq_full([row.asc_primary, *(row.asc_refs or []), *raw_codes], limit=100000)
            ranked = graph.get_candidate_citations(concept) if concept else []
            general = [arc for arc in refs if (arc.get("topic") or "").isdigit() and int(arc["topic"]) < 900]
            industry = [arc for arc in refs if (arc.get("topic") or "").isdigit() and int(arc["topic"]) >= 900]
            rows.append({"row": row.row_idx, "label": row.label, "value_present": row.value is not None,
                         "concept": row.concept, "mapping_strategy": row.strategy,
                         "mapping_confidence": row.confidence, "candidate_source": stage.citation_sources.get(row.row_idx, "none"),
                         "static_primary": before.asc_primary, "static_refs": before.asc_refs,
                         "enriched_primary": row.asc_primary, "stored_top8": row.asc_candidates,
                         "displayed_top8": displayed, "displayed_in_prompt": row.row_idx in visible_ids,
                         "displayed_full_codes": full(displayed), "unbounded_full_codes": full(unbounded),
                         "direct_references": direct, "camel_fallback_references": parent,
                         "all_reference_full_codes": full(raw_codes),
                         "taxonomy_ranked_unique_candidates": ranked,
                         "lexicographic_unbounded_candidates": unbounded,
                         "codes_with_multiple_arcs": {k:v for k,v in counter.items() if v > 1},
                         "codes_with_multiple_roles": {k:v for k,v in roles_by_code.items() if len(v) > 1},
                         "general_and_industry_compete": bool(general and industry),
                         "role_counts": dict(Counter(arc["role"] for arc in refs)),
                         "primary_role": next((arc["role"] for arc in refs
                             if full([row.asc_primary]) and full([row.asc_primary])[0] in arc["full_codes"]), None),
                         "unconditioned_pick_primary": pick_primary(displayed),
                         "ranking_changed_order": full([r["asc"] for r in ranked]) != full(raw_codes)
                             and full([r["asc"] for r in ranked]) != full(unbounded),
                         "same_specificity_tie_count": max(Counter(specificity(c) for c in unbounded).values(), default=0)})
        cases.append({"case_id": case["case_id"], "statement_type": metadata["statement_type"],
                      "company": metadata.get("company"), "rows": rows,
                      "stage1_summary": stage.summary(), "actual_candidate_prompt": _citation_block(stage.statement),
                      "public_all_rows_displayed_union": sorted({c for r in rows if r["displayed_in_prompt"] for c in r["displayed_full_codes"]}),
                      "public_all_rows_unbounded_union": sorted({c for r in rows for c in r["unbounded_full_codes"]}),
                      "public_all_rows_full_reference_union": sorted({c for r in rows for c in r["all_reference_full_codes"]})})
    # Commit inference artifacts before any scoring-sidecar path is opened.
    cache.write_text("".join(json.dumps(case, sort_keys=True) + "\n" for case in cases))
    inventory_path = output / "taxonomy_inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2) + "\n")
    provenance_path = taxonomy_path.with_suffix(".provenance.json")
    provenance = json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    manifest = {"public_input_sha256": sha(public_path), "candidate_cache_sha256": sha(cache),
                "taxonomy_inventory_sha256": sha(inventory_path), "taxonomy_xml_sha256": sha(taxonomy_path),
                "taxonomy_source": provenance, "case_count": len(cases), "model_calls": 0,
                "network_calls_in_script": 0, "scoring_key_opened_during_prepare": False,
                "source_sha256": {path: sha(ROOT / path) for path in SOURCE_FILES}}
    (output / "candidate_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def score(key_path, output):
    manifest = json.loads((output / "candidate_manifest.json").read_text())
    cache = output / "candidate_cache.jsonl"
    if sha(cache) != manifest["candidate_cache_sha256"]:
        raise SystemExit("Candidate cache hash differs from the blind-generation manifest.")
    cases = jsonl(cache)
    inventory = json.loads((output / "taxonomy_inventory.json").read_text())
    gold = {row["case_id"]: row["gold"] for row in jsonl(key_path)}
    counters, provenance, roles, ranking = Counter(), Counter(), Counter(), Counter()
    case_results = []
    all_rows = [r for case in cases for r in case["rows"]]
    for row in all_rows:
        provenance[row["candidate_source"]] += 1
        roles.update(row["role_counts"])
        displayed = row["displayed_top8"]
        lexical = row["lexicographic_unbounded_candidates"]
        taxonomy = row["taxonomy_ranked_unique_candidates"]
        ranking["rows_graph_primary_differs_from_lexicographic_first"] += int(bool(lexical) and row["enriched_primary"] != lexical[0])
        ranking["rows_selector_primary_differs_from_graph_primary"] += int(bool(displayed) and row["unconditioned_pick_primary"] != row["enriched_primary"])
        ranking["rows_taxonomy_ranked_order_changed_by_lexicographic_sort"] += int(
            [r["asc"] for r in taxonomy] != [c for c in lexical if c in {r["asc"] for r in taxonomy}])
        refs = [*row["direct_references"], *row["camel_fallback_references"]]
        topics = {int(r["topic"]) for r in refs if (r["topic"] or "").isdigit()}
        ranking["rows_800_to_899_candidates_compete_with_below_800"] += int(any(800 <= topic < 900 for topic in topics) and any(topic < 800 for topic in topics))
        primary = full([row["enriched_primary"]])
        primary_topic = int(primary[0].split()[1].split("-")[0]) if primary else None
        presentation = {205,210,220,225,230,235,260,270,275,505}
        ranking["rows_presentation_topic_primary_with_nonpresentation_alternative"] += int(primary_topic in presentation and bool(topics-presentation))
        for candidate in taxonomy:
            code = full([candidate["asc"]])
            matching = [r for r in refs if code and code[0] in r["full_codes"]]
            if matching:
                ranking["deduplicated_candidates_that_lost_higher_priority_role"] += int(
                    _ROLE_PRIORITY.get(candidate["role"],0) < max(_ROLE_PRIORITY.get(r["role"],0) for r in matching))
    for case in cases:
        key = gold[case["case_id"]]
        label = key["ground_truth_citations"]
        citable = bool(label.get("citable"))
        target = full([label.get("asc_full")])
        expected = target[0] if len(target) == 1 else None
        target_row = (key.get("error_identification") or {}).get("problematic_entry")
        oracle = next((r for r in case["rows"] if r["row"] == target_row), None)
        counters["cases"] += 1
        counters["citable_cases"] += int(citable)
        checks = {"public_union_displayed": expected in case["public_all_rows_displayed_union"],
                  "public_union_unbounded": expected in case["public_all_rows_unbounded_union"],
                  "public_union_full_reference": expected in case["public_all_rows_full_reference_union"],
                  "anywhere_in_taxonomy": expected in inventory["full_codes"],
                  "oracle_gold_row_exists": oracle is not None,
                  "oracle_gold_row_displayed": bool(oracle and oracle["displayed_in_prompt"]),
                  "oracle_gold_row_top8": bool(oracle and expected in oracle["displayed_full_codes"]),
                  "oracle_gold_row_top1": bool(oracle and full(oracle["displayed_top8"][:1]) == [expected]),
                  "oracle_gold_row_unbounded": bool(oracle and expected in oracle["unbounded_full_codes"]),
                  "oracle_gold_row_full_reference": bool(oracle and expected in oracle["all_reference_full_codes"]),
                  "oracle_gold_row_static": bool(oracle and expected in full([oracle["static_primary"], *oracle["static_refs"]]))}
        if citable:
            for name, hit in checks.items():
                counters[name] += int(hit)
        else:
            counters["noncitable_cases_with_candidates"] += int(bool(case["public_all_rows_displayed_union"]))
        hits = []
        if expected:
            for row in case["rows"]:
                for ref in [*row["direct_references"], *row["camel_fallback_references"]]:
                    if expected in ref["full_codes"]:
                        hits.append({"row":row["row"], "concept":row["concept"],
                                     "source":row["candidate_source"], "role":ref["role"],
                                     "reference_label":ref["reference_label"]})
        case_results.append({"case_id": case["case_id"], "citable": citable,
                             "label_validation": label.get("citation_tier"), "provisional_full_label": expected,
                             "oracle_gold_row": target_row, "oracle_gold_row_concept": oracle["concept"] if oracle else None,
                             "coverage": checks if citable else None, "positive_reference_provenance": hits,
                             "negative_reference_provenance": "No mapped-row reference contains this provisional paragraph" if expected and not hits else None,
                             "oracle_displayed_candidates": oracle["displayed_top8"] if oracle else [],
                             "oracle_full_reference_candidates": oracle["all_reference_full_codes"] if oracle else []})
    denominator = counters["citable_cases"]
    metrics = {k:{"hits":v,"denominator":denominator,"rate":v/denominator if denominator else None}
               for k,v in counters.items() if k.startswith(("public_", "oracle_", "anywhere_"))}
    report = {"scope":"reference coverage against UNVALIDATED labels; oracle rows used only after blind cache was saved",
              "manifest":manifest,"scoring_key_sha256":sha(key_path),"counts":dict(counters),"coverage":metrics,
              "row_diagnostics":{"row_count":len(all_rows),"provenance_counts":dict(provenance),"arc_role_counts":dict(roles),
                 "rows_with_camel_fallback":sum(bool(r["camel_fallback_references"]) for r in all_rows),
                 "rows_with_duplicate_citation_arcs":sum(bool(r["codes_with_multiple_arcs"]) for r in all_rows),
                 "rows_with_same_citation_multiple_roles":sum(bool(r["codes_with_multiple_roles"]) for r in all_rows),
                 "rows_with_general_and_industry_competition":sum(r["general_and_industry_compete"] for r in all_rows),
                 "rows_with_more_than_8_unbounded_candidates":sum(len(r["lexicographic_unbounded_candidates"])>8 for r in all_rows),
                 "valued_rows_hidden_by_40_row_cap":sum(r["value_present"] and bool(r["displayed_top8"]) and not r["displayed_in_prompt"] for r in all_rows),
                 "rows_with_equal_specificity_lexicographic_ties":sum(r["same_specificity_tie_count"]>1 for r in all_rows)},
              "mechanical_ranking_diagnostics":dict(ranking),
              "taxonomy_inventory_summary":{k:v for k,v in inventory.items() if k!="full_codes"},
              "cases":case_results,
              "limitations":["Reference membership is neither paragraph applicability nor independent label validation.",
                 "Full taxonomy means this 2023 reference linkbase, not the full Codification or a historical effective-date corpus.",
                 "Gold-row coverage is an oracle diagnostic; the deployed system does not receive that row.",
                 "CamelCase truncation is a name heuristic, not a verified taxonomy hierarchy.",
                 "Counts include repeated company/statement rows across this 48-case development pilot.",
                 "Absence means no explicit exact paragraph identifier in the reference metadata, not that the Codification lacks or rejects that paragraph.",
                 "Taxonomy ranking prefers topics below 900, while the separate selector prefers below 800; neither threshold establishes case-specific applicability."]}
    (output / "candidate_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    text = ["# Candidate coverage audit", "", report["scope"], "", f"| Coverage | Hits / {denominator} provisional citable labels |", "|---|---:|"]
    text.extend(f"| {name} | {value['hits']}/{value['denominator']} |" for name,value in metrics.items())
    text += ["", "## Row diagnostics", "", "```json", json.dumps(report["row_diagnostics"],indent=2), "```",
             "", "## Mechanical ranking diagnostics", "", "```json",json.dumps(dict(ranking),indent=2),"```",
             "", "## No explicit exact identifier anywhere in this reference taxonomy", ""]
    text.extend(f"- {r['case_id']}: {r['provisional_full_label']}" for r in case_results if r["citable"] and not r["coverage"]["anywhere_in_taxonomy"])
    text += ["", "## Limits", "", *["- "+limit for limit in report["limitations"]], ""]
    (output / "candidate_audit.md").write_text("\n".join(text))
    return {"counts":report["counts"],"coverage":metrics,"row_diagnostics":report["row_diagnostics"],"mechanical_ranking_diagnostics":dict(ranking)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared",type=Path,default=ROOT/"research/artifacts/pilot")
    parser.add_argument("--taxonomy-xml",type=Path,default=ROOT/".cache/us-gaap-ref-2023.xml")
    parser.add_argument("--output",type=Path,default=ROOT/"research/artifacts/phase2/candidate_audit_v3")
    parser.add_argument("--score-only",action="store_true")
    args=parser.parse_args()
    if not args.score_only:
        prepare(args.prepared/"public_inputs.jsonl",args.taxonomy_xml,args.output)
    print(json.dumps(score(args.prepared/"scoring_only.jsonl",args.output),indent=2))


if __name__=="__main__":
    main()
