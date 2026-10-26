"""Offline contracts for official local Zetaris SQL Editor REST. No real HTTP.

The source CSVs are 2026 curated/public-dateline and SYNTHETIC, respectively.
Mocking transport is never acceptance of a real live sponsor API call.
"""
from __future__ import annotations

import csv
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import run_zetaris_preflight as preflight
from evidencetrail.adapters.zetaris import ZetarisAdapter
from evidencetrail.adapters.zetaris_sql_editor import (
    FIELDS, MAX_ROWS, ORIGIN_LABELS, SqlEditorContractError,
    NoRedirect, decode_payload, query_rows, source_sql, validate_config,
    validate_sql,
)
from evidencetrail.firewall import filter_sources
from evidencetrail.models import RecordKind, ReplayMode, SponsorOutcome

ROOT = Path(__file__).resolve().parents[1]


def source_csv(kind: RecordKind) -> list[dict[str, str]]:
    name = ("zetaris_evidencetrail_public_datelines.csv"
            if kind == RecordKind.GOVERNMENT_NEWS
            else "zetaris_evidencetrail_synthetic_capacity.csv")
    with (ROOT / "samples" / "inputs" / name).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or any(row.keys() != set(FIELDS) for row in rows):
        raise AssertionError("CSV missing one or more declared fields")
    return rows


def fake_api_payload(kind: RecordKind) -> bytes:
    rows = source_csv(kind)
    return json.dumps({
        "data": [[row[field] for field in FIELDS] for row in rows],
    }).encode("utf-8")


class FakeReply:
    status = 200
    headers = {}
    def __init__(self, content: bytes):
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self, count: int):
        return self.content[:count]


class FakeOpener:
    def __init__(self):
        self.requests = []
    def open(self, req, *, timeout):
        self.requests.append(req)
        body = json.loads(req.data)
        kind = (
            RecordKind.GOVERNMENT_NEWS
            if "public_datelines" in body["sql"]
            else RecordKind.SYNTHETIC_CAPACITY
        )
        return FakeReply(fake_api_payload(kind))


def local_config() -> dict[str, str]:
    return {
        "ZETARIS_REST_MODE": "sql_editor",
        "ZETARIS_REST_URL": "http://127.0.0.1:8888/api/v1.0",
        "ZETARIS_API_KEY": "FAKE_UNIT_TOKEN_DO_NOT_USE",
        "ZETARIS_ORG_ID": "1",
        "ZETARIS_PUBLIC_SQL": source_sql(RecordKind.GOVERNMENT_NEWS),
        "ZETARIS_CAPACITY_SQL": source_sql(RecordKind.SYNTHETIC_CAPACITY),
        "ZETARIS_QUERY_URL": "",
    }


class SqlEditorLocalSourceTests(unittest.TestCase):
    def test_audited_sql_exactly_targets_two_distinct_registered_tables(self):
        gov = source_sql(RecordKind.GOVERNMENT_NEWS)
        synth = source_sql(RecordKind.SYNTHETIC_CAPACITY)
        self.assertNotEqual(gov, synth)
        self.assertEqual(len(FIELDS), 20)
        self.assertIn("EVIDENCETRAIL_YAGI.public_datelines", gov)
        self.assertIn("EVIDENCETRAIL_YAGI.synthetic_capacity", synth)
        for kind, sql in ((RecordKind.GOVERNMENT_NEWS, gov),
                          (RecordKind.SYNTHETIC_CAPACITY, synth)):
            validate_sql(sql, kind)
        with self.assertRaises(SqlEditorContractError):
            validate_sql(gov + " UNION SELECT * FROM secrets", RecordKind.GOVERNMENT_NEWS)
        with self.assertRaises(SqlEditorContractError):
            validate_sql("SELECT 1", RecordKind.GOVERNMENT_NEWS)

    def test_real_csv_fixture_round_trip_preserves_json_and_sources(self):
        for kind, expected_rows in ((RecordKind.GOVERNMENT_NEWS, 3),
                                    (RecordKind.SYNTHETIC_CAPACITY, 1)):
            rows = decode_payload(fake_api_payload(kind), kind)
            self.assertEqual(len(rows), expected_rows)
            self.assertEqual(set(rows[0]), set(FIELDS) - {"source_origin_label"})
            self.assertIn("yen bai", rows[0]["spatial_scope"])
            if kind == RecordKind.SYNTHETIC_CAPACITY:
                self.assertIn("coordinator_watch_authorized", rows[0]["plan_predicates"])
            else:
                self.assertEqual(
                    rows[-1]["published_at_displayed_utc"], "2024-09-08T09:37:00Z"
                )

    def test_source_origin_cannot_claim_authenticated_2024_archival_bytes(self):
        row = source_csv(RecordKind.GOVERNMENT_NEWS)[0]
        row["provenance_quality"] = "AUTHENTICATED_2024_SNAPSHOT"
        with self.assertRaises(SqlEditorContractError):
            decode_payload(json.dumps({"data": [[row[k] for k in FIELDS]]}).encode(),
                           RecordKind.GOVERNMENT_NEWS)
        row["provenance_quality"] = (
            "ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN"
        )
        row["source_origin_label"] = "FAKE_2024_SNAPSHOT_VERIFIED"
        with self.assertRaises(SqlEditorContractError):
            decode_payload(json.dumps({"data": [[row[k] for k in FIELDS]]}).encode(),
                           RecordKind.GOVERNMENT_NEWS)

    def test_synthetic_uses_explicit_origin_and_kind(self):
        record = source_csv(RecordKind.SYNTHETIC_CAPACITY)[0]
        self.assertEqual(record["source_origin_label"],
                         ORIGIN_LABELS[RecordKind.SYNTHETIC_CAPACITY])
        record["source_origin_label"] = "REAL_HOSPITAL_CAPACITY"
        with self.assertRaises(SqlEditorContractError):
            decode_payload(json.dumps({"data": [[record[k] for k in FIELDS]]}).encode(),
                           RecordKind.SYNTHETIC_CAPACITY)

    def test_schema_mismatch_and_full_page_fail_closed(self):
        row = [source_csv(RecordKind.GOVERNMENT_NEWS)[0][key] for key in FIELDS]
        for rows in ([], [row[:-1]], [row] * MAX_ROWS, [{"source_id": "bad"}]):
            with self.assertRaises(SqlEditorContractError):
                decode_payload(json.dumps({"data": rows}).encode(),
                               RecordKind.GOVERNMENT_NEWS)
        with self.assertRaises(SqlEditorContractError):
            decode_payload(json.dumps({"error": "forbidden", "data": [row]}).encode(),
                           RecordKind.GOVERNMENT_NEWS)

    def test_api_http_request_matches_official_contract_without_leaking_token(self):
        fake = FakeOpener()
        rows, uuid, sha12 = query_rows(
            source_sql(RecordKind.GOVERNMENT_NEWS),
            RecordKind.GOVERNMENT_NEWS,
            base_url="http://127.0.0.1:8888/api/v1.0",
            org_id="1", api_key="FAKE_UNIT_TOKEN_DO_NOT_USE",
            opener=fake.open,
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(uuid), 36)
        self.assertEqual(len(sha12), 12)
        req = fake.requests[0]
        self.assertEqual(req.full_url,
                         "http://127.0.0.1:8888/api/v1.0/sql-editor/sqls/run")
        body = json.loads(req.data)
        self.assertEqual(body["source"], "SqlEditor")
        self.assertEqual(body["limit"], 20)
        self.assertEqual(body["sql"], source_sql(RecordKind.GOVERNMENT_NEWS))
        self.assertNotIn("select", body)
        self.assertEqual(req.get_header("X-org-id"), "1")
        self.assertTrue(req.get_header("X-request-id"))
        self.assertTrue(req.get_header("Authorization").startswith("Bearer "))

    def test_remote_and_missing_credentials_refused_before_transport(self):
        for url in (
            "https://fake.example.org/api/v1.0",
            "http://127.0.0.1:8888/other",
            "http://user:pass@127.0.0.1:8888/api/v1.0",
        ):
            with self.assertRaises(SqlEditorContractError):
                validate_config(url, "1", "FAKE_UNIT_TOKEN")
        with self.assertRaises(SqlEditorContractError):
            validate_config("http://127.0.0.1:8888/api/v1.0", "", "FAKE_UNIT_TOKEN")
        with self.assertRaises(SqlEditorContractError):
            validate_config("http://127.0.0.1:8888/api/v1.0", "1", "")

    def test_cross_origin_redirect_is_forbidden(self):
        with self.assertRaises(SqlEditorContractError):
            NoRedirect().redirect_request(None, None, 302, "redirect", {},
                                         "https://external.example/steal-token")

    def test_adapter_decodes_two_real_csv_source_shapes_using_fake_http(self):
        fake = FakeOpener()
        with patch.dict(os.environ, local_config()), patch(
            "evidencetrail.adapters.zetaris_sql_editor.urllib.request.build_opener",
            return_value=fake,
        ):
            adapter = ZetarisAdapter(sample_mode=False)
            records, calls = adapter.fetch_two_logical_sources()
        self.assertEqual(len(records), 4)
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(
            [call.outcome for call in calls],
            [SponsorOutcome.REAL_SUCCESS] * 3,
        )
        self.assertEqual(
            [call.contract_label for call in calls[:2]],
            ["LOCAL_SQL_EDITOR_TWO_SOURCE_DATA"] * 2,
        )
        # REST is faked in this unit test. LIVE sponsor acceptance is NOT proved.

    def test_redacted_preflight_checks_local_mode_offline(self):
        config = local_config()
        with patch("evidencetrail.adapters.zetaris_sql_editor.urllib.request.build_opener",
                   side_effect=AssertionError("No network allowed for --check")):
            result = preflight.validate_config(config, allow_loopback=True)
        self.assertEqual(result["status"], "READY_FOR_EXPLICIT_LIVE_ATTEMPT")
        self.assertEqual(result["rest_mode"], "sql_editor")
        self.assertNotIn("FAKE_UNIT_TOKEN", json.dumps(result))
        self.assertNotIn("127.0.0.1", json.dumps(result))
        self.assertEqual(
            preflight.validate_config(config, allow_loopback=False)["status"],
            "BLOCKED_NOT_CONFIGURED",
        )

    def test_1637_public_dateline_cannot_cross_1630_temporal_firewall(self):
        rows = decode_payload(fake_api_payload(RecordKind.GOVERNMENT_NEWS),
                              RecordKind.GOVERNMENT_NEWS)
        sources = ZetarisAdapter._decode_rows(
            json.dumps({"rows": rows}).encode(), RecordKind.GOVERNMENT_NEWS,
        )
        at_1630 = datetime(2024, 9, 8, 9, 30, tzinfo=timezone.utc)
        at_1645 = datetime(2024, 9, 8, 9, 45, tzinfo=timezone.utc)
        before, _ = filter_sources(sources, at_1630,
                                   ReplayMode.REPORTED_DATELINE_REPLAY)
        after, _ = filter_sources(sources, at_1645,
                                  ReplayMode.REPORTED_DATELINE_REPLAY)
        self.assertNotIn("GOV-2024-09-08-1637", [r.source_id for r in before])
        self.assertIn("GOV-2024-09-08-1637", [r.source_id for r in after])


if __name__ == "__main__":
    unittest.main()
