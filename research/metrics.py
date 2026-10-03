"""Strict agreement metrics for an exploratory, unvalidated-key pilot.

Failures and missing predictions remain in every applicable denominator. Cluster
bootstrap intervals describe these eight companies only, not a target population.
"""
import math
import random
import re
from collections import Counter


ASC_CODE = re.compile(r"ASC\s+(\d{3})-(\d{2})-(\d{2})-(\d+[A-Z]?)", re.I)


def canonical_citation(value):
    """A single full paragraph code; lists, explanations and substrings fail."""
    if not isinstance(value, str):
        return None
    match = ASC_CODE.fullmatch(value.strip())
    return "ASC " + "-".join(match.groups()).upper() if match else None


def topic(value):
    code = canonical_citation(value)
    return code[:7] if code else None


def outcomes(gold, result):
    prediction = result.get("prediction") or {}
    ok = result.get("status") == "ok"
    control = gold["general_judgement"] == "Correct"
    citable = bool(gold["ground_truth_citations"].get("citable"))
    truth = gold["ground_truth_citations"].get("asc_full")
    identification = gold.get("error_identification") or {}
    citation = canonical_citation(prediction.get("citation"))
    judgement = prediction.get("judgement")
    expected = "correct" if control else "incorrect"
    row = prediction.get("row")
    # bool is a subclass of int, but cannot identify a statement row.
    row_correct = type(row) is int and row == identification.get("problematic_entry")
    evidence = result.get("evidence_verification") or {}
    return {
        "judgement_accuracy": int(ok and judgement == expected),
        "clean_specificity": int(ok and judgement == "correct") if control else None,
        "detection_sensitivity": int(ok and judgement == "incorrect") if not control else None,
        "error_type_accuracy": int(ok and judgement == "incorrect" and prediction.get("error_type") == gold.get("error_type")) if not control else None,
        "row_accuracy": int(ok and judgement == "incorrect" and row_correct) if not control else None,
        "joint_detection_type_row": int(ok and judgement == "incorrect" and prediction.get("error_type") == gold.get("error_type") and row_correct) if not control else None,
        "unvalidated_full_citation_agreement": int(ok and citation is not None and citation == canonical_citation(truth)) if citable else None,
        "unvalidated_topic_agreement": int(ok and citation is not None and topic(citation) == topic(truth)) if citable else None,
        "joint_detection_type_row_full_citation": int(ok and judgement == "incorrect" and prediction.get("error_type") == gold.get("error_type") and row_correct and citation is not None and citation == canonical_citation(truth)) if citable else None,
        "noncitable_citation_abstention": int(ok and prediction.get("citation") is None) if not citable else None,
        "decision_abstention_rate": int(ok and judgement == "abstain"),
        "citation_abstention_rate": int(ok and prediction.get("citation") is None),
        "failure_rate": int(not ok),
        "verified_quote_rate": int(ok and evidence.get("provided", 0) > 0 and evidence.get("verified") == evidence.get("provided")),
    }


def aggregate(rows):
    names = sorted({name for row in rows for name in row["outcomes"]})
    output = {}
    for name in names:
        values = [r["outcomes"][name] for r in rows if r["outcomes"].get(name) is not None]
        output[name] = {"value": sum(values) / len(values) if values else None,
                        "numerator": sum(values), "denominator": len(values)}
    return output


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def cluster_intervals(rows, draws=2000, seed=20261002):
    companies = sorted({r["company"] for r in rows})
    groups = {c: [r for r in rows if r["company"] == c] for c in companies}
    samples = {name: [] for name in aggregate(rows)}
    rng = random.Random(seed)
    for _ in range(draws):
        sampled = [r for c in rng.choices(companies, k=len(companies)) for r in groups[c]]
        for name, metric in aggregate(sampled).items():
            if metric["value"] is not None:
                samples[name].append(metric["value"])
    return {name: [percentile(values, .025), percentile(values, .975)] if values else None
            for name, values in samples.items()}


def paired_cluster_difference(left_rows, right_rows, draws=2000, seed=20261002):
    """Resample the SAME companies for both conditions; left minus right."""
    if {r["case_id"] for r in left_rows} != {r["case_id"] for r in right_rows}:
        raise ValueError("Paired comparison requires identical case sets")
    companies = sorted({r["company"] for r in left_rows})
    lg = {c: [r for r in left_rows if r["company"] == c] for c in companies}
    rg = {c: [r for r in right_rows if r["company"] == c] for c in companies}
    la, ra = aggregate(left_rows), aggregate(right_rows)
    samples = {name: [] for name in la}
    rng = random.Random(seed)
    for _ in range(draws):
        clusters = rng.choices(companies, k=len(companies))
        a = aggregate([r for c in clusters for r in lg[c]])
        b = aggregate([r for c in clusters for r in rg[c]])
        for name in samples:
            if a[name]["value"] is not None and b[name]["value"] is not None:
                samples[name].append(a[name]["value"] - b[name]["value"])
    return {name: {"difference": la[name]["value"] - ra[name]["value"] if la[name]["value"] is not None and ra[name]["value"] is not None else None,
                   "ci95": [percentile(values, .025), percentile(values, .975)] if values else None}
            for name, values in samples.items()}


def score_conditions(inputs, gold_by_id, predictions_by_condition, draws=2000):
    report = {"evaluation_label": "Exploratory development pilot; agreement with unvalidated labels, not accounting correctness",
              "caveat": "Eight purposively limited companies; company-cluster bootstrap is unstable at n=8. No final-test, representative-population, or superiority claim.",
              "n_companies": len({r["metadata"]["company"] for r in inputs}),
              "n_cases": len(inputs), "conditions": {}, "paired_differences": {}}
    rows_by_condition = {}
    for condition, predictions in predictions_by_condition.items():
        rows = []
        statuses = Counter()
        for case in inputs:
            cid = case["case_id"]
            result = predictions.get(cid, {"status": "missing", "prediction": None})
            statuses[result["status"]] += 1
            gold = gold_by_id[cid]
            rows.append({"case_id": cid, "company": case["metadata"]["company"],
                         "outcomes": outcomes(gold, result), "status": result["status"],
                         "prediction": result.get("prediction"),
                         "gold_judgement": gold["general_judgement"],
                         "gold_error_type": gold.get("error_type"),
                         "gold_row": (gold.get("error_identification") or {}).get("problematic_entry"),
                         "gold_citation": gold["ground_truth_citations"].get("asc_full"),
                         "gold_citable": gold["ground_truth_citations"].get("citable"),
                         "evidence_verification": result.get("evidence_verification")})
        metrics = aggregate(rows)
        for name, interval in cluster_intervals(rows, draws=draws).items():
            metrics[name]["company_cluster_ci95"] = interval
        report["conditions"][condition] = {"metrics": metrics, "statuses": dict(statuses), "cases": rows}
        rows_by_condition[condition] = rows
    comparisons = [("qwen30_evidence", "qwen30_direct"), ("qwen30_direct", "opus_direct"), ("qwen30_evidence", "opus_direct"), ("qwen8_direct", "opus_direct")]
    for left, right in comparisons:
        if left in rows_by_condition and right in rows_by_condition:
            report["paired_differences"][left + "_minus_" + right] = paired_cluster_difference(rows_by_condition[left], rows_by_condition[right], draws=draws)
    return report
