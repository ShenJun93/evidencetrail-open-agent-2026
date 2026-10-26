"""End-to-end DecisionAgent Nebius route, injected only. NO external network."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nebius_token_factory import MODEL, NebiusTokenFactory
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.models import SponsorOutcome, Verdict
from evidencetrail.traces import JsonlTrace
from run_nvidia_nemotron_preflight import public_sample_case

FAKE_KEY = "UNIT_ONLY_NEVER_USE_OR_SEND_123456789"
APPROVAL = {
    "NEBIUS_API_KEY": FAKE_KEY,
    "EVIDENCETRAIL_NEBIUS_ENABLED": "true",
    "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED": "true",
}


def reply(ids=None, verdict="WARN", model=MODEL):
    if ids is None:
        ids = ["GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"]
    return json.dumps({
        "id": "chatcmpl-nebius-safe-unit-123",
        "model": model,
        "choices": [{
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "proposed_verdict": verdict,
                    "rationale": "FICTIONAL research scenario only",
                    "source_ids": ids,
                }),
            },
        }],
    }).encode("utf8")


class NebiusDecisionPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.request, self.eligible = public_sample_case()
        self.assertFalse(self.request.sample_mode)

    def run_agent(self, overrides, model_response):
        calls = []
        def injected(req):
            calls.append(req)
            return 200, model_response
        agent = DecisionAgent(
            JsonlTrace(Path(self.temp.name) / "nebius-test-trace.jsonl",
                       self.request.run_id),
            nebius_provider=NebiusTokenFactory(transport=injected),
        )
        with patch.dict(os.environ, overrides, clear=True):
            draft = agent.run(self.request, self.eligible, memories=[])
        return draft, agent, calls

    def test_valid_fake_model_agreement_is_unit_only_not_sponsor(self):
        draft, agent, calls = self.run_agent(APPROVAL, reply())
        self.assertEqual(len(calls), 1)
        self.assertEqual(draft.nominated_verdict, Verdict.WARN)
        self.assertIn("_injected_unit_transport", draft.model_route)
        self.assertTrue(draft.model_route.startswith("nebius/"))
        self.assertEqual(len([c for c in agent.sponsor_calls
                              if c.provider == "nebius"]), 1)
        receipt = agent.sponsor_calls[-1]
        self.assertEqual(receipt.outcome, SponsorOutcome.UNIT_CONTRACT_ONLY)
        self.assertEqual(
            receipt.contract_label, "NEBIUS_THIRD_PARTY_NOT_NVIDIA_SPONSOR"
        )
        self.assertFalse(agent.nebius_transport_receipt[
            "nvidia_direct_sponsor_receipt"])
        self.assertFalse(agent.nebius_transport_receipt["network_called"])
        self.assertNotIn(FAKE_KEY, json.dumps(agent.nebius_transport_receipt))

    def test_key_alone_abstains_and_makes_zero_calls(self):
        draft, agent, calls = self.run_agent(
            {
                "NEBIUS_API_KEY": FAKE_KEY,
                "EVIDENCETRAIL_NEBIUS_ENABLED": "true",
            }, reply(),
        )
        self.assertEqual(calls, [])
        self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn(
            "nebius_third_party_model_required_but_not_verified",
            draft.missing_facts,
        )
        self.assertEqual(agent.sponsor_calls[-1].outcome, SponsorOutcome.BLOCKED)

    def test_nebius_and_nvidia_conflict_abstain_without_either_call(self):
        draft, agent, calls = self.run_agent({
            **APPROVAL,
            "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
            "NVIDIA_API_KEY": "nvidia-mock-key-only-no-live-call",
        }, reply())
        self.assertEqual(calls, [])
        self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("external_model_routes_conflict", draft.missing_facts)
        self.assertIsNone(agent.nebius_transport_receipt)
        self.assertIsNone(agent.nvidia_transport_receipt)
        self.assertEqual(agent.sponsor_calls[-1].outcome, SponsorOutcome.BLOCKED)

    def test_ineligible_model_citation_abstains_even_with_mock_http200(self):
        draft, agent, calls = self.run_agent(
            APPROVAL, reply(ids=["FORGED-SOURCE-ID"]))
        self.assertEqual(len(calls), 1)
        self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertEqual(agent.sponsor_calls[-1].outcome, SponsorOutcome.BLOCKED)

    def test_wrong_model_id_abstains(self):
        draft, agent, calls = self.run_agent(
            APPROVAL, reply(model="private/nvidia/nemotron-3-super-120b-a12b"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertFalse(agent.nebius_transport_receipt["nvidia_direct_sponsor_receipt"])


if __name__ == "__main__":
    unittest.main()
