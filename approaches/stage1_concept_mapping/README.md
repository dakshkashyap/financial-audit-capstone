# Stage 1 — Concept mapping (EDGAR Mapper)

**Turn a human-written statement label into its official XBRL concept.**

A filing says `"Property and equipment, net"`. The accounting rulebook is indexed
by machine-readable concepts like `us-gaap:PropertyPlantAndEquipmentNet`. Nothing
downstream — no citation lookup, no rule check — can happen until that bridge is
crossed.

## Why it exists

This is the bottleneck nobody in the literature has solved. FinAuditing's FinSM
task measures exactly this and the best LLMs score 9–13%, because they are being
asked to pick one concept out of an 18,000-concept space from a short text label.

Three routes are implemented here, in increasing order of authority:

1. **Static map** — normalized label matched against a curated
   `xbrl_concept_map.json`, with exact, fuzzy and word-stem fallbacks.
2. **Mapper v2** — adds period parsing, statement-type inference and better
   normalization.
3. **Live SEC EDGAR** — the interesting one. Every AuditBench company already
   filed XBRL with the SEC, where each line item was tagged by *the filer's own
   accountants*. Recovering that filing collapses an 18,000-concept guess into a
   lookup over the 300–600 concepts the company actually uses.

Route 3 is off by default (`use_edgar_xbrl=False`) so the offline deterministic
evaluations stay reproducible without network access.

## Files

| File | Purpose |
|---|---|
| `edgar_mapper.py` | The mapper: exact → fuzzy → stem, optional live-EDGAR route |
| `edgar_mapper_v2.py` | Second iteration with period and statement-type handling |
| `edgar_mapper_eval.py` | Coverage and accuracy evaluation over AuditBench |
| `edgar_xbrl.py` | Live SEC EDGAR concept resolver (the filer-tagged route) |
| `edgar_api.py` | Standalone SEC EDGAR XBRL client, no API key needed |
| `xbrl_concept_map.json` | Curated label → concept map |
| `company_tickers.json` | Company name → ticker, for CIK resolution |

## Run it

```bash
python -m approaches.stage1_concept_mapping.edgar_mapper_eval

# standalone EDGAR client demo — pulls real Apple facts from the SEC
python -m approaches.stage1_concept_mapping.edgar_api
```

See [EDGAR_XBRL_CLIENT.md](EDGAR_XBRL_CLIENT.md) for the client, and
[docs/architecture/EDGAR_MAPPER.md](../../docs/architecture/EDGAR_MAPPER.md) plus
[EDGAR_MAPPER_V2.md](../../docs/architecture/EDGAR_MAPPER_V2.md) for the full
design write-ups.

## Honest limitation

The static map is a first-pass solution: it only covers labels somebody thought to
add, so it degrades on companies and wordings outside the curated set. The live
EDGAR route is the principled fix and is why `edgar_xbrl.py` exists, but it needs
network access and reliable company-name resolution, so it is not yet the default
in the scored runs.
