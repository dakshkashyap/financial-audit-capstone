#!/usr/bin/env python3
"""Render a static comparison table from recorded result strings, without rescoring.

The input is a local research/results/comparison_table.json artifact. Unknown
cells remain dashes. All display text is HTML-escaped and no external resources
or scripts are loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = [
    ("model", "Model"), ("setup", "Setup"), ("general", "General"),
    ("error_type", "Error Type"), ("error_entry", "Error Entry"),
    ("topic", "Topic"), ("subtopic", "Subtopic"),
    ("full_citation", "Full Citation"), ("input_tokens", "Input Tokens"),
    ("output_tokens", "Output Tokens"), ("latency", "Latency"),
]
CSS = """
:root{color-scheme:dark;--bg:#0d111b;--panel:#141b29;--line:#334052;--text:#e5ebf5;--muted:#a4b0c2;--blue:#9fc0ff;--amber:#e8c583}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}.wrap{max-width:1840px;margin:0 auto;padding:36px 42px 30px}.eyebrow{color:var(--blue);font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}h1{font-size:31px;letter-spacing:-.025em;line-height:1.2;margin:8px 0 9px}h2{font-size:16px;font-weight:650;margin:0 0 7px}.subtitle{font-size:13px;color:var(--muted);margin:0;max-width:1250px}.top{display:flex;align-items:flex-start;justify-content:space-between;gap:28px}.tag{white-space:nowrap;padding:5px 10px;border:1px solid #685833;border-radius:5px;color:var(--amber);font-size:10px;font-weight:700;margin-top:9px}.section{margin-top:25px}.section-note{color:var(--muted);font-size:12px;margin:0 0 12px}.table-wrap{border:1px solid var(--line);border-radius:7px;overflow:auto;background:var(--panel)}table{border-collapse:collapse;width:100%;table-layout:fixed;min-width:1380px}th,td{padding:13px 11px;border-right:1px solid #273345;border-bottom:1px solid var(--line);text-align:center;vertical-align:middle}th:last-child,td:last-child{border-right:0}tr:last-child td{border-bottom:0}th{background:#1b2433;color:#d6dfed;font-size:11px;font-weight:650;white-space:normal}td{font-size:13px;font-variant-numeric:tabular-nums;white-space:pre-line;overflow-wrap:anywhere}td:nth-child(1),td:nth-child(2){text-align:left}td:nth-child(1){font-weight:650}td:nth-child(2){color:#bcc9dd;font-size:12px}th:nth-child(1){width:14%}th:nth-child(2){width:15%}th:nth-child(3),th:nth-child(4),th:nth-child(5),th:nth-child(6),th:nth-child(7),th:nth-child(8){width:8%}th:nth-child(9),th:nth-child(10){width:8%}th:nth-child(11){width:7%}tbody tr:nth-child(even){background:#17202e}.notes{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:15px;margin-top:24px}.notes p{margin:6px 0}.notes strong{color:#d4deed}.provenance{color:#8290a5;font-size:10px;margin-top:13px;overflow-wrap:anywhere}.badge{font-size:10px;color:var(--amber);font-weight:600;padding-left:10px}.muted{color:var(--muted)}@media(max-width:700px){.wrap{padding:23px 17px}.top{display:block}h1{font-size:26px}.tag{display:inline-block}.section{margin-top:24px}}@media print{body{background:white;color:black}.wrap{padding:0}th,td{border-color:#9aa4b3;color:black;background:white!important}.notes,.subtitle,.section-note,.provenance{color:#444}.table-wrap{background:white}.tag{color:#654300}table{min-width:0}h2{break-after:avoid}.section{break-inside:avoid}@page{size:landscape;margin:10mm}}
"""


def escape(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, dict):
        value = value.get("display", value.get("formatted", value.get("value", "—")))
    return html.escape(str(value), quote=True)


def rows_from(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get("rows"), list):
            return value["rows"]
    return []


def section(title: str, note: str, rows: list[dict[str, Any]], badge: str = "",
            columns: list[tuple[str, str]] | None = None, table_class: str = "") -> str:
    if not rows:
        return ""
    columns = columns or COLUMNS
    header = "".join(f'<th scope="col">{escape(label)}</th>' for _, label in columns)
    cells = []
    for row in rows:
        display = row.get("display", row)
        cells.append("<tr>" + "".join(f"<td>{escape(display.get(key))}</td>" for key, _ in columns) + "</tr>")
    tag = f'<span class="badge">{escape(badge)}</span>' if badge else ""
    return (f'<section class="section"><h2>{escape(title)}{tag}</h2><p class="section-note">{escape(note)}</p>'
            f'<div class="table-wrap"><table class="{escape(table_class)}"><thead><tr>{header}</tr></thead><tbody>{"".join(cells)}</tbody></table></div></section>')


def offline_display(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        display = {"setup": row.get("setup"), "api_cost_usd": "$0" if row.get("api_cost_usd") == 0 else row.get("api_cost_usd")}
        for key in ("detection_sensitivity", "joint_detection_type_row", "unvalidated_full_citation_agreement",
                    "decision_abstention_rate", "citation_abstention_rate"):
            metric = row.get(key, {})
            value = metric.get("value")
            display[key] = (f'{value * 100:.1f}% ({metric["numerator"]}/{metric["denominator"]})'
                            if value is not None else "—")
        output.append(display)
    return output


def build(source: Path, output: Path) -> dict[str, Any]:
    raw = source.read_bytes()
    data = json.loads(raw)
    title = data.get("title", "Financial audit pilot results")
    subtitle = data.get("subtitle", "48 cases · 8 companies · exploratory development sample. Citation scores measure agreement with unvalidated labels.")
    primary = rows_from(data, "primary_rows", "primary")
    posthoc = rows_from(data, "posthoc_rows", "posthoc", "diagnostic_rows")
    offline = rows_from(data, "offline_rows", "offline", "local_rows")
    body = (f'<main class="wrap"><div class="top"><div><div class="eyebrow">Recorded experiments · October 3, 2026</div>'
            f'<h1>{escape(title)}</h1><p class="subtitle">{escape(subtitle)}</p></div>'
            '<div class="tag">PROVISIONAL LABELS · NO SUPERIORITY CLAIM</div></div>')
    body += section("Frozen primary comparison", data.get("primary_note", "General: 48 cases. Error Type / Entry: 32 injected cases. Topic / Subtopic / Full Citation: 16 citable cases. Invalid outputs and failures receive zero credit."), primary)
    body += section("Post-hoc diagnostics", data.get("posthoc_note", "Both runs stopped on provider errors. Settings or method budgets differ from the primary conditions; these partial ordered cohorts do not establish a model ranking."), posthoc, "PARTIAL · SEPARATE PROTOCOLS")
    offline_columns = [("setup", "Setup"), ("detection_sensitivity", "Error Detection"),
                       ("joint_detection_type_row", "Detection + Type + Entry"),
                       ("unvalidated_full_citation_agreement", "Full Citation"),
                       ("decision_abstention_rate", "Decision Abstention"),
                       ("citation_abstention_rate", "Citation Abstention"), ("api_cost_usd", "API Cost")]
    body += section("Offline pipeline repair", data.get("offline_note", "Same 48 inputs; deterministic checks and offline taxonomy only. Abstention is not a clean certificate. Candidate citations require independent applicability verification."), offline_display(offline), "SOFTWARE DIAGNOSTIC", offline_columns, "offline")
    notes = data.get("notes", [])
    if isinstance(notes, dict):
        notes = [f"{key}: {value}" for key, value in notes.items()]
    body += ('<div class="notes"><p><strong>Resource measurements:</strong> Mean tokens sum requested stages per case with complete usage; n is measured cases. Latency sums API request time per attempted case, including errors; it excludes local processing and pacing.</p>'
             '<p><strong>Interpretation:</strong> Citation agreement uses provisional labels. Rate limits invalidate simple speed comparisons. Neither partial followups nor these engineering repairs establish cheap-model superiority.</p>'
             '<details><summary>Full metric definitions and limitations</summary>' +
             "".join(f"<p>{escape(note)}</p>" for note in notes) + '</details></div>')
    digest = hashlib.sha256(raw).hexdigest()
    body += f'<p class="provenance">Source: research/results/comparison_table.json · SHA-256 {digest}<br>Static review artifact. No model calls, hidden-label inference, or rescoring performed by this renderer.</p></main>'
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'">'
            f'<title>{escape(title)}</title><style>{CSS} .offline th:nth-child(n){{width:auto}} .offline th:first-child{{width:28%}} .offline td:nth-child(2){{text-align:center;color:var(--text);font-size:13px}} .offline td:first-child{{font-size:12px}} details{{margin-top:9px}} summary{{cursor:pointer;color:var(--blue);font-size:11px}}</style></head><body>{body}</body></html>\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page)
    return {"output": str(output), "source_sha256": digest, "primary_rows": len(primary), "posthoc_rows": len(posthoc), "offline_rows": len(offline)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "research/results/comparison_table.json")
    parser.add_argument("--output", type=Path, default=ROOT / "research/results/comparison.html")
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
