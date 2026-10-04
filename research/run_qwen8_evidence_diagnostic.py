"""Same-cohort Qwen 8B staged diagnostic with public-only inference preparation.

Default action is a no-spend whole-cohort plan. --execute uses the unchanged
research.harness.run under the SAME global ledger, with a local pacing/data-bound
wrapper. --score opens the parent scoring key only after inference. This new
post-hoc condition never replaces the frozen four-condition experiment.

    python -m research.run_qwen8_evidence_diagnostic --prepared research/artifacts/pilot --catalog /tmp/audit-model-catalog.json --reserve-other-usd 2.569704
    python -m research.run_qwen8_evidence_diagnostic --prepared research/artifacts/pilot --catalog /tmp/audit-model-catalog.json --reserve-other-usd 2.569704 --execute --key-file /tmp/key-file
    python -m research.run_qwen8_evidence_diagnostic --prepared research/artifacts/pilot --score
"""
import argparse
import json
import time
import types
from decimal import Decimal
from pathlib import Path
from unittest import mock

from . import harness
from .harness import (BASE, EXTRACT_SYSTEM, HARD_BUDGET, SYSTEM, BudgetError,
                      Ledger, ResponseError, append_jsonl, atomic_json,
                      condition_identity, estimate_cost, inference_inputs,
                      ledger_summary, load_catalog, utc_now, validate_config)
from .metrics import paired_cluster_difference, score_conditions
from .select_pilot import digest, json_dump, read_jsonl


CONDITION = "qwen8_evidence_diagnostic"
MODEL = "qwen/qwen3-8b"


class ProviderHalt(Exception):
    def __init__(self, response, case_id, call_ids, identity):
        self.response, self.case_id, self.call_ids, self.identity = response, case_id, call_ids, identity
        super().__init__("Diagnostic provider failure; stop without automatic retry")


def target_dir(prepared):
    return Path(prepared) / "qwen8_evidence_diagnostic"


def public_prepare(prepared, target):
    cases, manifest = inference_inputs(prepared)
    if len(cases) != 48:
        raise ValueError("The diagnostic requires the same complete 48-case cohort")
    target.mkdir(parents=True, exist_ok=True)
    for name in ("public_inputs.jsonl", "manifest.json"):
        data = (Path(prepared) / name).read_bytes()
        destination = target / name
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError("Public-only diagnostic preparation belongs to another cohort")
        if not destination.exists():
            destination.write_bytes(data)
    # Deliberately no scoring key in this inference preparation directory.
    if (target / "scoring_only.jsonl").exists():
        raise ValueError("Diagnostic inference directory must remain public-only")
    return cases, manifest


def validate_settings(config, entry):
    validate_config(config)
    if set(config["conditions"]) != {CONDITION}:
        raise ValueError("Only the separate Qwen8 evidence diagnostic condition is allowed")
    condition = config["conditions"][CONDITION]
    if condition["model"] != MODEL or condition["method"] != "evidence_then_decision" or condition.get("reasoning_enabled") is not False:
        raise ValueError("Diagnostic must use exact Qwen8, two calls, and disabled reasoning")
    if "reasoning" not in entry.get("supported_parameters", []):
        raise ValueError("Catalog must support the explicit reasoning setting")
    if condition["max_prior_analysis_extra_utf8_bytes"] != 6000 or condition["inter_call_delay_seconds"] != 1:
        raise ValueError("Preserve the registered 6000-byte analysis cap and one-second pacing")


def plan(prepared, config, catalog, ledger_path, reserve_other="0"):
    cases, manifest = inference_inputs(prepared)
    if len(cases) != 48 or config["selection"] != manifest["selection"]:
        raise ValueError("Same fixed 48-case selection is required")
    entry = load_catalog(catalog, MODEL)
    validate_settings(config, entry)
    others = Decimal(str(reserve_other))
    if not others.is_finite() or others < 0:
        raise ValueError("Other-condition reserve must be finite and nonnegative")
    condition = config["conditions"][CONDITION]
    identity = condition_identity(condition, config, manifest)
    estimates = []
    for case in cases:
        extract_messages = [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": json_dump(case)}]
        extract_cost, extract_bound = estimate_cost(extract_messages, entry, config["max_completion_tokens"])
        direct_messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json_dump(case)}]
        _, direct_bound = estimate_cost(direct_messages, entry, config["max_completion_tokens"])
        second_bound = direct_bound + condition["max_prior_analysis_extra_utf8_bytes"]
        if second_bound + config["max_completion_tokens"] > entry["context_length"]:
            raise ValueError("Bounded staged decision exceeds context")
        decision_cost = Decimal(second_bound) * Decimal(entry["pricing"]["prompt"]) + Decimal(config["max_completion_tokens"]) * Decimal(entry["pricing"]["completion"])
        estimates.append({"case_id": case["case_id"], "extract_token_upper_bound": extract_bound,
                          "decision_token_upper_bound": second_bound,
                          "two_call_upper_bound_usd": str(extract_cost + decision_cost)})
    events = list(read_jsonl(ledger_path)) if Path(ledger_path).exists() else []
    actual_reservations = sum((Decimal(e["reserved_usd"]) for e in events if e.get("event") == "reservation" and e.get("condition_id") == identity), Decimal("0"))
    full = sum((Decimal(e["two_call_upper_bound_usd"]) for e in estimates), Decimal("0"))
    additional = max(full - actual_reservations, Decimal("0"))
    global_reserved = Decimal(ledger_summary(ledger_path)["reserved_upper_bound_usd"])
    return {"label": "Post-hoc Qwen8 evidence diagnostic; original fixed 48 cases and 900-token per-call cap",
            "condition": CONDITION, "condition_id": identity, "n_cases": 48,
            "public_input_sha256": manifest["public_input_sha256"], "case_ids": manifest["case_ids"],
            "full_cohort_upper_bound_usd": str(full), "additional_upper_bound_usd": str(additional),
            "global_reserved_usd": str(global_reserved), "reserve_other_conditions_usd": str(others),
            "projected_global_including_other_conditions_usd": str(global_reserved + additional + others),
            "whole_cohort_fits_5_usd_cap": global_reserved + additional + others <= HARD_BUDGET,
            "per_case_reservations": estimates, "settings": config,
            "interpretation": "Two-call versus one-call comparison is a separate post-hoc pipeline condition. Same inputs/labels remain unvalidated and may contain synthetic shortcuts. Provider failures do not establish model capability."}, cases, manifest, entry


def execute(args, config):
    target = target_dir(args.prepared)
    if (target / "halted.json").exists():
        raise RuntimeError("Diagnostic halted after provider failure; no automatic continuation")
    specification, cases, manifest, _ = plan(args.prepared, config, args.catalog, args.ledger, args.reserve_other_usd)
    if not specification["whole_cohort_fits_5_usd_cap"]:
        raise BudgetError("Complete 48-case diagnostic plus other conditions cannot fit global $5; no calls started")
    public_prepare(args.prepared, target)
    atomic_json(target / "diagnostic_specification.json", {**specification, "wrapper_implementation_sha256": digest(Path(__file__).read_bytes())})
    case_map = {case["case_id"]: case for case in cases}
    call_ids, last_completion = {}, [None]
    original_call = harness.call_api
    original_ledger = harness.Ledger
    identity = specification["condition_id"]

    class WholeCohortLedger(original_ledger):
        def __enter__(self):
            super().__enter__()
            try:
                current = plan(args.prepared, config, args.catalog, args.ledger, args.reserve_other_usd)[0]
                if not current["whole_cohort_fits_5_usd_cap"]:
                    raise BudgetError("Budget changed before locked whole-cohort preflight; no calls started")
            except Exception:
                self.__exit__()
                raise
            return self

    def bounded_paced_call(messages, model, entry, current_config, key, ledger, prepared, condition, condition_id, case_id, stage):
        if stage == "decision":
            base = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json_dump(case_map[case_id])}]
            extra = len(json_dump(messages).encode("utf-8")) - len(json_dump(base).encode("utf-8"))
            if extra > config["conditions"][CONDITION]["max_prior_analysis_extra_utf8_bytes"]:
                raise ResponseError("Staged analysis exceeds the preregistered 6000-byte extra-input cap; no decision request billed")
        if last_completion[0] is not None:
            delay = 1 - (time.monotonic() - last_completion[0])
            if delay > 0:
                time.sleep(delay)
        response, call_id = original_call(messages, model, entry, current_config, key, ledger, prepared, condition, condition_id, case_id, stage)
        last_completion[0] = time.monotonic()
        call_ids.setdefault(case_id, []).append(call_id)
        if response["status"] != "ok":
            raise ProviderHalt(response, case_id, call_ids[case_id], condition_id)
        return response, call_id

    run_args = types.SimpleNamespace(condition=CONDITION, prepared=str(target), catalog=args.catalog,
                                     key_file=args.key_file, limit=args.limit, ledger=args.ledger)
    try:
        with mock.patch.object(harness, "Ledger", WholeCohortLedger), mock.patch.object(harness, "call_api", bounded_paced_call):
            result = harness.run(run_args, config)
    except ProviderHalt as failure:
        append_jsonl(harness.prediction_path(target, CONDITION), {
            "case_id": failure.case_id, "condition": CONDITION, "condition_id": failure.identity,
            "model": MODEL, "status": failure.response["status"], "prediction": None,
            "trace": failure.call_ids, "time": utc_now(), "error": "Provider failure stopped the post-hoc diagnostic; no automatic retry"})
        atomic_json(target / "halted.json", {"case_id": failure.case_id, "status": failure.response["status"], "automatic_continuation_prohibited": True})
        result = {"condition": CONDITION, "halted": True, "case_id": failure.case_id}
    return {**result, "diagnostic_directory": str(target.resolve()), "primary_protocol_unchanged": True}


def score(args, config):
    cases, manifest = inference_inputs(args.prepared)
    target = target_dir(args.prepared)
    key = Path(args.prepared) / "scoring_only.jsonl"
    if digest(key.read_bytes()) != manifest["scoring_key_sha256"]:
        raise ValueError("Hidden scoring key hash mismatch")
    gold = {r["case_id"]: r["gold"] for r in read_jsonl(key)}
    predicted = list(read_jsonl(harness.prediction_path(target, CONDITION)))
    identity = condition_identity(config["conditions"][CONDITION], config, manifest)
    if len({r["case_id"] for r in predicted}) != len(predicted) or any(r.get("condition_id") != identity or r.get("model") != MODEL for r in predicted):
        raise ValueError("Post-hoc prediction provenance mismatch")
    predictions = {CONDITION: {r["case_id"]: r for r in predicted}}
    for baseline in ("qwen8_direct", "opus_direct"):
        path = harness.prediction_path(args.prepared, baseline)
        if path.exists():
            predictions[baseline] = {r["case_id"]: r for r in read_jsonl(path)}
    report = score_conditions(cases, gold, predictions, draws=args.bootstrap_draws)
    report.update(evaluation_label="Post-hoc Qwen8 staged evidence diagnostic; unvalidated-key agreement", posthoc_condition=CONDITION,
                  primary_protocol_unchanged=True, provenance=manifest,
                  settings_difference="Qwen8 staged extraction+decision uses two calls, each900tokens, disabled reasoning and one-second pacing; Qwen8 direct used one900token call.",
                  cost_summary=ledger_summary(args.ledger))
    for baseline in ("qwen8_direct", "opus_direct"):
        if baseline in report["conditions"]:
            report["paired_differences"][CONDITION + "_minus_" + baseline] = paired_cluster_difference(report["conditions"][CONDITION]["cases"], report["conditions"][baseline]["cases"], draws=args.bootstrap_draws)
    atomic_json(target / "report.json", report)
    return {"report": str((target / "report.json").resolve()), "n_cases": 48, "posthoc_condition": CONDITION}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--config", default=str(BASE / "config/qwen8_evidence_diagnostic.json"))
    parser.add_argument("--catalog")
    parser.add_argument("--ledger", default=str(BASE / "artifacts/api_ledger.jsonl"))
    parser.add_argument("--key-file")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reserve-other-usd", default="0")
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true")
    action.add_argument("--score", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.score:
        result = score(args, config)
    elif args.execute:
        if not args.catalog:
            parser.error("--execute requires --catalog")
        result = execute(args, config)
    else:
        if not args.catalog:
            parser.error("Planning requires --catalog")
        result = plan(args.prepared, config, args.catalog, args.ledger, args.reserve_other_usd)[0]
        atomic_json(target_dir(args.prepared) / "prospective_plan.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
