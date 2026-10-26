"""External-domain replay of official NOAA/NHC advisories, offline only.

Uses the production EvidenceTrail initial-integrity and source-time firewall,
but NOT the Yagi-specific fictional coordinator watch reducer. The output
evaluates what a selected subset of official archived bulletins SAYS was
issued by as-of, without claiming authenticated original publication bytes.

The human-curated metadata in samples/ is NOT NHC raw article text.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from evidencetrail.evidence_integrity import initial_source_integrity_issues
from evidencetrail.firewall import filter_sources, jurisdiction_ok
from evidencetrail.models import (
    ProvenanceQuality, RecordKind, ReplayMode, RunRequest, SourceRecord, iso,
    parse_iso,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "samples" / "milton_nhc_primary_source_metadata_2024.json"
EARLIEST = parse_iso("2024-10-07T00:00:00Z")
LATEST = parse_iso("2024-10-11T00:00:00Z")


def _load() -> tuple[dict, list[SourceRecord]]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("kind") != "EXTERNAL_PRIMARY_SOURCE_METADATA_V1":
        raise ValueError("EXTERNAL_CORPUS_TYPE_INVALID")
    advisories = fixture.get("advisories")
    if not isinstance(advisories, list) or not 1 <= len(advisories) <= 30:
        raise ValueError("EXTERNAL_CORPUS_SIZE_INVALID")
    rows = []
    for item in advisories:
        if not isinstance(item, dict):
            raise ValueError("EXTERNAL_CORPUS_ITEM_INVALID")
        clock = parse_iso(item["issue_utc"])
        if clock is None or not EARLIEST <= clock <= LATEST:
            raise ValueError("EXTERNAL_ISSUE_CLOCK_INVALID")
        wind = item["wind_mph"]
        if type(wind) is not int or not 0 < wind < 250:
            raise ValueError("EXTERNAL_INTENSITY_INVALID")
        source_id = item["id"]
        locator = item["source_url"]
        if (not isinstance(source_id, str)
                or not source_id.startswith("NHC-AL142024-PUBLIC-")
                or not isinstance(locator, str)
                or not locator.startswith("https://www.nhc.noaa.gov/archive/2024/al14/")
                or not locator.endswith(".shtml")):
            raise ValueError("EXTERNAL_SOURCE_REFERENCE_INVALID")
        excerpt = item["paraphrase"]
        if not isinstance(excerpt, str) or not excerpt.strip():
            raise ValueError("EXTERNAL_SOURCE_PARAPHRASE_INVALID")
        rows.append(SourceRecord(
            source_id=source_id,
            record_kind=RecordKind.GOVERNMENT_NEWS,
            locator=locator,
            publisher="NOAA/National Hurricane Center",
            paraphrase=excerpt,
            excerpt=excerpt,
            excerpt_sha256=sha256(excerpt.encode("utf-8")).hexdigest(),
            published_at_displayed_utc=clock,
            observed_at_utc=None,
            issued_at_claimed_utc=clock,
            first_availability_proven_utc=None,
            retrieved_at_utc=None,
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            historical_admin_vintage="2024",
            spatial_scope=["national", "florida"],
            named_districts_2024=[],
            granularity="regional_advisory",
            observation_fields={"reported_maximum_sustained_wind_mph": wind},
        ))
    return fixture, rows


def run_milton_external_replay(
    at: str = "2024-10-07T11:00:00Z",
    *,
    strict: bool = False,
    catalog_override: list[SourceRecord] | None = None,
) -> dict:
    as_of = parse_iso(at)
    if as_of is None or not EARLIEST <= as_of <= LATEST:
        raise ValueError("MILTON_AS_OF_OUT_OF_RANGE")
    if type(strict) is not bool:
        raise ValueError("MILTON_STRICT_BOOLEAN_REQUIRED")
    policy = (
        ReplayMode.STRICT_AS_OF_2024 if strict
        else ReplayMode.REPORTED_DATELINE_REPLAY
    )
    request = RunRequest(
        schema_version="1", as_of_utc=as_of, mode=policy,
        mission_id="noaa-milton-selected-bulletin-replay",
        scenario_id="noaa-milton-external-source-evaluation",
        province_2024="florida", district_2024=None,
        granularity="province", question=(
            "Which of the selected NHC archived advisory clocks precedes this "
            "instant, and what maximum wind does its text report?"
        ), sample_mode=True,
    )
    fixture, standard = _load()
    catalog = standard if catalog_override is None else catalog_override
    if len(catalog) > 30:
        raise ValueError("MILTON_SOURCE_BOUND_EXCEEDED")
    issues = initial_source_integrity_issues(catalog, request)
    admitted = []
    excluded = []
    if not issues:
        in_scope = [
            row for row in catalog if jurisdiction_ok(
                row, request.province_2024, request.district_2024
            )
        ]
        admitted, excluded = filter_sources(in_scope, as_of, policy)
    admitted.sort(key=lambda x: (
        x.published_at_displayed_utc or EARLIEST, x.source_id
    ))
    selected = admitted[-1] if admitted else None
    all_winds = [
        row.observation_fields.get("reported_maximum_sustained_wind_mph")
        for row in standard
    ]
    return {
        "kind": "EVIDENCETRAIL_NOAA_MILTON_EXTERNAL_EVIDENCE_REPLAY_V1",
        "corpus_event": fixture["event"],
        "source_organization": fixture["source_organization"],
        "source_index_url": fixture["index_url"],
        "as_of_utc": iso(as_of),
        "policy": policy.value,
        "source_ids_selected": [row.source_id for row in admitted],
        "source_refs_selected": [
            {"id": row.source_id, "url": row.locator,
             "displayed_issue_utc": iso(row.issued_at_claimed_utc),
             "reported_maximum_sustained_wind_mph":
              row.observation_fields["reported_maximum_sustained_wind_mph"]}
            for row in admitted
        ],
        "excluded": excluded,
        "integrity_issues": issues,
        "result": (
            "REFUSED_AMBIGUOUS_SOURCE_SET" if issues
            else "NO_ADMISSIBLE_ARCHIVED_ISSUE_IN_SELECTED_SET" if not selected
            else "SELECTED_ISSUED_BULLETIN_FOUND"
        ),
        "latest_selected_issued_advisory_id": selected.source_id if selected else None,
        "latest_selected_reported_wind_mph": (
            selected.observation_fields["reported_maximum_sustained_wind_mph"]
            if selected else None
        ),
        "unsafe_full_archive_peak_mph": max(all_winds),
        "unsafe_full_archive_is_not_as_of_prediction": True,
        "published_first_availability_authenticated": False,
        "sample_bulletin_selection_is_not_full_nhc_archive": True,
        "local_metadata_curated_from_independent_primary_sources": True,
        "production_source_integrity_and_firewall_used": True,
        "yagi_disaster_rule_verdict_computed": False,
        "model_or_sponsor_called": False,
        "external_analyst_evaluation_performed": False,
        "operational_hurricane_forecast_authorized": False,
        "needed_next_proof": (
            "Original first-public-availability audit plus independent analyst "
            "review before any historical factual or operational impact claim."
        ),
        "notice": (
            "NHC official archived 2024 issue clocks and curated facts only. "
            "A 2026 page does not prove authenticated original 2024 page bytes. "
            "Only four selected advisories, not all NHC advisories, are replayed. "
            "No weather prediction, provider inference or operational guidance."
        ),
    }


# Human-checked issue clocks from the linked NHC advisory pages, NOT model gold.
EXTERNAL_CHRONOLOGY_CASES = [
    ("2024-10-07T08:59:00Z", None),
    ("2024-10-07T09:00:00Z", 100),
    ("2024-10-07T11:00:00Z", 100),
    ("2024-10-07T12:00:00Z", 125),
    ("2024-10-07T14:00:00Z", 125),
    ("2024-10-07T15:00:00Z", 155),
    ("2024-10-07T16:00:00Z", 155),
    ("2024-10-10T21:00:00Z", 70),
]


def run_external_chronology_checks() -> dict:
    results = []
    for clock, expected in EXTERNAL_CHRONOLOGY_CASES:
        report = run_milton_external_replay(clock)
        value = report["latest_selected_reported_wind_mph"]
        results.append({
            "as_of": clock, "expected": expected, "observed": value,
            "pass": value == expected and not report["integrity_issues"],
        })
    strict = run_milton_external_replay("2024-10-07T16:00:00Z", strict=True)
    return {
        "kind": "EVIDENCETRAIL_EXTERNAL_NOAA_ISSUE_CLOCK_CHECKS_V1",
        "source": "4 independently published NOAA/NHC archived public advisories",
        "source_archive": "https://www.nhc.noaa.gov/archive/2024/MILTON.shtml?lv=true",
        "checked_cases": results, "case_count": len(results),
        "passed": sum(x["pass"] for x in results),
        "all_pass": all(x["pass"] for x in results),
        "strict_abstains_without_authenticated_first_availability":
            strict["latest_selected_issued_advisory_id"] is None,
        "external_user_validation_or_prediction_accuracy": False,
        "sponsor_inference_called": False,
        "scope": "INDEPENDENT_PUBLISHER_METADATA_HAND_CURATED_INTERNAL_GOLD",
    }
