"""
Stage 1 - Auditor runner with multi-backend support.
 
Supports:
  - OpenAI (GPT-3.5, GPT-4, etc.)
  - Google Gemini
  - Ollama (local models)
  - Qwen (via Dashscope API)
  - Kimi (Moonshot AI)
  - Hugging Face Transformers (local)

Usage examples:
  # OpenAI
  export OPENAI_API_KEY=sk-...
  python main.py --model gpt-4 --split single_error --n 10
  
  # Gemini
  export GEMINI_API_KEY=AIza...
  python main.py --model gemini-2.0-flash --split single_error --n 10
  
  # Ollama (local)
  ollama serve  # start ollama first
  ollama pull llama3
  python main.py --model ollama/llama3 --split single_error --n 10
  
  # Qwen
  export DASHSCOPE_API_KEY=sk-...
  python main.py --model qwen/qwen-turbo --split single_error --n 10
  
  # Kimi
  export MOONSHOT_API_KEY=sk-...
  python main.py --model kimi/moonshot-v1-8k --split single_error --n 10
"""

import json, os, re, time
from typing import Dict, List, Optional, Any
from tqdm import tqdm
from core.auditor_prompt import SYSTEM, build_user_message
from core.model_backends import get_model_client

from core.paths import RESULTS_DIR   # repo-root results/
TEMPERATURE = 1.0
MAX_RETRIES = 6
INTER_CALL_SLEEP = 4.0     # API rate limiting spacing
os.makedirs(RESULTS_DIR, exist_ok=True)


def _extract_json(text: str) -> Optional[Dict]:
    """Three-stage JSON extraction: direct -> fenced block -> first {...}."""
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


def call_model(model: str, table: str, transaction_data: str) -> Dict[str, Any]:
    """Call the appropriate model backend and return results."""
    try:
        client = get_model_client(model)
    except (EnvironmentError, ValueError) as e:
        return {"raw_text": "", "parsed": None, "model_used": model, "error": str(e)}
    
    user_msg = build_user_message(table, transaction_data)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    
    for attempt in range(MAX_RETRIES):
        try:
            result = client.generate(messages, temperature=TEMPERATURE)
            raw = result["content"]
            return {
                "raw_text": raw, 
                "parsed": _extract_json(raw),
                "model_used": result["model"], 
                "error": None
            }
        
        except Exception as e:
            error_msg = str(e).lower()
            # Handle rate limiting
            if "rate" in error_msg or "429" in error_msg or "quota" in error_msg:
                wait = 30 * (2 ** attempt)
                print(f"  [rate limit] waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES}) ...", flush=True)
                time.sleep(wait)
            # Handle other API errors
            else:
                print(f"  [error attempt {attempt+1}] {e}", flush=True)
                time.sleep(2)
    
    return {"raw_text": "", "parsed": None, "model_used": model, "error": "max_retries"}


def _meta(item):
    return {"mode": item["mode"], "general_judgement": item["general_judgement"],
            "errors": item["errors"], "gt_table": item["gt_table"]}


def _dryrun_record(idx, item, model):
    """GT-as-prediction placeholder. Scores will be trivially 1.0 - plumbing test only."""
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
    print(f"  Saved {len(records)} -> {out_path}")
    return records
