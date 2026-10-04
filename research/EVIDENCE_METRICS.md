# Evidence-supported scoring contract

`research/evidence_metrics.py` implements post-run structural scoring. It accepts
**evaluator-owned, release-validated** IntelliAudit annotations, a public prediction,
and an independently logged runner acquisition trace. It never supplies annotations
or expected proof paths to inference. Calling a record `expert_reviewed` is not
proof that a human reviewed it: the canonical upstream release gate must validate
records first. Fictional unit-test records exercise branches, not human validation.

## Metrics and boundaries

- `label_correct`: exact conclusion agreement on an eligible reviewed case. Valid
  abstention on a resolvable case gets no static diagnosis credit.
- `supported_decision`: correct label plus at least one accepted sufficient proof,
  including required fact joins/refutations, acquired evidence and accepted authority.
  All explicitly asserted claims must have annotated support; extraneous unsupported
  facts, authorities or edges invalidate supported success.
- `warranted_abstention`: a valid insufficient-evidence response when an admissible
  proof is not acquired, or the frozen gold is itself insufficient. Report this with
  decision coverage and acquired cost: an agent that obtains nothing and abstains
  is not a successful investigator. `warranted_response` must never be the only
  headline metric, because such a strategy may score well on it.
- `citation_set_correct`: one accepted authority-ID set, acquired and applicable.
  Accepted alternatives can contain multiple paragraphs. IDs map to curator-verified
  paragraph codes and versioned sources; mere matching of a code is insufficient.
  `citation_abstention_correct` separately records withholding a citation when the
  authority disposition is non-governing. Asserting a paragraph in that case
  prevents supported-decision credit even if the source is otherwise applicable.
- Counterfactual `pair_both_correct` and `pair_both_supported`: both pair members
  must be correct/supported. Flipping two wrong answers gets zero pair credit.
- Missing/failed/invalid predictions stay in all eligible denominators. Unreviewed
  or unresolved gold is explicitly excluded with its count, never silently credited.
  Aggregation requires the entire frozen roster, including missing predictions.

## Acquisition and authority

The trusted trace records document ID, status and charged integer cost. The scorer
replays availability at the investigation cutoff, budget, cache returns and optional
returned-fact IDs. It rejects unacquired, unavailable, post-cutoff or unknown evidence,
and inconsistent traces.
Initially visible documents remain admissible at the cutoff even when they cannot
be requested again. Nonvisible, non-obtainable documents cannot be acquired.
Integer acquisition units are an experimental cost model;
they are separate from the real model API ledger and do not estimate dollars or
account for time. This protocol makes unsuccessful evidence acquisitions free;
change that policy prospectively if a future task charges for them.

Applicability checks enforce explicit annotation predicates: source type, reporting
framework, jurisdiction, entity scope, assertion family, effective period and acquired
required/refutation facts. Requiring effectiveness across the entire period is a
conservative default, not a universal accounting interpretation. Early adoption,
transition rules and exceptions must be explicitly adjudicated into the annotation
and a revised prospective contract when relevant. The software cannot infer legal
meaning, narrative entailment, undisclosed facts, source authenticity or genuine
reviewer qualifications. Free-text explanations are not scored as entailed claims.

## Usage

```python
from research.evidence_metrics import evaluate_case, summarize

score = evaluate_case(
    reviewed_annotation, submitted_prediction, trusted_runner_trace,
    budget=10,
    document_costs=curator_document_costs,
    authority_document_ids=curator_authority_source_mapping,
    claim_supports=curator_acceptable_claim_proofs,
)
report = summarize(all_case_scores, expected_case_ids=frozen_ids, pairs=reviewed_pairs)
```

Run `python -m unittest discover -s tests -p test_evidence_metrics.py -v` for
alternative-proof acceptance, wrong-but-flipping pairs, post-cutoff sources,
unacquired citations, failures, missing predictions and invalid budgets. No new
model performance is claimed by these scoring primitives.
