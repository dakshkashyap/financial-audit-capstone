"""Independently match clean-table cells to cached SEC companyfacts.

This verifies numeric source matches, not filing layout, rule applicability,
transaction authenticity, or accountant validation. No API/model calls.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import urllib.request


def verify(source: Path, cache: Path, ciks: list[str], download: bool = False) -> dict:
    counts = Counter()
    examples, snapshots = [], []
    for cik in sorted(set(ciks)):
        cik = cik.zfill(10)
        target = cache / f"CIK{cik}.json"
        if not target.exists() and download:
            req = urllib.request.Request(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                headers={"User-Agent": "FinancialAuditResearch/0.1 (https://github.com/dakshkashyap/financial-audit-capstone)"},
            )
            with urllib.request.urlopen(req, timeout=40) as response:
                raw = response.read()
            cache.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        if not target.exists():
            counts["missing_snapshot"] += 1
            continue
        raw = target.read_bytes()
        facts = json.loads(raw)
        snapshots.append({"cik": cik, "sha256": hashlib.sha256(raw).hexdigest(),
                          "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"})
        for table_path in sorted(source.glob("*.json")):
            table = json.loads(table_path.read_text())
            if str(table.get("cik", "")).zfill(10) != cik:
                continue
            counts["tables"] += 1
            for row in table.get("rows", []):
                value, concept = row.get("value"), row.get("concept")
                if value is None:
                    continue
                counts["numeric_rows"] += 1
                if not concept or ":" not in concept:
                    counts["derived_or_unmapped"] += 1
                    continue
                namespace, name = concept.split(":", 1)
                node = facts.get("facts", {}).get(namespace, {}).get(name, {})
                pool = node.get("units", {}).get(table.get("currency", "USD"), [])
                candidates = []
                for fact in pool:
                    if fact.get("end") != table["period"] or fact.get("form") not in ("10-K", "10-K/A", "20-F", "20-F/A", "40-F"):
                        continue
                    if table["statement_type"] != "BalanceSheet":
                        try:
                            days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
                        except (KeyError, ValueError):
                            continue
                        if not 330 <= days <= 380:
                            continue
                    elif "start" in fact:
                        continue
                    candidates.append(fact)
                scale = 1_000_000 if "millions" in table.get("unit", "").lower() else 1
                exact = [f for f in candidates if abs(float(f["val"]) / scale - value) <= .51]
                magnitude = [f for f in candidates if abs(abs(float(f["val"]) / scale) - abs(value)) <= .51]
                status = "exact_signed_match" if exact else "magnitude_only_match" if magnitude else "no_same_period_fact" if not candidates else "value_mismatch"
                counts[status] += 1
                match = (exact or magnitude or candidates)
                if len(examples) < 60 or status == "value_mismatch" and sum(e["status"] == status for e in examples) < 20:
                    chosen = match[0] if match else {}
                    accession = chosen.get("accn")
                    examples.append({"table": table_path.name, "row": row["idx"], "concept": concept,
                                     "value_in_table": value, "status": status, "period": table["period"],
                                     "sec_value": chosen.get("val"), "sec_start": chosen.get("start"),
                                     "sec_end": chosen.get("end"), "accession": accession,
                                     "filed": chosen.get("filed"),
                                     "filing_index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.html" if accession else None})
    return {"scope": "Numeric matches in clean tables for selected companies; not full provenance or accounting validation",
            "limitations": ["Current companyfacts may contain restated comparative values", "Magnitude-only matches do not verify sign conventions", "Derived normalized rows need independent reconciliation", "Exact numeric matches do not establish the stated original filing accession"],
            "counts": dict(counts), "snapshots": snapshots, "examples": examples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--ciks", nargs="+", required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.source, args.cache, args.ciks, args.download)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["counts"]))


if __name__ == "__main__":
    main()
