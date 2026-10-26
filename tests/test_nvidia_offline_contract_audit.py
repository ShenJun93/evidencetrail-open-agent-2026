"""No-billing NVIDIA matrix: never grant sponsor acceptance for a fake response."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from run_nvidia_offline_contract_audit import DUMMY_KEY, cases, run_matrix


class NvidiaOfflineMatrixProofTests(unittest.TestCase):
    def test_eight_injected_cases_and_no_accepted_vendor_completion(self):
        result = run_matrix()
        self.assertEqual(result["total"], 8)
        self.assertEqual(result["pass"], 8)
        self.assertTrue(result["all_pass"])
        self.assertFalse(result["real_nvidia_inference_accepted"])
        self.assertFalse(result["organizer_eligibility_verified"])
        self.assertFalse(result["actual_provider_network_called"])
        self.assertFalse(result["private_model_alias_accepted"])
        self.assertNotIn(DUMMY_KEY, json.dumps(result))

    def test_synthetic_transport_contracts_distinguish_parser_gates(self):
        report = run_matrix()
        items = {x["scenario"]: x for x in report["scenarios"]}
        self.assertEqual(items["canonical_envelope"]["observed_status"],
                         "UNIT_CONTRACT_ONLY")
        self.assertEqual(items["private_alias_unapproved"]["observed_status"], "BLOCKED")
        self.assertEqual(items["pending_http_202_no_success"]["observed_status"],
                         "UNAVAILABLE")
        self.assertEqual(items["synthetic_transport_timeout"]["observed_status"],
                         "UNAVAILABLE")
        self.assertTrue(all(x["injected_fixture"] for x in items.values()))

    def test_no_fixture_without_explicit_injected_transport(self):
        self.assertEqual(len(cases()), 8)
        with patch("evidencetrail.adapters.nvidia_nim._real_transport",
                   side_effect=AssertionError("No real NVIDIA request allowed")):
            result = run_matrix()
        self.assertTrue(result["all_pass"])


if __name__ == "__main__":
    unittest.main()
