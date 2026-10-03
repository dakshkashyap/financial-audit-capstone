#!/usr/bin/env python3
"""Offline transfer diagnostic of the legacy deterministic pipeline.

Predicts from public inputs before opening the scoring-only sidecar. No model
calls, API credentials, network access or implicit taxonomy downloads are used.
This condition tests the parser/rule interface on the new frozen pilot; it is
not a paid-model condition or a final accounting-validity experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from approaches.full_pipeline.pipeline import run_pipeline
from core.taxonomy_graph import TaxonomyGraph
from core.stage0_common import build_transactions
from research.metrics import canonical_citation, score_conditions

SHEETS = {"BalanceSheet": "balance sheet", "IncomeStatement": "income statement", "CashFlow": "cash flow"}


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def predict(case, graph):
    """Whitelisted input projection: no key, gold row, rule or sample-id parsing."""
    meta = case["metadata"]
    item = {"table": case["statement_text"], "transaction_data": case.get("transaction_data") or "",
            "sheet_type": SHEETS[meta["statement_type"]], "company": meta.get("company") or ""}
    record = run_pipeline(item, graph)
    evidence = build_transactions(item["transaction_data"])
    full = "ASC " + record.citation_primary if record.citation_primary else None
    return {"case_id": case["case_id"], "status": "ok", "model": None,
            "prediction": {"judgement": "abstain" if record.abstained else "incorrect",
                           "error_type": record.error_type, "row": record.problematic_entry,
                           "citation": canonical_citation(full)
                                       if record.citation_applicability_verified else None,
                           "evidence": []},
            "trace": [{"source": "offline_legacy_deterministic", "audit_record": record.to_dict(),
                       "raw_candidate_citation": full,
                       "component_evidence": {"format": evidence.evidence_format,
                                              "parsed_entries": len(evidence.entries),
                                              "rejected_labels": evidence.rejected_labels,
                                              "supporting_facts_present": evidence.supporting_facts_present,
                                              "scope": "partial synthetic evidence; not double-entry accounting"}}],
            "taxonomy_available": False, "api_cost_usd": 0,
            "diagnostic_scope": "deterministic_parser_transfer_on_synthetic_component_evidence"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared", type=Path, default=ROOT / "research/artifacts/pilot")
    parser.add_argument("--condition", default="legacy_local_offline")
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    args = parser.parse_args()
    if not args.condition.replace("_", "").isalnum():
        parser.error("condition must be an alphanumeric file-safe label")
    prepared = args.prepared.resolve()
    public = prepared / "public_inputs.jsonl"
    inputs = load_jsonl(public)
    graph = TaxonomyGraph()
    # Force offline behavior before any graph method can lazily fetch FASB.
    graph._xml_content = ""
    graph._available = False
    records = []
    for case in inputs:
        try:
            records.append(predict(case, graph))
        except Exception as exc:
            records.append({"case_id": case["case_id"], "status": "local_error",
                            "prediction": None, "error": f"{type(exc).__name__}: {exc}", "api_cost_usd": 0})
    prediction_path = prepared / "predictions" / (args.condition + ".jsonl")
    prediction_path.parent.mkdir(parents=True, exist_ok=True)
    if prediction_path.exists():
        raise SystemExit(f"Frozen predictions already exist: {prediction_path}; choose a new condition label.")
    prediction_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    # The key is deliberately unavailable to the prediction loop above.
    gold_path = prepared / "scoring_only.jsonl"
    gold = {row["case_id"]: row["gold"] for row in load_jsonl(gold_path)}
    report = score_conditions(inputs, gold, {args.condition: {r["case_id"]: r for r in records}}, draws=args.bootstrap_draws)
    source_files = ["core/stage0_common.py", "core/parser.py", "core/taxonomy_graph.py",
                    "approaches/full_pipeline/pipeline.py",
                    "approaches/stage0_deterministic_gate/stage0a.py", "approaches/stage0_deterministic_gate/stage0b.py",
                    "approaches/stage1_concept_mapping/edgar_mapper.py",
                    "approaches/stage1_concept_mapping/xbrl_concept_map.json",
                    "approaches/stage1_taxonomy_citation/stage1_arelle.py",
                    "approaches/stage1_taxonomy_citation/citation_select.py", "research/eval_local_pipeline.py"]
    report["provenance"] = {"condition": args.condition, "taxonomy_mode": "forced_offline_static_map",
                            "model_calls": 0, "api_cost_usd": 0,
                            "input_sha256": hashlib.sha256(public.read_bytes()).hexdigest(),
                            "key_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
                            "predictions_sha256": hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
                            "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in source_files}}
    report["diagnostic_limits"] = [
        "Abstention is retained when no error is proven; arithmetic consistency alone is not called a clean statement.",
        "Labelled component movement sums are partial synthetic evidence; amount reconstruction may make numeric detection easy and does not establish accounting realism.",
        "Supporting recognition/measurement review facts are excluded from the numeric parser. Covered arithmetic does not prove those facts satisfy a standard.",
        "Static reference-map full paragraphs are candidates, not independently validated governing standards.",
        "The deterministic citation output abstains unless applicability is separately verified; no current automatic checker verifies applicability.",
        "No taxonomy download occurred; this is not the full Stage 0/1/2 paid pipeline.",
    ]
    path = prepared / (args.condition + "_metrics.json")
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"predictions": str(prediction_path), "metrics": str(path),
                      "n": len(records), "taxonomy_available": False, "model_calls": 0,
                      "metrics_summary": report["conditions"][args.condition]["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
