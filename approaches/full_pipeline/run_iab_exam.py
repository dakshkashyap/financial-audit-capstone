#!/usr/bin/env python3
"""
Take the IntelliAudit-Bench exam with this repo's Stage 0 → 1 (optional Stage 2).

Run FROM the capstone root. The benchmark (exam + key + scorer) is loaded from
the IntelliAudit repo — it is not copied in.

Never parses sample_id for a rule. Answer key is opened only after predictions.

  cd /Users/admin/Desktop/financial-audit-capstone
  python3 -m approaches.full_pipeline.run_iab_exam
  python3 -m approaches.full_pipeline.run_iab_exam --full
  python3 -m approaches.full_pipeline.run_iab_exam --clean
  python3 -m approaches.full_pipeline.run_iab_exam --stage2

  python3 -m approaches.full_pipeline.run_iab_exam --bench /Users/admin/IntelliAudit-1
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

CAP = Path(__file__).resolve().parents[2]
if str(CAP) not in sys.path:
    sys.path.insert(0, str(CAP))

# Stage 2 imports intelliaudit_runner, which needs tqdm at import time.
try:
    import tqdm  # noqa: F401
except ImportError:
    import types
    _tqdm = types.ModuleType("tqdm")

    def _passthrough(it, *args, **kwargs):
        return it

    _tqdm.tqdm = _passthrough
    sys.modules["tqdm"] = _tqdm

BENCH_DEFAULT = Path(os.environ.get("INTELLIAUDIT_ROOT", "/Users/admin/IntelliAudit-1"))
SHEET = {
    "BalanceSheet": "balance sheet",
    "IncomeStatement": "income statement",
    "CashFlow": "cash flow",
}


class T:
    def __init__(self, color: bool):
        self.color = color and sys.stdout.isatty()

    def c(self, code, s):
        return f"\033[{code}m{s}\033[0m" if self.color else s

    def bold(self, s): return self.c("1", s)
    def dim(self, s): return self.c("2", s)
    def green(self, s): return self.c("32", s)
    def yellow(self, s): return self.c("33", s)
    def red(self, s): return self.c("31", s)
    def cyan(self, s): return self.c("36", s)

    def pct_color(self, p):
        txt = f"{p:5.1f}%"
        if p >= 80:
            return self.green(txt)
        if p >= 40:
            return self.yellow(txt)
        return self.red(txt)

    def bar(self, frac, width=28):
        frac = max(0.0, min(1.0, frac))
        n = int(round(width * frac))
        return self.cyan("█" * n + "░" * (width - n))

    def hr(self, w=72):
        print(self.dim("─" * w))

    def banner(self, title, subtitle):
        w = 72
        print()
        print(self.bold("┌" + "─" * (w - 2) + "┐"))
        print(self.bold("│") + title.center(w - 2) + self.bold("│"))
        print(self.bold("│") + self.dim(subtitle.center(w - 2)) + self.bold("│"))
        print(self.bold("└" + "─" * (w - 2) + "┘"))
        print()

    def kv(self, k, v):
        print(f"  {self.dim(k.ljust(22))} {v}")

    def progress(self, i, n, extra=""):
        frac = i / n if n else 1
        w = 24
        nfill = int(w * frac)
        bar = self.cyan("█" * nfill) + self.dim("░" * (w - nfill))
        msg = f"  {bar}  {i}/{n}  {extra}"
        if sys.stdout.isatty():
            sys.stdout.write("\r" + msg.ljust(78))
            sys.stdout.flush()
            if i >= n:
                sys.stdout.write("\n")
                sys.stdout.flush()
        elif i == n or i == 1 or i % 10 == 0:
            print(msg)


def fmt_asc(raw):
    if not raw:
        return None
    s = str(raw).replace("FASB ", "").strip()
    if s.lower().startswith("asc "):
        return "ASC " + s[4:].strip()
    return "ASC " + s


def resolve_bench(path: Path) -> Path:
    bench = path.expanduser().resolve()
    exam = bench / "data/benchmark/exam.jsonl"
    key = bench / "data/benchmark/answer_key.jsonl"
    scorer = bench / "src/scorer.py"
    if not exam.is_file() or not key.is_file() or not scorer.is_file():
        raise SystemExit(
            f"IntelliAudit-Bench not found at {bench}\n"
            "Need data/benchmark/exam.jsonl, answer_key.jsonl, and src/scorer.py\n"
            "Pass --bench /path/to/IntelliAudit-1  or set INTELLIAUDIT_ROOT"
        )
    return bench


def ensure_taxonomy_xml(bench: Path) -> Path:
    dest = CAP / ".cache/us-gaap-ref-2025.xml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return dest
    src_xml = bench / "results/.cache/us-gaap-ref-2025.xml"
    if src_xml.is_file() and src_xml.stat().st_size > 1_000_000:
        dest.write_bytes(src_xml.read_bytes())
        return dest
    zpath = bench / "src/.cache/us-gaap-2025.zip"
    if not zpath.is_file():
        raise SystemExit(
            f"US-GAAP 2025 taxonomy not found.\n"
            f"Looked for {dest}, {src_xml}, and {zpath}"
        )
    with zipfile.ZipFile(zpath) as z:
        name = "us-gaap-2025/elts/us-gaap-ref-2025.xml"
        if name not in z.namelist():
            hits = [n for n in z.namelist() if n.endswith("us-gaap-ref-2025.xml")]
            if not hits:
                raise SystemExit("us-gaap-ref-2025.xml not in zip")
            name = hits[0]
        dest.write_bytes(z.read(name))
    return dest


def load_exam(bench: Path, full: bool, n: int, seed: int):
    rows = [json.loads(l) for l in (bench / "data/benchmark/exam.jsonl").read_text().splitlines() if l.strip()]
    if full:
        return rows
    by = defaultdict(list)
    for e in rows:
        by[e["metadata"]["statement_type"]].append(e)
    rng = random.Random(seed)
    if n < 1:
        raise ValueError("--n must be positive")
    per, remainder = divmod(n, 3)
    out = []
    remaining = []
    for index, st in enumerate(("BalanceSheet", "IncomeStatement", "CashFlow")):
        pool = list(by[st])
        rng.shuffle(pool)
        take = per + int(index < remainder)
        out.extend(pool[:take])
        remaining.extend(pool[take:])
    rng.shuffle(remaining)
    out.extend(remaining[:max(0, n - len(out))])
    rng.shuffle(out)
    return out


def to_item(e):
    st = e["metadata"]["statement_type"]
    return {
        "table": e["statement_text"],
        "transaction_data": e.get("transaction_data") or "",
        "sheet_type": SHEET[st],
        "company": e["metadata"].get("company") or "",
    }


def load_dotenv_keys():
    """Pull API keys from capstone .env if they are not already in the environment."""
    env_path = CAP / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        name, val = raw.split("=", 1)
        name = name.strip()
        val = val.strip().strip('"').strip("'")
        if name and val and not os.environ.get(name):
            os.environ[name] = val


def stage2_provider():
    """Prefer OpenRouter (user's key). Fall back to OpenAI only if that is all we have."""
    load_dotenv_keys()
    or_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if or_key:
        return {
            "name": "openrouter",
            "key": or_key,
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "model": "openai/gpt-4o-mini",
            "headers": {
                "Authorization": "Bearer " + or_key,
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/dakshkashyap/financial-audit-capstone",
                "X-Title": "IntelliAudit Stage 2",
            },
        }
    oa_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if oa_key:
        return {
            "name": "openai",
            "key": oa_key,
            "url": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-4o-mini",
            "headers": {
                "Authorization": "Bearer " + oa_key,
                "Content-Type": "application/json",
            },
        }
    return None


def stage2_chat(system, user, model=None):
    prov = stage2_provider()
    if not prov:
        return None, "set OPENROUTER_API_KEY (capstone .env or export) — OpenAI has no credits"
    model = model or prov["model"]
    body = json.dumps({
        "model": model,
        "temperature": 1.0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        prov["url"],
        data=body,
        headers=prov["headers"],
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"], None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:240]}"


def parse_stage2_obj(raw):
    import re
    text = (raw or "").strip()
    parsed = None
    try:
        parsed = json.loads(text, strict=False)
    except json.JSONDecodeError:
        for m in re.finditer(r"```(?:json)?\s*([\s\S]+?)```", text):
            try:
                parsed = json.loads(m.group(1).strip(), strict=False)
                break
            except json.JSONDecodeError:
                pass
        if parsed is None:
            m = re.search(r"\{[\s\S]+\}", text)
            if m:
                try:
                    parsed = json.loads(m.group(0), strict=False)
                except json.JSONDecodeError:
                    parsed = None
    return parsed if isinstance(parsed, dict) else None


def parse_stage2(raw):
    import re
    parsed = parse_stage2_obj(raw)
    if not isinstance(parsed, dict):
        return None, None, None, None
    gj = str(parsed.get("General Judgment") or "")
    info = parsed.get("Information for error 1") or {}
    eid = info.get("Error Identification") or {}
    et = eid.get("Error Type")
    row = eid.get("Problematic Entry")
    row_n = None
    if row is not None:
        m = re.search(r"\d+", str(row))
        if m:
            row_n = int(m.group())
    incorrect = gj.strip().lower() == "incorrect"
    asc = fmt_asc(info.get("Standards Citation")) if incorrect else None
    if not incorrect:
        et, row_n = None, None
    return gj, et, row_n, asc


def score_preds(preds, key, bench: Path, t: T, det_title=None, cite_title=None):
    sys.path.insert(0, str(bench / "src"))
    from scorer import score_citation, score_detection
    from core.metrics import _norm_type

    n = len(preds)
    def judgment(p):
        return p.get("predicted_judgment") or ("Incorrect" if p.get("stage0_fired") or p.get("predicted_error_type") else "Unverified")

    det_fired = [p for p in preds if judgment(p).strip().lower() == "incorrect"]
    hit = {"topic": 0, "subtopic": 0, "full": 0, "etype": 0, "row": 0, "joint": 0, "judgment": 0}
    cite_fired = 0
    n_citable = 0
    citation_abstains = noncitable_n = noncitable_citations = 0
    by_type = defaultdict(lambda: {"n": 0, "fire": 0})
    pairs = []
    for p in preds:
        k = key[p["sample_id"]]
        et = k["error_type"]
        by_type[et]["n"] += 1
        det = {
            "General Judgment": judgment(p),
            "error_type": _norm_type(p.get("predicted_error_type") or ""),
            "problematic_entry": p.get("predicted_row"),
        }
        sd = score_detection(det, k)
        hit["judgment"] += sd["em_general_judgment"]
        if judgment(p).strip().lower() == "incorrect":
            by_type[et]["fire"] += 1
            if sd["em_error_type"]:
                hit["etype"] += 1
            if sd["em_error_entry"]:
                hit["row"] += 1
            hit["joint"] += int(bool(sd["em_general_judgment"] and sd["em_error_type"] and sd["em_error_entry"]))
        gt = k["ground_truth_citations"]
        sc = score_citation(p.get("predicted_asc") or "", gt, credit_linkbase_set=False)
        if sc is None:
            noncitable_n += 1
            noncitable_citations += int(bool(p.get("predicted_asc")))
            continue
        n_citable += 1
        if p.get("predicted_asc"):
            cite_fired += 1
            hit["topic"] += sc["em_topic"]
            hit["subtopic"] += sc["em_subtopic"]
            hit["full"] += sc["em_full"]
            pairs.append((et, gt.get("asc_full"), p["predicted_asc"], sc))
        else:
            citation_abstains += 1

    nf = len(det_fired)
    print()
    print(t.bold(det_title or "  STAGE 0  ·  detection"))
    t.hr()
    print(f"  fired          {nf}/{n}   {t.bar(nf / n if n else 0)}  {t.pct_color(100 * nf / n if n else 0)}")
    print(f"  abstained      {n - nf}/{n}")
    if nf:
        print(f"  type EM        {t.pct_color(100 * hit['etype'] / nf)}  of fires     "
              f"recall {t.pct_color(100 * hit['etype'] / n)}")
        print(f"  row  EM        {t.pct_color(100 * hit['row'] / nf)}  of fires     "
              f"recall {t.pct_color(100 * hit['row'] / n)}")
    print()
    print(f"  {'error type':<22} {'n':>4}  {'fired':>6}  coverage")
    for et, s in sorted(by_type.items(), key=lambda kv: -kv[1]["n"]):
        cov = 100 * s["fire"] / s["n"] if s["n"] else 0
        print(f"  {et:<22} {s['n']:>4}  {s['fire']:>6}  {t.bar(s['fire']/s['n'] if s['n'] else 0, 18)} {t.pct_color(cov)}")

    print()
    print(t.bold(cite_title or "  STAGE 1  ·  citation  (predicted ASC vs answer-key governing ASC)"))
    t.hr()
    cf = cite_fired
    print(f"  {'metric':<16} {'precision (of cited)':>22} {'recall (of this run)':>22}")
    for lab, keyn in (("ASC topic", "topic"), ("ASC subtopic", "subtopic"), ("ASC full", "full")):
        p_ = 100 * hit[keyn] / cf if cf else 0
        r_ = 100 * hit[keyn] / n_citable if n_citable else 0
        print(f"  {lab:<16} {t.pct_color(p_):>22} {t.pct_color(r_):>22}")
    print()
    print(t.dim("  Precision = correct WHEN Stage 1 printed an ASC."))
    print(t.dim(f"  Recall = correct / {n_citable} citable items (citation abstains count as misses)."))
    print(t.dim(f"  Non-citable items = {noncitable_n}; unsupported citations on these = {noncitable_citations}."))
    print(t.dim("  Full ASC is strict (210-10-45-1). Topic is loose (210)."))

    misses = [x for x in pairs if not x[3]["em_full"]]
    if pairs:
        print()
        print(t.bold("  Stage 1 mismatches (gold → predicted)"))
        t.hr()
        shown = Counter((g, p) for _, g, p, sc in misses)
        for (g, p), c in shown.most_common(8):
            print(f"  {g:<22} → {p:<22}  ×{c}")
        if not misses:
            print(t.green("  none — every cited ASC matched at full paragraph"))

    return {
        "n": n, "fired": nf, "cited": cf, "citable_n": n_citable,
        "citation_abstains": citation_abstains,
        "noncitable_n": noncitable_n, "noncitable_citations": noncitable_citations,
        "judgment_em": 100 * hit["judgment"] / n if n else 0,
        "joint_detection_em": 100 * hit["joint"] / n if n else 0,
        "type_p": 100 * hit["etype"] / nf if nf else 0,
        "row_p": 100 * hit["row"] / nf if nf else 0,
        "topic_p": 100 * hit["topic"] / cf if cf else 0,
        "topic_r": 100 * hit["topic"] / n_citable if n_citable else 0,
        "full_p": 100 * hit["full"] / cf if cf else 0,
        "full_r": 100 * hit["full"] / n_citable if n_citable else 0,
        "citation_metric": "strict_governing_paragraph_em_citable_only",
    }


def run_clean(bench: Path, graph, run_pipeline, t: T, n_max=223):
    path = bench / "data/benchmark/statements_clean.jsonl"
    if not path.is_file():
        print(t.yellow("  (no statements_clean.jsonl — skip false-alarm check)"))
        return
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()][:n_max]
    fp = 0
    t0 = time.time()
    for i, e in enumerate(rows, 1):
        st = e["metadata"]["statement_type"]
        item = {
            "table": e["statement_text"],
            "transaction_data": "",
            "sheet_type": SHEET[st],
            "company": e["metadata"].get("company") or "",
        }
        rec = run_pipeline(item, graph)
        if not rec.abstained:
            fp += 1
        t.progress(i, len(rows), extra=t.dim(f"false alarms {fp}"))
    print(f"  clean false alarms  {fp}/{len(rows)}   {t.pct_color(100 * fp / len(rows) if rows else 0)}"
          f"  {t.dim(f'{time.time()-t0:.1f}s')}")


def main():
    ap = argparse.ArgumentParser(
        description="Run this repo's Stage 0–1 on IntelliAudit-Bench exam.jsonl and print P/R."
    )
    ap.add_argument("--n", type=int, default=54, help="sample size split across BS/IS/CF (default 54)")
    ap.add_argument("--full", action="store_true", help="all exam items")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--stage2", action="store_true", help="LLM on Stage 0 abstains (OPENROUTER_API_KEY or OPENAI_API_KEY)")
    ap.add_argument("--stage2-model", default=None, help="OpenRouter/OpenAI model id (default: openai/gpt-4o-mini via OpenRouter)")
    ap.add_argument("--clean", action="store_true", help="also run Stage 0 on clean statements")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument(
        "--bench",
        default=str(BENCH_DEFAULT),
        help="path to IntelliAudit repo (exam.jsonl + answer_key + scorer)",
    )
    args = ap.parse_args()
    t = T(color=not args.no_color)
    bench = resolve_bench(Path(args.bench))

    t.banner(
        "Stage 0 → 1  on  IntelliAudit-Bench",
        "auditor = this repo  ·  exam/key pulled from --bench",
    )
    exam = load_exam(bench, args.full, args.n, args.seed)
    t.kv("cwd (auditor)", str(CAP))
    t.kv("benchmark", str(bench))
    t.kv("exam items", f"{len(exam)}" + ("  (full set)" if args.full else f"  (sample, seed={args.seed})"))
    t.kv("taxonomy", "US-GAAP 2025 reference linkbase")
    load_dotenv_keys()
    prov = stage2_provider() if args.stage2 else None
    if args.stage2 and prov:
        t.kv("stage 2", f"on  ({prov['name']} / {args.stage2_model or prov['model']})")
    elif args.stage2:
        t.kv("stage 2", "on  (no OPENROUTER_API_KEY — put it in capstone .env)")
    else:
        t.kv("stage 2", "off (add --stage2)")
    print()

    xml = ensure_taxonomy_xml(bench)
    from approaches.full_pipeline.pipeline import run_pipeline
    from approaches.stage1_taxonomy_citation.stage1_arelle import run_stage1
    from core.taxonomy_graph import TaxonomyGraph

    graph = TaxonomyGraph(cache_path=str(xml))
    if not graph.available:
        raise SystemExit("US-GAAP 2025 taxonomy failed to load")
    print(t.green("  taxonomy loaded") + t.dim(f"  {xml}"))
    print()
    print(t.bold("  running Stage 0 + Stage 1 (blind)"))

    out_dir = CAP / "results/iab_exam"
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "pred_exam_pipeline.jsonl"

    preds = []
    t0 = time.time()
    n_fire = 0
    for i, e in enumerate(exam, 1):
        rec = run_pipeline(to_item(e), graph)
        fired = not rec.abstained
        n_fire += int(fired)
        preds.append({
            "sample_id": e["sample_id"],
            "stage0_fired": fired,
            "predicted_judgment": rec.judgment if fired else "Unverified",
            "predicted_asc": fmt_asc(rec.citation_primary)
                             if fired and rec.citation_applicability_verified else None,
            "citation_candidate_primary": fmt_asc(rec.citation_primary) if fired else None,
            "citation_candidates": rec.citation_candidates if fired else [],
            "citation_applicability_verified": rec.citation_applicability_verified,
            "predicted_error_type": rec.error_type if fired else None,
            "predicted_row": rec.problematic_entry if fired else None,
            "stage1_source": rec.citation_source if fired else None,
        })
        extra = t.green("fire") if fired else t.dim("abstain")
        t.progress(i, len(exam), extra=f"{extra}   fires {n_fire}")
    elapsed = time.time() - t0

    s1_preds = [dict(p) for p in preds]

    if args.stage2:
        print()
        s2_model = args.stage2_model or ((prov or {}).get("model") if prov else None)
        print(t.bold(f"  STAGE 2  ·  focused LLM on abstains  ({(prov or {}).get('name', '?')} / {s2_model or 'no key'})"))
        t.hr()
        try:
            from approaches.stage2_llm_audit import stage2_llm
        except Exception as ex:
            print(t.red(f"  could not import Stage 2: {ex}"))
        else:
            abst = [p for p in preds if not p["stage0_fired"]]
            exam_by = {e["sample_id"]: e for e in exam}
            n_ok = n_err = n_flag = n_veto = 0
            for i, p in enumerate(abst, 1):
                item = to_item(exam_by[p["sample_id"]])
                rec = run_pipeline(item, graph)
                stmt = run_stage1(item, graph).statement
                raw, err = stage2_chat(
                    stage2_llm.system_for(rec),
                    stage2_llm.build_user(item, rec, stmt),
                    model=s2_model,
                )
                if err:
                    p["stage2_error"] = err
                    n_err += 1
                    print(t.red(f"  [{i}/{len(abst)}] {err}"))
                    low = err.lower()
                    if "no credits" in low or "429" in err or "insufficient_quota" in low or "401" in err:
                        print(t.yellow("  stopping Stage 2 — check OpenRouter key/credits, then re-run with --stage2"))
                        break
                    continue
                blob = parse_stage2_obj(raw)
                p["stage2_raw_text"] = raw
                vetoed = False
                if isinstance(blob, dict):
                    blob, vetoed = stage2_llm.apply_consistency_veto(
                        blob,
                        verified_consistent=rec.verified_consistent,
                        original_table=item["table"],
                    )
                    if vetoed:
                        n_veto += 1
                    blob = stage2_llm.apply_citation_snap(blob, stmt)
                    gj, et, row_n, asc = parse_stage2(json.dumps(blob) if blob else "")
                else:
                    gj, et, row_n, asc = parse_stage2(raw)
                    if stmt is not None:
                        fake = {
                            "General Judgment": gj or "",
                            "Information for error 1": {
                                "Error Identification": {
                                    "Error Type": et or "",
                                    "Problematic Entry": row_n,
                                },
                                "Standards Citation": asc or "",
                            },
                        }
                        fake = stage2_llm.apply_citation_snap(fake, stmt, et)
                        gj, et, row_n, asc = parse_stage2(json.dumps(fake))
                n_ok += 1
                p["predicted_judgment"] = gj or "Unverified"
                if (gj or "").strip().lower() == "incorrect":
                    n_flag += 1
                    p["predicted_asc"] = asc
                    p["predicted_error_type"] = et
                    p["predicted_row"] = row_n
                    p["stage2"] = True
                time.sleep(0.4)
                t.progress(i, len(abst), extra=t.dim(f"flagged {n_flag}  veto {n_veto}  errors {n_err}"))
            print(f"  stage 2 done   ok={n_ok}  flagged_incorrect={n_flag}  vetoed={n_veto}  errors={n_err}")

    pred_path.write_text("".join(json.dumps(p) + "\n" for p in preds))
    print()
    print(t.dim(f"  predictions saved  {pred_path}  ({elapsed:.1f}s)"))
    print(t.bold("  scoring against IntelliAudit answer_key.jsonl  (key unused while auditing)"))

    key = {}
    for line in (bench / "data/benchmark/answer_key.jsonl").read_text().splitlines():
        r = json.loads(line)
        key[r["sample_id"]] = r
    s1 = score_preds(
        s1_preds, key, bench, t,
        det_title="  STAGE 0  ·  detection  (rule gate only)",
        cite_title="  STAGE 1  ·  citation  (taxonomy, no LLM)",
    )
    summary = s1
    if args.stage2:
        summary = score_preds(
            preds, key, bench, t,
            det_title="  STAGE 0+2  ·  detection  (gate + LLM)",
            cite_title="  STAGE 1+2  ·  citation  (taxonomy + LLM)",
        )

    if args.clean:
        print()
        print(t.bold("  CLEAN CONTROL  ·  false alarms"))
        t.hr()
        run_clean(bench, graph, run_pipeline, t)

    print()
    t.hr()
    print(t.bold("  HEADLINE"))
    print(f"  Stage 0 fire rate     {t.pct_color(100 * s1['fired'] / s1['n'] if s1['n'] else 0)}"
          f"    type/row when fired  {t.pct_color(s1['type_p'])} / {t.pct_color(s1['row_p'])}")
    print(f"  Stage 1 ASC topic     P {t.pct_color(s1['topic_p'])}   R {t.pct_color(s1['topic_r'])}")
    print(f"  Stage 1 ASC full      P {t.pct_color(s1['full_p'])}   R {t.pct_color(s1['full_r'])}")
    if args.stage2 and summary is not s1:
        print(f"  Stage 0+2 fire rate   {t.pct_color(100 * summary['fired'] / summary['n'] if summary['n'] else 0)}"
              f"    type/row when fired  {t.pct_color(summary['type_p'])} / {t.pct_color(summary['row_p'])}")
        print(f"  Stage 1+2 ASC topic   P {t.pct_color(summary['topic_p'])}   R {t.pct_color(summary['topic_r'])}")
        print(f"  Stage 1+2 ASC full    P {t.pct_color(summary['full_p'])}   R {t.pct_color(summary['full_r'])}")
    print()
    print(t.dim("  cd /Users/admin/Desktop/financial-audit-capstone"))
    print(t.dim("  python3 -m approaches.full_pipeline.run_iab_exam"))
    print(t.dim("  python3 -m approaches.full_pipeline.run_iab_exam --full"))
    print()


if __name__ == "__main__":
    os.chdir(CAP)
    main()
