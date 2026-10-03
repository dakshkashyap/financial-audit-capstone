#!/usr/bin/env python3
"""Offline accession-consistency audit of normalized clean statement cells.

Read only SEC companyfacts snapshots and structured clean tables. Count numeric
alternatives within the same period, and test whether individually matched cell
magnitudes have at least one filing accession in common. This cannot prove that
unmatched/custom-tagged/derived facts were wrong, or establish sign conventions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path


FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F"}


def audit(source, cache, ciks):
    snapshots, counts, ambiguity, inconsistent = [], Counter(), [], []
    tables = [json.loads(p.read_text()) | {"_file": p.name} for p in sorted(Path(source).glob("*.json"))]
    for cik in sorted({str(cik).zfill(10) for cik in ciks}):
        path = Path(cache) / f"CIK{cik}.json"
        if not path.is_file():
            counts["missing_company_cache"] += 1
            continue
        raw = path.read_bytes()
        company = json.loads(raw)
        snapshots.append({"cik": cik, "sha256": hashlib.sha256(raw).hexdigest(),
                          "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"})
        for table in tables:
            if str(table.get("cik", "")).zfill(10) != cik:
                continue
            accession_sets, matched_rows = [], []
            for row in table["rows"]:
                if row.get("value") is None or not row.get("concept"):
                    continue
                namespace, name = row["concept"].split(":", 1)
                pool = company.get("facts", {}).get(namespace, {}).get(name, {}).get("units", {}).get(table.get("currency", "USD"), [])
                candidates = [fact for fact in pool if fact.get("end") == table["period"] and fact.get("form") in FORMS]
                if table["statement_type"] == "BalanceSheet":
                    candidates = [fact for fact in candidates if "start" not in fact]
                else:
                    candidates = [fact for fact in candidates if "start" in fact and
                                  330 <= (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days <= 380]
                if not candidates:
                    counts["no_same_period_annual_candidate_cells"] += 1
                    continue
                scale = 1_000_000 if "millions" in table.get("unit", "").lower() else 1
                counts["same_period_candidate_cells"] += 1
                alternatives = sorted({round(fact["val"] / scale, 3) for fact in candidates})
                if len(alternatives) > 1:
                    counts["cells_with_conflicting_same_period_values"] += 1
                    if len(ambiguity) < 12:
                        ambiguity.append({"table": table["_file"], "concept": row["concept"],
                                          "value_in_table": row["value"], "scaled_sec_alternatives": alternatives,
                                          "accessions": sorted({fact.get("accn") for fact in candidates})})
                matches = [fact for fact in candidates if abs(abs(fact["val"] / scale) - abs(row["value"])) <= .51]
                if not matches:
                    counts["candidate_cells_without_numeric_magnitude_match"] += 1
                    continue
                accession_set = {fact["accn"] for fact in matches}
                accession_sets.append(accession_set)
                matched_rows.append({"concept": row["concept"], "value": row["value"],
                                     "matching_accns": sorted(accession_set)})
            if not accession_sets:
                continue
            counts["tables_with_any_matched_rows"] += 1
            common = set.intersection(*accession_sets)
            if common:
                counts["tables_with_at_least_one_common_accession"] += 1
            else:
                counts["tables_with_no_common_accession_for_matched_rows"] += 1
                inconsistent.append({"table": table["_file"], "period": table["period"],
                                     "matched_row_n": len(matched_rows), "rows": matched_rows})
    return {"scope": "Selected companies' normalized clean tables matched to cached same-period annual SEC companyfacts",
            "model_calls": 0, "network_calls": 0,
            "limitations": ["Magnitude-only comparison does not verify presentation signs",
                            "Derived and custom-tagged/unmatched cells are excluded from accession intersections",
                            "Flat SEC companyfacts can omit custom/dimensional facts; absence of a common accession is a flattened-source inconsistency, not proof each numeric cell is false",
                            "A common accession does not validate filing layout, intended original-versus-restated version, transactions, or standards applicability"],
            "counts": dict(counts), "snapshot_hashes": snapshots,
            "value_ambiguity_examples": ambiguity, "accession_inconsistency_examples": inconsistent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--ciks", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.source, args.cache, args.ciks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
