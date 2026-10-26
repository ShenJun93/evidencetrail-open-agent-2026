"""Read-only Zetaris SQL Editor bridge for the Milton two-issuer *curated* corpus.

Never creates tables, reads .env, downloads files, or calls AI providers.
The source metadata is still manually curated from official pages; a valid SQL
response proves SQL rows were consumed, not first-publication provenance.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from hashlib import sha256
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable
from uuid import uuid4

from evidencetrail.adapters.zetaris_sql_editor import (
    SqlEditorContractError, NoRedirect, validate_config, LOCAL_BASE_URLS,
)
from evidencetrail.cross_issuer_milton import (
    _fl_metadata, _fl_safe_after, run_cross_issuer_milton,
)
from evidencetrail.external_milton import _load as load_nhc
from evidencetrail.evidence_integrity import initial_source_integrity_issues
from evidencetrail.firewall import filter_sources, jurisdiction_ok
from evidencetrail.models import (
    SourceRecord, RecordKind, ProvenanceQuality, ReplayMode,
    RunRequest, parse_iso, iso,
)

COLS = ("source_id", "issuer_family", "claim_type", "locator", "excerpt",
        "excerpt_sha256", "value_int", "issue_utc", "displayed_date_local")
NHC_TABLE = "EVIDENCETRAIL_MILTON.nhc_selected_advisories"
FL_TABLE = "EVIDENCETRAIL_MILTON.florida_governor_records"
SQL = {
    "NOAA_NHC": "SELECT " + ", ".join(COLS) + " FROM " + NHC_TABLE + " LIMIT 10",
    "FLORIDA_GOVERNOR": "SELECT " + ", ".join(COLS) + " FROM " + FL_TABLE + " LIMIT 10",
}
MAX_BODY = 1_048_576
MAX_ROWS = 9


def query_sql_editor(
    issuer: str, *, base_url: str, org_id: str, api_key: str,
    timeout: int = 20, opener: Callable[..., Any] | None = None,
) -> tuple[list[dict], str, str]:
    """Only the two hardcoded read-only SQL projections are allowed."""
    if issuer not in SQL:
        raise SqlEditorContractError("UNAPPROVED_ISSUER_QUERY")
    validate_config(base_url, org_id, api_key)
    query = SQL[issuer]
    request_id = str(uuid4())
    body = json.dumps({
        "queryId": str(uuid4()), "sql": query,
        "source": "SqlEditor", "limit": MAX_ROWS,
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/sql-editor/sqls/run",
        data=body, method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            "X-Org-ID": org_id, "X-Request-ID": request_id,
        },
    )
    transport = opener or urllib.request.build_opener(NoRedirect()).open
    try:
        with transport(request, timeout=timeout) as response:
            if response.status != 200:
                raise SqlEditorContractError("SOURCE_HTTP_NOT_200")
            payload = response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        raise SqlEditorContractError(
            "REST_UNAUTHORIZED" if exc.code in (401, 403)
            else "SOURCE_HTTP_ERROR"
        ) from None
    except (OSError, TimeoutError, urllib.error.URLError):
        raise SqlEditorContractError("LOCAL_SQL_EDITOR_UNAVAILABLE") from None
    if len(payload) > MAX_BODY:
        raise SqlEditorContractError("SOURCE_RESULT_TOO_LARGE")
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise SqlEditorContractError("SOURCE_RESULT_NOT_JSON") from None
    if not isinstance(obj, dict) or "error" in obj or obj.get("success") is False:
        raise SqlEditorContractError("SOURCE_SQL_EXECUTION_ERROR")
    rows = obj.get("data", obj.get("rows"))
    if isinstance(rows, dict):
        rows = rows.get("rows", rows.get("data"))
    if not isinstance(rows, list) or not 0 < len(rows) < MAX_ROWS:
        raise SqlEditorContractError("SOURCE_RESULT_MISSING_OR_PAGINATED")
    output: list[dict] = []
    for row in rows:
        if isinstance(row, list) and len(row) == len(COLS):
            value = dict(zip(COLS, row))
        elif isinstance(row, dict) and all(k in row for k in COLS):
            value = {k: row[k] for k in COLS}
        else:
            raise SqlEditorContractError("SOURCE_COLUMNS_MISMATCH")
        if value["issuer_family"] != issuer:
            raise SqlEditorContractError("SOURCE_ISSUER_MISMATCH")
        output.append(value)
    if len(set(x["source_id"] for x in output)) != len(output):
        raise SqlEditorContractError("SOURCE_DUPLICATE_IDS")
    return output, request_id, sha256(query.encode()).hexdigest()[:12]


def _sql_int(value: object) -> int:
    if type(value) is int and 0 <= value <= 999:
        return value
    if isinstance(value, str) and re.fullmatch(r"(0|[1-9][0-9]{0,2})",value):
        return int(value)
    raise SqlEditorContractError("SQL_INTEGER_TYPE_UNTRUSTED")


def _sql_issue_clock(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value,str):
        raise SqlEditorContractError("SQL_ISSUE_CLOCK_TYPE_UNTRUSTED")
    if re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}[.]0",value):
        try:
            return datetime.strptime(value,"%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        except ValueError:
            raise SqlEditorContractError("SQL_ISSUE_CLOCK_UNPARSABLE") from None
    try:
        parsed=parse_iso(value)
    except ValueError:
        parsed=None
    if parsed is None:
        raise SqlEditorContractError("SQL_ISSUE_CLOCK_NOT_EXPLICIT_UTC")
    return parsed


def _canonical_rows(nhc: list[dict], florida: list[dict]) -> list[SourceRecord]:
    """Bound SQL material to the seven curated, externally linked source IDs.

    Always use actual returned SQL fields; never substitute fixture values
    silently. The fixture is a data-origin allowlist, not a source of results.
    """
    _, nhc_expected = load_nhc()
    _, fl_expected = _fl_metadata()
    expected: dict[str, tuple] = {}
    for row in nhc_expected:
        expected[row.source_id] = (
            "NOAA_NHC", row.locator, row.issued_at_claimed_utc,
            None, row.observation_fields["reported_maximum_sustained_wind_mph"],
            "maximum_sustained_wind_mph",
        )
    for row in fl_expected:
        expected[row["id"]] = (
            "FLORIDA_GOVERNOR", row["url"], None,
            row["displayed_date_local"], row["value"], row["claim_type"],
        )
    if len(nhc) != 4 or len(florida) != 3:
        raise SqlEditorContractError("CROSS_ISSUER_MISSING_CURATED_ROWS")
    records: list[SourceRecord] = []
    for data in nhc + florida:
        sid = data.get("source_id")
        if not isinstance(sid, str) or sid not in expected:
            raise SqlEditorContractError("UNKNOWN_CROSS_ISSUER_SOURCE")
        issuer, url, issue, day, value, ctype = expected[sid]
        # CSV roundtrip yields decimal strings and Spark-naive display
        # timestamps. Enforce the official expected value and UTC instant.
        sql_value=_sql_int(data.get("value_int"))
        sql_clock=_sql_issue_clock(data.get("issue_utc"))
        if (data.get("issuer_family") != issuer
                or data.get("locator") != url
                or data.get("claim_type") != ctype
                or sql_value != value
                or data.get("displayed_date_local") != day
                or sql_clock != issue):
            raise SqlEditorContractError("CROSS_ISSUER_METADATA_DOES_NOT_MATCH_OFFICIAL_CURATED_SET")
        excerpt = data.get("excerpt")
        digest = data.get("excerpt_sha256")
        if (not isinstance(excerpt, str) or not excerpt.strip()
                or not isinstance(digest, str)
                or digest != sha256(excerpt.encode("utf-8")).hexdigest()):
            raise SqlEditorContractError("CROSS_ISSUER_EXCERPT_INVALID")
        records.append(SourceRecord(
            source_id=sid, record_kind=RecordKind.GOVERNMENT_NEWS,
            locator=url,
            publisher=("NOAA/National Hurricane Center" if issuer == "NOAA_NHC"
                       else "Florida Executive Office of the Governor"),
            paraphrase=excerpt, excerpt=excerpt, excerpt_sha256=digest,
            issued_at_claimed_utc=issue, published_at_displayed_utc=issue,
            observed_at_utc=None, retrieved_at_utc=None,
            first_availability_proven_utc=None,
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            historical_admin_vintage="2024", spatial_scope=["national", "florida"],
            named_districts_2024=[], granularity="regional_advisory" if issue else "state_press",
            observation_fields={
                "issuer_family":issuer, "claim_type":ctype, "value":value,
                "displayed_date_local":day,
            },
        ))
    if len({r.source_id for r in records}) != 7:
        raise SqlEditorContractError("CROSS_ISSUER_IDENTITY_AMBIGUOUS")
    return records


def evaluate_sql_rows(
    nhc: list[dict], florida: list[dict], *,
    clock: str = "2024-10-07T11:00:00Z", strict: bool = False,
) -> dict:
    """Consume actual materialized rows with shared production integrity/time gates."""
    if type(strict) is not bool:
        raise ValueError("STRICT_MUST_BE_BOOLEAN")
    at = parse_iso(clock)
    if at is None or not (
        parse_iso("2024-10-06T00:00:00Z") <= at <=
        parse_iso("2024-10-11T00:00:00Z")
    ):
        raise ValueError("AS_OF_OUT_OF_SCOPE")
    records = _canonical_rows(nhc, florida)
    request = RunRequest(
        schema_version="1", as_of_utc=at,
        mode=ReplayMode.STRICT_AS_OF_2024 if strict else ReplayMode.REPORTED_DATELINE_REPLAY,
        mission_id="zetaris-two-issuer-source-audit",
        scenario_id="milton-origin-precision-case",
        province_2024="florida", district_2024=None,
        granularity="province", sample_mode=False,
        question="What selected originally attributed evidence was knowable at this UTC time?",
    )
    issues = initial_source_integrity_issues(records, request)
    if issues:
        raise SqlEditorContractError("CROSS_ISSUER_INITIAL_SOURCE_INTEGRITY_REFUSED")
    nhc_rows = [r for r in records
                if r.observation_fields["issuer_family"] == "NOAA_NHC"]
    florida_rows = [r for r in records
                    if r.observation_fields["issuer_family"] == "FLORIDA_GOVERNOR"]
    admitted, excluded = filter_sources([
        r for r in nhc_rows
        if jurisdiction_ok(r, request.province_2024, request.district_2024)
    ], request.as_of_utc, request.mode)
    admitted.sort(key=lambda x: (x.issued_at_claimed_utc, x.source_id))
    eligible_fl = [
        r for r in florida_rows
        if not strict and _fl_safe_after(
            r.observation_fields["displayed_date_local"]
        ) <= at
    ]
    orders = [r for r in eligible_fl if
              r.observation_fields["claim_type"] == "florida_counties_under_emergency"]
    latest_order = max(orders, key=lambda r: (
        r.observation_fields["displayed_date_local"], r.source_id
    )) if orders else None
    latest_nhc = admitted[-1] if admitted else None
    return {
        "kind":"EVIDENCETRAIL_ZETARIS_TWO_ISSUER_ROWS_CONSUMED_V1",
        "as_of_utc":iso(at), "policy":request.mode.value,
        "sql_decoded_issuer_row_counts":{"NOAA_NHC":len(nhc),"FLORIDA_GOVERNOR":len(florida)},
        "selected_issuer_families":sorted(
            (["NOAA_NHC"] if latest_nhc else []) +
            (["FLORIDA_GOVERNOR"] if eligible_fl else [])
        ),
        "selected_original_ids":([r.source_id for r in admitted]+
                                 [r.source_id for r in eligible_fl]),
        "excluded_noaa_source_count":len(excluded),
        "latest_noaa_wind_mph":(
            latest_nhc.observation_fields["value"] if latest_nhc else None
        ),
        "latest_florida_emergency_counties":(
            latest_order.observation_fields["value"] if latest_order else None
        ),
        "source_data_was_supplied_by_sql_query_arguments":True,
        "original_2024_first_publication_authenticated":False,
        "zetaris_server_identity_independently_attested":False,
        "no_real_model_or_hmem_called":True,
        "republication_is_not_an_independent_third_origin":True,
    }
