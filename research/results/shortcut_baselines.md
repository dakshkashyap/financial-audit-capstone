# Offline shortcut baselines

Inspected developmental sample; provisional labels

| Baseline | Exact agreement |
|---|---:|
| Judgment: always_incorrect | 32/48 (66.7%) |
| Judgment: always_correct | 16/48 (33.3%) |
| Citation: other-company global_prior | 5/16 (31.2%) |
| Citation: other-company statement_type | 7/16 (43.8%) |
| Citation: other-company statement_type_year | 5/16 (31.2%) |

Always-incorrect clean specificity is 0/16. Citation priors are conditional, evaluator-restricted diagnostics; they do not locate errors or decide whether a citation is needed.

- Only eight selected companies and sixteen provisional citation targets; fold estimates are unstable.
- Synthetic text/format shortcuts are not tested by these metadata baselines.
- Citable-only evaluation uses an evaluator restriction, not a deployed citable detector.
- No baseline reads the held-out company labels while predicting its citations.
- No paid model calls or new empirical accounting labels.
