"""
finmr_loader.py — loader for the FinMR benchmark (FinAuditing, arXiv:2510.08886).

FinMR is the mathematical-reasoning task of FinAuditing: 332 real-XBRL audit
cases labeled by official DQC (Data Quality Committee) rules. Each item asks:
"identify the reported value of a financial element and calculate the actual
value that should be reported based on calculation relationships."

Three DQC rule families (same three AuditFlow evaluates on):
    DQC_US_0015 — sign consistency          (110 items)
    DQC_US_0117 — dimensional aggregation   (120 items)
    DQC_US_0126 — calculation-tree          (102 items)

Ground truth per item: {"extracted_value": str, "calculated_value": str}.
A prediction is scored correct when BOTH values match (AuditFlow's "Joint ACC").

Run `python download_finmr.py` once first (writes data/finmr/finmr_test.parquet).

Usage:
    from approaches.finmr_benchmark.finmr_loader import load_finmr, parse_gt_answer, values_equal
    items = load_finmr()                       # all 332
    items = load_finmr(dqc="DQC_US_0015")      # one rule family
    items = load_finmr(n=20, seed=42)          # reproducible sample
"""
from __future__ import annotations

import json
import os
import random
import re
from typing import Dict, List, Optional

import pandas as pd

from core.paths import DATA_DIR

PARQUET = os.path.join(DATA_DIR, "finmr", "finmr_test.parquet")


def _clean(s: str) -> str:
    """dqc_id / answer fields arrive JSON-quoted ('\"DQC_US_0015\"')."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s


def parse_gt_answer(answer) -> Dict[str, Optional[str]]:
    """Normalize the GT answer to {'extracted_value','calculated_value'} strings."""
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except json.JSONDecodeError:
            return {"extracted_value": None, "calculated_value": None}
    return {
        "extracted_value": str(answer.get("extracted_value", "")).strip() or None,
        "calculated_value": str(answer.get("calculated_value", "")).strip() or None,
    }


_NUM_RE = re.compile(r"-?[\d,]*\.?\d+")


def _to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    m = _NUM_RE.search(s.replace(",", ""))
    try:
        return float(m.group(0)) if m else None
    except ValueError:
        return None


def values_equal(a: Optional[str], b: Optional[str], rel_tol: float = 1e-6) -> bool:
    """Numeric comparison tolerant of formatting ('-1,284' == '-1284.0')."""
    fa, fb = _to_float(a), _to_float(b)
    if fa is None or fb is None:
        return (a or "").strip() == (b or "").strip()
    if fa == fb:
        return True
    denom = max(abs(fa), abs(fb), 1e-12)
    return abs(fa - fb) / denom <= rel_tol


def load_finmr(dqc: Optional[str] = None, n: Optional[int] = None,
               seed: int = 42) -> List[Dict]:
    """Load FinMR items as dicts: {id, dqc_id, query, gt}."""
    if not os.path.isfile(PARQUET):
        raise FileNotFoundError(
            f"{PARQUET} not found — run `python download_finmr.py` first.")
    df = pd.read_parquet(PARQUET)
    items = []
    for _, row in df.iterrows():
        rec = {
            "id": int(row["id"]),
            "dqc_id": _clean(row["dqc_id"]),
            "query": row["query"],
            "gt": parse_gt_answer(row["answer"]),
        }
        if dqc is None or rec["dqc_id"] == dqc:
            items.append(rec)
    if n is not None and n < len(items):
        random.seed(seed)
        items = random.sample(items, n)
        items.sort(key=lambda r: r["id"])
    return items


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(errors="replace")

    items = load_finmr()
    by_rule: Dict[str, int] = {}
    for it in items:
        by_rule[it["dqc_id"]] = by_rule.get(it["dqc_id"], 0) + 1
    print(f"FinMR loaded: {len(items)} items  {by_rule}")
    it = items[0]
    print(f"sample id={it['id']} rule={it['dqc_id']} gt={it['gt']} "
          f"query_len={len(it['query']):,}")
