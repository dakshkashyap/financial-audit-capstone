"""Deterministic post-run scoring against evaluator-owned reviewed annotations.

This module checks identities, acquisition, annotated proof structure and explicit
applicability predicates. It does not infer accounting truth or textual entailment.
See EVIDENCE_METRICS.md for the trust boundary and denominator definitions.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

VERSION = "evidence-metrics-v1"
DEFINITIVE = {"supported_misstatement", "supported_compliance"}
CONCLUSIONS = DEFINITIVE | {"insufficient_evidence", "suspicious"}
AUTHORITY_KINDS = {"canonical_standard", "regulator_rule", "amendment_transition",
                   "official_implementation_guidance"}


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _date(value: Any, name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO date") from error
    if result.isoformat() != value:
        raise ValueError(f"{name} must be YYYY-MM-DD")
    return result


def _ids(value: Any, name: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f"{name} must be a list of nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} contains duplicate IDs")
    return set(value)


def _index(records: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError(f"{key} records must be a list")
    result = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get(key), str) or not record[key]:
            raise ValueError(f"invalid {key}")
        if record[key] in result:
            raise ValueError(f"duplicate {key}")
        result[record[key]] = record
    return result


def _edges(records: Any) -> set[tuple[str, str, str]]:
    if not isinstance(records, list):
        raise ValueError("edges must be a list")
    result = set()
    for edge in records:
        if not isinstance(edge, dict):
            raise ValueError("edge must be an object")
        fields = tuple(edge.get(k) for k in ("from_fact_id", "to_fact_id", "relation"))
        if any(not isinstance(x, str) or not x for x in fields):
            raise ValueError("edge requires from_fact_id, to_fact_id and relation")
        if fields in result:
            raise ValueError("duplicate edge")
        result.add(fields)
    return result


def replay_acquisition(sources: list[dict[str, Any]], facts: list[dict[str, Any]],
                       trace: Sequence[Mapping[str, Any]], *, investigation_cutoff: str,
                       budget: int, document_costs: Mapping[str, int]) -> dict[str, Any]:
    """Validate a trusted runner's trace. Never use a model-supplied trace.

    Costs are integer acquisition units; cached/failed/denied requests cost zero.
    A malformed trace is recorded as invalid, not dropped from evaluation.
    Optional returned_fact_ids and spent fields are checked when supplied.
    """
    budget = _integer(budget, "budget")
    cutoff = _date(investigation_cutoff, "investigation_cutoff")
    documents = _index(sources, "document_id")
    fact_index = _index(facts, "fact_id")
    if set(document_costs) != set(documents):
        raise ValueError("document_costs must cover exactly the source document IDs")
    costs = {k: _integer(v, "document cost") for k, v in document_costs.items()}
    by_document: dict[str, set[str]] = {k: set() for k in documents}
    for fact_id, fact in fact_index.items():
        if fact.get("document_id") not in documents:
            raise ValueError("fact has unknown source document")
        by_document[fact["document_id"]].add(fact_id)
    available = set()
    for doc_id, document in documents.items():
        for key in ("initially_visible", "obtainable"):
            if not isinstance(document.get(key), bool):
                raise ValueError(f"source {key} must be boolean")
        # Unknown availability never establishes admissibility.
        when = document.get("available_at")
        if when is not None and _date(when, "source available_at") <= cutoff:
            available.add(doc_id)
    observed = {doc_id for doc_id in available if documents[doc_id]["initially_visible"]}
    errors: list[str] = []
    spent = 0
    if not isinstance(trace, (list, tuple)):
        errors.append("trace must be a list or tuple")
        trace = []
    for step, event in enumerate(trace, 1):
        try:
            if not isinstance(event, Mapping):
                raise ValueError("event must be an object")
            doc_id = event.get("document_id")
            if not isinstance(doc_id, str):
                raise ValueError("document_id must be a string")
            status = event.get("status")
            charge = _integer(event.get("charged_cost"), "charged_cost")
            expected = ("unknown_document" if doc_id not in documents else
                        "unavailable" if doc_id not in available else
                        "cached" if doc_id in observed else
                        "unavailable" if not documents[doc_id]["obtainable"] else
                        "budget_exceeded" if spent + costs[doc_id] > budget else "acquired")
            # An acquisition may fail before returning any data; failures are free
            # in this protocol. Real API billing belongs in its separate ledger.
            if status == "failed" and expected == "acquired":
                expected = "failed"
            expected_charge = costs[doc_id] if expected == "acquired" else 0
            if status != expected or charge != expected_charge:
                raise ValueError(f"expected {expected} with charge {expected_charge}")
            next_spent = spent + expected_charge
            if "spent" in event and _integer(event["spent"], "spent") != next_spent:
                raise ValueError("cumulative spent mismatch")
            returned = by_document.get(doc_id, set()) if status in {"acquired", "cached"} else set()
            if "returned_fact_ids" in event and _ids(event["returned_fact_ids"], "returned_fact_ids") != returned:
                raise ValueError("returned fact IDs mismatch")
            if status == "acquired":
                observed.add(doc_id)
            spent = next_spent
        except (ValueError, TypeError) as error:
            errors.append(f"step {step}: {error}")
    observed_facts = set().union(*(by_document[x] for x in observed)) if observed else set()
    return {"valid": not errors, "errors": errors, "spent": spent, "budget": budget,
            "observed_document_ids": sorted(observed), "observed_fact_ids": sorted(observed_facts)}


def authority_applicability(authority: Mapping[str, Any], scope: Mapping[str, Any], *,
                            observed_fact_ids: set[str], source_observed: bool) -> list[str]:
    """Return failed explicit predicates; an empty list means annotated support.

    Dates conservatively require the version to govern the entire reporting
    period. This function cannot decide adoption, exceptions or legal meaning.
    """
    problems = []
    if not source_observed:
        problems.append("authority_source_not_acquired")
    framework = "experimental" if scope.get("framework") == "experimental_only" else scope.get("framework")
    kinds = AUTHORITY_KINDS | ({"experimental_contract_rule"} if framework == "experimental" else set())
    if authority.get("source_kind") not in kinds:
        problems.append("source_is_not_governing_authority")
    if authority.get("applicability") != "supported" or authority.get("scope_decision") != "in_scope":
        problems.append("applicability_not_supported")
    if authority.get("framework") != framework:
        problems.append("framework_mismatch")
    if authority.get("assertion_family") not in {scope.get("assertion_family"), "cross_cutting"}:
        problems.append("assertion_family_mismatch")
    jurisdictions = set(scope.get("jurisdiction", []))
    if not jurisdictions or not jurisdictions <= set(authority.get("jurisdiction", [])):
        problems.append("jurisdiction_mismatch_or_unknown")
    if not scope.get("entity_type") or scope["entity_type"] not in authority.get("entity_scope", []):
        problems.append("entity_scope_mismatch_or_unknown")
    try:
        start = _date(scope.get("reporting_period_start"), "reporting_period_start")
        end = _date(scope.get("reporting_period_end"), "reporting_period_end")
        effective = _date(authority.get("effective_from"), "effective_from")
        expiry = authority.get("effective_to")
        if start > end or effective > start or (expiry is not None and _date(expiry, "effective_to") < end):
            problems.append("authority_not_effective_for_entire_period")
    except ValueError:
        problems.append("authority_or_period_date_unknown")
    requirements = _ids(authority.get("required_fact_ids", []), "authority required_fact_ids")
    # Annotated refutations must also have been inspected. Their resolution is
    # embodied in applicability=supported, not automatically inferred here.
    requirements |= _ids(authority.get("refutation_fact_ids", []), "authority refutation_fact_ids")
    if not requirements <= observed_fact_ids:
        problems.append("applicability_facts_not_acquired")
    return problems


def evaluate_case(annotation: Mapping[str, Any], prediction: Mapping[str, Any] | None,
                  runner_trace: Sequence[Mapping[str, Any]], *, budget: int,
                  document_costs: Mapping[str, int], authority_document_ids: Mapping[str, str],
                  claim_supports: Mapping[str, list[list[str]]] | None = None) -> dict[str, Any]:
    """Score a completed run; annotation and all keyword arguments are evaluator-owned.

    Prediction: status=ok|failure|missing, conclusion, cited_fact_ids,
    cited_authority_ids, edges, optional assertions [{claim_id,support_fact_ids}].
    ``claim_supports`` supplies annotated alternative support sets for assertion
    IDs. Free-form reasoning text is not semantically scored.
    """
    facts = _index(annotation.get("facts"), "fact_id")
    authorities = _index(annotation.get("authorities"), "authority_id")
    proofs = _index(annotation.get("proof_sets"), "proof_id")
    documents = _index(annotation.get("sources"), "document_id")
    if set(authority_document_ids) != set(authorities) or any(x not in documents for x in authority_document_ids.values()):
        raise ValueError("authority_document_ids must map every authority to a known document")
    scope, gold = annotation["scope"], annotation["gold"]
    accepted = _ids(gold.get("accepted_proof_ids"), "accepted_proof_ids")
    if not accepted <= set(proofs):
        raise ValueError("unknown accepted proof ID")
    proof_parts = {}
    for proof_id in accepted:
        proof = proofs[proof_id]
        required = _ids(proof.get("fact_ids"), "proof fact_ids") | _ids(proof.get("refutation_fact_ids", []), "refutation_fact_ids")
        required_authorities = _ids(proof.get("authority_ids"), "proof authority_ids")
        edges = _edges(proof.get("edges"))
        if not required <= set(facts) or not required_authorities <= set(authorities):
            raise ValueError("proof references unknown facts or authorities")
        if any(a not in required or b not in required for a, b, _ in edges):
            raise ValueError("proof edge endpoint outside proof facts")
        if proof.get("conclusion") != gold.get("conclusion"):
            raise ValueError("accepted proof conclusion differs from gold")
        if not required:
            raise ValueError("accepted proof must require at least one fact")
        proof_parts[proof_id] = (required, required_authorities, edges)
    citation_sets = [_ids(x, "acceptable citation set") for x in gold.get("acceptable_citation_sets", [])]
    if any(not x <= set(authorities) for x in citation_sets):
        raise ValueError("citation set references unknown authority")
    support_sets = {}
    for claim_id, alternatives in (claim_supports or {}).items():
        if not isinstance(claim_id, str) or not claim_id or not isinstance(alternatives, list) or not alternatives:
            raise ValueError("claim support requires ID and nonempty alternatives")
        support_sets[claim_id] = [_ids(x, "claim support set") for x in alternatives]
        if any(not x or not x <= set(facts) for x in support_sets[claim_id]):
            raise ValueError("claim support set must contain known facts")
    acquisition = replay_acquisition(annotation["sources"], annotation["facts"], runner_trace,
        investigation_cutoff=scope["investigation_cutoff"], budget=budget, document_costs=document_costs)
    observed = set(acquisition["observed_fact_ids"])
    observed_docs = set(acquisition["observed_document_ids"])
    authority_problems = {aid: authority_applicability(authority, scope,
        observed_fact_ids=observed, source_observed=authority_document_ids[aid] in observed_docs)
        for aid, authority in authorities.items()}
    applicable = {aid for aid, failures in authority_problems.items() if not failures}
    acquired_proofs = sorted(pid for pid, (required, aids, _) in proof_parts.items()
                             if required <= observed and aids <= applicable)
    eligible = (annotation.get("status") == "expert_reviewed" and annotation.get("release_status") == "eligible"
                and gold.get("conclusion") in CONCLUSIONS and gold.get("decision_sufficiency") in {"sufficient", "insufficient"})
    if gold.get("conclusion") in DEFINITIVE and (gold.get("decision_sufficiency") != "sufficient" or not accepted):
        eligible = False
    if gold.get("conclusion") == "insufficient_evidence" and gold.get("decision_sufficiency") != "insufficient":
        eligible = False
    if gold.get("authority_disposition") == "governing_paragraph" and not citation_sets:
        eligible = False
    valid = True
    errors = []
    cited_facts: set[str] = set()
    cited_authorities: set[str] = set()
    predicted_edges: set[tuple[str, str, str]] = set()
    unsupported_assertions = []
    conclusion = None
    status = "missing" if prediction is None else prediction.get("status") if isinstance(prediction, Mapping) else "invalid"
    if status == "ok":
        try:
            conclusion = prediction.get("conclusion")
            if not isinstance(conclusion, str) or conclusion not in CONCLUSIONS:
                raise ValueError("invalid conclusion")
            cited_facts = _ids(prediction.get("cited_fact_ids"), "cited_fact_ids")
            cited_authorities = _ids(prediction.get("cited_authority_ids"), "cited_authority_ids")
            predicted_edges = _edges(prediction.get("edges"))
            assertions = prediction.get("assertions", [])
            if not isinstance(assertions, list):
                raise ValueError("assertions must be a list")
            seen_claims = set()
            for assertion in assertions:
                if not isinstance(assertion, Mapping) or not isinstance(assertion.get("claim_id"), str):
                    raise ValueError("assertion requires claim_id")
                claim = assertion["claim_id"]
                if claim in seen_claims:
                    raise ValueError("duplicate assertion claim_id")
                seen_claims.add(claim)
                supports = _ids(assertion.get("support_fact_ids"), "assertion support_fact_ids")
                if not supports <= (cited_facts & observed) or not any(x <= supports for x in support_sets.get(claim, [])):
                    unsupported_assertions.append(claim)
        except (ValueError, TypeError) as error:
            errors.append(str(error))
            valid = False
    elif status not in {"failure", "missing"}:
        valid = False
        errors.append("invalid prediction status")
    completed = status == "ok" and valid
    unsupported_facts = cited_facts - observed
    unsupported_authorities = cited_authorities - applicable
    allowed_edges = set().union(*(x[2] for x in proof_parts.values())) if proof_parts else set()
    valid_edges = {edge for edge in predicted_edges & allowed_edges if set(edge[:2]) <= (cited_facts & observed)}
    invalid_edges = predicted_edges - valid_edges
    completed_proofs = sorted(pid for pid, (required, aids, edges) in proof_parts.items()
        if pid in acquired_proofs and required <= cited_facts and aids <= cited_authorities and edges <= valid_edges)
    clean = not (unsupported_facts or unsupported_authorities or unsupported_assertions or invalid_edges)
    usable = eligible and completed and acquisition["valid"]
    label_correct = bool(usable and conclusion == gold.get("conclusion"))
    abstained = bool(completed and conclusion == "insufficient_evidence")
    warranted_abstention = bool(usable and abstained and clean and
        (gold.get("conclusion") == "insufficient_evidence" or not acquired_proofs))
    governing = gold.get('authority_disposition') == 'governing_paragraph'
    citation_correct = bool(usable and clean and governing and any(cited_authorities == x for x in citation_sets))
    citation_abstention_correct = bool(usable and clean and not governing and not cited_authorities)
    supported_decision = bool(label_correct and clean and completed_proofs and
                              (citation_correct if governing else citation_abstention_correct))
    # Warranted abstention is an operational measure, never converted to correct
    # static diagnosis on a resolvable case where the agent simply acquired less.
    warranted_response = supported_decision or warranted_abstention
    proof_fact_recall = max((len(required & cited_facts & observed) / len(required)
                             for required, _, _ in proof_parts.values()), default=None)
    return {"version": VERSION, "case_id": annotation["case_id"], "gold_eligible": eligible,
        "best_acceptable_proof_fact_recall": proof_fact_recall,
        "prediction_status": status if valid else "invalid", "prediction_errors": errors,
        "completed": completed, "conclusion": conclusion, "label_correct": label_correct,
        "abstained": abstained, "warranted_abstention": warranted_abstention,
        "supported_decision": supported_decision, "warranted_response": warranted_response,
        "citation_set_correct": citation_correct, "citation_abstention_correct": citation_abstention_correct,
        "acquired_proof_ids": acquired_proofs,
        "completed_proof_ids": completed_proofs, "unsupported_fact_ids": sorted(unsupported_facts),
        "unsupported_authority_ids": sorted(unsupported_authorities),
        "unsupported_assertion_ids": sorted(unsupported_assertions),
        "invalid_edges": [list(x) for x in sorted(invalid_edges)],
        "authority_predicate_failures": authority_problems, "acquisition": acquisition}


def summarize(scores: Sequence[Mapping[str, Any]], *, expected_case_ids: Sequence[str],
              pairs: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Aggregate a frozen roster. Missing score rows are errors, not exclusions.

    Call evaluate_case(annotation, None, ...) for an unrequested/missing run.
    Only explicitly ineligible gold is excluded; all API and format failures on
    eligible cases remain in every accuracy denominator.
    """
    expected = _ids(list(expected_case_ids), "expected_case_ids")
    indexed = _index(list(scores), "case_id")
    if set(indexed) != expected:
        raise ValueError("scores must cover exactly the frozen roster, including missing predictions")
    eligible = [row for row in scores if row["gold_eligible"]]
    n = len(eligible)
    counts = {key: sum(bool(row[key]) for row in eligible) for key in
              ("completed", "label_correct", "abstained", "warranted_abstention", "supported_decision",
               "warranted_response", "citation_set_correct", "citation_abstention_correct")}
    for key in ("unsupported_fact_ids", "unsupported_authority_ids", "unsupported_assertion_ids", "invalid_edges"):
        counts[key + "_cases"] = sum(bool(row[key]) for row in eligible)
    counts["valid_acquisition"] = sum(row["acquisition"]["valid"] for row in eligible)
    counts["definitive_answers"] = sum(row["completed"] and row["conclusion"] in DEFINITIVE for row in eligible)
    statuses = {key: sum(row["prediction_status"] == key for row in eligible)
                for key in ("ok", "failure", "missing", "invalid")}
    pair_rows = []
    pair_index = _index(list(pairs), "pair_id")
    for pair_id, pair in pair_index.items():
        ids = _ids(pair.get("case_ids"), "pair case_ids")
        if len(ids) != 2 or not ids <= expected:
            raise ValueError("pair must contain two distinct roster cases")
        a, b = (indexed[k] for k in sorted(ids))
        pair_rows.append({"pair_id": pair_id, "eligible": a["gold_eligible"] and b["gold_eligible"],
            "both_correct": a["label_correct"] and b["label_correct"],
            "both_supported": a["supported_decision"] and b["supported_decision"],
            "label_changed": a["completed"] and b["completed"] and a["conclusion"] != b["conclusion"]})
    eligible_pairs = [row for row in pair_rows if row["eligible"]]
    definitive = [row for row in eligible if row["completed"] and row["conclusion"] in DEFINITIVE]
    total_cost = sum(row["acquisition"]["spent"] for row in eligible)
    proof_recalls = [row["best_acceptable_proof_fact_recall"] for row in eligible
                     if row["best_acceptable_proof_fact_recall"] is not None]
    return {"version": VERSION, "expected_cases": len(expected), "eligible_cases": n,
        "excluded_unresolved_cases": len(expected) - n, "counts": counts, "prediction_status_counts": statuses,
        "rates": {key: value / n if n else None for key, value in counts.items()},
        "pair_count": len(eligible_pairs), "pair_both_correct": sum(row["both_correct"] for row in eligible_pairs),
        "pair_both_supported": sum(row["both_supported"] for row in eligible_pairs),
        "pair_both_correct_rate": sum(row["both_correct"] for row in eligible_pairs) / len(eligible_pairs) if eligible_pairs else None,
        "mean_spent_acquisition_units": total_cost / n if n else None,
        "acquisition_units_per_supported_decision": total_cost / counts["supported_decision"] if counts["supported_decision"] else None,
        "mean_best_acceptable_proof_fact_recall": sum(proof_recalls) / len(proof_recalls) if proof_recalls else None,
        "proof_recall_denominator": len(proof_recalls),
        "selective_label_risk": 1 - sum(row["label_correct"] for row in definitive) / len(definitive) if definitive else None,
        "selective_supported_risk": 1 - sum(row["supported_decision"] for row in definitive) / len(definitive) if definitive else None,
        "pairs": pair_rows}
