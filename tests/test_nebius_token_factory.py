"""Nebius Token Factory contract: zero real network, separate provider identity."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nebius_token_factory import (
    ENDPOINT, MODEL, MAX_TOKENS, NebiusTokenFactory, gates
)
from run_nebius_offline_preflight import main

FAKE_KEY = "NEBIUS_FIXTURE_KEY_NOT_VALID_FOR_INFERENCE_1234"
FLAGS = {
    "NEBIUS_API_KEY": FAKE_KEY,
    "EVIDENCETRAIL_NEBIUS_ENABLED": "true",
    "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED": "true",
}
MESSAGES = [{"role": "user", "content": "Fictional historical replay."}]


def reply(model=MODEL, content='{"proposed_verdict":"INSUFFICIENT_EVIDENCE"}',
          finish="stop"):
    return json.dumps({
        "id": "chatcmpl-nebius-unit-12345", "model": model,
        "choices": [{"finish_reason": finish,
                     "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                  "total_tokens": 30},
    }).encode("utf8")


class NebiusContractTests(unittest.TestCase):
    def test_api_key_alone_never_allows_transport(self):
        calls = []
        with patch.dict(os.environ, {"NEBIUS_API_KEY": FAKE_KEY}, clear=True):
            out = NebiusTokenFactory(
                transport=lambda request: calls.append(request) or (200, reply())
            ).chat(MESSAGES)
        self.assertEqual(calls, [])
        self.assertEqual(out.status, "BLOCKED")
        self.assertFalse(out.network_called)

    def test_each_individual_authority_gate_blocks(self):
        for missing in (
            "EVIDENCETRAIL_NEBIUS_ENABLED",
            "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT",
            "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED",
        ):
            with self.subTest(missing=missing):
                values = {k: v for k, v in FLAGS.items() if k != missing}
                calls = []
                with patch.dict(os.environ, values, clear=True):
                    out = NebiusTokenFactory(
                        transport=lambda req: calls.append(req) or (200, reply())
                    ).chat(MESSAGES)
                self.assertEqual(out.status, "BLOCKED")
                self.assertFalse(out.network_called)
                self.assertEqual(calls, [])

    def test_pinned_nebius_request_is_mock_only(self):
        calls = []
        with patch.dict(os.environ, FLAGS, clear=True):
            out = NebiusTokenFactory(
                transport=lambda req: calls.append(req) or (200, reply())
            ).chat(MESSAGES)
        self.assertEqual(out.status, "UNIT_CONTRACT_ONLY")
        self.assertFalse(out.network_called)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].full_url, ENDPOINT)
        sent = json.loads(calls[0].data)
        self.assertEqual(sent["model"], MODEL)
        self.assertEqual(sent["max_tokens"], MAX_TOKENS)
        self.assertFalse(sent["stream"])
        receipt = json.dumps(out.public_receipt())
        self.assertNotIn(FAKE_KEY, receipt)
        self.assertNotIn(FAKE_KEY, calls[0].data.decode("utf8"))
        self.assertFalse(out.public_receipt()["nvidia_direct_sponsor_receipt"])
        self.assertFalse(out.public_receipt()["contest_organizer_eligibility_verified"])

    def test_wrong_model_or_truncated_reply_never_success(self):
        for content, model, finish in (
            ('{"test":true}', "private/nvidia/nemotron-3-super-120b-a12b", "stop"),
            ('{"test":true}', MODEL, "length"),
            (None, MODEL, "stop"),
        ):
            with self.subTest(model=model, finish=finish):
                with patch.dict(os.environ, FLAGS, clear=True):
                    out = NebiusTokenFactory(
                        transport=lambda req: (200, reply(
                            model=model, content=content, finish=finish
                        ))
                    ).chat(MESSAGES)
                self.assertEqual(out.status, "BLOCKED")
                self.assertIsNone(out.text)
                self.assertFalse(out.network_called)

    def test_unapproved_endpoint_override_is_ignored(self):
        calls = []
        with patch.dict(os.environ, {
            **FLAGS,
            "NEBIUS_BASE_URL": "https://malicious.invalid/v1",
            "NEBIUS_MODEL": "malicious/model",
        }, clear=True):
            out = NebiusTokenFactory(
                transport=lambda req: calls.append(req) or (200, reply())
            ).chat(MESSAGES)
        self.assertEqual(out.status, "UNIT_CONTRACT_ONLY")
        self.assertEqual(calls[0].full_url, ENDPOINT)
        self.assertEqual(json.loads(calls[0].data)["model"], MODEL)

    def test_offline_check_reads_key_only_as_boolean_not_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env.local"
            p.write_text("NEBIUS_API_KEY=" + FAKE_KEY + "\n", encoding="utf8")
            receipt = Path(tmp) / "receipt.json"
            with patch.dict(os.environ, {}, clear=True), patch(
                "evidencetrail.adapters.nebius_token_factory._real_transport",
                side_effect=AssertionError("no network allowed in --check"),
            ):
                status = main([
                    "--check", "--env-file", str(p),
                    "--receipt", str(receipt),
                ])
            self.assertEqual(status, 0)
            data = json.loads(receipt.read_text(encoding="utf8"))
            self.assertTrue(data["nebius_api_key_present"])
            self.assertEqual(data["external_network_calls"], 0)
            self.assertFalse(data["nvidia_direct_sponsor_receipt"])
            self.assertNotIn(FAKE_KEY, receipt.read_text(encoding="utf8"))

    def test_key_not_accepted_as_nvidia_token(self):
        with patch.dict(os.environ, {"NEBIUS_API_KEY": FAKE_KEY}, clear=True):
            self.assertTrue(gates()["nebius_api_key_present"])
            from evidencetrail.adapters.nvidia_nim import gates as nvidia_gates
            self.assertFalse(nvidia_gates()["nvidia_api_key_present"])


if __name__ == "__main__":
    unittest.main()
