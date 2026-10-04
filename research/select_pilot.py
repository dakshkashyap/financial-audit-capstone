"""Build a frozen local pilot; label reads are restricted to this preparation step."""
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


PUBLIC_METADATA = ("company", "cik", "fiscal_year", "statement_type", "period", "unit")


def digest(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def json_dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_jsonl(path):
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def public_input(record, case_id):
    """Positive whitelist: never forward arbitrary source dictionaries."""
    metadata = record.get("metadata") or {}
    return {"case_id": case_id,
            "metadata": {k: metadata[k] for k in PUBLIC_METADATA if k in metadata},
            "statement_text": record["statement_text"],
            "transaction_data": record.get("transaction_data", "")}


def source_sha(source):
    result = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def select(source, out, config):
    source, out = Path(source), Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Preparation target is nonempty; use a new directory to preserve frozen selection")
    records = {r["exam_id"]: r for r in read_jsonl(source / "exam.jsonl")}
    gold = {r["exam_id"]: r for r in read_jsonl(source / "answer_key.jsonl")}
    if set(records) != set(gold):
        raise ValueError("Exam and key IDs disagree")
    buckets = defaultdict(lambda: defaultdict(list))
    for exam_id, record in records.items():
        year = record["metadata"]["fiscal_year"]
        if not config["selection"].get("min_fiscal_year", year) <= year <= config["selection"].get("max_fiscal_year", year):
            continue
        key = gold[exam_id]
        category = "control" if key["general_judgement"] == "Correct" else "citable" if key["ground_truth_citations"].get("citable") else "detection_only"
        buckets[record["metadata"]["cik"]][category].append(exam_id)
    quota = config["selection"]["per_company"]
    eligible = [cik for cik, categories in buckets.items() if all(len(categories[category]) >= n for category, n in quota.items())]
    seed = str(config["selection"]["seed"])
    ordered = sorted(eligible, key=lambda cik: digest(seed + ":company:" + cik))
    companies = ordered[:config["selection"]["n_companies"]]
    if len(companies) != 8:
        raise ValueError("Pilot requires exactly eight eligible companies")
    selected = []
    # Prefer different rules and statement types within each category. This is
    # preparation-only stratification, never a feature passed to inference.
    for cik in companies:
        for category, n in quota.items():
            candidates = sorted(buckets[cik][category], key=lambda eid: digest(seed + ":case:" + eid))
            chosen, used_rules, used_types = [], set(), set()
            while len(chosen) < n:
                best = min((eid for eid in candidates if eid not in chosen),
                           key=lambda eid: (gold[eid].get("rule_id") in used_rules,
                                            records[eid]["metadata"]["statement_type"] in used_types,
                                            digest(seed + ":case:" + eid)))
                chosen.append(best)
                used_rules.add(gold[best].get("rule_id"))
                used_types.add(records[best]["metadata"]["statement_type"])
            selected.extend(chosen)
    selected.sort(key=lambda eid: digest(seed + ":order:" + eid))
    out.mkdir(parents=True, exist_ok=True)
    public, scoring = [], []
    for exam_id in selected:
        case_id = "case_" + digest(seed + ":opaque:" + exam_id)[:20]
        public.append(public_input(records[exam_id], case_id))
        scoring.append({"case_id": case_id, "source_exam_id": exam_id, "gold": gold[exam_id]})
    for name, rows in [("public_inputs.jsonl", public), ("scoring_only.jsonl", scoring)]:
        path = out / name
        path.write_text("".join(json_dump(r) + "\n" for r in rows), encoding="utf-8")
        if name == "scoring_only.jsonl":
            path.chmod(0o600)
    manifest = {"schema_version": 1, "cohort": "frozen exploration/development; not a final or untouched test",
                "selection": config["selection"], "source_commit": source_sha(source),
                "source_files": {name: digest((source / name).read_bytes()) for name in ("exam.jsonl", "answer_key.jsonl")},
                "n_source_cases": len(records), "n_eligible_companies": len(eligible), "n_cases": len(public),
                "companies": [{"cik": cik, "company": next(r["metadata"]["company"] for r in records.values() if r["metadata"]["cik"] == cik)} for cik in companies],
                "strata": dict(Counter("control" if gold[e]["general_judgement"] == "Correct" else "citable" if gold[e]["ground_truth_citations"].get("citable") else "detection_only" for e in selected)),
                "statement_types": dict(Counter(records[e]["metadata"]["statement_type"] for e in selected)),
                "public_input_sha256": digest((out / "public_inputs.jsonl").read_bytes()),
                "scoring_key_sha256": digest((out / "scoring_only.jsonl").read_bytes()),
                "case_ids": [r["case_id"] for r in public],
                "limitations": ["Original synthetic transaction evidence remains in this diagnostic pilot and may leak clean values.", "Gold paragraphs are unvalidated; label agreement cannot establish accounting correctness.", "No claim of population representativeness or company-disjoint generalization."]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
