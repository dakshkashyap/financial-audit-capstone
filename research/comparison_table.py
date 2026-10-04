"""Reproduce the requested results-table layout from recorded outputs; no API calls.

Primary scores remain frozen. Subtopic agreement and token/API-time summaries
are derived reporting statistics, not a new evaluation or a repaired prediction.
"""
import json
from pathlib import Path

from .metrics import canonical_citation
from .select_pilot import digest, read_jsonl

ROOT = Path(__file__).resolve().parent


def subtopic_agreement(cases):
    eligible = [case for case in cases if case["gold_citable"]]
    correct = 0
    for case in eligible:
        predicted = canonical_citation((case.get("prediction") or {}).get("citation"))
        gold = canonical_citation(case.get("gold_citation"))
        if case["status"] == "ok" and predicted and gold and predicted.split("-")[:2] == gold.split("-")[:2]:
            correct += 1
    return {"numerator": correct, "denominator": len(eligible),
            "value": correct / len(eligible) if eligible else None}


def resource_summary(predictions, response_dir):
    """Per-case sums across stages; absent usage never becomes a zero-token call."""
    samples = {"input_tokens": [], "output_tokens": [], "latency": []}
    calls = 0
    for prediction in predictions:
        responses = []
        for call_id in prediction.get("trace", []):
            calls += 1
            path = response_dir / (call_id + ".json")
            responses.append(json.loads(path.read_text()) if path.exists() else {})
        if not responses:
            continue
        for name, field in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
            values = [(response.get("usage") or {}).get(field) for response in responses]
            if all(type(value) in (int, float) and value >= 0 for value in values):
                samples[name].append(sum(values))
        times = [response.get("elapsed_seconds") for response in responses]
        if all(type(value) in (int, float) and value >= 0 for value in times):
            samples["latency"].append(sum(times))
    return {"attempted_cases": len(predictions), "calls": calls,
            **{name: {"mean": sum(values) / len(values) if values else None,
                      "n_cases_with_complete_measurement": len(values)}
               for name, values in samples.items()}}


def percentage(metric):
    return f'{100 * metric["value"]:.1f}%' if metric["value"] is not None else "—"


def make_row(report, condition, model, setup, prediction_path, responses):
    data = report["conditions"][condition]
    metrics = data["metrics"]
    records = list(read_jsonl(prediction_path))
    resources = resource_summary(records, responses)
    subtopic = subtopic_agreement(data["cases"])
    keys = {"general": "judgement_accuracy", "error_type": "error_type_accuracy",
            "error_entry": "row_accuracy", "topic": "unvalidated_topic_agreement",
            "full_citation": "unvalidated_full_citation_agreement"}
    row = {"condition": condition, "model": model,
           "setup": f'{setup} · {data["statuses"].get("ok", 0)}/48 valid',
           **{column: percentage(metrics[key]) for column, key in keys.items()},
           "subtopic": percentage(subtopic), "statuses": data["statuses"],
           "counts": {**{column: {key: metrics[metric][key] for key in ("numerator", "denominator")}
                          for column, metric in keys.items()}, "subtopic": subtopic},
           "resources": resources}
    for column in ("input_tokens", "output_tokens", "latency"):
        value = resources[column]
        mean = value["mean"]
        display = "—" if mean is None else (f"{mean:.1f}s" if column == "latency" else f"{mean:,.0f}")
        row[column] = f'{display} (n={value["n_cases_with_complete_measurement"]})'
    return row


def main():
    pilot = ROOT / "artifacts/pilot"
    primary = json.loads((pilot / "report.json").read_text())
    rows = []
    for condition, model, setup in [
        ("opus_direct", "Claude Opus 5.5", "Direct"),
        ("qwen8_direct", "Qwen3-8B", "Direct"),
        ("qwen30_direct", "Qwen3-30B-A3B", "Direct"),
        ("qwen30_evidence", "Qwen3-30B-A3B", "Evidence → decision"),
    ]:
        rows.append(make_row(primary, condition, model, setup,
                             pilot / "predictions" / (condition + ".jsonl"), pilot / "responses"))
    posthoc = []
    source_reports = [pilot / "report.json"]
    for directory, condition, model, setup in [
        ("frontier_format_diagnostic", "opus_format_diagnostic", "Claude Opus 5.5", "Schema + low reasoning; stopped"),
        ("qwen8_evidence_diagnostic", "qwen8_evidence_diagnostic", "Qwen3-8B", "Evidence → decision; stopped"),
    ]:
        folder = pilot / directory
        path = folder / "report.json"
        source_reports.append(path)
        prediction_path = folder / "predictions.jsonl" if condition == "opus_format_diagnostic" else folder / "predictions" / (condition + ".jsonl")
        posthoc.append(make_row(json.loads(path.read_text()), condition, model, setup, prediction_path, folder / "responses"))
    offline = []
    for condition, setup in [("legacy_local_offline", "Original interface"),
                             ("legacy_local_adapted", "Signed component parser"),
                             ("legacy_local_adapted_verified_citation", "Parser + citation applicability gate")]:
        path = pilot / (condition + "_metrics.json")
        source_reports.append(path)
        report = json.loads(path.read_text())
        metrics = report["conditions"][condition]["metrics"]
        offline.append({"condition": condition, "setup": setup,
                        **{key: metrics[key] for key in ["detection_sensitivity", "joint_detection_type_row", "unvalidated_full_citation_agreement", "decision_abstention_rate", "citation_abstention_rate"]},
                        "api_cost_usd": 0})
    columns = [["model", "Model"], ["setup", "Setup"], ["general", "General"],
               ["error_type", "Error Type"], ["error_entry", "Error Entry"],
               ["topic", "Topic"], ["subtopic", "Subtopic"], ["full_citation", "Full Citation"],
               ["input_tokens", "Input Tokens"], ["output_tokens", "Output Tokens"], ["latency", "Latency"]]
    notes = [
        "Frozen primary development cohort: 48 cases / 8 companies, FY2020–2024; 16 clean, 16 detection-only, 16 nominally citable. These results are not comparable to the user-provided historical screenshot without its exact data, predictions and protocol.",
        "General denominator=48; Error Type and Error Entry=32 injected cases; Topic, Subtopic and Full Citation=16 citable cases. Row agreement is evaluated separately from type agreement. Failures and missing predictions receive zero credit; abstentions are never clean decisions.",
        "Citation scores require a schema-valid response and one syntactically valid full ASC code, then compare its topic, subtopic or full paragraph to the provisional key. They do not establish accounting applicability. Subtopic is a newly derived reporting statistic; primary scores and predictions are unchanged.",
        "Token means sum all requested stages per case, including format-invalid responses, and include only cases with complete provider usage. Each n is the number of cases with the required measurement. Missing usage is excluded, never imputed as zero.",
        "Latency is mean summed measured API request time per attempted case, including failed requests. It excludes local processing and the post-hoc wrapper's pacing, so it is not end-to-end wall time. Heavy rate-limit failures make speed comparisons unreliable.",
        "Post-hoc conditions retain all 48 eligible cases but stopped at the first provider failure: Opus 37 attempted / 11 unrequested (HTTP 503); Qwen8 11 attempted / 37 unrequested (HTTP 429). They cannot replace the frozen baseline or establish a ranking. Opus also changes schema/reasoning/output budget.",
        "The local before/after diagnostic measures parser transfer on synthetic component evidence, with no Stage 2 LLM and forced-offline taxonomy. It is not a complete baseline-versus-pipeline model comparison or evidence of realistic audit efficacy.",
        "Only one frontier family was used. No new GPT-4o, Llama 70B or DeepSeek results were generated. No measured cheap-model superiority is supported."
    ]
    result = {"title": "Financial audit — measured development results", "date": "2026-10-03",
              "columns": columns, "primary_rows": rows, "posthoc_rows": posthoc, "offline_rows": offline,
              "notes": notes, "source_report_sha256": {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in source_reports}}
    target = ROOT / "results/comparison_table.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# Measured development results", "", *[note + "\n" for note in notes[:3]]]
    for title, items in [("Frozen primary comparison", rows), ("Separate incomplete post-hoc diagnostics", posthoc)]:
        lines += ["## " + title, "", "| " + " | ".join(label for _, label in columns) + " |",
                  "| " + " | ".join("---" for _ in columns) + " |"]
        lines += ["| " + " | ".join(row[key] for key, _ in columns) + " |" for row in items]
        lines += [""]
    lines += ["## Measurement notes", "", *["- " + note for note in notes[3:]]]
    (ROOT / "results/comparison_table.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"report": str(target), "primary_rows": rows, "posthoc_rows": posthoc}, indent=2))


if __name__ == "__main__":
    main()
