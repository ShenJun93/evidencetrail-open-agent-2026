"""Two-issuer cross-claim timeline: NHC and Florida Governor, OFFLINE.

Date-only Florida press items have no authenticated issue clock. A conservative
end-of-local-day bound is used ONLY for reported-date replay. FDEM's ICYMI
repost is NOT an independent third issuing organization.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

from evidencetrail.external_milton import _load as load_nhc
from evidencetrail.evidence_integrity import initial_source_integrity_issues
from evidencetrail.firewall import filter_sources, jurisdiction_ok
from evidencetrail.models import (
    RecordKind, ReplayMode, RunRequest, SourceRecord, ProvenanceQuality,
    iso, parse_iso
)

FL_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "samples" / "milton_florida_governor_source_metadata_2024.json"
)
EDT = timezone(timedelta(hours=-4))
MIN_CLOCK = parse_iso("2024-10-06T00:00:00Z")
MAX_CLOCK = parse_iso("2024-10-11T00:00:00Z")


def _fl_metadata() -> tuple[dict, list[dict]]:
    fixture = json.loads(FL_FIXTURE.read_text("utf-8"))
    if (fixture.get("kind") != "EVIDENCETRAIL_MILTON_CROSS_ISSUER_2024_V1"
            or fixture.get("issuer_families") != ["NOAA_NHC", "FLORIDA_GOVERNOR"]
            or fixture.get("date_only_2024_october_offset_hours") != -4):
        raise ValueError("ISSUER_CATALOG_IDENTITY_INVALID")
    items = fixture["items"]
    if not isinstance(items, list) or len(items) != 3:
        raise ValueError("ISSUER_CATALOG_SIZE_INVALID")
    ids = [x["id"] for x in items]
    if len(set(ids)) != len(ids):
        raise ValueError("ISSUER_CATALOG_DUPLICATE_IDS")
    for item in items:
        if (item.get("issuer_family") != "FLORIDA_GOVERNOR"
                or not isinstance(item.get("value"), int)
                or not item["url"].startswith(("https://flgov.com/", "https://www.flgov.com/"))):
            raise ValueError("ISSUER_SOURCE_MALFORMED")
        _fl_safe_after(item["displayed_date_local"])
        if item["claim_type"] == "florida_counties_under_emergency":
            if item["value"] not in {35, 51}:
                raise ValueError("ISSUER_COUNT_INVALID")
        elif item["claim_type"] == "florida_governor_press_wind_mph_reported_asof_11am_et":
            if item["value"] != 155:
                raise ValueError("ISSUER_WIND_METADATA_UNEXPECTED")
        else:
            raise ValueError("ISSUER_CLAIM_TYPE_UNEXPECTED")
    return fixture, items


def _fl_safe_after(local_day: str) -> datetime:
    """After final possible instant of printed EDT calendar date.

    This is a *policy bound*, NOT proof a page was publicly retrievable then.
    October 2024 date-only claims are explicitly limited to EDT, UTC-04.
    """
    if not isinstance(local_day, str) or len(local_day) != 10:
        raise ValueError("LOCAL_DATE_INVALID")
    day = date.fromisoformat(local_day)
    if day.year != 2024 or day.month != 10:
        raise ValueError("LOCAL_DATE_OUT_OF_SCOPE")
    return datetime.combine(day + timedelta(days=1), time.min,
                            tzinfo=EDT).astimezone(timezone.utc)


def _as_source(item: dict) -> SourceRecord:
    desc = item["description"]
    return SourceRecord(
        source_id=item["id"], record_kind=RecordKind.GOVERNMENT_NEWS,
        locator=item["url"], publisher="Florida Executive Office of the Governor",
        paraphrase=desc, excerpt=desc,
        excerpt_sha256=sha256(desc.encode("utf8")).hexdigest(),
        # DO NOT forge a precise dateline from a date-only web page.
        published_at_displayed_utc=None, observed_at_utc=None,
        issued_at_claimed_utc=None, first_availability_proven_utc=None,
        retrieved_at_utc=None,
        provenance_quality=(
            ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN
        ),
        historical_admin_vintage="2024",
        spatial_scope=["national", "florida"],
        named_districts_2024=[], granularity="state_press",
        observation_fields={"claim_type":item["claim_type"], "value":item["value"]},
    )


def run_cross_issuer_milton(
    as_of_utc: str = "2024-10-07T11:00:00Z", *,
    strict: bool = False,
    extra_sources: list[SourceRecord] | None = None,
) -> dict:
    at = parse_iso(as_of_utc)
    if at is None or not MIN_CLOCK <= at <= MAX_CLOCK:
        raise ValueError("CROSS_ISSUER_CLOCK_OUT_OF_RANGE")
    if type(strict) is not bool:
        raise ValueError("CROSS_ISSUER_STRICT_BOOL_REQUIRED")
    _, nhc = load_nhc()
    fixture, florida = _fl_metadata()
    originals = nhc + [_as_source(item) for item in florida]
    rows = originals + (extra_sources if extra_sources is not None else [])
    if len(rows) > 30:
        raise ValueError("CROSS_ISSUER_TOO_MANY_SOURCES")
    policy = (ReplayMode.STRICT_AS_OF_2024 if strict
              else ReplayMode.REPORTED_DATELINE_REPLAY)
    request = RunRequest(
        schema_version="1", as_of_utc=at, mode=policy,
        mission_id="cross-issuer-milton-2024",
        scenario_id="issuer-independent-milton-case",
        province_2024="florida", district_2024=None,
        granularity="province", sample_mode=True,
        question="Which separate official claims are admissible at this time?"
    )
    issues = initial_source_integrity_issues(rows, request)
    admitted_nhc: list[SourceRecord] = []
    excluded_nhc: list[dict] = []
    florida_admitted: list[dict] = []
    florida_excluded: list[dict] = []
    if not issues:
        valid_nhc = [
            row for row in nhc
            if jurisdiction_ok(row, request.province_2024, request.district_2024)
        ]
        admitted_nhc, excluded_nhc = filter_sources(valid_nhc, at, policy)
        for item in florida:
            bound = _fl_safe_after(item["displayed_date_local"])
            allowed = not strict and at >= bound
            detail = {
                "id": item["id"], "url": item["url"],
                "issuer_family": item["issuer_family"],
                "claim_type": item["claim_type"], "value":item["value"],
                "displayed_local_date":item["displayed_date_local"],
                "conservative_safe_after_utc":iso(bound),
                "clock_is_derived_not_publisher_timestamp":True,
            }
            if allowed:
                florida_admitted.append(detail)
            else:
                florida_excluded.append({
                    **detail,
                    "reason": "UNPROVEN_FIRST_PUBLIC_AVAILABILITY" if strict
                              else "LOCAL_DATE_NOT_FULLY_ELAPSED",
                })
    admitted_nhc.sort(key=lambda x: (x.issued_at_claimed_utc, x.source_id))
    selected_nhc = admitted_nhc[-1] if admitted_nhc else None
    orders = [x for x in florida_admitted
              if x["claim_type"] == "florida_counties_under_emergency"]
    selected_order = max(
        orders, key=lambda x:(x["displayed_local_date"],x["id"])
    ) if orders else None
    press = [x for x in florida_admitted
             if x["claim_type"].startswith("florida_governor_press")]
    return {
        "kind":"EVIDENCETRAIL_CROSS_ISSUER_MILTON_V1",
        "as_of_utc":iso(at), "policy":policy.value,
        "source_families_with_admissible_claims":sorted(
            (["NOAA_NHC"] if admitted_nhc else [])+
            (["FLORIDA_GOVERNOR"] if florida_admitted else [])
        ),
        "source_family_count":int(bool(admitted_nhc))+int(bool(florida_admitted)),
        "nhc_admitted_ids":[x.source_id for x in admitted_nhc],
        "nhc_excluded":excluded_nhc,
        "florida_admitted":florida_admitted,
        "florida_excluded":florida_excluded,
        "latest_nhc_selected_wind_mph":(
            selected_nhc.observation_fields["reported_maximum_sustained_wind_mph"]
            if selected_nhc else None
        ),
        "florida_counties_under_emergency_in_selected_order":(
            selected_order["value"] if selected_order else None
        ),
        "florida_governor_11am_et_press_wind_mph":(
            press[-1]["value"] if press else None
        ),
        "integrity_issues":issues,
        "refused":bool(issues),
        "florida_republication":{
            "url":florida[-1]["syndicated_references"][0]["url"],
            "independent_issuer_family":False,
            "adds_independent_corroboration":False,
            "reason":"FDEM labels it an ICYMI repost of the Florida Governor press update",
        },
        "baseline_time_blind_sources_considered":len(originals),
        "baseline_future_source_count":(
            sum(bool(x.published_at_displayed_utc and
                     x.published_at_displayed_utc > at) for x in nhc)
            + sum(_fl_safe_after(x["displayed_date_local"])>at for x in florida)
        ),
        "baseline_is_intentionally_invalid":True,
        "source_selection_from_production_integrity_and_nhc_firewall":True,
        "date_precision_firewall_is_new_explicit_policy":True,
        "original_2024_first_publication_authenticated":False,
        "external_analyst_or_field_impact_measured":False,
        "independent_issuer_families_in_corpus":2,
        "noaahurricane_weather_prediction_performed":False,
        "sponsor_calls_performed":False,
        "notice":(
            "NHC and Florida Governor issue separate kinds of claims. "
            "FDEM ICYMI repost is NOT a third corroborating issuer. "
            "Date-only Florida admission waits until after its entire EDT date; "
            "this is conservative chronology logic, not a verified 2024 "
            "publication or safety decision. Strict mode abstains."
        ),
    }


CROSS_ISSUER_GOLD = (
    ("2024-10-06T03:00:00Z", None, None, 0),
    ("2024-10-06T04:00:00Z", None, 35, 1),
    ("2024-10-07T03:59:00Z", None, 35, 1),
    ("2024-10-07T04:00:00Z", None, 51, 1),
    ("2024-10-07T08:59:00Z", None, 51, 1),
    ("2024-10-07T11:00:00Z", 100, 51, 2),
    ("2024-10-07T15:00:00Z", 155, 51, 2),
    ("2024-10-08T03:59:00Z", 155, 51, 2),
    ("2024-10-08T04:00:00Z", 155, 51, 2),
)
def run_cross_issuer_evaluation() -> dict:
    cases=[]
    for clock, wind, count, families in CROSS_ISSUER_GOLD:
        r=run_cross_issuer_milton(clock)
        cases.append({
            "as_of_utc":clock, "expected_wind":wind,"observed_wind":r["latest_nhc_selected_wind_mph"],
            "expected_emergency_count":count,
            "observed_emergency_count":r["florida_counties_under_emergency_in_selected_order"],
            "expected_issuer_count":families,"observed_issuer_count":r["source_family_count"],
            "pass":(
                wind==r["latest_nhc_selected_wind_mph"]
                and count==r["florida_counties_under_emergency_in_selected_order"]
                and families==r["source_family_count"]
                and not r["integrity_issues"]
                and not r["florida_republication"]["adds_independent_corroboration"]
            ),
        })
    strict=run_cross_issuer_milton("2024-10-08T04:00:00Z",strict=True)
    return {
        "kind":"EVIDENCETRAIL_CROSS_ISSUER_CONSERVATIVE_GOLD_V1",
        "cases":cases, "passed":sum(c["pass"] for c in cases),
        "total":len(cases), "pass":all(c["pass"] for c in cases),
        "strict_all_families_abstain":(
            strict["source_family_count"]==0
            and strict["latest_nhc_selected_wind_mph"] is None
            and strict["florida_counties_under_emergency_in_selected_order"] is None
        ),
        "gold_is_internally_authored_from_official_issuer_pages":True,
        "independent_human_outcomes_measured":False,
        "sponsor_calls_performed":False,
    }
