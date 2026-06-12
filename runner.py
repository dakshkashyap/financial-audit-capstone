"""
Stage 1 — Auditor runner (multi-provider).

Paper-faithful settings (confirmed by author email, Rushi Wang, June 2026):
  TEMPERATURE = 1.0   (paper used 1.0, not 0.0)

Providers — all reached through the OpenAI SDK via OpenAI-compatible endpoints,
routed automatically from the model name (override with --provider in main.py):

  anthropic   claude-*                 needs ANTHROPIC_API_KEY   (paid)
  openai      gpt-*, o1/o3/o4          needs OPENAI_API_KEY      (paid)
  gemini      gemini-*                 needs GEMINI_API_KEY      (free tier)
  groq        any open-weight id       needs GROQ_API_KEY        (free tier)
  openrouter  any open-weight id       needs OPENROUTER_API_KEY  (free :free models)
  together    any open-weight id       needs TOGETHER_API_KEY
  ollama      any local model          no key, local server on :11434

For open-weight ids (e.g. "openai/gpt-oss-120b", "llama-3.3-70b-versatile",
"moonshotai/kimi-k2-instruct") the first of groq → openrouter → together with a
key set wins; otherwise ollama is assumed.

PowerShell usage:
  $env:ANTHROPIC_API_KEY="sk-ant-..."
  python main.py --model claude-sonnet-4-6 --split single_error --n 10

  $env:GROQ_API_KEY="gsk_..."
  python main.py --model openai/gpt-oss-120b --split single_error --n 10
"""

import hashlib
import json, os, re, time
from typing import Dict, List, Optional, Any
from tqdm import tqdm
from auditor_prompt import SYSTEM, build_user_message

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
TEMPERATURE = 1.0
MAX_RETRIES = 6
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Provider registry ─────────────────────────────────────────────────────────
# sleep      : seconds between calls (free tiers need spacing; paid tiers don't)
# max_tokens : explicit completion cap. Anthropic's OpenAI-compat endpoint and
#              Groq need one; legacy OpenAI models (gpt-4-0613, 8k ctx) must NOT
#              get a large cap, so we leave it unset there.
PROVIDERS = {
    "openai":     dict(env="OPENAI_API_KEY",     base_url=None,                      sleep=0.5, max_tokens=None),
    "anthropic":  dict(env="ANTHROPIC_API_KEY",  base_url="https://api.anthropic.com/v1/", sleep=0.0, max_tokens=8192),
    "gemini":     dict(env="GEMINI_API_KEY",     base_url="https://generativelanguage.googleapis.com/v1beta/openai/", sleep=4.0, max_tokens=None),
    "groq":       dict(env="GROQ_API_KEY",       base_url="https://api.groq.com/openai/v1", sleep=2.5, max_tokens=8192),
    "openrouter": dict(env="OPENROUTER_API_KEY", base_url="https://openrouter.ai/api/v1",   sleep=1.0, max_tokens=8192),
    "together":   dict(env="TOGETHER_API_KEY",   base_url="https://api.together.xyz/v1",    sleep=1.0, max_tokens=8192),
    "ollama":     dict(env=None,                 base_url="http://localhost:11434/v1",      sleep=0.0, max_tokens=8192),
}

# HTTP statuses that retrying will never fix — fail fast instead of burning
# 6 retries per sample and silently writing empty predictions.
FATAL_STATUS = {400, 401, 403, 404, 422}


def detect_provider(model: str) -> str:
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "gemini"
    if (m.startswith(("gpt-3", "gpt-4", "gpt-5", "o1", "o3", "o4", "chatgpt"))
            and not m.startswith("gpt-oss")):
        return "openai"
    # open-weight id → first configured hosted provider, else local ollama
    for prov in ("groq", "openrouter", "together"):
        if os.environ.get(PROVIDERS[prov]["env"], ""):
            return prov
    return "ollama"


_CLIENTS: Dict[str, Any] = {}

def _make_client(provider: str):
    if provider in _CLIENTS:
        return _CLIENTS[provider]
    import openai
    cfg = PROVIDERS[provider]
    key = os.environ.get(cfg["env"], "") if cfg["env"] else "ollama"
    if not key:
        raise EnvironmentError(
            f"Provider '{provider}' selected but {cfg['env']} is not set.\n"
            f"PowerShell:  $env:{cfg['env']}=\"...\"")
    client = openai.OpenAI(api_key=key, base_url=cfg["base_url"], max_retries=0)
    _CLIENTS[provider] = client
    return client


# ── JSON extraction (hardened) ────────────────────────────────────────────────
# strict=False lets json accept literal newlines/control chars inside strings —
# Claude and open-weight models often emit those in "Corrected Statements".
def _try_load(s: str) -> Optional[Dict]:
    try:
        out = json.loads(s, strict=False)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def _balanced_objects(text: str) -> List[str]:
    """All top-level {...} spans with balanced braces (brace-counting, string-aware)."""
    spans, depth, start, in_str, esc = [], 0, -1, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0:
                    spans.append(text[start:i + 1])
    return spans


def _extract_json(text: str) -> Optional[Dict]:
    """direct → fenced block(s) → balanced {...} candidates (longest first)."""
    if not text:
        return None
    # reasoning models (DeepSeek R1, Qwen3, ...) wrap thinking in <think> tags
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    parsed = _try_load(text)
    if parsed is not None:
        return parsed
    for m in re.finditer(r"```(?:json)?\s*([\s\S]+?)```", text):
        parsed = _try_load(m.group(1).strip())
        if parsed is not None:
            return parsed
    for cand in sorted(_balanced_objects(text), key=len, reverse=True):
        parsed = _try_load(cand)
        if parsed is not None:
            return parsed
    return None


# ── Model call with retry / fail-fast ─────────────────────────────────────────
def call_model(model: str, table: str, transaction_data: str,
               provider: Optional[str] = None) -> Dict[str, Any]:
    import openai
    provider = provider or detect_provider(model)
    client = _make_client(provider)
    user_msg = build_user_message(table, transaction_data)

    kwargs: Dict[str, Any] = dict(
        model=model,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user",   "content": user_msg}],
        temperature=TEMPERATURE,
    )
    if PROVIDERS[provider]["max_tokens"]:
        kwargs["max_tokens"] = PROVIDERS[provider]["max_tokens"]

    last_err = "max_retries"
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content or ""
            return {"raw_text": raw, "parsed": _extract_json(raw),
                    "model_used": resp.model, "provider": provider, "error": None}

        except openai.RateLimitError as e:
            wait = min(30 * (2 ** attempt), 300)
            print(f"  [rate limit] waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES}) ...", flush=True)
            time.sleep(wait)
            last_err = f"rate_limit: {e}"
        except openai.APIStatusError as e:
            if e.status_code in FATAL_STATUS:
                # model not found / bad key / bad request → retrying cannot help
                raise RuntimeError(
                    f"Fatal API error {e.status_code} from {provider} for model "
                    f"'{model}'. Check the model id and your API key.\n{e}") from e
            wait = min(30 * (2 ** attempt), 300)   # 429/5xx/529-overloaded
            print(f"  [HTTP {e.status_code}] waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES}) ...", flush=True)
            time.sleep(wait)
            last_err = f"http_{e.status_code}: {e}"
        except (openai.APIConnectionError, openai.APITimeoutError) as e:
            print(f"  [connection error attempt {attempt+1}] {e}", flush=True)
            time.sleep(5 * (attempt + 1))
            last_err = f"connection: {e}"
        except openai.APIError as e:
            print(f"  [API error attempt {attempt+1}] {e}", flush=True)
            time.sleep(2)
            last_err = f"api: {e}"

    return {"raw_text": "", "parsed": None, "model_used": model,
            "provider": provider, "error": last_err}


# ── Bookkeeping ───────────────────────────────────────────────────────────────
def _safe_name(model: str) -> str:
    """Model id → Windows-safe filename fragment ('/' and ':' are illegal)."""
    return re.sub(r"[\\/:*?\"<>|]", "_", model)


def _table_hash(item: Dict) -> str:
    return hashlib.md5(item["table"].encode("utf-8")).hexdigest()[:12]


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
    return {"item_idx": idx, "table_hash": _table_hash(item),
            "model_used": model + "_dryrun",
            "raw_text": json.dumps(parsed), "parsed": parsed,
            "error": None, "item_meta": _meta(item)}


def run_split(model, split_name, items, seed, dry_run=False, resume=True,
              provider=None, sleep=None):
    provider = provider or detect_provider(model)
    inter_sleep = PROVIDERS[provider]["sleep"] if sleep is None else sleep
    out_path = os.path.join(RESULTS_DIR,
                            f"{_safe_name(model)}_{split_name}_predictions.json")

    existing = {}
    if resume and os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for rec in json.load(f):
                existing[rec["item_idx"]] = rec
        print(f"  Resuming: {len(existing)} records found in {os.path.basename(out_path)}")

    records, reused, parse_fail = [], 0, 0
    for idx, item in enumerate(tqdm(items, desc=f"{model}/{split_name}", unit="smpl")):
        rec = None
        prev = existing.get(idx)
        was_dryrun = str(prev.get("model_used", "")).endswith("_dryrun") if prev else False
        if prev is not None and prev.get("error") is None and (dry_run or not was_dryrun):
            # only reuse if it is verifiably the SAME item (different --n values
            # produce different random draws, so item_idx alone is not identity)
            h = prev.get("table_hash")
            same = (h == _table_hash(item)) if h else \
                   (prev.get("item_meta", {}).get("gt_table") == item["gt_table"])
            if same:
                rec, reused = prev, reused + 1

        if rec is None:
            if dry_run:
                rec = _dryrun_record(idx, item, model)
            else:
                r = call_model(model, item["table"], item["transaction_data"], provider)
                rec = {"item_idx": idx, "table_hash": _table_hash(item),
                       "model_used": r["model_used"], "raw_text": r["raw_text"],
                       "parsed": r["parsed"], "error": r["error"],
                       "item_meta": _meta(item)}
                if inter_sleep:
                    time.sleep(inter_sleep)

        if rec.get("parsed") is None:
            parse_fail += 1
        records.append(rec)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    n = len(records)
    print(f"  Saved {n} -> {out_path}")
    if reused:
        print(f"  ({reused} reused from previous run)")
    if parse_fail:
        print(f"  WARNING: {parse_fail}/{n} responses could not be parsed as JSON "
              f"— these score 0 on every EM metric. Inspect 'raw_text' in the "
              f"predictions file if this number is high.")
    return records
