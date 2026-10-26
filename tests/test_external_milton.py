"""Reproducible cross-event NOAA issued-time and API guardrail tests.

The official bulletin metadata is hand-checked from NHC pages, not independent
human evaluation and not authenticated original 2024 archive bytes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from evidencetrail.api import DEMO_HTML, create_local_server
from evidencetrail.external_milton import (
    _load, run_external_chronology_checks, run_milton_external_replay,
)
from evidencetrail.pipeline import EvidenceTrailPipeline


class ExternalNoaaSourceTests(unittest.TestCase):
    def test_eight_issuer_clock_checks_from_official_milton_pages(self):
        report = run_external_chronology_checks()
        self.assertEqual(report["case_count"], 8)
        self.assertEqual(report["passed"], 8)
        self.assertTrue(report["all_pass"])
        self.assertTrue(report["strict_abstains_without_authenticated_first_availability"])
        self.assertFalse(report["external_user_validation_or_prediction_accuracy"])
        self.assertFalse(report["sponsor_inference_called"])

    def test_pre_advisory_9_uses_100_not_future_155(self):
        report = run_milton_external_replay("2024-10-07T11:00:00Z")
        self.assertEqual(report["latest_selected_reported_wind_mph"], 100)
        self.assertEqual(report["unsafe_full_archive_peak_mph"], 155)
        self.assertEqual(report["source_ids_selected"], ["NHC-AL142024-PUBLIC-008"])
        self.assertEqual(len(report["excluded"]), 3)
        self.assertFalse(report["published_first_availability_authenticated"])
        self.assertFalse(report["yagi_disaster_rule_verdict_computed"])

    def test_special_advisory_9_becomes_eligible_at_1200_exactly(self):
        before = run_milton_external_replay("2024-10-07T11:59:00Z")
        at = run_milton_external_replay("2024-10-07T12:00:00Z")
        self.assertEqual(before["latest_selected_reported_wind_mph"], 100)
        self.assertEqual(at["latest_selected_reported_wind_mph"], 125)
        self.assertEqual(at["latest_selected_issued_advisory_id"], "NHC-AL142024-PUBLIC-009")

    def test_strict_abstains_even_after_official_issuance(self):
        for stamp in ("2024-10-07T09:00:00Z", "2024-10-10T21:00:00Z"):
            with self.subTest(clock=stamp):
                out = run_milton_external_replay(stamp, strict=True)
                self.assertIsNone(out["latest_selected_reported_wind_mph"])
                self.assertEqual(out["source_ids_selected"], [])
                self.assertEqual(out["result"], "NO_ADMISSIBLE_ARCHIVED_ISSUE_IN_SELECTED_SET")

    def test_cannot_launder_future_10_with_new_id_reused_locator(self):
        _, catalog = _load()
        ten = next(x for x in catalog if x.source_id.endswith("010"))
        fake = replace(
            ten, source_id="NHC-AL142024-PUBLIC-MIRROR",
            published_at_displayed_utc=ten.published_at_displayed_utc-timedelta(hours=5),
        )
        report = run_milton_external_replay(
            "2024-10-07T11:00:00Z", catalog_override=catalog + [fake])
        self.assertEqual(report["result"], "REFUSED_AMBIGUOUS_SOURCE_SET")
        self.assertEqual(report["source_ids_selected"], [])
        self.assertIn("SOURCE_LOCATOR_ALIAS_REFUSED", {x["code"] for x in report["integrity_issues"]})

    def test_cannot_forge_excerpt_under_existing_sha(self):
        _, catalog = _load()
        ten = next(x for x in catalog if x.source_id.endswith("010"))
        fake = replace(ten, excerpt="Fictitious text without matching actual SHA-256")
        out = run_milton_external_replay(
            "2024-10-07T16:00:00Z",
            catalog_override=[fake if x.source_id == ten.source_id else x for x in catalog])
        self.assertEqual(out["result"], "REFUSED_AMBIGUOUS_SOURCE_SET")
        self.assertIn("SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED",
                      {x["code"] for x in out["integrity_issues"]})

    def test_bad_asof_and_boolean_inputs_refused(self):
        for value in ("2024-10-06T23:59:00Z", "2024-10-11T00:01:00Z",
                      "2024-10-07T12:00:00", "not-a-time"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_milton_external_replay(value)
        with self.assertRaisesRegex(ValueError, "STRICT_BOOLEAN_REQUIRED"):
            run_milton_external_replay(strict="false")

    def test_selected_source_claim_does_not_fake_a_raw_bytes_attestation(self):
        metadata, rows = _load()
        self.assertEqual(metadata["source_organization"], "NOAA / National Hurricane Center")
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(x.first_availability_proven_utc is None for x in rows))
        self.assertTrue(all(x.locator.startswith(
            "https://www.nhc.noaa.gov/archive/2024/") for x in rows))
        self.assertFalse(metadata["original_2024_first_publication_authenticated"])

    def test_no_sponsor_or_hmem_called(self):
        with patch("evidencetrail.adapters.zetaris.ZetarisAdapter.fetch_two_logical_sources",
                   side_effect=AssertionError("no real SQL permitted")), patch(
             "evidencetrail.adapters.meterless.MeterlessRuntimeProvider.chat",
                   side_effect=AssertionError("no model permitted")), patch(
             "evidencetrail.adapters.hmem.HMemAdapter.query",
                   side_effect=AssertionError("no memory permitted")):
            out = run_milton_external_replay("2024-10-07T11:00:00Z")
        self.assertFalse(out["model_or_sponsor_called"])


class ExternalNoaaHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pipeline = EvidenceTrailPipeline(
            sample_mode=True,
            log_dir=Path(self.tmp.name)/"logs",
            persist_dir=Path(self.tmp.name)/"mem",
        )
        self.server = create_local_server("127.0.0.1", 0, pipeline=pipeline)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, payload):
        req=Request(
            f"http://127.0.0.1:{self.server.server_port}/external-milton",
            data=json.dumps(payload).encode("utf8"),method="POST",
            headers={"Content-Type":"application/json"},
        )
        try:
            with urlopen(req, timeout=9) as resp:
                return resp.status, json.loads(resp.read().decode("utf8"))
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read().decode("utf8"))

    def test_real_local_http_milton_replay_and_strict_abstention(self):
        code, data = self.post({"as_of_utc":"2024-10-07T11:00:00Z"})
        self.assertEqual(code,200)
        self.assertEqual(data["latest_selected_reported_wind_mph"],100)
        self.assertFalse(data["model_or_sponsor_called"])
        strict_code, strict_data = self.post({
            "as_of_utc":"2024-10-07T11:00:00Z","strict":True})
        self.assertEqual(strict_code,200)
        self.assertIsNone(strict_data["latest_selected_reported_wind_mph"])
        self.assertEqual(
            list((Path(self.tmp.name)/"logs").glob("run-*.json")), [])

    def test_browser_cannot_inject_external_sources_or_network_mode(self):
        for payload in (
            {"as_of_utc":"2024-10-07T11:00:00Z","sample_mode":False},
            {"as_of_utc":"2024-10-07T11:00:00Z","catalog":[{"claim":"fake"}]},
            {"as_of_utc":"2024-10-07T11:00:00Z","strict":"False"},
        ):
            with self.subTest(payload=payload):
                code, data=self.post(payload)
                self.assertEqual(code,400)
                self.assertEqual(data["error"],"invalid_request")

    def test_real_ui_has_clickable_external_case_and_safe_rendering(self):
        html=DEMO_HTML.read_text(encoding="utf8")
        self.assertIn('id="miltonRun"',html)
        self.assertIn('id="miltonClock"',html)
        self.assertIn('id="miltonPolicy"',html)
        self.assertIn('fetch("/external-milton"',html)
        self.assertIn("published_first_availability_authenticated!==false",html)
        self.assertIn("No network calls to NOAA",html)
        self.assertNotIn("innerHTML",html)
