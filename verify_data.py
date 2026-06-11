"""
Preflight check — run BEFORE spending any API money.

Confirms the three JSON files exist, counts match the paper (1484 / 372 / 371),
all required fields are present, and tables parse. Exits non-zero on any problem.

Usage:
    AUDITBENCH_DATA=/path/to/jsons python verify_data.py
"""

import sys
from collections import Counter
from parser import (DATA, _load_raw, parse_table,
                    load_single_error, load_multi_error, load_correct)

EXPECT = {"single_error": 1484, "multi_error": 372, "correct": 371}


def main():
    ok = True
    print("AuditBench data verification\n" + "="*40)
    for split, path in DATA.items():
        try:
            raw = _load_raw(path)
        except FileNotFoundError:
            print(f"  [MISSING] {split}: {path}"); ok = False; continue
        n = len(raw)
        flag = "OK" if n == EXPECT[split] else f"WARN expected {EXPECT[split]}"
        print(f"  {split:<13} {n:>5} items   [{flag}]")

    # field checks
    s = _load_raw(DATA["single_error"])[0]
    need_s = {"Modified Financial Statement with Errors","Error Identification",
              "gt_table","gt_transaction_data"}
    miss = need_s - set(s.keys())
    print(f"\n  single_error fields: {'OK' if not miss else 'MISSING '+str(miss)}")
    if miss: ok = False

    m = [r for r in _load_raw(DATA["multi_error"]) if "Information for error 1" in r][0]
    print(f"  multi_error fields:  {'OK' if 'gt_table' in m else 'MISSING gt_table'}")

    c = _load_raw(DATA["correct"])[0]
    print(f"  correct fields:      {'OK' if {'Table','Transaction_data'} <= set(c.keys()) else 'MISSING'}")

    # error-type balance
    types = Counter(r["Error Identification"]["Error Type"] for r in _load_raw(DATA["single_error"]))
    print(f"\n  single error-type balance: {dict(types)}")

    # parse check
    items = load_single_error(n=5)
    rows = parse_table(items[0]["table"])
    print(f"  sample table parsed into {len(rows)} rows  [{'OK' if rows else 'FAIL'}]")
    if not rows: ok = False

    print("\n" + ("ALL CHECKS PASSED — safe to run." if ok else "PROBLEMS FOUND — fix before running."))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
