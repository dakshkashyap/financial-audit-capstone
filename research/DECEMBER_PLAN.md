# Research plan: October 2 to December 31, 2026 (Pacific dates)

Target a validated public release and submission-ready preprint by December 15,
with December 31 as the buffer. Conference acceptance and publication cannot be
guaranteed by that date. ICLR 2027 submission closed September 25; FinNLP 2026
deadlines passed. The October 12 ARR deadline is too close for an unvalidated
new benchmark. Verify venue policies again before submitting. FinAI's October
15 challenge deadline is a possible separate small submission if it fits the
already available data; it should not displace validation of the main work.

| Dates | Concrete deliverable | Exit criterion |
|---|---|---|
| October 2–9 | Source audit, clean integration, 8-company pilot, professor briefing | No leaked label inputs; exact metrics; reproducible traces and costs |
| October 10–23 | One narrow task specification: sufficient evidence for revenue-recognition/cutoff judgments, with explicit citation applicability | One accountant reviews scope, rules, effective dates and control definitions; single-reviewer limitation disclosed |
| October 24–November 6 | 5–10 company-derived engagements, paired controls, typed acquisitions with costs | Original documents, provenance and balanced ledgers; source motifs alone cannot reveal answers |
| November 7–20 | Single-accountant blind review, reconciliation and delayed repeats; hidden proof graphs | Disagreements reported; ambiguous/unidentifiable items marked or excluded prospectively |
| November 21–December 4 | Freeze test split; one frontier and cheap-model evaluation | All conditions use the same observable inputs; budget and errors included; no test-driven tuning |
| December 5–15 | Ablations, artifact check, paper and preprint | Matched comparisons, company-level uncertainty, licenses and limitations completed |
| December 16–31 | Reproduction by teammate and submission buffer | Independent reproduction from tagged release; venue-specific compliance |

Assign owners at the next meeting: accounting/gold (one qualified accountant),
data/provenance, method/harness, and analysis/artifact. A student review is useful,
but it is not a substitute for the documented single-expert accounting review claimed
in a dataset card.

Preserve most of the $30–40 model budget for a frozen experiment. This work uses
a $5 ceiling for development. Final experiment planning must estimate worst-case
tokens and tool costs first, then choose a small case set; 5–10 companies limits
cost but produces wide confidence intervals and narrow population coverage.

Preregister paired company-level differences, strict paragraph agreement,
evidence-supported judgment, clean specificity, selective risk/coverage, proof
recall, wasted acquisitions and dollars per supported correct decision. Include
direct cheap/frontier, same-model structured prompting, deterministic tools,
retrieval without entailment checks, uniform/random acquisition and oracle
evidence as explicitly labeled upper bounds. Do not claim noninferiority from
overlapping intervals or one development sample.
