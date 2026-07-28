"""
Stage 0 — Table parser and data loaders  (FIXED).

Changes vs. your version:
  * DATA paths now point at a DATA_DIR you set (env var or edit below) instead
    of the non-existent /home/user/workspace/... paths.
  * correct split now reads output_transaction_table_pair.json (not paste.txt).
  * loaders unchanged in schema so the rest of the pipeline still works.
"""

import re
import json
import random
import os
from typing import Dict, List, Optional, Any

# Project root (directory containing this file).
PROJECT_ROOT = os.environ.get("AUDITBENCH_DATA", os.path.dirname(__file__))

# AuditBench data was archived (2026-07) in favour of FinMR/FinAuditing as the
# primary benchmark; it remains fully usable as the baseline via these paths.
_ARCHIVE = os.path.join(PROJECT_ROOT, "archive_auditbench_data")
_DATA_ROOT = _ARCHIVE if os.path.isdir(_ARCHIVE) else PROJECT_ROOT

DATA = {
    "single_error": os.path.join(_DATA_ROOT, "Error_insertion", "wrong_table_data.json"),
    "multi_error":  os.path.join(_DATA_ROOT, "Error_insertion", "wrong_table_data_multiple_errors.json"),
    "correct":      os.path.join(_DATA_ROOT, "transaction_data", "output_transaction_table_pair.json"),
}


def parse_table(raw: str) -> Dict[int, Dict]:
    rows = {}
    pattern = re.compile(r'\[row\s+(\d+)\]\s*:\s*(.*?)(?=\[row\s+\d+\]|\Z)', re.DOTALL)
    for m in pattern.finditer(raw):
        idx = int(m.group(1))
        content = m.group(2).strip().rstrip('[SEP]').strip()
        if '|' in content:
            label, value = content.split('|', 1)
            label = label.strip()
            value = value.replace('[SEP]', '').strip()
        else:
            label = content.replace('[SEP]', '').strip()
            value = None
        rows[idx] = {"label": label, "value": value}
    return rows


def parse_numeric_value(val_str: Optional[str]) -> Optional[float]:
    if not val_str:
        return None
    s = val_str.replace(',', '').replace('$', '').strip()
    negative = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    try:
        v = float(s)
        return -v if negative else v
    except ValueError:
        return None


def _load_raw(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_single_error(seed: int = 42, n: int = 150) -> List[Dict]:
    raw = _load_raw(DATA["single_error"])
    random.seed(seed)
    sample = random.sample(raw, min(n, len(raw)))
    items = []
    for r in sample:
        ei = r["Error Identification"]
        items.append({
            "table":             r["Modified Financial Statement with Errors"],
            "transaction_data":  r["gt_transaction_data"],
            "gt_table":          r["gt_table"],
            "general_judgement": r["General Judgement"],
            "errors": [{
                "error_type":         ei["Error Type"],
                "problematic_entry":  ei["Problematic Entry"],
                "error_resolution":   r.get("Error Resolution", ""),
                "standards_citation": r.get("Standards Citation", ""),
            }],
            "mode": "single_error",
        })
    return items


def load_multi_error(seed: int = 42, n: int = 150) -> List[Dict]:
    raw = _load_raw(DATA["multi_error"])
    # drop any malformed item lacking 'Information for error 1'
    raw = [r for r in raw if "Information for error 1" in r]
    random.seed(seed)
    sample = random.sample(raw, min(n, len(raw)))
    items = []
    for r in sample:
        errors, i = [], 1
        while f"Information for error {i}" in r:
            info = r[f"Information for error {i}"]
            ei = info["Error Identification"]
            errors.append({
                "error_type":         ei["Error Type"],
                "problematic_entry":  ei["Problematic Entry"],
                "error_resolution":   info.get("Error Resolution", ""),
                "standards_citation": info.get("Standards Citation", ""),
            })
            i += 1
        items.append({
            "table":             r["Modified Financial Statement with Errors"],
            "transaction_data":  r["gt_transaction_data"],
            "gt_table":          r["gt_table"],
            "general_judgement": "Incorrect",
            "errors":            errors,
            "mode":              "multi_error",
        })
    return items


def load_correct(seed: int = 42, n: int = 150) -> List[Dict]:
    raw = _load_raw(DATA["correct"])
    random.seed(seed)
    sample = random.sample(raw, min(n, len(raw)))
    items = []
    for r in sample:
        items.append({
            "table":             r["Table"],
            "transaction_data":  r["Transaction_data"],
            "gt_table":          r["Table"],
            "general_judgement": "Correct",
            "errors":            [],
            "mode":              "correct",
            "company":           r.get("Company", ""),
            "sheet_type":        r.get("Sheet_type", ""),
        })
    return items


if __name__ == "__main__":
    for name, loader in [("correct", load_correct),
                         ("single_error", load_single_error),
                         ("multi_error", load_multi_error)]:
        items = loader()
        print(f"{name}: {len(items)} samples | sample errors: {items[0]['errors'][:1]}")
