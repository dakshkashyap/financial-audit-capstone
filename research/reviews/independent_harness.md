# Independent pilot and evidence-acquisition review

This review used executable source inspection, local adversarial probes, and mocked/local tests. It made **zero model/API calls** and did not read or use credentials. Paid inference belongs to the root agent. The pilot is an exploratory agreement experiment against unvalidated labels; this review does not establish accounting efficacy.

## Findings and repairs verified

| Priority when discovered | Defect reproduced | Current status |
|---|---|---|
| P1 | A graph containing all possible ordered fact-ID pairs, plus a fabricated cited fact, earned `supported_decision=true` when the gold paths were contained somewhere in the graph. One local fixture had edge precision 5.56% and 85 invalid links yet `supported_correct`. | Fixed by method author: complete paths plus clean acquired claims/valid links are required; contaminated answers lose supported-decision credit. All-pairs regression passes. |
| P1 | A provider cost exceeding its reservation was detected on the current call, but cached-response resume could forget the anomaly and allow future calls. | Fixed by harness author: durable completion/reservation reconciliation is checked when opening the ledger. Restart-overcharge regression passes. |
| P2 | An actual statement substring accompanied by invented `row=999` passed quote verification. | Fixed: declared statement rows must exist and the quote must occur on the declared row. Local quote attribution tests pass. |
| P2 | Scoring could mix stale prediction files after prompt/config/model changes because it did not verify their condition identity and input hash. | Fixed: scoring validates run manifest, current condition identity, model, condition name and case membership. |
| P2 | Arbitrary observations/hypotheses from the first model pass were inserted into the system message, elevating untrusted generated content. | Fixed: the stable system prompt remains separate; the staged analysis is user-message data. Two-call regression passes. |
| P2 | Token-only cost estimation ignored possible nonzero per-request catalogue fees. | Fixed: nonzero request fees are refused. |
| P2 | An early prepared manifest did not include newly configured FY2020–2024 bounds. | Regenerated before final protocol; the actual pilot now contains FY2020–2024 only. |

The adversarial graph check was communicated to the method author and root before model experiments. The budget/scoring issues were communicated to the harness author. The final protocol was frozen after the repairs; this reviewer did not modify their owned files or change prompts/configuration during paid inference.

## Invariants independently checked

- `public_input` uses a positive whitelist: company/cik/year/statement/period/unit metadata, statement text, transaction text and opaque case ID. Extra `rule_id`, citations and answer-key fields in a source dictionary are discarded.
- Inference reads `public_inputs.jsonl` and its frozen manifest, not `scoring_only.jsonl`. The answer key is opened only by preparation/stratification and the separate scoring command.
- The final pilot has eight companies and 48 cases, with 16 controls, 16 detection-only errors and 16 citable errors. Its years are 2020–2024. A case-level API request supplies one independent whitelisted case; the API does not receive the whole dataset or other variants.
- Malformed, failed and missing predictions remain in every applicable accuracy denominator. A malformed citation is not converted into successful abstention. A citation-only match cannot substitute for the separate joint detection/type/row/citation metric.
- Conditions use the same frozen public input SHA-256; one exact frontier model ID and two allowlisted cheap models are accepted. No automatic model fallback or retry is implemented. Returned model mismatches are failures.
- An exclusive durable ledger lock prevents concurrent default-ledger runs. Upper-bound reservations are written and fsynced before requests. Failures, unknown outcomes and timeouts retain their reservations. An already reserved request with no durable response cannot automatically retry.
- UTF-8 byte counts plus framing allowance provide deliberately loose input-cost estimates, with bounded completion tokens and catalogue/provider price caps. Unknown/tiered prices and nonzero per-request fees are refused. Reported actual charges are separate from reservations; missing usage costs remain unknown, not zero cost claims.
- Acquisition sessions return no document bodies on budget denial. Duplicate reads are cached without double charging. Initial/tool-returned data contain no private graph, required-path or expected-label fields. Only server-recorded successful acquisition establishes observation; caller-supplied traces do not.
- The deterministic evidence fixture pairs issue/control cases with identical initial statements, amounts, motifs, contract and all event dates; only the target shipment join changes. Event chronology respects dispatch before acceptance. The rule baseline joins observable IDs and uses no private gold.

## Remaining interpretive limits

Quote substring verification proves textual presence and row attribution, **not entailment, relevance or accounting authority**. A model can quote a real but irrelevant line. Report quote verification as an engineering trace check; do not call it validated rationale quality.

The selected source has synthetic component ledgers and unvalidated governing-paragraph keys. Four pilot company/year/statement groups have two variants in the public pack. Independent API requests prevent direct cross-case diffing by the model, but correlated variants are still clustered observations and must never be treated as independent test examples for narrow uncertainty claims. The final 48-case cohort is development exploration, not untouched final testing or a representative company sample.

The evidence prototype is a deterministic fixture with readily informative document types, arbitrary budget units, and a canonical author-specified graph. Its success shows that acquisition, provenance and budget accounting work as software. It does not show novel audit competence, causal faithfulness of a model's reasoning, fraud detection, or independent accountant correctness. Valid alternative proof graphs might be under-credited by the canonical graph; expert annotation is needed before research use.

The `$5` ledger cap is local to the configured ledger path; it is not an account-wide OpenRouter spending limit. Root-controlled execution uses the same ledger. Deliberately selecting a separate ledger would define a separate local budget, so research runs must record and retain the canonical path.

## Local verification

At review completion:

```text
python -m unittest discover -s tests -p 'test_research_harness.py' -v
17 tests passed

python -m unittest discover -s tests -p 'test_evidence_budget.py' -v
14 tests passed
```

No further paid-run prompt, model or config changes are proposed by this review. Accounting gold adjudication and independently designed, company-held-out final experiments remain prerequisites for a publication efficacy claim.
