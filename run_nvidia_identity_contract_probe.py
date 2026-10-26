"""Offline NVIDIA model-identity contract probe for cold judges.

NO external requests. Every result is from an injected in-process fixture and
must NEVER be presented as an actual vendor completion or sponsor success.

Usage: py -3 run_nvidia_identity_contract_probe.py
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

from evidencetrail.adapters.nvidia_nim import ENDPOINT, MODEL, NvidiaNemotronDirect

# Fake fixture only, not a NVIDIA developer credential.
FAKE_KEY = "TEST_ONLY_DO_NOT_USE_FOR_REAL_INFERENCE_1234567"
CONSENT = {
    "NVIDIA_API_KEY": FAKE_KEY,
    "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
    "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED": "true",
}
PUBLIC_REPORT_MODEL_ID = "private/nvidia/nemotron-3.5-super-120b-a12b"
USER_MESSAGES = [
    {"role": "user", "content": "FICTIONAL research-only contract fixture"}
]


def fake_json(*, model: str, finish_reason: str = "stop",
              content: str | None = '{"proposed_verdict":"INSUFFICIENT_EVIDENCE"}') -> bytes:
    """NVIDIA-published response shape, populated with synthetic example values."""
    return json.dumps({
        "id": "chatcmpl-unit-contract-12345678",
        "object": "chat.completion",
        "created": 1791404342,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content,
                "reasoning": None,
                "refusal": None,
                "annotations": None,
                "function_call": None,
            },
            "logprobs": None,
            "finish_reason": finish_reason,
            "stop_reason": None,
        }],
        "usage": {
            "prompt_tokens": 22,
            "completion_tokens": 20,
            "total_tokens": 42,
        },
    }).encode("utf8")


def fixture_result(payload: bytes) -> tuple[object, int]:
    """Runs only an INJECTED transport. Never contact the NVIDIA host."""
    fake_requests = []
    def transport(request):
        fake_requests.append(request)
        return 200, payload

    with patch.dict(os.environ, CONSENT, clear=True):
        reply = NvidiaNemotronDirect(transport=transport).chat(USER_MESSAGES)
    return reply, len(fake_requests)


def probe() -> dict:
    tests = (
        ("nvidia_documented_canonical_shape", MODEL, "stop", "UNIT_CONTRACT_ONLY"),
        ("publicly_reported_unverified_private_alias", PUBLIC_REPORT_MODEL_ID,
         "stop", "BLOCKED"),
        ("private_alias_with_truncated_completion", PUBLIC_REPORT_MODEL_ID,
         "length", "BLOCKED"),
        ("canonical_but_truncated_completion", MODEL, "length", "BLOCKED"),
    )
    cases = []
    for name, model, finish_reason, expected in tests:
        reply, transport_count = fixture_result(
            fake_json(model=model, finish_reason=finish_reason)
        )
        passed = (
            reply.status == expected and reply.network_called is False
            and reply.test_transport is True and transport_count == 1
            and not (reply.status == "REAL_MODEL_RESPONSE")
        )
        cases.append({
            "case": name, "pass": passed,
            "expected_status": expected, "actual_status": reply.status,
            "network_called": reply.network_called,
        })
    return {
        "kind": "NVIDIA_MODEL_IDENTITY_OFFLINE_PROBE",
        "fixture_only": True,
        "requested_model": MODEL,
        "official_endpoint": ENDPOINT,
        "external_network_calls": 0,
        "vendor_model_identity_alias_confirmed": False,
        "organizer_sponsor_acceptance": "NOT_VERIFIED",
        "pass": sum(bool(c["pass"]) for c in cases),
        "total": len(cases),
        "cases": cases,
    }


def main() -> int:
    report = probe()
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0 if report["pass"] == report["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
