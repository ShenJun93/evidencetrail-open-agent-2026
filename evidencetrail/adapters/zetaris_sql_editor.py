"""Pinned Zetaris local SQL Editor REST transport, source-row contract only.

This is NOT the older DBQuery/OpenSqlQuery API:
POST /api/v1.0/sql-editor/sqls/run
{queryId: UUID, sql: SELECT, source: SqlEditor, limit: 20}
Bearer API key + X-Org-ID + X-Request-ID.

Never call the network in sample mode or without an explicit local token.
User-managed secrets stay in the OS environment or ignored .env.local.
No remote/cloud endpoint, redirects, mutations, arbitrary SQL or fixtures.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from evidencetrail.models import RecordKind

FIELDS = (
    "source_id", "record_kind", "locator", "publisher", "paraphrase",
    "excerpt", "published_at_displayed_utc", "observed_at_utc",
    "issued_at_claimed_utc", "first_availability_proven_utc",
    "provenance_quality", "historical_admin_vintage", "spatial_scope",
    "named_districts_2024", "granularity", "scenario_id",
    "plan_predicates", "metadata_conflicts", "observation_fields",
    "source_origin_label",
)
TABLES = {
    RecordKind.GOVERNMENT_NEWS: "EVIDENCETRAIL_YAGI.public_datelines",
    RecordKind.SYNTHETIC_CAPACITY: "EVIDENCETRAIL_YAGI.synthetic_capacity",
}
ORIGIN_LABELS = {
    RecordKind.GOVERNMENT_NEWS:
        "2026_CURATED_PUBLIC_DATELINE_PARAPHRASE_EDIT_HISTORY_NOT_AUTHENTICATED",
    RecordKind.SYNTHETIC_CAPACITY:
        "FICTIONAL_SCENARIO_NOT_HISTORICAL_RESCUE_CAPACITY",
}
LOCAL_BASE_URLS = frozenset({
    "http://localhost:8888/api/v1.0",
    "http://127.0.0.1:8888/api/v1.0",
})
MAX_BODY = 1_048_576
MAX_ROWS = 20


class SqlEditorContractError(ValueError):
    """Safe error code only, never propagate response bytes or tokens."""


def source_sql(kind: RecordKind) -> str:
    if kind not in TABLES:
        raise SqlEditorContractError("UNSUPPORTED_SOURCE_KIND")
    return f"SELECT {', '.join(FIELDS)} FROM {TABLES[kind]} LIMIT {MAX_ROWS}"


def validate_sql(sql: str, kind: RecordKind) -> None:
    # The only permissible SQL is the exact audited fixed projection.
    # Does not admit SELECT 1, JOIN, UNION, injected WHERE or other tables.
    normalized = re.sub(r"\s+", " ", sql.strip()).lower()
    expected = re.sub(r"\s+", " ", source_sql(kind)).lower()
    if normalized != expected:
        raise SqlEditorContractError("SOURCE_SQL_NOT_ALLOWLISTED")


def validate_config(base_url: str, org_id: str, api_key: str) -> None:
    parsed = urlsplit(base_url)
    if (
        base_url.rstrip("/") not in LOCAL_BASE_URLS
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        raise SqlEditorContractError("LOCAL_SQL_EDITOR_API_BASE_REQUIRED")
    if not re.fullmatch(r"[1-9][0-9]{0,11}", org_id or ""):
        raise SqlEditorContractError("ORG_ID_NUMERIC_REQUIRED")
    if not api_key.strip() or api_key.strip().lower() in {
        "<redacted>", "changeme", "null", "none", "your-api-key",
    }:
        raise SqlEditorContractError("API_KEY_MISSING")


def decode_payload(payload: bytes, kind: RecordKind) -> list[dict[str, Any]]:
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise SqlEditorContractError("INVALID_REST_JSON") from exc
    if not isinstance(body, dict):
        raise SqlEditorContractError("EXPECTED_RESPONSE_OBJECT")
    if body.get("success") is False or "error" in body:
        raise SqlEditorContractError("ZETARIS_REPORTED_QUERY_FAILURE")
    rows = body.get("data", body.get("rows"))
    if isinstance(rows, dict):
        rows = rows.get("rows", rows.get("data"))
    if not isinstance(rows, list) or not 0 < len(rows) < MAX_ROWS:
        # 20 returned rows would be a full page with pagination not verified.
        raise SqlEditorContractError("EMPTY_UNRECOGNIZED_OR_FULL_PAGE")

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, list):
            if len(row) != len(FIELDS):
                raise SqlEditorContractError("COLUMN_WIDTH_MISMATCH")
            mapped = dict(zip(FIELDS, row))
        elif isinstance(row, dict):
            if any(f not in row for f in FIELDS):
                raise SqlEditorContractError("MISSING_PROJECTED_COLUMN")
            mapped = {key: row[key] for key in FIELDS}
        else:
            raise SqlEditorContractError("ROW_SHAPE_INVALID")

        if mapped["record_kind"] != kind.value:
            raise SqlEditorContractError("ROW_KIND_MISMATCH")
        if mapped["source_origin_label"] != ORIGIN_LABELS[kind]:
            raise SqlEditorContractError("UNVERIFIED_SOURCE_ORIGIN_LABEL")
        sid = str(mapped["source_id"] or "")
        if kind == RecordKind.GOVERNMENT_NEWS:
            if not sid.startswith("GOV-2024-"):
                raise SqlEditorContractError("GOVERNMENT_SOURCE_ID_INVALID")
            if mapped["provenance_quality"] != (
                "ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN"
            ):
                raise SqlEditorContractError("HISTORIC_ARCHIVE_SELF_ATTESTATION_DENIED")
        elif kind == RecordKind.SYNTHETIC_CAPACITY:
            if not sid.startswith("SYN-CAP-") or mapped["provenance_quality"] != "SYNTHETIC":
                raise SqlEditorContractError("UNLABELLED_SYNTHETIC_CAPACITY")
        mapped.pop("source_origin_label")
        normalized.append(mapped)
    if len({x["source_id"] for x in normalized}) != len(normalized):
        raise SqlEditorContractError("DUPLICATE_SOURCE_ID")
    return normalized


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SqlEditorContractError("REST_REDIRECT_REFUSED")


def query_rows(
    sql: str, kind: RecordKind, *,
    base_url: str, org_id: str, api_key: str,
    timeout: float = 12.0,
    opener: Callable[..., Any] | None = None,
) -> tuple[list[dict[str, Any]], str, str]:
    validate_sql(sql, kind)
    validate_config(base_url, org_id, api_key)
    request_id = str(uuid4())
    url = base_url.rstrip("/") + "/sql-editor/sqls/run"
    encoded = json.dumps({
        "queryId": str(uuid4()),
        "sql": sql,
        "source": "SqlEditor",
        "limit": MAX_ROWS,
    }, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Org-ID": org_id,
        "X-Request-ID": request_id,
    })

    # No redirects: prevent cross-origin transfer of authorization token.
    transport = opener or urllib.request.build_opener(NoRedirect()).open
    try:
        with transport(req, timeout=timeout) as response:
            if response.status != 200:
                raise SqlEditorContractError("SQL_EDITOR_HTTP_NOT_200")
            payload = response.read(MAX_BODY + 1)
            if len(payload) > MAX_BODY:
                raise SqlEditorContractError("SQL_EDITOR_RESPONSE_TOO_LARGE")
            rows = decode_payload(payload, kind)
    except urllib.error.HTTPError as exc:
        raise SqlEditorContractError(
            "REST_UNAUTHORIZED" if exc.code in (401, 403)
            else "SQL_EDITOR_HTTP_ERROR"
        ) from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SqlEditorContractError("LOCAL_REST_TRANSPORT_UNAVAILABLE") from None

    return rows, request_id, hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]
