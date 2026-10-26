"""No-network tests for NVIDIA one-shot preflight and owner consent gates."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nvidia_nim import MODEL
from evidencetrail.models import Verdict
from run_nvidia_nemotron_preflight import main, public_sample_case


class NvidiaOwnerGatedPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private-receipt.json"
        self.env_path = Path(self.temp.name) / "unavailable.env.local"

    def opts(self, *argv):
        return [*argv, "--env-file", str(self.env_path),
                "--receipt", str(self.path)]

    def read(self):
        return json.loads(self.path.read_text("utf-8"))

    def test_offline_check_missing_key_never_calls_network(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "evidencetrail.adapters.nvidia_nim._real_transport",
            side_effect=AssertionError("no Nvidia connection approved"),
        ):
            ret = main(self.opts("--check"))
        self.assertEqual(ret, 0)
        obj = self.read()
        self.assertEqual(obj["status"], "BLOCKED_NVIDIA_API_KEY_MISSING")
        self.assertFalse(obj["network_called"])
        self.assertFalse(obj["organizer_eligibility_confirmed"])
        self.assertFalse(obj["nvidia_api_key_present"])

    def test_key_present_check_still_never_sends(self):
        with patch.dict(os.environ, {
            "NVIDIA_API_KEY": "nvapi-SYNTHETIC-TEST-NOT-REAL-KEY"
        }, clear=True), patch(
            "evidencetrail.adapters.nvidia_nim._real_transport",
            side_effect=AssertionError("no external call on --check"),
        ):
            ret = main(self.opts("--check"))
        self.assertEqual(ret, 0)
        obj = self.read()
        self.assertTrue(obj["nvidia_api_key_present"])
        self.assertFalse(obj["network_called"])
        self.assertNotIn("nvapi-", self.path.read_text("utf-8"))
        self.assertNotIn("SYNTHETIC-TEST", self.path.read_text("utf-8"))
        self.assertEqual(obj["requested_model"], MODEL)

    def test_live_with_no_key_is_blocked_before_transport(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "evidencetrail.adapters.nvidia_nim._real_transport",
            side_effect=AssertionError("NVIDIA API unavailable"),
        ):
            ret = main(self.opts(
                "--live", "--confirm-public-research-egress",
                "--confirm-free-developer-endpoint",
            ))
        self.assertEqual(ret, 2)
        obj = self.read()
        self.assertEqual(obj["status"], "BLOCKED_MISSING_OWNER_CONSENT_OR_KEY")
        self.assertFalse(obj["network_called"])

    def test_live_key_but_one_acknowledgement_missing_is_blocked(self):
        key = {"NVIDIA_API_KEY": "nvapi-SYNTHETIC-TEST-NOT-REAL-KEY"}
        for provided in ("--confirm-public-research-egress",
                         "--confirm-free-developer-endpoint"):
            with self.subTest(provided=provided):
                with patch.dict(os.environ, key, clear=True), patch(
                    "evidencetrail.adapters.nvidia_nim._real_transport",
                    side_effect=AssertionError("not approved"),
                ):
                    ret = main(self.opts("--live", provided))
                self.assertEqual(ret, 2)
                self.assertFalse(self.read()["network_called"])

    def test_public_sample_marks_fictional_scenario_not_live_zetaris(self):
        req, sources = public_sample_case()
        self.assertFalse(req.sample_mode)
        self.assertEqual(req.mode.value, "REPORTED_DATELINE_REPLAY")
        self.assertIn("GOV-2024-09-08-1637", [s.source_id for s in sources])
        self.assertTrue(any(s.record_kind.value == "SYNTHETIC_CAPACITY"
                            for s in sources))
        self.assertFalse(any(s.first_availability_proven_utc is not None
                             and s.record_kind.value == "GOVERNMENT_NEWS"
                             for s in sources))


if __name__ == "__main__":
    unittest.main()
