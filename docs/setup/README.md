# `docs/setup/` — environment setup

Getting the project running, including without paying for API calls.

| Document | What it covers |
|---|---|
| [SETUP_FREE_MODELS.md](SETUP_FREE_MODELS.md) | Running against free local models (Ollama, Qwen, Llama) instead of paid APIs |
| [quick_start.sh](quick_start.sh) | Environment bootstrap script |

---

## The short version

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m core.verify_data      # confirm the datasets are intact
```

Then check everything still works:

```bash
python scripts/status.py        # ~25s
```

---

## Most of the project needs no API key

```mermaid
flowchart LR
    subgraph FREE["Runs offline — no key, no cost"]
        A["stage0_deterministic_gate"]
        B["stage1_concept_mapping"]
        C["stage1_taxonomy_citation"]
        D["citation_mcp_agent (heuristic, oracle)"]
        E["audit_patch_repair"]
        F["finmr_benchmark (verifier)"]
        G["full_pipeline (ablation)"]
    end

    subgraph PAID["Needs an API key"]
        H["baseline_auditbench (live run)"]
        I["stage2_llm_audit"]
        J["citation_mcp_agent --mode llm"]
        K["finmr_benchmark eval_finmr"]
    end

    style FREE fill:#dcfce7,stroke:#16a34a
    style PAID fill:#fee2e2,stroke:#dc2626
```

That includes the headline result — AuditPatch's 81.5% exact repair is fully
deterministic, so anyone can reproduce it with no key at all. The ablation also
runs free, because it reuses stored predictions committed to `results/`.

## Keys

Read from the environment:

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
```

Never commit a key, and never paste one into a chat or an issue. If one is
exposed, rotate it in the provider console — editing it out afterwards does not
help, because it stays in the history.

## First-run downloads

Two things fetch themselves and are gitignored:

| What | Size | Trigger |
|---|---|---|
| FASB US-GAAP taxonomy → `.cache/` | ~11 MB | First use of `core.taxonomy_graph` |
| FinMR dataset → `data/finmr/` | ~85 MB | `python -m approaches.finmr_benchmark.download_finmr` |

Both are self-healing — delete and they come back.
