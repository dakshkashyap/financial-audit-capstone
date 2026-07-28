"""
eval_finmr.py — smoke / baseline eval of a modern LLM on FinMR (FinAuditing).

FinMR asks for BOTH:
  extracted_value  — what the filing reports
  calculated_value — what the calculation/taxonomy relationships imply
A prediction is correct only when BOTH match (AuditFlow "Joint ACC").

IMPORTANT cost note
-------------------
Each FinMR query is 17k–167k characters of XBRL context stuffed into one prompt.
A full 332-item Claude run is expensive. Defaults:
  --n 10          (reproducible smoke)
  --dqc DQC_US_0015  (sign-consistency; often the easiest family)

AuditFlow's own protocol is smarter: they use FinMR *metadata* (ticker, concept,
period, GT) but re-download raw XBRL from SEC and verify with tools — they do
NOT dump the entire FinMR query into the LLM. This script is the *naive*
baseline (paper-style single prompt) so we can measure how far that gets us
before building the tool-using agent.

Usage:
  $env:ANTHROPIC_API_KEY="sk-ant-..."
  python eval_finmr.py --n 10 --model claude-sonnet-4-6
  python eval_finmr.py --n 10 --dqc DQC_US_0015
  python eval_finmr.py --manual-only          # no API: dump GT + query heads for review
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, Optional

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(errors="replace")

from finmr_loader import load_finmr, values_equal

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "results")
os.makedirs(OUT_DIR, exist_ok=True)

SYSTEM = (
    "You are an auditor for XBRL filings. Extract the reported value of the "
    "target financial element and compute the value implied by the calculation "
    "/ taxonomy relationships in the provided filing context.\n"
    "Respond with ONLY a JSON object:\n"
    '{"extracted_value": "<number as string>", "calculated_value": "<number as string>"}\n'
    "No markdown fences, no commentary."
)


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    m = re.search(r"\{[^{}]*extracted_value[^{}]*\}", text, re.DOTALL)
    if not m:
        m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def call_claude(query: str, model: str) -> Dict:
    """Naive single-prompt call. Truncates the query if needed to stay under a
    practical context budget (keep head + tail — DQC rule + answer schema live
    near the head; instance facts often near the end)."""
    import anthropic

    # Keep ~120k chars ≈ ~30–40k tokens of context; FinMR queries can be 167k.
    MAX = 120_000
    if len(query) > MAX:
        head, tail = query[:80_000], query[-40_000:]
        query = head + "\n\n[... middle of filing truncated for context budget ...]\n\n" + tail

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=512,
        temperature=0,
        system=SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    raw = ""
    for block in msg.content:
        if hasattr(block, "text"):
            raw += block.text
    parsed = _extract_json(raw)
    return {"raw_text": raw, "parsed": parsed,
            "usage": {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}}


def score_one(pred: Optional[dict], gt: dict) -> dict:
    if not pred:
        return {"extracted_ok": False, "calculated_ok": False, "joint_ok": False}
    e_ok = values_equal(pred.get("extracted_value"), gt.get("extracted_value"))
    c_ok = values_equal(pred.get("calculated_value"), gt.get("calculated_value"))
    return {"extracted_ok": e_ok, "calculated_ok": c_ok, "joint_ok": e_ok and c_ok}


def manual_audit(items) -> None:
    """Write a human-readable review sheet (no API)."""
    path = os.path.join(OUT_DIR, "finmr_manual_review.md")
    lines = [
        "# FinMR manual review sheet",
        "",
        "Use this to spot-check GT labels and failure patterns before/after an LLM run.",
        "",
    ]
    for it in items:
        gt = it["gt"]
        # Heuristic: sign-flip cases (0015) are recognizable
        pattern = "unknown"
        ev, cv = gt.get("extracted_value"), gt.get("calculated_value")
        if ev and cv:
            try:
                from finmr_loader import _to_float
                fe, fc = _to_float(ev), _to_float(cv)
                if fe is not None and fc is not None and abs(fe + fc) < 1e-9 and fe != 0:
                    pattern = "sign_flip (extracted ≈ −calculated)"
                elif fe is not None and fc is not None and fe != fc:
                    pattern = "value_mismatch (calc tree / aggregation)"
                elif fe == fc:
                    pattern = "values_equal (possible clean / control?)"
            except Exception:
                pass
        lines += [
            f"## id={it['id']} · {it['dqc_id']}",
            f"- GT extracted: `{ev}`",
            f"- GT calculated: `{cv}`",
            f"- Pattern hint: **{pattern}**",
            f"- Query length: {len(it['query']):,} chars",
            f"- Query head:",
            "```",
            it["query"][:500].replace("```", "`'`"),
            "```",
            "",
        ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dqc", default=None,
                    help="DQC_US_0015 | DQC_US_0117 | DQC_US_0126")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--manual-only", action="store_true",
                    help="No API calls — write a review sheet only.")
    args = ap.parse_args()

    items = load_finmr(dqc=args.dqc, n=args.n, seed=args.seed)
    print(f"FinMR sample: n={len(items)} dqc={args.dqc or 'all'} seed={args.seed}")

    if args.manual_only:
        manual_audit(items)
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — writing manual review sheet instead.")
        print("Set the key and re-run to get Joint ACC numbers.")
        manual_audit(items)
        return

    records, n_joint, n_ext, n_calc, n_parse = [], 0, 0, 0, 0
    for it in items:
        print(f"  id={it['id']} {it['dqc_id']} query={len(it['query']):,} chars …", flush=True)
        try:
            r = call_claude(it["query"], args.model)
        except Exception as e:
            r = {"raw_text": "", "parsed": None, "error": str(e), "usage": {}}
        sc = score_one(r.get("parsed"), it["gt"])
        n_joint += int(sc["joint_ok"])
        n_ext += int(sc["extracted_ok"])
        n_calc += int(sc["calculated_ok"])
        n_parse += int(r.get("parsed") is not None)
        rec = {
            "id": it["id"], "dqc_id": it["dqc_id"], "gt": it["gt"],
            "pred": r.get("parsed"), "score": sc,
            "usage": r.get("usage"), "error": r.get("error"),
            "raw_text_head": (r.get("raw_text") or "")[:400],
        }
        records.append(rec)
        print(f"    joint={sc['joint_ok']}  pred={r.get('parsed')}  gt={it['gt']}")

    summary = {
        "model": args.model, "n": len(items), "dqc": args.dqc, "seed": args.seed,
        "parse_rate": n_parse / max(len(items), 1),
        "extracted_acc": n_ext / max(len(items), 1),
        "calculated_acc": n_calc / max(len(items), 1),
        "joint_acc": n_joint / max(len(items), 1),
        "auditflow_paper_joint_acc_reference": 0.8209,
        "auditflow_llm_only_ablation_reference": 0.1791,
    }
    out = os.path.join(OUT_DIR, f"finmr_{args.model.replace('/', '_')}_n{len(items)}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "records": records}, f, indent=2)
    print("\n-- summary --")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"wrote {out}")
    manual_audit(items)


if __name__ == "__main__":
    main()
