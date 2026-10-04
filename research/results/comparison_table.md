# Measured development results

Frozen primary development cohort: 48 cases / 8 companies, FY2020–2024; 16 clean, 16 detection-only, 16 nominally citable. These results are not comparable to the user-provided historical screenshot without its exact data, predictions and protocol.

General denominator=48; Error Type and Error Entry=32 injected cases; Topic, Subtopic and Full Citation=16 citable cases. Row agreement is evaluated separately from type agreement. Failures and missing predictions receive zero credit; abstentions are never clean decisions.

Citation scores require a schema-valid response and one syntactically valid full ASC code, then compare its topic, subtopic or full paragraph to the provisional key. They do not establish accounting applicability. Subtopic is a newly derived reporting statistic; primary scores and predictions are unchanged.

## Frozen primary comparison

| Model | Setup | General | Error Type | Error Entry | Topic | Subtopic | Full Citation | Input Tokens | Output Tokens | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Opus 5.5 | Direct · 29/48 valid | 60.4% | 78.1% | 75.0% | 68.8% | 68.8% | 68.8% | 1,985 (n=48) | 712 (n=48) | 8.3s (n=48) |
| Qwen3-8B | Direct · 47/48 valid | 64.6% | 50.0% | 15.6% | 0.0% | 0.0% | 0.0% | 1,385 (n=48) | 260 (n=48) | 4.7s (n=48) |
| Qwen3-30B-A3B | Direct · 16/48 valid | 22.9% | 21.9% | 6.2% | 18.8% | 18.8% | 18.8% | 1,391 (n=17) | 447 (n=17) | 1.8s (n=48) |
| Qwen3-30B-A3B | Evidence → decision · 3/48 valid | 2.1% | 3.1% | 3.1% | 6.2% | 6.2% | 0.0% | 1,637 (n=15) | 329 (n=15) | 1.3s (n=48) |

## Separate incomplete post-hoc diagnostics

| Model | Setup | General | Error Type | Error Entry | Topic | Subtopic | Full Citation | Input Tokens | Output Tokens | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Opus 5.5 | Schema + low reasoning; stopped · 35/48 valid | 70.8% | 65.6% | 65.6% | 68.8% | 68.8% | 68.8% | 2,706 (n=36) | 582 (n=36) | 7.7s (n=37) |
| Qwen3-8B | Evidence → decision; stopped · 7/48 valid | 8.3% | 3.1% | 3.1% | 0.0% | 0.0% | 0.0% | 2,547 (n=10) | 502 (n=10) | 8.4s (n=11) |

## Measurement notes

- Token means sum all requested stages per case, including format-invalid responses, and include only cases with complete provider usage. Each n is the number of cases with the required measurement. Missing usage is excluded, never imputed as zero.
- Latency is mean summed measured API request time per attempted case, including failed requests. It excludes local processing and the post-hoc wrapper's pacing, so it is not end-to-end wall time. Heavy rate-limit failures make speed comparisons unreliable.
- Post-hoc conditions retain all 48 eligible cases but stopped at the first provider failure: Opus 37 attempted / 11 unrequested (HTTP 503); Qwen8 11 attempted / 37 unrequested (HTTP 429). They cannot replace the frozen baseline or establish a ranking. Opus also changes schema/reasoning/output budget.
- The local before/after diagnostic measures parser transfer on synthetic component evidence, with no Stage 2 LLM and forced-offline taxonomy. It is not a complete baseline-versus-pipeline model comparison or evidence of realistic audit efficacy.
- Only one frontier family was used. No new GPT-4o, Llama 70B or DeepSeek results were generated. No measured cheap-model superiority is supported.
