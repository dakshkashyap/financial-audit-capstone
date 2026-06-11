"""
Stage 1 — Auditor runner.
 
Confirmed settings from author email (Rushi Wang, June 2026):
  TEMPERATURE = 1.0              (paper used 1.0, not 0.0)
  MODELS      = gpt-3.5-turbo-0125, gpt-4-0613  (OpenAI)
              = gemini-2.0-flash, gemini-1.5-pro  (Gemini — free tier)
 
Gemini usage:
  export GEMINI_API_KEY=AIza...
  python main.py --model gemini-2.0-flash --split single_error --n 10
 
OpenAI usage (unchanged):
  export OPENAI_API_KEY=sk-...
  python main.py --model gpt-3.5-turbo-0125 --split single_error --n 10
 
Gemini uses Google's OpenAI-compatible endpoint — same code, different
base_url and key. No extra library needed.
"""
 
import json, os, re, time
from typing import Dict, List, Optional, Any
from tqdm import tqdm
from auditor_prompt import SYSTEM, build_user_message
 
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
TEMPERATURE = 1.0
MAX_RETRIES = 6
INTER_CALL_SLEEP = 4.0     # Gemini free tier: ~15 RPM, need spacing
os.makedirs(RESULTS_DIR, exist_ok=True)
 
# ── CHANGE 1: build the right client based on which key is set ────────────────
def _make_client():
    """
    Returns an openai.OpenAI client pointed at either:
      - Google Gemini  (if GEMINI_API_KEY is set)
      - OpenAI         (if OPENAI_API_KEY is set)
    Gemini exposes an OpenAI-compatible REST endpoint so the same
    client.chat.completions.create() call works for both.
    """
    import openai
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
 
    if gemini_key:
        return openai.OpenAI(
            api_key=gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    elif openai_key:
        return openai.OpenAI(api_key=openai_key)
    else:
        raise EnvironmentError(
            "Set GEMINI_API_KEY (free) or OPENAI_API_KEY before running."
        )
 
 
def _extract_json(text: str) -> Optional[Dict]:
    """Three-stage JSON extraction: direct → fenced block → first {...}."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None
 
 
# ── CHANGE 2: call_model uses _make_client() instead of bare openai ───────────
def call_model(model: str, table: str, transaction_data: str) -> Dict[str, Any]:
    import openai
    client = _make_client()
    user_msg = build_user_message(table, transaction_data)
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=TEMPERATURE,
            )
            raw = resp.choices[0].message.content
            return {"raw_text": raw, "parsed": _extract_json(raw),
                    "model_used": resp.model, "error": None}
 
        # ── CHANGE 3: catch both OpenAI and generic HTTP 429s ─────────────────
        except openai.RateLimitError:
            wait = 30 * (2 ** attempt)
            print(f"  [rate limit] waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES}) …", flush=True)
            time.sleep(wait)
        except openai.APIStatusError as e:
            if e.status_code == 429:
                wait = 30 * (2 ** attempt)
                print(f"  [rate limit 429] waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES}) …", flush=True)
                time.sleep(wait)
            else:
                print(f"  [API error attempt {attempt+1}] {e}", flush=True)
                time.sleep(2)
        except openai.APIError as e:
            print(f"  [API error attempt {attempt+1}] {e}", flush=True)
            time.sleep(2)
 
    return {"raw_text": "", "parsed": None, "model_used": model, "error": "max_retries"}
 
 
def _meta(item):
    return {"mode": item["mode"], "general_judgement": item["general_judgement"],
            "errors": item["errors"], "gt_table": item["gt_table"]}
 
 
def _dryrun_record(idx, item, model):
    """GT-as-prediction placeholder. Scores will be trivially 1.0 — plumbing test only."""
    parsed = {"General Judgment": item["general_judgement"]}
    for i, e in enumerate(item["errors"], 1):
        parsed[f"Information for error {i}"] = {
            "Error Identification": {"Error Type": e["error_type"],
                                     "Problematic Entry": f"Row {e['problematic_entry']}"},
            "Error Resolution":   e["error_resolution"],
            "Standards Citation": e["standards_citation"],
        }
    parsed["Corrected Statements"] = item["gt_table"]
    return {"item_idx": idx, "model_used": model + "_dryrun",
            "raw_text": json.dumps(parsed), "parsed": parsed,
            "error": None, "item_meta": _meta(item)}
 
 
def run_split(model, split_name, items, seed, dry_run=False, resume=True):
    out_path = os.path.join(RESULTS_DIR,
                            f"{model.replace('/','_')}_{split_name}_predictions.json")
    existing = {}
    if resume and os.path.exists(out_path):
        with open(out_path) as f:
            for rec in json.load(f):
                existing[rec["item_idx"]] = rec
        print(f"  Resuming: {len(existing)} already done.")
 
    records = []
    for idx, item in enumerate(tqdm(items, desc=f"{model}/{split_name}", unit="smpl")):
        if idx in existing:
            records.append(existing[idx]); continue
        if dry_run:
            rec = _dryrun_record(idx, item, model)
        else:
            r = call_model(model, item["table"], item["transaction_data"])
            rec = {"item_idx": idx, "model_used": r["model_used"],
                   "raw_text": r["raw_text"], "parsed": r["parsed"],
                   "error": r["error"], "item_meta": _meta(item)}
            time.sleep(INTER_CALL_SLEEP)
        records.append(rec)
        with open(out_path, "w") as f:
            json.dump(records, f, indent=2)
    print(f"  Saved {len(records)} → {out_path}")
    return records