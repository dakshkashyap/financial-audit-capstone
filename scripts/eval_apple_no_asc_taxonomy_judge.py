#!/usr/bin/env python3
"""
Apple scrubbed pack (no Standards Citation) → Stage 0/1 + taxonomy LLM-as-judge.

Does NOT score citations against AuditBench's LLM-written Standards Citation.
Instead:
  1) Deterministic: predicted ASC must be in FASB US-GAAP taxonomy candidates.
  2) Ollama LLM judge: given error context + official candidate list, is the
     pick appropriate? (may only choose from the candidate list)

Usage:
  export AUDITBENCH_DATA=$PWD/data/apple_no_asc_hints
  export AUDIT_RESULTS_DIR=$PWD/results/apple_no_asc_pipeline_judge
  .venv/bin/python scripts/eval_apple_no_asc_taxonomy_judge.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("AUDITBENCH_DATA", str(ROOT / "data" / "apple_no_asc_hints"))
os.environ.setdefault("AUDIT_RESULTS_DIR", str(ROOT / "results" / "apple_no_asc_pipeline_judge"))

from approaches.citation_mcp_agent.tools import TaxonomyTools  # noqa: E402
from approaches.full_pipeline.pipeline import run_pipeline  # noqa: E402
from approaches.stage1_taxonomy_citation.stage1_arelle import run_stage1  # noqa: E402
from core.parser import load_correct, load_single_error, parse_table  # noqa: E402
from core.paths import RESULTS_DIR  # noqa: E402
from core.taxonomy_graph import TaxonomyGraph  # noqa: E402

OLLAMA_MODEL = os.environ.get("OLLAMA_JUDGE_MODEL", "mistral")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")


def _bare(concept: Optional[str]) -> str:
    if not concept:
        return ""
    return concept.split(":")[-1]


def _row_label(item: dict, row_idx: int) -> Optional[str]:
    rows = parse_table(item["table"])
    r = rows.get(row_idx)
    return r["label"] if r else None


def _focus_row(s1, row_idx: int):
    return next((r for r in s1.statement.rows if r.row_idx == row_idx), None)


def _ollama_judge(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ask local Ollama to judge citation quality vs taxonomy candidates only."""
    prompt = f"""You are an accounting citation judge.
You MUST only use the official FASB US-GAAP taxonomy candidate list provided.
Do NOT invent ASC codes. Do NOT use any outside answer key.

Error type: {payload['error_type']}
Broken row index: {payload['row_idx']}
Row label: {payload['label']}
Mapped US-GAAP concept: {payload['concept']}
Error resolution summary: {payload['error_resolution'][:500]}

Official taxonomy ASC candidates for this concept:
{json.dumps(payload['candidates'], indent=2)}

Pipeline predicted citation: {payload['predicted_asc']}
Taxonomy validate_citation says valid={payload['taxonomy_valid']}

Decide:
1) grounded: true only if predicted_asc is in the candidate list (or a clear prefix of one).
2) appropriate: true if, among the candidates, this is a reasonable ASC for this error
   (subject-matter topics preferred for numerical/value errors; presentation topics
   205/210/220/230 ok for misclassification/placement when present in candidates).
3) better_candidate: if appropriate is false but a better candidate exists, give that ASC,
   else null.
4) reason: one short sentence.

Reply with ONLY JSON:
{{"grounded": true/false, "appropriate": true/false, "better_candidate": "..." or null, "reason": "..."}}
"""
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read().decode())
    text = raw.get("response", "") or ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        return {
            "grounded": None,
            "appropriate": None,
            "better_candidate": None,
            "reason": f"unparseable_judge_response: {text[:200]}",
            "raw": text,
        }


def main() -> None:
    out_dir = Path(RESULTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = TaxonomyGraph()
    _ = graph.available
    tools = TaxonomyTools(graph)

    items = load_single_error(seed=42, n=20)
    clean = load_correct(seed=42, n=20)

    records: List[Dict[str, Any]] = []
    stage0_fire = 0
    stage0_type_ok = 0
    stage0_row_ok = 0
    clean_fp = 0

    for item in clean:
        rec = run_pipeline(item, graph)
        if not rec.abstained:
            clean_fp += 1

    cite_n = 0
    taxonomy_valid_n = 0
    judge_grounded_n = 0
    judge_appropriate_n = 0
    judge_ran = 0
    fake_accepted = 0

    for i, item in enumerate(items):
        gt = item["errors"][0]
        gt_type = gt["error_type"]
        gt_row = int(gt["problematic_entry"])
        resolution = gt.get("error_resolution") or ""

        pipe = run_pipeline(item, graph)
        s1 = run_stage1(item, graph)
        focus = _focus_row(s1, gt_row)

        concept = _bare(focus.concept) if focus else None
        label = (focus.label if focus else None) or _row_label(item, gt_row)
        predicted = focus.asc_primary if focus else None
        source = s1.citation_sources.get(gt_row) if focus else None

        cand_payload = tools.get_candidates(concept) if concept else {"candidates": [], "n": 0}
        candidates = [
            c["asc"] if isinstance(c, dict) else str(c)
            for c in cand_payload.get("candidates", [])
        ]
        # Also keep rich candidate objects when available
        rich_cands = cand_payload.get("candidates", [])

        taxonomy_valid = False
        if concept and predicted:
            v = tools.validate_citation(concept, predicted)
            taxonomy_valid = bool(v.get("valid"))
        if concept:
            fake = tools.validate_citation(concept, "999-99-99-9")
            if fake.get("valid"):
                fake_accepted += 1

        fired = not pipe.abstained
        if fired:
            stage0_fire += 1
            if (pipe.error_type or "").lower() == gt_type.lower():
                stage0_type_ok += 1
            if pipe.problematic_entry == gt_row:
                stage0_row_ok += 1

        row_rec: Dict[str, Any] = {
            "index": i,
            "stage0": {
                "fired": fired,
                "pred_type": pipe.error_type,
                "pred_row": pipe.problematic_entry,
                "gt_type": gt_type,
                "gt_row": gt_row,
                "type_match": fired and (pipe.error_type or "").lower() == gt_type.lower(),
                "row_match": fired and pipe.problematic_entry == gt_row,
                "detail": pipe.detail,
            },
            "stage1": {
                "label": label,
                "concept": concept,
                "predicted_asc": predicted,
                "citation_source": source,
                "candidates": candidates,
                "n_candidates": len(candidates),
                "taxonomy_valid": taxonomy_valid,
                "fake_999_accepted": False,
            },
            "llm_judge": None,
            "note": "Citation judged vs taxonomy graph only; AuditBench Standards Citation not used.",
        }

        if predicted and candidates:
            cite_n += 1
            if taxonomy_valid:
                taxonomy_valid_n += 1
            try:
                judge = _ollama_judge({
                    "error_type": gt_type,
                    "row_idx": gt_row,
                    "label": label,
                    "concept": concept,
                    "error_resolution": resolution,
                    "candidates": rich_cands or candidates,
                    "predicted_asc": predicted,
                    "taxonomy_valid": taxonomy_valid,
                })
                row_rec["llm_judge"] = judge
                judge_ran += 1
                if judge.get("grounded") is True:
                    judge_grounded_n += 1
                if judge.get("appropriate") is True:
                    judge_appropriate_n += 1
            except Exception as exc:
                row_rec["llm_judge"] = {"error": str(exc)}

        records.append(row_rec)

    n = len(items)
    summary = {
        "dataset": "data/apple_no_asc_hints",
        "asc_hints_in_input": 0,
        "citation_gt_source": "US-GAAP taxonomy graph + Ollama LLM judge (NOT AuditBench Standards Citation)",
        "judge_model": OLLAMA_MODEL,
        "stage0": {
            "n_single_error": n,
            "fire_rate": stage0_fire / n,
            "type_acc_when_fired": stage0_type_ok / stage0_fire if stage0_fire else None,
            "row_acc_when_fired": stage0_row_ok / stage0_fire if stage0_fire else None,
            "clean_false_positives": f"{clean_fp}/{len(clean)}",
        },
        "stage1_and_judge": {
            "items_with_predicted_asc_and_candidates": cite_n,
            "taxonomy_validate_pass": f"{taxonomy_valid_n}/{cite_n}" if cite_n else "0/0",
            "taxonomy_validate_pct": taxonomy_valid_n / cite_n if cite_n else None,
            "fake_999_accepted": fake_accepted,
            "llm_judge_ran": judge_ran,
            "llm_judge_grounded": f"{judge_grounded_n}/{judge_ran}" if judge_ran else "0/0",
            "llm_judge_appropriate": f"{judge_appropriate_n}/{judge_ran}" if judge_ran else "0/0",
            "llm_judge_grounded_pct": judge_grounded_n / judge_ran if judge_ran else None,
            "llm_judge_appropriate_pct": judge_appropriate_n / judge_ran if judge_ran else None,
        },
    }

    out = {"summary": summary, "records": records}
    out_path = out_dir / "taxonomy_llm_judge.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
