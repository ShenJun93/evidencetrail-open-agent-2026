"""Meterless route discovery and vendor-origin truthfulness contract.

All injected 200s here are UNIT fixtures, NOT proof of Nightshift/Power.
"""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.meterless import (
    MeterlessRuntimeProvider, parse_routed_receipt,
)
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.catalog import all_catalog
from evidencetrail.models import RunRequest, SponsorOutcome
from evidencetrail.traces import JsonlTrace


class RouteProofTests(unittest.TestCase):
    def test_direct_route_receipt_contains_only_safe_identifiers(self):
        doc = {"meterless": {
            "routed_model": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "provider_model": "meterless/auto",
            "api_key": "never-in-output",
            "egress": {"destination": "https://untrusted.invalid/private"},
        }}
        self.assertEqual(parse_routed_receipt(doc), {
            "routed_model": "nvidia/nemotron-3.5-lightning-30b-a3b",
            "provider_model": "meterless/auto",
        })

    def test_nested_receipt_supports_a_local_webllm_route(self):
        self.assertEqual(parse_routed_receipt({"meterless": {
            "receipt": {"routed_model": "webllm/SmolLM2-1.7B-UnitOnly"}
        }}), {"routed_model": "webllm/SmolLM2-1.7B-UnitOnly"})

    def test_nightshift_top_level_route_with_full_receipt_envelope(self):
        # Observed Nightshift 1.2.3 shape: the nested receipt records the
        # winning route, while the public routed_model sits beside it.
        doc = {"meterless": {
            "routed_model": "local-runtime/llama-3.2-1b-instruct",
            "provider_model": "local-runtime/llama-3.2-1b-instruct",
            "receipt": {"winning_route": {
                "model": "local-runtime/llama-3.2-1b-instruct",
                "kind": "local",
            }},
        }}
        self.assertEqual(parse_routed_receipt(doc), {
            "routed_model": "local-runtime/llama-3.2-1b-instruct",
            "provider_model": "local-runtime/llama-3.2-1b-instruct",
        })

    def test_conflicting_direct_and_nested_routes_are_rejected(self):
        self.assertIsNone(parse_routed_receipt({"meterless": {
            "routed_model": "local-runtime/llama-3.2-1b-instruct",
            "receipt": {"routed_model": "cloud/other-model"},
        }}))

    def test_malformed_or_missing_route_receipt_is_not_made_up(self):
        payloads = (
            {}, {"meterless": "NIGHTSHIFT"}, {"meterless": {"routed_model": ""}},
            {"meterless": {"routed_model": "nvidia/unit\nBearer:unsafe"}},
            {"meterless": {"receipt": ["route"]}},
            {"meterless": {"routed_model": "x" * 161}},
        )
        for item in payloads:
            with self.subTest(payload=item):
                self.assertIsNone(parse_routed_receipt(item))

    def test_chat_only_returns_sanitized_route_and_safe_request_id(self):
        def transport(url, method, headers, body, timeout):
            payload = {
                "id": "reply-unit-1",
                "choices": [{"message": {"content": "safe unit-only text"}}],
                "meterless": {
                    "routed_model": "local-runtime/phi-unit",
                    "secret": "never-returned",
                },
            }
            return 200, {}, json.dumps(payload).encode()
        p = MeterlessRuntimeProvider(token="unit-only-fake-token", transport=transport)
        result = p.chat("safe unit prompt")
        self.assertTrue(result["ok"])
        self.assertEqual(result["raw_id"], "reply-unit-1")
        self.assertEqual(result["route_receipt"], {"routed_model": "local-runtime/phi-unit"})
        self.assertFalse(result["route_identity_independently_verified"])
        self.assertNotIn("secret", str(result))

    def test_malformed_request_id_not_exposed_in_result(self):
        def transport(url, method, headers, body, timeout):
            return 200, {}, json.dumps({
                "id": "token\negress: private",
                "choices": [{"message": {"content": "text"}}],
            }).encode()
        p = MeterlessRuntimeProvider(token="unit-only", transport=transport)
        response = p.chat("hello")
        self.assertTrue(response["ok"])
        self.assertIsNone(response["raw_id"])

    def test_unstable_application_ids_rejected_before_any_transport(self):
        for bad in ("EvidenceTrail", "foo\nAuthorization:danger", "root app", "/" * 12):
            with self.subTest(app=bad):
                with self.assertRaises(ValueError):
                    MeterlessRuntimeProvider(
                        token="unit-only", app=bad,
                        transport=lambda *_: self.fail("transport must never start"),
                    )


def run_fake_decision(*, listed_modes, reply_route, response_id="fake-injected-id"):
    requests = []
    payload = json.dumps({
        "proposed_verdict": "INSUFFICIENT_EVIDENCE",
        "rationale": "Synthetic unit-only proposal",
        "source_ids": [],
    })

    def transport(url, method, headers, body, timeout):
        requests.append((url, method))
        if url.endswith("/models"):
            return 200, {}, json.dumps({
                "data": [{"id": item} for item in listed_modes],
            }).encode()
        message = {
            "id": response_id,
            "choices": [{"message": {"content": payload}}],
        }
        if reply_route:
            message["meterless"] = {"receipt": {"routed_model": reply_route}}
        return 200, {}, json.dumps(message).encode()

    fake = MeterlessRuntimeProvider(
        token="fake-unit-token",
        transport=transport,
        base_url="http://127.0.0.1:8088/v1",
    )
    request = RunRequest.from_dict({
        "schema_version": "1",
        "mission_id": "yagi-yenbai-2024",
        "scenario_id": "yagi-replay-alpha",
        "as_of_utc": "2024-09-08T09:45:00Z",
        "mode": "REPORTED_DATELINE_REPLAY",
        "province_2024": "yen bai",
        "district_2024": "luc yen",
        "granularity": "district",
        "question": "Synthetic research-only unit test",
        "sample_mode": False,
    })
    with tempfile.TemporaryDirectory() as td:
        trace = JsonlTrace(Path(td) / "trace.jsonl", "unit-route-attest")
        agent = DecisionAgent(trace)
        # Only the default constructor is patched. The tested code follows
        # the real provider branch (self.provider=None) but has no network.
        with patch(
            "evidencetrail.agents.decision.MeterlessRuntimeProvider",
            return_value=fake,
        ):
            draft = agent.run(request, all_catalog())
        receipts = list(agent.sponsor_calls)
        return draft, receipts, requests


class DefaultProviderCannotClaimSponsorFromFakeRuntimeTests(unittest.TestCase):
    def test_real_http_socket_impersonator_is_not_a_vendor_success(self):
        """Spoofing a local HTTP response cannot create a sponsor success."""
        paths = []

        class Impersonator(BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(("GET", self.path))
                self._respond({"data": [{"id": "meterless/auto"}]})

            def do_POST(self):
                paths.append(("POST", self.path))
                n = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(min(n, 32000))
                self._respond({
                    "id": "local-spoof-response",
                    "choices": [{"message": {"content": json.dumps({
                        "proposed_verdict": "INSUFFICIENT_EVIDENCE",
                        "source_ids": [],
                        "rationale": "Mock HTTP responder, not a real provider",
                    })}}],
                    "meterless": {"receipt": {
                        "routed_model": "nvidia/nemotron-3.5-lightning-30b-a3b",
                    }},
                })

            def _respond(self, obj):
                raw = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Impersonator)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            req = RunRequest.from_dict({
                "schema_version": "1",
                "mission_id": "yagi-yenbai-2024",
                "scenario_id": "yagi-replay-alpha",
                "as_of_utc": "2024-09-08T09:45:00Z",
                "mode": "REPORTED_DATELINE_REPLAY",
                "province_2024": "yen bai",
                "district_2024": "luc yen",
                "granularity": "district",
                "question": "Unit-only, not operational advice",
                "sample_mode": False,
            })
            with tempfile.TemporaryDirectory() as td:
                trace = JsonlTrace(Path(td) / "trace.jsonl", "fake-http-loopback")
                agent = DecisionAgent(trace)
                with patch.dict("os.environ", {
                    "METERLESS_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                    "METERLESS_RUNTIME_TOKEN": "dummy-local-not-real-token",
                    "METERLESS_APP": "evidencetrail",
                }):
                    agent.run(req, all_catalog())
            self.assertEqual(len(paths), 2)
            self.assertTrue(any(path.endswith("/models") for _, path in paths))
            self.assertTrue(any(path.endswith("/chat/completions") for _, path in paths))
            self.assertTrue(any(
                x.outcome == SponsorOutcome.REAL_PROBE_ONLY
                and x.contract_label == "LOCAL_ROUTED_CHAT_UNVERIFIED_INSTANCE_ORIGIN"
                for x in agent.sponsor_calls
            ))
            self.assertFalse(any(x.outcome == SponsorOutcome.REAL_SUCCESS
                                 for x in agent.sponsor_calls))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_models_missing_auto_never_sends_chat(self):
        draft, receipts, requests = run_fake_decision(
            listed_modes=["meterless/fast"],
            reply_route="nvidia/unit-model",
        )
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0][0].endswith("/models"))
        self.assertTrue(any(
            receipt.contract_label == "MODEL_ROUTE_NOT_DISCOVERED"
            and receipt.outcome == SponsorOutcome.BLOCKED
            for receipt in receipts
        ))
        self.assertFalse(any(x.outcome == SponsorOutcome.REAL_SUCCESS for x in receipts))

    def test_fake_local_http_200_without_routed_receipt_is_not_sponsor_success(self):
        draft, receipts, requests = run_fake_decision(
            listed_modes=["meterless/auto"], reply_route=None
        )
        self.assertEqual(len(requests), 2)
        self.assertTrue(any(
            x.outcome == SponsorOutcome.REAL_PROBE_ONLY
            and x.contract_label == "LOCAL_CHAT_ROUTING_UNVERIFIED"
            for x in receipts
        ))
        self.assertEqual(draft.model_route, "deterministic_reducer_offline_or_fallback")
        self.assertFalse(any(x.outcome == SponsorOutcome.REAL_SUCCESS for x in receipts))

    def test_fake_routed_model_receipt_cannot_claim_authenticated_nightshift(self):
        draft, receipts, requests = run_fake_decision(
            listed_modes=["meterless/auto"],
            reply_route="nvidia/nemotron-3.5-lightning-30b-a3b",
        )
        self.assertEqual(len(requests), 2)
        self.assertTrue(any(
            x.outcome == SponsorOutcome.REAL_PROBE_ONLY
            and x.contract_label == "LOCAL_ROUTED_CHAT_UNVERIFIED_INSTANCE_ORIGIN"
            for x in receipts
        ))
        self.assertFalse(any(x.outcome == SponsorOutcome.REAL_SUCCESS for x in receipts))
        self.assertIn("origin_unverified", draft.model_route)


if __name__ == "__main__":
    unittest.main()
