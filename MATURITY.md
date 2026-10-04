# How far each approach can be trusted

[STATUS.md](STATUS.md) answers "does it run", and a script generates it. This file
answers "should you believe it", which is a judgement call. Written honestly —
including the parts that did not work.

Four verdicts are used:

- **Solid** — runs, measured at full scale, reproducible, defensible in the report
- **Works, capped** — runs and is measured, but has a known ceiling we cannot
  currently raise
- **Prototype** — runs, but not measured well enough to make claims from
- **Negative result** — worked as designed and told us the idea does not pay off.
  Kept deliberately: knowing this saved us building on it

---

## Solid

### `audit_patch_repair` — the strongest result we have
**81.5% exact repair on 332 real SEC filings, 0 regressions.**

Measured against official DQC rule labels, so ground truth is an institutional
artifact rather than our opinion. Fully deterministic — no LLM in the numerical
path — so the numbers are exactly reproducible on any machine.

Where it is weak, and we report rather than hide it: `DQC_US_0117` (dimensional
aggregation) scores 36.4% against 96.5% on calculation-tree errors. Solving
backwards for a missing component needs the whole filing, and the dataset
sometimes only contains part of it. The value is not recoverable, not
mis-computed.

Also note the pipeline proposes repairs for 178 of 332 records. The 81.5% is
measured on those. It abstains elsewhere rather than guessing, which is the right
behaviour but does mean the headline covers a little over half the dataset.

### `stage0_deterministic_gate` — the best-validated component
**0% false positives on clean statements, 94.7% error-type accuracy when it fires.**

The most trustworthy thing in the repo, because it can only speak when it has a
proof. Directly fixes the baseline's worst failure (50% false alarms). The
trade-off is deliberate and should be stated whenever the number is quoted: it
stays silent on ~62% of real errors. Precision is its job; coverage is not.

### `finmr_benchmark` — infrastructure, and it holds up
Loading, parsing and DQC verification of 332 real filings. Everything downstream
depends on it and nothing downstream has contradicted it. The manual review in
[docs/results/finmr_manual_review.md](docs/results/finmr_manual_review.md) checked
labels by hand and they stood.

### `full_pipeline` — produces the argument for the whole architecture
The ablation is the cleanest evidence we have that the architecture, not the
model, is doing the work: false alarms 50% → 28.7% at a **fixed** model. Runs with
no API calls because it reuses stored predictions, so anyone can re-run it.

### `baseline_auditbench` — a faithful control
Reproduces the paper's setup with its prompt kept verbatim, which is what makes
every comparison legitimate. Nothing novel here by design.

*Caveat: scoring loads BERTScore (roberta-large), so a cold run takes ~8 minutes
regardless of `--n`. This is why `status.py` skips it in quick mode.*

---

## Works, capped

### `stage1_taxonomy_citation` — correct approach, hard ceiling
Citations are looked up in the official FASB linkbase, so **it is structurally
incapable of inventing one**. That property is worth more than the accuracy
number and should be the thing we claim.

The ceiling: the correct governing topic is present in a concept's candidate arcs
only **~28%** of the time. The linkbase attaches presentation topics (210, 220,
S99) and sometimes irrelevant ones (852 Reorganizations) to face-of-statement
concepts. So a single deterministic pick is capped near the paper's own 26% — and
no smarter picking strategy can fix that, because the answer often is not in the
candidate set at all.

Do not present this as "our citation accuracy is low". Present it as "the taxonomy
alone does not contain the answer often enough, and here is the measurement that
proves it."

### `stage1_concept_mapping` — works on curated labels, and that is the real bottleneck
82% row coverage on the sampled AuditBench statements, but that number flatters
it: the static map only contains labels somebody thought to add, so it degrades on
companies and wordings outside the curated set.

**This is the most important unsolved problem in the project.** Everything
downstream — citation, rule checking, repair — is gated on getting the concept
right. FinAuditing's FinSM task measures exactly this and the best LLMs score
9–13%.

`edgar_xbrl.py` is the principled fix: recover the filer's *own* XBRL tags from
SEC EDGAR, collapsing an 18,000-concept guess into a lookup over the 300–600
concepts that company actually uses. It is implemented and off by default
(`use_edgar_xbrl=False`) because it needs network access and reliable company-name
resolution. Turning it on and measuring it is the highest-value next task.

---

## Negative result

### `citation_mcp_agent` — proved the point, did not improve the score
Ran as a real experiment over 42 items in three conditions.

What it **did** establish, and this is a genuine finding:

- **0 invented citations.** Every accepted answer was verified against the
  taxonomy first.
- **100% grounded accept rate**, with a written rationale for every pick.

What it **did not** do: improve accuracy. Tool-locked LLM scored 19.0%, identical
to plain lookup. The oracle condition explains why — a *perfect* chooser given the
same candidates scores 26.2%, so the correct answer was usually absent from the
candidate list. **The bottleneck is taxonomy coverage, not the model.**

This is worth presenting precisely because it is negative. It says grounding
solves hallucination but not coverage, and it is what pushed the project toward
using the LLM to *explain* a verified decision rather than to *make* one — which
is what `audit_patch_repair` does.

---

## Prototype

### `stage2_llm_audit` — the least validated thing in the repo
The design is right: call the model only when the gate abstains, hand it the
verified-consistent flag and a grounded candidate set. But it is the weakest
evidence base here.

- No standalone entry point; only reachable through `full_pipeline`
- Needs an API key, so it is not in the offline reproducible set
- Only measured in [docs/results/stage2_comparison.md](docs/results/stage2_comparison.md)

If someone asks which part needs work before the final report, this and the
concept mapper are the honest answers.

---

## Summary

| Approach | Verdict | The number to quote |
|---|---|---|
| `audit_patch_repair` | Solid | 81.5% exact repair, 0 regressions, 332 real filings |
| `stage0_deterministic_gate` | Solid | 0% false alarms, 94.7% type EM when fired |
| `full_pipeline` | Solid | false alarms 50% → 28.7% at fixed model |
| `finmr_benchmark` | Solid | 332 filings, 3 DQC rule families |
| `baseline_auditbench` | Solid (control) | 50% false-alarm rate — the problem statement |
| `stage1_taxonomy_citation` | Works, capped | 0 possible hallucinations; ~28% candidate coverage |
| `stage1_concept_mapping` | Works, capped | 82% on curated labels; live-EDGAR route unmeasured |
| `citation_mcp_agent` | Negative result | 0 invented citations; no accuracy gain (19.0% vs 26.2% ceiling) |
| `stage2_llm_audit` | Prototype | not independently measured |

**If you only present three things:** the AuditPatch repair result, the
deterministic gate's false-alarm fix, and the citation experiment's zero
hallucinations. Those are measured, reproducible, and none of them depend on
trusting a model's output.
