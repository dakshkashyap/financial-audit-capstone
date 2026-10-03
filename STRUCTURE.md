# How this repository is organised

This branch consolidates work that used to live across six separate branches. This
file explains the shape it landed in and, more importantly, *why* — so you know
where to put the next thing you write.

---

## The one-sentence version

**Shared code goes in `core/`, each distinct approach gets its own folder under
`approaches/`, and everything written goes in `docs/`.**

---

## The whole repository

```mermaid
flowchart TD
    ROOT["financial-audit-capstone/"]

    ROOT --> CORE["core/<br/><i>shared code — 11 modules</i>"]
    ROOT --> APP["approaches/<br/><i>the work — 9 folders</i>"]
    ROOT --> DOCS["docs/<br/><i>everything written — 6 folders</i>"]
    ROOT --> DATA["Error_insertion/ · Raw_table_data/<br/>transaction_data/ · data/<br/><i>datasets in, read-only</i>"]
    ROOT --> RES["results/<br/><i>numbers out, machine-readable</i>"]
    ROOT --> SCR["scripts/<br/><i>repo utilities</i>"]

    style CORE fill:#dbeafe,stroke:#2563eb
    style APP  fill:#dcfce7,stroke:#16a34a
    style DOCS fill:#fef3c7,stroke:#d97706
    style DATA fill:#f3f4f6,stroke:#6b7280
    style RES  fill:#f3f4f6,stroke:#6b7280
    style SCR  fill:#f3f4f6,stroke:#6b7280
```

At the top level there are also four files worth knowing:

| File | What it is |
|---|---|
| `README.md` | The front door — what the project is, headline results, quick start |
| `STATUS.md` | **Auto-generated.** Does each approach still run? Never hand-edit |
| `MATURITY.md` | Hand-written. How far each approach can be trusted |
| `requirements.txt` | One dependency list for everything |

---

## The three layers

Read this diagram top to bottom — it is the dependency direction, and it never
runs the other way.

```mermaid
flowchart TD
    subgraph L3["docs/ — describes, imports nothing"]
        D["research · architecture · results<br/>presentations · meetings · setup"]
    end

    subgraph L2["approaches/ — one folder per approach"]
        A1["baseline_auditbench"]
        A2["stage0_deterministic_gate"]
        A3["stage1_concept_mapping"]
        A4["stage1_taxonomy_citation"]
        A5["stage2_llm_audit"]
        A6["citation_mcp_agent"]
        A7["audit_patch_repair"]
        A8["finmr_benchmark"]
        A9["full_pipeline"]
    end

    subgraph L1["core/ — shared, depends on nothing above it"]
        C["paths · parser · metrics · stage0_common<br/>taxonomy_graph · finmr_parser · finmr_verifier<br/>model_backends · auditor_prompt · verify_data"]
    end

    L2 --> L1
    L3 -.describes.-> L2

    style L1 fill:#dbeafe,stroke:#2563eb
    style L2 fill:#dcfce7,stroke:#16a34a
    style L3 fill:#fef3c7,stroke:#d97706
```

**`core/` never imports from `approaches/`.** That is the one structural rule. If
you find yourself wanting to break it, the thing you are reaching for belongs in
`core/`.

Approaches *may* import each other, and that is fine — the import line documents
the dependency. When `audit_patch_repair` says
`from approaches.stage0_deterministic_gate import stage0a`, you can see the
relationship without reading a design doc.

---

## Where does a new file go?

```mermaid
flowchart TD
    START["I wrote a new file"] --> Q1{"Is it code?"}

    Q1 -- No --> Q2{"What kind of writing?"}
    Q2 -- "Paper analysis"      --> R1["docs/research/"]
    Q2 -- "Design or diagram"   --> R2["docs/architecture/"]
    Q2 -- "Findings write-up"   --> R3["docs/results/"]
    Q2 -- "Slides or report"    --> R4["docs/presentations/"]
    Q2 -- "Meeting or planning" --> R5["docs/meetings/"]

    Q1 -- Yes --> Q3{"Will two or more<br/>approaches use it?"}
    Q3 -- Yes --> R6["core/"]
    Q3 -- No  --> Q4{"Does it belong to an<br/>existing approach?"}
    Q4 -- Yes --> R7["that approach's folder"]
    Q4 -- No  --> R8["new approaches/&lt;name&gt;/<br/>+ __init__.py + README.md"]

    style R6 fill:#dbeafe,stroke:#2563eb
    style R7 fill:#dcfce7,stroke:#16a34a
    style R8 fill:#dcfce7,stroke:#16a34a
```

---

## How the approaches connect

Not a strict chain — some were built as alternatives to each other.

```mermaid
flowchart TB
    B["baseline_auditbench<br/><i>the thing we are beating</i>"]
    S0["stage0_deterministic_gate<br/><i>prove it with arithmetic</i>"]
    S1A["stage1_concept_mapping<br/><i>label → XBRL concept</i>"]
    S1B["stage1_taxonomy_citation<br/><i>concept → ASC citation</i>"]
    MCP["citation_mcp_agent<br/><i>same job, as MCP tools</i>"]
    S2["stage2_llm_audit<br/><i>focused LLM on abstain</i>"]
    FP["full_pipeline<br/><i>0 → 1 → 2 + ablation</i>"]
    AP["audit_patch_repair<br/><i>localize · repair · revalidate</i>"]
    FM["finmr_benchmark<br/><i>real filings + DQC rules</i>"]

    B -.->|"motivates"| S0
    S0 --> S1A --> S1B
    S1B -->|"alternative"| MCP
    S1B --> S2
    S2 --> FP
    S0 --> AP
    S1B --> AP
    FM --> AP
    FM --> FP

    style AP fill:#dcfce7,stroke:#16a34a,stroke-width:3px
    style B  fill:#fee2e2,stroke:#dc2626
```

`audit_patch_repair` is outlined because it is the current research direction and
where the headline result comes from. `baseline_auditbench` is red because it is
the control, not a contribution.

---

## How data flows through a run

```mermaid
flowchart LR
    IN["Error_insertion/<br/>Raw_table_data/<br/>data/finmr/"] --> P["core/parser.py<br/>core/finmr_parser.py"]
    P --> AP["an approach<br/>runs"]
    TAX[".cache/<br/>FASB taxonomy XML"] --> TG["core/taxonomy_graph.py"]
    TG --> AP
    AP --> OUT["results/*.json"]
    OUT --> W["docs/results/*.md<br/><i>hand-written analysis</i>"]
    OUT --> ST["STATUS.md<br/><i>auto-generated</i>"]

    style IN  fill:#f3f4f6,stroke:#6b7280
    style TAX fill:#f3f4f6,stroke:#6b7280
    style OUT fill:#fef3c7,stroke:#d97706
```

Two things to keep straight:

- **`results/` versus `docs/results/`** — the first is JSON a script writes, the
  second is prose a human writes about that JSON.
- **`.cache/` is gitignored and self-healing.** The FASB taxonomy (~11 MB)
  downloads on first use. Delete it and it comes back.

---

## Why it is shaped this way

**Why `core/` instead of duplicating helpers into each approach?**
Six of the nine approaches parse AuditBench tables and four use the taxonomy
graph. Duplicating those would mean six copies drifting apart, and the results
would stop being comparable across approaches — which is the entire point of
having approaches side by side.

**Why folders per approach instead of one big package?**
Because the deliverable is a comparison. When a supervisor asks "what did you try
for citations?", the answer should be a folder you can point at, with a README
that states what it scored, rather than a set of files you have to identify by
name.

**Why no `01_`, `02_` number prefixes?**
Python identifiers cannot start with a digit — `approaches.01_baseline` will not
import. The ordering lives in the `stage0`/`stage1`/`stage2` prefixes and in
[`approaches/README.md`](approaches/README.md) instead.

**Why is everything run with `python -m` from the root?**
Because the root is then on `sys.path`, so `core` and `approaches` both resolve
with no setup. That is what let us delete every `sys.path.insert` hack during the
restructure. It also means **you must run from the repository root** — that is the
only real constraint the layout imposes.

**Why `core/paths.py` instead of `os.path.dirname(__file__)`?**
Modules sit at different depths, so anchoring paths to a file's own location
breaks the moment it moves. Roughly thirty of those broke during this restructure.
Everything now resolves through one module, and `RESULTS_DIR` is overridable via
`AUDIT_RESULTS_DIR` so a health check can write to scratch without overwriting
committed evidence.

---

## Every folder has a README

| Folder | README |
|---|---|
| Root | [README.md](README.md) |
| `core/` | [core/README.md](core/README.md) |
| `approaches/` | [approaches/README.md](approaches/README.md) — plus one inside each of the 9 |
| `docs/` | [docs/README.md](docs/README.md) — plus one inside each of the 6 |
| `results/` | [results/README.md](results/README.md) |
| `data/` | [data/README.md](data/README.md) |
| `scripts/` | [scripts/README.md](scripts/README.md) |

Each approach README answers the same four questions in the same order: what it
does, why it exists, how to run it, and what it scored.
