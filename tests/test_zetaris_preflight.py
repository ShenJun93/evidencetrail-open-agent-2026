"""Zetaris preflight unit contracts. No network, no hackathon credentials."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_zetaris_preflight as preflight
from evidencetrail.catalog import all_catalog
from evidencetrail.models import SponsorCall, SponsorOutcome


def safe_configuration():
    return {
        "ZETARIS_QUERY_URL": "https://zetaris-unit.example.org/rest/DBQuery/OpenSqlQuery",
        "ZETARIS_API_KEY": "unit-fake-token-not-an-actual-credential",
        "ZETARIS_PUBLIC_SQL": "SELECT * FROM government_bulletins",
        "ZETARIS_CAPACITY_SQL": "SELECT * FROM synthetic_capacity",
    }


class ZetarisSafeReadinessTests(unittest.TestCase):
    def test_missing_configuration_is_blocked_without_network(self):
        with patch.object(preflight.ZetarisAdapter, "fetch_two_logical_sources",
                          side_effect=AssertionError("network must not execute")):
            report, status = preflight.run({}, False, False, False)
        self.assertEqual(status, 2)
        self.assertEqual(report["result"], "BLOCKED_CONFIGURATION")
        self.assertFalse(report["network_called"])
        self.assertFalse(report["instance_identity_independently_verified"])

    def test_check_only_never_queries_a_configured_endpoint(self):
        with patch.object(preflight.ZetarisAdapter, "fetch_two_logical_sources",
                          side_effect=AssertionError("network must not execute")):
            report, code = preflight.run(safe_configuration(), False, False, False)
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "READY_TO_TEST_NOT_YET_QUERIED")
        self.assertFalse(report["network_called"])
        self.assertNotIn("unit-fake-token", json.dumps(report))
        self.assertNotIn("zetaris-unit.example.org", json.dumps(report))

    def test_remote_plain_http_and_userinfo_urls_are_rejected(self):
        base = safe_configuration()
        for url in (
            "http://remote.example.org/DBQuery/OpenSqlQuery",
            "https://user:password@remote.example.org/DBQuery/OpenSqlQuery",
            "https://remote.example.org/DBQuery/OpenSqlQuery?bearer=SECRET",
            "file:///C:/secret/response.json",
        ):
            bad = {**base, "ZETARIS_QUERY_URL": url}
            report = preflight.validate_config(bad)
            self.assertEqual(report["status"], "BLOCKED_NOT_CONFIGURED", url)
            self.assertNotIn("SECRET", json.dumps(report))
            self.assertNotIn("password", json.dumps(report))

    def test_loopback_http_requires_explicit_opt_in(self):
        base = safe_configuration()
        base["ZETARIS_QUERY_URL"] = "http://127.0.0.1:8888/DBQuery/OpenSqlQuery"
        self.assertEqual(preflight.validate_config(base)["status"], "BLOCKED_NOT_CONFIGURED")
        self.assertEqual(
            preflight.validate_config(base, allow_loopback=True)["status"],
            "READY_FOR_EXPLICIT_LIVE_ATTEMPT",
        )

    def test_queries_must_have_distinct_read_only_from_tables(self):
        base = safe_configuration()
        base["ZETARIS_CAPACITY_SQL"] = "SELECT * FROM government_bulletins"
        self.assertIn(
            "public_and_synthetic_must_read_distinct_tables",
            preflight.validate_config(base)["issues"],
        )
        base["ZETARIS_CAPACITY_SQL"] = "DELETE FROM synthetic_capacity"
        self.assertEqual(preflight.validate_config(base)["status"], "BLOCKED_NOT_CONFIGURED")
        base["ZETARIS_CAPACITY_SQL"] = "SELECT * FROM synthetic_capacity"
        self.assertEqual(preflight.validate_config(base)["status"], "READY_FOR_EXPLICIT_LIVE_ATTEMPT")

    def test_live_requires_explicit_sponsor_access_acknowledgement(self):
        with patch.object(preflight.ZetarisAdapter, "fetch_two_logical_sources",
                          side_effect=AssertionError("network must not execute")):
            report, code = preflight.run(safe_configuration(), True, False, False)
        self.assertEqual(code, 2)
        self.assertEqual(report["result"], "BLOCKED_EVENT_ACCESS_NOT_CONFIRMED")
        self.assertFalse(report["network_called"])

    def test_fake_two_source_http_still_has_unverified_instance_origin(self):
        calls = [
            SponsorCall("zetaris", "query:government-news", SponsorOutcome.REAL_SUCCESS,
                        "UNIT_FAKE", row_count=4),
            SponsorCall("zetaris", "query:synthetic-capacity", SponsorOutcome.REAL_SUCCESS,
                        "UNIT_FAKE", row_count=1),
            SponsorCall("zetaris", "decision-path", SponsorOutcome.REAL_SUCCESS,
                        "UNIT_FAKE", row_count=5),
        ]
        with patch.object(preflight.ZetarisAdapter, "fetch_two_logical_sources",
                          return_value=(all_catalog(), calls)):
            report, code = preflight.run(safe_configuration(), True, False, True)
        self.assertEqual(code, 0)
        self.assertEqual(report["sponsor_eligibility"], "NOT_VERIFIED")
        self.assertFalse(report["instance_identity_independently_verified"])
        result = report["computed_replays_without_memory_or_model"]
        self.assertEqual(result["yagi_1630_lucyen"]["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["yagi_1645_lucyen"]["verdict"], "WARN")
        self.assertNotIn("unit-fake-token", json.dumps(report))

    def test_exactly_full_page_fails_until_pagination_verified(self):
        calls = [
            SponsorCall("zetaris", "query:government-news", SponsorOutcome.REAL_SUCCESS,
                        "UNIT_FAKE", row_count=100),
            SponsorCall("zetaris", "query:synthetic-capacity", SponsorOutcome.REAL_SUCCESS,
                        "UNIT_FAKE", row_count=1),
        ]
        with patch.object(preflight.ZetarisAdapter, "fetch_two_logical_sources",
                          return_value=(all_catalog(), calls)):
            report, code = preflight.run(safe_configuration(), True, False, True)
        self.assertEqual(code, 1)
        self.assertEqual(report["pagination_limit"], "100_ROWS_PAGINATION_NOT_VERIFIED")

    def test_dotenv_requires_explicit_local_project_path_and_filters_keys(self):
        with tempfile.TemporaryDirectory() as td:
            localroot = Path(td)
            (localroot / ".env.local").write_text(
                "ZETARIS_API_KEY=private-unit-test-value\n"
                "DANGEROUS_KEY=do-not-load\n"
                "ZETARIS_QUERY_URL=https://example.org/api/DBQuery/OpenSqlQuery\n",
                encoding="utf-8",
            )
            with patch.object(preflight, "ROOT", localroot):
                cfg = preflight.read_local_env(".env.local")
                self.assertEqual(cfg["ZETARIS_API_KEY"], "private-unit-test-value")
                self.assertNotIn("DANGEROUS_KEY", cfg)
                with self.assertRaises(ValueError):
                    preflight.read_local_env("../external.env")
