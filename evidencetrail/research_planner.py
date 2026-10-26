"""Explainable next research actions for an OFFLINE simulated evidence dossier.

This is a deterministic action PLAN, not autonomous internet research,
operational disaster guidance, sponsor inference or verified archive evidence.
Every instruction remains subject to human verification and a new as-of check.
"""
from __future__ import annotations

from typing import Any

VALIDATION = {
    "MISSING_PUBLIC_CONTEXT": (
        "Retrieve a government bulletin for the requested historical jurisdiction.",
        "Verify official publisher, 2024 geography, original content and source-time eligibility."
    ),
    "MISSING_DISTRICT_NAMED_BULLETIN": (
        "Find a contemporaneous government bulletin that explicitly names the requested district.",
        "Confirm the district appears in the source body and its publication proof predates the decision."
    ),
    "MISSING_SCENARIO_BOUND_CAPACITY": (
        "Provide a coordinator capacity record scoped to this exact simulated scenario.",
        "Confirm its scenario ID and district, and clearly label all hypothetical figures FICTIONAL."
    ),
    "MISSING_SYNTHETIC_WATCH_AUTHORIZATION": (
        "Inspect the simulated coordinator plan for an explicit research-watch authorization.",
        "Require a true explicit authorization predicate; do not infer consent from free text."
    ),
    "HISTORICAL_AVAILABILITY_NOT_AUTHENTICATED": (
        "Seek original, timestamp-attested September 2024 publication bytes or contemporaneous archive capture.",
        "Compare authenticated capture/publication times with the as-of instant; a later Wayback copy or displayed dateline alone is insufficient."
    ),
    "MISSING_REAL_SITE_POPULATION": (
        "Request independently verified site-level capacity and population data before any real deployment.",
        "Record the verifying agency, measurement date, scope and human review; fictional counts never qualify."
    ),
    "MISSING_VERIFIED_ROUTE_SAFETY": (
        "Obtain independently checked present-time route safety from the responsible authority.",
        "Require a current authenticated route status; a historical research replay cannot establish safety."
    ),
}


def _action(code: str, request_action: str, blocks: bool) -> dict[str, Any]:
    suggested, test = VALIDATION.get(code, (
        request_action, "Require independently inspected primary evidence before changing the rule verdict."
    ))
    return {
        "code": code,
        "priority": "P0_RESEARCH_EVIDENCE" if blocks else "P1_OPERATIONAL_VERIFICATION",
        "action": suggested,
        "verification_criterion": test,
        "blocks_simulated_research_watch": bool(blocks),
        "human_approval_required": True,
        "perform_network_or_field_action_now": False,
    }


def plan_research_next_steps(
    current: dict, earlier: dict, other_policy: dict, newly: list[str],
) -> dict[str, Any]:
    """Summarize provenance and counterfactuals; do not invent new observations."""
    if not all(isinstance(r, dict) for r in (current, earlier, other_policy)):
        raise ValueError("RESEARCH_PLANNER_INPUT_INVALID")
    if not isinstance(newly, list) or not all(isinstance(s, str) for s in newly):
        raise ValueError("RESEARCH_PLANNER_SOURCE_IDS_INVALID")
    steps = []
    codes = set()
    for req in current.get("next_evidence_requirements", []):
        code = req["code"]
        if code in codes:
            continue
        codes.add(code)
        steps.append(_action(code, req["action"], req["blocks_research_watch"]))
    pivots = current.get("pivotal_source_ids", [])
    witness = current.get("minimum_sufficient_source_set", [])
    proven = {
        row["source_id"]: row.get("first_archive_proof_verified_in_default_catalog") is True
        for row in witness
    }
    for sid in pivots:
        is_synthetic = any(
            row["source_id"] == sid and row.get("synthetic_scenario") is True
            for row in witness
        )
        if is_synthetic:
            steps.append({
                "code": "RECHECK_PIVOTAL_FICTIONAL_CAPACITY",
                "priority": "P1_OPERATIONAL_VERIFICATION",
                "source_id": sid,
                "action": "Preserve FICTIONAL labeling and audit whether this capacity row is scenario-bound.",
                "verification_criterion": "A real operating plan requires separately verified capacity and human authorization; this simulated input is not one.",
                "blocks_simulated_research_watch": False,
                "human_approval_required": True,
                "perform_network_or_field_action_now": False,
            })
        elif not proven.get(sid, False):
            steps.append({
                "code": "VERIFY_PIVOTAL_PUBLICATION_PROVENANCE",
                "priority": "P0_RESEARCH_EVIDENCE",
                "source_id": sid,
                "action": "Verify original publisher bytes and their first demonstrated public-availability time.",
                "verification_criterion": "Authenticated source body plus availability at or before the chosen as-of; displayed dates and URL slugs are not proof.",
                "blocks_simulated_research_watch": False,
                "human_approval_required": True,
                "perform_network_or_field_action_now": False,
            })
    steps.sort(key=lambda item: (0 if item["priority"].startswith("P0") else 1,
                                 item["code"], item.get("source_id", "")))
    current_verdict = current["rule_verdict"]
    earlier_verdict = earlier["rule_verdict"]
    strict_contrast = other_policy["rule_verdict"]
    time_changed = current_verdict != earlier_verdict
    policy_changed = current_verdict != strict_contrast
    return {
        "kind": "OFFLINE_HUMAN_REVIEW_RESEARCH_PLAN_V1",
        "reasoning_engine": "DETERMINISTIC_RULE_AND_SOURCE_ABLATION",
        "current_rule_verdict": current_verdict,
        "simulated_rule_warning_only": current_verdict == "WARN",
        "time_comparison": {
            "verdict_before": earlier_verdict,
            "verdict_now": current_verdict,
            "changed": time_changed,
            "newly_eligible_source_ids": list(newly),
            "interpretation": (
                "Change is explained by newly admissible evidence, not the clock alone."
                if time_changed and newly
                else "No causal time-only effect is proven by this replay."
            ),
        },
        "policy_comparison": {
            "other_policy": other_policy["policy"],
            "other_verdict": strict_contrast,
            "differs": policy_changed,
            "interpretation": (
                "Different evidence admissibility standard; not proof of publication."
                if policy_changed else
                "The compared policies yielded the same rule verdict in this fixture."
            ),
        },
        "pivotal_source_ids": list(pivots),
        "next_evidence_steps": steps,
        "priority_one": steps[0]["code"] if steps else None,
        "requires_human_review": True,
        "new_evidence_collected": False,
        "model_or_vendor_called": False,
        "operational_emergency_action_authorized": False,
        "external_field_accuracy_demonstrated": False,
        "notice": (
            "Only research verification actions are proposed. Every source must be "
            "re-evaluated against the selected as-of policy; this plan cannot turn "
            "FICTIONAL capacity or retrospective data into real disaster advice."
        ),
    }
