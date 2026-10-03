# Evidence acquisition direction: implemented scaffold and research gates

This is a synthetic, unvalidated software prototype, not a released audit
benchmark. It establishes that paid retrieval, observable evidence witnesses,
private evaluation, and paired controls can be implemented without putting the
answer into the inference interface. No real financial filing, accounting
expert gold, fraud finding, model result, or verified novelty claim is attached
to its scores. It does not justify replacing the existing benchmark with a
larger synthetic benchmark and reporting its deterministic solver as AI progress.

## Why citation percentage alone cannot choose the next experiment

An exact citation score conflates detection, evidence sufficiency, retrieval,
paragraph applicability, and answer-key validity. Improving the final selector
against a questionable key can improve the percentage while making the audit
less defensible. First establish paragraph-level expert agreement, acceptable
alternative citations, the exact blind information boundary, and whether
different evidence could change the conclusion. Use the implementation audits
in the other review files to determine which reported historical scores are
actually reproducible. Treat 12% as a reported observation until its run,
schema, answer key, and denominator are identified.

The research hypothesis worth testing is narrower: **under a fixed evidence
budget, can a small-model agent obtain and connect sufficient evidence as
reliably as a single frontier baseline, at lower measured cost?** A separate
hypothesis asks whether validated deterministic consistency checks and a
conservative evidence verifier improve the small model's supported decisions.
Neither hypothesis is established by the prototype or a pilot over invalid
citations. A finding that the frontier model remains better is publishable
evidence if the benchmark and evaluation are sound; beating it is not a
prerequisite for an honest contribution.

## Implemented contribution seed

`research/evidence_budget.py` uses the Python standard library and constructs
eight opaque synthetic company aliases, each with a paired recognition-issue
and supported-recognition case. There are 16 cases and eight dependent clusters,
not 16 independent companies. Both cases have an identical balanced receivable
debit/revenue credit, amount, new-customer motif, receivables growth motif,
collection date, and year-end chronology. Balanced debits and credits do not
make premature recognition correct.

The target invoice references a contract and a shipment. The shipment references
one of three opaque receipt records. All variants contain the same early,
year-end-crossing, and late delivery timelines, with dispatch before acceptance.
The only counterfactual intervention selects the shipment's receipt reference.
The contract independently specifies dispatch or customer acceptance as its
synthetic transfer trigger. The crossing timeline can therefore be supported
or premature depending on that contract; an isolated customer register or
generic risk motif does not determine the label. This is an experimental rule
for a reference-joining task. Actual revenue recognition also depends on
contract enforceability, performance obligations, control indicators, pricing,
return rights, and other facts omitted here. Intent is never inferred.

The five required facts form two provenance paths:

```
journal -> invoice -> contract -> customer events
                    \ shipment -> customer events
```

The paths must join to the same journal, invoice, contract, shipment, customer,
and target receipt. Facts are distributed over two, three, or four documents.
The customer event register costs two arbitrary acquisition units; each other
document costs one. Payroll, depreciation, and cash documents are observable
distractors. Costs do not represent model-token dollars or real audit fees.

`PublicCase.initial_view()` returns the case ID, opaque company alias, initial
journal fact, task, allowed conclusions, and document catalog only. The
acquisition tool accepts a document ID, enforces the budget before returning
content, records successful acquisitions, and serves repeat requests from cache
without charging twice. Invalid IDs and over-budget requests return no document
facts. Trace entries record the returned fact IDs, charged cost, accumulated
cost, and a digest of the returned response. Returned objects are copies.

`PrivateGold` contains pair IDs, conclusions, the required graph, and minimum
required-document cost. It is separate from every inference response. Gold is
used only after the run. The local Python session is not a hostile-code sandbox:
a real runner must expose only the public tools and keep the session, seed,
gold, and evaluator server-side. Publishing a generator and fixed seed enables
reconstruction, so hidden-test seeds and mappings must be held out during
evaluation. A public corpus file includes document bodies for reuse; it must
not be preloaded into an experiment advertised as paid evidence acquisition.
Paired cases also require independent model sessions: shared conversation state
or access to another case's answers can reveal that a matched counterpart must
have the opposite conclusion. Keep pair IDs hidden and all variants in the same
split; neither hidden IDs nor deterministic fixture code protects against a
runner that exposes prior answers or lets cases share unrestricted memory.

## What the graph score establishes

The evaluator checks citations against **server-observed acquisitions**, not
against a model's account of what it read. A valid graph edge requires both
endpoints to have been observed and cited, plus a matching evaluator edge. Both
required connected paths must be submitted. A correct conclusion without these
paths is `correct_but_unsupported`. Invented facts and invalid edges get no
credit; even a complete correct witness with extra unsupported claims becomes
`contaminated_correct` and loses the strict supported-decision score.

`recognition_issue` and `supported_recognition` are definitive conclusions
under the simplified rule. `insufficient_evidence` is assessed separately as
justified or unnecessary abstention. `suspicious` is a provisional conclusion
and earns no definitive-decision credit. The demonstration reports supported
decisions, abstention, and acquisition cost separately.

This metric establishes an **acquired, connected evidence witness**. It does not
prove the model causally used that evidence, that its natural-language argument
is faithful, or that the evidence is authentic. The evaluator uses one canonical
graph and can under-credit a logically equivalent graph. Production annotation
must include acceptable alternative proofs, contradictory sources, provenance
trust, and independently reviewed sufficiency criteria. Avoid advertising a
trace metric as access to an agent's true internal reasoning.

## Reproduction and scope of verification

```
python -m unittest discover -s tests -p test_evidence_budget.py -v
python -m research.evidence_budget --output research/artifacts
```

The CLI exports `evidence_budget_public.json`, evaluator-only
`private/evidence_budget_gold.json`, and post-run `evidence_budget_demo.json`.
The demo compares catalog-order acquisition with document-type-priority
acquisition at budgets 0, 2, 3, 4, 5, and 8. Both policies solve using structured
observable facts and explicit reference joins. They neither accept nor read
private gold. Their performance is a software demonstration, not an LLM
experiment and not a comparison to Opus.
The current schema is deliberately solvable by a short reference-joining
program, and document titles make a productive acquisition order easy to find.
It establishes simulator invariants, not benchmark difficulty or the need for
an LLM. Richer uncertainty and independently reviewed evidence would be needed
before using this direction to rank financial reasoning systems.

Tests cover deterministic rebuilds; balanced matched pairs; chronology;
absence of private graph fields in tools; no budget overrun or double charge;
immutable returned copies; unsupported guesses; required connected edges;
invented facts; abstention; wrong-customer joins; and malformed answers.
Passing tests validate those invariants, not realistic accounting, sample
representativeness, fraud adjudication, or scientific novelty.

## Model system to evaluate after gold passes review

Use exactly one verified available frontier model as a frozen baseline. Do not
invent an OpenRouter model ID for an unavailable requested model. Other model
arms should be a small open-weight model or a very cheap hosted model whose
exact version, license, provider, context size, and dated token prices are
recorded. A cheap small-model API is a cost baseline; it is not reproducible
local open-weight inference unless the same weights are actually run locally.

Suggested public interface: an initial case, `request_document(document_id)`,
remaining budget, and a final JSON answer containing conclusion, cited fact
IDs, and provenance links. Keep models on the same corpus, tools, acquisition
budget, context cap, output cap, and stopping rules. Log prompt digests,
requests, response IDs, token usage, dollar cost, tool cost, latency, failures,
and retries. Attribute failed calls to the assigned arm; never silently drop
them or let cheaper arms retry indefinitely. A single frontier baseline should
receive the same observation policy as the small-model agent when comparing
models; a separate full-evidence arm can isolate acquisition from reasoning.

The small-model system should earn gains through public evidence: reference
joins and arithmetic checks, a compact planner selecting the next document,
retrieval from a dated permissible standards corpus, and a cheap verifier
checking factual support and applicability. The verifier should prefer
insufficient evidence over an unsupported paragraph. No component receives a
rule ID, injected-error annotation, generated answer key, or gold graph. Avoid
a frontier fallback inside the cheap agent if the claim is that small models
match a frontier model; that would conflate routing and model capability.

## Necessary experiments and annotation gates

1. **Validity gate:** two independently working accounting reviewers label the
   error, sufficient evidence, applicable standards, and acceptable alternative
   proofs/citations. Adjudicate disagreements and disclose agreement before and
   after adjudication. No reviewer has performed that work for this prototype.
2. **Shortcut gate:** test statement-only, metadata-only, document-type-only,
   motif-only, citation-prior, and shuffled-reference controls. Jointly shuffle
   facts where appropriate; arbitrary shuffling can itself make an accounting
   case invalid. Require a paired intervention to change the conclusion while
   preserving superficial cues. Ablate every required source to check that
   the annotation's necessity claim holds.
3. **Data gate:** source real public cases with lawful redistribution, exact
   accession/date/provenance, dated standards, amendments/restatements, and
   support excerpts. Distinguish pre-outcome evidence from later enforcement
   conclusions. A model must not receive the enforcement document naming the
   fraud when the task is to discover it. Do not present real filings combined
   with fabricated journal entries as an authentic engagement.
4. **Comparison gate:** freeze the benchmark and test protocol before running
   the locked evaluation. Compare one frontier direct baseline, one small direct
   baseline, the same small model with acquisition, and the small model with
   acquisition plus verification. Add full-evidence and graph-verifier ablations
   only if the budget allows them. Report raw denominators and all failures.
5. **Statistical gate:** keep both variants, paraphrases, related filings, and
   shared enforcement events together in train/test splits. Use company/event
   clusters for uncertainty and paired differences. Eight clusters permit an
   engineering pilot and descriptive results; they cannot establish broad
   financial-audit representativeness or a precise population improvement.
   Report per-company outcomes and sensitivity to leaving each company out.
6. **Release gate:** include source/license manifest, data card, label schema,
   annotation protocol, reviewer independence, blind runner, prompt/model
   registry, cost ledger, hidden-key boundaries, reconstruction instructions,
   tests, and archived raw outputs. Make externally unsupported claims explicit.

For the current USD 30–40 limit, spend nothing on a broad model sweep while the
gold is disputed. Run a small smoke check after validity gates, use measured
per-case cost to forecast the remaining paired run, impose a reservation-aware
total-dollar cap including retries, and hold a reserve for failures. Acquisition
units and dollar spend are separate budgets. A small number of companies reduces
rate pressure; it does not by itself produce an accurate representative result.

## Work sequence toward December 31, 2026

Dates below are planning targets from the user's deadline, not verified venue
deadlines or promises of acceptance.

| Target | Deliverable and stop condition |
| --- | --- |
| October 9 | Reproduce current scores, trace answer leakage, triage citation keys; no headline result before this passes. |
| October 23 | Accountant-reviewed task definition and pilot evidence cases; reject unsupported synthetic accounting. |
| November 6 | Frozen pilot schema, paired controls, public-only runner, and shortcut audit; record what remains unvalidated. |
| November 20 | Budgeted pilot with one frontier and a small/cheap model, cost audit, and per-company results. |
| December 4 | Reviewer adjudication, required ablations, related-work comparison, and venue/deadline check. |
| December 18 | Paper draft and code/data release candidate; independent reproduction and claim audit. |
| December 31 | Submission or public research artifact appropriate to the verified evidence and venue calendar. |

Existing work on financial fraud benchmarks, synthetic audit engagements,
agentic audit workflows, evidence retrieval, and process evaluation may already
cover substantial parts of this direction. A related-work novelty matrix must
be checked against the actual papers before selecting a contribution. The
plausible contribution is a validated paired evidence-acquisition evaluation
with budget-sensitive supported decisions and a reproducible cheap-agent
baseline, not the unverified claim that multi-hop fraud or evidence graphs are
new. Meeting a writing deadline and acceptance at a top conference are separate
outcomes.
