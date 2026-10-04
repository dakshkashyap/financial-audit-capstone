# Dataset audit: measured defects, repairs, and publication gates

This is an independent offline audit of the actual JSONL records and executable generation code. It uses no model calls and spends no API budget. The student's historical 1,089-case review and the user's 12% result are observations supplied in the request; neither was reproduced because the original predictions, exact evaluation command, and historical dataset revision were not supplied. Current files are different versions. This distinction prevents old feedback from being treated as a measurement of today's benchmark.

The current benchmark has improved substantially, but it is **not yet publication-quality ground truth for governing-paragraph reasoning or fraud detection**. The imported capstone snapshot is especially unsuitable as a blind benchmark: every exam ID contains the injected rule name, there are no clean controls, and 112 nominally citable answers are section codes rather than paragraphs. The latest upstream removes these defects, adds useful controls and measurement evidence, and retains important validity gaps described below.

## Scope and reproducibility

Reviewed revisions:

| Source | Commit | Audited package |
|---|---|---|
| capstone `irvin/citation-full-asc` | `159ae080dcddedf4a9cee9c5f831bb624d113782` | `/workspace/source-asc/data/intelliaudit` |
| capstone `daksh/ifrs-pipeline` | `4a622e0bd39e19c3a0d6fe6033e14854b107d983` | `/workspace/source-ifrs/data/intelliaudit` |
| IntelliAudit requested dashboard source | `72da89a9e6400bfd1da9041a742f9cdeb00470bc` | `/workspace/IntelliAudit/data/benchmark` and `data/ifrs/benchmark` |

The two capstone `data/intelliaudit` snapshots are byte-identical for exam, key, and clean statements; the IFRS branch name does not make this copied package an IFRS benchmark. The separate current upstream IFRS package contains genuine IFRS-labelled cases. SHA-256 hashes for all twelve input files are in `research/results/dataset_audit.json`.

Reproduce from the checked-out upstream sources:

```bash
python research/scripts/audit_dataset.py \
  --dataset asc_snapshot=/workspace/source-asc/data/intelliaudit \
  --dataset ifrs_snapshot=/workspace/source-ifrs/data/intelliaudit \
  --dataset upstream_usgaap=/workspace/IntelliAudit/data/benchmark \
  --dataset upstream_ifrs=/workspace/IntelliAudit/data/ifrs/benchmark \
  --structured-clean upstream_usgaap=/workspace/IntelliAudit/data/clean \
  --structured-clean upstream_ifrs=/workspace/IntelliAudit/data/ifrs/clean \
  --output research/results/dataset_audit.json
```

Paths are configurable and the script uses only the Python standard library. Its mechanically verifiable findings are counts, joins, code formats, paragraph membership in recorded reference sets, text cues, component arithmetic, and metadata shortcuts. **It does not validate the normative content or temporal applicability of accounting standards, establish whether human review occurred elsewhere, or verify financial values against live SEC filings.**

## What the current records actually contain

| Measured property | Both embedded capstone snapshots | Latest upstream US GAAP | Latest upstream IFRS |
|---|---:|---:|---:|
| Exam records | 1,202 | 14,963 | 1,382 |
| Companies | 8 | 70 | 31 |
| Base statements | 220 | 1,989 | 161 |
| Clean controls on exam | 0 | 1,989 | 161 |
| Key marks `citable=true` | 492 | 6,388 | 648 |
| Distinct assigned citation codes | 9 | 15 | 8 |
| Strict linkbase flag | 13 | 1,363 | 0 |
| Explicit `expert-authored-UNVALIDATED` | 479 | 5,025 | 648 |
| Detection-only, no governing paragraph | 710 | 6,586 | 573 |
| Rule name exposed in exam ID/text | 1,202 | 0 | 0 |
| Citable section code lacking paragraph | 112 | 0 | 0 |

No duplicate exam IDs, unmatched exam keys, or duplicate key IDs were found in these single-error packages. Upstream IFRS is **balance sheets only**. No claim of three-statement or full financial-audit coverage is supported for that package. The upstream multi-error pack was inspected at the code/schema level but is outside this quantitative single-error audit.

## Citation accuracy must be interpreted against the right denominator

On only `citable=true` cases, a classifier that sees **statement type alone** achieves 39.0% leave-one-company-out (LOCO) exact agreement on the embedded snapshot, 29.6% on current US GAAP, and 23.0% on current IFRS. These predictions use gold only from other companies. They do not inspect statement amounts or transaction narratives.

Adding the **gold error type** gives 46.5%, 38.3%, and 34.9% respectively. This is an oracle diagnostic, not a fair deployed baseline: the exam does not disclose the true error type. Adding **gold rule ID** gives 100% on both US-GAAP versions and 99.85% on IFRS LOCO; one IFRS securities case has no matching rule example outside its company. Gold rule ID is an oracle diagnostic on the repaired upstream, but the embedded exam IDs expose it directly.

| Citation shortcut, citable cases only | Embedded LOCO | Upstream US GAAP LOCO | Upstream IFRS LOCO |
|---|---:|---:|---:|
| Statement type; deployable metadata diagnostic | 192/492 = 39.0% | 1,889/6,388 = 29.6% | 149/648 = 23.0% |
| Gold error type + statement; oracle | 229/492 = 46.5% | 2,445/6,388 = 38.3% | 226/648 = 34.9% |
| Gold rule ID + statement; oracle except leaked embedded IDs | 492/492 = 100% | 6,388/6,388 = 100% | 647/648 = 99.85% |

An additional deterministic 80/20 item split produces statement-only exact agreement of 41.2%, 29.9%, and 22.7%; these numbers are included as a shortcut audit, **not a recommended research split**. Multiple variants of the same base statement cross item splits. The student's reported 72%/79% shortcuts were measured on an earlier version; this audit cannot reproduce them on today's restricted citable denominator. The difference is not evidence that either audit was wrong.

The user's 12% therefore cannot be read as an established scientific performance result until the run's dataset hash, eligible denominator, citation normalization, malformed outputs, abstentions, model ID, prompts, token budget, and exposure to hidden fields are known. A percentage against an unadjudicated single-answer key measures agreement with its author, not necessarily accounting correctness.

## Which student findings are fixed, partly fixed, or unresolved

### 1. Trivial detection: difficulty remains unmeasured

The embedded exam is 100% injected. Always saying `Incorrect` scores 100% judgement accuracy, so false-positive behavior cannot be measured. The latest US-GAAP exam includes 1,989 controls, but 86.7% of records remain injected. The latest IFRS exam is 88.35% injected. Always-incorrect accuracy is still a necessary trivial baseline; balanced accuracy, clean false-positive rate, macro rule performance, and matched contrasts are better primary diagnostics.

The new citable injections recompute subtotals or balance the opposing equity effect; the generation code separates arithmetic faults from standards-based errors. That repair addresses the old "all errors break sums" problem. The audit did not run new LLM detection baselines and makes no claim that the repaired benchmark is easy or hard for current models. An author-written deterministic solver is not independent evidence of model difficulty or accounting gold validity.

### 2. Guessable citations: direct ID leakage fixed upstream, narrow ontology remains

The embedded package exposes strings such as `IA-AAPL-2015-BS-R01_current_noncurrent_asset_misclass-00` to the model. All 1,202 exam records expose a rule token. This invalidates any claimed blind citation result unless the input builder removes it.

The latest upstream replaces IDs with `EX-` hashes, removes rule tokens and explicit citation codes from exam inputs, and keeps hidden information in the answer key. The form allocation has no repeated base statement within a form: this property was checked, rather than assumed. There are 17 US-GAAP forms and 12 IFRS forms.

Every current rule still maps to one assigned paragraph. The citable US-GAAP task has only 15 labels and the IFRS task eight. This is a rule-family recognition task unless competing authorities, factual exceptions, alternative valid citations, and evidence sufficiency are evaluated. Seeing a taxonomy topic associated with a concept does not establish that a paragraph governs the particular misstatement.

### 3. Original-value evidence leakage: fixed for current recognition cases, retained for arithmetic cases

The transaction generator avoids printing an individual component equal to a line total, but its components **sum exactly to the generating line total**. Code evidence: upstream `src/transactions.py` `_pair` at line 148 and `generate_for_statement`, and `src/injector.py` `exam_evidence` at line 365. The phrase "NOT the reported line totals" does not eliminate this algebraic reconstruction.

| Target-component check | Embedded | Latest US GAAP | Latest IFRS |
|---|---:|---:|---:|
| Numeric injections checked | 571 | 6,496 | 542 |
| Target caption receives component evidence | 346 | 4,258 | 335 |
| Signed sum restores the pre-injection value | 259 | 2,144 | 161 |
| Absolute sum restores original magnitude | 338 | 2,144 | 161 |
| Signed sum agrees with erroneous as-booked target | 0 | 2,086 | 172 |

These denominators include cases where random 65% ledger coverage omits the target. In the embedded snapshot, wrong orientation explains many differences between signed and absolute recovery. In current US GAAP, original-value reconstruction is confined here to noncitable R05 (1,296), R07 (418), and R12 (430). Their citable recognition/measurement counterparts generate the ledger from the erroneous **as-booked** statement; none of those numeric target ledgers sum to the original value. This is a real, material repair. It does not make the transactions authentic journal entries.

Old row-number transaction evidence occurs in 13,565 ledger lines across embedded records. It preserves clean row numbers even when the presented statement changes. Current upstream uses captions, so zero old row-number transaction lines remain. Do not feed multiple variants of a base statement together: all 1,989 current US-GAAP base statements have several exam variants, allowing a separate cross-case diff shortcut.

### 4. Transactions: sign repairs are visible; bookkeeping realism is unresolved

Current executable templates explicitly make dividends decrease retained earnings, receivable write-offs decrease net receivables, and depreciation decrease PP&E. Current retained-earnings evidence says "balance brought forward plus net income", improving the prior opening-balance error. Expense/cash-outflow orientation is handled separately.

Nevertheless, these are two-component random decompositions of statement balances. They generally lack posting dates, account pairs, opening/closing schedules, settlement details, transaction IDs, journal balancing, and source documents. Credit/charge generic templates for residual accounts do not supply accounting provenance. The data should be described as **synthetic account-level supporting evidence anchored to public statement numbers**, not real transactions or authentic audit engagements. There is no basis in these records to infer fraudulent intent.

### 5. Governing citations: honesty improved; normative gold still needs adjudication

The latest generator sets arithmetic/missing/fabricated-row cases to `citable=false`, disables unverified DQC outputs, chooses governing policy clauses, and checks **exact paragraph membership** when labelling a taxonomy reference match. Every flagged US-GAAP linkbase match in the inspected packages passes that mechanical consistency check: zero flag/reference mismatches. This addresses the old "topic match presented as paragraph verified" defect.

But linkbase membership establishes a reference associated with an XBRL concept, not the authority governing this error. Current labels themselves mark 5,025/6,388 US-GAAP citable cases and all 648 IFRS citable cases `expert-authored-UNVALIDATED`. No reviewer identities, adjudication results, acceptance sets, or standards-version fields appear in the keys. This does not prove that no person ever examined a case; it means the released ground truth contains no verifiable completed-review record.

The embedded key additionally calls `ASC 230-10-45` and `ASC 470-10-45` "full" in 112 citable cases, although those strings end at section level. The latest upstream uses paragraph codes, fixing this formatting problem. Exact paragraph agreement should be withheld as a headline quality claim until two independent qualified annotators and an adjudicator assess the allegation, required facts, authoritative paragraph, acceptable alternatives, and abstention status.

### 6. Residual filler: large balance-sheet repair; cash-flow abstraction remains

The embedded clean tables contain 389 `(residual)`-suffixed rows across 188/220 statements. The upstream removes that suffix but retains explicit `residual=true` flags in structured clean JSONs. The audit uses those flags, not the displayed caption, to assess remaining plugs.

| Current structured statement | Residual share of absolute non-total line mass | Median per-statement share | 90th percentile | Maximum |
|---|---:|---:|---:|---:|
| US-GAAP balance sheets | 3.73% | 0.11% | 12.90% | 64.28% |
| US-GAAP cash flow | 33.43% | 32.90% | 65.51% | 91.33% |
| US-GAAP income statements | 15.89% | 8.09% | 44.40% | 65.82% |
| IFRS balance sheets | 9.82% | 2.60% | 24.30% | 53.82% |

The metric sums absolute `kind=line` values and excludes totals/subtotals; it is **not the student's percentage of assets** and must not be compared as if identical. Every current cash-flow and income-statement structured table still has residual rows. The current source now supplies random ledger evidence for residual rows as well, so "no transaction" is less of a direct plug fingerprint. Residual-heavy cases should be excluded from accounting-realism claims or accompanied by a faithful full filing reconstruction.

### 7. Sample/rule bias: expanded source; planned pilot remains small

Upstream now has 70 US-GAAP companies and 31 IFRS companies, rather than the embedded eight. Current US-GAAP rules include revenue timing, goodwill/PP&E impairment, receivable credit losses, securities measurement, R&D and DTA recognition, with explicit supporting facts. Recognition/measurement was formerly inferred from altered values without a causal narrative; the embedded pack has zero `Supporting facts` sections. The new templates give models information they previously could not identify.

US-GAAP controls carry supporting facts in 1,297/1,989 cases (65.2%), while injected cases do so in 10,273/12,974 (79.2%). Thus fact presence is no longer a perfect error flag, but the pooled distribution still differs. Match control/injected case families and hold out evidence phrasings rather than claiming the cue has no predictive power. IFRS supporting facts occur in all controls and all injected cases.

Banks and insurers remain inappropriate without dedicated accounting rule families; the expanded source does not solve that omission. A budgeted 5–10-company pilot is useful for debugging, paired exploratory estimates, and annotation development. It cannot support a narrow confidence interval or a claim about the entire corporate audit population. Resample the company or case-family clusters; never resample generated perturbations as independent observations. Report all per-company outcomes and wide intervals.

## Additional defects found independently

### Exported "XBRL JSON" is an internal scaled table, not a correct fact export

Upstream `src/render.py` lines 21–33 emits every fact with an **instant** period. All 1,312 current US-GAAP income/cash-flow clean statements therefore export duration facts with the wrong period kind; 155 embedded duration statements do too.

All clean statements use millions in their table metadata, but serialize the same scaled value with an `iso4217` currency unit and `decimals=-6`. For example, 21,120 USD millions becomes numeric fact value `21120` with unit `iso4217:USD`. XBRL `decimals` specifies rounding precision; it does not multiply that value by one million. The serialization is off by the scale factor if interpreted as an actual monetary fact. Current IFRS preserves the actual currency code in structured data, but the text renderer uses a dollar sign for EUR, SEK, CAD and other presentation currencies. A consumer must read `metadata.unit`; the generic symbol is misleading.

Fix the export with actual currency-unit values, explicit scale in the internal schema, and proper start/end periods preserved from source facts. Do not call it OIM-compliant unless an OIM validator passes it.

### Source provenance and filing-version consistency are not independently inspectable

No clean-statement metadata or serialized fact in these packages contains a filing accession or filing URL. No structured row contains one either. The checked-out IntelliAudit data has no `raw`/`raw_snapshot` companyfacts dump or filing-linkbase snapshot. It cannot be rebuilt from fresh raw SEC evidence entirely offline, and the claimed original-value verification cannot be independently repeated from the committed package alone.

`src/edgar_ingest.py` `concept_value` lines 68–96 selects candidate facts per concept by fiscal-year metadata and latest period; its tie-break does not pin a consistent filing accession/restatement version across all selected concepts. It returns accession/start/end, but builders discard row-level provenance. Different concepts can therefore draw from different versions of the same reporting period. This is a code-level risk, not a measured count of actual wrong SEC values. Preserve and hash the selected accession, form, start/end, filing date, fact unit, raw value and calculation weight at each row; validate them against one explicitly chosen filing version.

**Independent primary-source follow-up:** after the root agent downloaded current SEC companyfacts for the eight pilot companies, an additional offline audit checked every one of their 226 upstream clean tables. The root numeric audit finds 2,929 signed matches, 397 magnitude-only matches, 160 mapped cells without a same-period annual fact, 604 derived/unmapped cells, and two value mismatches among 4,092 numeric rows. This supports source origin for many numeric magnitudes; it does not validate all cells or their alleged original filing version.

The separate reproducible `research/scripts/audit_sec_accessions.py` finds that **164/3,328 cells with same-period candidates have different numeric values across accessions**. It also finds **18/226 tables have no single accession in common across their individually matched numeric magnitudes**, even with a permissive ±0.51-million tolerance and with unmatched/derived rows excluded. For Union Pacific FY2017 cash flow, operating cash 7,230, investing cash −3,086 and financing cash −4,146 match accession `0000100885-20-000065`, while the displayed net cash change −2 matches only `0000100885-18-000048`. The tuple is not jointly supported by one accession in the flat SEC snapshots. Custom/dimensional facts omitted by companyfacts are a remaining limitation; this finding should be described as a **flattened-source filing-version inconsistency**, not proof that each displayed number is fabricated. All 18 table witnesses and snapshot hashes are in `research/results/sec_accession_consistency.json`.

```bash
python research/scripts/audit_sec_accessions.py \
  --source /workspace/IntelliAudit/data/clean --cache /tmp/audit-sec \
  --ciks 0000001800 0000051434 0000100885 0000731766 \
         0000831259 0000949870 0001334036 0001655210 \
  --output research/results/sec_accession_consistency.json
```

### Accounting standards have no as-of version

No key carries an effective date or standard version. The current US-GAAP pack applies its revenue-recognition rule to 150 company-cases from FY2015–2017, modern credit-loss rule to 257 from FY2015–2019, inventory NRV rule to 80 from FY2015–2016, and reporting-unit goodwill templates to 225 from FY2015–2019. These are **temporal review flags**, not automatically proven invalid cases: adoption dates, early adoption, entity-specific accounting policies and historical amendments must be verified against authoritative sources. The metadata gives historical fiscal years, so silently applying current standards is not justified. Either version the applicable rule to the actual reporting date or state clearly that numbers are historical anchors for a synthetic current-period scenario and change the scenario date accordingly.

## Minimum release gates before a high-quality paper claims efficacy

1. Freeze a versioned 5–10-company pilot, grouped by company and base case; avoid cross-form/variant access during inference. Retain the current big upstream pack as an explicitly quarantined legacy diagnostic source.
2. Separate three tasks: detecting an arithmetic/data fault, identifying an accounting misstatement, and grounding a governing citation. Fraud/intent requires additional authentic or carefully labelled synthetic evidence; it is not equivalent to a balance discrepancy.
3. Publish independent annotation evidence for the entire small test set: two qualified reviewers, adjudication, agreement before adjudication, standard effective date, necessary conditions, alternative acceptable authorities, and insufficient-evidence labels. Synthetic expected answers must remain `UNVALIDATED` until this is completed.
4. Build matched positive/negative and insufficient-evidence cases with the same account, company, period and narrative family. Examples: wrong versus warranted revenue deferral, recoverable PP&E versus true impairment, waived versus unwaived debt breach, legitimate development capitalization versus prohibited research capitalization. Hold out company and wording families.
5. For budgeted evidence acquisition, expose only requested documents to the agent and score required evidence coverage, valid intermediate inferences, unnecessary acquisition cost, final decision, citation entailment and appropriate abstention. Ground-truth graph edges need reviewer validation; showing graph labels to the agent invalidates process scoring.
6. Preserve per-fact and per-document provenance, original and restated accession versions, real units and duration periods. Label fabricated account schedules as synthetic. Release citation identifiers and lawful snippets/links; availability of a source is not redistribution permission.
7. Report majority/prior baselines, metadata/phrase/amount-masked shortcuts, a deterministic accounting calculator, retrieval-only ranking, and single-model versus staged systems under the same input evidence and cost limits. One frontier reference and cheap/open-weight alternatives should be a preregistered resource constraint, not a reason to overfit to one sample.
8. Report joint correctness and cost only on adjudicated cases. Include retrieval recall separately from paragraph selection, support/entailment separately from string match, failure and abstention rates, paired company-level uncertainty, and total spend. Claiming a cheap model beats a frontier model requires replicated, paired evidence; this audit establishes no such result.

The most defensible immediate contribution is the reproducible **validity audit and evaluation protocol**, followed by an independently adjudicated contrastive citation/evidence pilot. The measured improvements are useful engineering progress. They do not substitute for authoritative gold review or a completed model comparison.
