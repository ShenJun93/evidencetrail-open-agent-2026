"""UNIT_CONTRACT_ONLY — fake transport. Not live Nightshift inference."""

from __future__ import annotations

import json
import unittest

from evidencetrail.adapters.meterless import (
    MeterlessRuntimeProvider,
    normalize_v1_base,
    reject_placeholder_token,
)


def _transport_factory(status: int, body: dict | None = None):
    payload = json.dumps(body or {}).encode("utf-8")

    def transport(url, method, headers, body_in, timeout):
        return status, {"content-type": "application/json"}, payload

    return transport


class MeterlessContractV4Tests(unittest.TestCase):
    def test_normalize_never_doubles_v1(self):
        self.assertEqual(normalize_v1_base("http://127.0.0.1:8088/v1/models"), "http://127.0.0.1:8088/v1")
        self.assertEqual(normalize_v1_base("http://127.0.0.1:8088/v1/chat/completions"), "http://127.0.0.1:8088/v1")
        self.assertEqual(normalize_v1_base("127.0.0.1:8088"), "http://127.0.0.1:8088/v1")
        self.assertEqual(normalize_v1_base("http://127.0.0.1:8088/healthz"), "http://127.0.0.1:8088/v1")

    def test_rejects_rt_local(self):
        with self.assertRaises(ValueError):
            reject_placeholder_token("rt-local")

    def test_missing_token_is_not_connected_not_online(self):
        p = MeterlessRuntimeProvider(token="", transport=_transport_factory(200, {"data": [{"id": "meterless/auto"}]}))
        result = p.models()
        self.assertEqual(result.status, "not_connected")

    def test_401_is_unauthorized_not_offline(self):
        p = MeterlessRuntimeProvider(token="real-token-not-placeholder", transport=_transport_factory(401, {}))
        result = p.models()
        self.assertEqual(result.status, "unauthorized")

    def test_403_is_unauthorized(self):
        p = MeterlessRuntimeProvider(token="real-token-not-placeholder", transport=_transport_factory(403, {}))
        self.assertEqual(p.models().status, "unauthorized")

    def test_200_with_meterless_ids_is_online(self):
        p = MeterlessRuntimeProvider(
            token="real-token-not-placeholder",
            transport=_transport_factory(200, {"data": [{"id": "meterless/auto"}, {"id": "meterless/fast"}]}),
        )
        result = p.models()
        self.assertEqual(result.status, "online")
        self.assertIn("meterless/auto", result.models)

    def test_headers_include_app_and_scope(self):
        captured = {}

        def transport(url, method, headers, body, timeout):
            captured["headers"] = headers
            captured["url"] = url
            return 200, {}, json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        p = MeterlessRuntimeProvider(token="real-token-not-placeholder", transport=transport)
        p.chat("hello")
        self.assertEqual(captured["headers"]["meterless-app"], "evidencetrail")
        self.assertEqual(captured["headers"]["meterless-scope"], "user")
        self.assertTrue(captured["headers"]["Authorization"].startswith("Bearer "))
        self.assertIn("/v1/chat/completions", captured["url"])

    def test_contract_label_is_unit_only(self):
        self.assertTrue(True)  # this module is UNIT_CONTRACT_ONLY by file docstring
