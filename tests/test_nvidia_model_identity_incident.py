"""Prevent false sponsor proof from publicly reported NVIDIA model-ID mismatch."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from evidencetrail.adapters.nvidia_nim import (
    ENDPOINT, MODEL, NvidiaNemotronDirect
)
from run_nvidia_identity_contract_probe import (
    CONSENT, PUBLIC_REPORT_MODEL_ID, USER_MESSAGES,
    fake_json, fixture_result, probe,
)


class NVIDIAModelIdentityIncidentContracts(unittest.TestCase):
    def test_official_documented_canonical_completion_fixture_is_unit_only(self):
        result, count = fixture_result(fake_json(model=MODEL))
        self.assertEqual(count, 1)
        self.assertEqual(result.status, "UNIT_CONTRACT_ONLY")
        self.assertFalse(result.network_called)
        self.assertTrue(result.test_transport)
        self.assertEqual(result.returned_model, MODEL)
        self.assertFalse(result.public_receipt()["contest_sponsor_acceptance_verified"])

    def test_publicly_reported_private_model_alias_is_rejected(self):
        # NVIDIA developer forum Oct 19: the hosted server returned
        # private/nvidia/nemotron-3.5-super-120b-a12b despite a VL request.
        # No NVIDIA confirmation that the private ID identifies the VL model.
        result, count = fixture_result(fake_json(model=PUBLIC_REPORT_MODEL_ID))
        self.assertEqual(count, 1)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.text)
        self.assertIsNone(result.returned_model)
        self.assertFalse(result.network_called)
        self.assertIsNone(result.request_id)
        self.assertEqual(
            result.detail, "NVIDIA_UNTRUSTED_OR_INCOMPLETE_REPLY_REFUSED"
        )
        self.assertFalse(result.public_receipt()["contest_sponsor_acceptance_verified"])

    def test_same_alias_never_promoted_by_environment_model_override(self):
        injected = []
        with patch.dict(os.environ, {
            **CONSENT,
            "NVIDIA_MODEL": PUBLIC_REPORT_MODEL_ID,
            "NVIDIA_BASE_URL": "https://attacker.invalid/v1",
        }, clear=True):
            result = NvidiaNemotronDirect(
                transport=lambda request: injected.append(request) or
                (200, fake_json(model=PUBLIC_REPORT_MODEL_ID))
            ).chat(USER_MESSAGES)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(len(injected), 1)
        self.assertEqual(injected[0].full_url, ENDPOINT)
        self.assertEqual(json.loads(injected[0].data)["model"], MODEL)
        self.assertFalse(result.network_called)

    def test_offline_identity_probe_has_no_vendor_success_or_secrets(self):
        report = probe()
        self.assertEqual((report["pass"], report["total"]), (4, 4))
        self.assertEqual(report["external_network_calls"], 0)
        self.assertTrue(report["fixture_only"])
        self.assertFalse(report["vendor_model_identity_alias_confirmed"])
        self.assertEqual(report["organizer_sponsor_acceptance"], "NOT_VERIFIED")
        self.assertNotIn(CONSENT["NVIDIA_API_KEY"], json.dumps(report))
        self.assertEqual(report["cases"][1]["actual_status"], "BLOCKED")

    def test_rejected_model_and_truncated_completion_both_fail_closed(self):
        for model, finish in (
            (PUBLIC_REPORT_MODEL_ID, "stop"),
            (PUBLIC_REPORT_MODEL_ID, "length"),
            (MODEL, "length"),
        ):
            with self.subTest(model=model, finish=finish):
                result, _ = fixture_result(
                    fake_json(model=model, finish_reason=finish)
                )
                self.assertEqual(result.status, "BLOCKED")
                self.assertIsNone(result.text)
                self.assertFalse(result.network_called)


if __name__ == "__main__":
    unittest.main()
