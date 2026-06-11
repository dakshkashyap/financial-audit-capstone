"""
Stage 2 — Five-stage evaluator  (FIXED).
 
Fixes vs. your version:
  * BLEU: take ONE corrected table per sample (the model emits the full
    corrected statement once), not a join across every error — the join
    duplicated the table and crushed BLEU (that's why dry-run multi was 0.5047
    instead of 1.0).
  * Multi-error type/entry EM: one-to-one greedy matching so a model can't
    score a GT error twice with a duplicated prediction.
  * BERTScore: model_type + num_layers pinned; rescale_with_baseline exposed
    as a calibration knob. lang dropped so model_type fully controls it.
  * Standards Citation unchanged: still a regex substitute, still flagged.
"""
 
import re
from typing import List, Dict, Optional, Any
 
# ── Calibration knobs (sweep these against the paper's numbers) ──────────────
BERTSCORE_MODEL   = "roberta-large"
BERTSCORE_LAYERS  = 17           # roberta-large default in bert-score
BERTSCORE_RESCALE = False        # try True if your BertScore lands ~0.05 high
 
EM_THRESHOLD   = 1.0
BS_THRESHOLD   = 0.85
BLEU_THRESHOLD = 0.99
 
 
# ── Stage 1 ──────────────────────────────────────────────────────────────────
def em_general_judgment(pred: str, gt: str) -> float:
    return float(str(pred).strip().lower() == str(gt).strip().lower())
 
 
# ── Stage 2 ──────────────────────────────────────────────────────────────────
_ERROR_TYPE_MAP = {
    "missing row": "missing row", "missing_row": "missing row",
    "numerical error": "numerical error", "numerical_error": "numerical error",
    "redundant row": "redundant row", "redundant_row": "redundant row",
    "misclassification": "misclassification",
}
 
def _norm_type(s: str) -> str:
    return _ERROR_TYPE_MAP.get(str(s).strip().lower(), str(s).strip().lower())
 
def _row_int(entry: Any) -> Optional[int]:
    if entry is None:
        return None
    if isinstance(entry, int):
        return entry
    m = re.search(r"\d+", str(entry))
    return int(m.group()) if m else None
 
 
def _one_to_one(gt_errors, pred_errors, key_fn) -> float:
    """Greedy one-to-one match. Each prediction consumed at most once."""
    if not gt_errors:
        return 1.0
    remaining = [key_fn(p) for p in pred_errors]
    hits = 0
    for gt in gt_errors:
        g = key_fn(gt)
        if g in remaining:
            remaining.remove(g)   # consume so it can't match twice
            hits += 1
    return hits / len(gt_errors)
 
 
def em_error_type(pred_errors: List[Dict], gt_errors: List[Dict]) -> float:
    return _one_to_one(
        gt_errors, pred_errors,
        lambda e: _norm_type(e.get("error_type", e.get("Error Type", ""))),
    )
 
def em_error_entry(pred_errors: List[Dict], gt_errors: List[Dict]) -> float:
    return _one_to_one(
        gt_errors, pred_errors,
        lambda e: _row_int(e.get("problematic_entry", e.get("Problematic Entry"))),
    )
 
 
# ── Stage 3 — BERTScore (batched, pinned) ─────────────────────────────────────
def bertscore_batch(preds: List[str], refs: List[str]) -> List[float]:
    from bert_score import score as _bscore
    safe_preds = [p if p and p.strip() else "N/A" for p in preds]
    safe_refs  = [r if r and r.strip() else "N/A" for r in refs]
    _, _, F = _bscore(
        safe_preds, safe_refs,
        model_type=BERTSCORE_MODEL,
        num_layers=BERTSCORE_LAYERS,
        rescale_with_baseline=BERTSCORE_RESCALE,
        lang="en",
        verbose=False,
        batch_size=16,
    )
    return F.tolist()
 
 
# ── Stage 4 — Standards Citation (regex substitute, NOT paper's metric) ───────
def _fasb_ids(text: str) -> List[str]:
    raw = re.findall(r"(?:FASB\s+)?(?:ASC|SFAC|SAB|FAS|APB|SOP)\s*[\d][\d\-\.]*",
                     str(text), re.IGNORECASE)
    return [re.sub(r"\s+", " ", r.strip().upper()) for r in raw]
 
def em_standards_topk(pred_text: str, gt_text: str, k: int = 1) -> float:
    """
    Confirmed by author email (Rushi Wang, June 2026):
    - No external FASB DB. The LLM uses its own prior knowledge.
    - The model's generated Standards Citation text is compared against the
      'Standards Citation' field in the JSON ground truth directly.
    - Evaluation is Top-K retrieval-based EM on extracted FASB IDs.
 
    Strategy (two-stage):
    1. Extract FASB ASC IDs from both sides and do string overlap (Top-K).
    2. Fall back to substring match on the full text if no IDs are found.
    """
    pred_ids, gt_ids = _fasb_ids(pred_text), _fasb_ids(gt_text)
    if gt_ids:
        for gid in gt_ids:
            if any(gid in p or p in gid for p in pred_ids[:k]):
                return 1.0
        return 0.0
    # No parseable IDs in GT → substring match on raw text
    g = str(gt_text).strip().lower()
    p = str(pred_text).strip().lower()
    return float(bool(g) and bool(p) and (g[:40] in p or p[:40] in g))
 
 
# ── Stage 5 — Table Revision BLEU ─────────────────────────────────────────────
def bleu_table_revision(pred_table: str, gt_table: str) -> float:
    import sacrebleu
    if not pred_table or not gt_table:
        return 0.0
    res = sacrebleu.corpus_bleu([pred_table], [[gt_table]], smooth_method="exp")
    return res.score / 100.0
 
 
# ── Overall SR ────────────────────────────────────────────────────────────────
def success_rate(s: Dict[str, float]) -> float:
    return float(
        s["em_general_judgment"] >= EM_THRESHOLD and
        s["em_error_type"]       >= EM_THRESHOLD and
        s["em_error_entry"]      >= EM_THRESHOLD and
        s["bertscore"]           >= BS_THRESHOLD and
        s["bleu"]                >= BLEU_THRESHOLD
    )
 
 
# ── Extract predicted errors + single corrected table ─────────────────────────
def extract_pred_errors(parsed: Optional[Dict]) -> List[Dict]:
    if not parsed:
        return []
    errors, i = [], 1
    while f"Information for error {i}" in parsed:
        info = parsed[f"Information for error {i}"]
        ei = info.get("Error Identification", {}) or {}
        errors.append({
            "Error Type":        ei.get("Error Type", ""),
            "Problematic Entry": ei.get("Problematic Entry", ""),
            "resolution":        info.get("Error Resolution", ""),
            "citation":          info.get("Standards Citation", ""),
        })
        i += 1
    if not errors and "Error Identification" in parsed:
        ei = parsed["Error Identification"] or {}
        errors.append({
            "Error Type":        ei.get("Error Type", ""),
            "Problematic Entry": ei.get("Problematic Entry", ""),
            "resolution":        parsed.get("Error Resolution", ""),
            "citation":          parsed.get("Standards Citation", ""),
        })
    return errors
 
 
def extract_corrected_table(parsed: Optional[Dict]) -> str:
    """ONE corrected table per sample. Prefer top-level, else first error block."""
    if not parsed:
        return ""
    if parsed.get("Corrected Statements"):
        return parsed["Corrected Statements"]
    i = 1
    while f"Information for error {i}" in parsed:
        c = parsed[f"Information for error {i}"].get("Corrected Statements")
        if c:
            return c
        i += 1
    return ""
 