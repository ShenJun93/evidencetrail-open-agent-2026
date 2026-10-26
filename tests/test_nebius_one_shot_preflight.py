"""Nebius one-shot consent tests: mock transport only, zero network."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nebius_token_factory import MODEL, NebiusTokenFactory
from run_nebius_one_shot_preflight import main

KEY = "UNIT_ONLY_NEBIUS_NEVER_EXPORTED_01234567890"
ACKS = (
    "--confirm-nebius-third-party-host",
    "--confirm-public-research-egress",
    "--approve-possible-token-charges",
)


def valid_reply():
    text = json.dumps({
        "proposed_verdict": "WARN", "rationale": "FICTIONAL research replay",
        "source_ids": ["GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"],
    })
    return json.dumps({
        "id": "chatcmpl-unit-0123456789", "model": MODEL,
        "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": text
        }}],
    }).encode("utf8")


class OneShotNebiusTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path = Path(t.name)
        self.rcpt = self.path / "one-shot.json"

    def args(self, *extra):
        return [*extra, "--env-file", str(self.path / "missing.env"),
                "--receipt", str(self.rcpt),
                "--trace", str(self.path / "trace.jsonl")]

    def read(self):
        return json.loads(self.rcpt.read_text(encoding="utf8"))

    def test_check_never_egresses_even_if_env_was_enabled(self):
        env = {"NEBIUS_API_KEY": KEY, "EVIDENCETRAIL_NEBIUS_ENABLED": "true",
               "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT": "true",
               "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED": "true"}
        with patch.dict(os.environ, env, clear=True), patch(
            "evidencetrail.adapters.nebius_token_factory._real_transport",
            side_effect=AssertionError("offline check cannot call network"),
        ):
            ret = main(self.args("--check"))
        self.assertEqual(ret, 0)
        self.assertEqual(self.read()["status"], "KEY_PRESENT_OWNER_PAID_APPROVAL_REQUIRED")
        self.assertFalse(self.read()["network_called"])
        self.assertFalse(self.read()["fee_cap_guaranteed"])
        self.assertNotIn(KEY, self.rcpt.read_text(encoding="utf8"))

    def test_missing_any_new_ack_blocks_without_http(self):
        for missing in ACKS:
            with self.subTest(missing=missing), patch.dict(
                os.environ, {"NEBIUS_API_KEY": KEY}, clear=True
            ), patch("evidencetrail.adapters.nebius_token_factory._real_transport",
                     side_effect=AssertionError("not authorized")):
                ret = main(self.args("--live", *(f for f in ACKS if f != missing)))
            self.assertEqual(ret, 2)
            self.assertFalse(self.read()["network_called"])

    def test_missing_key_rejects_even_with_three_acknowledgements(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "evidencetrail.adapters.nebius_token_factory._real_transport",
            side_effect=AssertionError("no key"),
        ):
            ret = main(self.args("--live", *ACKS))
        self.assertEqual(ret, 2)
        self.assertFalse(self.read()["network_called"])

    def test_injected_success_is_not_real_vendor_receipt(self):
        calls = []
        fake = NebiusTokenFactory(
            transport=lambda req: (calls.append(req) or (200, valid_reply()))
        )
        with patch.dict(os.environ, {"NEBIUS_API_KEY": KEY}, clear=True), patch(
            "evidencetrail.agents.decision.NebiusTokenFactory",
            return_value=fake,
        ):
            ret = main(self.args("--live", *ACKS))
        self.assertEqual(len(calls), 1)
        self.assertEqual(ret, 2)
        self.assertFalse(self.read()["network_called"])
        self.assertFalse(self.read()["nvidia_direct_sponsor_receipt"])
        self.assertEqual(self.read()["status"], "NEBIUS_NOT_ACCEPTED_OR_BLOCKED")
        self.assertTrue(self.read()["model_route"].endswith(
            "_injected_unit_transport"
        ))
        self.assertNotIn("_third_party_https_non_sponsor",
                         self.read()["model_route"])
        self.assertNotIn(KEY, self.rcpt.read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
