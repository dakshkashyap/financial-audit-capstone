"""Run every approach and report which ones actually work.

Executes a small smoke run per approach, records whether it completed, how long
it took, and the headline number it produced. Scratch output goes to a temp
directory so the committed full-run evidence in results/ is never overwritten.

    python scripts/status.py              # quick pass, prints a table
    python scripts/status.py --full       # full n, the real numbers
    python scripts/status.py --write      # also refresh STATUS.md
    python scripts/status.py --only audit_patch_repair
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK = "PASS"
BROKE = "FAIL"
SKIP = "SKIP"


def has_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def finmr_present() -> bool:
    d = os.path.join(REPO, "data", "finmr")
    return os.path.isdir(d) and any(
        f.endswith((".jsonl", ".parquet")) for f in os.listdir(d)
    )


# ---------------------------------------------------------------- metric readers
# Each returns a short human-readable headline, or None if it cannot be read.

def m_stage0(d):
    s = d["splits"]
    return (f"false alarms {s['correct']['false_positive_rate']:.1%} · "
            f"type EM when fired {s['single_error']['error_type_em_fired']:.1%}")


def m_mapper(d):
    sp = next(iter(d["splits"].values()))
    mapped = sp.get("mapped_rows") or sp.get("total_mapped_rows")
    total = sp.get("total_valued_rows")
    if mapped and total:
        return f"row coverage {mapped / total:.1%} ({mapped}/{total})"
    return f"{total} valued rows scored"


def m_stage1(d):
    sp = next(iter(d["splits"].values()))
    tot, unmapped = sp.get("total_valued_rows"), sp.get("unmapped_rows")
    tax = "taxonomy loaded" if d.get("taxonomy_available") else "NO TAXONOMY"
    if tot and unmapped is not None:
        return f"{tax} · rows resolved {(tot - unmapped) / tot:.1%} ({tot - unmapped}/{tot})"
    return tax


def m_citation(d):
    a = d["A_graph_single_pick"]["topic_em"]
    c = d["C_citation_agent"]
    return (f"lookup {a:.1%} · agent {c['topic_em']:.1%} · "
            f"invented citations {c['hallucinated_attempts_total']}")


def m_patch_v0(d):
    s = d["summary"]
    return (f"gate fires {s['stage0_fire_rate']:.1%} · "
            f"patches accepted {s['accept_rate_among_repairable']:.0%}")


def m_patch_finmr(d):
    s = d["summary"]
    return (f"exact repair {s['exact_patch_match_pct_of_patched']:.1f}% · "
            f"regressions {100 - s['no_regression_pct_of_patched']:.0f}%")


def m_finmr_eval(d):
    return f"joint ACC {d['ACC(%)']:.1f}% over {d['total']} items"


def m_ablation(d):
    c = d["splits"]["correct"]
    se = d["splits"]["single_error"]
    out = f"clean-split gate {c['config_B_gen_judgment_em']:.0%}"
    if c.get("have_llm"):
        out += f" · false alarms {c['fp_rate_llm']:.0%}→{c['fp_rate_veto']:.0%}"
    out += f" · type EM {se['gate_localization_type_em_among_fired']:.0%}"
    return out


# ---------------------------------------------------------------- the checks
# name, module, quick args, full args, output file, metric reader, requirement
CHECKS = [
    # Always scores with BERTScore, which loads roberta-large (~8 min cold).
    ("baseline_auditbench", "approaches.baseline_auditbench.main",
     ["--dry-run", "--n", "5"], ["--dry-run", "--n", "20"],
     None, None, "slow"),

    ("stage0_deterministic_gate", "approaches.stage0_deterministic_gate.stage0_eval",
     ["--n", "20"], ["--n", "150"],
     "stage0_eval.json", m_stage0, None),

    ("stage1_concept_mapping", "approaches.stage1_concept_mapping.edgar_mapper_eval",
     ["--n", "20"], ["--n", "150"],
     "edgar_mapper_eval.json", m_mapper, None),

    ("stage1_taxonomy_citation", "approaches.stage1_taxonomy_citation.stage1_eval",
     ["--n", "20"], ["--n", "150"],
     "stage1_eval.json", m_stage1, None),

    # Library module with no standalone CLI; reached through full_pipeline.
    ("stage2_llm_audit", "approaches.stage2_llm_audit.stage2_llm",
     [], [], None, None, "importonly"),

    ("citation_mcp_agent", "approaches.citation_mcp_agent.eval_agent",
     ["--n", "20"], ["--n", "50"],
     None, m_citation, None),

    ("audit_patch_repair (AuditBench)", "approaches.audit_patch_repair.run_v0",
     ["--n", "20"], ["--n", "80"],
     None, m_patch_v0, None),

    ("audit_patch_repair (FinMR)", "approaches.audit_patch_repair.run_finmr",
     ["--n", "20"], ["--n", "332"],
     None, m_patch_finmr, "finmr"),

    ("finmr_benchmark", "approaches.finmr_benchmark.finmr_eval",
     ["--n", "20"], ["--n", "332"],
     "finmr_eval.json", m_finmr_eval, "finmr"),

    ("full_pipeline", "approaches.full_pipeline.pipeline_eval",
     ["--n", "20"], ["--n", "150"],
     "pipeline_ablation.json", m_ablation, None),
]


def newest_json(d: str) -> str | None:
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")]
    return max(files, key=os.path.getmtime) if files else None


def run_check(name, module, args, out_name, reader, needs, scratch, timeout, full):
    if needs == "apikey" and not has_key():
        return SKIP, 0.0, "needs ANTHROPIC_API_KEY or OPENAI_API_KEY", ""
    if needs == "finmr" and not finmr_present():
        return SKIP, 0.0, "needs data/finmr — run download_finmr", ""
    if needs == "slow" and not full:
        return SKIP, 0.0, "slow (BERTScore model load) — use --full", ""
    if needs == "importonly":
        t0 = time.time()
        p = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=REPO,
                           capture_output=True, text=True, timeout=timeout)
        dt = time.time() - t0
        if p.returncode != 0:
            tail = (p.stderr or "").strip().splitlines()
            return BROKE, dt, tail[-1][:90] if tail else "import failed", p.stderr
        key = "API key present" if has_key() else "no API key set"
        return OK, dt, f"imports clean; no standalone CLI ({key})", ""

    run_dir = os.path.join(scratch, name.split()[0])
    os.makedirs(run_dir, exist_ok=True)
    env = {**os.environ, "AUDIT_RESULTS_DIR": run_dir, "PYTHONWARNINGS": "ignore"}

    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-m", module, *args], cwd=REPO, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return BROKE, time.time() - t0, f"timed out after {timeout}s", ""
    dt = time.time() - t0

    if p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()
        return BROKE, dt, tail[-1][:90] if tail else f"exit {p.returncode}", p.stderr

    headline = "ran clean (no metric file)"
    if reader:
        path = os.path.join(run_dir, out_name) if out_name else newest_json(run_dir)
        if path and os.path.exists(path):
            try:
                headline = reader(json.load(open(path)))
            except Exception as e:
                headline = f"ran, but metric unreadable ({type(e).__name__})"
        else:
            headline = "ran, but wrote no results file"
    return OK, dt, headline, ""


def main():
    ap = argparse.ArgumentParser(description="Report which approaches actually work.")
    ap.add_argument("--full", action="store_true", help="use full n instead of a quick sample")
    ap.add_argument("--write", action="store_true", help="refresh STATUS.md")
    ap.add_argument("--only", help="substring match on approach name")
    ap.add_argument("--timeout", type=int, default=900)
    a = ap.parse_args()

    checks = [c for c in CHECKS if not a.only or a.only in c[0]]
    scratch = tempfile.mkdtemp(prefix="audit-status-")
    mode = "full" if a.full else "quick"

    print(f"\nRunning {len(checks)} approach checks ({mode} mode)")
    print(f"scratch results → {scratch}\n")

    rows, verbose = [], []
    for name, module, qargs, fargs, out_name, reader, needs in checks:
        print(f"  {name:34s} … ", end="", flush=True)
        args = fargs if a.full else qargs
        status, dt, headline, err = run_check(
            name, module, args, out_name, reader, needs, scratch, a.timeout, a.full)
        print(f"{status}  {dt:5.1f}s  {headline}")
        rows.append((name, status, dt, headline))
        if err:
            verbose.append((name, err))

    n_ok = sum(1 for r in rows if r[1] == OK)
    n_bad = sum(1 for r in rows if r[1] == BROKE)
    n_skip = sum(1 for r in rows if r[1] == SKIP)
    print(f"\n  {n_ok} passing · {n_bad} failing · {n_skip} skipped\n")

    for name, err in verbose:
        print(f"--- {name} stderr tail ---")
        print("\n".join(err.strip().splitlines()[-12:]))
        print()

    if a.write:
        write_status_md(rows, mode)
        print(f"Wrote {os.path.join(REPO, 'STATUS.md')}")

    shutil.rmtree(scratch, ignore_errors=True)
    return 1 if n_bad else 0


BADGE = {OK: "working", BROKE: "**broken**", SKIP: "not run"}


def write_status_md(rows, mode):
    from datetime import date
    lines = [
        "# Approach status",
        "",
        "Generated by `python scripts/status.py --write`. Every row below was",
        f"produced by actually running the approach ({mode} mode), not by hand.",
        "",
        f"Last run: **{date.today().isoformat()}**",
        "",
    ]
    if mode == "quick":
        lines += [
            "> **These are small-sample numbers (n=20), not our reported results.**",
            "> Quick mode exists to answer *does it still run*. On a sample this small",
            "> the figures swing well above and below the real ones — quote",
            "> [MATURITY.md](MATURITY.md) or `docs/results/` instead, and run",
            "> `--full` if you need these cells to be citable.",
            "",
        ]
    lines += [
        "| Approach | Status | Time | Headline number |",
        "|---|---|---|---|",
    ]
    for name, status, dt, headline in rows:
        lines.append(f"| `{name}` | {BADGE[status]} | {dt:.1f}s | {headline} |")
    lines += [
        "",
        "`not run` means the check needs something absent from this machine — an",
        "API key, or the FinMR download — not that the approach is broken.",
        "",
        "Re-run it yourself:",
        "",
        "```bash",
        "python scripts/status.py            # quick",
        "python scripts/status.py --full     # the real numbers",
        "```",
        "",
        "See [MATURITY.md](MATURITY.md) for the judgement call on how far each",
        "approach can be trusted, which a script cannot measure.",
    ]
    open(os.path.join(REPO, "STATUS.md"), "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
