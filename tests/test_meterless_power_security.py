"""Nightshift v4 adversarial transport/unit tests. NO real Meterless runtime claims."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from evidencetrail.adapters.meterless import (
    MeterlessRuntimeProvider, _urllib_transport, normalize_v1_base,
)
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.catalog import all_catalog
from evidencetrail.models import RunRequest, SponsorOutcome, Verdict
from evidencetrail.traces import JsonlTrace


def fake_transport(status: int, body):
    payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def transport(url, method, headers, post_body, timeout):
        return status, {"content-type": "application/json"}, payload
    return transport


class MeterlessLocalTokenBoundaryTests(unittest.TestCase):
    def test_valid_local_urls_normalize_only_once(self):
        for base in (
            "127.0.0.1:8088", "http://localhost:8090/healthz",
            "http://[::1]:8787/v1/models", "http://127.0.0.1:8088/v1/chat/completions"
        ):
            with self.subTest(base=base):
                canonical = normalize_v1_base(base)
                self.assertEqual(canonical.count("/v1"), 1)
                self.assertTrue(canonical.startswith("http://"))

    def test_reject_remote_userinfo_https_query_fragment_bad_path_and_trick_hosts(self):
        dangerous = (
            "https://127.0.0.1:8088/v1",
            "http://meterless.example.com:8088/v1",
            "http://127.0.0.2:8088/v1",
            "http://127.0.0.1.evil.example.com:8088/v1",
            "http://user:secret@127.0.0.1:8088/v1",
            "http://127.0.0.1:8088/v1?token=leak",
            "http://127.0.0.1:8088/v1#k=secret",
            "http://127.0.0.1:8088/v1/v1",
            "http://127.0.0.1:8088/v1/other",
            "http://[::1]:bogus/v1",
            "http://localhost:65536/v1",
        )
        for bad in dangerous:
            with self.subTest(base=bad):
                with self.assertRaises(ValueError):
                    MeterlessRuntimeProvider(base_url=bad, token="dummy-contract-token")

    def test_no_external_transport_even_with_bearer_argument(self):
        with self.assertRaises(ValueError):
            _urllib_transport(
                "http://example.com/v1/chat/completions", "POST",
                {"Authorization": "Bearer dummy-contract-token"}, b"{}", 1,
            )

    def test_local_redirect_cannot_forward_token(self):
        observed = {"redirected": 0, "auth_seen_on_target": False}

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                observed["redirected"] += 1
                observed["auth_seen_on_target"] = bool(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *_args):
                return

        target = ThreadingHTTPServer(("127.0.0.1", 0), Target)

        class Origin(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header(
                    "Location",
                    f"http://127.0.0.1:{target.server_port}/receiver"
                )
                self.end_headers()

            def log_message(self, *_args):
                return

        origin = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        workers = [
            threading.Thread(target=s.serve_forever, daemon=True)
            for s in (origin, target)
        ]
        try:
            for th in workers:
                th.start()
            with self.assertRaises(ValueError):
                _urllib_transport(
                    f"http://127.0.0.1:{origin.server_port}/v1/models",
                    "GET", {"Authorization": "Bearer dummy-contract-token"}, None, 3
                )
            self.assertEqual(observed["redirected"], 0)
            self.assertFalse(observed["auth_seen_on_target"])
        finally:
            for s in (origin, target):
                s.shutdown()
                s.server_close()
            for th in workers:
                th.join(timeout=2)

    def test_models_malformed_http_200_is_not_online(self):
        shapes = (
            b"not-json", b"[]", b'{"data":"meterless/auto"}',
            b'{"data":[{"id":10}]}', b'{"data":[{"id":"not-meterless/auto"}]}',
        )
        for body in shapes:
            with self.subTest(body=body):
                p = MeterlessRuntimeProvider(
                    token="dummy-contract-token",
                    transport=fake_transport(200, body)
                )
                self.assertNotEqual(p.models().status, "online")

    def test_unauthorized_preserved_not_translated_offline(self):
        for status in (401, 403):
            with self.subTest(status=status):
                p = MeterlessRuntimeProvider(
                    token="dummy-contract-token",
                    transport=fake_transport(status, {})
                )
                self.assertEqual(p.models().status, "unauthorized")

    def test_chat_invalid_http_200_is_not_success(self):
        shapes = (
            b"not-json", b"[]", b'{"choices":[]}',
            b'{"choices":[{"message":{"content":null}}]}',
            b'{"choices":[{"message":{"content":"  "}}]}',
        )
        for body in shapes:
            with self.subTest(body=body):
                p = MeterlessRuntimeProvider(
                    token="dummy-contract-token",
                    transport=fake_transport(200, body)
                )
                result = p.chat("Safe unit-only contract prompt")
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "invalid_response")

    def test_chat_valid_transport_remains_unit_only(self):
        payload = {"id": "mock-receipt", "choices": [{
            "message": {"content": '{"proposed_verdict":"INSUFFICIENT_EVIDENCE","rationale":"Unit-only reason","source_ids":[]}'}
        }]}
        provider = MeterlessRuntimeProvider(
            token="dummy-contract-token",
            transport=fake_transport(200, payload)
        )
        response = provider.chat("Unit-only request")
        self.assertTrue(response["ok"])
        self.assertEqual(response["raw_id"], "mock-receipt")

    def test_reject_nonlinear_model_route_before_transport(self):
        p = MeterlessRuntimeProvider(
            token="dummy-contract-token",
            transport=lambda *_: self.fail("invalid model triggered network")
        )
        for model in ("gpt-4", "meterless/auto\nAuthorization:x", "meterless/", ""):
            with self.subTest(model=model):
                with self.assertRaises(ValueError):
                    p.chat("test", model=model)

    def test_reject_oversize_model_prompt_before_transport(self):
        p = MeterlessRuntimeProvider(
            token="dummy-contract-token",
            transport=lambda *_: self.fail("oversize prompt triggered network")
        )
        with self.assertRaises(ValueError):
            p.chat("a" * 16001)


class FakeModelCitationIntegrityTests(unittest.TestCase):
    def make_agent(self, content):
        def transport(url, method, headers, body, timeout):
            if url.endswith("/models"):
                return 200, {}, b'{"data":[{"id":"meterless/auto"}]}'
            return 200, {}, json.dumps({
                "id": "fake-id-unit-not-live",
                "choices": [{"message": {"content": content}}]
            }).encode("utf-8")
        provider = MeterlessRuntimeProvider(
            token="dummy-contract-token", transport=transport
        )
        td = tempfile.TemporaryDirectory()
        agent = DecisionAgent(
            JsonlTrace(Path(td.name) / "trace.jsonl", "unit-malformed"),
            provider=provider,
        )
        return td, agent

    @staticmethod
    def request():
        return RunRequest.from_dict({
            "schema_version": "1",
            "mission_id": "yagi-yenbai-2024",
            "scenario_id": "yagi-replay-alpha",
            "as_of_utc": "2024-09-08T09:45:00Z",
            "mode": "REPORTED_DATELINE_REPLAY",
            "province_2024": "yen bai",
            "district_2024": "luc yen",
            "granularity": "district",
            "question": "Fictional watch, not operational advice?",
            "sample_mode": False,
        })

    def test_malformed_model_json_must_not_create_success_receipt(self):
        td, agent = self.make_agent("not a JSON object")
        try:
            draft = agent.run(self.request(), all_catalog())
            self.assertEqual(draft.model_route, "deterministic_reducer_offline_or_fallback")
            self.assertFalse(any(
                c.outcome == SponsorOutcome.REAL_SUCCESS for c in agent.sponsor_calls
            ))
            self.assertTrue(any(
                c.contract_label == "CHAT_RESULT_NOT_VERIFIED" for c in agent.sponsor_calls
            ))
        finally:
            td.cleanup()

    def test_hallucinated_source_fails_both_decision_and_receipt(self):
        fake_json = json.dumps({
            "proposed_verdict": "WARN",
            "rationale": "Fabricated source ID from unit model",
            "source_ids": ["GOV-FAKE-IN-FUTURE"],
        })
        td, agent = self.make_agent(fake_json)
        try:
            draft = agent.run(self.request(), all_catalog())
            self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
            self.assertIn("model_citation_not_in_eligible_source_set", draft.missing_facts)
            self.assertTrue(any(
                c.contract_label == "MODEL_CITATION_FAILED_LOCAL_VALIDATION"
                and c.outcome == SponsorOutcome.BLOCKED
                for c in agent.sponsor_calls
            ))
        finally:
            td.cleanup()
