# Approaches

One folder per distinct approach. Each is independently runnable and documented,
and each folder's README states what the approach does, why it exists, how to run
it, and what it scored.

They are listed in pipeline order, but they are not a strict chain — several were
built as alternatives to each other, and the READMEs say so where it matters.

---

## Pipeline order

```
baseline_auditbench          the thing we are trying to beat
        │
        ▼
stage0_deterministic_gate    catch what arithmetic alone can prove
        │
        ▼
stage1_concept_mapping       label  →  official XBRL concept
        │
        ▼
stage1_taxonomy_citation     concept →  real FASB ASC citation
        │
        ├──────────────► citation_mcp_agent     same job, exposed as MCP tools
        │                                        so an LLM can only pick real ones
        ▼
stage2_llm_audit             focused LLM, only when the gate abstains
        │
        ▼
full_pipeline                stage 0 → 1 → 2 end to end + ablation

audit_patch_repair           the current research direction: not just detect,
                             but localize, repair, revalidate and certify

finmr_benchmark              dataset plumbing + baselines the above evaluate on
```

---

## Which one should I look at?

| If you want to… | Go to |
|---|---|
| See the published baseline we are measured against | `baseline_auditbench` |
| See how we avoid calling an LLM at all when maths suffices | `stage0_deterministic_gate` |
| See how a text label becomes a machine-readable concept | `stage1_concept_mapping` |
| See how a citation is looked up instead of recalled | `stage1_taxonomy_citation` |
| See the MCP server and the tool-locked citation experiment | `citation_mcp_agent` |
| See the current headline result (81.5% exact repair) | `audit_patch_repair` |
| See what the deterministic architecture adds to an LLM | `full_pipeline` |

---

## Shared code

Anything used by two or more approaches lives in [`core/`](../core/) rather than
being duplicated:

| Module | Purpose |
|---|---|
| `core.paths` | Single source of truth for data, results and cache directories |
| `core.parser` | AuditBench loaders and table parsing |
| `core.metrics` | Scoring functions |
| `core.stage0_common` | `Finding`, table building, label normalization |
| `core.taxonomy_graph` | FASB US-GAAP reference linkbase graph |
| `core.finmr_parser` | FinMR record → XBRL facts, contexts, calculation arcs |
| `core.finmr_verifier` | FinMR DQC rule checks |
| `core.model_backends` | Unified LLM client across providers |
| `core.auditor_prompt` | The AuditBench paper's prompt, verbatim |
| `core.verify_data` | Dataset integrity check |

---

## Running anything

Always from the repository root, as a module:

```bash
python -m approaches.<approach>.<entry_point> [--n N]
```

Every evaluation writes machine-readable output to the repo-root `results/`
directory.
