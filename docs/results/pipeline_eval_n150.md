# IntelliAudit — Deterministic pipeline evaluation (Stage 0 → EDGAR → Stage 1)

> This is the raw **first-run** record. For the current state (post citation-fix
> numbers, the six AuditBench metrics, findings, and the publication plan) see
> **`MEETING_BRIEF_2026-06-26.md`** in this folder. Section 4 below documents the
> *pre-fix* citation numbers; the fix lifted version-fair single-pick to 31.5% and
> the Stage-2 union ceiling to 41%.


**Run:** seed=42, n=150 per split, no LLM / no API key. Date: 2026-06-26.
**Scope:** everything built so far — the non-LLM stages. Stage 2 (LLM) and Stage 3
(reviser) are not yet implemented, so these are the numbers the LLM layer will
*start from*, plus the ceilings it will be bounded by.

Reproduce:
```powershell
$env:PYTHONUTF8=1   # bar chars need UTF-8 on Windows consoles
python stage0_eval.py --n 150                                  # gate + FP rate
python edgar_mapper_eval.py --split all --n 150                # concept mapping
python stage1_eval.py --split all --n 150                      # citation COVERAGE
python stage1_citation_eval.py --split single_error --n 150    # citation ACCURACY
```

---

## 1. Stage 0 — deterministic gate (Stage 0A arithmetic + 0B equation)

| Metric | single_error (n=150) |
|---|---|
| **False-positive rate (clean `correct` split)** | **0.000 (0/150)** |
| Coverage (gate fires) | 0.380 |
| Error Row EM — among fired | **0.895** |
| Error Type EM — among fired | **0.947** |
| Correct-value accuracy (when it proposes a fix) | **1.000 (33/33)** |
| Error Row EM — overall | 0.340 |
| Error Type EM — overall | 0.360 |

Per ground-truth error type (coverage / type-EM / row-EM):

| GT type | n | coverage | typeEM | rowEM | owner |
|---|---|---|---|---|---|
| numerical error | 44 | 0.659 | 0.659 | 0.636 | 0A |
| redundant row | 43 | 0.442 | 0.372 | 0.372 | 0B |
| missing row | 33 | 0.212 | 0.212 | 0.151 | 0A |
| misclassification | 30 | 0.067 | 0.067 | 0.067 | 0B |

**Read:** precision is essentially perfect — 0% false alarms on clean tables (the
paper's LLM baseline was ~50%) and ~90–95% correct on what it fires. The gap is
**recall/coverage** (38%), concentrated in *missing row* and *misclassification*,
which are the cases with little or no arithmetic signal — correctly deferred to the
(not-yet-built) LLM stage.

---

## 2. EDGAR Mapper — row label → us-gaap concept

| Split | concept coverage | ticker lookup | period parse |
|---|---|---|---|
| correct | 77.9% | 100% | 100% |
| single_error | 77.8% | 0% | 100% |
| multi_error | 75.7% | 0% | 100% |

Strategy mix (single_error): exact 56.5% · fuzzy 12.7% · stem_exact 8.6% · **none 22.2%**.
Coverage by statement: balance_sheet 84.4% · cash_flow 82.1% · income_statement 75.1%.

**Read:** mapping is **pure string-matching against the static `xbrl_concept_map.json`**,
not the live SEC EDGAR XBRL retrieval the design doc describes as the "novel
contribution" (ticker lookup is 0% on the error splits — the company name is stripped,
so even the metadata route is dead there). 22% of valued rows get **no concept at
all**, which directly caps Stage 1 (no concept → no graph citation).

---

## 3. Stage 1 — taxonomy citation COVERAGE

| Split | before (EDGAR map) | after (taxonomy) | source mix (after) |
|---|---|---|---|
| correct | 77.9% | 100.0% | taxonomy 72% · static 3.6% · parent/section fallback ~24% |
| single_error | 77.8% | 99.8% | same shape |
| multi_error | 75.7% | 99.8% | same shape |

**Read:** coverage is ~100% — but coverage just means "*a* citation was produced,"
including section-level fallbacks. It says nothing about whether the citation is
*right*. That is the next table, and it is the one that matters.

---

## 4. Stage 1 — citation ACCURACY vs ground truth  ⬅ the headline

single_error, n=150, broken-row citation scored against the GT Standards Citation
topic (127 records have a usable GT ASC; 23 are Conceptual-Framework with no ASC).

| Metric | Topic (e.g. 330) | Subtopic (330-10) |
|---|---|---|
| Broken-row coverage | 92.9% | 92.9% |
| **Citation EM (single pick)** | **24.4% (31/127)** | 18.1% (23/127) |
| EM among covered | 26.3% | 19.5% |
| **Candidate recall — Stage-2 ceiling** | **28.3% (36/127)** | 21.3% (27/127) |
| Paper GPT-4 baseline | 26.2% | 26.2% |
| Δ vs paper (single pick) | **−1.8%** | −8.1% |

By GT error type (topic EM / recall): Misclassification 0.44 / 0.44 · Missing 0.24 /
0.28 · Numerical 0.22 / 0.32 · Redundant 0.10 / 0.10.

### Why this is the most important result
- **The deterministic citation does NOT beat the paper** — 24.4% vs 26.2%. Coverage of
  100% masked this completely.
- **The ceiling is ~28%.** Even a *perfect* Stage-2 LLM that always picks the best of
  the graph's candidate citations tops out at 28.3%, because the correct ASC topic is
  simply **not in the candidate set 72% of the time**. The architecture doc projects
  Config C citation EM ≈ 0.75 — there is a ~47-point gap between projection and the
  measured ceiling.
- **Ranking is *not* the main problem.** EM (31) is within 5 of recall (36): when the
  right topic is in the candidate set, the ranker already picks it ~86% of the time.
  The bottleneck is **recall** — getting the right topic into the set.

### Root cause (verified by probing `taxonomy_graph.get_candidate_citations`)
The FASB **reference linkbase** attaches *presentation / SEC-staff* topics to
face-of-statement concepts, not the *subject-matter* topics AuditBench cites:

| Concept | Graph "best" pick | Candidate topics | GT-style correct |
|---|---|---|---|
| InventoryNet | 210-10-**S99**-1 | 210, 210, 852 | **330** (absent) |
| PropertyPlantAndEquipmentNet | **852**-10-55-10 | 852, 360, 942, 944 | **360** (present, mis-ranked) |
| Goodwill | 210-10-**S99**-1 | 210, **350**, 350, 852 | **350** (present, mis-ranked) |
| Revenue…Customer | **280**-10-50-30 | 280×6, 606, 606 | **606** (present, mis-ranked) |
| GeneralAndAdministrativeExpense | 220-10-**S99**-2 | 220, 946 | **720** (absent) |

Two failure modes: (a) the subject topic is **absent** from the linkbase arcs
(inventory→330, G&A→720) → unfixable by ranking; (b) it is **present but mis-ranked**
because `_rank_key` rewards low topic numbers + presentation roles (210/220/280) and
lets junk topics (852 Reorganizations, 235 Notes, S99 SEC staff) win.

---

## 5. Bottom line

| Stage | Status | Verdict |
|---|---|---|
| Stage 0 gate | precision solved (0% FP), recall partial (38%) | **working as designed** |
| EDGAR mapper | 78% coverage, static string-match only | **OK, but 22% unmapped + not the live-XBRL route** |
| Stage 1 coverage | ~100% | **misleading metric** |
| Stage 1 accuracy | 24% topic EM, 28% ceiling | **at paper parity, capped — needs rework** |

The over-auditing thesis is validated (Stage 0). The citation thesis is **not yet** —
as built, the taxonomy graph reproduces the paper's ~26%, not the projected ~75%, and
hard-caps the downstream LLM at 28%. See `RECOMMENDATIONS` below / chat for the fix plan.
</content>
