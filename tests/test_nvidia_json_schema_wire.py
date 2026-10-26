"""No-network regression for NVIDIA Nemotron's documented JSON-schema request.

These tests invoke injected transports ONLY; they do not read real credentials,
call the NVIDIA service, or assert organizer/model acceptance.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from evidencetrail.adapters.nvidia_nim import MODEL, NvidiaNemotronDirect


FLAGS = {
    "NVIDIA_API_KEY": "TEST_ONLY_PLACEHOLDER_123456789",
    "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
    "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED": "true",
}
MESSAGES = [{"role": "user", "content": "Historical fictional research."}]


def _reply(model=MODEL, finish="stop"):
    return json.dumps({
        "id": "chatcmpl-offline-test-123456",
        "model": model,
        "choices": [{
            "finish_reason": finish,
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "proposed_verdict": "INSUFFICIENT_EVIDENCE",
                    "rationale": "Evidence incomplete; synthetic only.",
                    "source_ids": [],
                }),
            },
        }],
    }).encode("utf8")


class NvidiaJsonSchemaWireContracts(unittest.TestCase):
    def test_json_schema_payload_has_all_required_fields_and_no_extras(self):
        calls = []

        def fake(req):
            calls.append(req)
            return 200, _reply()

        with patch.dict(os.environ, FLAGS, clear=True):
            result = NvidiaNemotronDirect(transport=fake).chat(MESSAGES)
        self.assertEqual(result.status, "UNIT_CONTRACT_ONLY")
        self.assertFalse(result.network_called)
        self.assertEqual(len(calls), 1)
        body = json.loads(calls[0].data)
        schema_format = body["response_format"]
        self.assertEqual(schema_format["type"], "json_schema")
        schema = schema_format["json_schema"]["schema"]
        self.assertEqual(schema["type"], "object")
        expected = {"proposed_verdict", "rationale", "source_ids"}
        self.assertEqual(set(schema["properties"]), expected)
        self.assertEqual(set(schema["required"]), expected)
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(
            set(schema["properties"]["proposed_verdict"]["enum"]),
            {"WARN", "NO_WARN", "INSUFFICIENT_EVIDENCE"},
        )
        self.assertEqual(schema["properties"]["source_ids"]["type"], "array")
        self.assertEqual(schema["properties"]["source_ids"]["items"]["type"], "string")
        self.assertEqual(body["model"], MODEL)
        self.assertFalse(body["stream"])
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertNotIn(FLAGS["NVIDIA_API_KEY"], json.dumps(result.public_receipt()))

    def test_missing_owner_consent_blocks_before_any_wire_request(self):
        for removed in (
            "NVIDIA_API_KEY",
            "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED",
            "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT",
            "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED",
        ):
            calls = []
            with self.subTest(missing=removed), patch.dict(
                os.environ, {k: v for k, v in FLAGS.items() if k != removed},
                clear=True,
            ):
                result = NvidiaNemotronDirect(
                    transport=lambda req: calls.append(req) or (200, _reply())
                ).chat(MESSAGES)
            self.assertEqual(calls, [])
            self.assertFalse(result.network_called)
            self.assertNotEqual(result.status, "UNIT_CONTRACT_ONLY")

    def test_unverified_private_model_identity_still_rejected(self):
        with patch.dict(os.environ, FLAGS, clear=True):
            result = NvidiaNemotronDirect(
                transport=lambda req: (
                    200, _reply(model="private/nvidia/nemotron-3.5-super-120b-a12b")
                )
            ).chat(MESSAGES)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIsNone(result.text)
        self.assertFalse(result.network_called)

    def test_pending_http_202_never_counted_as_completed_inference(self):
        with patch.dict(os.environ, FLAGS, clear=True):
            result = NvidiaNemotronDirect(
                transport=lambda req: (202, b'{"requestId":"untrusted-pending"}')
            ).chat(MESSAGES)
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertIsNone(result.text)
        self.assertFalse(result.network_called)
        self.assertFalse(result.public_receipt()["contest_sponsor_acceptance_verified"])


if __name__ == "__main__":
    unittest.main()
