# Stage 1 — Taxonomy citation

**Look the accounting standard up instead of recalling it.**

Given an XBRL concept from [`stage1_concept_mapping`](../stage1_concept_mapping/),
produce the FASB ASC citation that governs it — by reading the official FASB
US-GAAP reference linkbase, not by asking a model what it remembers.

## Why it exists

Citation is the single worst-performing task in the AuditBench paper, and the
failure mode is specific: the model invents rule numbers that look plausible and
do not exist. Inventing a legal citation is disqualifying in auditing.

A citation is a *retrieval* problem, so this stage treats it as one. The
`TaxonomyGraph` (in `core/taxonomy_graph.py`) downloads the FASB US-GAAP 2023
reference linkbase, indexes every concept's codification references, and can
answer "which ASC topics does this concept point at?" from the authoritative
source. Nothing here can produce a citation that does not exist.

## The problem this stage exposes

The raw linkbase is not a clean answer key. For face-of-statement concepts it
attaches presentation topics (210 Balance Sheet, 220 Income Statement, 235, S99
SEC staff guidance) and occasionally irrelevant ones (852 Reorganizations)
alongside the correct subject-matter topic.

Measuring against the AuditBench citation ground truth, the correct governing
topic is present in a concept's candidate arcs only about **28%** of the time. So
a single deterministic pick is capped near the paper's own 26% — the ceiling is
the taxonomy's coverage, not the picking strategy. `concept_citation.py` exists to
separate subject-matter topics from presentation ones and squeeze what it can out
of that.

This finding is what motivated [`citation_mcp_agent`](../citation_mcp_agent/):
if a single pick is capped, expose the whole candidate set as tools and let an
agent choose, with validation on the way out.

## Files

| File | Purpose |
|---|---|
| `stage1_arelle.py` | Enriches mapped rows with taxonomy citations |
| `concept_citation.py` | Subject-matter vs presentation topic split, version families |
| `stage1_eval.py` | Citation coverage and accuracy vs the static-map baseline |
| `stage1_citation_eval.py` | Citation-only evaluation on broken rows |
| `constraint_registry.py` | Extracts the ASC ids appearing in AuditBench ground truth |
| `constraint_registry.json` | Cached output of the above |

## Run it

```bash
python -m approaches.stage1_taxonomy_citation.stage1_eval --n 150
python -m approaches.stage1_taxonomy_citation.stage1_citation_eval --n 150
python -m approaches.stage1_taxonomy_citation.constraint_registry
```

First run downloads the FASB taxonomy (~11 MB) to `.cache/`; later runs read from
disk. No API key required.
