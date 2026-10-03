#!/usr/bin/env python3
"""Build an offline, review-only dashboard using verified local research artifacts.

No server, dependencies, credentials, or network calls are required. Missing
reports remain missing; this builder never supplies an experimental result.
The answer key is used ONLY for the explicitly labelled review panel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "dataset": "research/results/dataset_audit.json",
    "pipeline": "research/reviews/pipeline.json",
    "pilot": "research/artifacts/pilot/report.json",
    "frontier_format_diagnostic": "research/artifacts/pilot/frontier_format_diagnostic/report.json",
    "cheap_evidence_diagnostic": "research/artifacts/pilot/qwen8_evidence_diagnostic/report.json",
    "raw_output_diagnostic": "research/artifacts/pilot/raw_output_diagnostics.json",
    "pilot_manifest": "research/artifacts/pilot/manifest.json",
    "pilot_config": "research/config/pilot.json",
    "legacy_offline": "research/artifacts/pilot/legacy_local_offline_metrics.json",
    "legacy_adapted": "research/artifacts/pilot/legacy_local_adapted_metrics.json",
    "legacy_verified_citation": "research/artifacts/pilot/legacy_local_adapted_verified_citation_metrics.json",
    "sec": "research/results/sec_pilot_companies.json",
    "sec_accessions": "research/results/sec_accession_consistency.json",
    "evidence_demo": "research/artifacts/evidence_budget_demo.json",
    "related_work": "research/related_work.json",
}


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def first(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return default


def records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [dict(value=row, key=key) if not isinstance(row, dict)
                else dict(row, key=key) for key, row in value.items()]
    return []


def load_sources(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reports: dict[str, Any] = {}
    provenance = []
    for name, relative in SOURCES.items():
        path = root / relative
        entry: dict[str, Any] = {"name": name, "path": relative, "status": "missing"}
        if path.exists():
            raw = path.read_bytes()
            entry.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            try:
                reports[name] = json.loads(raw)
                entry["status"] = "loaded"
            except (ValueError, UnicodeError) as exc:
                entry.update(status="invalid", error=str(exc))
        provenance.append(entry)
    return reports, provenance


def prediction_files(root: Path, pilot: dict[str, Any]) -> list[Path]:
    # All discovery is restricted to the local pilot output directory. API keys,
    # environment variables, and unrelated output trees are never inspected.
    base = root / "research/artifacts/pilot"
    candidates = set(base.glob("*predictions*.jsonl"))
    candidates.update(base.glob("predictions/*.jsonl"))
    candidates.update(base.glob("runs/*/predictions.jsonl"))
    for run in records(first(pilot, "runs", "models", default=[])):
        for key in ("predictions_path", "output_path", "predictions_file"):
            raw = run.get(key)
            if isinstance(raw, str):
                candidate = (root / raw).resolve()
                if candidate.is_relative_to(base.resolve()) and candidate.suffix == ".jsonl":
                    candidates.add(candidate)
    return sorted(path for path in candidates if path.exists())


def build_cases(root: Path, pilot: dict[str, Any], limit: int,
                supplementary: dict[str, Any] | None = None) -> dict[str, Any]:
    prepared = root / "research/artifacts/pilot/public_inputs.jsonl"
    if prepared.exists():
        exams = read_jsonl(prepared)
        gold = {row["case_id"]: row["gold"] for row in
                read_jsonl(root / "research/artifacts/pilot/scoring_only.jsonl") if "case_id" in row}
        case_source = "Frozen development pilot public inputs. Scoring-only gold is joined exclusively for review."
    else:
        exams = read_jsonl(root / "data/intelliaudit/exam.jsonl")
        gold = {row["sample_id"]: row for row in
                read_jsonl(root / "data/intelliaudit/answer_key.jsonl") if "sample_id" in row}
        case_source = "Legacy local snapshot; pilot inputs unavailable."
    predictions: dict[str, list[dict[str, Any]]] = {}
    inline = records(first(pilot, "predictions", "case_results", default=[]))
    outputs: list[tuple[str, dict[str, Any]]] = [("report", row) for row in inline]
    config_path = root / "research/config/pilot.json"
    config = read_json(config_path) if config_path.exists() else {}
    for condition, result in pilot.get("conditions", {}).items():
        model = config.get("conditions", {}).get(condition, {}).get("model", condition)
        for row in result.get("cases", []):
            outputs.append((condition, dict(row, condition=condition, model=model,
                                            evaluation_phase="Frozen primary pilot")))
    for report in (supplementary or {}).values():
        for condition, result in report.get("conditions", {}).items():
            if condition != report.get("posthoc_condition"):
                continue
            settings = report.get("diagnostic_manifest", {}).get("settings", {})
            model = settings.get("model") or (
                config.get("conditions", {}).get("opus_direct" if condition.startswith("opus")
                                                  else "qwen8_direct", {}).get("model", condition))
            for row in result.get("cases", []):
                outputs.append((condition, dict(row, condition=condition, model=model,
                                                evaluation_phase="Post-hoc diagnostic; unmatched settings or method budget")))
    files = prediction_files(root, pilot)
    if not pilot.get("conditions"):
        for path in files:
            for row in read_jsonl(path):
                outputs.append((path.stem.replace("predictions_", ""), row))
    for source, row in outputs:
        sample_id = first(row, "sample_id", "case_id", "id")
        if sample_id:
            # Scorer rows include hidden truth columns. They belong exclusively
            # in the labelled, closed answer-key review panel, never in the
            # ordinary prediction display.
            item = {key: value for key, value in row.items()
                    if not key.startswith("gold_") and key not in {"gold", "corrected_statement_text"}}
            item.setdefault("model", first(row, "model_id", "model_name", default=source))
            item.setdefault("condition", first(row, "ablation", default="full"))
            predictions.setdefault(str(sample_id), []).append(item)

    # Show experimental cases first, then round-robin by company and rule so a
    # bounded review sample is explicit and reproducible, not a success filter.
    by_id = {str(first(row, "sample_id", "case_id")): row for row in exams}
    selected_ids = [sample_id for sample_id in sorted(predictions) if sample_id in by_id]
    buckets: dict[tuple[str, str], list[str]] = {}
    for row in exams:
        sample_id = str(first(row, "sample_id", "case_id"))
        if sample_id in selected_ids:
            continue
        metadata = row.get("metadata", {})
        key = (str(metadata.get("company", "Unknown")), str(gold.get(sample_id, {}).get("rule_id", "Unknown")))
        buckets.setdefault(key, []).append(sample_id)
    while buckets and len(selected_ids) < limit:
        for key in sorted(buckets):
            selected_ids.append(buckets[key].pop(0))
            if not buckets[key]:
                del buckets[key]
            if len(selected_ids) >= limit:
                break
    selected_ids = selected_ids[:limit]
    cases = []
    for sample_id in selected_ids:
        row = by_id[sample_id]
        cases.append({
            "sample_id": sample_id,
            "metadata": row.get("metadata", {}),
            "statement_text": row.get("statement_text", ""),
            "transaction_data": row.get("transaction_data", ""),
            "gold_review_only": gold.get(sample_id),
            "predictions": predictions.get(sample_id, []),
        })
    return {"rows": cases, "available_cases": len(exams), "displayed_cases": len(cases),
            "case_selection": case_source + " Pilot cases first, then deterministic company × rule round-robin; bounded review sample, not a new evaluation split.",
            "prediction_files": [str(path.relative_to(root)) for path in files]}


def embedded_json(value: Any) -> str:
    # Escape script delimiters, HTML metacharacters, and JS line separators even
    # inside application/json. A case containing </script> remains inert text.
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def condition_costs(root: Path, pilot: dict[str, Any], prepared: str = "research/artifacts/pilot") -> dict[str, Any]:
    """Join final condition traces to ledger call IDs; exclude archived smoke calls."""
    ledger_path = root / "research/artifacts/api_ledger.jsonl"
    ledger = read_jsonl(ledger_path)
    reserved = {row["call_id"]: row for row in ledger if row.get("event") == "reservation"}
    completed = {row["call_id"]: row for row in ledger if row.get("event") == "completion"}
    output = {}
    for condition in pilot.get("conditions", {}):
        path = root / prepared / "predictions" / (condition + ".jsonl")
        if condition == pilot.get("posthoc_condition") and not path.exists():
            path = root / prepared / "predictions.jsonl"
        if not path.exists() or not path.resolve().is_relative_to((root / prepared).resolve()):
            continue
        allowed = {row["case_id"] for row in pilot["conditions"][condition].get("cases", [])}
        call_ids = {call_id for row in read_jsonl(path) if row.get("case_id") in allowed
                    for call_id in row.get("trace", []) if isinstance(call_id, str)}
        if not call_ids:
            continue
        responses = [completed[call_id] for call_id in call_ids if call_id in completed]
        priced = [Decimal(str(row["reported_actual_usd"])) for row in responses
                  if row.get("reported_actual_usd") is not None]
        output[condition] = {
            "reported_actual_usd": float(sum(priced, Decimal("0"))) if priced else None,
            "reserved_upper_bound_usd": float(sum((Decimal(str(reserved[c]["reserved_usd"]))
                                                    for c in call_ids if c in reserved), Decimal("0"))),
            "calls": len(call_ids), "priced_responses": len(priced),
            "unpriced_responses": len(responses) - len(priced),
            "unresolved_calls": len(call_ids) - len(responses),
            "scope": "Current condition prediction traces only; excludes archived setup/protocol smoke calls.",
        }
    return output


def global_cost(root: Path) -> dict[str, Any] | None:
    path = root / "research/artifacts/api_ledger.jsonl"
    if not path.exists():
        return None
    events = read_jsonl(path)
    responses = [row for row in events if row.get("event") == "completion"]
    priced = [Decimal(str(row["reported_actual_usd"])) for row in responses if row.get("reported_actual_usd") is not None]
    reservations = [row for row in events if row.get("event") == "reservation"]
    return {"reported_actual_usd": float(sum(priced, Decimal("0"))) if priced else None,
            "unpriced_responses": len(responses) - len(priced),
            "reserved_upper_bound_usd": float(sum((Decimal(str(row["reserved_usd"])) for row in reservations), Decimal("0"))),
            "scope": "All shared-ledger calls, including archived smoke and post-hoc format diagnostics; no refund assumed for missing usage.cost."}


CSS = r"""
:root{--ink:#152b46;--navy:#102742;--blue:#285cdb;--light:#f3f6fb;--line:#dce4ef;--muted:#617087;--amber:#936600;--red:#a1303e;--green:#13705f;--white:#fff}*{box-sizing:border-box}body{margin:0;background:var(--light);color:var(--ink);font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}a{color:var(--blue)}button,select,input{font:inherit}button{cursor:pointer}button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #68b4ff;outline-offset:3px}.shell{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;background:var(--navy);color:white;padding:30px 23px;display:flex;flex-direction:column}.brand-mark{border:1px solid #7690bc;width:38px;height:38px;display:grid;place-items:center;border-radius:9px;color:#a9c7ff;font-weight:750}.brand{font-size:19px;font-weight:700;line-height:1.3;margin:16px 0 6px}.brand-sub{color:#a8bdd9;font-size:12px}.sidebar nav{margin-top:32px;display:grid;gap:8px}.sidebar nav a{display:block;color:#c4d2e8;text-decoration:none;padding:11px 12px;border-radius:7px}.sidebar nav a:hover,.sidebar nav a.active{color:white;background:#294463}.nav-num{font-size:11px;opacity:.65;padding-right:10px}.sidebar .foot{margin-top:auto;font-size:12px;color:#a8bdd9;border-top:1px solid #39516e;padding-top:18px}.main{max-width:1600px;padding:35px 44px 60px;width:100%;margin:auto}.eyebrow{color:var(--blue);font-weight:700;font-size:12px;letter-spacing:.12em;text-transform:uppercase}h1{font-size:34px;line-height:1.15;letter-spacing:-.025em;margin:9px 0 12px}h2{font-size:23px;line-height:1.3;margin:0 0 8px}h3{font-size:16px;line-height:1.4;margin:0 0 8px}.lede{color:var(--muted);max-width:830px;margin:0}.topline{display:flex;justify-content:space-between;gap:24px;align-items:start}.badge{display:inline-block;background:#e8eefc;border:1px solid #cedcfb;border-radius:20px;color:#254b93;padding:5px 11px;font-size:11px;font-weight:700;white-space:nowrap}.badge.pending{background:#fff6e4;color:var(--amber);border-color:#eddcae}.badge.failed{background:#fff0f1;color:var(--red);border-color:#edd1d7}.badge.good{background:#eaf7f2;color:var(--green);border-color:#c9e5da}.notice{border:1px solid #e5d4a6;background:#fff9ec;color:#72530d;border-radius:9px;padding:16px 19px;margin:24px 0;font-size:13px}.notice strong{color:#654708}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px}.card,.panel{border:1px solid var(--line);background:white;border-radius:10px}.card{padding:20px}.card-label{color:var(--muted);font-size:12px;line-height:1.3}.card-value{font-size:31px;line-height:1.2;font-weight:740;letter-spacing:-.02em;margin:12px 0 6px}.card-sub{color:var(--muted);font-size:11px;line-height:1.5}.section{margin-top:34px;scroll-margin-top:25px}.section-header{display:flex;justify-content:space-between;align-items:start;gap:20px;margin-bottom:17px}.section-header p{margin:0;color:var(--muted);font-size:13px}.panel{padding:23px;min-width:0}.muted{color:var(--muted)}.small{font-size:12px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:12px;text-align:left}th{font-weight:650;font-size:11px;color:var(--muted);padding:13px 12px;border-bottom:1px solid var(--line);white-space:nowrap;background:#fafbfd}td{padding:15px 12px;border-bottom:1px solid #edf1f6;vertical-align:top}tr:last-child td{border-bottom:0}.model-name{font-weight:680;max-width:210px;word-break:break-word}.bar-row{display:grid;grid-template-columns:200px minmax(100px,1fr) 80px;gap:15px;align-items:center;margin:17px 0;font-size:12px}.bar-track{height:12px;background:#eef2f8;border-radius:3px;overflow:hidden}.bar-fill{background:var(--blue);height:100%;border-radius:3px}.bar-note{font-variant-numeric:tabular-nums}.chart-caption{font-size:11px;color:var(--muted);margin-top:20px}.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:19px}.findings{display:grid;gap:12px}.finding{border-left:3px solid #d1a647;background:#fafbfd;padding:16px 18px;border-radius:0 6px 6px 0}.finding.critical{border-color:var(--red)}.finding h3{font-size:14px}.finding p{font-size:12px;margin:6px 0}.finding pre{white-space:pre-wrap;overflow-wrap:anywhere}.provenance{font-size:11px;color:var(--muted);word-break:break-word}.filters{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.filter{display:grid;gap:5px;color:var(--muted);font-size:11px}.filter select,.filter input{border:1px solid #cdd8e7;color:var(--ink);background:white;border-radius:6px;padding:8px 11px;min-width:160px}.case-layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:19px}.case-list{max-height:680px;overflow:auto;border:1px solid var(--line);border-radius:8px;background:white}.case-item{border:0;border-bottom:1px solid #e7edf6;padding:14px;width:100%;text-align:left;color:var(--ink);background:white;display:block}.case-item:hover{background:#f0f5ff}.case-item.active{background:#eaf1ff;box-shadow:inset 3px 0 var(--blue)}.case-company{font-size:12px;font-weight:700}.case-id{font-size:10px;color:var(--muted);overflow-wrap:anywhere;margin-top:3px}.case-meta{font-size:10px;color:var(--muted);margin-top:5px}.case-detail{min-width:0}.case-title{margin:0 0 3px;font-size:18px}.evidence-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:16px 0}.text-box{border:1px solid var(--line);border-radius:7px;overflow:hidden}.text-box h3{padding:12px 14px;margin:0;background:#f7f9fc;font-size:12px}.text-box pre,pre.report{font:11px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;padding:15px;margin:0;max-height:430px;overflow:auto;color:#31445d}.prediction{margin-top:12px;padding:15px;border:1px solid var(--line);border-radius:7px;font-size:12px;overflow-wrap:anywhere}.prediction pre{font:11px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;max-height:250px;overflow:auto}.gold{margin-top:20px;border:1px solid #e4cf97;background:#fff9ec;border-radius:8px;padding:13px 16px}.gold summary{font-size:12px;font-weight:700;cursor:pointer;color:#805a0a}.gold pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:350px;overflow:auto;font:11px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}.empty{padding:25px;text-align:center;color:var(--muted);font-size:13px}.legend{display:flex;flex-wrap:wrap;gap:20px;font-size:11px;color:var(--muted)}.dot{display:inline-block;width:8px;height:8px;border-radius:2px;background:var(--blue);margin-right:5px}.source{overflow-wrap:anywhere;font-size:12px;border-bottom:1px solid var(--line);padding:13px 0}.source:last-child{border:0}.source code{display:block;font-size:10px;color:var(--muted);overflow-wrap:anywhere;margin-top:5px}.tabs{display:flex;gap:6px;margin:14px 0}.tabs button{border:1px solid var(--line);background:white;color:var(--muted);padding:6px 11px;border-radius:5px;font-size:12px}.tabs button.active{background:#eaf1ff;color:var(--blue);border-color:#b7cafa}.footer{margin-top:40px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.button{border:1px solid #cbd8ec;background:white;color:var(--blue);padding:8px 13px;border-radius:6px;text-decoration:none;font-size:12px;display:inline-block}.slide{display:none;min-height:calc(100vh - 140px);padding:65px 70px;background:white;border:1px solid var(--line);border-radius:12px;position:relative}.slide.active{display:block}.slide h1{font-size:46px;max-width:920px}.slide h2{font-size:34px;margin-top:12px}.slide .lede{font-size:19px;max-width:1000px}.slide .cards{margin-top:40px}.slide li{font-size:21px;margin:20px 0;max-width:1000px}.slide .finding p{font-size:16px}.slide .finding h3{font-size:19px}.slide-footer{position:absolute;bottom:20px;left:70px;right:70px;display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}.slide-controls{display:flex;gap:12px;align-items:center;justify-content:center;margin:16px}.slide-controls button{border:1px solid #ccd8e8;background:white;padding:8px 18px;border-radius:6px;color:var(--blue)}.slides-body{padding:30px 5vw}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:1200px){.main{padding:30px 26px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.case-layout{grid-template-columns:225px minmax(0,1fr)}.evidence-grid{grid-template-columns:1fr}.bar-row{grid-template-columns:150px minmax(100px,1fr) 65px}}@media(max-width:850px){.shell{display:block}.sidebar{height:auto;position:static;padding:18px 22px}.brand-mark{display:none}.brand{margin:0;font-size:17px}.sidebar nav{display:flex;overflow:auto;margin-top:15px;gap:5px}.sidebar nav a{white-space:nowrap;font-size:12px;padding:8px}.sidebar .foot{display:none}.main{padding:24px 18px}.topline{display:block}.topline .badge{margin-top:15px}h1{font-size:29px}.two,.case-layout{grid-template-columns:1fr}.case-list{max-height:225px}.slide{padding:30px 25px}.slide h1{font-size:31px}.slide h2{font-size:26px}.slide li{font-size:17px}.slide-footer{left:25px;right:25px}.slide .lede{font-size:16px}}@media(max-width:550px){.cards{grid-template-columns:1fr}.bar-row{grid-template-columns:110px minmax(60px,1fr) 50px;gap:8px}.card-value{overflow-wrap:anywhere}}@media print{.sidebar,.filters,.slide-controls,.button{display:none!important}.shell,.main{display:block;padding:0;max-width:none}.panel,.card,.finding{break-inside:avoid}.case-list{display:none}.case-layout,.evidence-grid{display:block}.slide{display:block!important;min-height:0;height:100vh;border:0;border-radius:0;break-after:page;padding:35px}.slides-body{padding:0}.slide-footer{bottom:10px}.gold{background:white}.section{break-inside:avoid}body{background:white}table{font-size:10px}}
"""

JS = r"""
(()=>{
'use strict';
const DATA=JSON.parse(document.getElementById('research-data').textContent);
const $=id=>document.getElementById(id);
function el(tag,text,className){const n=document.createElement(tag);if(text!==null&&text!==undefined)n.textContent=String(text);if(className)n.className=className;return n;}
function append(parent,...children){children.filter(Boolean).forEach(c=>parent.append(c));return parent;}
function first(o,...keys){if(!o||typeof o!=='object')return null;for(const k of keys)if(o[k]!==undefined&&o[k]!==null)return o[k];return null;}
function entries(x){if(Array.isArray(x))return x.filter(v=>v&&typeof v==='object');if(x&&typeof x==='object')return Object.entries(x).map(([key,v])=>typeof v==='object'&&v!==null?{...v,key}:{key,value:v});return [];}
function number(x){if(typeof x==='string'&&/^[0-9]+(?:\.[0-9]+)?$/.test(x))x=Number(x);return typeof x==='number'&&Number.isFinite(x)?x:null;}
function fmt(x,d=1){const n=number(x);return n===null?'Not available':n.toLocaleString(undefined,{maximumFractionDigits:d});}
function percent(x){const n=number(x);return n===null?'Not measured':(n*100).toFixed(1)+'%';}
function money(x){const n=number(x);return n===null?'Not recorded':'$'+n.toFixed(4);}
function costLabel(run){const cost=DATA.condition_costs?.[run.condition];if(!cost)return money(run.cost_usd);let label=money(cost.reported_actual_usd);if(cost.unpriced_responses)label+=' + '+cost.unpriced_responses+' unpriced';if(cost.unresolved_calls)label+=' + '+cost.unresolved_calls+' unresolved';return label;}
function json(x){return JSON.stringify(x,null,2);}
function badge(text,status){return el('span',text,'badge '+(status||''));}
function metric(container,label,value,sub){append(container,append(el('article',null,'card'),el('div',label,'card-label'),el('div',value,'card-value'),el('div',sub,'card-sub')));}
function reportPanel(container,value){if(value===undefined||value===null){container.append(el('div','Artifact pending. No result has been substituted.','empty'));return;}container.append(el('pre',json(value),'report'));}
function safeURL(raw){try{const u=new URL(raw);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}}
function link(raw,label){const url=safeURL(raw);if(!url)return el('span',label||raw);const a=el('a',label||raw);a.href=url;a.rel='noopener noreferrer';a.target='_blank';return a;}
const reports=DATA.reports||{},dataset=reports.dataset||{},pilot=reports.pilot||{},pipeline=reports.pipeline||{};
const manifest=reports.pilot_manifest||{},config=reports.pilot_config||{},upstream=dataset.datasets?.upstream_usgaap||{};
function summaryValue(...keys){const s=upstream.counts||first(dataset,'summary','metrics')||dataset;return first(s,...keys);}
function renderSummary(){
 const companies=summaryValue('companies','n_companies','company_count');
 const ncompanies=Array.isArray(companies)?companies.length:number(companies);
 const ncases=summaryValue('exam','cases','n_cases','total_cases','exam_count','sample_count');
 metric($('metrics'),'Audited upstream cases',fmt(number(ncases)??number(DATA.cases.available_cases),0),'US GAAP upstream artifact count; accounting labels remain unvalidated.');
 metric($('metrics'),'Pilot cases / companies',fmt(number(pilot.n_cases)??number(manifest.n_cases),0)+' / '+fmt(number(pilot.n_companies)??number(manifest.selection?.n_companies),0),'Frozen development sample from '+fmt(ncompanies,0)+' upstream company clusters.');
 const actual=number(DATA.global_cost?.reported_actual_usd??pilot.cost_summary?.reported_actual_usd),unpriced=DATA.global_cost?.unpriced_responses;
 metric($('metrics'),'Shared ledger reported cost',actual===null?'Pending':'$'+actual.toFixed(4),'Includes archived smoke and post-hoc calls. '+(unpriced!==undefined?fmt(unpriced,0)+' unpriced responses. ':'')+'Conservative total reservation $'+fmt(DATA.global_cost?.reserved_upper_bound_usd,4)+'; hard cap $5.');
 metric($('metrics'),'Citation applicability','Unvalidated','Exact label agreement does not establish that a paragraph governs an error.');
 $('built-at').textContent='Built '+DATA.built_at+' (America/Vancouver) · offline review artifact';
}
function runRows(){
 if(pilot.conditions&&typeof pilot.conditions==='object')return Object.entries(pilot.conditions).map(([condition,row])=>{const states=row.statuses||{},successful=number(states.ok)||0,attempted=Object.values(states).reduce((a,b)=>a+(number(b)||0),0),missing=number(states.missing)||0;return {...row,condition,model:config.conditions?.[condition]?.model||condition,status:attempted===0||missing===attempted?'pending':successful===attempted?'completed':successful>0?'partial':'failed',successful,attempted,missing,errors:attempted-successful-missing,cost_usd:DATA.condition_costs?.[condition]?.reported_actual_usd};});
 return entries(first(pilot,'runs','models','results','model_results'));
}
function noValidAnswers(run){return number(run.successful)===0;}
function metricsFor(run){return first(run,'metrics','scores','evaluation')||run;}
function countedMetric(metric){if(!metric)return 'Not measured';return percent(metric.value)+' · '+fmt(metric.numerator,0)+' / '+fmt(metric.denominator,0);}
function agreement(run){const m=metricsFor(run);const nested=first(m,'unvalidated_full_citation_agreement','citation_full','full_citation','citation_exact','full_citation_accuracy','asc_full_accuracy','exact_citation_accuracy','citation_full_accuracy');if(typeof nested==='object'&&nested!==null)return first(nested,'accuracy','rate','value');return number(nested);}
function ci(run){const m=metricsFor(run);const full=first(m,'unvalidated_full_citation_agreement','citation_full','full_citation','citation_exact');const raw=first(m,'citation_full_ci','full_citation_ci','citation_ci','ci95','ci_95')||first(full,'company_cluster_ci95','ci95','ci_95','ci');if(Array.isArray(raw)&&raw.length===2)return raw.map(v=>percent(v)).join('–');if(raw&&typeof raw==='object'){const lo=first(raw,'low','lower','lo'),hi=first(raw,'high','upper','hi');if(number(lo)!==null&&number(hi)!==null)return percent(lo)+'–'+percent(hi);}return 'Not reported';}
function renderModels(){
 const runs=runRows();const body=$('model-body');body.replaceChildren();$('chart').replaceChildren();
 if(!runs.length){const tr=el('tr');const td=el('td','Pilot results pending. Model accuracy, costs, and confidence intervals are not measured.','empty');td.colSpan=9;tr.append(td);body.append(tr);$('chart').append(el('div','No measured model comparisons yet.','empty'));return;}
 for(const run of runs){const m=metricsFor(run),name=first(run,'model','model_id','model_name','name','key')||'Unknown model',condition=first(run,'condition','ablation')||'full';const status=first(run,'status','state')||'not recorded';const denominator=first(m,'citation_denominator','n_citable','citation_n','citable_n')??first(first(m,'unvalidated_full_citation_agreement','citation_full','full_citation','citation_exact'),'n','denominator');const attempted=first(run,'attempted','n_attempted','total_cases','n_cases')??first(m,'n','sample_count');const successful=first(run,'successful','n_successful','completed_cases')??first(m,'n_successful','n_evaluated');const errors=first(run,'errors','error_count','n_errors','failed')??first(m,'errors','error_count');const errorCount=Array.isArray(errors)?errors.length:errors;
 const tr=el('tr');append(tr,el('td',name,'model-name'),el('td',condition),append(el('td'),badge(status,/fail|error|blocked/i.test(status)?'failed':/complete|ok|success/i.test(status)?'good':'pending')),el('td',fmt(successful,0)+' / '+fmt(attempted,0)),el('td',noValidAnswers(run)?'No valid answers':percent(agreement(run))),el('td',fmt(denominator,0)),el('td',noValidAnswers(run)?'Not applicable':ci(run)),el('td',costLabel(run)),el('td',fmt(number(errorCount),0)+' / '+fmt(run.missing??null,0)));body.append(tr);
 const a=number(agreement(run));if(a!==null&&!noValidAnswers(run)){const track=el('div',null,'bar-track');const fill=el('div',null,'bar-fill');fill.style.width=Math.max(0,Math.min(100,a*100))+'%';track.append(fill);const label=el('span',name+' · '+condition);append($('chart'),append(el('div',null,'bar-row'),label,track,el('span',percent(a),'bar-note')));}
 }
 if(!$('chart').childElementCount)$('chart').append(el('div','No citation agreement metrics were recorded. Missing metrics are not replaced with zero.','empty'));
 reportPanel($('pilot-details'),reports.pilot);
}
function renderDecisionMetrics(){const runs=runRows(),box=$('decision-metrics');if(!runs.length)return;box.append(el('h3','Detection, clean controls & evidence verification'));const wrap=el('div',null,'table-wrap'),table=el('table'),head=el('thead'),tr=el('tr');['Model / condition','Judgment agreement','Error sensitivity','Detection + type + row','Clean certificate','Decision abstention','Verbatim evidence quotes'].forEach(t=>tr.append(el('th',t)));head.append(tr);table.append(head);const body=el('tbody');for(const run of runs){const m=metricsFor(run),row=el('tr');row.append(el('td',(run.model||run.key||'Unknown')+' · '+(run.condition||'full'),'model-name'));for(const key of ['judgement_accuracy','detection_sensitivity','joint_detection_type_row','clean_specificity','decision_abstention_rate','verified_quote_rate'])row.append(el('td',noValidAnswers(run)?'No valid answers':countedMetric(m[key])));body.append(row);}table.append(body);wrap.append(table);box.append(wrap);box.append(el('p','Each cell shows percentage and numerator / denominator. A clean certificate requires an explicit correct judgment: clean-case abstentions are not true negatives. Quote verification checks observable text provenance, not governing-standard entailment.','chart-caption'));const differences=pilot.paired_differences;if(differences&&Object.keys(differences).length){const d=el('details');d.append(el('summary','Paired company-cluster differences and intervals','small'));reportPanel(d,differences);box.append(d);}}
function diagnosticStatus(box,result){const states=result.statuses||{},ok=number(states.ok)||0,missing=number(states.missing)||0,total=Object.values(states).reduce((a,b)=>a+(number(b)||0),0),errors=total-ok-missing;box.append(el('p','Schema-valid answers '+fmt(ok,0)+' / '+fmt(total,0)+' cohort cases · failed '+fmt(errors,0)+' · not requested / missing '+fmt(missing,0)+'. Missing cases remain in metric denominators.','small'));if(missing)box.append(el('p','The run stopped before the ordered cohort was complete. This partial cohort is not a confirmatory ranking or a random subsample.','notice'));box.append(el('p','Recorded statuses: '+Object.entries(states).map(([key,n])=>key+' '+n).join(' · '),'chart-caption'));}
function renderOutputDiagnostics(){const box=$('output-diagnostics'),raw=reports.raw_output_diagnostic,format=reports.frontier_format_diagnostic;if(!raw&&!format)return;box.append(el('h3','Output and format diagnostics · separate from primary comparisons'));box.append(badge('POST-HOC · UNMATCHED PROTOCOL','pending'));box.append(el('p','These analyses explore whether schema failures or completion limits affect the primary scores. Secondary field extraction and a differently configured frontier rerun do not replace the frozen primary protocol, establish accounting correctness, or support superiority claims.','small muted'));if(raw){const t=el('table'),h=el('tr');['Condition','Strict failures','Complete JSON / cohort','Missing reason','Finish-length complete JSON','Secondary full-label agreement'].forEach(v=>h.append(el('th',v)));const thead=el('thead');thead.append(h);t.append(thead);const body=el('tbody');for(const [condition,row] of Object.entries(raw.conditions||{})){const tr=el('tr');[condition,fmt(row.strict_failure_count,0),fmt(row.complete_json_count,0)+' / '+fmt(raw.n_cases,0),fmt(row.complete_json_missing_reason_count,0),fmt(row.finish_length_with_complete_json_count,0),countedMetric(row.field_level_metrics?.raw_field_unvalidated_full_citation_agreement)].forEach(v=>tr.append(el('td',v)));body.append(tr);}t.append(body);const wrap=el('div',null,'table-wrap');wrap.append(t);box.append(wrap);const d=el('details');d.append(el('summary','Inspect raw-output diagnostic definitions and per-case provenance · REVIEW ONLY','small'));reportPanel(d,raw);box.append(d);}if(format){const condition=format.posthoc_condition||'opus_format_diagnostic',result=format.conditions?.[condition],model=format.diagnostic_manifest?.settings?.model||config.conditions?.opus_direct?.model||'Same frontier model';if(result){const run={...result,condition,model},m=metricsFor(run);box.append(el('h3','Same-frontier format rerun'));diagnosticStatus(box,result);box.append(el('p',format.settings_difference||'Changed JSON schema, reasoning setting, and/or completion budget.','small muted'));box.append(el('p',model+' · full unvalidated citation agreement '+countedMetric(m.unvalidated_full_citation_agreement)+' · 95% company interval '+ci(run)+' · trace API cost '+costLabel(run),'small'));box.append(el('p','This is a post-hoc protocol diagnostic with unmatched settings/budget. Primary scores remain unchanged.','chart-caption'));}const d=el('details');d.append(el('summary','Inspect the separate post-hoc rerun report · REVIEW ONLY','small'));reportPanel(d,format);box.append(d);}}
function renderCheapEvidenceDiagnostic(){const report=reports.cheap_evidence_diagnostic;if(!report)return;const condition=report.posthoc_condition||'qwen8_evidence_diagnostic',result=report.conditions?.[condition],box=$('output-diagnostics');box.append(el('h3','Small-model evidence cascade · separate post-hoc diagnostic'));box.append(badge('POST-HOC · EXTRA METHOD BUDGET','pending'));box.append(el('p',report.settings_difference||'Qwen8 with evidence extraction followed by a decision; two calls instead of the direct baseline. Root model availability failures motivated this diagnostic.','small muted'));if(result){const model=report.diagnostic_manifest?.settings?.model||config.conditions?.qwen8_direct?.model||'Qwen8',run={...result,condition,model},m=metricsFor(run);diagnosticStatus(box,result);box.append(el('p',model+' · full unvalidated citation agreement '+countedMetric(m.unvalidated_full_citation_agreement)+' · 95% company interval '+ci(run)+' · trace API cost '+costLabel(run),'small'));box.append(el('p','Detection + type + row '+countedMetric(m.joint_detection_type_row)+' · decision abstention '+countedMetric(m.decision_abstention_rate)+'. This is not a frozen primary condition or a matched-call-budget comparison.','chart-caption'));}const d=el('details');d.append(el('summary','Inspect the separate small-model evidence diagnostic · REVIEW ONLY','small'));reportPanel(d,report);box.append(d);}
function normalizeFindings(report){
 const source=first(report,'findings','issues','audit_findings','verified_findings');if(source)return entries(source);
 if(report.datasets){const old=report.datasets.asc_snapshot||{},fresh=report.datasets.upstream_usgaap||{},oldCounts=old.counts||{},counts=fresh.counts||{},totals=fresh.numeric_transaction_reconstruction?.totals||{},gold=fresh.gold||{},tiers=gold.citation_tiers||{};return [
 {title:'The checked upstream version differs from the branch snapshots',severity:'verified version difference',description:'ASC snapshot: '+fmt(oldCounts.exam,0)+' cases, '+fmt(oldCounts.companies,0)+' companies, '+fmt(oldCounts.controls,0)+' clean controls. US GAAP upstream: '+fmt(counts.exam,0)+' cases, '+fmt(counts.companies,0)+' companies, '+fmt(counts.controls,0)+' clean controls. Historical feedback cannot be applied to all versions interchangeably.',source:'research/results/dataset_audit.json → datasets.{asc_snapshot,upstream_usgaap}.counts'},
 {title:'Opaque IDs repair direct rule-name leakage; numerical evidence still needs controls',severity:'remaining limitation',description:'Rule-name tokens in IDs: '+fmt(old.leakage?.exam_rule_id_tokens,0)+' in the snapshot and '+fmt(fresh.leakage?.exam_rule_id_tokens,0)+' upstream. Signed transaction components reconstruct the original clean value in '+fmt(totals.components_sum_to_original,0)+' / '+fmt(totals.numeric_cases,0)+' upstream numerical cases. This count preserves partial evidence coverage.',source:'research/results/dataset_audit.json → leakage; numeric_transaction_reconstruction.totals'},
 {title:'Linkbase membership does not validate the governing paragraph',severity:'accounting review required',description:fmt(gold.citable_n,0)+' upstream cases are marked citable. '+fmt(tiers['linkbase-verified'],0)+' have strict taxonomy-reference membership; '+fmt(tiers['expert-authored-UNVALIDATED'],0)+' remain expert-authored-UNVALIDATED. No independent governing-paragraph adjudication is inferred.',source:'research/results/dataset_audit.json → datasets.upstream_usgaap.gold'}
 ];}return [];
}
function finding(container,item){const title=first(item,'title','name','finding','id','key')||'Verified artifact finding';const severity=first(item,'severity','priority','status')||'';const div=el('article',null,'finding '+(/critical|high|block/i.test(severity)?'critical':''));append(div,el('h3',title),el('p',first(item,'description','summary','detail','message')||''));const evidence=first(item,'evidence','observations','result','metrics');if(evidence!==null)div.append(el('pre',typeof evidence==='string'?evidence:json(evidence),'provenance'));const source=first(item,'source','sources','provenance','file','paths','references');if(source!==null)div.append(el('p','Source: '+(typeof source==='string'?source:json(source)),'provenance'));if(severity)div.prepend(badge(severity,/critical|high|block/i.test(severity)?'failed':'pending'));container.append(div);}
function renderFindings(){for(const [name,report] of [['dataset',dataset],['pipeline',pipeline]]){const container=$(name+'-findings');const items=normalizeFindings(report);if(items.length)items.forEach(item=>finding(container,item));else container.append(el('div',reports[name]?'Findings are available in the source report below.':'Review artifact pending.','empty'));reportPanel($(name+'-details'),reports[name]);}const legacy=reports.legacy_offline;if(legacy){const m=legacy.conditions?.legacy_local_offline?.metrics||{},abstain=m.decision_abstention_rate,detect=m.detection_sensitivity,full=m.unvalidated_full_citation_agreement;finding($('pipeline-findings'),{title:'Offline legacy pipeline transfer diagnostic',severity:'interface limitation',description:'Decision abstention '+fmt(abstain?.numerator,0)+' / '+fmt(abstain?.denominator,0)+'; detection '+fmt(detect?.numerator,0)+' / '+fmt(detect?.denominator,0)+'; full unvalidated label agreement '+fmt(full?.numerator,0)+' / '+fmt(full?.denominator,0)+'. The old parser expects different evidence syntax; this is an interface/coverage diagnostic, separate from paid model comparisons.',source:'research/artifacts/pilot/legacy_local_offline_metrics.json'});const d=el('details');d.append(el('summary','Inspect the offline transfer diagnostic','small'));reportPanel(d,legacy);$('pipeline-findings').append(d);}}
function renderDemo(){const value=reports.evidence_demo;if(!value){$('evidence-demo').append(el('div','Evidence-acquisition demonstration pending. This section does not imply a measured model advantage.','empty'));return;}const status=first(value,'experiment_type','status','label','claim_status')||'Algorithmic demonstration';const box=$('evidence-demo');box.append(badge(status,'pending'));box.append(el('p',value.disclaimer||'This prototype illustrates evidence selection under a budget. Its output is separate from the citation pilot and does not establish fraud-detection validity.','small muted'));const table=el('table'),head=el('thead'),h=el('tr');['Deterministic policy','Budget units','Cases','Supported decision','Mean spent','Abstention'].forEach(t=>h.append(el('th',t)));head.append(h);table.append(head);const body=el('tbody');for(const row of entries(value.results)){const tr=el('tr');[row.policy,fmt(row.budget,0),fmt(row.case_count,0),percent(row.supported_decision_rate),fmt(row.mean_spent,2),percent(row.abstention_rate)].forEach(t=>tr.append(el('td',t)));body.append(tr);}table.append(body);const wrap=el('div',null,'table-wrap');wrap.append(table);box.append(wrap);box.append(el('p','Rates describe unvalidated generated contractual criteria in a deterministic software demonstration. Budget units are arbitrary and are not API dollars. No LLM was evaluated here.','chart-caption'));const details=el('details');details.append(el('summary','Inspect prototype report and acquisition traces','small'));reportPanel(details,value);box.append(details);}
function renderParserRepair(){
 const old=reports.legacy_offline,adapted=reports.legacy_adapted,verified=reports.legacy_verified_citation;if(!old||!adapted)return;
 const before=old.conditions?.legacy_local_offline,after=adapted.conditions?.legacy_local_adapted,guarded=verified?.conditions?.legacy_local_adapted_verified_citation;if(!before||!after)return;
 const conditions=[before,after],labels=['Old parser','Adapted parser'];if(guarded){conditions.push(guarded);labels.push('Adapted + citation guard');}
 const box=$('parser-repair');box.append(el('h3','Before → after: evidence parser compatibility and citation guard'));
 box.append(el('p','A software repair accepts the current signed component narrative format. A further guard suppresses unverified candidate citations. These identical development cases still contain synthetic evidence and unvalidated gold; this is a compatibility diagnostic, separate from paid LLM comparisons.','small muted'));
 const table=el('table'),head=el('thead'),tr=el('tr');['Diagnostic',...labels].forEach(t=>tr.append(el('th',t)));head.append(tr);table.append(head);const body=el('tbody');
 for(const [label,key] of [['Error detection','detection_sensitivity'],['Detection + type + row','joint_detection_type_row'],['Full unvalidated citation agreement','unvalidated_full_citation_agreement'],['Decision abstention','decision_abstention_rate'],['Citation abstention','citation_abstention_rate']]){const line=el('tr');line.append(el('td',label));for(const condition of conditions){line.append(el('td',countedMetric(condition.metrics?.[key])));}body.append(line);}
 table.append(body);const wrap=el('div',null,'table-wrap');wrap.append(table);box.append(wrap);
 const latest=guarded||after,clean=latest.cases?.filter(c=>c.gold_judgement==='Correct')||[],abstained=clean.filter(c=>c.prediction?.judgement==='abstain');box.append(el('p','Latest parser on clean controls: '+abstained.length+' / '+clean.length+' abstained. An abstention is not a correct-statement certificate. API model calls: zero.','chart-caption'));
 if(guarded)box.append(el('p','The final guard retains candidate hints for later reasoning but emits no governing citation without a separate applicability verification. It does not create validated citations or improve measured citation agreement.','chart-caption'));
 const d=el('details');d.append(el('summary','Inspect local compatibility and citation-guard reports','small'));reportPanel(d,{adapted,verified});box.append(d);
}
function renderSec(){const value=reports.sec,box=$('sec-check');if(!value){box.append(el('div','Independent SEC value check pending.','empty'));return;}const c=value.counts||{},cards=el('div',null,'cards');metric(cards,'Numeric rows checked',fmt(c.numeric_rows,0),fmt(c.tables,0)+' clean source tables for the eight pilot companies.');metric(cards,'Exact signed matches',fmt(c.exact_signed_match,0),'A source-value match, not a finding about the governing standard.');metric(cards,'Magnitude-only matches',fmt(c.magnitude_only_match,0),'Signs require separate validation.');metric(cards,'Value mismatches',fmt(c.value_mismatch,0),fmt(c.derived_or_unmapped,0)+' derived/unmapped; '+fmt(c.no_same_period_fact,0)+' without a same-period fact.');box.append(cards);box.append(el('p',value.scope,'small muted'));if(value.limitations)box.append(el('p',value.limitations.join(' '),'small muted'));const details=el('details');details.append(el('summary','Inspect match examples, filing links and SEC snapshot hashes','small'));reportPanel(details,value);box.append(details);const accessions=reports.sec_accessions;if(accessions){const counts=accessions.counts||{};finding(box,{title:'Individual SEC cell matches do not establish one consistent filing',severity:'verified provenance limitation',description:fmt(counts.tables_with_no_common_accession_for_matched_rows,0)+' / '+fmt(counts.tables_with_any_matched_rows,0)+' checked tables have no single accession supporting all matched row values. '+fmt(counts.cells_with_conflicting_same_period_values,0)+' / '+fmt(counts.same_period_candidate_cells,0)+' same-period candidate cells have conflicting reported values. This is a flattened-companyfacts limitation; it does not imply all values are false.',source:'research/results/sec_accession_consistency.json'});const d=el('details');d.append(el('summary','Inspect accession consistency witnesses','small'));reportPanel(d,accessions);box.append(d);}}
function renderRelated(){const value=reports.related_work;if(!value){$('related-work').append(el('div','Related-work verification pending.','empty'));return;}const rows=entries(Array.isArray(value)?value:first(value,'works','papers','references','resources'));if(!rows.length){reportPanel($('related-work'),value);return;}for(const row of rows){const box=el('div',null,'source');const title=first(row,'title','name','id','key')||'Related work';const url=first(row,'primary_url','url','paper_url','source_url');append(box,el('strong',title),el('div',first(row,'status','verification_status')||'Verification status not recorded','small muted'));if(url)box.append(link(url,'Primary source'));const detail=first(row,'positioning','contribution','summary','novelty_overlap','relevance','notes');if(detail)box.append(el('p',typeof detail==='string'?detail:json(detail),'small'));$('related-work').append(box);}const details=el('details');details.append(el('summary','Venue dates, inaccessible prior chats and verification details','small'));reportPanel(details,value);$('related-work').append(details);}
function renderSources(){for(const row of DATA.provenance){const div=el('div',null,'source');append(div,el('strong',row.path),document.createTextNode(' '),badge(row.status,row.status==='loaded'?'good':row.status==='invalid'?'failed':'pending'));if(row.sha256)div.append(el('code','SHA-256 '+row.sha256+' · '+fmt(row.bytes,0)+' bytes'));if(row.error)div.append(el('p',row.error,'small'));$('sources').append(div);}}
const cases=DATA.cases.rows||[];let selectedCase=null;
function filterControl(id,options){const select=$(id);select.replaceChildren(el('option','All'));select.firstChild.value='';for(const value of [...new Set(options.filter(Boolean))].sort()){const opt=el('option',value);opt.value=value;select.append(opt);}}
function renderCases(){filterControl('company-filter',cases.map(c=>c.metadata?.company));filterControl('model-filter',cases.flatMap(c=>(c.predictions||[]).map(p=>p.model)));filterControl('condition-filter',cases.flatMap(c=>(c.predictions||[]).map(p=>p.condition)));$('case-sample').textContent=fmt(DATA.cases.displayed_cases,0)+' of '+fmt(DATA.cases.available_cases,0)+' cases embedded. '+DATA.cases.case_selection;['company-filter','model-filter','condition-filter','search-filter'].forEach(id=>$(id).addEventListener('input',updateCases));updateCases();}
function updateCases(){const company=$('company-filter').value,model=$('model-filter').value,condition=$('condition-filter').value,query=$('search-filter').value.toLowerCase();const filtered=cases.filter(c=>(!company||c.metadata?.company===company)&&(!model||(c.predictions||[]).some(p=>p.model===model))&&(!condition||(c.predictions||[]).some(p=>p.condition===condition))&&(!query||[c.sample_id,c.metadata?.company,c.metadata?.statement_type].join(' ').toLowerCase().includes(query)));$('case-count').textContent=filtered.length+' matching review cases';$('case-list').replaceChildren();if(!filtered.length){$('case-list').append(el('div','No matching review cases.','empty'));$('case-detail').replaceChildren();return;}if(!filtered.some(c=>c.sample_id===selectedCase))selectedCase=filtered[0].sample_id;for(const c of filtered){const b=el('button',null,'case-item '+(selectedCase===c.sample_id?'active':''));b.type='button';b.setAttribute('aria-pressed',String(selectedCase===c.sample_id));append(b,el('div',c.metadata?.company||'Unknown company','case-company'),el('div',c.sample_id,'case-id'),el('div',(c.metadata?.fiscal_year||'')+' · '+(c.metadata?.statement_type||'')+' · '+(c.predictions?.length||0)+' predictions','case-meta'));b.addEventListener('click',()=>{selectedCase=c.sample_id;updateCases();});$('case-list').append(b);}renderCase(filtered.find(c=>c.sample_id===selectedCase));}
function textBox(title,text){const box=el('div',null,'text-box');return append(box,el('h3',title),el('pre',text||'Not available.'));}
function renderCase(c){const panel=$('case-detail');panel.replaceChildren();append(panel,el('h3',c.metadata?.company||'Case review','case-title'),el('div',c.sample_id,'provenance'),el('p','Inference-visible fields are displayed below. Template transaction evidence is synthetic; source provenance must be checked before scientific use.','small muted'));append(panel,append(el('div',null,'evidence-grid'),textBox('Statement given to the model',c.statement_text),textBox('Transaction evidence given to the model',c.transaction_data)));panel.append(el('h3','Recorded predictions'));const model=$('model-filter').value,condition=$('condition-filter').value,predictions=(c.predictions||[]).filter(p=>(!model||p.model===model)&&(!condition||p.condition===condition));if(!predictions.length)panel.append(el('div','No recorded prediction in the loaded pilot artifacts.','empty'));for(const p of predictions){const div=el('div',null,'prediction');append(div,el('strong',(p.model||'Unknown model')+' · '+(p.condition||'full')),el('pre',json(p)));panel.append(div);}const gold=el('details',null,'gold');append(gold,el('summary','Reveal unvalidated answer key · REVIEW ONLY'),el('p','This hidden gold is never an input to evaluation inference. It is shown here only for manual inspection. A citable/linkbase-verified flag is a dataset annotation, not proof of normative applicability.','small'),el('pre',c.gold_review_only?json(c.gold_review_only):'Answer key missing.'));panel.append(gold);}
function initDashboard(){renderSummary();renderModels();renderDecisionMetrics();renderOutputDiagnostics();renderCheapEvidenceDiagnostic();renderFindings();renderParserRepair();renderSec();renderDemo();renderRelated();renderSources();renderCases();document.querySelectorAll('.sidebar nav a').forEach(a=>a.addEventListener('click',()=>{document.querySelectorAll('.sidebar nav a').forEach(n=>n.classList.remove('active'));a.classList.add('active');}));$('download-data').addEventListener('click',()=>{const blob=new Blob([json(DATA)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=el('a');a.href=url;a.download='research-review-snapshot.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
function initSlides(){
 const slides=[...document.querySelectorAll('.slide')];let i=0;function show(index){i=Math.max(0,Math.min(slides.length-1,index));slides.forEach((s,j)=>s.classList.toggle('active',i===j));$('slide-counter').textContent=(i+1)+' / '+slides.length;document.title='Financial audit research · '+(i+1)+' / '+slides.length;}
 const companies=summaryValue('companies','n_companies','company_count'),ncompanies=Array.isArray(companies)?companies.length:number(companies),ncases=summaryValue('exam','cases','n_cases','total_cases','exam_count','sample_count')??DATA.cases.available_cases;
 metric($('slide-metrics'),'Audited upstream cases',fmt(ncases,0),fmt(ncompanies,0)+' companies; label validity is a separate question.');metric($('slide-metrics'),'Pilot cases / companies',fmt(pilot.n_cases??manifest.n_cases,0)+' / '+fmt(pilot.n_companies??manifest.selection?.n_companies,0),'Cases within a company are dependent.');metric($('slide-metrics'),'Citation applicability','Unvalidated','Human accounting adjudication remains required.');metric($('slide-metrics'),'Pilot comparison',reports.pilot?'Recorded':'Pending','See the dashboard for denominators, costs, failures and confidence intervals.');
 const findings=normalizeFindings(dataset);findings.slice(0,3).forEach(f=>finding($('slide-findings'),f));if(!findings.length)$('slide-findings').append(el('p','No verified findings loaded. Review the dashboard source reports.','muted'));
 const local=reports.legacy_verified_citation?.conditions?.legacy_local_adapted_verified_citation?.metrics||reports.legacy_adapted?.conditions?.legacy_local_adapted?.metrics;if(local)$('slide-repair').textContent='Verified compatibility repair on the same development cases: detection '+fmt(local.detection_sensitivity?.numerator,0)+' / '+fmt(local.detection_sensitivity?.denominator,0)+'; joint type + row '+fmt(local.joint_detection_type_row?.numerator,0)+' / '+fmt(local.joint_detection_type_row?.denominator,0)+'. Unverified governing citations now abstain. Full citation agreement remains '+fmt(local.unvalidated_full_citation_agreement?.numerator,0)+' / '+fmt(local.unvalidated_full_citation_agreement?.denominator,0)+'; clean controls abstain. This is a parser transfer diagnostic, not accounting validation.';
 const runs=runRows();for(const r of runs.slice(0,6)){const tr=el('tr');append(tr,el('td',first(r,'model','model_id','model_name','name','key')||'Unknown'),el('td',first(r,'condition','ablation')||'full'),el('td',first(r,'status','state')||'Not recorded'),el('td',noValidAnswers(r)?'No valid answers':countedMetric(metricsFor(r).unvalidated_full_citation_agreement)),el('td',costLabel(r)));$('slide-models').append(tr);}if(!runs.length){const tr=el('tr'),td=el('td','Pilot artifact pending. No model score asserted.');td.colSpan=5;tr.append(td);$('slide-models').append(tr);}
 const diagnostics=[];for(const [name,label] of [['frontier_format_diagnostic','Same-frontier format followup'],['cheap_evidence_diagnostic','Qwen8 evidence followup']]){const report=reports[name],condition=report?.posthoc_condition,result=report?.conditions?.[condition];if(!result)continue;const states=result.statuses||{};diagnostics.push(label+': '+countedMetric(result.metrics?.unvalidated_full_citation_agreement)+' full-label agreement; '+(states.ok||0)+' valid, '+(states.missing||0)+' not requested / missing.');}$('slide-posthoc').textContent=diagnostics.length?'Separate post-hoc diagnostics (unmatched protocol/budget): '+diagnostics.join(' '):'Post-hoc followups are not part of the frozen primary comparison.';
 const sources=DATA.provenance.filter(p=>p.status==='loaded');$('slide-source-list').textContent=sources.map(p=>p.path+' · SHA-256 '+p.sha256.slice(0,12)).join('\n')||'Source report artifacts not available.';
 $('prev-slide').addEventListener('click',()=>show(i-1));$('next-slide').addEventListener('click',()=>show(i+1));document.addEventListener('keydown',e=>{if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(i+1);}if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(i-1);}if(e.key==='Home')show(0);if(e.key==='End')show(slides.length-1);});show(0);
}
if(document.body.dataset.view==='slides')initSlides();else initDashboard();
})();
"""

DASHBOARD_BODY = r"""
<div class="shell"><aside class="sidebar"><div class="brand-mark" aria-hidden="true">FA</div><div class="brand">Financial Audit<br>Research Review</div><div class="brand-sub">Evidence, validity &amp; model cost</div><nav aria-label="Dashboard sections"><a href="#overview" class="active"><span class="nav-num">01</span>Overview</a><a href="#models"><span class="nav-num">02</span>Model comparisons</a><a href="#validity"><span class="nav-num">03</span>Validity audit</a><a href="#cases"><span class="nav-num">04</span>Case explorer</a><a href="#evidence"><span class="nav-num">05</span>Evidence budget</a><a href="#provenance"><span class="nav-num">06</span>Sources &amp; provenance</a></nav><div class="foot">Offline review artifact<br>Gold is hidden by default<br>No external dependencies</div></aside><main class="main">
<section id="overview"><div class="topline"><div><div class="eyebrow">Research checkpoint · October 2026</div><h1>Measure validity before model gains.</h1><p class="lede">An inspectable record of the dataset audit, the cleaned pipeline, and a bounded model pilot. Read every score with its denominator, request failures, cost, and scope.</p></div><span class="badge pending">PRELIMINARY · REVIEW ONLY</span></div><div class="notice"><strong>Scientific status:</strong> Answer-key agreement is an engineering diagnostic. The key has not established paragraph applicability through independent accounting adjudication. No score here demonstrates that a smaller model matches a frontier model on valid audit judgment; API failures and missing artifacts remain explicit.</div><div id="metrics" class="cards" aria-label="Research summary"></div></section>
<section class="section" id="models"><div class="section-header"><div><h2>Model comparisons</h2><p>Full citation agreement against the unvalidated pilot key; all applicable citable cases remain in the denominator, including failures.</p></div><button class="button" id="download-data" type="button">Download review snapshot</button></div><div class="panel"><div class="table-wrap"><table><caption class="sr-only">Pilot model comparisons with schema-valid answers, cohort cases, citation agreement, denominator, confidence interval, API cost and failures</caption><thead><tr><th scope="col">Model</th><th scope="col">Condition</th><th scope="col">Status</th><th scope="col">Valid / cohort</th><th scope="col">Full label agreement</th><th scope="col">Citable n</th><th scope="col">95% CI</th><th scope="col">API cost</th><th scope="col">Errors / missing</th></tr></thead><tbody id="model-body"></tbody></table></div><div id="chart" aria-label="Citation label agreement chart"></div><div id="decision-metrics" style="margin-top:24px"></div><div id="output-diagnostics" style="margin-top:24px"></div><p class="chart-caption">These are descriptive development-pilot results from eight purposively selected companies. Company-cluster intervals are unstable at n = 8 and do not describe a representative company population. A valid method comparison requires paired held-out cases and company-level uncertainty. Request errors count as unsuccessful outcomes in applicable report denominators, while remaining separate from completed model answers. Providers with no valid completed answers are not plotted or assigned a model accuracy; their raw protocol counts remain in the source report. Confidence intervals are displayed only when supplied by the report.</p><details><summary class="small">Inspect full pilot report · includes scoring annotations · REVIEW ONLY</summary><div id="pilot-details"></div></details></div></section>
<section class="section" id="validity"><div class="section-header"><div><h2>What the audit actually verifies</h2><p>Code and artifact findings remain separate from reported historical claims.</p></div></div><div class="two"><div class="panel"><h3>Dataset &amp; generator</h3><div class="findings" id="dataset-findings"></div><details><summary class="small">Full dataset audit</summary><div id="dataset-details"></div></details></div><div class="panel"><h3>Pipeline &amp; evaluation</h3><div class="findings" id="pipeline-findings"></div><details><summary class="small">Full pipeline audit</summary><div id="pipeline-details"></div></details></div></div><div class="panel" id="parser-repair" style="margin-top:19px"></div><div class="panel" id="sec-check" style="margin-top:19px"><h3>Independent SEC value check</h3></div></section>
<section class="section" id="cases"><div class="section-header"><div><h2>Case explorer</h2><p id="case-sample"></p></div><span class="badge pending">ANSWER KEY IS REVIEW ONLY</span></div><div class="filters"><label class="filter">Company<select id="company-filter" aria-label="Filter cases by company"></select></label><label class="filter">Model<select id="model-filter" aria-label="Filter cases by model"></select></label><label class="filter">Condition<select id="condition-filter" aria-label="Filter cases by condition"></select></label><label class="filter">Case search<input id="search-filter" type="search" placeholder="Company, case ID, statement" aria-label="Search cases"></label></div><p id="case-count" class="small muted" aria-live="polite"></p><div class="case-layout"><div class="case-list" id="case-list" aria-label="Review cases"></div><div class="panel case-detail" id="case-detail"></div></div></section>
<section class="section" id="evidence"><div class="section-header"><div><h2>Evidence acquisition under a budget</h2><p>A prototype for the proposed contribution; evaluation of its realism and benefit is pending.</p></div></div><div class="panel" id="evidence-demo"></div></section>
<section class="section" id="provenance"><div class="section-header"><div><h2>Sources &amp; provenance</h2><p>Local artifact hashes identify the exact snapshot used to build this review.</p></div></div><div class="two"><div class="panel"><h3>Verified source reports</h3><div id="sources"></div></div><div class="panel"><h3>Related work verification</h3><div id="related-work"></div></div></div></section><footer class="footer"><span id="built-at"></span><p>The dashboard contains no API keys, makes no network requests, and treats all case text as inert text. Review gold is not an inference input. This file is not a benchmark release or evidence of submission readiness.</p></footer></main></div>
"""

SLIDES_BODY = r"""
<main class="slides-body"><section class="slide active"><div class="eyebrow">Professor briefing · 10 minutes · October 2026</div><h1>From citation accuracy to valid audit evidence.</h1><p class="lede">A research reset built on an independently inspected dataset and codebase, with a bounded pilot and an explicit route to an open benchmark contribution.</p><div class="notice"><strong>Present status:</strong> Engineering findings and legacy label agreement are reviewable. Accounting applicability and a fair frontier comparison remain unvalidated.</div><div class="slide-footer"><span>Research checkpoint · preliminary</span><span>1 / 8 · 1 minute</span></div></section>
<section class="slide"><div class="eyebrow">01 · What we have</div><h2>Useful infrastructure. Limited scientific claims.</h2><div class="cards" id="slide-metrics"></div><p id="slide-repair" class="small muted" style="margin-top:25px"></p><p class="lede" style="margin-top:32px">A small company sample is suitable for feasibility and cost control. It cannot by itself establish broad generalization across industries.</p><div class="slide-footer"><span>Dataset source count is distinct from label validity.</span><span>2 / 8 · 1 minute</span></div></section>
<section class="slide"><div class="eyebrow">02 · Independently checked</div><h2>Audit the shortcuts before optimizing the solver.</h2><div class="findings" id="slide-findings" style="margin-top:25px"></div><div class="slide-footer"><span>Source files and exact counts appear in the dashboard.</span><span>3 / 8 · 2 minutes</span></div></section>
<section class="slide"><div class="eyebrow">03 · The actual pilot</div><h2>Agreement is measurable. Applicability needs review.</h2><div class="table-wrap" style="margin-top:30px"><table><thead><tr><th>Model</th><th>Condition</th><th>Status</th><th>Full label agreement</th><th>API cost</th></tr></thead><tbody id="slide-models"></tbody></table></div><p id="slide-posthoc" class="small muted" style="margin-top:18px"></p><div class="notice">The full dashboard records denominators, confidence intervals, errors, and metric definitions. Failed requests remain unsuccessful in applicable metric denominators and are not completed model answers. No superiority claim is supported by key agreement alone.</div><div class="slide-footer"><span>Pilot results are feasibility evidence.</span><span>4 / 8 · 1 minute</span></div></section>
<section class="slide"><div class="eyebrow">04 · Proposed benchmark contribution</div><h2>Audit conclusions must follow an evidence chain.</h2><ul><li>Cases combine corroborating and contradicting evidence across documents; no single template clue should reveal the label.</li><li>Record a minimally sufficient evidence graph, alternative explanations, and acceptable citations with explicit applicability rationale.</li><li>Give agents paid evidence actions and a fixed budget; score the conclusion and the investigation path.</li></ul><div class="notice">Research design proposal. Novelty must be positioned against the verified related work; realism and annotations require independent accountant review.</div><div class="slide-footer"><span>Hidden gold remains outside every inference interface.</span><span>5 / 8 · 1 minute</span></div></section>
<section class="slide"><div class="eyebrow">05 · Proposed economical method</div><h2>Spend model capacity where evidence is ambiguous.</h2><ul><li>Run deterministic arithmetic and evidence consistency checks first; never select the answer using rule IDs.</li><li>Use small models to extract claims and rank retrieved governing paragraphs. Verify the paragraph against the specific error and evidence.</li><li>Allow calibrated abstention. Compare this cascade with one verified frontier reference and cheap/open-weight baselines on the same blind cases.</li></ul><div class="slide-footer"><span>Measure accuracy, calibrated abstention, evidence coverage, action cost and latency.</span><span>6 / 8 · 1 minute</span></div></section>
<section class="slide"><div class="eyebrow">06 · Feasible route to December</div><h2>Freeze validity before the final model comparison.</h2><ul><li><strong>October:</strong> accountant adjudication, citation policy, company-disjoint splits, source provenance and leakage tests; freeze a small pilot.</li><li><strong>November:</strong> budgeted evidence cases, paired ablations, one frontier baseline, cheap model cascade; preregister exclusions and primary metrics.</li><li><strong>December:</strong> held-out evaluation, company-level uncertainty, error analysis, dataset/code documentation and a reproducible submission draft.</li></ul><p class="small muted">Submission by December is a planning target. Venue eligibility, deadlines and acceptance must be checked independently; acceptance cannot be promised.</p><div class="slide-footer"><span>Release only material with established provenance and redistribution rights.</span><span>7 / 8 · 1 minute</span></div></section>
<section class="slide"><div class="eyebrow">07 · Concrete decisions</div><h2>Three gates before a publishable claim.</h2><ul><li>Can independent accountants identify the error and governing citation from only the permitted evidence?</li><li>Does performance survive template, company, clean-case and evidence-removal controls?</li><li>Does the economical method improve the paired accuracy–cost tradeoff on a held-out test, with uncertainty?</li></ul><pre id="slide-source-list" class="provenance" style="white-space:pre-wrap"></pre><div class="slide-footer"><span>Open the dashboard to inspect cases and recorded artifacts.</span><span>8 / 8 · 1 minute</span></div></section><div class="slide-controls"><button id="prev-slide" type="button">Previous</button><span id="slide-counter" aria-live="polite"></span><button id="next-slide" type="button">Next</button><a class="button" href="dashboard/dist/index.html">Open dashboard</a></div></main>
"""


def page(title: str, body: str, payload: dict[str, Any], view: str) -> str:
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
            "script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
            "connect-src 'none'; base-uri 'none'; form-action 'none'\">"
            f"<title>{title}</title><style>{CSS}</style></head>"
            f"<body data-view=\"{view}\">{body}"
            f"<script id=\"research-data\" type=\"application/json\">{embedded_json(payload)}</script>"
            f"<script>{JS}</script></body></html>\n")


def build(root: Path, output: Path, case_limit: int) -> dict[str, Any]:
    reports, provenance = load_sources(root)
    costs = condition_costs(root, reports.get("pilot", {}))
    costs.update(condition_costs(root, reports.get("frontier_format_diagnostic", {}),
                                 "research/artifacts/pilot/frontier_format_diagnostic"))
    costs.update(condition_costs(root, reports.get("cheap_evidence_diagnostic", {}),
                                 "research/artifacts/pilot/qwen8_evidence_diagnostic"))
    payload = {"schema_version": "1.0", "built_at": datetime.now(ZoneInfo("America/Vancouver")).isoformat(timespec="seconds"),
               "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "review_only": True, "reports": reports, "provenance": provenance,
               "condition_costs": costs, "global_cost": global_cost(root),
               "cases": build_cases(root, reports.get("pilot", {}), case_limit,
                                    {name: reports[name] for name in
                                     ("frontier_format_diagnostic", "cheap_evidence_diagnostic")
                                     if name in reports})}
    linked_paths = ["research/artifacts/pilot/public_inputs.jsonl",
                    "research/artifacts/pilot/scoring_only.jsonl"]
    linked_paths.extend(payload["cases"]["prediction_files"])
    if payload["global_cost"] is not None:
        linked_paths.append("research/artifacts/api_ledger.jsonl")
    if "opus_format_diagnostic" in costs:
        linked_paths.append("research/artifacts/pilot/frontier_format_diagnostic/predictions.jsonl")
    if "qwen8_evidence_diagnostic" in costs:
        linked_paths.append("research/artifacts/pilot/qwen8_evidence_diagnostic/predictions.jsonl")
    for relative in sorted(set(linked_paths)):
        path = root / relative
        if path.exists():
            raw = path.read_bytes()
            provenance.append({"name": "review join", "path": relative, "status": "loaded",
                               "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    if re.search(r"sk-or-v1-[A-Za-z0-9]{20,}", json.dumps(payload)):
        raise ValueError("Refusing to embed an apparent API credential in a review artifact")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page("Financial audit research review", DASHBOARD_BODY, payload, "dashboard"), encoding="utf-8")
    (root / "research/slides.html").write_text(page("Financial audit research briefing", SLIDES_BODY, payload, "slides"), encoding="utf-8")
    return {"dashboard": str(output), "slides": str(root / "research/slides.html"),
            "embedded_cases": len(payload["cases"]["rows"]), "reports": provenance}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case-limit", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.case_limit <= 1000:
        parser.error("--case-limit must be between 1 and 1000")
    root = args.root.resolve()
    output = args.output or root / "research/dashboard/dist/index.html"
    print(json.dumps(build(root, output, args.case_limit), indent=2))


if __name__ == "__main__":
    main()
