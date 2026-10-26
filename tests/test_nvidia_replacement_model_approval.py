"""New model-specific owner-consent gate: NO external HTTP requests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nvidia_nim import MODEL, gates
from run_nvidia_nemotron_preflight import main

KEY = "nvapi-DUMMY-LOCAL-UNIT-FIXTURE"


class Nemotron35OwnerConsentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receipt = Path(self.temp.name) / "receipt.json"
        self.envfile = Path(self.temp.name) / "nonexistent.env.local"

    def run_preflight(self, *args):
        return main([*args, "--env-file", str(self.envfile),
                     "--receipt", str(self.receipt)])

    def receipt_data(self):
        return json.loads(self.receipt.read_text(encoding="utf8"))

    def test_offline_readiness_remains_network_free_even_with_key(self):
        with patch.dict(os.environ, {"NVIDIA_API_KEY": KEY}, clear=True), patch(
            "evidencetrail.adapters.nvidia_nim._real_transport",
            side_effect=AssertionError("offline check network forbidden"),
        ):
            code = self.run_preflight("--check")
        self.assertEqual(code, 0)
        data = self.receipt_data()
        self.assertEqual(MODEL, "nvidia/nemotron-3.5-super-vl-120b-a12b")
        self.assertEqual(data["requested_model"], MODEL)
        self.assertEqual(data["status"], "OWNER_KEY_PRESENT_NEW_MODEL_APPROVAL_REQUIRED")
        self.assertFalse(data["network_called"])
        self.assertFalse(data["replacement_model_approval_for_this_call"])
        self.assertNotIn(KEY, self.receipt.read_text(encoding="utf8"))

    def test_old_two_cli_acknowledgements_must_not_trigger_new_model(self):
        with patch.dict(os.environ, {"NVIDIA_API_KEY": KEY}, clear=True), patch(
            "evidencetrail.adapters.nvidia_nim._real_transport",
            side_effect=AssertionError("old approval must not connect"),
        ):
            code = self.run_preflight(
                "--live", "--confirm-public-research-egress",
                "--confirm-free-developer-endpoint",
            )
        self.assertEqual(code, 2)
        data = self.receipt_data()
        self.assertEqual(data["status"], "BLOCKED_NEW_MODEL_CONSENT_REQUIRED")
        self.assertFalse(data["network_called"])
        self.assertFalse(data["replacement_model_approval_for_this_call"])
        self.assertFalse(data["organizer_eligibility_confirmed"])

    def test_model_approval_only_in_environment_without_new_cli_flag_is_insufficient(self):
        env = {"NVIDIA_API_KEY": KEY,
               "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED": "true",
               "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
               "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT": "true"}
        with patch.dict(os.environ, env, clear=True), patch(
            "evidencetrail.adapters.nvidia_nim._real_transport",
            side_effect=AssertionError("explicit CLI approval required"),
        ):
            code = self.run_preflight(
                "--live", "--confirm-public-research-egress",
                "--confirm-free-developer-endpoint",
            )
        self.assertEqual(code, 2)
        self.assertFalse(self.receipt_data()["network_called"])
        self.assertFalse(self.receipt_data()["replacement_model_approval_for_this_call"])


if __name__ == "__main__":
    unittest.main()
