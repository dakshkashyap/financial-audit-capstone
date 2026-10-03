"""Read-only, explicitly post-hoc formatting diagnostics for cached responses.

This script never changes predictions, repairs JSON, sends API requests, or
replaces primary scores. Complete raw JSON can reveal field-level decisions even
when the strict seven-field output protocol failed, e.g. an omitted `reason`.
Such diagnostics still measure agreement with unvalidated labels.

After the primary report is ready::
    python -m research.diagnose_raw_outputs --prepared research/artifacts/pilot

To estimate a separately labelled frontier formatting study without spending::
    python -m research.diagnose_raw_outputs --prepared research/artifacts/pilot \
      --plan-repair --catalog /tmp/audit-model-catalog.json
"""
import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .harness import (BASE, ERROR_TYPES, FRONTIER, HARD_BUDGET, SYSTEM,
                      ResponseError, atomic_json, inference_inputs,
                      ledger_summary, load_catalog, parse_object,
                      parse_prediction, verify_evidence)
from .metrics import (aggregate, canonical_citation, cluster_intervals,
                      outcomes, paired_cluster_difference, topic)
from .select_pilot import digest, json_dump, read_jsonl


REQUIRED = {"judgement", "error_type", "row", "citation", "citation_abstain", "evidence", "reason"}


def diagnostic_output_path(prepared, output=None):
    prepared = Path(prepared)
    target = Path(output) if output else prepared / "raw_output_diagnostics.json"
    protected = {prepared / name for name in ("report.json", "manifest.json", "public_inputs.jsonl", "scoring_only.jsonl")}
    if target.suffix != ".json" or target.resolve() in {p.resolve() for p in protected} or "predictions" in target.parts or "responses" in target.parts:
        raise ValueError("Diagnostics cannot overwrite primary inputs, caches, keys, ledgers, or scores")
    return target


def normalize_complete_object(value):
    """Per-field validation only. Never fill in a missing field or infer values."""
    judgement = value.get("judgement")
    valid_judgement = isinstance(judgement, str) and judgement.lower() in {"correct", "incorrect", "abstain"}
    row = value.get("row")
    valid_row = "row" in value and (row is None or type(row) is int and row >= 0)
    error_type = value.get("error_type")
    valid_type = "error_type" in value and (error_type is None or isinstance(error_type, str) and error_type in ERROR_TYPES)
    raw_citation = value.get("citation")
    citation = canonical_citation(raw_citation)
    valid_citation = "citation" in value and (raw_citation is None or citation is not None)
    return {"judgement": judgement.lower() if valid_judgement else None,
            "judgement_valid": valid_judgement,
            "row": row if valid_row else None, "row_valid": valid_row,
            "error_type": error_type if valid_type else None, "error_type_valid": valid_type,
            "citation": citation, "citation_valid": valid_citation,
            "citation_null": valid_citation and raw_citation is None,
            "missing_fields": sorted(REQUIRED - set(value))}


def field_outcomes(gold, normalized):
    """All applicable cases stay in the denominator, including unavailable JSON."""
    value = normalized or {}
    control = gold["general_judgement"] == "Correct"
    citable = bool(gold["ground_truth_citations"].get("citable"))
    judgement = value.get("judgement")
    valid_judgement = value.get("judgement_valid", False)
    expected = "correct" if control else "incorrect"
    full = canonical_citation(gold["ground_truth_citations"].get("asc_full"))
    row = (gold.get("error_identification") or {}).get("problematic_entry")
    row_match = value.get("row_valid", False) and type(value.get("row")) is int and value["row"] == row
    type_match = value.get("error_type_valid", False) and value.get("error_type") == gold.get("error_type")
    citation_match = value.get("citation_valid", False) and value.get("citation") is not None and value["citation"] == full
    found = valid_judgement and judgement == "incorrect"
    return {
        "raw_field_judgement_accuracy": int(valid_judgement and judgement == expected),
        "raw_field_clean_specificity": int(valid_judgement and judgement == "correct") if control else None,
        "raw_field_detection_sensitivity": int(found) if not control else None,
        "raw_field_type_accuracy": int(found and type_match) if not control else None,
        "raw_field_row_accuracy": int(found and row_match) if not control else None,
        "raw_field_joint_detection_type_row": int(found and type_match and row_match) if not control else None,
        "raw_field_unvalidated_full_citation_agreement": int(citation_match) if citable else None,
        "raw_field_unvalidated_topic_agreement": int(value.get("citation_valid", False) and value.get("citation") is not None and topic(value["citation"]) == topic(full)) if citable else None,
        "raw_field_citable_judgement_full_citation_agreement": int(found and citation_match) if citable else None,
        "raw_field_joint_detection_type_row_full_citation": int(found and type_match and row_match and citation_match) if citable else None,
        "raw_field_noncitable_citation_abstention": int(value.get("citation_null", False)) if not citable else None,
        "raw_field_judgement_abstention": int(valid_judgement and judgement == "abstain"),
        "raw_field_judgement_available": int(valid_judgement),
    }


def inspect_response(response, primary_status, case):
    """Accept complete JSON only, even when finish_reason says length."""
    result = {"primary_status": primary_status, "format_class": "unavailable_response",
              "complete_json": False, "strict_schema_valid": False, "normalized_fields": None,
              "finish_reason": response.get("finish_reason") if response else None,
              "quote_verification": None}
    if not response:
        return result
    if response.get("status") != "ok" or not isinstance(response.get("content"), str):
        result["format_class"] = "provider_or_empty_content_failure"
        return result
    try:
        value = parse_object(response["content"])
    except ResponseError:
        result["format_class"] = "truncation" if response.get("finish_reason") == "length" else "invalid_json"
        return result
    result["complete_json"] = True
    result["normalized_fields"] = normalize_complete_object(value)
    try:
        parse_prediction(response["content"])
    except ResponseError as error:
        result["format_class"] = "complete_json_response_format_failure"
        result["strict_schema_error"] = str(error)
    else:
        result["strict_schema_valid"] = True
        result["format_class"] = "strict_schema_valid"
    if isinstance(value.get("evidence"), list):
        verification, _ = verify_evidence(value["evidence"], case)
        result["quote_verification"] = verification
    return result


def cached_decision(prepared, prediction):
    """Only the decision-stage cache qualifies; extractor output is never scored."""
    if not prediction:
        return None, None
    for call_id in reversed(prediction.get("trace") or []):
        if not isinstance(call_id, str) or len(call_id) != 32 or any(c not in "0123456789abcdef" for c in call_id):
            raise ValueError("Unexpected cached response identity")
        path = Path(prepared) / "responses" / (call_id + ".json")
        if not path.exists():
            continue
        response = json.loads(path.read_text(encoding="utf-8"))
        if response.get("stage") == "decision":
            if response.get("call_id") != call_id or response.get("model") != prediction.get("model"):
                raise ValueError("Cached decision provenance mismatch")
            return response, {"call_id": call_id, "sha256": digest(path.read_bytes())}
    return None, None


def analyze(prepared, output=None, draws=2000):
    prepared = Path(prepared)
    cases, manifest = inference_inputs(prepared)
    primary_path = prepared / "report.json"
    primary = json.loads(primary_path.read_text(encoding="utf-8"))
    if primary["provenance"]["public_input_sha256"] != manifest["public_input_sha256"]:
        raise ValueError("Primary report belongs to another public input cohort")
    key_path = prepared / "scoring_only.jsonl"
    if digest(key_path.read_bytes()) != manifest["scoring_key_sha256"]:
        raise ValueError("Diagnostic scoring key hash mismatch")
    # Read-only analysis opens keys only here. No API module is called.
    gold = {r["case_id"]: r["gold"] for r in read_jsonl(key_path)}
    if set(gold) != {case["case_id"] for case in cases}:
        raise ValueError("Diagnostic key cases disagree")
    report = {
        "diagnostic_label": "Post-hoc field-level response-format analysis; secondary and non-confirmatory",
        "primary_scores_unchanged": True,
        "interpretation": [
            "Primary strict scores retain every recorded parse, schema, provider, and truncation failure.",
            "Secondary scores accept only complete single JSON objects and only present, type-valid fields. They never reconstruct truncated JSON or infer missing answers.",
            "Each condition uses exactly the same field normalization and fixed case denominators.",
            "Missing explanation fields may depress strict scores even when decision fields exist; this can distort apparent cheap-model versus frontier rankings.",
            "A valid JSON decision or exact quote does not establish accounting reasoning. These remain agreements with unvalidated labels, on synthetic evidence that may leak answers.",
            "Raw paragraph agreement alone ignores decision correctness; citable judgement/citation and full joint metrics require an incorrect judgement, and full joint additionally requires the gold type and row.",
            "This post-hoc analysis cannot establish superiority, repair the benchmark's validity, or replace a preregistered evaluation.",
        ],
        "n_companies": primary["n_companies"], "n_cases": len(cases),
        "public_input_sha256": manifest["public_input_sha256"],
        "scoring_key_sha256": manifest["scoring_key_sha256"],
        "primary_report_sha256": digest(primary_path.read_bytes()),
        "conditions": {}, "paired_field_differences": {},
    }
    rows_by_condition = {}
    for name, primary_condition in primary["conditions"].items():
        path = prepared / "predictions" / (name + ".jsonl")
        predictions = {r["case_id"]: r for r in read_jsonl(path)} if path.exists() else {}
        rows, classes, statuses, missing, total_json = [], Counter(), Counter(), Counter(), 0
        for case in cases:
            case_id = case["case_id"]
            prediction = predictions.get(case_id)
            primary_status = prediction.get("status") if prediction else "missing"
            response, provenance = cached_decision(prepared, prediction)
            analysis = inspect_response(response, primary_status, case)
            normalized = analysis["normalized_fields"]
            classes[analysis["format_class"]] += 1
            statuses[primary_status] += 1
            if normalized:
                total_json += 1
                missing.update(normalized["missing_fields"])
            primary_values = outcomes(gold[case_id], prediction or {"status": "missing"})
            row = {"case_id": case_id, "company": case["metadata"]["company"],
                   "outcomes": field_outcomes(gold[case_id], normalized),
                   "primary_outcomes": primary_values, "response_provenance": provenance, **analysis}
            rows.append(row)
        metrics = aggregate(rows)
        intervals = cluster_intervals(rows, draws=draws)
        for metric, interval in intervals.items():
            metrics[metric]["company_cluster_ci95"] = interval
        valid_failure = sum(r["primary_status"] != "ok" and r["complete_json"] for r in rows)
        missing_reason = sum(r["complete_json"] and "reason" in r["normalized_fields"]["missing_fields"] for r in rows)
        report["conditions"][name] = {
            "primary_metrics": primary_condition["metrics"], "field_level_metrics": metrics,
            "recorded_primary_status_counts": dict(statuses), "format_class_counts": dict(classes),
            "complete_json_count": total_json, "complete_json_missing_field_counts": dict(missing),
            "complete_json_missing_reason_count": missing_reason,
            "strict_failures_with_complete_json_count": valid_failure,
            "strict_failure_count": sum(s != "ok" for s in (r["primary_status"] for r in rows)),
            "finish_length_with_complete_json_count": sum(r["complete_json"] and r["finish_reason"] == "length" for r in rows),
            "cases": rows,
        }
        rows_by_condition[name] = rows
    for left, right in [("qwen30_direct", "opus_direct"), ("qwen8_direct", "opus_direct"), ("qwen30_evidence", "opus_direct"), ("qwen30_evidence", "qwen30_direct")]:
        if left in rows_by_condition and right in rows_by_condition:
            report["paired_field_differences"][left + "_minus_" + right] = paired_cluster_difference(rows_by_condition[left], rows_by_condition[right], draws=draws)
    target = diagnostic_output_path(prepared, output)
    atomic_json(target, report)
    return report


def repair_schema():
    nullable_row = {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]}
    return {"type": "object", "additionalProperties": False,
            "required": sorted(REQUIRED), "properties": {
                "judgement": {"type": "string", "enum": ["correct", "incorrect", "abstain"]},
                "error_type": {"enum": sorted(ERROR_TYPES) + [None]}, "row": nullable_row,
                "citation": {"anyOf": [{"type": "string", "pattern": "^ASC [0-9]{3}-[0-9]{2}-[0-9]{2}-[0-9]+[A-Z]?$"}, {"type": "null"}]},
                "citation_abstain": {"type": "boolean"},
                "evidence": {"type": "array", "maxItems": 4, "items": {"type": "object", "additionalProperties": False,
                    "required": ["source", "quote", "row"], "properties": {
                        "source": {"type": "string", "enum": ["statement", "transactions"]},
                        "quote": {"type": "string", "minLength": 8, "maxLength": 160}, "row": nullable_row}}},
                "reason": {"type": "string", "maxLength": 700}}}


def prospective_repair_plan(prepared, catalog, ledger):
    """No-spend specification only; deliberately not an executable API runner."""
    cases, manifest = inference_inputs(prepared)
    entry = load_catalog(catalog, FRONTIER)
    parameters = set(entry.get("supported_parameters") or [])
    schema = repair_schema()
    body = {"model": FRONTIER, "max_tokens": 1200, "temperature": 0,
            "reasoning": {"effort": "low"},
            "response_format": {"type": "json_schema", "json_schema": {"name": "audit_decision", "strict": True, "schema": schema}},
            "provider": {"allow_fallbacks": False, "require_parameters": True,
                         "max_price": {"prompt": float(Decimal(entry["pricing"]["prompt"]) * 1000000),
                                       "completion": float(Decimal(entry["pricing"]["completion"]) * 1000000)}}}
    estimates = []
    for case in cases:
        request = {**body, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json_dump(case)}]}
        # Includes schema and all serialized request bytes, not just messages.
        prompt_upper = len(json_dump(request).encode("utf-8")) + 1024
        upper = Decimal(prompt_upper) * Decimal(entry["pricing"]["prompt"]) + Decimal(1200) * Decimal(entry["pricing"]["completion"])
        estimates.append({"case_id": case["case_id"], "prompt_token_upper_bound": prompt_upper, "reserved_upper_bound_usd": str(upper)})
    total = sum((Decimal(e["reserved_upper_bound_usd"]) for e in estimates), Decimal("0"))
    spent = Decimal(ledger_summary(ledger)["reserved_upper_bound_usd"])
    return {"label": "Prospective, explicitly post-hoc frontier formatting study; no API calls performed",
            "executable": False, "condition_name": "opus_format_repair_diagnostic",
            "same_fixed_case_ids": manifest["case_ids"], "public_input_sha256": manifest["public_input_sha256"],
            "request_settings": body, "catalog_required_parameters_present": {p: p in parameters for p in ("reasoning", "response_format", "structured_outputs")},
            "rationale": "Require all JSON fields and lower reasoning effort to test whether missing explanations/truncation explain the primary frontier failure rate. Opus catalog marks reasoning mandatory, so disabling it is not proposed.",
            "reservations": estimates, "prospective_full_cohort_upper_bound_usd": str(total),
            "current_global_reserved_usd": str(spent), "projected_global_reserved_usd": str(spent + total),
            "fits_global_5_usd_cap_at_snapshot": spent + total <= HARD_BUDGET,
            "constraints": ["Keep the primary report and protocol unchanged.", "Run all 48 fixed cases, or report an incomplete diagnostic; do not select cases by outcome.", "Use an isolated diagnostic output directory and a distinct condition ID, but the SAME global locked budget ledger.", "No model fallback or retry; provider schema support must be verified before calls.", "The higher 1200-token budget and changed reasoning/format settings make this a separate post-hoc condition, not a replacement for the 900-token baseline.", "Accountant validation and a preregistered final evaluation remain necessary before superiority claims."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--out")
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    parser.add_argument("--plan-repair", action="store_true")
    parser.add_argument("--catalog")
    parser.add_argument("--ledger", default=str(BASE / "artifacts/api_ledger.jsonl"))
    args = parser.parse_args(argv)
    if args.plan_repair:
        if not args.catalog:
            parser.error("--plan-repair requires --catalog")
        report = prospective_repair_plan(args.prepared, args.catalog, args.ledger)
        if args.out:
            atomic_json(diagnostic_output_path(args.prepared, args.out), report)
        print(json.dumps(report, indent=2))
    else:
        report = analyze(args.prepared, args.out, draws=args.bootstrap_draws)
        print(json.dumps({"diagnostic": str(Path(args.out).resolve() if args.out else Path(args.prepared).resolve() / "raw_output_diagnostics.json"),
                          "n_cases": report["n_cases"], "primary_scores_unchanged": report["primary_scores_unchanged"]}, indent=2))


if __name__ == "__main__":
    main()
