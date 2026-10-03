#!/usr/bin/env python3
"""Reproducible offline audit of IntelliAudit single-error exam/key packages.

Uses only the Python standard library. Never calls a model or the network.
Metadata baselines fit their lookup tables on training labels only. Baselines
using error_type are explicitly oracle diagnostics, because the exam does not
supply that field. This audit checks consistency and shortcuts, not whether an
accounting paragraph is the legally correct authority for a case.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
from pathlib import Path


ROW = re.compile(r"^\[row (\d+)\]: (.*?)(?: \| (\(?\$[\d,]+\)?))? \[SEP\]$")
PART = re.compile(r": ([+−-])([\d,]+) \((increase|decrease|inflow|outflow)\)")
OLD_TX = re.compile(r"^\[row (\d+)\] (.*?): (.*)$")
NEW_TX = re.compile(r"^\[(.*?)\] (.*)$")


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def identity(row):
    return row.get("exam_id", row.get("sample_id"))


def statement_key(row):
    meta = row["metadata"]
    return (str(meta.get("cik", meta["company"])), meta["fiscal_year"], meta["statement_type"])


def money(text):
    return int(text.strip("()$").replace(",", "")) * (-1 if text.startswith("(") else 1)


def parse_rows(text):
    out = []
    for line in text.splitlines():
        match = ROW.match(line)
        if match:
            idx, label, val = match.groups()
            out.append({"idx": int(idx), "label": label, "value": money(val) if val else None})
    return out


def parse_ledger(text):
    out = []
    for line in text.splitlines():
        match = OLD_TX.match(line)
        if match:
            idx, label, body = match.groups()
            idx = int(idx)
        else:
            match = NEW_TX.match(line)
            if not match:
                continue
            label, body = match.groups()
            idx = None
        signed = [(-1 if sign in "−-" else 1) * int(amt.replace(",", ""))
                  for sign, amt, _word in PART.findall(body)]
        if signed:
            out.append({"label": label, "idx": idx, "parts": signed, "sum": sum(signed)})
    return out


def majority(rows, feature):
    table = collections.defaultdict(collections.Counter)
    fallback = collections.Counter()
    for row in rows:
        label = row["gold"]
        table[feature(row)][label] += 1
        fallback[label] += 1
    # Stable lexical tie-breaking makes outcomes reproducible across Python versions.
    pick = lambda c: sorted(c, key=lambda label: (-c[label], str(label)))[0] if c else None
    return {key: pick(counts) for key, counts in table.items()}, pick(fallback)


def score(train, test, feature):
    table, fallback = majority(train, feature)
    hit = sum(table.get(feature(row), fallback) == row["gold"] for row in test)
    return {"correct": hit, "n": len(test), "accuracy": hit / len(test) if test else None,
            "unseen_feature_n": sum(feature(row) not in table for row in test)}


def shortcuts(joined):
    rows = [{"gold": key["ground_truth_citations"]["asc_full"],
             "company": exam["metadata"]["company"],
             "statement": exam["metadata"]["statement_type"],
             "error_type": key.get("error_type"), "rule": key.get("rule_id"),
             "id": identity(exam)} for exam, key in joined
            if key.get("ground_truth_citations", {}).get("citable")]
    train, test = [], []
    for row in rows:
        bucket = int(hashlib.sha256(str(row["id"]).encode()).hexdigest()[:8], 16) % 5
        (test if bucket == 0 else train).append(row)
    features = {"statement_type": lambda row: row["statement"],
                "oracle_error_type_and_statement": lambda row: (row["error_type"], row["statement"]),
                "oracle_rule_id_and_statement": lambda row: (row["rule"], row["statement"])}
    out = {"denominator": "only cases whose key marks citable=true",
           "split": "sha256(exam_id or sample_id) modulo 5; bucket 0 test; others train",
           "n": len(rows), "train_n": len(train), "test_n": len(test), "features": {}}
    companies = sorted({row["company"] for row in rows})
    for name, feature in features.items():
        folds = {}
        for company in companies:
            folds[company] = score([r for r in rows if r["company"] != company],
                                   [r for r in rows if r["company"] == company], feature)
        n = sum(fold["n"] for fold in folds.values())
        hits = sum(fold["correct"] for fold in folds.values())
        out["features"][name] = {"resubstitution_diagnostic": score(rows, rows, feature),
                                "heldout_item": score(train, test, feature),
                                "leave_one_company_out": {"correct": hits, "n": n,
                                    "micro_accuracy": hits / n if n else None,
                                    "macro_accuracy": sum(f["accuracy"] for f in folds.values()) / len(folds) if folds else None,
                                    "folds": folds}}
    return out


def distribution(rows, field):
    return dict(sorted(collections.Counter(field(row) for row in rows).items(), key=lambda item: str(item[0])))


def numeric_leak(joined):
    per_rule = collections.defaultdict(collections.Counter)
    examples = []
    for exam, key in joined:
        detail = key.get("injection_detail") or {}
        if "original_value" not in detail:
            continue
        rid = key.get("rule_id")
        counts = per_rule[rid]
        counts["numeric_cases"] += 1
        label = detail.get("row_label")
        # Duplicate captions can be qualified by original section in newer evidence.
        candidates = [line for line in parse_ledger(exam.get("transaction_data", ""))
                      if line["label"] == label or line["label"].startswith(str(label) + " (")]
        counts["target_has_component_evidence"] += bool(candidates)
        original, shown = detail["original_value"], detail.get("erroneous_value")
        orig_hit = any(line["sum"] == original for line in candidates)
        shown_hit = any(line["sum"] == shown for line in candidates)
        counts["components_sum_to_original"] += orig_hit
        counts["absolute_component_sum_equals_original_magnitude"] += any(abs(line["sum"]) == abs(original) for line in candidates)
        counts["components_sum_to_erroneous_as_booked"] += shown_hit
        counts["single_component_equals_original_magnitude"] += any(abs(part) == abs(original)
                                                                     for line in candidates for part in line["parts"])
        if orig_hit and len(examples) < 8:
            examples.append({"id": identity(exam), "rule_id": rid, "label": label,
                             "original": original, "shown": shown, "parts": candidates[0]["parts"]})
    total = collections.Counter()
    for counts in per_rule.values():
        total.update(counts)
    return {"definition": "signed component sums on target caption compared with key original_value; partial evidence coverage is preserved",
            "totals": dict(total), "by_rule": {rid: dict(c) for rid, c in sorted(per_rule.items())},
            "examples": examples}


def quantiles(values):
    if not values:
        return {}
    ordered = sorted(values)
    return {"min": ordered[0], "median": ordered[len(ordered) // 2],
            "p90": ordered[math.floor(0.9 * (len(ordered) - 1))], "max": ordered[-1]}


def residuals(clean, structured_dir):
    literal = {"statements_with_residual_suffix": sum("(residual)" in row["statement_text"] for row in clean),
               "residual_suffix_rows": sum("(residual)" in line for row in clean for line in row["statement_text"].splitlines()),
               "note": "suffix absence alone does not prove residual elimination; upstream renames plug lines"}
    if not structured_dir or not Path(structured_dir).is_dir():
        literal["structured_audit"] = "not available: clean JSON rows required to distinguish plugs from real other-assets captions"
        return literal
    by_type = collections.defaultdict(lambda: {"statements": 0, "with_residual": 0,
                                               "line_rows": 0, "residual_rows": 0,
                                               "absolute_line_mass": 0, "absolute_residual_mass": 0,
                                               "per_statement_absolute_share": []})
    examples = []
    for path in sorted(Path(structured_dir).glob("*.json")):
        stmt = json.loads(path.read_text())
        if "rows" not in stmt:
            continue
        lines = [r for r in stmt["rows"] if r.get("kind") == "line" and r.get("value") is not None]
        plug = [r for r in lines if r.get("residual")]
        mass = sum(abs(r["value"]) for r in lines)
        residual_mass = sum(abs(r["value"]) for r in plug)
        counts = by_type[stmt["statement_type"]]
        counts["statements"] += 1
        counts["with_residual"] += bool(plug)
        counts["line_rows"] += len(lines)
        counts["residual_rows"] += len(plug)
        counts["absolute_line_mass"] += mass
        counts["absolute_residual_mass"] += residual_mass
        if mass:
            counts["per_statement_absolute_share"].append(residual_mass / mass)
        if mass and residual_mass / mass > 0.5 and len(examples) < 5:
            examples.append({"file": str(path), "absolute_residual_share": residual_mass / mass,
                             "residual_rows": [{"label": r["label"], "value": r["value"]} for r in plug]})
    for counts in by_type.values():
        counts["per_statement_absolute_share"] = quantiles(counts["per_statement_absolute_share"])
        counts["mass_weighted_share"] = counts["absolute_residual_mass"] / counts["absolute_line_mass"] if counts["absolute_line_mass"] else None
    literal["structured_by_statement_type"] = dict(by_type)
    literal["examples_over_50pct"] = examples
    literal["mass_definition"] = "sum absolute values of kind=line only; excludes all totals/subtotals; descriptive, not total-assets percentage"
    return literal


def provenance(clean, structured_dir):
    facts = [fact for row in clean for fact in row.get("xbrl_json", {}).get("facts", [])]
    duration = [row for row in clean if row["metadata"]["statement_type"] in ("IncomeStatement", "CashFlow")]
    scaled = [row for row in clean if "million" in row["metadata"].get("unit", "").lower()]
    out = {"clean_statements": len(clean), "serialized_facts": len(facts),
           "statement_source_descriptions": distribution(clean, lambda row: row["metadata"].get("source", "MISSING")),
           "statements_with_accession_or_filing_url": sum(any(k in row["metadata"] for k in ("accession", "accn", "filing_url", "source_url")) for row in clean),
           "facts_with_accession_or_filing_url": sum(any(k in fact for k in ("accession", "accn", "filing_url", "source_url")) for fact in facts),
           "duration_statement_n": len(duration),
           "duration_statements_with_only_instant_fact_periods": sum(bool(row.get("xbrl_json", {}).get("facts")) and all("instant" in f.get("period", {}) and "start" not in f.get("period", {}) for f in row["xbrl_json"]["facts"]) for row in duration),
           "scaled_millions_statements": len(scaled),
           "scaled_statements_whose_numeric_table_values_equal_iso4217_fact_values": sum(any(f.get("unit", "").startswith("iso4217:") and any(r["idx"] == f.get("row") and r["value"] == f.get("value") for r in parse_rows(row["statement_text"])) for f in row.get("xbrl_json", {}).get("facts", [])) for row in scaled),
           "interpretation": "decimals=-6 describes precision; it does not multiply an ISO4217 fact value by one million. Instant periods do not represent annual revenues/cash flows. These are scaled internal tables, not valid filing fact exports."}
    if structured_dir and Path(structured_dir).is_dir():
        raw = [json.loads(p.read_text()) for p in Path(structured_dir).glob("*.json")]
        out["structured_clean_n"] = len(raw)
        out["structured_rows_with_accession_or_filing_url"] = sum(any(k in row for k in ("accession", "accn", "filing_url", "source_url")) for stmt in raw for row in stmt.get("rows", []))
    return out


def audit(name, directory, structured_dir=None):
    directory = Path(directory)
    exam = read_jsonl(directory / "exam.jsonl")
    key = read_jsonl(directory / "answer_key.jsonl")
    clean = read_jsonl(directory / "statements_clean.jsonl")
    gold = {identity(row): row for row in key}
    joined = [(row, gold[identity(row)]) for row in exam if identity(row) in gold]
    citations = [row.get("ground_truth_citations", {}) for row in key]
    citable = [g for g in citations if g.get("citable")]
    nonparagraph = [g["asc_full"] for g in citable
                    if not re.fullmatch(r"ASC \d{3}-\d{2}-\d{2}-\d+[A-Z]?|(?:IAS|IFRS) \d+\.(?:\d+\.)*\d+[A-Z]?", g["asc_full"])]
    strict = lambda value: re.sub(r"\(\(.*?\)\)", "", value).strip()
    mismatches = []
    for row in key:
        g = row.get("ground_truth_citations", {})
        if g.get("linkbase_verified") and g.get("asc_full") not in [strict(ref) for ref in g.get("linkbase_reference_set", [])]:
            mismatches.append(identity(row))
    versions = collections.Counter(statement_key(row) for row in exam)
    forms = collections.Counter((row.get("form"), statement_key(row)) for row in exam)
    leakage = {"exam_rule_id_tokens": sum(bool(re.search(r"\b[RI]\d{2}[a-z]?_", json.dumps(row))) for row in exam),
               "exam_citation_codes": sum(bool(re.search(r"\bASC\s+\d|\b(?:IAS|IFRS)\s+\d+\.\d", json.dumps(row))) for row in exam),
               "evidence_contains_clean_row_numbers": sum(bool(OLD_TX.search(line)) for row in exam for line in row.get("transaction_data", "").splitlines()),
               "public_salt_hash_reversibility": "opaque hashes prevent direct semantic reading, not secrecy if generator salt and sample-id construction are public"}
    control_evidence = collections.Counter()
    for row, answer in joined:
        label = "control" if answer.get("general_judgement") == "Correct" else "injected"
        control_evidence[label + "_n"] += 1
        control_evidence[label + "_with_ledger_n"] += bool(parse_ledger(row.get("transaction_data", "")))
        control_evidence[label + "_with_supporting_facts_n"] += "Supporting facts" in row.get("transaction_data", "")
    years_by_rule = collections.defaultdict(collections.Counter)
    for row, answer in joined:
        if answer.get("rule_id"):
            years_by_rule[answer["rule_id"]][row["metadata"]["fiscal_year"]] += 1
    return {"name": name, "directory": str(directory),
            "file_sha256": {f: hashlib.sha256((directory / f).read_bytes()).hexdigest() for f in ("exam.jsonl", "answer_key.jsonl", "statements_clean.jsonl")},
            "counts": {"exam": len(exam), "answer_key": len(key), "clean_statements": len(clean),
                       "joined": len(joined), "companies": len({r["metadata"]["company"] for r in exam}),
                       "company_statement_year_groups": len(versions), "controls": sum(r.get("general_judgement") == "Correct" for r in key),
                       "duplicate_exam_ids": len(exam) - len({identity(r) for r in exam}),
                       "duplicate_key_ids": len(key) - len(gold), "exam_without_key": len(exam) - len(joined)},
            "company_counts": distribution(exam, lambda row: row["metadata"]["company"]),
            "statement_counts": distribution(exam, lambda row: row["metadata"]["statement_type"]),
            "year_counts": distribution(exam, lambda row: row["metadata"]["fiscal_year"]),
            "rule_counts": distribution(key, lambda row: row.get("rule_id") or "CONTROL"),
            "error_type_counts": distribution(key, lambda row: row.get("error_type") or "CONTROL"),
            "rule_year_counts": {rid: dict(sorted(counts.items())) for rid, counts in sorted(years_by_rule.items())},
            "gold": {"citable_n": len(citable), "distinct_paragraphs": sorted({g["asc_full"] for g in citable}),
                     "citable_nonparagraph_code_n": len(nonparagraph), "nonparagraph_codes": sorted(set(nonparagraph)),
                     "citation_tiers": dict(collections.Counter(g.get("citation_tier", "MISSING") for g in citations)),
                     "strict_linkbase_flag_mismatch_n": len(mismatches), "mismatch_examples": mismatches[:8],
                     "human_review_fields_in_key_n": sum(any(k in row or k in row.get("ground_truth_citations", {}) for k in ("reviewer", "reviewers", "adjudicated", "review_status", "annotation_status", "human_validated")) for row in key),
                     "standard_version_fields_in_key_n": sum(any(k in row or k in row.get("ground_truth_citations", {}) for k in ("effective_date", "standard_version", "standard_as_of", "applicable_from")) for row in key),
                     "interpretation": "exact paragraph membership in taxonomy references is mechanically checked; it does not prove paragraph governs the alleged violation or that human review happened"},
            "leakage": leakage, "control_evidence": dict(control_evidence),
            "repeated_statement_versions": {"groups_with_more_than_one_version": sum(n > 1 for n in versions.values()),
                                            "version_count_quantiles": quantiles(list(versions.values())),
                                            "forms_present": sorted({row["form"] for row in exam if "form" in row}),
                                            "same_statement_duplicates_within_form": sum(n - 1 for (form, _group), n in forms.items() if form is not None and n > 1),
                                            "warning": "random item splits can share the same base statement across train/test; fit learned systems by company and keep case variants together"},
            "metadata_citation_shortcuts": shortcuts(joined), "numeric_transaction_reconstruction": numeric_leak(joined),
            "residuals": residuals(clean, structured_dir), "provenance": provenance(clean, structured_dir)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", required=True, metavar="NAME=DIR",
                        help="may repeat; DIR must hold exam/key/clean JSONL")
    parser.add_argument("--structured-clean", action="append", default=[], metavar="NAME=DIR",
                        help="optional upstream data/clean folder for residual provenance audit")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    structured = dict(value.split("=", 1) for value in args.structured_clean)
    result = {"audit_schema": "intelliaudit-offline-v1", "model_calls": 0, "datasets": {}}
    for value in args.dataset:
        name, path = value.split("=", 1)
        result["datasets"][name] = audit(name, path, structured.get(name))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for name, row in result["datasets"].items():
        print(name, json.dumps({"counts": row["counts"], "tiers": row["gold"]["citation_tiers"],
                              "numeric_leak": row["numeric_transaction_reconstruction"]["totals"]}, sort_keys=True))
    print("Wrote", output)


if __name__ == "__main__":
    main()
