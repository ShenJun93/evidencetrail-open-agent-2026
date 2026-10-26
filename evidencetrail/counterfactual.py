"""Deterministic counterfactual evidence lab, not an operational hazard model.

A separate, strictly offline research analysis on the SAME firewall and rule
reducer as EvidenceTrail, with no Zetaris, H-MEM, Nightshift or NVIDIA calls.

Withheld-one-source ablations and the minimum sufficient source subset are
rule-level sensitivity certificates, NEVER empirical proof that a disaster
was caused by a news article or that a 2024 WARN truly occurred.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from itertools import combinations

from evidencetrail.firewall import filter_sources, jurisdiction_ok
from evidencetrail.evidence_integrity import initial_source_integrity_issues, matching_scenario_capacities
from evidencetrail.models import (
    RecordKind, ReplayMode, RunRequest, SourceRecord, Verdict, iso,
)
from evidencetrail.reducer import decide
from evidencetrail.research_planner import plan_research_next_steps

MAX_COUNTERFACTUAL_SOURCES = 12


def _admissible(
    request: RunRequest,
    catalog: list[SourceRecord],
) -> tuple[list[SourceRecord], list[dict]]:
    # Mirror the Collector's FULL initial trust boundary before either
    # time or geography filtering; source aliases and overlapping plans
    # cannot become admissible merely by hiding a conflicting twin.
    issues = initial_source_integrity_issues(catalog, request)
    if issues:
        raise ValueError(issues[0]["code"])
    in_scope = [
        row for row in catalog
        if jurisdiction_ok(row, request.province_2024, request.district_2024)
    ]
    eligible, excluded = filter_sources(in_scope, request.as_of_utc, request.mode)
    eligible = sorted(eligible, key=lambda row: row.source_id)
    if len(eligible) > MAX_COUNTERFACTUAL_SOURCES:
        raise ValueError("COUNTERFACTUAL_SOURCE_LIMIT_EXCEEDED")
    if len({s.source_id for s in eligible}) != len(eligible):
        raise ValueError("DUPLICATE_SOURCE_ID_REFUSED")
    return eligible, excluded


def _minimum_sufficient(
    request: RunRequest,
    eligible: list[SourceRecord],
    verdict: Verdict,
) -> list[SourceRecord]:
    if verdict != Verdict.WARN:
        return []
    # Bounded exact combinatorial search, ordered by cardinality and stable
    # source ID; never label a greedy subset globally minimal.
    for count in range(1, len(eligible) + 1):
        for group in combinations(eligible, count):
            if decide(request, list(group))[0] == verdict:
                return list(group)
    raise ValueError("NO_SUFFICIENT_WITNESS_FOR_NOMINATED_WARNING")


def _source_proof(row: SourceRecord) -> dict:
    return {
        "source_id": row.source_id,
        "kind": row.record_kind.value,
        "excerpt_sha256": row.excerpt_sha256,
        "synthetic_scenario": row.record_kind == RecordKind.SYNTHETIC_CAPACITY,
        "first_archive_proof_verified_in_default_catalog": (
            row.first_availability_proven_utc is not None
            and row.record_kind == RecordKind.GOVERNMENT_NEWS
        ),
    }


def _requirements(request: RunRequest, eligible: list[SourceRecord]) -> list[dict]:
    public = [r for r in eligible if r.record_kind == RecordKind.GOVERNMENT_NEWS]
    district_named = any(
        request.district_2024 and request.district_2024.casefold()
        in {d.casefold() for d in r.named_districts_2024}
        for r in public
    )
    cap = matching_scenario_capacities(request, eligible)
    requirements = []
    if not public:
        requirements.append({
            "code": "MISSING_PUBLIC_CONTEXT",
            "action": "Find a date-admissible public disaster bulletin for the 2024 jurisdiction.",
            "blocks_research_watch": True,
        })
    if request.granularity == "district" and not district_named:
        requirements.append({
            "code": "MISSING_DISTRICT_NAMED_BULLETIN",
            "action": (
                "Find a source naming the requested 2024 district, demonstrably "
                "available under the selected as-of evidence policy."
            ),
            "blocks_research_watch": True,
        })
    if not cap:
        requirements.append({
            "code": "MISSING_SCENARIO_BOUND_CAPACITY",
            "action": (
                "Supply a scenario-bound coordinator plan. A fictional plan is "
                "only allowed for a visibly SIMULATED watch, never real dispatch."
            ),
            "blocks_research_watch": True,
        })
    elif not any(c.plan_predicates.get("coordinator_watch_authorized") for c in cap):
        requirements.append({
            "code": "MISSING_SYNTHETIC_WATCH_AUTHORIZATION",
            "action": "Verify explicit watch authorization within the stated simulation.",
            "blocks_research_watch": True,
        })
    if request.mode == ReplayMode.STRICT_AS_OF_2024 and not public:
        requirements.append({
            "code": "HISTORICAL_AVAILABILITY_NOT_AUTHENTICATED",
            "action": (
                "Check an actual September 2024 archive body and its capture time "
                "before the as-of instant; curated displayed datelines are insufficient."
            ),
            "blocks_research_watch": True,
        })
    # These requirements remain open EVEN when a simulated watch passes.
    if not cap or not all(r.plan_predicates.get("site_population_verified") for r in cap):
        requirements.append({
            "code": "MISSING_REAL_SITE_POPULATION",
            "action": "Confirm real site-level people/capacity figures; never infer from synthetic rows.",
            "blocks_research_watch": False,
        })
    if not cap or not all(r.plan_predicates.get("route_safety_verified") for r in cap):
        requirements.append({
            "code": "MISSING_VERIFIED_ROUTE_SAFETY",
            "action": "Obtain current, independently checked route safety before any real action.",
            "blocks_research_watch": False,
        })
    return requirements


def _evaluate(request: RunRequest, catalog: list[SourceRecord], *, full: bool) -> dict:
    eligible, excluded = _admissible(request, catalog)
    verdict, rationale, missing, used = decide(request, eligible)
    result = {
        "as_of_utc": iso(request.as_of_utc),
        "policy": request.mode.value,
        "rule_verdict": verdict.value,
        "rule_is_simulated_research": True,
        "eligible_source_ids": [r.source_id for r in eligible],
        "excluded": [
            {"source_id": row["source_id"], "reason": row["reason"]}
            for row in excluded
        ],
        "missing_facts": missing,
        "next_evidence_requirements": _requirements(request, eligible),
    }
    if not full:
        return result
    witness = _minimum_sufficient(request, eligible, verdict)
    removal = []
    for row in eligible:
        without = [r for r in eligible if r.source_id != row.source_id]
        other, _, _, _ = decide(request, without)
        removal.append({
            "source_id": row.source_id,
            "kind": row.record_kind.value,
            "synthetic_scenario": row.record_kind == RecordKind.SYNTHETIC_CAPACITY,
            "without_source_rule_verdict": other.value,
            "changes_rule_verdict": other != verdict,
        })
    result["source_removal_tests"] = removal
    result["pivotal_source_ids"] = [
        r["source_id"] for r in removal if r["changes_rule_verdict"]
    ]
    result["minimum_sufficient_source_set"] = [_source_proof(r) for r in witness]
    result["minimum_set_cardinality"] = len(witness) if verdict == Verdict.WARN else None
    result["minimum_set_proven"] = verdict == Verdict.WARN
    result["source_ablation_scope"] = (
        "REMOVE_ONE_SOURCE_FROM_THE_ALREADY_ADMISSIBLE_SET; "
        "rule sensitivity only, not proof of environmental causation"
    )
    return result


def counterfactual_dossier(
    request: RunRequest,
    catalog: list[SourceRecord],
    *,
    minutes_earlier: int = 15,
) -> dict:
    """Compute counterfactuals from trusted offline catalog, never network."""
    if request.sample_mode is not True:
        raise ValueError("COUNTERFACTUAL_OFFLINE_SAMPLE_ONLY")
    if type(minutes_earlier) is not int or not 1 <= minutes_earlier <= 180:
        raise ValueError("COUNTERFACTUAL_EARLIER_MINUTES_INVALID")
    if len(catalog) > 100:
        raise ValueError("COUNTERFACTUAL_CATALOG_LIMIT_EXCEEDED")

    now = _evaluate(request, catalog, full=True)
    before_request = replace(
        request, as_of_utc=request.as_of_utc - timedelta(minutes=minutes_earlier)
    )
    before = _evaluate(before_request, catalog, full=False)
    other_mode = (
        ReplayMode.STRICT_AS_OF_2024
        if request.mode == ReplayMode.REPORTED_DATELINE_REPLAY
        else ReplayMode.REPORTED_DATELINE_REPLAY
    )
    alternate = _evaluate(replace(request, mode=other_mode), catalog, full=False)
    admitted_before = set(before["eligible_source_ids"])
    newly_eligible = [
        sid for sid in now["eligible_source_ids"] if sid not in admitted_before
    ]
    # Derive next verification steps solely from already-computed admissible
    # sources, requirements and ablations. No new records or vendor inference.
    now["research_action_plan"] = plan_research_next_steps(
        now, before, alternate, newly_eligible
    )
    return {
        "kind": "OFFLINE_DETERMINISTIC_COUNTERFACTUAL_DOSSIER_V1",
        "offline_sample_only": True,
        "mission_id": request.mission_id,
        "scenario_id": request.scenario_id,
        "requested_granularity": request.granularity,
        "current": now,
        "earlier_same_policy": before,
        "earlier_by_minutes": minutes_earlier,
        "newly_eligible_source_ids": newly_eligible,
        "time_changed_rule_verdict": (
            before["rule_verdict"] != now["rule_verdict"]
        ),
        "same_clock_other_policy": alternate,
        "policy_changed_rule_verdict": (
            alternate["rule_verdict"] != now["rule_verdict"]
        ),
        "actual_agent_result_reused": False,
        "simulation_not_historical_warning": True,
        "real_time_emergency_use": False,
        "historical_source_first_publication_authenticated": False,
        "official_meterless_nightshift_called": False,
        "real_zetaris_query_performed": False,
        "first_party_hmem_called": False,
        "notice": (
            "Pure replay of the production source firewall and deterministic "
            "rule reducer on the bundled sample catalog. Minimal evidence "
            "and leave-one-source-out tests explain decision sensitivity; "
            "not proof of external causation, historical source publication "
            "or real operational safety."
        ),
    }
