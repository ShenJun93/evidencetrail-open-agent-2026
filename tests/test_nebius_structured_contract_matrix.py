"""Nebius offline structured-response matrix. No cloud call or user key."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from evidencetrail.adapters.nebius_token_factory import MODEL, ENDPOINT, NebiusTokenFactory
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.models import Verdict, SponsorOutcome
from evidencetrail.traces import JsonlTrace
from run_nvidia_nemotron_preflight import public_sample_case

FAKE_KEY = "UNIT_FAKE_KEY_NEVER_SENT_LIVE_123456789"
FLAGS = {
    "NEBIUS_API_KEY": FAKE_KEY,
    "EVIDENCETRAIL_NEBIUS_ENABLED": "true",
    "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED": "true",
}
PUBLIC = "GOV-2024-09-08-1637"
CAPACITY = "SYN-CAP-YAGI-ALPHA-LUCYEN"


def base():
    return {
        "proposed_verdict": "WARN",
        "rationale": "FICTIONAL historical research, not operational.",
        "source_ids": [PUBLIC, CAPACITY],
    }


def envelope(content):
    return json.dumps({
        "id": "chatcmpl-nebius-fixture-0123456789",
        "model": MODEL,
        "choices": [{"finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
    }).encode("utf8")


class NebiusStructuredMatrix(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.request, self.sources = public_sample_case()
        self.assertFalse(self.request.sample_mode)

    def trial(self, item):
        text = item if isinstance(item, str) else json.dumps(item)
        calls = []
        client = NebiusTokenFactory(
            transport=lambda request: (calls.append(request) or
                                       (200, envelope(text)))
        )
        agent = DecisionAgent(
            JsonlTrace(self.path / "matrix.jsonl", self.request.run_id),
            nebius_provider=client,
        )
        with patch.dict(os.environ, FLAGS, clear=True):
            draft = agent.run(self.request, self.sources, memories=[])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].full_url, ENDPOINT)
        payload = json.loads(calls[0].data)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["model"], MODEL)
        self.assertFalse(payload["stream"])
        self.assertFalse(agent.nebius_transport_receipt["network_called"])
        self.assertTrue(agent.nebius_transport_receipt["injected_transport"])
        self.assertFalse(agent.nebius_transport_receipt["nvidia_direct_sponsor_receipt"])
        self.assertNotIn(FAKE_KEY, json.dumps(agent.nebius_transport_receipt))
        return draft, agent

    def blocked(self, item):
        draft, agent = self.trial(item)
        self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertEqual(agent.sponsor_calls[-1].outcome, SponsorOutcome.BLOCKED)

    def test_valid_fixture_is_unit_only(self):
        draft, agent = self.trial(base())
        self.assertEqual(draft.nominated_verdict, Verdict.WARN)
        self.assertEqual(agent.sponsor_calls[-1].outcome,
                         SponsorOutcome.UNIT_CONTRACT_ONLY)
        self.assertIn("_injected_unit_transport", draft.model_route)

    def test_fenced_json_refused(self):
        fence = chr(96) * 3
        self.blocked(fence + "json\n" + json.dumps(base()) + "\n" + fence)

    def test_extra_key_refused(self):
        item = base()
        item["confidence"] = 1.0
        self.blocked(item)

    def test_missing_key_refused(self):
        item = base()
        item.pop("source_ids")
        self.blocked(item)

    def test_forged_citation_refused(self):
        item = base()
        item["source_ids"] = [PUBLIC, "HALLUCINATED"]
        self.blocked(item)

    def test_without_capacity_refused(self):
        item = base()
        item["source_ids"] = [PUBLIC]
        self.blocked(item)

    def test_without_government_witness_refused(self):
        item = base()
        item["source_ids"] = [CAPACITY]
        self.blocked(item)

    def test_empty_rationale_refused(self):
        item = base()
        item["rationale"] = ""
        self.blocked(item)

    def test_non_list_citations_refused(self):
        item = base()
        item["source_ids"] = PUBLIC
        self.blocked(item)

    def test_model_rule_disagreement_abstains(self):
        item = base()
        item["proposed_verdict"] = "NO_WARN"
        draft, agent = self.trial(item)
        self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("model_disagreed_with_safety_gate", draft.missing_facts)
        self.assertEqual(agent.sponsor_calls[-1].outcome,
                         SponsorOutcome.UNIT_CONTRACT_ONLY)


if __name__ == "__main__":
    unittest.main()
