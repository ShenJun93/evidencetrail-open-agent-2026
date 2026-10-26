from __future__ import annotations

from evidencetrail.models import RecordKind, ReplayMode, RunRequest, SourceRecord, Verdict
from evidencetrail.evidence_integrity import matching_scenario_capacities


def decide(request: RunRequest, eligible: list[SourceRecord]) -> tuple[Verdict, str, list[str], list[str]]:
    """Rule reducer. Time/place never maps directly to WARN.

    WARN only if every required predicate is present on eligible rows.
    """
    missing: list[str] = []
    used: list[str] = []

    if request.mode == ReplayMode.STRICT_AS_OF_2024:
        proven = [
            s
            for s in eligible
            if s.record_kind == RecordKind.GOVERNMENT_NEWS and s.first_availability_proven_utc is not None
        ]
        if not proven:
            missing.append("AUTHENTICATED_2024_SNAPSHOT or proven first_availability_proven_utc")
            return (
                Verdict.INSUFFICIENT_EVIDENCE,
                "STRICT_AS_OF_2024 cannot treat displayed datelines as immutable original bytes.",
                missing,
                used,
            )

    public = [s for s in eligible if s.record_kind == RecordKind.GOVERNMENT_NEWS]
    used.extend(s.source_id for s in public)

    if request.granularity == "district":
        district_named = [
            s
            for s in public
            if request.district_2024
            and request.district_2024.lower() in [d.lower() for d in s.named_districts_2024]
        ]
        if not district_named:
            missing.append(
                f"public source naming district '{request.district_2024}' available at as_of "
                "(province-wide articles are not district proof)"
            )
    else:
        district_named = []

    capacity = matching_scenario_capacities(request, eligible)
    if not capacity:
        missing.append(f"scenario-bound SYNTHETIC capacity row for {request.scenario_id}")
    else:
        used.extend(s.source_id for s in capacity)
        pred = capacity[0].plan_predicates
        if request.granularity == "district" and request.district_2024:
            if not pred.get("named_district_matches"):
                missing.append("synthetic plan predicate named_district_matches")
            elif request.district_2024.lower() not in [d.lower() for d in capacity[0].named_districts_2024]:
                missing.append("synthetic capacity district does not match requested 2024 district")
        if not pred.get("coordinator_watch_authorized"):
            missing.append("synthetic plan predicate coordinator_watch_authorized")
        if pred.get("site_population_verified") is not True:
            missing.append("verified site-level population (absent; required for operational WARN, not simulated watch)")
        if pred.get("route_safety_verified") is not True:
            missing.append("verified route safety")
        if pred.get("original_2024_bytes_authenticated") is not True:
            missing.append("authenticated original 2024 source bytes")

    # Simulated coordinator watch: allowed only when district-named public source
    # AND scenario-bound synthetic watch authorization exist. Missing operational
    # predicates keep the verdict from being an implied real evacuation order;
    # they are listed as caveats via missing_facts but do not block SIMULATED WARN
    # if the two research predicates hold.
    research_blockers = [
        m
        for m in missing
        if m.startswith("public source naming")
        or m.startswith("scenario-bound")
        or "named_district_matches" in m
        or "does not match requested" in m
        or "coordinator_watch_authorized" in m
    ]
    operational_gaps = [m for m in missing if m not in research_blockers]

    if not research_blockers and district_named and capacity:
        rationale = (
            "SIMULATED coordinator watch: a reported-dateline public source names the "
            "requested 2024 district and a scenario-bound SYNTHETIC capacity row authorizes "
            "watch. This is not a 2024 evacuation order and not authenticated original bytes."
        )
        return Verdict.WARN, rationale, operational_gaps, used

    rationale = (
        "INSUFFICIENT_EVIDENCE: required research predicates are missing at this as_of. "
        "No hardcoded WARN by clock or place name."
    )
    return Verdict.INSUFFICIENT_EVIDENCE, rationale, missing, used
