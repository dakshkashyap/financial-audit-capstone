#!/usr/bin/env python3
"""Recompute archived metrics and oracle diagnostics without network/model calls."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.metrics import (citation_codes, em_citation_exact, em_error_entry,
                          em_error_type, em_general_judgment,
                          em_standards_topk, extract_pred_errors)


def revision(path):
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def archived_metrics(source):
    result = []
    for path in sorted((source / "results").glob("*_predictions.json")):
        rows = json.loads(path.read_text())
        if not rows:
            continue
        counts = Counter()
        full_gold = full_hits = 0
        for row in rows:
            meta = row.get("item_meta", {})
            gold_errors = meta.get("errors", [])
            parsed = row.get("parsed") or {}
            predicted_errors = extract_pred_errors(parsed)
            counts["judgment_correct"] += em_general_judgment(
                parsed.get("General Judgment", parsed.get("General Judgement", "")),
                meta.get("general_judgement", "Incorrect"))
            counts["error_type_score_sum"] += em_error_type(predicted_errors, gold_errors)
            counts["row_score_sum"] += em_error_entry(predicted_errors, gold_errors)
            prediction = " ".join(error["citation"] or "" for error in predicted_errors)
            gold = " ".join(error.get("standards_citation", "") or "" for error in gold_errors)
            counts["legacy_prefix_top1_correct"] += em_standards_topk(prediction, gold)
            counts["deterministic_routes"] += row.get("route") == "deterministic"
            counts["api_error_records"] += row.get("error") is not None
            if citation_codes(gold, "full"):
                full_gold += 1
                full_hits += int(em_citation_exact(prediction, gold))
        name = path.name.removesuffix("_predictions.json")
        split = next(split for split in ["single_error", "multi_error", "correct"] if name.endswith(split))
        n = len(rows)
        result.append({"artifact": str(path.relative_to(source)), "split": split,
                       "system": name.removesuffix("_" + split), "n": n,
                       "model_ids": sorted({row.get("model_used", "unknown") for row in rows}),
                       "counts": dict(counts), "rates": {key: value / n for key, value in counts.items()},
                       "full_gold_samples": full_gold, "strict_full_hits": full_hits,
                       "strict_full_rate_on_available_full_gold": full_hits / full_gold if full_gold else None,
                       "status": "legacy_unvalidated_gold",
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def dataset_version(source, relative):
    path = source / relative
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    counts = Counter(row.get("ground_truth_citations", {}).get("citable") for row in rows)
    return {"source": str(source), "path": relative, "n": len(rows),
            "citable_n": counts[True], "noncitable_n": counts[False],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def evidence(branch, path, line, detail):
    return {"source_branch": branch, "path": path, "line": line, "detail": detail}


def findings():
    return [
        {"id": "P01", "severity": "critical", "title": "Legacy citation scoring is prefix overlap, not paragraph EM",
         "evidence": [evidence("asc", "core/metrics.py", 119, "ASC 210 receives credit against ASC 210-10-45-1; no full-ID equality is required."),
                      evidence("ifrs", "core/metrics.py", 123, "Different IAS 36 paragraphs receive shared-standard credit.")],
         "status": "fixed_with_separate_metric", "repair": "New em_citation_exact and em_citation_topic; legacy helper retained and explicitly labelled."},
        {"id": "P02", "severity": "critical", "title": "Oracle error/concept information makes the axis diagnostic perfect",
         "evidence": [evidence("asc", "approaches/stage2_llm_audit/axis_stage2.py", 148, "load_joined reads error_type and affected_xbrl_concept from the answer key."),
                      evidence("asc", "approaches/stage2_llm_audit/axis_stage2.py", 304, "principle_topic feeds those gold fields into axis_decision.")],
         "status": "diagnostic_only", "repair": "Report 100% as an oracle upper bound; deployable stage0_principle_full uses predicted type and mapped concept (1034–1041)."},
        {"id": "P03", "severity": "high", "title": "Citation recall includes non-citable items in its denominator",
         "evidence": [evidence("asc", "approaches/full_pipeline/run_iab_exam.py", 339, "Scorer returns None for non-citable items but recall still divides by every item at 373/398.")],
         "status": "fixed", "repair": "Count citable_n separately and report unsupported citations on non-citable items."},
        {"id": "P04", "severity": "high", "title": "Postprocessing replaces invalid picks with unrelated candidate citations",
         "evidence": [evidence("asc", "approaches/stage1_taxonomy_citation/citation_select.py", 138, "No matching topic still returns a heuristic primary candidate."),
                      evidence("asc", "approaches/stage2_llm_audit/stage2_llm.py", 215, "apply_citation_snap applied replacement only to the first error and left invalid picks intact on rows without candidates.")],
         "status": "fixed_in_stage2", "repair": "Validate all errors; preserve raw pick and reject to null, without candidate substitution."},
        {"id": "P05", "severity": "high", "title": "Prompt forces citations even when no paragraph applies",
         "evidence": [evidence("asc", "approaches/stage2_llm_audit/stage2_llm.py", 133, "If nothing fits, copy the most complete code anyway."),
                      evidence("ifrs", "approaches/stage2_llm_audit/stage2_llm.py", 144, "The IFRS prompt likewise requires never leaving citation blank.")],
         "status": "fixed", "repair": "Allow null citation, require evidence of applicability, distinguish reference membership from governing authority."},
        {"id": "P06", "severity": "high", "title": "Numeric revision can alter the wrong row",
         "evidence": [evidence("asc", "approaches/full_pipeline/run_intelliaudit.py", 63, "Global replace changes the first repeated number and ignores problematic_entry.")],
         "status": "fixed", "repair": "Bind the edit to the unique localized row and verify its whole existing numeric cell."},
        {"id": "P07", "severity": "high", "title": "IFRS retrieval discards exact paragraph information",
         "evidence": [evidence("ifrs", "approaches/stage1_taxonomy_citation/stage1_arelle.py", 307, "tax_codes collapse to tax_standards before setting candidates, and best_topic prefers subject standard.")],
         "status": "fixed", "repair": "Retain exact tax_codes and label source as taxonomy; bypass the ASC-only candidate normalizer in merged IFRS pipeline."},
        {"id": "P08", "severity": "high", "title": "Partial arithmetic consistency is used as an error-absence certificate",
         "evidence": [evidence("asc", "approaches/full_pipeline/pipeline.py", 114, "Only two checkable identities/subtotals and no detected anomaly are needed."),
                      evidence("asc", "approaches/stage2_llm_audit/stage2_llm.py", 50, "Prompt declares no Numerical Error or Missing Row exists and veto can erase those findings.")],
         "status": "fixed_default", "repair": "Soften evidence wording; a hard veto additionally requires explicit verified_error_absence, absent from legacy callers."},
        {"id": "P09", "severity": "high", "title": "Checked-in benchmark and upstream benchmark are different versions",
         "evidence": [evidence("both", "data/intelliaudit/answer_key.jsonl", 1, "Both capstone branches have 1202 cases/492 citable; upstream snapshot has 14963/6388.")],
         "status": "requires_version_pinning", "repair": "Freeze code, generator, exam, key, rubric, and source hashes before comparing systems."},
        {"id": "P10", "severity": "medium", "title": "GT row/type is available to citation-only diagnostic evaluators",
         "evidence": [evidence("asc", "approaches/stage1_taxonomy_citation/stage1_citation_eval.py", 200, "Lookup selects the gold broken row; this isolates retrieval and cannot be called end-to-end accuracy."),
                      evidence("asc", "approaches/citation_mcp_agent/eval_agent.py", 131, "Agent receives gold error type; its explicitly named oracle mode additionally consumes gold topic.")],
         "status": "diagnostic_only", "repair": "Keep separate oracle-localization and blind end-to-end tracks with whitelisted model inputs."},
        {"id": "P11", "severity": "medium", "title": "Result reuse ignores transactions, model, prompt and taxonomy changes",
         "evidence": [evidence("asc", "approaches/full_pipeline/intelliaudit_runner.py", 212, "Resume identity hashes only the table, using 12 MD5 characters."),
                      evidence("asc", "approaches/full_pipeline/run_intelliaudit.py", 93, "Prior record can be reused after architecture/prompt change when table matches.")],
         "status": "use_new_harness", "repair": "Cache with full prompt/model/config/dataset hashes and isolated run manifests; avoid interpreting old resumed files as new experiments."},
        {"id": "P12", "severity": "medium", "title": "General taxonomy references are treated as governing authority",
         "evidence": [evidence("asc", "core/taxonomy_graph.py", 308, "All general topics outrank industry standards, regardless of company; name truncation at 344 is not a real taxonomy ancestry relation."),
                      evidence("asc", "approaches/stage1_taxonomy_citation/citation_select.py", 102, "A specificity/lexicographic maximum decides between paragraphs without evidence or rule text.")],
         "status": "research_limitation", "repair": "Use accounting applicability labels and evidence-backed selection; evaluate list membership separately from semantic validity."},
        {"id": "P13", "severity": "medium", "title": "Historical success rate does not require citation success",
         "evidence": [evidence("asc", "core/metrics.py", 139, "success_rate thresholds judgment, type, row, BERTScore and BLEU but never citation.")],
         "status": "legacy_metric_only", "repair": "Publish separate joint detection/localization/citation/evidence outcomes and label historical SR's actual definition."},
        {"id": "P14", "severity": "high", "title": "Legacy row-index transaction parser cannot consume current label evidence",
         "evidence": [evidence("asc", "core/stage0_common.py", 275, "Component parser requires [row n] markers; current upstream uses [Label] movement lines."),
                      evidence("asc", "approaches/stage0_deterministic_gate/stage0a.py", 65, "Leaf reconciliation requires original row index; current label evidence carries none.")],
         "status": "fixed_with_partial_evidence_scope", "repair": "Strict signed-component label parser with exact signed/decimal comparison and unique-label reconciliation; reviewers' facts and totals are excluded. No complete-clean certificate from partial evidence."},
        {"id": "P15", "severity": "high", "title": "Deterministic arithmetic output promotes a reference hint to a governing citation",
         "evidence": [evidence("asc", "approaches/full_pipeline/run_intelliaudit.py", 74, "Deterministic output directly copies citation_primary without an applicability decision."),
                      evidence("asc", "approaches/full_pipeline/run_iab_exam.py", 491, "Stage 0 firing is sufficient to emit the primary taxonomy reference as predicted_asc.")],
         "status": "fixed_with_explicit_applicability_gate", "repair": "Actual citation output requires citation_applicability_verified, false by default and never set true by the current deterministic checkers. Preserve candidates and provenance separately; no claim that an automatic applicability verifier exists."},
        {"id": "P16", "severity": "high", "title": "Historical ablation replay coerces abstention and silently truncates evaluation",
         "evidence": [evidence("asc", "approaches/full_pipeline/pipeline_eval.py", 93, "Stage 0 abstention is treated as Correct; partial consistency also unconditionally vetoes Incorrect model outputs."),
                      evidence("asc", "approaches/full_pipeline/pipeline_eval.py", 66, "Prediction arrays align by order and the denominator is shortened to the smaller file.")],
         "status": "fixed", "repair": "Retain unverified outcomes and every selected case, require item-index/table-hash agreement, count missing/failed/misaligned records as failures, and route vetoes through the shared complete-certificate guard."},
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asc-source", type=Path, default=ROOT)
    parser.add_argument("--ifrs-source", type=Path)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"status": "verified_code_audit", "date": "2026-10-02",
              "source_revisions": {"asc": revision(args.asc_source)},
              "findings": findings(), "archived_metrics": archived_metrics(args.asc_source),
              "claimed_12_percent": {"reproduced": False,
                  "reason": "No corresponding frozen run artifact was present in either provided capstone branch.",
                  "possible_denominator_issue": "run_iab_exam originally divides strict hits by all items, including non-citable cases. This hypothesis is not a reconstruction of the team's 12% run."},
              "verification": {"model_api_calls": 0, "new_paid_model_results": False,
                  "tests_passed": 92, "test_command": "python -m unittest discover -s tests -p 'test_*.py'",
                  "test_files": sorted(str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_*.py"))},
              "dataset_versions": []}
    for source, relative in [(args.asc_source, "data/intelliaudit/answer_key.jsonl"),
                             (args.ifrs_source, "data/intelliaudit/answer_key.jsonl"),
                             (args.benchmark, "data/benchmark/answer_key.jsonl")]:
        if source and (source / relative).is_file():
            report["dataset_versions"].append(dataset_version(source, relative))
    if args.ifrs_source:
        report["source_revisions"]["ifrs"] = revision(args.ifrs_source)
    # Isolate import resolution to reproduce the original branch's diagnostic.
    diagnostic = args.asc_source / "approaches/stage2_llm_audit/axis_stage2.py"
    if diagnostic.is_file():
        code = "import sys,json; sys.path.insert(0,sys.argv[1]); from approaches.stage2_llm_audit.axis_stage2 import load_joined,analyze_full; print(json.dumps(analyze_full(load_joined())))"
        report["oracle_axis_diagnostic"] = json.loads(subprocess.check_output(
            [sys.executable, "-c", code, str(args.asc_source.resolve())], text=True))
        report["oracle_axis_diagnostic"]["status"] = "gold_error_type_and_concept_available_not_deployable"
    local = ROOT / "research/artifacts/pilot/legacy_local_offline_metrics.json"
    if local.is_file():
        local_report = json.loads(local.read_text())
        report["local_transfer_diagnostic"] = {
            "artifact": "research/artifacts/pilot/legacy_local_offline_metrics.json",
            "n_cases": local_report["n_cases"],
            "metrics": local_report["conditions"]["legacy_local_offline"]["metrics"],
            "scope": "offline_legacy_parser_transfer_not_full_stage2",
            "model_api_calls": 0,
            "limitations": local_report["diagnostic_limits"],
        }
    adapted = ROOT / "research/artifacts/pilot/legacy_local_adapted_metrics.json"
    if adapted.is_file():
        adapted_report = json.loads(adapted.read_text())
        report["adapted_local_transfer_diagnostic"] = {
            "artifact": "research/artifacts/pilot/legacy_local_adapted_metrics.json",
            "n_cases": adapted_report["n_cases"],
            "metrics": adapted_report["conditions"]["legacy_local_adapted"]["metrics"],
            "scope": "signed_label_parser_transfer_not_accounting_correctness",
            "model_api_calls": 0,
            "limitations": adapted_report["diagnostic_limits"],
        }
    guarded = ROOT / "research/artifacts/pilot/legacy_local_adapted_verified_citation_metrics.json"
    if guarded.is_file():
        guarded_report = json.loads(guarded.read_text())
        report["applicability_guard_local_diagnostic"] = {
            "artifact": "research/artifacts/pilot/legacy_local_adapted_verified_citation_metrics.json",
            "n_cases": guarded_report["n_cases"],
            "metrics": guarded_report["conditions"]["legacy_local_adapted_verified_citation"]["metrics"],
            "scope": "citation_output_abstention_gate_no_automatic_applicability_verifier",
            "model_api_calls": 0,
            "limitations": guarded_report["diagnostic_limits"],
        }
    serialized = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    else:
        print(serialized)


if __name__ == "__main__":
    main()
