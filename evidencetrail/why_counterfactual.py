"""Source-withdrawal and timeline counterfactual explanations over a validated ledger.

Counterfactuals are *simulations*, not publisher events, model inference,
human evaluation, or new authentication of original first-web availability.
Inputs must pass the original FULL source/pin integrity gate before any
intervention is analyzed. No vendor/network calls, no inference, no mutations.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from itertools import combinations
from typing import Mapping

from evidencetrail.claim_ledger import (
    ClaimLedgerRefusal, ClaimRule, SourcePin, _validate_pins,
    evaluate_claim_ledger,
)
from evidencetrail.models import ReplayMode, SourceRecord, iso, parse_iso


def _claim_view(result: dict) -> dict[str, dict]:
    return {
        c["claim_key"]: {
            "source_id": c["source_id"],
            "value": c["value"],
            "unit": c["unit"],
            "issuer_family": c["issuer_family"],
            "clock_basis": c["clock_basis"],
            "fictional": c["fictional"],
            "original_first_publication_authenticated": False,
        }
        for c in result["typed_claims"]
    }


def _changes(before: dict[str, dict], after: dict[str, dict]) -> list[dict]:
    output = []
    for key in sorted(set(before) | set(after)):
        was, now = before.get(key), after.get(key)
        if was == now:
            continue
        if was is None:
            relation = "CLAIM_APPEARS"
        elif now is None:
            relation = "CLAIM_ABSTAINS"
        elif was["value"] != now["value"]:
            relation = "VALUE_CHANGED"
        elif was["source_id"] != now["source_id"]:
            relation = "SOURCE_ATTRIBUTION_CHANGED_SAME_VALUE"
        else:
            relation = "OTHER_METADATA_CHANGED"
        output.append({
            "claim_key": key,
            "effect": relation,
            "before": was,
            "after": now,
        })
    return output


def _evaluate(rows: list[SourceRecord], pins: Mapping[str, SourcePin],
              rules: list[ClaimRule], clock: str, mode: ReplayMode) -> dict:
    if not rows:
        # Only used for an explicit remove-last-source counterfactual; never
        # treat empty real input as an authenticated positive assertion.
        return {"typed_claims": [], "status": "ABSTAIN_NO_SOURCES"}
    return evaluate_claim_ledger(rows, pins, rules, as_of_utc=clock, mode=mode)


def _value_signature(claim: dict | None) -> tuple | None:
    """Numeric/availability sensitivity is different from citation changes."""
    return ((claim["value"], claim["unit"])
            if claim is not None else None)


def explain_source_sets(
    rows: list[SourceRecord], pins: Mapping[str, SourcePin], rules: list[ClaimRule],
    *, as_of_utc: str, mode: ReplayMode = ReplayMode.REPORTED_DATELINE_REPLAY,
    search_depth: int = 2,
) -> dict:
    """Find inclusion-minimal withdrawals within an explicit bounded search.

    This is conditional computational sensitivity, not causal influence,
    issuer independence, a probability or verification of a source's truth.
    All original records pass the ledger gate before any subset is evaluated.
    """
    if type(search_depth) is not int or not 1 <= search_depth <= 3:
        raise ClaimLedgerRefusal("WITHDRAWAL_SEARCH_DEPTH_INVALID")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
        raise ClaimLedgerRefusal("WITHDRAWAL_SOURCE_LIMIT_12")
    original = evaluate_claim_ledger(rows, pins, rules, as_of_utc=as_of_utc, mode=mode)
    baseline = _claim_view(original)
    candidates = sorted(original["source_ids_eligible"])
    searched_depth = min(search_depth, len(candidates))
    found: dict[str, list[dict]] = {rule.key: [] for rule in rules}
    evaluated = 0
    for size in range(1, searched_depth + 1):
        for ids in combinations(candidates, size):
            removed = set(ids)
            alternate = _claim_view(_evaluate(
                [row for row in rows if row.source_id not in removed],
                {sid: pin for sid, pin in pins.items() if sid not in removed},
                rules, original["as_of_utc"], mode))
            evaluated += 1
            for rule in rules:
                before, after = baseline.get(rule.key), alternate.get(rule.key)
                if _value_signature(before) == _value_signature(after):
                    continue
                if any(set(item["removed_source_ids"]).issubset(removed)
                       for item in found[rule.key]):
                    continue
                found[rule.key].append({
                    "removed_source_ids": list(ids), "before": before, "after": after,
                    "effect": ("CLAIM_APPEARS" if before is None else
                               "CLAIM_ABSTAINS" if after is None else "VALUE_CHANGED"),
                })
    return {
        "kind": "BOUNDED_MINIMAL_SOURCE_WITHDRAWALS_V1",
        "searched_max_withdrawal_size": searched_depth,
        "requested_search_depth": search_depth,
        "withdrawal_candidate_source_ids": candidates,
        "scope": "POLICY_ADMISSIBLE_SOURCES_AT_THE_SAME_AS_OF",
        "subsets_evaluated": evaluated,
        "all_source_subsets_examined": searched_depth == len(candidates),
        "inclusion_minimal_sets_complete_up_to_searched_depth": True,
        "resilience_is_statistical_confidence": False,
        "source_withdrawal_is_real_world_causation": False,
        "claims": {
            rule.key: {
                "baseline_claim": baseline.get(rule.key),
                "interpretation": ("VALUE_OR_AVAILABILITY_SENSITIVITY" if rule.key in baseline
                                   else "RESOLUTION_PROBE_NOT_FACT_VALIDATION"),
                "minimum_withdrawals_to_change_value_or_availability": (
                    len(found[rule.key][0]["removed_source_ids"]) if found[rule.key] else None),
                "proven_minimum_lower_bound": (
                    len(found[rule.key][0]["removed_source_ids"]) if found[rule.key] else
                    searched_depth + 1 if searched_depth < len(candidates) else None),
                "minimal_withdrawal_sets": found[rule.key],
            } for rule in rules
        },
    }


def explain_why(
    rows: list[SourceRecord],
    pins: Mapping[str, SourcePin],
    rules: list[ClaimRule],
    *, as_of_utc: str,
    mode: ReplayMode = ReplayMode.REPORTED_DATELINE_REPLAY,
    max_counterfactual_sources: int = 80,
) -> dict:
    """Explain why each selected claim was picked and what could change it.

    Source removal leaves every other source intact; timeline shifts adjust
    only the study as-of clock. Neither scenario forges a publisher clock.
    """
    if (type(max_counterfactual_sources) is not int or
            not 1 <= max_counterfactual_sources <= 80):
        raise ClaimLedgerRefusal("WHY_SIMULATION_LIMIT_INVALID")
    # Validates even FUTURE sources before any removal, and refuses missing
    # records or unpinned duplicate/forged sources in original input.
    original = evaluate_claim_ledger(
        rows, pins, rules, as_of_utc=as_of_utc, mode=mode
    )
    if len(rows) > max_counterfactual_sources:
        raise ClaimLedgerRefusal("WHY_TOO_MANY_SOURCE_INTERVENTIONS")
    prepared = _validate_pins(rows, pins, rules)
    at = parse_iso(original["as_of_utc"])
    assert at is not None
    baseline = _claim_view(original)
    source_tests = []
    for victim in sorted(rows, key=lambda r:r.source_id):
        removed_id = victim.source_id
        subrows = [r for r in rows if r.source_id != removed_id]
        subpins = {sid: pin for sid,pin in pins.items() if sid != removed_id}
        alternate = _evaluate(subrows, subpins, rules, original["as_of_utc"], mode)
        effects = _changes(baseline, _claim_view(alternate))
        was_eligible = removed_id in original["source_ids_eligible"]
        source_tests.append({
            "simulated_action": "REMOVE_ONE_SOURCE_NOT_AN_ACTUAL_EVENT",
            "removed_source_id": removed_id,
            "source_was_admissible_before_removal": was_eligible,
            "changed_claims": effects,
            "outcome": (
                "COUNTERFACTUAL_CLAIM_CHANGES" if effects
                else "NO_CHANGE_TO_SELECTED_CLAIMS"
            ),
            "genuine_publisher_action_or_retraction_observed": False,
        })
    time_tests = []
    if mode == ReplayMode.REPORTED_DATELINE_REPLAY:
        boundary_by_clock: dict[datetime, list[str]] = {}
        for source_id, (_, gate, _) in prepared.items():
            boundary_by_clock.setdefault(gate, []).append(source_id)
        for gate in sorted(boundary_by_clock):
            # At a boundary, compare the instant strictly before the gate to
            # the first admissible instant. Prevent past-anchored 0001 underflow.
            if gate <= datetime.min.replace(tzinfo=timezone.utc):
                raise ClaimLedgerRefusal("WHY_CLOCK_BOUNDARY_UNDERFLOW")
            preceding = iso(gate - timedelta(microseconds=1))
            arrived = iso(gate)
            before = _claim_view(_evaluate(rows,pins,rules,preceding,mode))
            after = _claim_view(_evaluate(rows,pins,rules,arrived,mode))
            time_tests.append({
                "simulated_action": "MOVE_AS_OF_TO_POLICY_BOUNDARY",
                "before_as_of_utc": preceding,
                "at_boundary_utc": arrived,
                "crossed_source_ids": sorted(boundary_by_clock[gate]),
                "changed_claims": _changes(before, after),
                "clock_is_policy_or_claimed_issuer_time_not_verified_first_publication": True,
            })
    rule_explanations = []
    evidence_needed = []
    conflicts = {item["claim_key"]: item
                 for item in original["unresolved_claim_conflicts"]}
    for rule in rules:
        value = baseline.get(rule.key)
        # Removing a conflicting contender can make an abstained claim appear.
        # Report that pivot as well as changes to already-selected claims.
        pivots = [
            entry["removed_source_id"] for entry in source_tests
            if any(x["claim_key"]==rule.key for x in entry["changed_claims"])
        ]
        if value is None:
            source_ids = sorted(sid for sid, (candidate, _, _) in prepared.items()
                                if candidate.key == rule.key)
            if rule.key in conflicts:
                status = "ABSTAIN_CONFLICTING_LATEST_SOURCES"
                code = "RESOLVE_CONFLICTING_LATEST_SOURCES"
                source_ids = conflicts[rule.key]["source_ids"]
                action = (
                    "Obtain an issuer correction or independently establish the "
                    "revision order of the conflicting sources. Removing a source "
                    "here only simulates resolution; it does not establish truth."
                )
            elif mode == ReplayMode.STRICT_AS_OF_2024:
                status = "ABSTAIN_NO_ADMISSIBLE_SOURCE_FOR_RULE"
                code = "ORIGINAL_AVAILABILITY_ATTESTATION_REQUIRED"
                action = (
                    "Obtain externally authenticated publisher bytes and an "
                    "availability bound at or before the requested as-of. "
                    "This ledger does not yet admit external attestations; "
                    "waiting or switching clocks cannot satisfy Strict policy."
                )
            else:
                status = "ABSTAIN_NO_ADMISSIBLE_SOURCE_FOR_RULE"
                code = "NO_SOURCE_ADMISSIBLE_AT_AS_OF"
                action = (
                    "Find a source for this claim with a defensible clock at "
                    "or before the requested as-of. A later reported-date replay "
                    "answers a different question and does not backdate evidence."
                )
            evidence_needed.append({
                "claim_key": rule.key, "reason_code": code,
                "source_ids": source_ids, "next_action": action,
            })
            rule_explanations.append({
                "claim_key": rule.key,
                "status": status,
                "selected_claim": None,
                "source_removal_pivots": pivots,
                "pivots_are_simulated_not_real_retractions": True,
            })
            continue
        rule_explanations.append({
            "claim_key": rule.key, "status": "PINNED_CLAIM_SELECTED",
            "selected_claim": value,
            "source_removal_pivots": pivots,
            "pivots_are_simulated_not_real_retractions": True,
        })
    digest = sha256(json.dumps(
        {
            "as_of": original["as_of_utc"],
            "mode": original["mode"],
            "policy_version": "LATEST_POLICY_CLOCK_CONFLICT_ABSTENTION_V1",
            "pins": [asdict(pins[sid]) for sid in sorted(pins)],
            "rules": [asdict(rule) for rule in sorted(rules, key=lambda r: r.key)],
        },sort_keys=True,separators=(",",":")
    ).encode("utf-8")).hexdigest()
    return {
        "kind": "EVIDENCETRAIL_SOURCE_WITHDRAWAL_AND_TIME_WHY_V1",
        "status": original["status"],
        "as_of_utc": original["as_of_utc"],
        "policy":original["mode"],
        "selected_claims":baseline,
        "rule_explanations":rule_explanations,
        "excluded_sources":original["excluded"],
        "unresolved_claim_conflicts":original["unresolved_claim_conflicts"],
        "evidence_needed":evidence_needed,
        "source_withdrawal_interventions":source_tests,
        "clock_boundary_interventions":time_tests,
        "audited_full_batch_source_count":len(rows),
        "pinned_input_policy_sha256_not_a_signature":digest,
        "counterfactuals_are_not_real_source_retractions":True,
        "publisher_first_publication_authenticated":False,
        "issuer_names_are_not_independent_fact_attestation":True,
        "sample_replay_not_weather_forecast":True,
        "model_or_sponsor_called":False,
        "independent_human_participants":0,
        "free_text_semantic_entailment_proven":False,
    }
