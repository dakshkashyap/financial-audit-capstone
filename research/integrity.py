"""Offline payload and split checks; passing these is not benchmark validation.

`python -m research.integrity` audits the frozen 48-case development pilot.
`--groups FILE --require-release-ready` additionally checks a curator-side JSONL
partition manifest and exits nonzero unless complete, disjoint identities exist.
Group records use case_id, split, company_id, filing_ids, event_ids, and
variant_group_ids. Every case must have at least one identity in each namespace;
singletons still need explicit IDs, rather than an empty/unknown group.
"""

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "research/artifacts/pilot"
INSPECTED_PUBLIC_SHA256 = "5b07b65a8427ca4615339d1dfc240b02ad08ece654872c1c72ea94c8efaf71b9"
PUBLIC_KEYS = {"case_id", "metadata", "statement_text", "transaction_data"}
METADATA_KEYS = {"cik", "company", "fiscal_year", "period", "statement_type", "unit"}
GROUP_FIELDS = ("filing_ids", "event_ids", "variant_group_ids")
SPLITS = {"train", "development", "validation", "test"}
LEAK_MARKERS = re.compile(
    r"\b(?:rule_id|sample_id|source_exam_id|ground_truth_citations|"
    r"corrected_statement_text|injection_detail|general_judgement|"
    r"linkbase_verified|citation_tier)\b", re.I)


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_payload(record):
    """Fail closed on extra fields, missing accounting context, or keyed labels.

    This is a schema/obvious-marker boundary, not proof that synthetic evidence
    text contains no semantic shortcut or answer. Source documents can contain
    legitimate accounting citations; those are deliberately not forbidden.
    """
    errors = []
    if not isinstance(record, dict):
        return ["payload must be an object"]
    for key in sorted(PUBLIC_KEYS - record.keys()):
        errors.append(f"missing public field: {key}")
    for key in sorted(record.keys() - PUBLIC_KEYS):
        errors.append(f"forbidden public field: {key}")
    for key in ("case_id", "statement_text"):
        if not nonempty(record.get(key)):
            errors.append(f"{key} must be a nonempty string")
    if isinstance(record.get('case_id'), str) and not re.fullmatch(r'case_[0-9a-f]{20}', record['case_id']):
        errors.append('case_id must be an opaque case_<20 hex> identifier')
    if not isinstance(record.get("transaction_data"), str):
        errors.append("transaction_data must be a string (empty is allowed)")
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
        metadata = {}
    for key in sorted(METADATA_KEYS - metadata.keys()):
        errors.append(f"missing metadata field: {key}")
    for key in sorted(metadata.keys() - METADATA_KEYS):
        errors.append(f"forbidden metadata field: {key}")
    for key in METADATA_KEYS - {"fiscal_year"}:
        if not nonempty(metadata.get(key)):
            errors.append(f"metadata.{key} must be a nonempty string")
    cik = metadata.get("cik")
    if not isinstance(cik, str) or not re.fullmatch(r"[0-9]{10}", cik):
        errors.append("metadata.cik must be a canonical 10-digit CIK")
    year = metadata.get("fiscal_year")
    if type(year) is not int or not 1900 <= year <= 2200:
        errors.append("metadata.fiscal_year must be an integer year")
    try:
        date.fromisoformat(metadata.get("period", ""))
    except (TypeError, ValueError):
        errors.append("metadata.period must be an ISO calendar date")
    for key, value in [(k, record.get(k)) for k in PUBLIC_KEYS - {"metadata"}] + [
            (f"metadata.{k}", v) for k, v in metadata.items()]:
        if isinstance(value, str) and LEAK_MARKERS.search(value):
            errors.append(f"private-label marker in {key}")
    return sorted(set(errors))


def validate_public_cases(records):
    errors = []
    ids = []
    if not records:
        errors.append({"error": "empty public cohort"})
    for index, record in enumerate(records):
        cid = record.get("case_id") if isinstance(record, dict) else None
        errors.extend({"index": index, "case_id": cid, "error": message}
                      for message in validate_payload(record))
        if nonempty(cid):
            ids.append(cid)
    duplicate_ids = sorted(cid for cid, count in Counter(ids).items() if count > 1)
    errors.extend({"case_id": cid, "error": "duplicate case_id"} for cid in duplicate_ids)
    return {"passed": not errors, "n_records": len(records),
            "duplicate_case_ids": duplicate_ids, "errors": errors,
            "scope": "Structural whitelist and obvious label-marker checks only; semantic leakage is not certified absent."}


def validate_group_splits(records, expected_case_ids=None, require_test=True):
    """Reject overlap of ANY connected company/filing/event/variant component.

    Identities are curator-side data, never inference features. Lists support
    cases involving multiple companies' filings or multiple underlying events.
    Missing identities fail closed instead of being treated as unique groups.
    """
    errors, token_to_indices, ids = [], defaultdict(list), []
    parents = list(range(len(records)))

    def find(index):
        while index != parents[index]:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(a, b):
        parents[find(b)] = find(a)

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append({"index": index, "error": "group record must be an object"})
            continue
        cid = record.get("case_id")
        if not nonempty(cid):
            errors.append({"index": index, "error": "missing case_id"})
        else:
            ids.append(cid)
        if record.get("split") not in SPLITS:
            errors.append({"case_id": cid, "error": "missing or unsupported split"})
        company = record.get("company_id")
        if not nonempty(company):
            errors.append({"case_id": cid, "error": "missing company_id"})
        else:
            # Numeric CIKs use a consistent representation even if zero-padding differs.
            normalized = str(int(company)) if company.isascii() and company.isdigit() else company.strip().casefold()
            token_to_indices[("company_id", normalized)].append(index)
        for field in GROUP_FIELDS:
            values = record.get(field)
            if not isinstance(values, list) or not values or any(not nonempty(v) for v in values):
                errors.append({"case_id": cid, "error": f"missing or invalid {field}"})
                continue
            for value in values:
                token_to_indices[(field, value.strip())].append(index)
    if not records:
        errors.append({"error": "empty partition manifest"})
    duplicates = sorted(cid for cid, count in Counter(ids).items() if count > 1)
    errors.extend({"case_id": cid, "error": "duplicate case_id"} for cid in duplicates)
    if expected_case_ids is not None:
        expected = list(expected_case_ids)
        if len(set(expected)) != len(expected):
            errors.append({"error": "expected case_ids contain duplicates"})
        if set(expected) != set(ids):
            errors.append({"error": "partition case_ids do not match cohort",
                           "missing": sorted(set(expected) - set(ids)),
                           "extra": sorted(set(ids) - set(expected))})
    split_counts = Counter(r.get("split") for r in records if isinstance(r, dict)
                           and r.get("split") in SPLITS)
    if require_test and (not split_counts.get("test") or not any(
            split_counts.get(s) for s in SPLITS - {"test"})):
        errors.append({"error": "release partition requires test and at least one non-test split"})
    overlaps = []
    for (field, value), indices in sorted(token_to_indices.items()):
        for index in indices[1:]:
            union(indices[0], index)
        splits = sorted({records[i].get("split") for i in indices
                         if records[i].get("split") in SPLITS})
        if len(splits) > 1:
            overlaps.append({"identity_type": field, "identity": value,
                             "splits": splits, "case_ids": sorted({records[i].get("case_id") for i in indices
                                                                     if nonempty(records[i].get("case_id"))})})
    components = defaultdict(list)
    for index in range(len(records)):
        if isinstance(records[index], dict):
            components[find(index)].append(records[index])
    mixed_components = []
    for component in components.values():
        splits = sorted({r.get("split") for r in component if r.get("split") in SPLITS})
        if len(splits) > 1:
            mixed_components.append({"case_ids": sorted(r["case_id"] for r in component if nonempty(r.get("case_id"))),
                                     "splits": splits})
    return {"passed": not errors and not overlaps, "n_records": len(records),
            "split_counts": dict(sorted(split_counts.items())),
            "n_connected_components": len(components), "errors": errors,
            "overlapping_identities": overlaps, "mixed_components": mixed_components,
            "scope": "Identity disjointness only; supplied IDs and source relationships still require provenance verification."}


def duplicate_groups(records, key):
    groups = defaultdict(list)
    for record in records:
        value = key(record)
        if value is not None:
            groups[value].append(record["case_id"])
    return [{"identity": identity, "case_ids": case_ids} for identity, case_ids in sorted(groups.items())
            if len(case_ids) > 1]


def audit(prepared=PILOT, groups_path=None):
    prepared = Path(prepared)
    public = read_jsonl(prepared / "public_inputs.jsonl")
    keys = read_jsonl(prepared / "scoring_only.jsonl")
    manifest = json.loads((prepared / "manifest.json").read_text())
    public_check = validate_public_cases(public)
    public_ids = [r["case_id"] for r in public]
    key_ids = [r["case_id"] for r in keys]
    hashes = {"public_input_sha256": sha256(prepared / "public_inputs.jsonl"),
              "scoring_key_sha256": sha256(prepared / "scoring_only.jsonl")}
    provenance_errors = [f"{field} mismatch" for field, value in hashes.items() if manifest.get(field) != value]
    if len(key_ids) != len(set(key_ids)):
        provenance_errors.append("duplicate scoring case IDs")
    if set(public_ids) != set(key_ids) or public_ids != manifest.get("case_ids"):
        provenance_errors.append("public, scoring, or manifest case IDs disagree")
    if manifest.get("n_cases") != len(public):
        provenance_errors.append("manifest n_cases mismatch")
    groups = read_jsonl(groups_path) if groups_path else [
        {"case_id": r["case_id"], "split": "development", "company_id": r["metadata"].get("cik")}
        for r in public]
    partitions = validate_group_splits(groups, public_ids)
    known_companies = {r['case_id']: r['metadata']['cik'] for r in public}
    for group in groups:
        if not isinstance(group, dict) or group.get('case_id') not in known_companies:
            continue
        company = group.get('company_id')
        expected = known_companies[group['case_id']]
        if not isinstance(company, str) or not company.isascii() or not company.isdigit() or int(company) != int(expected):
            partitions['errors'].append({'case_id': group['case_id'], 'error': 'company_id disagrees with public CIK'})
            partitions['passed'] = False
    inspected = hashes['public_input_sha256'] == INSPECTED_PUBLIC_SHA256
    coarse_groups = duplicate_groups(public, lambda r: ":".join(str(r["metadata"][field])
                                    for field in ("cik", "period", "statement_type")))
    return {"schema_version": 1,
            "study_status": "Frozen inspected development cohort; provisional labels; no publication test certification.",
            "n_cases": len(public), "n_company_clusters": len({r["metadata"]["cik"] for r in public}),
            "provenance": {**hashes, "manifest_sha256": sha256(prepared / "manifest.json"),
                           "recorded_source_commit": manifest.get("source_commit"),
                           "recorded_source_file_hashes": manifest.get("source_files"),
                           "errors": provenance_errors, "passed": not provenance_errors},
            "public_payload": public_check,
            "partition_manifest_provided": bool(groups_path),
            "partition_validation": partitions,
            "development_history": {"passed": not inspected, "known_inspected_cohort": inspected,
                                    "reason": "Inspected public cohort cannot be relabelled as a fresh test" if inspected else "No match to the recorded inspected pilot; curator must verify exposure history"},
            "integrity_release_gate_passed": not inspected and not provenance_errors and public_check["passed"] and partitions["passed"],
            "duplicate_source_exam_ids": duplicate_groups(keys, lambda r: r.get("source_exam_id")),
            "identical_observable_statement_and_evidence": duplicate_groups(public, lambda r: hashlib.sha256(
                json.dumps([r["statement_text"], r["transaction_data"]], ensure_ascii=False).encode()).hexdigest()),
            "shared_company_period_statement_groups": coarse_groups,
            "shared_clean_statement_hashes": duplicate_groups(keys, lambda r: hashlib.sha256(
                r["gold"]["corrected_statement_text"].encode()).hexdigest()
                if isinstance(r.get("gold", {}).get("corrected_statement_text"), str) else None),
            "limitations": [
                "Structural payload checks do not rule out semantic leakage through synthetic transaction evidence.",
                "Company/period/statement matches are coarse source-reuse diagnostics, not verified filing/event IDs.",
                "Missing filing, underlying-event and variant-family identities block disjointness certification; no IDs were invented.",
                "The already inspected 48 cases remain development data even if a later partition file passes identity checks.",
                "Eight selected companies and unvalidated citation labels do not support population generalization or accounting-correctness claims.",
                "Source file hashes are those recorded at original selection; this command does not download or re-audit SEC filings."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, default=PILOT)
    parser.add_argument("--groups", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "research/results/integrity.json")
    parser.add_argument("--require-release-ready", action="store_true",
                        help="Exit 1 if integrity checks cannot certify supplied split identities; this is only one release gate.")
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output already exists; use a fresh path')
    report = audit(args.prepared, args.groups)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        output.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(args.out), "payload_passed": report["public_payload"]["passed"],
                      "provenance_passed": report["provenance"]["passed"],
                      "integrity_release_gate_passed": report["integrity_release_gate_passed"]}))
    return int(args.require_release_ready and not report["integrity_release_gate_passed"])


if __name__ == "__main__":
    raise SystemExit(main())
