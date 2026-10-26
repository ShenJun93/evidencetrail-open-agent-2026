"""Offline-only NVIDIA contract investigation; never calls or bills a provider.

All requests use an injected fixture transport and a synthetic dummy key
in a temporary environment. Reports only fixed allowlisted status codes.
No .env.local read, no endpoint traffic, no model identity alias acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nvidia_nim import MODEL, NvidiaNemotronDirect

REPORT = Path("acceptance/logs/nvidia-strict-offline-contract-matrix.json")
DUMMY_KEY = "DUMMY-FIXTURE-NEVER-REAL-NVIDIA-TOKEN"
CONSENT = {
    "NVIDIA_API_KEY": DUMMY_KEY,
    "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
    "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED": "true",
}
MESSAGES = [{"role": "user", "content": "Public fictional historical research fixture."}]


def response(*, model: str = MODEL, finish: str = "stop",
             role: str = "assistant", content: str | None = None) -> bytes:
    proposal = {"proposed_verdict": "INSUFFICIENT_EVIDENCE",
                "rationale": "Fictional research fixture; no first-publication proof.",
                "source_ids": []}
    return json.dumps({
        "id": "chatcmpl-injected-fixture-123456",
        "model": model,
        "choices": [{"finish_reason": finish, "message": {
            "role": role, "content": content if content is not None
            else json.dumps(proposal),
        }}],
    }).encode("utf8")


def cases() -> list[tuple[str, str, object]]:
    def forced_timeout(request):
        raise TimeoutError("Local synthetic fault; not a vendor error")

    return [
        ("canonical_envelope", "UNIT_CONTRACT_ONLY",
         lambda request: (200, response())),
        ("private_alias_unapproved", "BLOCKED",
         lambda request: (200, response(
             model="private/nvidia/nemotron-3.5-super-120b-a12b"))),
        ("pending_http_202_no_success", "UNAVAILABLE",
         lambda request: (202, b'{"requestId":"synthetic-pending"}')),
        ("http_400_no_success", "UNAVAILABLE",
         lambda request: (400, b'{"error":"synthetic-bad-request"}')),
        ("synthetic_transport_timeout", "UNAVAILABLE", forced_timeout),
        ("truncated_finish_refused", "BLOCKED",
         lambda request: (200, response(finish="length"))),
        ("wrong_message_role_refused", "BLOCKED",
         lambda request: (200, response(role="tool"))),
        ("malformed_reply_refused", "BLOCKED",
         lambda request: (200, b'{"choices":[]}')),
    ]


def run_matrix() -> dict:
    records = []
    with patch.dict(os.environ, CONSENT, clear=True):
        for name, expected, transport in cases():
            observed = NvidiaNemotronDirect(transport=transport).chat(MESSAGES)
            # The EXACT public-request envelope is checked by separate wire tests.
            passed = (
                observed.status == expected
                and observed.network_called is False
                and observed.test_transport is True
                and observed.public_receipt()["contest_sponsor_acceptance_verified"] is False
                and (observed.text is None or expected == "UNIT_CONTRACT_ONLY")
            )
            records.append({
                "scenario": name, "expected_status": expected,
                "observed_status": observed.status, "pass": passed,
                "injected_fixture": observed.test_transport,
                "actual_provider_network_called": observed.network_called,
            })
    return {
        "kind": "NVIDIA_STRICT_OFFLINE_CONTRACT_MATRIX_V1",
        "requested_model": MODEL,
        "vendor_reference": "https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-super-vl-120b-a12b-infer",
        "scenarios": records,
        "pass": sum(c["pass"] for c in records),
        "total": len(records),
        "all_pass": all(c["pass"] for c in records),
        "injected_transport_only": True,
        "actual_provider_network_called": False,
        "private_model_alias_accepted": False,
        "real_nvidia_inference_accepted": False,
        "organizer_eligibility_verified": False,
        "past_live_transport_failure_cause_diagnosed": False,
        "note": (
            "A mocked success is not vendor inference. This matrix exercises "
            "only request/response refusal contracts and cannot establish any "
            "commercial key, model alias, actual timeout cause or sponsor compliance."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, default=REPORT)
    args = ap.parse_args()
    report = run_matrix()
    if not report["all_pass"]:
        print(json.dumps({"status": "LOCAL_CONTRACT_FAILURE",
                          "passed": report["pass"], "total": report["total"]}))
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps({
        "status": "INJECTED_ONLY_CONTRACT_PASS",
        "passed": report["pass"], "total": report["total"],
        "vendor_network_called": False, "sponsor_verified": False,
        "receipt": str(args.report),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
