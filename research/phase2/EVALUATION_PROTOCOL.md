> **Paused design:** the benchmark-first accountant pilot now precedes any paid execution. This document is prospective, not a registered executed experiment. The unfinished runner is archived in `design/`; final models, corpus and budgets require a new freeze after review.

# Phase 2 evaluation protocol: issue-conditioned standards retrieval

Status: prospective protocol, October 3, 2026. This document does not report new
experiments, validate accounting labels, or establish novelty. Freeze its final
version, exact model IDs, prompts, corpus, case manifest, and numeric request
limits before the first scored phase-2 request. Any subsequent change creates a
new, explicitly exploratory condition; it never replaces a failed result.

## Research questions and permitted conclusions

The mechanism hypothesis is that an explicit account of **which financial
assertion is violated and which observable facts establish that violation**
selects governing paragraphs more effectively than retrieving by statement or
account labels. A second hypothesis is that an applicability check reduces
unsupported citations without an unacceptable loss of supported decisions.

The current 48 cases and their outcomes have already been inspected. A fixed
24-case subset is **development data for every phase-2 ablation**, including
every new direct run; all 48 remain historically inspected development data.
An improvement there is a measured development result, not held-out efficacy.
Current citation labels are unvalidated; agreement with them is not accounting
correctness. A low-cost system need not beat a frontier model to make a useful
benchmark contribution, and a higher percentage alone does not validate the
proposed mechanism.

The project will use at most **10 distinct real companies across both phases**:
the original eight plus two previously unused companies. The two new companies
provide a small locked replication. Two test company clusters cannot support
population significance, noninferiority, or a claim of broad representation.
Reassigning four of the original eight companies to a new split would not make
them company-held-out; all eight already have inspected outputs.

## Data allocation and locking

| Partition | Companies | Cases | Purpose |
|---|---:|---:|---|
| Inspected development | Original 8 | 24: one clean, one detection-only, one citable per company | All phase-2 method ablations on a hashed subset of the inspected 48 |
| Locked replication | 2 previously unused | 12: two clean, two detection-only, two citable per company | Descriptive transfer to unseen companies |
| Future validated benchmark | Not created by this protocol | To be determined with the accountant reviewer | Accounting efficacy and evidence-process evaluation |

The fixed phase-2 cohort has **36 cases**. Select development cases by a frozen
hash ordering within each of the original eight companies and each of the three
strata, choosing one from the already inspected 48: 24 total, 16 injected, eight
clean, and eight citable. Select two clean, two detection-only, and two nominally
citable cases for each of two previously unused companies: 12 total, eight
injected, four clean, and four citable. This is the frozen size; there is no
optional 18-case replication in phase 2. Report development and replication
separately. A pooled 36-case number is supplementary and is never described as
held-out performance.

No case is selected because an earlier model succeeded or failed on it. The
original 48-case results remain intact; a 24-case result must identify its new
case manifest and denominator. All required phase-2 conditions use these same
36 observable cases. If the prospective cost envelope cannot accommodate the
required paired design, revise and freeze the design **before any scored call**;
never shrink an opened cohort to its favorable prefix.

1. Pin the upstream source commit, generator version, catalog of source files,
   fiscal-year range, and case-selection implementation. Retain FY2020–2024
   unless an independently justified change is frozen before selection.
2. For replication, exclude the eight previously evaluated company identifiers. Order eligible
   companies and cases using a fixed recorded hash seed. Eligibility and
   balancing use source metadata and data-quality requirements, never model
   scores. Publish the full eligible pool, exclusion reasons, and selection
   manifest so the two companies are not an undocumented favorable choice.
3. Group a base statement, accession/amendments, fiscal event, all injected
   variants, counterfactuals, paraphrases, and any enforcement event together.
   No such group may cross partitions. Company separation alone is insufficient
   if an enforcement event or duplicated evidence connects companies.
4. Check original filing accession, periods, units, sign conventions, and
   evidence provenance before locking. Flattened SEC companyfacts matches alone
   do not establish one internally consistent source filing. Predeclare whether
   unresolved provenance yields exclusion or a flagged exploratory stratum;
   never exclude because a model failed.
5. Keep replication answer keys and intermediate model scores inaccessible to
   method development. Dataset custodians may perform prescribed integrity and
   selection checks; they must not provide case-specific hints to prompts,
   retrieval rules, the candidate corpus, or developers. Persist predictions
   and request traces before joining any scoring annotations.
6. Use opaque case IDs with no rule, error, pairing, or label tokens. Sessions
   are independent across cases and conditions. No conversation memory or
   retrieval cache may contain another condition's answers or hidden gold.

The upstream 70-company audit inspected broad counts and metadata; it is not
itself a paid run on those companies. Disclose that source inspection when
calling the new two-company sample "previously unevaluated." If anyone has
already read a selected case's answer while designing the new method, flag the
exposure and retain that case only as development; apply the predeclared next
eligible case rule before the replication is opened.

## One-accountant review and gold status

One accountant is available. Use that expert carefully and state the resulting
single-reviewer limitation; do not claim two-expert adjudication, inter-rater
agreement, or inter-rater kappa. Record relevant qualifications and whether the
reviewer helped author the cases. Independence from the generating method or
team must be described accurately, not assumed from the word "expert."

The review packet initially contains only the permitted case evidence, source
provenance and dated standards material, without model answers, proposed gold,
condition identities or scores. The accountant first records the judgment,
error type/row where identifiable, evidence sufficiency, governing paragraph(s),
acceptable alternative citations, rationale, and an ambiguity flag. A second
pass exposes the proposed key and asks the same reviewer to confirm or amend it
with a reason. Preserve both passes and all changes. This is a documented
single-expert review process, not independent multi-expert adjudication.

Before a case can enter an **expert-reviewed release**, the reviewer must approve
all scored label fields, required evidence, citation applicability, framework
and effective-date assumptions. Allow justified alternative citations and proof
sets in the frozen key. If the evidence cannot identify a unique error/row or
support a governing paragraph, retain an explicit ambiguous/unidentifiable label
with permissible responses or exclude it under a prospective rule; never force
one convenient answer. A case requiring a combination of paragraphs needs a
schema and scoring rule capable of representing that combination, rather than
silently choosing a single paragraph after seeing predictions.

Use a preselected stratified subset for a delayed blind repeat review, preferably
at least two weeks later, with shuffled opaque IDs and no access to the first
answers. Report exact repeat counts, within-reviewer agreement by label field,
and reasons for changes. Call this **intra-rater consistency**; it neither
estimates inter-rater reliability nor removes the single-reviewer limitation.
Do not invent a repeat review if the deadline does not permit it.

All current and new labels remain **review pending / unvalidated** until this
work is actually recorded. Engineering experiments may proceed with that status
and report provisional-label agreement. Their scores cannot be relabeled as
expert-validated after casual consultation. Freeze reviewer-approved labels
before opening the corresponding locked model predictions; post-run label
repairs must be versioned and reported alongside the original scores. The
release data card must disclose one reviewer, coverage, dates, unresolved cases,
alternative-label policy, and the absence of inter-rater validation.

## Conditions and information boundary

Select one primary cheap model and, only if the whole design fits the budget,
one additional cheap model. Record exact provider/catalog IDs and prices before
running. Existing candidates are `qwen/qwen3-8b` and
`qwen/qwen3-30b-a3b-instruct-2507`; their prior rate-limit failures are a reason
to verify availability, not to hide failures or silently swap models. A newly
selected cheap model requires a prospective named condition. No unregistered
model fallback is allowed. **Claude Opus 5.5
(`anthropic/claude-opus-5.5`) is the only frontier family.**

All arms receive byte-identical public statement, transaction/evidence,
framework, fiscal-year, and permitted company metadata for a given case.
Neither inference nor retrieval may read error type, rule ID, citable flag,
answer citation, corrupted-row index, corrected values, gold graph, or review
annotations. Model hypotheses are untrusted user data, not system instructions.

| Arm | Observable procedure | Contrast it supports |
|---|---|---|
| Q-D: Qwen direct | One decision from the public case; no standards retrieval | Closed-book reference under the phase-2 output contract |
| Q-M: Qwen row-metadata retrieval | Deterministic retrieval using framework/date, statement type and visible row/account metadata; one model decision | Metadata-based candidate reference |
| Q-I: Qwen issue-authority retrieval | Build a query from observable supporting facts and deterministic mechanical checks; retrieve source-traceable authority cards; one model decision | Q-I minus Q-M tests the issue/evidence-conditioned retrieval bundle |
| Q-P: Qwen issue-authority + condition gate | Apply the frozen deterministic condition checker to the exact saved Q-I response, case and candidate packet; suppress unsupported claims or abstain | Q-P minus Q-I isolates postprocessing of the same model output; zero additional API calls |
| O-D: Opus direct | Same public case and decision contract as Q-D, using Opus | Matched closed-book model reference |
| O-I: Opus issue-authority retrieval | Byte-identical issue query outputs, mechanical-check results and retrieved candidate packet as Q-I; one Opus decision | Q-I versus O-I compares models with matched observable tool evidence |

**No LLM planner or LLM query-extraction stage is used.** The query builder,
mechanical checks, retrieval and gate are deterministic and use public fields
only. The core freeze has five paid arms and one derived zero-additional-API
arm. Do not introduce an unbudgeted extra model stage or second cheap-model sweep.
If a second cheap model is prospectively registered, it remains optional and
must fit the complete paired budget before any scored phase-2 calls.

Use the same authority corpus and candidate-cap policy for the Q-M and Q-I
contrast when possible. If Q-M exposes reference metadata while Q-I additionally
exposes explanatory authority text or mechanical-check results, document that
intervention: the contrast tests the **combined information/retrieval design**,
not isolated query wording. A text-access-matched query ablation is necessary
before attributing the entire difference specifically to issue conditioning.

The old closed-book Opus score used a different output contract and remains
historical development evidence. New model comparisons use Q-D versus O-D and
Q-I versus O-I on the exact phase-2 cohort. Comparing Q-P with ungated O-I is an
asymmetric system comparison, not an isolated model comparison. The same frozen
gate may also be applied offline to O-I as a labeled secondary diagnostic,
without new API calls, if that analysis is declared before opening scores.

Persist each deterministic candidate packet once, before generation, and use
that exact packet for Q-I and O-I. Derive Q-P from the unchanged saved Q-I
response; never rerun the model for a better gated answer. Raw and gated outputs
remain available side by side, including newly induced abstentions. Shared
retrieval reduces experiment overhead; standalone deployment accounting still
includes the local retrieval/checking work each system would need. Do not share
frontier-generated analysis with the cheap arm.

The authority corpus contains broad US GAAP cards derived from **actually read
FASB and Big Four sources**, constructed independently of case answer keys.
Register each source URL, access date, source-content hash, citation identifier,
coverage, applicable dates when established, and redistribution status. Clearly
mark **secondary paraphrases / authority metadata; accounting review pending**.
These cards are not the complete verbatim authoritative ASC, and a readable Big
Four interpretation is not itself an FASB-issued paragraph. Source traceability
does not establish that a card governs a particular case. Missing licensed text
or an unresolved effective date is documented uncertainty, not permission to
fabricate quotations, dates or paragraph text.

The deterministic gate is a **source-traceable condition checker**, not a formal
accounting proof system. Its checked predicates, input spans, applicability
assumptions and failure/unknown states must be inspectable. A positive checker
result means its implemented conditions matched observable data; expert
validation is still pending. The phrase "proof gate" in a condition identifier
must not be converted into a claim of formally proved accounting correctness.

## Resource controls and execution order

The freeze must specify one shared maximum number of retrieved candidates,
passage/context byte limits, call limits by stage, temperature, reasoning
settings, timeout, output schema, and **aggregate per-case completion-token
ceiling**. A practical initial target is at most six candidates and 1,200 total
completion tokens per case, allocated explicitly across stages. Do not mistake
1,200 tokens per call for a matched 1,200-token case budget.

Same-model paid ablations use one generation call, the same output contract and
the same completion ceiling. Query construction and mechanical checks add no
LLM calls. Q-P reuses Q-I and adds zero API tokens/dollars; report its local
processing time and abstention tradeoff. Do not double-count Q-I spend as a
second paid experiment, but do charge a standalone Q-P system for its underlying
Q-I generation. Retrieval arms may contain more input tokens than direct arms;
report those inputs and actual costs rather than calling added context free.

For Q-I versus O-I, match observable tools and evidence limits, not literal API
tokens across incompatible tokenizers. Report UTF-8 prompt bytes, provider
input/output and reasoning tokens when available, generation/retry counts,
retrieval count, dollars, request latency and end-to-end elapsed time. The same
principle applies to the direct Q-D versus O-D comparison. A faster failed HTTP
response is not evidence of faster reasoning.

Use the same fixed case set for every required condition. Generate a seeded,
company/stratum-balanced schedule and rotate condition order within each case
block to reduce confounding by provider time and availability. Run one model
request at a time with a predeclared minimum inter-request interval; never
launch a burst to finish before a rate limit. Resume the saved schedule and
cached completed requests, not an outcome-selected new order.

### Cumulative dollar boundary

The canonical shared ledger is `research/artifacts/api_ledger.jsonl`.
Its pre-phase-2 state is:

- Reported charges: **$1.92078856970**; this is incomplete accounting.
- Responses without reported cost: **67**; unresolved reservations: **0**.
- Conservative reservations retained: **$4.230397654**.
- New explicit lifetime ceiling: **$12.00**, leaving at most **$7.769602346**
  of additional conservative reservations, before any phase-2 call.

The previous $5 ceiling describes phase 1. The implementation must record the
prospective policy change to $12 and keep all earlier ledger events. Do not
reset the ledger, use a new filename to bypass prior spend, refund unknown
errors, or interpret the account balance as the research allocation. Keep the
remaining $18–28 of the user's stated $30–40 allocation unspent by this phase.

Before each batch, reserve a worst-case bound for the entire required paired
cohort, all stages, at most one permitted retry per request, and operational
preflights. Use current price caps, full message/schema overhead, bounded
outputs, and the existing conservative byte-based prompt accounting. Provider
pricing/model mismatch triggers a stop. If the full run does not fit, remove
optional cheap-model arms or optional diagnostics before the protocol freeze.
The core cohort remains 24 development plus 12 replication cases. Any further
core-design revision must precede all scored phase-2 calls and be explicit. Do
not buy only the promising conditions. All preflights and retries count toward the same $12.

### Failures and bounded retries

Freeze this policy before requests: at most **one retry of an identical request**
for HTTP 429, transient 5xx, or transport timeout. For 429/5xx, honor a valid
Retry-After of at most 30 seconds; otherwise wait a fixed 10 seconds. If the
provider requests a longer wait, pause the batch for a later scheduled resume
instead of retrying early. Reserve both attempts before issuing the first.
Timeouts may have been charged; retain both reservations. No retry follows an
invalid schema, wrong citation, refusal, empty answer, or unfavorable score.
No second-model retry or opportunistic provider substitution is permitted.

Store both attempts and designate success/failure using a fixed rule: the first
schema-valid returned response is the case-stage response; an already successful
stage is never rerun. After two consecutive requests exhaust the permitted
transient retry, pause that condition and report the interruption. Resume only
the saved remaining requests after the availability problem resolves, within
the frozen policy and remaining budget. Never fill missing cases with a later
protocol's predictions.

Report outcomes over the entire intended cohort, valid-output outcomes as a
secondary descriptive view, request-failure counts separately, and the number
not requested. A partial ordered cohort cannot replace a completed experiment
or produce a confirmatory ranking. Publish both first-attempt service success
and eventual success under the bounded retry policy. Retry dollars, tokens and
time belong to their assigned condition, including failed attempts.

## Outcomes, risk, and exact denominators

Each report must carry raw numerators and denominators, per-company counts, and
per-case predictions. The current labels support **agreement diagnostics** only.
Full accounting applicability and sufficient-proof scores remain unmeasured
until the accountant reviewer supplies and approves that gold. Do not use one LLM as both solver
and final judge of its own citation.

| Outcome | Eligible denominator | Success or risk definition |
|---|---|---|
| General judgment agreement | All intended cases | Schema-valid correct/incorrect judgment equals the frozen label; abstention is separate |
| Error type | All injected cases | Incorrect judgment and correct type |
| Error entry | All injected cases | Incorrect judgment and correct row; distinguish this from the joint score |
| Joint detection + type + entry | All injected cases | All three correct together |
| Full-citation agreement | All citable cases | One valid full citation matches the predeclared acceptable set; an unvalidated key gives label agreement only |
| Joint detection + type + entry + full citation | All citable cases | Every component correct on the same case; primary engineering quality outcome |
| Clean specificity | All clean cases | Explicit correct judgment; abstention and failures are not true negatives |
| Clean false accusation | All clean cases | Explicit incorrect judgment; also report failure and abstention fractions separately |
| Citation emission on noncitable cases | All cases annotated noncitable | A governing-violation citation is asserted; annotation risk, not automatically proven false applicability |
| Invalid source provenance | All intended cases, and all citation-bearing outputs | Cited document/span does not exist or its claimed quotation disagrees with the registered source; separately flag unverified out-of-corpus citation codes |
| False applicability | Independently adjudicated cases, and independently adjudicated citation-bearing outputs | Governing-violation citation fails the reviewer-approved applicability policy; unavailable with current unvalidated gold |
| Supported decision / proof coverage | Cases with independently adjudicated sufficient evidence and acceptable proof sets | Correct decision plus a complete acquired evidence witness, without unsupported edges or invented facts |
| Decision/citation abstention | All intended cases | Explicit abstention; distinguish from failed requests and missing predictions |
| Service/format failure | All intended cases and all requests | Report provider, timeout, schema and missing cases separately |

Exact source-span matching and valid graph references establish observable
provenance, not accounting entailment or true internal reasoning. A paragraph
absent from the retrieved corpus is unverified; absence alone does not prove the
standard is nonexistent or fabricated. The direct arm can cite from model
knowledge, so do not turn its lack of retrieval into an automatic false-citation
judgment. On current
cases without reviewed sufficient proofs, report only quote/reference validity
and evidence coverage under their literal definitions; leave supported-proof
accuracy **not measured**. Retrieval coverage against the key is an evaluator
analysis after inference, never an input. Conditional citation accuracy must
always accompany citation coverage and unconditional risk to prevent an
all-abstaining system appearing perfect.

Predeclare three paired development contrasts for the primary cheap model:
**Q-I − Q-M**, **Q-P − Q-I**, and **Q-I − O-I**. The first investigates the
retrieval/information bundle, the second isolates a deterministic condition gate,
and the third compares models under identical observable tool evidence. Report
Q-D versus O-D as the matched closed-book reference. Freeze every retrieval rule,
gate predicate and threshold before replication. All six core conditions use
the same intended 24 development and 12 replication cases; Q-P derives from Q-I
without new API calls. No per-case choice of the best arm, best citation
hierarchy, or cheapest successful retry is allowed. Report the full
General/Type/Entry/Topic/Subtopic/Full Citation table as secondary outcomes rather
than choosing whichever column improves.

## Chance controls, counterfactuals, and statistical limits

Freeze deployable shortcut baselines using **the selected 24 development cases only**: constant
correct/incorrect decisions, a statement-type citation prior, and a visible
account-label/statement-type retrieval prior. Apply those fitted mappings to
replication without updating them. A rule-ID or gold-error-type selector is an
explicit oracle diagnostic, never a deployable chance baseline. All abstention,
coverage and risk denominators apply to shortcut baselines too.

A blocked label-permutation analysis may diagnose residual association: fix the
predictions and permute citation labels only among citable cases within the
predeclared company × statement-type blocks, preserving each block's label
multiset. Use all distinct permutations when feasible, otherwise 10,000 seeded
permutations with the finite-simulation correction `(1 + exceedances)/(B + 1)`.
Report the block sizes, movable-case fraction and null statistic distribution.
Singleton or constant-label blocks provide no test; do not relax the blocking
scheme after observing the answer. This is a conditional association diagnostic,
not an accounting-validity test or evidence that shuffled tasks are realistic.
Do not permute labels to create new model-facing accounting cases.

The stronger future control is a **reviewed paired counterfactual benchmark**:
change a necessary observable fact or reference join while preserving company,
account label, document style, amount/risk motifs and other superficial cues.
Both variants stay in the same split and separate model sessions; pair IDs are
hidden. The accountant reviewer must establish that the intervention changes
(or deliberately preserves) the governing conclusion and whether citations
should change. Score pairwise correctness and supported switching, not merely
any answer change. Remove each purportedly necessary source to test evidence
sufficiency. An agent-generated pair with its own generated gold cannot replace
that review and must remain an unvalidated software fixture.

For the eight-company, 24-case development set, show pooled and company-macro results,
paired company differences, and leave-one-company-out sensitivity. Any company
bootstrap interval is descriptive and unstable; neither the 24 selected cases
nor the historical 48 are independent filings or evidence of population coverage. For the **two-company replication**,
show the two company results separately and their range. Do not publish a
nominal cluster-bootstrap confidence interval or significance/noninferiority
claim from two clusters. Case-level Wilson/binomial intervals would also ignore
within-company dependence and are not a remedy.

No superiority claim follows from overlapping intervals, a positive point
estimate, zero observed false citations on four replication clean cases, or reduced cost
among only successful requests. A credible cost/quality finding reports all
failures, all costs, clean-case risk, citation coverage, the joint supported
outcome when available, and the exact small-company scope. A later validated
benchmark needs a fresh locked evaluation and a power/design analysis grounded
in independent companies or events, not just more variants of these statements.

## Required freeze and release artifacts

Before paid replication, save the protocol hash; partition and exclusion
manifest; source/accession hashes; corpus/license/effective-date manifest;
acceptable-label policy and validation status; model/provider registry; prompts
and output schema; retrieval/checker implementations; numeric token/tool caps;
condition-order schedule; retry policy; and cumulative worst-case cost forecast.
After the run, preserve immutable raw responses, stage/candidate packets,
attempt-level ledger records, all intended-case outcomes, failure reasons,
resource-measurement denominators, paired comparisons, and explicit deviations.

The paper must separate (1) source and label audits, (2) development method
gains, (3) two-company descriptive replication, and (4) an unvalidated proposal
for a future evidence-process benchmark. Neither this protocol nor another
model run completes completed accounting review or proves novelty.
