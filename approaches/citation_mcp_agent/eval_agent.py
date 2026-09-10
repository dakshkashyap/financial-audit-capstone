"""
A vs C citation evaluation.

  A — graph single pick (TaxonomyGraph.get_fasb_citation_detail)
  C — iterative citation agent (heuristic / llm / oracle)

Usage
-----
  python -m citation_mcp.eval_agent                  # heuristic, n=50
  python -m citation_mcp.eval_agent --n 150
  python -m citation_mcp.eval_agent --mode llm --model claude/claude-3-5-haiku --n 20
  python -m citation_mcp.eval_agent --mode oracle --n 50   # candidate ceiling
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import List, Optional

from core.paths import REPO_ROOT as _ROOT
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.parser import load_single_error, load_multi_error
from approaches.stage1_taxonomy_citation.stage1_arelle import run_stage1
from core.taxonomy_graph import TaxonomyGraph
from approaches.citation_mcp_agent.tools import TaxonomyTools
from approaches.citation_mcp_agent.agent import CitationAgent

from core.paths import RESULTS_DIR
PAPER_BASELINE = 0.262

_GT_ASC_RE = re.compile(r"ASC[^\d]{0,8}(\d{3})")


def extract_gt_topic(text: str) -> Optional[str]:
    m = _GT_ASC_RE.search(text or "")
    return m.group(1) if m else None


def extract_pred_topic(asc: Optional[str]) -> Optional[str]:
    if not asc:
        return None
    m = re.match(r"^(\d{3})", asc.replace("FASB ASC ", "").strip())
    return m.group(1) if m else None


def _broken_row_context(item: dict, graph: TaxonomyGraph):
    """Return (concept, label, statement_type, gt_topic, gt_et, gt_row) for first usable error."""
    result = run_stage1(item, graph)
    stmt_type = getattr(result.statement, "statement_type", "") or item.get("statement_type", "")

    for err in item["errors"]:
        gt_topic = extract_gt_topic(err.get("standards_citation", ""))
        if not gt_topic:
            continue
        gt_row = err.get("problematic_entry")
        try:
            gt_row = int(re.search(r"\d+", str(gt_row)).group())
        except (AttributeError, TypeError, ValueError):
            continue
        row = next((r for r in result.statement.rows if r.row_idx == gt_row), None)
        if row is None:
            continue
        concept = (row.concept or "").replace("us-gaap:", "")
        return {
            "concept": concept,
            "label": row.label or "",
            "statement_type": stmt_type,
            "gt_topic": gt_topic,
            "gt_et": err.get("error_type", "?"),
            "gt_row": gt_row,
            "baseline_asc": row.asc_primary,
            "baseline_topic": extract_pred_topic(row.asc_primary),
        }
    return None


def run_eval(
    items: List[dict],
    mode: str = "heuristic",
    model: str = "claude/claude-haiku-4-5",
    max_iterations: int = 3,
) -> dict:
    graph = TaxonomyGraph()
    tools = TaxonomyTools(graph)
    agent = CitationAgent(
        tools=tools, mode=mode, max_iterations=max_iterations, model=model
    )

    records = []
    for idx, item in enumerate(items):
        ctx = _broken_row_context(item, graph)
        if ctx is None:
            continue
        if not ctx["concept"]:
            records.append({
                **ctx,
                "a_hit": False,
                "c_hit": False,
                "c_citation": None,
                "c_topic": None,
                "validated": False,
                "hallucinated_attempts": 0,
                "iterations": 0,
                "recall": False,
                "improved": False,
                "regressed": False,
                "mode": mode,
                "rationale": "no_concept",
            })
            continue

        # Candidate recall (ceiling)
        cand_topics = {
            c["topic"] for c in graph.get_candidate_citations(ctx["concept"]) if c.get("topic")
        }
        recall = ctx["gt_topic"] in cand_topics

        a_hit = bool(ctx["baseline_topic"]) and ctx["baseline_topic"] == ctx["gt_topic"]

        res = agent.cite(
            ctx["concept"],
            item_id=f"item_{idx}",
            label=ctx["label"],
            statement_type=ctx["statement_type"],
            error_type=ctx["gt_et"],
            gt_topic=ctx["gt_topic"],
        )
        c_topic = res.topic
        c_hit = bool(c_topic) and c_topic == ctx["gt_topic"]

        records.append({
            **ctx,
            "a_hit": a_hit,
            "c_hit": c_hit,
            "c_citation": res.citation,
            "c_topic": c_topic,
            "validated": res.validated,
            "hallucinated_attempts": res.hallucinated_attempts,
            "iterations": res.iterations,
            "recall": recall,
            "mode": res.mode,
            "rationale": res.rationale,
            "improved": c_hit and not a_hit,
            "regressed": a_hit and not c_hit,
        })

    n = len(records)
    a_hits = sum(r["a_hit"] for r in records)
    c_hits = sum(r["c_hit"] for r in records)
    recall_n = sum(r["recall"] for r in records)
    with_pick = [r for r in records if r.get("c_citation")]
    validated_n = sum(r["validated"] for r in with_pick)
    # Accepted citations that were NOT validated = grounding failure (should be 0)
    ungrounded = sum(1 for r in with_pick if not r["validated"])
    hallu = sum(r["hallucinated_attempts"] for r in records)
    improved = sum(r["improved"] for r in records)
    regressed = sum(r["regressed"] for r in records)
    attempted = [r for r in records if r.get("concept")]
    avg_iter = (
        sum(r["iterations"] for r in attempted) / len(attempted) if attempted else 0.0
    )

    wins = [r for r in records if r["improved"]][:8]
    samples = []
    for r in wins:
        samples.append({
            "label": r["label"][:60],
            "concept": r["concept"],
            "gt_topic": r["gt_topic"],
            "a_topic": r["baseline_topic"],
            "c_topic": r["c_topic"],
            "c_citation": r["c_citation"],
            "rationale": r.get("rationale", ""),
        })

    return {
        "mode": mode,
        "model": model if mode == "llm" else None,
        "n_records": n,
        "A_graph_single_pick": {
            "topic_em": round(a_hits / n, 4) if n else 0.0,
            "hits": a_hits,
        },
        "C_citation_agent": {
            "topic_em": round(c_hits / n, 4) if n else 0.0,
            "hits": c_hits,
            "n_with_citation": len(with_pick),
            "grounded_accept_rate": (
                round(validated_n / len(with_pick), 4) if with_pick else 1.0
            ),
            "ungrounded_accepts": ungrounded,
            "hallucinated_attempts_total": hallu,
            "avg_iterations": round(avg_iter, 3),
            "improved_vs_A": improved,
            "regressed_vs_A": regressed,
        },
        "candidate_recall_ceiling": {
            "topic_em": round(recall_n / n, 4) if n else 0.0,
            "hits": recall_n,
        },
        "paper_baseline_gpt4": PAPER_BASELINE,
        "delta_C_minus_A": round((c_hits - a_hits) / n, 4) if n else 0.0,
        "sample_improvements": samples,
    }


def _print(summary: dict) -> None:
    a = summary["A_graph_single_pick"]
    c = summary["C_citation_agent"]
    ceil = summary["candidate_recall_ceiling"]
    print()
    print("=" * 64)
    print("  Citation MCP Agent — A vs C")
    print("=" * 64)
    print(f"  mode={summary['mode']}  n={summary['n_records']}")
    print()
    print(f"  A  graph single pick     topic EM = {a['topic_em']:.1%}  ({a['hits']}/{summary['n_records']})")
    print(f"  C  citation agent        topic EM = {c['topic_em']:.1%}  ({c['hits']}/{summary['n_records']})")
    print(f"     candidate ceiling                 {ceil['topic_em']:.1%}  ({ceil['hits']}/{summary['n_records']})")
    print(f"     GPT-4 paper baseline              {summary['paper_baseline_gpt4']:.1%}")
    print()
    print(f"  Δ (C − A)                {summary['delta_C_minus_A']:+.1%}")
    print(f"  grounded accept rate     {c['grounded_accept_rate']:.1%}   "
          f"({c['n_with_citation']} picks, ungrounded={c['ungrounded_accepts']})")
    print(f"  hallucinated attempts    {c['hallucinated_attempts_total']}   (rejected by validate_citation)")
    print(f"  avg iterations           {c['avg_iterations']}")
    print(f"  improved / regressed     {c['improved_vs_A']} / {c['regressed_vs_A']}")
    if summary["sample_improvements"]:
        print()
        print("  Sample improvements (A wrong → C correct):")
        for s in summary["sample_improvements"][:5]:
            print(f"    • {s['label']}")
            print(f"      {s['concept']}: A={s['a_topic']} → C={s['c_topic']}  (GT={s['gt_topic']})")
    print("=" * 64)
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Citation MCP agent A vs C eval")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--split", default="single_error", choices=["single_error", "multi_error"])
    ap.add_argument("--mode", default="heuristic", choices=["heuristic", "llm", "oracle"])
    ap.add_argument("--model", default="claude/claude-haiku-4-5")
    ap.add_argument("--max-iterations", type=int, default=3)
    ap.add_argument("--out", default=None, help="Write JSON to results/")
    args = ap.parse_args()

    loader = load_single_error if args.split == "single_error" else load_multi_error
    items = loader(seed=args.seed, n=args.n)
    print(f"Loaded {len(items)} {args.split} items (seed={args.seed})")

    summary = run_eval(
        items, mode=args.mode, model=args.model, max_iterations=args.max_iterations
    )
    _print(summary)

    out = args.out or os.path.join(RESULTS_DIR, f"citation_mcp_{args.mode}_{args.n}.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
