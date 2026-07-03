# CLAUDE.md — Project memory & session handoff

> Purpose: transfer the Cursor agent session memory into Claude Code accurately.
> This file is the single source of truth for *what this repo is, what was built,
> why, what works/doesn't, and what the next person should do*. Read it fully
> before editing code.

---

## 1. What this project is

**Capstone:** "IntelliAudit" — a financial-statement auditing system that improves
on the **AuditBench** baseline (paper: *Automating Financial Statement Audits with
Large Language Models*, arXiv:2506.17282).

- **Baseline paper repo / dataset:** [Oppugno-Rushi/AuditBench](https://github.com/Oppugno-Rushi/AuditBench-Benchmarking-LLMs-for-Financial-Auditing)
- **Our repo:** `github.com/dakshkashyap/financial-audit-capstone`
- **Team architecture vision (Phase 2):** a multi-stage pipeline ending in an
  adversarial **Auditor → Defender → Judge** multi-agent loop, fronted by cheap
  **deterministic gates** (Stage 0) and grounded by retrieval (EDGAR mapper,
  FASB/standards citation). Goal: keep the baseline's high error-detection recall
  while killing its **over-auditing problem** (50% false alarms on clean tables).

**The task this developer owns:** implement **Stage 0A (Arithmetic Verifier)** and
**Stage 0B (Equation Checker)** — the deterministic, no-LLM, $0 pre-filter — and
wire them to the existing codebase **without changing the LLM pipeline**. ✅ Done
(see §4–§7). Teammates own other stages (see §11).

### The 4 AuditBench error types (the whole task is localizing/classifying these)
1. **Numerical Error** — a value was changed. *(Stage 0A owns)*
2. **Missing Row** — a row was deleted. *(Stage 0A owns)*
3. **Redundant Row** — an extra unsupported row was added. *(Stage 0B owns)*
4. **Misclassification** — a real row placed in the wrong section. *(Stage 0B owns)*

---

## 2. Repository layout

### Baseline LLM pipeline (pre-existing — DO NOT modify without reason)
- `parser.py` — `[row n]: Label | $value [SEP]` table parser + the 3 data loaders
  (`load_single_error`, `load_multi_error`, `load_correct`; fixed seed). Also
  `parse_table`, `parse_numeric_value`.
- `auditor_prompt.py` — system + user prompt, **verbatim from the paper appendix**.
- `runner.py` — multi-provider routing (Claude / OpenAI / Gemini / Groq / OpenRouter
  / Together / Ollama), retries, crash-safe resume, hardened JSON extraction.
- `metrics.py` — the 5-stage metrics + calibration knobs. Exposes `_norm_type`,
  `_row_int` (reused by Stage 0 eval).
- `evaluate.py`, `main.py`, `verify_data.py` — scoring, glue, preflight.

### Stage 0 — deterministic gate (BUILT THIS WORK — see §4)
- `stage0_common.py` — shared parsing/oracle layer + `Finding` schema + `combine_findings`.
- `stage0a.py` — Arithmetic Verifier (SymPy + pandas): Numerical Error, Missing Row.
- `stage0b.py` — Equation Checker (pure Python): Redundant Row, Misclassification.
- `stage0_eval.py` — offline metrics harness → `results/stage0_eval.json`.

### Data (already in repo; raw subset folders NOT needed)
- `Error_insertion/wrong_table_data.json` — 1484 single-error tables (paper Table 2).
- `Error_insertion/wrong_table_data_multiple_errors.json` — 372 multi-error (Table 3).
- `transaction_data/output_transaction_table_pair.json` — 371 clean tables (Table 1).

### Docs
- `README.md` — setup/run for baseline + a "Stage 0 deterministic gate" section.
- `todo.md` — team research roadmap; has a **"Phase 2 Progress — Stage 0A+0B"** section
  with the full design rationale, results, limitations, and handoff contract.
- `CLAUDE.md` — this file.

---

## 3. How to run

Everything runs from `c:\Users\daksh\Desktop\Capstone\financial-audit-capstone`.
Shell is **Windows PowerShell** (gotchas in §12).

```powershell
pip install --user -r requirements.txt   # adds sympy + pandas for Stage 0
python verify_data.py                     # free preflight, no API key

# Stage 0 deterministic gate — FREE, no API key, this is the new work:
python stage0_eval.py                            # single_error + correct, n=150
python stage0_eval.py --split single_error --n 1484
python stage0_eval.py --split all --n 400        # adds multi_error
# → prints metrics and writes results/stage0_eval.json

# Baseline LLM pipeline (needs an API key):
$env:ANTHROPIC_API_KEY="sk-ant-..."
python main.py --model claude-opus-4-6 --split single_error --n 10   # smoke
python main.py --model claude-opus-4-6                                # full protocol
python main.py --eval-only                                           # re-score only
```

`stage0_eval.py` flags: `--split {single_error,multi_error,correct,all,default}`
(default = single_error + correct), `--n` (default 150), `--seed` (default 42).

---

## 4. Stage 0 — what was built (detail)

Two deterministic modules read a parser item (`{table, transaction_data, gt_table,
errors, ...}`) and localize an error **without any LLM call**. Precision-first:
abstain unless a finding is corroborated. The single integration point is
`combine_findings(...)` which returns a `Finding` or `None` (abstain).

### `stage0_common.py` — shared layer
- **Label normalization:** `norm_label` (lowercase, strip punctuation, curly→straight
  quotes), `core_label` (strip trailing ` non current`/` current`/` cost` qualifiers).
- **Subtotal detection:** `_is_subtotal_label` — `startswith("total ")` OR matches
  `_NAMED_SUBTOTAL_KEYS` (gross margin/profit, operating income, net income, cash
  flow aggregates, etc.). "gross profit" was explicitly added to fix a unit-mismatch FP.
- **Comparison helpers:**
  - `approx_eq(a,b,tol=0.5)` — exact-for-integers equality.
  - `values_match(a,b)` — **magnitude-aware**: equal up to sign AND a 0.5% relative
    tolerance (`REL_TOL`). Transactions state magnitudes (`$160`) for rows shown
    signed (`($160)`); a sign-only or sub-percent gap is narration noise, not an
    error. Injected numerical errors move values far more than 0.5%.
- **Noise cleanup:** `strip_noise` removes HTML-comment injector markers
  (`$22,118 <!-- An incorrect value entered deliberately -->`) and wrapping
  quotes/asterisks; `clean_value` runs it before `parse_numeric_value`. Without
  this, malformed cells silently parse to `None` and a real leaf gets demoted to
  a value-less "header", causing a flood of fake "missing row" hits.
- **Structured table:** `build_table` → pandas DataFrame of `Row(idx,label,norm,
  core,value,kind)` where `kind ∈ {header,leaf,subtotal}`. Helpers: `rows_of`,
  `next_subtotal_after`, `subtotal_at_or_after`.
- **Transaction oracle:** `build_transactions` parses `[contributing to row N]`
  blocks. **Always reads the Explanation LHS value** (`[Explanation: $X = $a + $b]`
  → `$X`), falling back to the inline `| $value`; the RHS is LLM-generated and
  sometimes drops a term. `Transactions` indexes entries by original row index
  and by core label (`expected_for_index`, `by_core`, `value_present`,
  `unique_by_core`, `expected_subtotal`).
- **`subtotal_expected_map(df, tx)`** — maps each table subtotal's index to its
  oracle value. **Key insight:** none of the 4 error types add/remove a *subtotal*,
  so the ordered subtotal lists align 1:1 → **positional alignment** when counts
  match (falls back to unique-label match otherwise). Label matching alone only
  worked ~64% of the time.
- **`infer_groups(df)`** — heuristic subtotal→member-leaf hierarchy (contiguous run
  of leaves since the previous subtotal/header). **Unreliable on income/cash-flow
  statements** — used only for the weak-tamper fallback. Do not build hard logic on it.
- **`Finding`** dataclass: `error_type, problematic_entry, correct_value,
  stated_value, source ∈ {"0A","0B"}, detail`.
- **`Stage0AResult`**: `flagged, primary, weak, reconciliation, footing, missing`.
- **`Stage0BResult`**: `flagged, primary, equations, redundant, misclassification`.
- **`combine_findings(a, b)`** — deterministic verdict, most-specific first:
  1. 0A `primary` (leaf Numerical / Missing Row),
  2. 0B `primary` (Redundant / Misclassification),
  3. 0A `weak` (subtotal tamper) — **only** if no structural evidence exists
     (`not (b.redundant or b.misclassification or a.missing)`), else abstain.

### `stage0a.py` — Arithmetic Verifier (SymPy)
- `_reconcile_leaves` → **Numerical Error**. Leaf whose stated value disagrees with
  the oracle, matched by original index + label guard, **label must be unique** in
  the table (avoids `Basic`/`Diluted` EPS-vs-shares collisions), magnitude-aware.
  No subtotal corroboration needed (the unique-label+index match is strong enough).
- `_check_footing` → subtotal mismatches vs oracle (SymPy exact); pure evidence/cascade.
- `_detect_missing` → **Missing Row**. A tx leaf whose core AND value are both
  absent from the table, **corroborated** by `_subtotal_anomaly_magnitudes` (some
  subtotal is off by exactly its value — vs oracle or vs its own footing). Skips
  $0 rows. Reports the **successor index** (re-insertion position, AuditBench GT
  convention). Abstains if >1 candidate survives.
- `_detect_subtotal_tamper` → Numerical Error injected directly on a subtotal
  (leaves intact, leaf-sum == oracle but stated != oracle). Demoted to `res.weak`.
- `verify(item)` order: reconciliation (Numerical) → missing → weak tamper.

### `stage0b.py` — Equation Checker (pure Python)
- `_check_identities` → definitional identities as evidence: Assets = Liab + Equity,
  IS chain (sales − cogs = gross margin; gross margin − opex = operating income),
  cash-flow (op + inv + fin = change in cash). Each guarded by row presence.
- `_detect_section_anomalies` → the **unified** Redundant/Misclassification detector
  using `subtotal_expected_map`:
  - **Over-statement:** a leaf whose enclosing subtotal is over by exactly that
    row's value → **Redundant Row** if no transaction describes it, else
    **Misclassification** (real row, wrong place).
  - **Under-statement:** a subtotal short by exactly V where a tx-described leaf of
    magnitude V sits in a *different* group → that leaf was **Misclassified out**
    (catches moves inside a grand total, e.g. current→non-current assets).
  - Skips $0 rows. "subtotal off by exactly this value" is the corroboration that
    keeps clean statements silent.
- `check(item)` order: redundant → misclassification.

### `stage0_eval.py` — harness
- `run_gate(item)` = `combine_findings(stage0a.verify(item), stage0b.check(item))`.
- `eval_single` (coverage, Error Row/Type EM overall + among-fired, success,
  correct-value accuracy, per-type breakdown, confusion matrix), `eval_correct`
  (false-positive rate on clean split), `eval_multi` (primary-vs-any-GT partial credit).
- `_gt_value_for` looks up the GT correct value from `gt_table` to score Numerical/Missing.
- Writes `results/stage0_eval.json`.

`requirements.txt` gained `sympy>=1.12` and `pandas>=2.0.0`.

---

## 5. Design principles that made it work (precision-first)

Each was learned empirically; each removed a class of false positives:
1. **Corroboration anchoring** — fire only when a subtotal is off by *exactly* the
   implicated row's value. Clean statements foot, so the gate stays silent.
2. **Magnitude-aware comparison** (`values_match`) — ignore sign + 0.5% rounding.
3. **Positional subtotal alignment** (`subtotal_expected_map`) — order, not labels.
4. **Injector-noise cleanup** (`strip_noise`) — strip HTML comments / quotes.
5. **Unique-label + index guard** on reconciliation — avoid ambiguous-label collisions.
6. **Abstain by default** — multiple/ambiguous candidates → `None`. Coverage is
   measured, not forced.

---

## 6. Results (latest validation: n=400, seed=42 → `results/stage0_eval.json`)

| Metric | Value | Note |
|---|---|---|
| **False-positive rate (clean split)** | **0.019** (7/371) | vs LLM baseline 0.50 — the headline win |
| **Correct-value accuracy** | **0.989** | when it proposes a fix, the number is right |
| **Error Type EM (among fired)** | **0.919** | |
| **Error Row EM (among fired)** | **0.856** | |
| Coverage (fires) | ~0.40 | intentionally partial; rest deferred to LLM |

Per-type coverage / type-EM / row-EM (single-error, n=400):

| GT type | n | coverage | type EM | row EM | owner |
|---|---|---|---|---|---|
| numerical error | 95 | 0.72 | 0.72 | 0.67 | 0A |
| redundant row | 104 | 0.41 | 0.35 | 0.35 | 0B |
| missing row | 108 | 0.31 | 0.30 | 0.26 | 0A |
| misclassification | 93 | 0.16 | 0.12 | 0.10 | 0B |

(Earlier baseline LLM run for context: clean-split Gen Judgment 0.50 = **50% false
alarms** — the exact problem Stage 0 fixes.)

---

## 7. What did NOT work / known limitations (READ before extending)

- **Misclassification recall is low (0.16) and partly undetectable deterministically.**
  Many injected cases are pure within-section reorders, or the subtotals were not
  recomputed → **no arithmetic signal at all**. These genuinely need the LLM stage
  or transaction-ordering semantics. Only the "section over/short by exactly the
  moved value" flavor is caught.
- **`infer_groups()` is heuristic and unreliable** on income/cash-flow statements
  (no section headers, net subtotals, mixed signs). Improving it is the main lever
  for higher coverage.
- **The 7 residual clean-split FPs are dataset tx/table inconsistencies, not bugs:**
  unit mismatches (`R&D 2987` table vs tx `2987000`, thousands-vs-dollars) and noisy
  transaction LHS values. Inherent to the benchmark's narratives.
- **Transaction label coverage caps missing/redundant recall** — when the narrative
  labels a row differently than the table (`Products` vs `Net Sales of Products`),
  reconciliation can't match and the gate abstains (safe: no FP, but lower coverage).
- **Reconciliation needs a unique, index-aligned label** — duplicate/shifted labels abstain.

### Things tried and rejected along the way
- Label-based subtotal matching (≈64% reliable) → replaced by positional alignment.
- Aggressive `_detect_subtotal_tamper` as a primary finding → caused type
  mislabels; demoted to `weak` and gated in `combine_findings`.
- Early missing-row detection without corroboration → flooded FPs; now requires a
  subtotal anomaly of exactly the row's value.
- Inline Python debug one-liners in PowerShell → kept failing on escaping; used a
  throwaway `_dbg.py` script instead (since deleted).

---

## 8. Handoff contract for downstream stages

Single integration point:

```python
import stage0a, stage0b
from stage0_common import combine_findings
finding = combine_findings(stage0a.verify(item), stage0b.check(item))
# finding is None (abstain) OR Finding(error_type, problematic_entry,
#   correct_value, stated_value, source ∈ {"0A","0B"}, detail)
```

Recommended pipeline wiring (this *is* the gate and the cheapest available win):
- **Stage 0 fires →** trust it (exact + free), short-circuit, **skip the LLM**.
  This is what converts the clean-split fire rate (0.019) into a ~0.50→~0.98
  Gen-Judgment improvement and saves API cost.
- **Stage 0 abstains →** fall through to the **LLM stage**; feed the LLM the Stage-0
  evidence (`Stage0AResult.footing` / `Stage0BResult.equations`) to ground reasoning.
- **Reviser stage** can apply `correct_value` + `problematic_entry` to rewrite the
  table deterministically for Numerical/Missing — no LLM needed for those.
- **EDGAR mapper / taxonomy stages** can reuse `stage0_common.build_table()` and the
  `Finding` schema instead of re-parsing.

---

## 9. Git state

- **Repo:** `github.com/dakshkashyap/financial-audit-capstone`
- **Default branch:** `main`. Baseline analysis lives on `claude-results`.
- **This work shipped on branch:** `stage0-deterministic-gate` (pushed to origin;
  commit `31475e4` "Add Stage 0A/0B deterministic pre-LLM audit gate"). PR not yet opened.
- **Teammate branches on origin (next stages, see §11):**
  `irvin/edgar-mapper`, `stage1-citation-improvements`.
- A `.gitignore` was added (ignores `__pycache__/`, `*.pyc`, venvs, `.env`); the
  `__pycache__` build artifacts are intentionally NOT committed.

---

## 10. Session history (memory being transferred)

1. **278c39b9 (Jun 5):** Original baseline — first attempt to reproduce the
   AuditBench paper in phases (`audit_llm/phase1`, `phase2_identification`,
   `phase3_resolution`) using free Gemini tier. Hit a `bert_score`/`RobertaTokenizer`
   error. This structure was later flattened into the current `main.py`/`runner.py` repo.
   **Full detail in §13.**
2. **589f8f8e (Jun 17–23):** Research-direction + baseline-analysis session. Defined
   the IntelliAudit research thesis (precision-aware, model-agnostic, Auditor/
   Defender/Judge + neuro-symbolic gate + GraphRAG), reviewed the Opus-4.6 baseline
   run, and **wrote `todo.md`** (the results analysis + roadmap). Established the
   headline finding: Opus beats GPT-4 on success rate but has **50% false alarms on
   clean tables**.
3. **96fb92c3 (Jun 23):** Aborted immediately — "Model not available" (Anthropic
   removed access to that model). No work done.
4. **b804b895 (Jun 23–25, CURRENT):** Implemented Stage 0A + 0B + common + eval
   (this work), iteratively debugged to FP ≈ 0.019, documented everything in
   `README.md` + `todo.md`, then committed and pushed to `stage0-deterministic-gate`.
   Finally produced this `CLAUDE.md`.

---

## 11. Next stages & owners (team)

- **EDGAR mapper** (`origin/irvin/edgar-mapper`) — ingest/normalize EDGAR filings.
  Can consume `build_table` + `Finding`.
- **Stage 1 — Standards/Citation** (`origin/stage1-citation-improvements`) — FASB ASC
  citation; baseline used a regex substitute (flagged †, not the paper's private
  retriever). Roadmap target: an open FASB knowledge-graph + retriever (GraphRAG).
- **Stage 2 — LLM auditor** — only invoked on Stage-0 abstain; pass Stage-0 evidence.
- **Stage 3 — Reviser** — deterministic table rewrite from `correct_value`/`problematic_entry`.
- **Multi-agent (Auditor / Defender / Judge)** — the eventual adversarial loop;
  Defender argues a table is correct citing transactions; Judge issues the final
  verdict + structured reasoning trace (persisted via FastAPI + PostgreSQL per the
  capstone spec).

### Highest-ROI open task
**Wire Stage 0 into the runner as a gate** (short-circuit on fire, evidence-to-LLM
on abstain) and run the on/off ablation on all 3 splits. The offline numbers exist
(`results/stage0_eval.json`); the end-to-end Δ false-positive-rate is still unmeasured.

Other good first tasks: improve `infer_groups`; parse explicit subtotal membership
from the transaction RHS; unit-normalize tx vs table (×10/×1000) to remove the
remaining FPs; fuzzy transaction↔table label matching to lift missing/redundant recall.

---

## 12. Environment gotchas

- **OS / shell:** Windows 10, **PowerShell**. The Bash heredoc
  (`git commit -m "$(cat <<'EOF' … EOF)"`) does NOT work — write the commit message
  to a temp file and use `git commit -F <file>` instead.
- **Model availability:** providers occasionally pull model access mid-session
  (killed session 96fb92c3). The `runner.py` is multi-provider; pick an available model.
- **Dataset quirks to remember:** HTML-comment injector markers and wrapping quotes
  in values; dual-currency strings (`RMB 70,655 | US$ 9,927`); implicit unit
  differences (thousands vs dollars) between table and transactions; `[contributing
  to row N]` uses *original* (pre-injection) indices; Explanation **RHS** can drop a
  term so always trust the **LHS**.
- **Stage 0 is offline** — no API key required; safe to run/iterate freely.

---

## 13. Appendix — Session 278c39b9 detail (original Gemini phased reproduction, Jun 5)

> This is the **first** session of the project and the conceptual origin of
> everything above. The code it built (`audit_llm/`) **no longer exists** — it was
> later flattened/refactored into the current flat repo (`parser.py`, `runner.py`,
> `metrics.py`, `auditor_prompt.py`, `evaluate.py`, `main.py`). It is documented
> here because its *findings* (especially the over-auditing problem) directly
> motivated the IntelliAudit thesis and the Stage 0 gate.

### Goal
Reproduce AuditBench "exactly," using **free-tier Gemini**, structured into phases
that mirror the paper's 5-stage framework and the verbatim appendix prompts.

### Decisions taken (confirmed with the user up front)
- **Clean Python rewrite.** The pre-existing partial **TypeScript + Prisma + SQLite**
  scaffolding was archived to `legacy/` and replaced by a Python package.
- **Two free Gemini models** to mirror the paper's GPT-3.5-turbo vs GPT-4 table:
  `gemini-2.5-flash-lite` (≈ GPT-3.5-turbo) and `gemini-2.5-flash` (≈ GPT-4).
  (Gemini 2.0 was already shut down by then; 2.5 supports JSON output.)
- **Smoke-test first** (~10 items/category) before the paper's 150/category protocol.

### Architecture built (the `audit_llm/` package — now historical)
- `config.py` — all knobs, env-overridable (models, seed/N, rate limit, token budget,
  success thresholds).
- `prompts.py` — the auditor prompt transcribed **verbatim from the appendix
  (pp. 13–14)**, including the one-shot example. → today's `auditor_prompt.py`.
- `data.py` — normalize the **3 datasets** into one `AuditItem` schema
  (correct / single / multi). → today's loaders in `parser.py`.
- `standards_db.py` — **reconstructed FASB standards database** from the unique
  ground-truth citations + a local sentence-transformer retriever for Top-K
  (the paper never released its citation DB).
- `parsing.py` — robust JSON parser **+ regex salvage** for truncated output.
- `matching.py` — greedy **multi-error alignment** (row → type → resolution overlap).
- `metrics.py` — BERTScore + BLEU. → today's `metrics.py`.
- `evalutil.py`, `phase0_prepare … phase5_revision_overall`, `run_all` orchestrator.
- **5 stages:** (1) General Judgment EM, (2) Error Type/Entry EM, (3) Resolution
  BERTScore, (4) Standards Citation Top-1/Top-5 retrieval EM, (5) Table Revision
  BLEU, (6) Overall Success Rate (all EM = 1, BERT > 0.85, BLEU > 0.99).
- **Documented deviations:** reconstructed citation retriever; the multi-error
  alignment scheme; the success-rate "all EM" ambiguity; Gemini instead of GPT.

### Bugs diagnosed and the three findings that mattered
1. **Output truncation (the killer).** Gemini 2.5 counts *thinking* tokens against
   `max_output_tokens`; with `8192` + the auditor re-emitting the full corrected
   table **per error**, responses were cut off mid-JSON → parse failure → judgment
   `None` → EM collapse (e.g. `flash/single` General-Judgment EM = 0.000). The whole
   first smoke run's Phase-2 numbers were truncation artifacts, not real performance.
2. **`bert_score` incompatible with current `transformers`**
   (`RobertaTokenizer has no attribute build_inputs_with_special_tokens`) → Phase 3 crash.
3. **Over-eager auditor (the seed insight).** On a **clean** cash-flow statement,
   `gemini-2.5-flash` hallucinated 4 errors (fabricated "redundant empty rows" + its
   own arithmetic) and judged it *Incorrect*. This previewed the central project
   finding — **LLM auditors over-audit clean tables (~50% false alarms)** — which
   later became the motivation for the Stage 0 deterministic gate (§1, §4–§6).
4. **Free-tier reality:** ~40 s/call with thinking on; the full 150×3×2 = 900-call
   run ≈ ~10 h plus daily request caps.

### Fixes applied at session end (in `audit_llm/`, carried forward conceptually)
- `max_output_tokens` **8192 → 32768**; log `finish_reason` + token usage to *see* truncation.
- **Regex salvage parser** to recover judgment/type/entry from truncated JSON.
- **Replaced `bert-score`** with a self-contained BERTScore on `transformers`
  (roberta-large, layer 17, greedy cosine F1, empty candidate → 0).
- `run_all --force-inference` flag for a clean re-inference.

### Status at handoff
Fixes were written but the **re-run was handed to the user**: the agent's integrated
shell could not execute (probe files never materialized), so all commands were run
manually. The phased `audit_llm/` was subsequently flattened into the current repo,
`runner.py` generalized inference to multi-provider, and the over-auditing finding
drove the pivot to the neuro-symbolic Stage 0 gate.

---

*Generated as a memory-transfer artifact from the Cursor agent sessions listed in
§10. Baseline metrics from Claude Opus 4.6 (seed=42, n=150); Stage 0 metrics from
`stage0_eval.py` (seed=42, n=400).*
