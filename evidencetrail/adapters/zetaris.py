from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from evidencetrail.catalog import all_catalog
from evidencetrail.models import (
    SourceRecord, SponsorCall, SponsorOutcome, RecordKind,
    ProvenanceQuality, parse_iso, utc_now,
)


class ZetarisAdapter:
    """Two logical source classes: government-news catalog and synthetic capacity.

    Live REST is attempted only when SAMPLE_MODE is false and credentials/URL exist.
    A cache hit is SAMPLE_CACHE, never REAL_SUCCESS.
    """

    def __init__(self, sample_mode: bool = True):
        self.sample_mode = sample_mode
        self.rest_url = os.environ.get("ZETARIS_REST_URL", "").rstrip("/")
        self.api_key = os.environ.get("ZETARIS_API_KEY", "")
        self.rest_mode = os.environ.get("ZETARIS_REST_MODE", "open_sql_query").strip().lower()
        self.timeout = 8

    def probe(self) -> SponsorCall:
        if self.sample_mode:
            return SponsorCall(
                provider="zetaris",
                engine="catalog-cache",
                outcome=SponsorOutcome.SAMPLE_CACHE,
                detail="SAMPLE_MODE uses labelled local catalog; not a live Zetaris receipt",
            )
        if not self.rest_url:
            return SponsorCall(
                provider="zetaris",
                engine="rest",
                outcome=SponsorOutcome.NOT_CONFIGURED,
                detail="ZETARIS_REST_URL empty",
            )
        url = self.rest_url
        try:
            req = urllib.request.Request(url, method="GET")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return SponsorCall(
                    provider="zetaris",
                    engine="rest",
                    outcome=SponsorOutcome.UNIT_CONTRACT_ONLY,
                    detail=f"GET {url} HTTP {resp.status}: connectivity only; NOT source-query evidence",
                    contract_label="REST_HEALTH_ONLY",
                )
        except urllib.error.HTTPError as exc:
            return SponsorCall(
                provider="zetaris",
                engine="rest",
                outcome=SponsorOutcome.UNAVAILABLE,
                detail=f"HTTP {exc.code} for {url}",
            )
        except Exception as exc:
            return SponsorCall(
                provider="zetaris",
                engine="rest",
                outcome=SponsorOutcome.UNAVAILABLE,
                detail=f"{type(exc).__name__}: {exc}",
            )

    def fetch_two_logical_sources(self) -> tuple[list[SourceRecord], list[SponsorCall]]:
        """Return usable data from BOTH logical sources or fail closed.

        SAMPLE_MODE is an explicit offline fixture. In live mode, SQL success
        requires actual decoded decision rows: SELECT 1, health probes, and
        stale cached catalogs cannot count as successful data integration.
        """
        if self.sample_mode:
            catalog = all_catalog()
            public = [r for r in catalog if r.record_kind != RecordKind.SYNTHETIC_CAPACITY]
            synthetic = [r for r in catalog if r.record_kind == RecordKind.SYNTHETIC_CAPACITY]
            return catalog, [
                SponsorCall("zetaris", "cached-government-news", SponsorOutcome.SAMPLE_CACHE,
                            "OFFLINE fixture; NOT queried via Zetaris", row_count=len(public)),
                SponsorCall("zetaris", "cached-synthetic-capacity", SponsorOutcome.SAMPLE_CACHE,
                            "OFFLINE fixture; NOT queried via Zetaris", row_count=len(synthetic)),
            ]

        if self.rest_mode not in {"sql_editor", "open_sql_query"}:
            return [], [SponsorCall(
                "zetaris", "two-source-sql", SponsorOutcome.NOT_CONFIGURED,
                "Unsupported ZETARIS_REST_MODE; no HTTP attempted",
            )]
        if self.rest_mode != "sql_editor" and not os.environ.get("ZETARIS_QUERY_URL", "").strip():
            return [], [
                SponsorCall("zetaris", "two-source-sql", SponsorOutcome.NOT_CONFIGURED,
                            "ZETARIS_QUERY_URL must be copied from the organizer's actual "
                            "OpenSqlQuery endpoint; never guess an API path or use cache")
            ]
        results: list[list[SourceRecord]] = []
        calls: list[SponsorCall] = []
        queries = (
            ("government-news", RecordKind.GOVERNMENT_NEWS, "ZETARIS_PUBLIC_SQL"),
            ("synthetic-capacity", RecordKind.SYNTHETIC_CAPACITY, "ZETARIS_CAPACITY_SQL"),
        )
        for label, expected_kind, key in queries:
            sql = os.environ.get(key, "").strip()
            if not self._read_only_select(sql):
                results.append([])
                calls.append(SponsorCall(
                    provider="zetaris", engine=f"query:{label}",
                    outcome=SponsorOutcome.NOT_CONFIGURED,
                    detail=f"{key} must contain a read-only SELECT against a real source table",
                    contract_label="LIVE_QUERY_NOT_CONFIGURED",
                ))
                continue
            rows, call = self._query_rows(sql, label, expected_kind)
            results.append(rows)
            calls.append(call)

        if any(call.outcome != SponsorOutcome.REAL_SUCCESS for call in calls):
            calls.append(SponsorCall(
                provider="zetaris", engine="decision-path", outcome=SponsorOutcome.BLOCKED,
                detail="One or more real source queries failed; fail-closed EMPTY data; "
                       "no sample fallback or sponsor PASS",
                contract_label="LIVE_TWO_SOURCE_INCOMPLETE",
            ))
            return [], calls
        records = results[0] + results[1]
        ids = [row.source_id for row in records]
        if len(ids) != len(set(ids)):
            calls.append(SponsorCall(
                provider="zetaris", engine="decision-path", outcome=SponsorOutcome.BLOCKED,
                detail="Source IDs collide across live query results; fail closed",
            ))
            return [], calls
        calls.append(SponsorCall(
            provider="zetaris", engine="decision-path", outcome=SponsorOutcome.REAL_SUCCESS,
            detail="Both independent SELECT responses decoded and CONSUMED as decision input; "
                   "verify server-side query logs separately",
            row_count=len(records),
            contract_label="TWO_LIVE_QUERY_DATASETS_CONSUMED",
        ))
        return records, calls

    @staticmethod
    def _read_only_select(sql: str) -> bool:
        clean = sql.strip().lower()
        # Explicitly reject SQL scripts, comments and side-effecting statements.
        return bool(re.match(r"^select\b", clean)) and bool(re.search(r"\bfrom\b", clean)) and not any(
            marker in clean for marker in (
                ";", "--", "/*", "*/", " insert ", " update ", " delete ",
                " drop ", " alter ", " create ", " into ", " execute ",
                " pg_sleep(", " load_file(",
            )
        )

    @staticmethod
    def _list_value(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).lower() for item in value]
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                data = json.loads(value)
                if not isinstance(data, list):
                    raise ValueError("expected a JSON list")
                return [str(item).lower() for item in data]
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        raise ValueError("a list field must contain an array or JSON array string")

    @staticmethod
    def _object_value(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
        raise ValueError("object column must contain a JSON object")

    @classmethod
    def _decode_rows(cls, raw: bytes, expected_kind: RecordKind) -> list[SourceRecord]:
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, dict) and ("error" in payload or payload.get("success") is False):
            raise ValueError("Zetaris returned an application error, not result rows")
        rows = payload
        if isinstance(payload, dict):
            rows = payload.get("rows", payload.get("data", payload.get("result")))
        if isinstance(rows, dict):
            rows = rows.get("rows", rows.get("data"))
        if not isinstance(rows, list):
            raise ValueError("unrecognized Zetaris result shape; expected rows or data array")
        if not rows:
            raise ValueError("source query returned zero rows")
        if len(rows) > 100:
            raise ValueError("source query returned >100 rows; narrow the configured SELECT")

        decoded: list[SourceRecord] = []
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                raise ValueError("query rows must be JSON objects")
            row = raw_row
            if isinstance(row.get("record_json"), str):
                row = json.loads(row["record_json"])
            if not isinstance(row, dict):
                raise ValueError("record_json must decode to a JSON object")
            required = (
                "record_kind", "source_id", "excerpt", "locator", "paraphrase",
                "provenance_quality", "historical_admin_vintage", "spatial_scope",
                "named_districts_2024", "granularity",
            )
            missing = [field for field in required if field not in row]
            if missing:
                raise ValueError(
                    "Zetaris source row missing required field(s): "
                    + ", ".join(missing)
                )
            kind = RecordKind(row["record_kind"])
            if kind != expected_kind:
                raise ValueError(f"source kind {kind.value} not allowed in {expected_kind.value} SELECT")
            source_id = str(row["source_id"])
            excerpt = str(row["excerpt"])
            if not source_id or not excerpt or not row.get("locator"):
                raise ValueError("source_id, excerpt and locator are mandatory")
            actual_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
            if row.get("excerpt_sha256") and row["excerpt_sha256"] != actual_hash:
                raise ValueError(f"SQL excerpt hash mismatch for {source_id}")

            provenance = ProvenanceQuality(row["provenance_quality"])
            if kind == RecordKind.GOVERNMENT_NEWS:
                if provenance == ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT:
                    raise ValueError("SQL record cannot self-attest an immutable 2024 snapshot")
                if provenance == ProvenanceQuality.SYNTHETIC:
                    raise ValueError("public warning cannot be labelled synthetic")
            elif provenance != ProvenanceQuality.SYNTHETIC:
                raise ValueError("capacity dataset must be explicitly SYNTHETIC")

            decoded.append(SourceRecord(
                source_id=source_id,
                record_kind=kind,
                locator=str(row["locator"]),
                publisher=str(row.get("publisher") or "unknown"),
                paraphrase=str(row["paraphrase"]),
                excerpt=excerpt,
                excerpt_sha256=actual_hash,
                published_at_displayed_utc=parse_iso(row.get("published_at_displayed_utc")),
                observed_at_utc=parse_iso(row.get("observed_at_utc")),
                issued_at_claimed_utc=parse_iso(row.get("issued_at_claimed_utc")),
                # An unaudited SQL field is NOT independent proof of original 2024 bytes.
                first_availability_proven_utc=(
                    parse_iso(row.get("first_availability_proven_utc"))
                    if kind == RecordKind.SYNTHETIC_CAPACITY else None
                ),
                retrieved_at_utc=utc_now(),
                provenance_quality=provenance,
                historical_admin_vintage=str(row["historical_admin_vintage"]),
                spatial_scope=cls._list_value(row["spatial_scope"]),
                named_districts_2024=cls._list_value(row["named_districts_2024"]),
                granularity=str(row["granularity"]),
                scenario_id=row.get("scenario_id"),
                plan_predicates=cls._object_value(row.get("plan_predicates") or {}),
                metadata_conflicts=cls._list_value(row.get("metadata_conflicts") or []),
                observation_fields=cls._object_value(row.get("observation_fields") or {}),
            ))
        return decoded

    def _query_rows(
        self, sql: str, label: str, kind: RecordKind
    ) -> tuple[list[SourceRecord], SponsorCall]:
        if self.rest_mode == "sql_editor":
            from evidencetrail.adapters.zetaris_sql_editor import (
                query_rows, SqlEditorContractError,
            )
            try:
                raw_rows, request_id, digest = query_rows(
                    sql, kind,
                    base_url=self.rest_url,
                    org_id=os.environ.get("ZETARIS_ORG_ID", ""),
                    api_key=self.api_key,
                    timeout=max(18, self.timeout),
                )
                decoded = self._decode_rows(
                    json.dumps({"rows": raw_rows}).encode("utf-8"), kind
                )
                return decoded, SponsorCall(
                    provider="zetaris",
                    engine=f"query:{label}",
                    outcome=SponsorOutcome.REAL_SUCCESS,
                    detail=(
                        f"LOCAL_ZETARIS_SQL_EDITOR HTTP 200, SQL SHA12 {digest}, "
                        f"{len(decoded)} verified source rows consumed; "
                        "2026-curated government summaries are NOT "
                        "authenticated immutable 2024 archival evidence"
                    ),
                    invocation_id=request_id,
                    row_count=len(decoded),
                    contract_label="LOCAL_SQL_EDITOR_TWO_SOURCE_DATA",
                )
            except SqlEditorContractError as exc:
                code = str(exc)
                outcome = (
                    SponsorOutcome.NOT_CONFIGURED
                    if code in {
                        "LOCAL_SQL_EDITOR_API_BASE_REQUIRED",
                        "ORG_ID_NUMERIC_REQUIRED", "API_KEY_MISSING",
                        "SOURCE_SQL_NOT_ALLOWLISTED",
                    }
                    else SponsorOutcome.UNAUTHORIZED
                    if code == "REST_UNAUTHORIZED" else SponsorOutcome.UNAVAILABLE
                )
                return [], SponsorCall(
                    "zetaris", f"query:{label}", outcome,
                    f"SQL_EDITOR_CONTRACT: {code}; no source data admitted",
                    contract_label="LOCAL_SQL_EDITOR_NOT_ACCEPTED",
                )
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                return [], SponsorCall(
                    "zetaris", f"query:{label}", SponsorOutcome.BLOCKED,
                    f"SQL_EDITOR_DECODING_{type(exc).__name__}: invalid source rows",
                    contract_label="LOCAL_SQL_EDITOR_ROW_REJECTED",
                )

        # Official Zetaris REST API OpenSqlQuery collection uses "select"
        # and "pageLimit", NOT the earlier unverified {"sql": ...} payload.
        # Exact endpoint path is deployment-specific: require an owner-supplied
        # organizer-approved full URL instead of inventing /query.
        url = os.environ.get("ZETARIS_QUERY_URL", "").strip()
        if not url.startswith(("https://", "http://")):
            return [], SponsorCall(
                "zetaris", f"query:{label}", SponsorOutcome.NOT_CONFIGURED,
                "Missing/invalid ZETARIS_QUERY_URL (HTTP(S) OpenSqlQuery path required)",
                contract_label="QUERY_ENDPOINT_NOT_VERIFIED",
            )
        request_body = json.dumps({"select": sql, "pageLimit": 100}).encode("utf-8")
        sql_digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]
        try:
            req = urllib.request.Request(url, data=request_body, method="POST")
            req.add_header("Content-Type", "application/json")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # Bounded read: no unlimited response body or secret logging.
                raw = resp.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise ValueError("Zetaris response exceeded 1 MiB")
                rows = self._decode_rows(raw, kind)
                request_id = resp.headers.get("X-Request-ID")
                return rows, SponsorCall(
                    provider="zetaris", engine=f"query:{label}",
                    outcome=SponsorOutcome.REAL_SUCCESS,
                    detail=f"HTTP {resp.status}, SQL SHA12 {sql_digest}, "
                           f"{len(rows)} decoded rows used (not SELECT 1)",
                    invocation_id=request_id,
                    row_count=len(rows),
                    contract_label="LIVE_SQL_ROWS_CONSUMED",
                )
        except urllib.error.HTTPError as exc:
            outcome = SponsorOutcome.UNAUTHORIZED if exc.code in (401, 403) else SponsorOutcome.UNAVAILABLE
            detail = f"HTTP {exc.code} for {label}; no source rows admitted"
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
            outcome = SponsorOutcome.UNAVAILABLE
            detail = f"query:{label} {type(exc).__name__}: {exc}"
        return [], SponsorCall(
            provider="zetaris", engine=f"query:{label}",
            outcome=outcome, detail=detail, contract_label="LIVE_QUERY_FAILED",
        )


    def fetch_targeted_sources(self) -> tuple[list[SourceRecord], SponsorCall]:
        """A separately configured live SQL query for auditor-requested evidence.

        Caller must reapply time, mission and jurisdiction filters; absence of
        a source is NOT proof that a requery succeeded.
        """
        if self.sample_mode:
            return [], SponsorCall(
                "zetaris", "targeted-requery", SponsorOutcome.SKIPPED,
                "SAMPLE_MODE has no external targeted query; cache is not new evidence",
            )
        sql = os.environ.get("ZETARIS_TARGETED_PUBLIC_SQL", "").strip()
        if (self.rest_mode != "sql_editor" and not os.environ.get("ZETARIS_QUERY_URL", "").strip()) or not self._read_only_select(sql):
            return [], SponsorCall(
                "zetaris", "targeted-requery", SponsorOutcome.NOT_CONFIGURED,
                "ZETARIS_TARGETED_PUBLIC_SQL must be a real read-only SELECT",
            )
        return self._query_rows(sql, "targeted-government-news", RecordKind.GOVERNMENT_NEWS)
