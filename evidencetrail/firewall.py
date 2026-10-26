from __future__ import annotations

import re
from datetime import datetime

from evidencetrail.models import ProvenanceQuality, RecordKind, ReplayMode, SourceRecord

URL_TIME_GUESS = re.compile(r"16[0-9]{2}")


def availability_reason(source: SourceRecord, as_of: datetime, mode: ReplayMode) -> str | None:
    """Return exclusion reason, or None if the source may enter the evidence set.

    Availability is the source-record publication/proof clock, never observation
    time, URL slug digits, retrieval time, or model valid time.
    """
    # Typed identity is a trust boundary: an imported 2026 portal or a
    # synthetic record cannot become government evidence merely by retyping
    # its kind or choosing a 2024-looking published_at_displayed_utc.
    if source.record_kind == RecordKind.GOVERNMENT_NEWS and source.provenance_quality in (
        ProvenanceQuality.IMPORTED_2024_DATELINE_ON_2026_PORTAL,
        ProvenanceQuality.SYNTHETIC,
    ):
        return "PUBLIC_NEWS_ORIGIN_LABEL_CONFLICT_REJECTED"
    if (source.record_kind == RecordKind.SYNTHETIC_CAPACITY
        and source.provenance_quality != ProvenanceQuality.SYNTHETIC):
        return "SYNTHETIC_CAPACITY_ORIGIN_LABEL_CONFLICT_REJECTED"
    if source.record_kind == RecordKind.RETROSPECTIVE_HINDCAST:
        return "RETROSPECTIVE_HINDCAST_not_operational_2024_forecast"
    if source.record_kind == RecordKind.IMPORTED_ARCHIVE:
        return "IMPORTED_2024_DATELINE_ON_2026_PORTAL_first_publication_unverified"
    if source.provenance_quality == ProvenanceQuality.RETROSPECTIVE_2026_HINDCAST:
        return "RETROSPECTIVE_2026_HINDCAST"

    if source.record_kind == RecordKind.SYNTHETIC_CAPACITY:
        return None

    if mode == ReplayMode.STRICT_AS_OF_2024:
        # A clock claimed inside a curated row is not an archive attestation.
        # Both an authenticated snapshot provenance classification AND a
        # concrete verified-availability bound are required. CDX index
        # timestamps alone never set either field.
        if source.provenance_quality != ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT:
            return "STRICT_AS_OF_2024_snapshot_provenance_not_authenticated"
        proven = source.first_availability_proven_utc
        if proven is None:
            return "STRICT_AS_OF_2024_unproven_first_availability"
        if proven > as_of:
            return "STRICT_AS_OF_2024_proven_availability_after_as_of"
        return None

    published = source.published_at_displayed_utc
    if published is None:
        return "missing_published_at_displayed_utc"
    if published > as_of:
        return "published_at_displayed_after_as_of"
    return None


def filter_sources(
    sources: list[SourceRecord],
    as_of: datetime,
    mode: ReplayMode,
) -> tuple[list[SourceRecord], list[dict]]:
    eligible: list[SourceRecord] = []
    excluded: list[dict] = []
    for source in sources:
        reason = availability_reason(source, as_of, mode)
        extra = []
        if source.observed_at_utc and source.published_at_displayed_utc:
            if source.observed_at_utc < source.published_at_displayed_utc:
                extra.append("observation_time_is_not_publication_time")
        if URL_TIME_GUESS.search(source.locator) and source.published_at_displayed_utc:
            extra.append("url_slug_or_id_is_not_publication_time")
        if reason:
            excluded.append(
                {
                    "source_id": source.source_id,
                    "reason": reason,
                    "advisories": extra + source.metadata_conflicts,
                    "published_at_displayed_utc": (
                        source.published_at_displayed_utc.isoformat()
                        if source.published_at_displayed_utc
                        else None
                    ),
                    "observed_at_utc": (
                        source.observed_at_utc.isoformat() if source.observed_at_utc else None
                    ),
                }
            )
        else:
            eligible.append(source)
    return eligible, excluded


def jurisdiction_ok(source: SourceRecord, province_2024: str, district_2024: str | None) -> bool:
    if source.record_kind == RecordKind.SYNTHETIC_CAPACITY:
        return True
    if source.historical_admin_vintage and "2026" in source.historical_admin_vintage:
        if "lao cai" in ",".join(source.spatial_scope).lower() and province_2024.lower() == "yen bai":
            return False
    scopes = [s.lower() for s in source.spatial_scope]
    if "national" in scopes:
        return True
    # District names can appear in a mis-scoped article; they are a
    # *granularity predicate* for the reducer, never geographic authority to
    # override an explicitly different province's source scope.
    return province_2024.lower() in scopes or (
        district_2024 is not None and district_2024.lower() in scopes
    )


def filter_memories(
    memories: list[dict],
    mission_id: str,
    as_of: datetime,
    eligible_source_ids: set[str],
    scenario_id: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Memory is untrusted recall. Require explicit mission, vintage and scope.

    H-MEM retrieval does not enforce as-of. Never supply a tagless or malicious
    memory to an AI provider as an instruction. An admissible prior verdict is
    comparison context only, not new evidence or a citation source.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for mem in memories:
        reasons: list[str] = []
        mid = mem.get("missionId") or mem.get("mission_id")
        if mid != mission_id:
            reasons.append("cross_mission")
        if mem.get("source") != "evidencetrail.decision":
            reasons.append("untrusted_memory_origin")
        tags = mem.get("tags") or []
        prior_as_of = None
        cited = []
        scenarios = []
        for tag in tags:
            if not isinstance(tag, str):
                reasons.append("malformed_tag")
                continue
            if tag.startswith("prior_decision_as_of:"):
                prior_as_of = tag.split(":", 1)[1]
            elif tag.startswith("source:"):
                cited.append(tag.split(":", 1)[1])
            elif tag.startswith("scenario:"):
                scenarios.append(tag.split(":", 1)[1])
        for sid in cited:
            if sid not in eligible_source_ids:
                reasons.append(f"memory_cites_ineligible_source:{sid}")
        if not prior_as_of:
            reasons.append("missing_prior_as_of")
        else:
            try:
                from evidencetrail.models import parse_iso

                prior_dt = parse_iso(prior_as_of)
                if prior_dt and prior_dt > as_of:
                    reasons.append("future_decision_memory")
            except (ValueError, TypeError):
                reasons.append("malformed_prior_as_of")
        if scenario_id and (len(scenarios) != 1 or scenarios[0] != scenario_id):
            reasons.append("cross_scenario_or_untagged")
        if reasons:
            dropped.append({"memory_id": mem.get("id"), "reasons": list(dict.fromkeys(reasons))})
        else:
            kept.append(mem)
    return kept, dropped
