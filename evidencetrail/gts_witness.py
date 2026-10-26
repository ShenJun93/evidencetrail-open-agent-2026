"""Conservative comparison of NOAA bulletin valid clocks with GDACS GTS relay clocks.

Both corpora are operator-curated from currently public archives. This NEVER
establishes cryptographically authenticated 2024 first publication/availability.
Relay receipt adds no independent *issuer* and cannot be used as Strict proof.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from evidencetrail.external_milton import _load as load_official
from evidencetrail.models import parse_iso, iso

FIXTURE = Path(__file__).resolve().parent.parent / "samples" / "milton_gdacs_gts_2024.json"
EXPECTED_SOURCE = "https://gdacs.org/gts.aspx?eventid=1001111&eventtype=TC"
HEADER_RE = re.compile(r"WTNT34 KNHC ([0-3][0-9])([0-2][0-9])([0-5][0-9])")


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"2024-10-(?:0[5-9]|10)T(?:[01][0-9]|2[0-3]):[0-5][0-9]:00Z", value
    ):
        raise ValueError(f"GTS_{label}_INVALID")
    parsed = parse_iso(value)
    if parsed is None:
        raise ValueError(f"GTS_{label}_INVALID")
    return parsed.astimezone(timezone.utc)


def validated_gts_witnesses(
    fixture: dict | None = None,
) -> list[dict]:
    """Validate whole pinned batch before letting any clock drive a replay."""
    data = fixture if fixture is not None else json.loads(FIXTURE.read_text("utf-8"))
    if not isinstance(data, dict) or data.get("kind") != (
        "EVIDENCETRAIL_GDACS_GTS_WITNESS_METADATA_V1"
    ):
        raise ValueError("GTS_CORPUS_TYPE_INVALID")
    if data.get("source_url") != EXPECTED_SOURCE or (
        data.get("authentic_2024_first_web_publication_proven") is not False
        or data.get("contemporaneous_immutable_reception_log_proven") is not False
    ):
        raise ValueError("GTS_UNSUPPORTED_PROVENANCE_CLAIM")
    records = data.get("rows")
    if not isinstance(records, list) or len(records) != 4:
        raise ValueError("GTS_INCOMPLETE_OR_OVERSIZED_BATCH")
    _, official = load_official()
    originals = {rec.source_id: rec for rec in official}
    if len(originals) != 4:
        raise ValueError("GTS_OFFICIAL_CORPUS_CHANGED")
    seen: set[str] = set()
    witnesses = []
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("GTS_MALFORMED_ROW")
        source_id = row.get("source_id")
        if type(source_id) is not str or source_id in seen or source_id not in originals:
            raise ValueError("GTS_DUPLICATE_OR_UNPINNED_SOURCE")
        seen.add(source_id)
        official_record = originals[source_id]
        expected_wind = official_record.observation_fields["reported_maximum_sustained_wind_mph"]
        if type(row.get("wind_mph")) is not int or row["wind_mph"] != expected_wind:
            raise ValueError("GTS_WIND_DIVERGES_FROM_OFFICIAL")
        received = _utc(row.get("gts_received_utc"), "RECEIPT_CLOCK")
        valid = official_record.issued_at_claimed_utc
        if valid is None or received.date() != valid.date():
            raise ValueError("GTS_UNEXPECTED_RECEIPT_DAY")
        header = row.get("wmo_header")
        m = HEADER_RE.fullmatch(header) if isinstance(header, str) else None
        if m is None:
            raise ValueError("GTS_WMO_HEADER_INVALID")
        try:
            transmitted = datetime(2024, 10, int(m[1]), int(m[2]), int(m[3]),
                                   tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("GTS_WMO_CLOCK_INVALID") from exc
        if not (transmitted <= received <= transmitted + timedelta(minutes=15)):
            raise ValueError("GTS_TRANSMISSION_RECEIPT_ORDER_INVALID")
        # This is a bounded dataset observation, NOT a universal NHC rule.
        if not (transmitted <= valid <= transmitted + timedelta(minutes=35)):
            raise ValueError("GTS_BULLETIN_REFERENCE_TIME_MISMATCH")
        witnesses.append({
            "source_id": source_id,
            "reported_wind_mph": expected_wind,
            "wmo_header": header,
            "wire_header_utc": iso(transmitted),
            "gdacs_reported_received_utc": iso(received),
            "nhc_bulletin_valid_utc": iso(valid),
            "minutes_received_before_valid": int((valid - received).total_seconds() / 60),
        })
    if seen != set(originals):
        raise ValueError("GTS_MISSING_OFFICIAL_SOURCE")
    return sorted(witnesses, key=lambda x: (x["gdacs_reported_received_utc"], x["source_id"]))


def compare_gts_vs_bulletin_clocks(as_of_utc: str, *, strict: bool = False,
                                  fixture: dict | None = None) -> dict:
    if type(strict) is not bool:
        raise ValueError("GTS_STRICT_MUST_BE_BOOLEAN")
    moment = _utc(as_of_utc, "AS_OF")
    witnesses = validated_gts_witnesses(fixture)
    relay = [r for r in witnesses if r["gdacs_reported_received_utc"] <= iso(moment)]
    bulletin = [r for r in witnesses if r["nhc_bulletin_valid_utc"] <= iso(moment)]
    return {
        "kind": "EVIDENCETRAIL_GTS_RELAY_VS_BULLETIN_CLOCKS_V1",
        "as_of_utc": iso(moment),
        "mode": "STRICT_NO_AUTHENTICATED_CAPTURE" if strict else "TWO_REPORTED_CLOCKS_COMPARISON",
        "status": "ABSTAIN_UNAUTHENTICATED_FIRST_PUBLICATION" if strict else "REPORTED_CLOCK_COMPARISON_ONLY",
        "gdacs_relay_reportedly_seen_source_ids": [r["source_id"] for r in relay] if not strict else [],
        "nhc_bulletin_valid_source_ids": [r["source_id"] for r in bulletin] if not strict else [],
        "reported_receipt_before_bulletin_valid_source_ids": (
            [r["source_id"] for r in relay if r not in bulletin] if not strict else []
        ),
        "witnesses": witnesses,
        "independent_original_first_publication_proven": False,
        "relay_is_additional_independent_issuer": False,
        "gdacs_reported_clock_is_authenticated_2024_capture": False,
        "claim_is_not_operational_weather_forecast": True,
        "model_or_sponsor_called": False,
        "independent_human_participants": 0,
        "notice": (
            "A retrospectively visible GTS relay log can corroborate transmitted "
            "NHC content and show clock discrepancies; it is not a signed "
            "first-web-publication timestamp, and strict as-of still abstains."
        ),
    }
