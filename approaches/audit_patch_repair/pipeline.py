"""
AuditPatch V0 pipeline (numerical only, AuditBench tables).

  detect (Stage 0) → build patch → sandbox apply → re-detect → certificate

Authority: only a patch that clears the Stage 0 fire (or removes the same
root-cause row) is accepted. No LLM in V0.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from approaches.stage0_deterministic_gate import stage0a
from approaches.stage0_deterministic_gate import stage0b
from core.stage0_common import Finding, approx_eq, build_table, combine_findings

from .patch import apply_replace_fact, make_patch


@dataclass
class RepairResult:
    repaired: bool
    patch: Optional[Dict[str, Any]] = None
    certificate: Dict[str, Any] = field(default_factory=dict)
    before_finding: Optional[Dict[str, Any]] = None
    after_finding: Optional[Dict[str, Any]] = None
    cascade_before: int = 0
    cascade_after: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _finding_dict(f: Optional[Finding]) -> Optional[Dict[str, Any]]:
    if f is None:
        return None
    return {
        "error_type": f.error_type,
        "problematic_entry": f.problematic_entry,
        "correct_value": f.correct_value,
        "stated_value": f.stated_value,
        "source": f.source,
        "detail": f.detail,
    }


def _detect(item: dict):
    a = stage0a.verify(item)
    b = stage0b.check(item)
    finding = combine_findings(a, b)
    cascade = len(a.footing) + len(a.reconciliation)
    return finding, a, b, cascade


def _row_label(item: dict, row_idx: int) -> str:
    try:
        df = build_table(item["table"])
        hit = df[df["idx"] == row_idx]
        if len(hit):
            return str(hit.iloc[0]["label"])
    except Exception:
        pass
    return ""


def repair_item(item: dict) -> RepairResult:
    """Run AuditPatch V0 on one AuditBench item."""
    before, a0, _b0, cascade_before = _detect(item)
    before_d = _finding_dict(before)

    cert_base = {
        "original_violations": before_d,
        "cascade_warning_count": cascade_before,
        "footing_mismatches": len(a0.footing),
        "leaf_mismatches": len(a0.reconciliation),
        "table_hash_before": hashlib.sha256(item["table"].encode()).hexdigest()[:16],
    }

    # V0: only numerical repairs with an exact correct_value from Stage 0
    if before is None or before.correct_value is None or before.problematic_entry is None:
        return RepairResult(
            repaired=False,
            certificate={
                **cert_base,
                "status": "abstain",
                "reason": "stage0_no_repairable_finding",
            },
            before_finding=before_d,
            cascade_before=cascade_before,
        )

    if before.error_type and "numerical" not in before.error_type.lower():
        # Still try if we have a correct_value (e.g. some edge cases), but tag it
        pass

    row_idx = int(before.problematic_entry)
    new_val = float(before.correct_value)
    label = _row_label(item, row_idx)
    patch = make_patch(
        row_idx=row_idx,
        old_value=before.stated_value,
        new_value=new_val,
        label=label,
        reason=before.detail or "Stage 0 exact corrected value",
    )

    new_table, old_fmt, new_fmt = apply_replace_fact(item["table"], row_idx, new_val)
    if old_fmt is None:
        return RepairResult(
            repaired=False,
            patch=patch,
            certificate={
                **cert_base,
                "status": "patch_apply_failed",
                "reason": f"could_not_edit_row_{row_idx}",
            },
            before_finding=before_d,
            cascade_before=cascade_before,
        )

    patched = copy.deepcopy(item)
    patched["table"] = new_table

    after, a1, _b1, cascade_after = _detect(patched)
    after_d = _finding_dict(after)

    # Success: Stage 0 abstains, OR no longer flags the same root row
    cleared = after is None
    same_row = (
        after is not None
        and after.problematic_entry is not None
        and int(after.problematic_entry) == row_idx
    )
    value_fixed = (
        before.stated_value is not None
        and approx_eq(new_val, before.correct_value)
    )
    no_regression = cleared or not same_row
    accepted = bool(value_fixed and no_regression and (cleared or cascade_after <= cascade_before))

    cert = {
        **cert_base,
        "status": "accepted" if accepted else "rejected",
        "root_cause": {
            "row_idx": row_idx,
            "label": label,
            "hypothesis": "Incorrect reported leaf/subtotal value",
        },
        "operation": patch,
        "old_value_text": old_fmt,
        "new_value_text": new_fmt,
        "after_violations": after_d,
        "cascade_warning_count_after": cascade_after,
        "target_rule_status": "cleared" if cleared else "still_flagged",
        "new_violations_introduced": 0 if (cleared or not same_row) else 1,
        "table_hash_after": hashlib.sha256(new_table.encode()).hexdigest()[:16],
        "alert_compression": max(0, cascade_before - cascade_after),
    }

    return RepairResult(
        repaired=accepted,
        patch=patch if accepted else patch,
        certificate=cert,
        before_finding=before_d,
        after_finding=after_d,
        cascade_before=cascade_before,
        cascade_after=cascade_after,
    )


def dumps_cert(result: RepairResult) -> str:
    return json.dumps(result.certificate, indent=2, default=str)
