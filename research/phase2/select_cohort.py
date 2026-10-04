"""Freeze 24 inspected cases and 12 new-company replication cases before inference."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from research.select_pilot import digest, json_dump, public_input, read_jsonl, source_sha

SEED = "20261003-phase2-v1"


def stratum(gold):
    if gold["general_judgement"] == "Correct":
        return "control"
    return "citable" if gold["ground_truth_citations"].get("citable") else "detection_only"


def prepare(source, original, target):
    source, original, target = map(Path, (source, original, target))
    if target.exists() and any(target.iterdir()):
        raise ValueError("Refusing to replace a frozen cohort")
    records = {r["exam_id"]: r for r in read_jsonl(source / "exam.jsonl")}
    gold = {r["exam_id"]: r for r in read_jsonl(source / "answer_key.jsonl")}
    if set(records) != set(gold):
        raise ValueError("Source exam and key disagree")
    first_manifest = json.loads((original / "manifest.json").read_text())
    for name, expected in first_manifest["source_files"].items():
        if digest((source / name).read_bytes()) != expected:
            raise ValueError("Source revision changed")
    prior = list(read_jsonl(original / "scoring_only.jsonl"))
    old_companies = {r["metadata"]["cik"] for r in read_jsonl(original / "public_inputs.jsonl")}
    old_buckets = defaultdict(list)
    for row in prior:
        eid = row["source_exam_id"]
        old_buckets[(records[eid]["metadata"]["cik"], stratum(gold[eid]))].append(eid)
    selected = [(min(ids, key=lambda eid: digest(SEED + ":dev:" + eid)), "inspected_development")
                for _, ids in sorted(old_buckets.items())]
    if len(selected) != 24 or len(old_companies) != 8:
        raise ValueError("Original pilot does not have the planned 8x3 strata")
    fresh = defaultdict(lambda: defaultdict(list))
    for eid, record in records.items():
        metadata = record["metadata"]
        if metadata["cik"] not in old_companies and 2020 <= metadata["fiscal_year"] <= 2024:
            fresh[metadata["cik"]][stratum(gold[eid])].append(eid)
    categories = ("control", "detection_only", "citable")
    eligible = [cik for cik, buckets in fresh.items() if all(len(buckets[c]) >= 2 for c in categories)]
    new_companies = sorted(eligible, key=lambda cik: digest(SEED + ":company:" + cik))[:2]
    if len(new_companies) != 2:
        raise ValueError("Two unseen companies are required")
    for cik in new_companies:
        for category in categories:
            candidates = sorted(fresh[cik][category], key=lambda eid: digest(SEED + ":fresh:" + eid))
            chosen, used_rules, used_types = [], set(), set()
            for _ in range(2):
                eid = min((e for e in candidates if e not in chosen),
                          key=lambda e: (gold[e].get("rule_id") in used_rules,
                                         records[e]["metadata"]["statement_type"] in used_types,
                                         digest(SEED + ":fresh:" + e)))
                chosen.append(eid)
                used_rules.add(gold[eid].get("rule_id"))
                used_types.add(records[eid]["metadata"]["statement_type"])
                selected.append((eid, "new_company_replication"))
    # All development outputs are scored before any replication result is read.
    selected.sort(key=lambda x: (x[1] != "inspected_development", digest(SEED + ":order:" + x[0])))
    public, scoring, groups = [], [], {}
    for eid, group in selected:
        cid = "phase2_" + digest(SEED + ":opaque:" + eid)[:20]
        public.append(public_input(records[eid], cid))
        scoring.append({"case_id": cid, "source_exam_id": eid, "gold": gold[eid]})
        groups[cid] = group
    target.mkdir(parents=True, exist_ok=True)
    for name, rows in (("public_inputs.jsonl", public), ("scoring_only.jsonl", scoring)):
        (target / name).write_text("".join(json_dump(row) + "\n" for row in rows))
    manifest = {"schema_version": 2, "seed": SEED, "source_commit": source_sha(source),
                "source_files": first_manifest["source_files"], "n_cases": 36,
                "n_companies": 10, "original_companies": sorted(old_companies),
                "new_companies": new_companies, "case_ids": [r["case_id"] for r in public],
                "case_groups": groups, "selection": {"inspected_development": "8 prior companies x 1 case per stratum = 24", "new_company_replication": "2 new companies x 2 cases per stratum = 12", "fiscal_years": [2020, 2024]},
                "strata_by_group": {group: dict(Counter(stratum(gold[eid]) for eid, g in selected if g == group)) for group in set(groups.values())},
                "public_input_sha256": digest((target / "public_inputs.jsonl").read_bytes()),
                "scoring_key_sha256": digest((target / "scoring_only.jsonl").read_bytes()),
                "limitations": ["Development subset was selected from already inspected cases; it is not a new test.", "Replication has only two new companies and uses the same synthetic generator; no significance, population, new-rule, or gold-standard claim.", "All labels remain provisional until the named single-accountant review is actually completed.", "Stratification used the key during preparation; inference receives only the whitelisted public case."]}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"prepared": str(target), "n_cases": 36, "new_companies": new_companies,
                      "public_input_sha256": manifest["public_input_sha256"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="../IntelliAudit/data/benchmark")
    parser.add_argument("--original", default="research/artifacts/pilot")
    parser.add_argument("--out", default="research/artifacts/phase2/experiment_v1")
    args = parser.parse_args()
    prepare(args.source, args.original, args.out)
