"""Typed patch ops for AuditBench table strings (V0: numerical replace only)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


_ROW_RE = re.compile(
    r"(\[row\s+(\d+)\]\s*:\s*)(.*?)(\s*(?=\[row\s+\d+\]|\Z))",
    re.DOTALL | re.IGNORECASE,
)


def format_value(v: float) -> str:
    """Format a numeric value in AuditBench-ish style."""
    if abs(v - round(v)) < 1e-9:
        iv = int(round(v))
        neg = iv < 0
        s = f"{abs(iv):,}"
        return f"$({s})" if neg else f"${s}"
    neg = v < 0
    s = f"{abs(v):,.2f}"
    return f"$({s})" if neg else f"${s}"


def apply_replace_fact(
    table: str,
    row_idx: int,
    new_value: float,
) -> Tuple[str, Optional[str], Optional[str]]:
    """Replace the value on ``[row row_idx]``; return (new_table, old, new_fmt)."""
    new_fmt = format_value(new_value)
    old_val: Optional[str] = None

    def _sub(m: re.Match) -> str:
        nonlocal old_val
        idx = int(m.group(2))
        if idx != row_idx:
            return m.group(0)
        content = m.group(3).rstrip()
        # strip trailing [SEP] markers for edit, re-append if present
        sep = ""
        if content.endswith("[SEP]"):
            content = content[: -len("[SEP]")].rstrip()
            sep = " [SEP]"
        if "|" not in content:
            # header / no value — cannot patch
            return m.group(0)
        label, old = content.split("|", 1)
        old_val = old.strip()
        rebuilt = f"{label.strip()} | {new_fmt}{sep}"
        return f"{m.group(1)}{rebuilt}{m.group(4)}"

    new_table, n = _ROW_RE.subn(_sub, table)
    if n == 0 or old_val is None:
        return table, None, None
    return new_table, old_val, new_fmt


def make_patch(
    *,
    row_idx: int,
    old_value: Optional[float],
    new_value: float,
    label: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    return {
        "operation": "replace_fact_value",
        "row_idx": row_idx,
        "label": label,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "patch_size": 1,
    }
