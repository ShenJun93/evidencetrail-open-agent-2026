"""NOAA + Florida curated SOURCE MANIFEST for reusable claim-ledger engine.

All pins are operator-curated metadata independently loaded from the curated
source-reference files, not derived from SQL rows being evaluated. Their
presence proves a local policy contract, NOT original 2024 page bytes.
"""
from __future__ import annotations

from hashlib import sha256

from evidencetrail.claim_ledger import ClaimRule, SourcePin, evaluate_claim_ledger
from evidencetrail.cross_issuer_milton import _fl_metadata, _fl_safe_after
from evidencetrail.external_milton import _load as load_nhc
from evidencetrail.models import (
    ProvenanceQuality, RecordKind, ReplayMode, iso
)
from evidencetrail.zetaris_cross_issuer import _canonical_rows


def curated_milton_manifest() -> tuple[dict[str, SourcePin], list[ClaimRule]]:
    _, nhc = load_nhc()
    _, florida = _fl_metadata()
    pins: dict[str, SourcePin] = {}
    for row in nhc:
        pins[row.source_id] = SourcePin(
            source_id=row.source_id,locator=row.locator,
            publisher=row.publisher,excerpt_sha256=row.excerpt_sha256,
            issuer_family="NOAA_NHC",claim_key="NHC_WIND",
            expected_value=row.observation_fields[
                "reported_maximum_sustained_wind_mph"],
            record_kind=RecordKind.GOVERNMENT_NEWS,
            provenance_quality=row.provenance_quality,
            claimed_issue_utc=iso(row.issued_at_claimed_utc),
        )
    for item in florida:
        claim_type=item["claim_type"]
        key=("FL_ORDER" if claim_type == "florida_counties_under_emergency"
             else "FL_PRESS")
        pins[item["id"]] = SourcePin(
            source_id=item["id"],locator=item["url"],
            publisher="Florida Executive Office of the Governor",
            excerpt_sha256=sha256(item["description"].encode()).hexdigest(),
            issuer_family="FLORIDA_GOVERNOR",claim_key=key,
            expected_value=item["value"],
            record_kind=RecordKind.GOVERNMENT_NEWS,
            provenance_quality=(
                ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN),
            displayed_local_day=item["displayed_date_local"],
            curator_not_before_utc=iso(_fl_safe_after(item["displayed_date_local"])),
            local_utc_offset_minutes=-240,
        )
    rules=[
        ClaimRule("NHC_WIND","NOAA_NHC","maximum_sustained_wind_mph",
                  "value","mph","NOAA reported sustained wind"),
        ClaimRule("FL_ORDER","FLORIDA_GOVERNOR",
                  "florida_counties_under_emergency","value","counties",
                  "Florida emergency order county count"),
        ClaimRule("FL_PRESS","FLORIDA_GOVERNOR",
                  "florida_governor_press_wind_mph_reported_asof_11am_et",
                  "value","mph","Florida press reported wind"),
    ]
    return pins, rules


def evaluate_milton_sql_claims(
    nhc_sql: list[dict], florida_sql: list[dict], *,
    as_of_utc: str = "2024-10-07T11:00:00Z",
    strict: bool = False
) -> dict:
    """Must receive actual rows from the caller; never substitute local fixtures."""
    if type(strict) is not bool:
        raise ValueError("LEDGER_STRICT_MUST_BE_BOOLEAN")
    pins, rules = curated_milton_manifest()
    # Existing physical Zetaris adapter enforces the seven-row issuer,
    # source-URL/value/clock contract, then generic ledger rebinds to pins.
    records = _canonical_rows(nhc_sql, florida_sql)
    return evaluate_claim_ledger(
        records,pins,rules,as_of_utc=as_of_utc,
        mode=(ReplayMode.STRICT_AS_OF_2024 if strict
              else ReplayMode.REPORTED_DATELINE_REPLAY)
    )
