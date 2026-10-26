"""Safety/transport contracts for direct NVIDIA Nemotron, all offline fixtures.

No integration test makes an actual NVIDIA NIM HTTP request or counts its
injected reply as REAL_SUCCESS. Authenticated vendor inference must be run
separately by the owner, with a real key and explicit remote-data consent.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nvidia_nim import (
    ENDPOINT, MODEL, MAX_TOKENS, NvidiaNemotronDirect,
    _parse_response, gates,
)
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.catalog import all_catalog
from evidencetrail.firewall import filter_sources
from evidencetrail.models import (
    RunRequest, ReplayMode, SponsorOutcome, Verdict,
)
from evidencetrail.traces import JsonlTrace


KEY = "nvapi-DUMMY-FIXTURE-NOT-A-REAL-KEY"
CONSENT = {
    "NVIDIA_API_KEY": KEY,
    "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
    "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED": "true",
}
USER = [{"role": "user", "content": "Research-only test. No sensitive data."}]


def output(verdict="WARN", ids=None, rationale="Simulated and citation-bound."):
    return json.dumps({
        "proposed_verdict": verdict, "rationale": rationale,
        "source_ids": ids if ids is not None else [
            "GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"
        ],
    })


def reply(*, content=None, model=MODEL, finish="stop", role="assistant",
          request_id="chatcmpl-fake-unit-12345"):
    return json.dumps({
        "id": request_id, "model": model,
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": role, "content": (
                         content if content is not None else output()
                     )}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 65,
                  "total_tokens": 185},
    }).encode("utf8")


def at_1645():
    from pathlib import Path
    obj = json.loads(Path("samples/inputs/yagi_1645_lucyen.json").read_text("utf8"))
    obj["sample_mode"] = False
    return RunRequest.from_dict(obj)


class FakeDirectNemotronTransportTests(unittest.TestCase):
    def test_all_four_owner_authorization_gates_fail_closed(self):
        for missing in CONSENT:
            with self.subTest(missing=missing):
                config = {k: v for k, v in CONSENT.items() if k != missing}
                calls = []
                with patch.dict(os.environ, config, clear=True):
                    result = NvidiaNemotronDirect(
                        transport=lambda req: calls.append(req) or (200, reply())
                    ).chat(USER)
                self.assertEqual(len(calls), 0)
                self.assertFalse(result.network_called)
                self.assertNotIn(result.status, ("REAL_MODEL_RESPONSE", "REAL_SUCCESS"))
        self.assertEqual(set(gates()), {
            "explicit_nvidia_direct_enabled",
            "explicit_external_research_data_consent",
            "explicit_replacement_model_approval",
            "nvidia_api_key_present",
        })

    def test_old_consent_never_authorizes_replacement_model(self):
        calls = []
        old_consent = {
            k: v for k, v in CONSENT.items()
            if k != "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED"
        }
        with patch.dict(os.environ, old_consent, clear=True):
            result = NvidiaNemotronDirect(
                transport=lambda req: calls.append(req) or (200, reply())
            ).chat(USER)
        self.assertEqual(calls, [])
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.detail, "NVIDIA_35_VL_MODEL_APPROVAL_MISSING")
        self.assertFalse(result.network_called)

    def test_fake_transport_must_be_unit_only_even_with_valid_200(self):
        calls = []
        def fake(req):
            calls.append(req)
            return 200, reply()
        with patch.dict(os.environ, CONSENT, clear=True):
            value = NvidiaNemotronDirect(transport=fake).chat(USER)
        self.assertEqual(value.status, "UNIT_CONTRACT_ONLY")
        self.assertTrue(value.test_transport)
        self.assertFalse(value.network_called)
        self.assertEqual(value.returned_model, MODEL)
        self.assertEqual(value.usage["total_tokens"], 185)
        self.assertEqual(len(calls), 1)
        sent = calls[0]
        self.assertEqual(sent.full_url, ENDPOINT)
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(sent.get_header("Authorization"), "Bearer "+KEY)
        sent_body = json.loads(sent.data)
        self.assertEqual(sent_body["model"], MODEL)
        self.assertEqual(sent_body["max_tokens"], MAX_TOKENS)
        self.assertEqual(MODEL, "nvidia/nemotron-3.5-super-vl-120b-a12b")
        self.assertEqual(sent_body["reasoning_effort"], "none")
        self.assertFalse(sent_body["stream"])
        self.assertNotIn(KEY, json.dumps(value.public_receipt()))

    def test_model_substitution_and_truncated_completion_fail(self):
        for kwargs in (
            {"model": "meta/llama3-8b-instruct"},
            {"model": "nvidia/nemotron-3-super-120b-a12b"},
            {"finish": "length"},
            {"role": "tool"},
            {"request_id": "../../path-traversal"},
        ):
            with self.subTest(kwargs=kwargs):
                with patch.dict(os.environ, CONSENT, clear=True):
                    result = NvidiaNemotronDirect(
                        transport=lambda req: (200, reply(**kwargs))
                    ).chat(USER)
                self.assertEqual(result.status, "BLOCKED")
                self.assertIsNone(result.text)

    def test_redirect_proxy_and_http_statuses_not_success(self):
        for status in (201, 202, 302, 401, 402, 429, 500):
            with self.subTest(status=status):
                with patch.dict(os.environ, CONSENT, clear=True):
                    result = NvidiaNemotronDirect(
                        transport=lambda req: (status, reply())
                    ).chat(USER)
                self.assertNotEqual(result.status, "REAL_MODEL_RESPONSE")
                self.assertIsNone(result.text)
        for code, expected in ((401, "UNAUTHORIZED"),
                               (402, "NO_FREE_CREDITS"),
                               (429, "RATE_LIMITED")):
            def fail(req):
                raise urllib.error.HTTPError(ENDPOINT, code, "no key", None, None)
            with patch.dict(os.environ, CONSENT, clear=True):
                result = NvidiaNemotronDirect(transport=fail).chat(USER)
            self.assertEqual(result.status, expected)

    def test_malformed_response_never_accepted(self):
        for body in (b"<html>fake</html>", b"[]", b"{}", b"x"*262145):
            with self.subTest(body=body[:30]):
                with patch.dict(os.environ, CONSENT, clear=True):
                    result = NvidiaNemotronDirect(
                        transport=lambda req: (200, body)
                    ).chat(USER)
                self.assertEqual(result.status, "BLOCKED")

    def test_prompt_size_roles_and_secret_not_in_receipt(self):
        invalid = (
            [{"role": "assistant", "content": "abc"}],
            [{"role": "user", "content": "p"*13000}],
            [{"role": "user", "content": ""}],
            [{"role": "tool", "content": "cannot"}],
        )
        for messages in invalid:
            with patch.dict(os.environ, CONSENT, clear=True):
                value = NvidiaNemotronDirect(transport=lambda req: (
                    200, reply()
                )).chat(messages)
            self.assertEqual(value.status, "BLOCKED")
            self.assertEqual(value.detail, "NVIDIA_SAFE_PROMPT_REJECTED")
            self.assertFalse(value.network_called)
            self.assertNotIn(KEY, json.dumps(value.public_receipt()))

    def test_no_untrusted_reply_promotion_without_model_and_safe_role(self):
        for bad in (
            {"content": "x", "model": "nvidia/fake", "rid": "chat123"},
            {"content": "x", "model": MODEL, "rid": "evil /path"},
        ):
            data = reply(content=bad["content"], model=bad["model"],
                         request_id=bad["rid"])
            with self.assertRaises(ValueError):
                _parse_response(data)


class NemotronDecisionAgentContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.trace = JsonlTrace(Path(self.temp.name)/"trace.jsonl", "test-nvidia")
        self.request = at_1645()
        from evidencetrail.firewall import filter_sources
        self.sources = filter_sources(
            all_catalog(), self.request.as_of_utc,
            ReplayMode.REPORTED_DATELINE_REPLAY,
        )[0]

    def agent(self, response_content=None):
        transport_calls = []
        def fake(req):
            transport_calls.append(req)
            return 200, reply(content=response_content)
        agent = DecisionAgent(
            self.trace, nvidia_provider=NvidiaNemotronDirect(transport=fake)
        )
        return agent, transport_calls

    def test_nvidia_model_agreement_is_unit_only_and_verified_citations(self):
        agent, calls = self.agent()
        with patch.dict(os.environ, CONSENT, clear=True):
            draft = agent.run(self.request, self.sources, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(draft.nominated_verdict, Verdict.WARN)
        self.assertTrue(draft.model_route.startswith("nvidia/"))
        n = [s for s in agent.sponsor_calls if s.provider == "nvidia"]
        self.assertEqual(len(n), 1)
        self.assertEqual(n[0].outcome, SponsorOutcome.UNIT_CONTRACT_ONLY)
        self.assertIsNone(n[0].invocation_id)
        self.assertTrue(
            {"GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"}
            .issubset({c.source_id for c in draft.citations})
        )
        self.assertIn("SIMULATED coordinator watch", draft.rationale)

    def test_remote_model_must_cite_both_watch_prerequisites(self):
        for selected in (["GOV-2024-09-08-1637"],
                         ["SYN-CAP-YAGI-ALPHA-LUCYEN"], []):
            with self.subTest(selected=selected):
                agent, calls = self.agent(response_content=output(ids=selected))
                with patch.dict(os.environ, CONSENT, clear=True):
                    draft = agent.run(self.request, self.sources, [])
                self.assertEqual(len(calls), 1)
                self.assertEqual(agent.sponsor_calls[0].outcome,
                                 SponsorOutcome.BLOCKED)
                self.assertEqual(draft.nominated_verdict,
                                 Verdict.INSUFFICIENT_EVIDENCE)
                self.assertIn("nvidia_direct_model_required_but_not_verified",
                              draft.missing_facts)

    def test_model_can_never_substitute_false_operational_rationale(self):
        injected = output(rationale="THIS IS AN ACTUAL 2024 EVACUATION ORDER.")
        agent, calls = self.agent(response_content=injected)
        with patch.dict(os.environ, CONSENT, clear=True):
            draft = agent.run(self.request, self.sources, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(agent.sponsor_calls[0].outcome,
                         SponsorOutcome.UNIT_CONTRACT_ONLY)
        self.assertNotIn("ACTUAL 2024 EVACUATION ORDER", draft.rationale)
        self.assertIn("SIMULATED coordinator watch", draft.rationale)

    def test_nvidia_disagrees_with_reducer_agent_abstains(self):
        agent, calls = self.agent(response_content=output(verdict="NO_WARN"))
        with patch.dict(os.environ, CONSENT, clear=True):
            draft = agent.run(self.request, self.sources, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(draft.nominated_verdict,
                         Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("model_disagreed_with_safety_gate", draft.missing_facts)
        self.assertFalse(any(s.outcome == SponsorOutcome.REAL_SUCCESS
                             for s in agent.sponsor_calls))

    def test_nvidia_cites_future_or_ineligible_sources_blocked(self):
        bogus = output(ids=["GOV-2024-09-09-1540"])
        agent, calls = self.agent(response_content=bogus)
        with patch.dict(os.environ, CONSENT, clear=True):
            draft = agent.run(self.request, self.sources, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [s.outcome for s in agent.sponsor_calls],
            [SponsorOutcome.BLOCKED],
        )
        self.assertEqual(draft.model_route, "deterministic_reducer_offline_or_fallback")
        self.assertNotIn("GOV-2024-09-09-1540",
                         [c.source_id for c in draft.citations])

    def test_no_egress_in_sample_even_with_valid_flags(self):
        agent, calls = self.agent()
        self.request.sample_mode = True
        with patch.dict(os.environ, CONSENT, clear=True):
            draft = agent.run(self.request, self.sources, [])
        self.assertEqual(calls, [])
        self.assertEqual(draft.nominated_verdict, Verdict.WARN)
        self.assertFalse(any(c.provider == "nvidia" for c in agent.sponsor_calls))

    def test_one_nvidia_call_even_if_agent_retries(self):
        agent, calls = self.agent()
        with patch.dict(os.environ, CONSENT, clear=True):
            agent.run(self.request, self.sources, [])
            agent.run(self.request, self.sources, [])
        self.assertEqual(len(calls), 1)

    def test_cloud_consent_cannot_be_forged_by_runrequest(self):
        agent, calls = self.agent()
        with patch.dict(os.environ, {
            "NVIDIA_API_KEY": KEY,
            "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
        }, clear=True):
            agent.run(self.request, self.sources, [])
        self.assertEqual(calls, [])
        self.assertTrue(any(c.outcome == SponsorOutcome.BLOCKED
                            for c in agent.sponsor_calls))

    def test_model_input_has_no_raw_excerpts_user_question_or_secret(self):
        agent, calls = self.agent()
        self.request.question = "CONFIDENTIAL_PERSONAL_QUESTION_SENTINEL"
        with patch.dict(os.environ, CONSENT, clear=True):
            agent.run(self.request, self.sources, [])
        self.assertEqual(len(calls), 1)
        raw = calls[0].data.decode("utf8")
        self.assertNotIn("CONFIDENTIAL_PERSONAL_QUESTION_SENTINEL", raw)
        self.assertNotIn(KEY, raw)
        self.assertNotIn("excerpt_sha256", raw)
        self.assertIn("paraphrase_untrusted_data", raw)
        self.assertIn("FICTIONAL", raw.upper())


if __name__ == "__main__":
    unittest.main()
