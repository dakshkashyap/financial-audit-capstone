# Apple pack — Stage 0 / 1 / 2 (Cursor as Stage-2 LLM)

Data: [`data/apple_pack/apple_all.json`](../../data/apple_pack/apple_all.json)  
Machine results: `results/apple_pack_run/`

## What’s in the JSON pack

| Section | Count | Meaning |
|---|---|---|
| `raw_table_data` | 3 | Public Apple BS / IS / CF text |
| `correct` | 8 | Clean table + synthetic transactions |
| `single_error` | 20 | Injected errors + labels |
| `multi_error` | 6 | Two injected errors each |

---

## Stage 0 (deterministic gate)

| Metric | Result |
|---|---|
| False alarms on clean Apple (n=8) | **0 / 8** |
| Fire rate on single_error (n=20) | **40%** (8 fired, 12 abstain) |
| Type exact match when fired | **8 / 8 (100%)** |
| Row exact match when fired | **7 / 8 (87.5%)** |

Stage 0 works on Apple: silent when clean, accurate when it speaks.

---

## Stage 1 (map + taxonomy graph)

| Metric | Result |
|---|---|
| Concept mapping coverage (clean) | **~89–93%** of valued rows |
| Focus rows with ≥1 ASC candidate | **8 / 20** |
| Invented ASC `999-99-99-9` accepted | **0** (rejected whenever candidates exist) |

Taxonomy graph **is working**: every returned ASC comes from the FASB linkbase; fakes are rejected.

Citation *topic* vs AuditBench GT is still weak when the GT topic isn’t in the candidate list (same ceiling as before).

---

## Stage 2 — Cursor acting as the LLM (no API key)

Rule followed: **only pick from Stage-1 candidates**; never invent.

| Item | Route | GT topic | In candidates? | Cursor pick | Match GT? |
|---|---|---|---|---|---|
| 1 | ABSTAIN | 210 | **yes** (`210-10-45-1`) | `210-10-45-1` | **yes** (beats bad heuristic `323-…`) |
| 7 | FIRE | 310 | yes | `310-10-45-2` | **yes** |
| 0 | FIRE | 210 | **no** (only 310) | `310-10-45-2` | no — correctly tool-locked |
| 11 | ABSTAIN | 250 | **no** | `360-10-50-1` | no — GT absent |
| 16 | ABSTAIN | 205 | **no** | `280-10-50-22` | no — GT absent |

**Takeaway:** When the right topic is in the graph candidates, Cursor-as-Stage-2 can select it (and even beat the heuristic). When it isn’t, staying honest means missing GT — that proves the graph/tool-lock works, not that Stage 2 is free to hallucinate.

Full decisions: `results/apple_pack_run/stage2_cursor_llm.json`  
Evidence packets: `results/apple_pack_run/stage2_evidence_packets.json`

---

## Re-run Stage 0 / 1

```bash
export AUDITBENCH_DATA="$(pwd)/data/apple_pack"
export AUDIT_RESULTS_DIR="$(pwd)/results/apple_pack_run"
python -m approaches.stage0_deterministic_gate.stage0_eval --n 20
python -m approaches.stage1_concept_mapping.edgar_mapper_eval --n 20
python -m approaches.stage1_taxonomy_citation.stage1_citation_eval --n 20
```
