"""Offline NVIDIA Nemotron 3.5 request shape and fail-closed tests."""
from __future__ import annotations
import json
import os
import unittest
from unittest.mock import patch
from evidencetrail.adapters.nvidia_nim import (
    MODEL, MAX_TOKENS, ENDPOINT, NvidiaNemotronDirect
)

FAKE_KEY = "UNIT_TEST_PLACEHOLDER_KEY_1234567890"
FLAGS = {
    "NVIDIA_API_KEY": FAKE_KEY,
    "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
    "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED": "true",
}
MESSAGES = [{"role": "user", "content": "Fictional historical replay."}]


def fixture(content="OK", finish="stop"):
    return json.dumps({
        "id": "chatcmpl-unit-000123",
        "model": MODEL,
        "choices": [{"finish_reason": finish, "message": {
            "role": "assistant", "content": content, "reasoning": None
        }}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 60,
                  "total_tokens": 80}
    }).encode("utf-8")


class Nemotron35ReasoningPayloadTests(unittest.TestCase):
    def test_explicit_non_thinking_payload_and_bounded_budget(self):
        calls = []
        def fake(req):
            calls.append(req)
            return 200, fixture()
        with patch.dict(os.environ, FLAGS, clear=True):
            result = NvidiaNemotronDirect(transport=fake).chat(MESSAGES)
        self.assertEqual(result.status, "UNIT_CONTRACT_ONLY")
        self.assertFalse(result.network_called)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].full_url, ENDPOINT)
        payload = json.loads(calls[0].data)
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(MAX_TOKENS, 768)
        self.assertEqual(payload["max_tokens"], MAX_TOKENS)
        self.assertFalse(payload["stream"])
        self.assertNotIn(FAKE_KEY, json.dumps(result.public_receipt()))
        self.assertNotIn(FAKE_KEY, calls[0].data.decode("utf-8"))

    def test_reasoning_exhaustion_never_accepted(self):
        for content in (None, ""):
            with self.subTest(content=content):
                with patch.dict(os.environ, FLAGS, clear=True):
                    reply = NvidiaNemotronDirect(
                        transport=lambda req: (200, fixture(
                            content=content, finish="length"))
                    ).chat(MESSAGES)
                self.assertEqual(reply.status, "BLOCKED")
                self.assertIsNone(reply.text)
                self.assertFalse(reply.network_called)

    def test_missing_replacement_model_permission_never_egresses(self):
        flags = {k: v for k, v in FLAGS.items()
                 if k != "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED"}
        calls = []
        with patch.dict(os.environ, flags, clear=True):
            reply = NvidiaNemotronDirect(
                transport=lambda req: calls.append(req) or (200, fixture())
            ).chat(MESSAGES)
        self.assertEqual(calls, [])
        self.assertEqual(reply.status, "BLOCKED")
        self.assertFalse(reply.network_called)


if __name__ == "__main__":
    unittest.main()
