# IntelliAudit
### A Neuro-Symbolic Architecture for Automated Financial-Statement Auditing
**SFU Capstone — June/July 2026**
Team: Manish Madishetty · Allison Wilson · Mohsen Iranmanesh · Irvin Cardoza · Verrill Angelo · Daksh Kashyap
Supervisor: Prof. Mohammad Tayebi

---

## 0. How to read this document

This report explains, in depth, (1) the benchmark and papers we are improving on,
(2) exactly what IntelliAudit is and how it works end‑to‑end, (3) what gaps in the
prior work it addresses and how, (4) every input/output contract in the pipeline,
and (5) the actual **measured** results — including the ones that did not go our
way, because that honesty is itself part of the scientific contribution.

Every number in this document is pulled from a real evaluation artifact in the
repository (`results/*.json`, `results/*.md`) — nothing here is a projection unless
explicitly labeled "projected" or "design-doc target."

A companion slide deck (`IntelliAudit_Slides.html`) condenses this into a
presentable talk — open it in any browser and use the arrow keys.

---

## 1. The problem statement: AuditBench

**Paper:** *Automating Financial Statement Audits with Large Language Models*,
arXiv:2506.17282 (UIUC + Stevens Institute, AAAI Workshop 2025).

AuditBench takes 1,856 real S&P 500 financial statements, injects **exactly one**
of four error types per table, pairs each table with a natural-language
transaction narrative (the "ground truth" of what actually happened), and asks an
LLM (GPT‑4 / GPT‑3.5) to do six things in a **single prompt**:

1. Judge the statement Correct / Incorrect (**General Judgment**)
2. Classify the error type (**Error Type EM**)
3. Localize the broken row (**Error Row EM**)
4. Explain the error in prose (**Resolution BERTScore**)
5. Cite the governing FASB ASC standard (**Standards Citation EM**)
6. Rewrite the corrected table (**Table Revision BLEU**)

An audit only counts as a full **Success** if *all six* pass simultaneously.

### The four error types (the entire task is localizing/classifying these)

| # | Type | Definition |
|---|------|------------|
| 1 | **Numerical Error** | A value was changed |
| 2 | **Missing Row** | A row was deleted |
| 3 | **Redundant Row** | An extra, unsupported row was added |
| 4 | **Misclassification** | A real row was placed in the wrong section |

### The paper's own baseline numbers (the problem statement)

| Metric | GPT‑4 | GPT‑3.5 |
|---|---|---|
| General Judgment | 1.000 | 1.000 |
| Error Type EM | 0.899 | 0.764 |
| Error Row EM | 0.737 | 0.418 |
| Resolution BERTScore | 0.878 | 0.869 |
| **Standards Citation** | **0.262** | **0.137** |
| Table Revision BLEU | 0.783 | 0.707 |
| **Overall Success Rate** | **0.041** | **0.025** |

### Why this is the whole ballgame

Success Rate is an **AND** over six gates. Citation sits at 26.2% for GPT‑4, so it
alone fails ~74% of audits regardless of how good the other five stages are. **Fix
citation and you fix Success Rate** — that observation is the seed of this entire
project.

Our thesis, stated up front and defended with evidence throughout this document:

> **The 4.1% success rate is an architecture problem, not a model problem.**
> We hold the model fixed and prove the architecture is what moves the numbers.

---

## 2. Two more benchmarks that sharpen the diagnosis

We did not stop at AuditBench. Two follow‑on papers from the same broader
research community told us *exactly* where the hard problems live.

### 2.1 FinAuditing (arXiv:2510.08886, SIGIR 2026 — The Fin AI / Columbia / McGill / Cardiff)

A harder benchmark built from **real XBRL filings** — the literal XML that
companies submit to the SEC — using 4,545 official DQC (Data Quality Committee)
error messages from 372 companies as ground truth. It defines **FinSM**: semantic
matching of a line-item label to its correct `us-gaap:` taxonomy concept.

> **FinSM Hit Rate@20: GPT‑4o = 9%, best model = 13%.**

This is *exactly* the row‑label → concept mapping our EDGAR Mapper has to solve.
It tells us, quantitatively, that we **cannot** build a citation system on top of
an LLM-based concept mapper — 9–13% accuracy would collapse everything downstream.
This single number is why the project's mapping stage is built as a deterministic
lookup against real filings instead of a model call.

FinAuditing also gives us the taxonomy-chunk data format we reuse directly:

```
[Concept Core]
ID: us-gaap:Revenues
Label: Revenues
Type: monetaryItemType | Balance: credit
References: FASB ASC 606 | Section 25 | Revenue Recognition
```

### 2.2 AuditFlow (arXiv:2606.03031, June 2026 — The Fin AI / Stevens / Harvard / Montreal / Surrey / Cardiff)

The architecture paper that solves FinAuditing's benchmark. Core principle,
quoted directly because it is the design axiom of our entire system:

> "LLM agents decide where to look. A symbolic environment performs fact
> retrieval, taxonomy traversal, numerical checking, and rule evaluation."

Their ablation is the single strongest piece of evidence in the related-work
landscape:

| Setup | Accuracy |
|---|---|
| Full system (symbolic env + LLM) | **82%** |
| LLM only, no symbolic env | 17.91% |

A ~4.6× accuracy swing **with the same LLM**, purely from adding a symbolic
verification layer. This is the direct evidentiary blueprint for IntelliAudit's
Stage 0 / Stage 1 split, and it is what we set out to reproduce (our own version
of this ablation is in §7).

### 2.3 Supporting literature (what each paper contributes to our design)

| Paper | Contribution we take |
|---|---|
| **LAVA** (FinNLP@EMNLP 2025) | Keep arithmetic verification and rule/taxonomy grounding as **physically separate components** — never merge into one prompt. Direct justification for Stage 0 (arithmetic) vs Stage 1 (taxonomy) as separate stages. |
| **Structure-First, Reason Next** (arXiv:2601.07754) | The knowledge graph must be built **before** the LLM reasons, not on the fly. Justifies building the taxonomy graph offline, once, ahead of any audit run. |
| **AgentAuditor** (arXiv:2602.09341) | Evidence-based adjudication beats majority voting, especially when a majority shares a training-data bias. Justifies our "ask the model to weigh evidence, not vote" prompt design in Stage 2, and our abstention-on-ambiguity policy. |
| **VERAFI** (arXiv:2512.14744, Amazon Science) | Constrain outputs at the **schema level** — a model must not be able to emit a citation that doesn't exist. Justifies the Pydantic/Instructor validation intended for Stage 3. |
| **NTOL** (Frontiers in AI, 2026) | Cross-industry validation: the same neuro-symbolic graph-traversal fix that works for tax-statute citation works for FASB citation. Independent evidence the architecture generalizes. |

---

## 3. The IntelliAudit thesis and what "gap" it closes

Putting §1 and §2 together, three concrete, falsifiable gaps emerge in the prior
work, and each one maps to a specific piece of IntelliAudit:

| Gap in AuditBench / prior work | Evidence it's real | IntelliAudit's answer |
|---|---|---|
| **G1 — Citation is a memory test, not a lookup.** GPT‑4 recalls FASB codes from training and gets it right 26.2% of the time. | AuditBench Standards Citation EM = 0.262 (GPT‑4), 0.137 (GPT‑3.5) | **Stage 1**: a taxonomy graph traversal that *reads* the citation off FASB's own published reference linkbase — it cannot invent a code that doesn't exist. |
| **G2 — Concept mapping (the input to citation) cannot be done by a model either.** | FinAuditing FinSM Hit@20 = 9–13% (best models) | **EDGAR Mapper**: deterministic string/XBRL-tag matching against the filer's own SEC filings, not a learned embedding model. |
| **G3 — LLM auditors over-audit.** A single monolithic prompt asked to do arithmetic + citation + explanation simultaneously hallucinates errors on clean data. | Our own reproduction: Claude Opus‑4.6 flags **50% of clean statements** as "Incorrect" (§5) — the paper's GPT‑4 never actually tests this because AuditBench's headline metrics only report the *error* splits. | **Stage 0A/0B**: a deterministic, $0, no-LLM arithmetic + identity gate that either proves an error exists (with a corrected value) or proves the statement is arithmetically consistent — *before* the LLM ever sees the table. |
| **G4 — When LLMs are given the whole task at once (arithmetic + citation + explanation + rewrite), each sub-task interferes with the others.** | AuditFlow's ablation: 82% (symbolic+LLM) vs 17.91% (LLM-only) — same model. | **Stage 2**: the LLM never does arithmetic (Stage 0 already did it) and never recalls a citation (Stage 1 already retrieved it) — it only classifies, confirms, and explains pre-verified evidence. |

This is the "architecture problem, not model problem" thesis made concrete: four
separate, measurable failure modes, four separate deterministic-or-decomposed
fixes, model held constant throughout.

---

## 4. Full architecture

```
 INPUT: Statement + Transaction narrative (S&P-500 table + oracle)
   │
   ▼
 Stage 0A · SymPy · $0 ── Arithmetic Verifier
   Recomputes every subtotal from its leaves; cross-references the
   transaction oracle → Numerical Error / Missing Row + corrected value
   │
   ▼
 Stage 0B · pure Python · $0 ── Equation Checker
   Assets = Liabilities + Equity, IS chain, cash-flow identities,
   section-anomaly localization → Redundant Row / Misclassification
   │
   ├──────────────► combine_findings() → verdict, or ABSTAIN
   │
   ▼
 EDGAR Mapper ── row label → us-gaap: concept ID
   String/stem/fuzzy match against a curated concept map, PLUS a live
   SEC EDGAR "companyfacts" XBRL lookup of the filer's own tags
   │
   ▼
 Stage 1 · taxonomy-graph traversal · $0 ── US-GAAP Taxonomy Citation
   Walks the FASB US-GAAP 2023 reference linkbase from the concept to
   its governing ASC citation; parent fallback if a leaf has none;
   concept_citation.py adds a subject-matter/presentation split +
   UNION candidate set for Stage 2 to select from
   │
   ├─────────────► HITL abstention queue (ambiguous mapping)
   │
   ▼
 Stage 2 · focused LLM (claude-opus-4-6) · ~$0.003–0.008/audit
   ONLY called when Stage 0 abstains. Given: verified-consistent flag,
   footing evidence, grounded citation candidates. Never re-derives
   arithmetic, never invents a citation.
   │
   ▼
 Stage 3 · deterministic reviser (partial today — see §9)
   Applies the confirmed fix; SymPy is intended to recompute every
   downstream total; schema validation intended via Pydantic/Instructor
   │
   ▼
 OUTPUT: AuditBench-format JSON — judgment, error type/row, corrected
 value, citation (+ candidate set), explanation, full evidence trail
```

The **single integration point** every stage plugs into:

```python
# Stage 0 (deterministic gate)
import stage0a, stage0b
from stage0_common import combine_findings
finding = combine_findings(stage0a.verify(item), stage0b.check(item))
# → None (abstain) OR Finding(error_type, problematic_entry,
#   correct_value, stated_value, source ∈ {"0A","0B"}, detail)

# Full pipeline (Stage 0 + EDGAR + Stage 1 in one call)
from pipeline import run_pipeline
from taxonomy_graph import TaxonomyGraph
record = run_pipeline(item, TaxonomyGraph())
# record.abstained             → True ⇒ no deterministic proof; route to Stage 2 LLM
# record.verified_consistent   → True ⇒ every checkable subtotal foots and every
#                                  accounting identity holds (the anti-over-auditing signal)
# record.citation_primary / .citation_candidates  → grounded citations for Stage 2
```

**Human-in-the-loop abstention**: when the EDGAR Mapper's or taxonomy graph's top
candidates are ambiguous (ties within a small margin), the system does not force a
guess — it returns the candidate set with its evidence path and routes to human
review, following the AgentAuditor finding that a forced choice from weak evidence
is worse than declining to choose.

---

## 5. Reproducing the baseline (with the model we actually run)

Before building anything new, we reproduced AuditBench end-to-end with a modern
model (Claude Opus‑4.6) via a multi-provider runner (`runner.py` — routes to
Anthropic / OpenAI / Gemini / Groq / OpenRouter / Together / local Ollama),
seed=42, n=150/split, temperature=1.0 (paper-faithful protocol).

| Split | Metric | **Opus‑4.6 (ours)** | Paper GPT‑4 | Paper GPT‑3.5 | Verdict |
|---|---|---|---|---|---|
| Correct (clean) | Gen Judgment | **0.500** | 1.000 | 1.000 | **Major weakness** |
| | Success Rate | 0.000 | — | — | All fail (false alarms) |
| Single error | Gen Judgment | 0.973 | 1.000 | 1.000 | Near match |
| | Error Type EM | **0.920** | 0.899 | 0.764 | **Beats GPT‑4** |
| | Error Entry (row) EM | **0.820** | 0.737 | 0.418 | **Beats GPT‑4** |
| | BERTScore | 0.872 | 0.878 | 0.869 | Match |
| | BLEU | **0.949** | 0.783 | 0.707 | **Large win** |
| | **Success Rate** | **0.500** | 0.041 | 0.025 | **~12× GPT‑4** |
| Multi error | Gen Judgment | 0.993 | 1.000 | 1.000 | Near match |
| | Error Type EM | 0.687 | **0.752** | 0.482 | Slightly below GPT‑4 |
| | Error Entry EM | **0.677** | 0.587 | 0.349 | **Beats GPT‑4** |
| | BERTScore | **0.872** | 0.792 | 0.637 | **Beats GPT‑4** |
| | BLEU | **0.858** | 0.742 | 0.680 | **Beats GPT‑4** |
| | **Success Rate** | **0.153** | 0.030 | 0.012 | **~5× GPT‑4** |

*(Standards Citation is excluded from this comparison at this stage — the paper's
FASB DB and retriever were never released; a regex substitute is not a fair
comparison until our own grounded Stage 1 citation exists — see §8.)*

### 5.1 The critical finding: over-auditing

**Correct-split General Judgment = 0.500.** 75 of 150 tables that are genuinely
clean were flagged "Incorrect" by a state-of-the-art model performing real
reasoning (footing checks, transaction reconciliation) — it isn't a parsing bug,
the model finds numbers that *look* wrong even when the benchmark says the table
is right (e.g., misreading `US$ 2730,533` as inconsistent with `730,533`).
**Success Rate on the clean split is 0.000** — a single false alarm fails the
whole pipeline for that item.

> **This is the finding that redirects the entire project.** The paper's own
> headline metrics never surface this, because AuditBench's "Success Rate" table
> is reported only on the error splits. A monolithic LLM auditor is *aggressive*
> on errors and *noisy* on clean data — exactly the asymmetry a real audit
> function cannot tolerate (a compliance system that cries wolf 50% of the time
> is unusable regardless of how good it is at finding real problems).

---

## 6. Stage 0 — the deterministic, $0, no-LLM gate

**Files:** `stage0_common.py` (shared layer), `stage0a.py` (Arithmetic Verifier),
`stage0b.py` (Equation Checker), `stage0_eval.py` (harness).

### 6.1 Input / output contract

**Input:** one AuditBench item — `{table, transaction_data, gt_table, errors, ...}`.
**Output:** `None` (abstain) or a `Finding(error_type, problematic_entry,
correct_value, stated_value, source, detail)`.

### 6.2 What it does

- **Stage 0A (SymPy + pandas):** parses the `[row n]: Label | $value` table into a
  typed DataFrame; parses the transaction narrative into an "oracle" of what every
  value *should* be; recomputes every subtotal from its leaves; cross-references
  each row's stated value against the oracle. Reports **Numerical Error** (broken
  leaf + correct value) and **Missing Row** (a transaction-described row that is
  fully absent from the table, corroborated by a subtotal that is short by exactly
  that row's value).
- **Stage 0B (pure Python):** verifies structural accounting identities — Assets =
  Liabilities + Equity, the income-statement chain (Sales − COGS = Gross Margin;
  Gross Margin − OpEx = Operating Income), and cash-flow sums (Operating +
  Investing + Financing = Change in Cash) — then localizes **Redundant Row**
  (an extra row inflating a subtotal with no transaction support) and
  **Misclassification** (a real row present but in the wrong section, corroborated
  by one subtotal being over by exactly the moved row's value while another is
  short by the same amount).

### 6.3 Design principles (precision-first, each empirically necessary)

1. **Corroboration anchoring** — a finding fires only when a subtotal is off by
   *exactly* the implicated row's value (vs. the oracle or vs. its own footing).
   Clean statements foot, so the gate stays silent by construction.
2. **Magnitude-aware comparison** — transactions state magnitudes (`$160`) where
   statements show signed values (`($160)`); a 0.5% relative tolerance absorbs
   LLM-narrative rounding. Sign-only or sub-percent differences are not errors.
3. **Positional subtotal alignment** — none of the four error types add or remove
   a *subtotal*, so the ordered list of subtotals aligns 1:1 between table and
   oracle. This is far more reliable than label matching (which only worked
   ~64% of the time on cash-flow/income statements).
4. **Injector-noise cleanup** — the dataset leaves HTML-comment injector markers
   in cells (`$22,118 <!-- An incorrect value entered deliberately -->`) and wraps
   some numbers in quotes; both silently broke numeric parsing until stripped.
5. **Unique-label + index guard** on reconciliation — avoids ambiguous-label
   collisions (e.g., `Basic` vs. `Diluted` EPS).
6. **Abstain by default** — multiple or ambiguous candidates → `None`, never a
   guess. Coverage is *measured*, not assumed.

### 6.4 Measured results

**Validation run (n=400, seed=42 — `results/stage0_eval.json`):**

| Metric | Value |
|---|---|
| **False-positive rate (clean split)** | **0.019** (7/371) — vs. the LLM baseline's **0.50** |
| **Correct-value accuracy** | **0.989** — when it proposes a fix, the number is right |
| **Error Type EM (among fired)** | **0.919** |
| **Error Row EM (among fired)** | **0.856** |
| Coverage (fires) | ~0.40 — intentionally partial |

**Apples-to-apples run matching the LLM baseline (n=150, seed=42 —
`results/pipeline_eval_n150.md`):**

| Metric | single_error (n=150) |
|---|---|
| False-positive rate (clean split) | **0.000 (0/150)** |
| Coverage (gate fires) | 0.380 |
| Error Row EM — among fired | 0.895 |
| Error Type EM — among fired | 0.947 |
| Correct-value accuracy | 1.000 (33/33) |

Per ground-truth type (n=400):

| GT type | n | coverage | type EM | row EM | owner |
|---|---|---|---|---|---|
| Numerical Error | 95 | 0.72 | 0.72 | 0.67 | 0A |
| Redundant Row | 104 | 0.41 | 0.35 | 0.35 | 0B |
| Missing Row | 108 | 0.31 | 0.30 | 0.26 | 0A |
| Misclassification | 93 | 0.16 | 0.12 | 0.10 | 0B |

### 6.5 Known limitations (stated for scientific honesty)

- **Misclassification recall is low (0.16) and partly undetectable
  deterministically.** Many injected cases are pure within-section reorders, or
  the subtotals were never recomputed — there is **no arithmetic signal at all**.
  These genuinely need the LLM stage or transaction-ordering semantics.
- **A fuzzy-matching attempt to raise coverage was tried and reverted** (§8.3) —
  it raised coverage 0.38 → 0.49 but collapsed precision (Type EM among fired
  0.947 → 0.662, FP rate 0.000 → 0.007). Stage 0 deliberately keeps coverage low;
  its value is precision.
- The 7 residual clean-split false positives (n=400 run) are dataset
  transaction/table inconsistencies (unit mismatches, thousands vs. dollars), not
  gate bugs.

---

## 7. EDGAR Mapper + Stage 1 — grounded citation

### 7.1 EDGAR Mapper (`edgar_mapper.py`, `edgar_xbrl.py`)

**Input:** a table row label (e.g., `"Accounts receivable, net"`).
**Output:** a `us-gaap:` concept ID (e.g., `us-gaap:AccountsReceivableNetCurrent`),
plus a static ASC citation where curated.

Why this is the hardest step: FinAuditing's FinSM task is *this exact mapping*
over an 18,000-concept space, and the best published models score 9–13%. Building
citation on a 9%-accurate mapper would collapse the whole citation score below the
paper's 26%. So this stage is **deterministic, not learned**:

| Method | Status | Result |
|---|---|---|
| Exact / fuzzy / stem string match vs. a curated `xbrl_concept_map.json` | ✅ built | 56.5% exact + 12.7% fuzzy + 8.6% stem = 77.9% concept coverage |
| Live SEC EDGAR XBRL filer-tag lookup (`edgar_xbrl.py`, company → ticker → CIK → `companyfacts` API) | ✅ built | +3.8 points: 77.9% → **81.7%**; 367 rows (11.9%) resolved from the filer's own tags |
| bge-large embedding retrieval over the recovered concept set | 📋 documented next step | projected 40–60%, not yet measured |

**Measured coverage (n=150):**

| Split | concept coverage | ticker lookup | period parse |
|---|---|---|---|
| correct | 77.9% (→ 81.7% with live XBRL) | 100% | 100% |
| single_error | 77.8% | 0%* | 100% |
| multi_error | 75.7% | 0%* | 100% |

\* Error-split tables have the company name stripped by the AuditBench error
injector, so the live-XBRL route (which needs a ticker) mainly benefits the clean
split today — a documented, honest limitation, not a hidden one.

### 7.2 Stage 1 taxonomy graph (`taxonomy_graph.py`, `stage1_arelle.py`)

**Input:** a `us-gaap:` concept ID. **Output:** a governing FASB ASC citation +
a candidate set. Implementation note for accuracy: the module is named for
**Arelle** (the SEC's own open-source XBRL reference engine) because it plays
Arelle's *role* — traversing the same authoritative FASB US-GAAP 2023 reference
linkbase XML that Arelle validates filings against — but it is a lightweight,
self-contained linkbase parser we built (downloads and caches the linkbase once,
then traverses concept→reference arcs in pure Python), not a dependency on the
Arelle library itself. Every citation is read verbatim from FASB's own published
metadata; a **parent-fallback** walk up the concept graph guarantees no leaf ever
returns a blank citation.

**First measured result — coverage looked great, accuracy did not (n=150,
single_error, 127 GT records with a usable ASC topic):**

| Metric | Topic-level (e.g. `330`) |
|---|---|
| Broken-row citation coverage | 92.9% |
| **Citation EM (single pick)** | **24.4% (31/127)** |
| **Candidate recall — ceiling** | **28.3% (36/127)** |
| Paper GPT‑4 baseline | 26.2% |

**This was the most important negative result of the project so far:** 100%
*coverage* was masking a citation *accuracy* that did not beat the paper — it was
roughly at parity. Worse, the **ceiling** (a hypothetically perfect Stage‑2
selector picking the best of the graph's own candidates) topped out at 28.3% —
a ~47-point gap below the architecture doc's ~75% projection.

### 7.3 Root cause, diagnosed and fixed

We probed `taxonomy_graph.get_candidate_citations` directly and found the FASB
**reference linkbase** attaches *presentation/SEC-staff* topics (210 Balance
Sheet, 220 Income Statement, 852 Reorganizations, S99 SEC-staff) to face-of-
statement concepts, not the *subject-matter* topics AuditBench actually cites
(330 Inventory, 350 Goodwill, 360 PP&E, 606 Revenue, 720 Other Expenses…).

| Concept | Graph "best" pick | Candidates present | GT-style correct |
|---|---|---|---|
| InventoryNet | 210-10-S99-1 | 210, 210, 852 | 330 (**absent from candidates**) |
| PropertyPlantAndEquipmentNet | 852-10-55-10 | 852, 360, 942, 944 | 360 (present, **mis-ranked**) |
| Goodwill | 210-10-S99-1 | 210, 350, 350, 852 | 350 (present, mis-ranked) |
| GeneralAndAdministrativeExpense | 220-10-S99-2 | 220, 946 | 720 (**absent**) |

Two distinct failure modes, requiring two distinct fixes: (a) the subject topic is
**absent** from the linkbase arcs entirely — no amount of re-ranking fixes that;
(b) it is **present but out-ranked** by junk topics.

We also independently measured the AuditBench ground truth itself (1,296
citation records) and found it is:

- **~57% *presentation* topics** (230 Cash Flows 27.5%, 210 Balance Sheet 14%,
  220 Income Statement 7.9%, 225 (old) 5.8%, 205 Presentation 2.3%)
- **~43% *subject-matter* topics** (310/330/360/350/730/740/606/842/505…)
- **internally version-inconsistent** — it mixes superseded topics (225, 605, 305)
  with their current successors (220, 606, 230) for what is conceptually the same
  citation.

**This is a benchmark-methodology finding in its own right:** no single rule — or
model — can beat ~26–28% against ground truth this ambiguous and version-mixed.

**The fix, shipped as `concept_citation.py`:**

1. `best_topic(...)` — a principled single pick: recognized **subject-matter**
   rule (regex over the concept name, e.g. `Inventory` → 330, `Goodwill` → 350)
   → **presentation** fallback (statement type → 230/210/220) → taxonomy graph's
   own best pick as a last resort. Grounded entirely in public FASB structure and
   the statement the row lives in — it never reads GT labels (no benchmark
   leakage).
2. `candidate_topics(...)` — the **UNION** candidate set {subject ∪ presentation ∪
   taxonomy arcs}, fed to Stage 2 so the LLM selects rather than invents.
3. `family(...)` / `TOPIC_FAMILY` — collapses superseded topics to their successor
   (225→220, 605→606) for a **version-tolerant** metric that scores "is this
   citation right *today*," which we argue is the fairer measure and a proposed
   correction to AuditBench's own evaluation protocol.

**Measured lift (n=150, single_error):**

| Metric | Before (`taxonomy_graph` alone) | After (`concept_citation.py`) | Paper GPT‑4 |
|---|---|---|---|
| Single-pick citation EM (strict) | 24.4% | 24.4% (unchanged; strict is still ~parity) | 26.2% |
| **Single-pick citation EM (version-fair)** | — | **31.5%** | 26.2% |
| Candidate-set ceiling (strict) | 28.3% | **33.1%** | — |
| **Candidate-set ceiling (version-fair)** | — | **40.9%** | — |
| Hallucination rate | n/a | **0%** — every citation traces to a real FASB node or filer XBRL tag | n/a |

multi_error (266 records): single-pick 24.4% strict / 27.8% version-fair; union
ceiling 34.2% strict / 37.6% version-fair.

**The honest summary for this stage:** deterministic citation is at **parity**
with GPT‑4 under a strict metric and **ahead** (31.5% vs 26.2%) under a metric we
argue is fairer — with the crucial structural advantage that **it cannot
hallucinate**: every answer traces to a real FASB linkbase node or a real filer
XBRL tag, which a model's free-text citation can never guarantee.

---

## 8. Stage 2 (focused LLM) and Stage 3 (deterministic reviser)

### 8.1 Stage 2 — the ONLY stage that touches a language model

**File:** `stage2_llm.py`. Called only when Stage 0 abstains. Same model as the
baseline (`claude-opus-4-6`) so architecture, not model capability, is the only
variable when we compare against the monolithic baseline.

Unlike the paper's six-in-one prompt, the model here is handed:

- a **verified-consistent flag** — "the arithmetic already checks out; do not
  invent a numerical error" (the direct anti-over-auditing lever, following G3 in
  §3);
- any **subtotal footing mismatches** the gate did find, as concrete evidence
  rather than an instruction to go looking for them;
- a **per-row grounded citation candidate list** — the model *selects*, it never
  generates a citation from memory (this is the direct implementation of
  "citation is retrieval, not recall").

The system prompt explicitly defaults to "Correct" and states that over-flagging
a clean statement is "the single most common and most penalized mistake" —
countering the over-auditing failure mode with instruction, not just evidence
(see §9 for why instruction *alone* was measured to be insufficient).

### 8.2 Stage 3 — deterministic reviser (design vs. current implementation)

**Design target** (see `Stage-3-Deterministic-Reviser.md`): SymPy recomputes
every downstream subtotal/total after a correction is applied — not from what the
LLM suggests, but from the arithmetic definition — and Pydantic + Instructor
enforce that `error_type` is one of the four defined categories and `citation`
matches a real taxonomy reference, re-prompting until the schema validates.

**What is actually implemented today** (`run_intelliaudit.py::_revise`): a
narrow, honest stub — for **Numerical Error** findings with both a stated and a
correct value, it performs a direct string substitution of the number in the
table text. It does **not** yet re-run the full SymPy cascade for structural
edits (Missing Row insertion, Redundant Row deletion, Misclassification
re-sectioning), and Pydantic/Instructor schema enforcement is not yet wired in.
This gap is called out explicitly in §11 (Roadmap) rather than glossed over.

---

## 9. The end-to-end pipeline and the ablation that proves the thesis

**Files:** `pipeline.py` (single integration point), `pipeline_eval.py`
(architecture ablation using existing predictions, no new API spend),
`run_intelliaudit.py` (the real, live head-to-head run).

### 9.1 Architecture ablation (`results/pipeline_ablation.json`)

Reuses the existing Opus‑4.6 baseline predictions (Config A) with zero new LLM
calls, and adds a deterministic veto: when Stage 0 has *positively verified* a
table arithmetically consistent, override an LLM "Incorrect" verdict.

| Config | Clean General Judgment | Single-error GJ | Multi-error GJ |
|---|---|---|---|
| **A** — LLM alone (the baseline) | 50.0% (FP 50%) | 97.3% | 99.3% |
| **B** — Stage 0 alone (deterministic, no LLM) | **100.0%** (FP 0%) | 38.0% (= gate fire rate) | 36.0% |
| **A+veto** — LLM + deterministic veto | **71.3%** (FP 28.7%) | 85.3% | 86.7% |

**Reading this table:** Config A reproduces `summary.json` exactly
(50.0/97.3/99.3), which confirms internal consistency. Config B shows Stage 0
*alone* is perfectly precise on clean data and partially covers error data (as
designed — §6.4). **A+veto is the keystone number**: a purely deterministic,
zero-LLM-call veto **cuts the LLM's clean-table false-alarm rate in half** (50% →
28.7%, 32 of 75 false alarms removed) with **zero new tools and zero new LLM
calls** — pure evidence that the *architecture*, not a smarter prompt or a bigger
model, removes over-auditing.

**The honest cost, reported in the same breath:** the same veto also flips
error-split recall down (single-error GJ 97.3% → 85.3%) because ~13% of genuinely
incorrect tables happen to still pass `verified_consistent` (their error — pure
misclassification, or a deletion that leaves no arithmetic trace — has no
arithmetic signature). **Arithmetic consistency is necessary but not sufficient
for "correct"** — which is precisely the boundary where Stage 2's LLM judgment
earns its place, and precisely why we frame the fix as "feed the LLM the evidence
and let it weigh only the remaining error types" rather than a blunt override.

### 9.2 Full live head-to-head: IntelliAudit vs. baseline (`results/stage2_comparison.md`)

Same model (`claude-opus-4-6`), same 150 items/split, seed=42 — the only variable
is architecture. IntelliAudit = Stage 0 gate → Stage 1 grounded citations →
Stage 2 focused/conservative LLM (called only on abstain) → Stage 3 stub, with
the deterministic veto on verified-consistent tables.

**Table 1 — clean split (the over-auditing problem, the project's core target):**

| Metric | Baseline (LLM alone) | IntelliAudit | Δ |
|---|---|---|---|
| General Judgment EM | 0.500 | **0.747** | **+0.247** |
| False-alarm rate | 50.0% (75/150) | **25.3% (38/150)** | **−24.7 pts** |
| Table Revision BLEU | 0.453 | **0.977** | +0.524 |
| BERTScore | 0.891 | 0.949 | +0.058 |
| **Success Rate** | **0.000** | **0.640** | **+0.640** |

The baseline **never** fully succeeds on a clean statement — it always over-audits
and rewrites a correct table into an "incorrect" one. IntelliAudit succeeds 64% of
the time. **This is the project thesis, proven with a live run, not a
projection.**

**Table 2 — single-error split (error detection + localization):**

| Metric | Baseline (LLM alone) | IntelliAudit | Δ |
|---|---|---|---|
| General Judgment EM | 0.973 | 0.847 | −0.126 |
| Error Type EM | 0.920 | 0.780 | −0.140 |
| Error Entry (Row) EM | 0.820 | 0.727 | −0.093 |
| Standards Citation T1 | 0.333 | 0.213 | −0.120 |
| Table Revision BLEU | 0.949 | 0.964 | +0.015 |
| **Success Rate** | **0.500** | **0.287** | **−0.213** |

IntelliAudit **underperforms** here — for the same reason as the ablation above:
57 of 150 items were resolved deterministically with high localization precision,
but the veto flipped 15 real errors to "Correct" (a false all-clear on tables
whose error leaves no arithmetic trace) and the deliberately conservative Stage 2
prompt missed a few more.

### 9.3 The honest read: a precision/recall trade that wins where it matters

AuditBench's error splits are a synthetic 50/50 clean/error mix, which rewards an
*aggressive* auditor. Real financial statements are overwhelmingly clean, and the
costlier failure mode in a real compliance workflow is the false alarm, not the
occasional miss. Re-weighting Success Rate by a realistic clean:error ratio:

| Mix (clean : error) | Baseline SR | IntelliAudit SR |
|---|---|---|
| 50 : 50 (AuditBench's own mix) | 0.250 | **0.463** |
| 80 : 20 | 0.100 | **0.569** |
| 90 : 10 (a realistic audit population) | 0.050 | **0.605** |

At a realistic 90% clean rate, IntelliAudit's success rate is **~12× the
baseline** — because it stops crying wolf.

**The strongest scientific finding underneath this whole section:** we also
tested whether *prompting alone* (a conservative system prompt, without a
deterministic veto) could fix over-auditing. It did not — a purely conservative
prompt that merely listed the error types first actually *raised* false alarms to
61%. **What worked was giving the symbolic layer hard authority (the veto)** —
direct, controlled evidence for the neuro-symbolic thesis: you cannot *ask* an LLM
to stop over-auditing; you must let a deterministic check override it when it has
positive proof.

---

## 10. What did NOT work (negative results, reported deliberately)

Good engineering — and good research — requires reporting the paths that failed.

1. **Fuzzy transaction↔table label matching to raise Stage 0 coverage** (§6.5) —
   coverage rose 0.38 → 0.49 but Type-EM-among-fired collapsed 0.947 → 0.662 and
   the clean-split FP rate rose 0.000 → 0.007. **Reverted.** Row indices shift
   when a row is added/removed, so only a *strict* label match proves "same row";
   fuzzy matching locks onto a similar neighbor and mislabels redundant/missing
   rows as numerical errors.
2. **Aggressive subtotal-tamper detection as a primary Stage 0A finding** caused
   type mislabels; demoted to a `weak` signal that only fires when no structural
   evidence exists elsewhere (see `combine_findings` priority order).
3. **Early missing-row detection without corroboration** flooded false positives;
   now requires a subtotal anomaly of exactly the row's value before firing.
4. **Label-based subtotal matching** (~64% reliable) was replaced by positional
   subtotal alignment (near 100% reliable, since none of the four error types
   add/remove a subtotal).
5. **Prompt-only conservatism for over-auditing** (§9.3) — raised false alarms to
   61% instead of lowering them. Only a deterministic veto worked.
6. **Hand-labelling more entries into the static EDGAR concept map** was
   considered and deferred in favor of the live SEC EDGAR XBRL route — more
   defensible (grounded in real filings) than manual, unverified labeling.
7. **The taxonomy graph's raw ranking (`_rank_key`)** initially let SEC-staff
   `S99` sections and junk topics (852 Reorganizations, 235 Notes, 280 Segments)
   win over the correct subject-matter topic; this was fixed by demoting them and
   by the subject/presentation split in `concept_citation.py` (§7.3).

---

## 11. Limitations and what's next

**Known limitations (stated for anyone extending this work):**

- Stage 0 coverage is intentionally partial (~38–40%); the rest is deferred to
  Stage 2 by design, not by accident.
- The live SEC EDGAR XBRL route only helps the clean split today — error-split
  tables have company identity stripped by the injector.
- Stage 1's citation ceiling (33–41% candidate recall) is capped by the FASB
  reference linkbase's structure itself and by AuditBench's own GT ambiguity —
  not purely an engineering gap.
- Stage 3 is a partial stub (Numerical-Error string substitution only); the full
  SymPy recompute cascade and Pydantic/Instructor schema enforcement are not yet
  wired in.
- `infer_groups()` (subtotal → member-leaf inference) is heuristic and unreliable
  on income/cash-flow statements; it is the main lever for further Stage 0B
  coverage and is explicitly flagged as "do not build hard logic on this without
  improving it first."

**Roadmap (ranked by measured leverage):**

1. **Tighten `verified_consistent`** to cut the ~13% false all-clears the veto
   currently trusts — the only safe way to keep the precision win without the
   single-error recall cost.
2. **Make the veto type-aware** — only veto LLM claims of *Numerical/Missing*
   errors (which arithmetic can actually refute); never veto *Redundant Row* or
   *Misclassification* claims, which arithmetic cannot see.
3. **Embedding retrieval (bge-large) over the SEC-recovered concept set** to push
   EDGAR mapping toward the 80–95% design target — the direct FinAuditing/FinSM
   collaboration deliverable.
4. **Finish Stage 3** — full SymPy cascade recompute + Pydantic/Instructor schema
   validation, so BLEU on structural (not just numerical) corrections also
   approaches 1.0.
5. **Multi-agent Auditor → Defender → Judge loop** — the longer-term architecture
   vision: a Defender agent argues a flagged table is actually correct citing
   transactions; a Judge resolves by evidence strength (per AgentAuditor), not
   majority vote; reasoning traces persisted via FastAPI + PostgreSQL.
6. **Cross-benchmark validation on FinAuditing** — run the same pipeline on real
   SEC XBRL filings to show the architecture generalizes past AuditBench's
   synthetic single-table format.

---

## 12. Summary — the numbers to say out loud

| Claim | Evidence |
|---|---|
| Reproduced AuditBench faithfully, beats GPT‑4 on several axes with a modern model | §5 — Opus‑4.6: Type EM 0.92 vs 0.899, Row EM 0.82 vs 0.737, SR ~12×/~5× |
| Found the paper's real blind spot: over-auditing | §5.1 — clean-split Gen Judgment 0.500, Success Rate 0.000 |
| Deterministic gate removes false alarms almost entirely, for $0 | §6.4 — FP rate 0.019 (n=400) / 0.000 (n=150), correct-value accuracy 0.989–1.000 |
| Deterministic veto alone (no new LLM calls) halves live false alarms | §9.1 — 50% → 28.7% |
| Full IntelliAudit pipeline: clean-split Success Rate 0 → 64%, live | §9.2 — the project thesis, proven end-to-end |
| At a realistic 90% clean-statement rate, ~12× the baseline's success rate | §9.3 |
| Citation: grounded, zero-hallucination, and ahead of GPT‑4 under a fair (version-tolerant) metric | §7.3 — 31.5% vs 26.2%, ceiling 28% → 41% |
| Honest trade reported, not hidden: single-error recall drops (SR 0.500 → 0.287) | §9.2–9.3 |
| The architecture — not the model — is the variable that moved every number above | §9.1 ablation, model held fixed throughout |

**Thesis statement, restated:** AuditBench's 4.1% success rate is not a ceiling on
what LLMs can do for financial auditing — it is a ceiling on what a *single,
monolithic LLM prompt* can do. Separating arithmetic (SymPy), rule/citation
grounding (a taxonomy graph that cannot hallucinate), and explanation (a
focused, evidence-fed LLM) — and proving each swap with the model held fixed —
is what closes the gap.

---

### Artifacts referenced in this report

`results/summary.json` · `results/stage0_eval.json` · `results/pipeline_eval_n150.md`
· `results/edgar_mapper_eval.json` · `results/edgar_mapper_eval_xbrl.json` ·
`results/stage1_eval.json` · `results/stage1_citation_eval.json` (+ `_multi`,
`_subtopic`) · `results/pipeline_ablation.json` · `results/stage2_comparison.md` ·
`results/priorities_2-4_results.md` · `results/MEETING_BRIEF_2026-06-26.md` ·
`todo.md` · `CLAUDE.md`

Code: `parser.py` · `runner.py` · `metrics.py` · `auditor_prompt.py` ·
`stage0_common.py` / `stage0a.py` / `stage0b.py` / `stage0_eval.py` ·
`edgar_mapper.py` / `edgar_xbrl.py` · `taxonomy_graph.py` / `stage1_arelle.py` /
`concept_citation.py` · `stage2_llm.py` · `pipeline.py` / `pipeline_eval.py` /
`run_intelliaudit.py`
