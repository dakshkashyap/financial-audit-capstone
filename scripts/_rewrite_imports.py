"""One-shot import rewriter for the repo restructure.

Maps old flat module names to their new package paths and rewrites every
`import X` / `from X import ...` / `from X.Y import ...` statement in place.
Kept in the repo only as a record of how the restructure was performed.
"""

import pathlib
import re

MAP = {
    # core (shared by 2+ approaches)
    "parser": "core.parser",
    "metrics": "core.metrics",
    "model_backends": "core.model_backends",
    "auditor_prompt": "core.auditor_prompt",
    "taxonomy_graph": "core.taxonomy_graph",
    "stage0_common": "core.stage0_common",
    "finmr_parser": "core.finmr_parser",
    "finmr_verifier": "core.finmr_verifier",
    "verify_data": "core.verify_data",
    # baseline
    "runner": "approaches.baseline_auditbench.runner",
    "evaluate": "approaches.baseline_auditbench.evaluate",
    # stage 0
    "stage0a": "approaches.stage0_deterministic_gate.stage0a",
    "stage0b": "approaches.stage0_deterministic_gate.stage0b",
    "stage0_eval": "approaches.stage0_deterministic_gate.stage0_eval",
    # stage 1 — concept mapping
    "edgar_mapper": "approaches.stage1_concept_mapping.edgar_mapper",
    "edgar_mapper_v2": "approaches.stage1_concept_mapping.edgar_mapper_v2",
    "edgar_mapper_eval": "approaches.stage1_concept_mapping.edgar_mapper_eval",
    "edgar_xbrl": "approaches.stage1_concept_mapping.edgar_xbrl",
    "edgar_api": "approaches.stage1_concept_mapping.edgar_api",
    # stage 1 — taxonomy citation
    "stage1_arelle": "approaches.stage1_taxonomy_citation.stage1_arelle",
    "stage1_eval": "approaches.stage1_taxonomy_citation.stage1_eval",
    "stage1_citation_eval": "approaches.stage1_taxonomy_citation.stage1_citation_eval",
    "concept_citation": "approaches.stage1_taxonomy_citation.concept_citation",
    "constraint_registry": "approaches.stage1_taxonomy_citation.constraint_registry",
    # stage 2
    "stage2_llm": "approaches.stage2_llm_audit.stage2_llm",
    "enhanced_auditor_prompt": "approaches.stage2_llm_audit.enhanced_auditor_prompt",
    "enhance_predictions": "approaches.stage2_llm_audit.enhance_predictions",
    # citation MCP agent
    "citation_mcp": "approaches.citation_mcp_agent",
    "taxonomy_mcp_server": "approaches.citation_mcp_agent.taxonomy_mcp_server",
    # audit patch
    "audit_patch": "approaches.audit_patch_repair",
    # FinMR benchmark
    "finmr_eval": "approaches.finmr_benchmark.finmr_eval",
    "finmr_auditbench_format": "approaches.finmr_benchmark.finmr_auditbench_format",
    "finmr_taxonomy_citations": "approaches.finmr_benchmark.finmr_taxonomy_citations",
    "finmr_loader": "approaches.finmr_benchmark.finmr_loader",
    "download_finmr": "approaches.finmr_benchmark.download_finmr",
    "eval_finmr": "approaches.finmr_benchmark.eval_finmr",
    # full pipeline
    "run_audit": "approaches.full_pipeline.run_audit",
    "pipeline": "approaches.full_pipeline.pipeline",
    "pipeline_eval": "approaches.full_pipeline.pipeline_eval",
    "run_intelliaudit": "approaches.full_pipeline.run_intelliaudit",
}

ROOTS = ["core", "approaches"]


def rewrite(text: str) -> tuple[str, int]:
    n = 0
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]

        # `from X import ...` / `from X.Y import ...`  (skip relative imports)
        m = re.match(r"from\s+([A-Za-z_][\w.]*)\s+import\s", stripped)
        if m:
            mod = m.group(1)
            head = mod.split(".")[0]
            if head in MAP:
                new_head = MAP[head]
                new_mod = new_head + mod[len(head):]
                line = indent + stripped.replace(f"from {mod} import", f"from {new_mod} import", 1)
                n += 1
            out.append(line)
            continue

        # bare `import X` -> `from <parent> import X` so the local name survives
        m = re.match(r"import\s+([A-Za-z_]\w*)\s*$", stripped.rstrip())
        if m:
            mod = m.group(1)
            if mod in MAP:
                new = MAP[mod]
                parent, _, leaf = new.rpartition(".")
                line = f"{indent}from {parent} import {leaf}\n"
                n += 1
            out.append(line)
            continue

        out.append(line)
    return "".join(out), n


def main():
    total_files = 0
    total_edits = 0
    for root in ROOTS:
        for path in sorted(pathlib.Path(root).rglob("*.py")):
            original = path.read_text()
            new, n = rewrite(original)
            if n:
                path.write_text(new)
                total_files += 1
                total_edits += n
                print(f"{path}: {n} import(s) rewritten")
    print(f"\n{total_edits} imports rewritten across {total_files} files")


if __name__ == "__main__":
    main()
