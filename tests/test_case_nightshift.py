"""Injected contract checks only; these are not vendor execution evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evidencetrail.adapters.meterless import ProbeResult
from evidencetrail.case_investigator import example_case, investigate_case
from evidencetrail.case_nightshift import propose_local_explanation


class FakeLocalProvider:
    def __init__(self, *, routed="local-runtime/unit", value=12):
        self.routed, self.value, self.calls = routed, value, []

    def models(self):
        return ProbeResult("online", "unit fixture", "http://127.0.0.1:1/v1",
                           ["meterless/local"])

    def chat(self, prompt, model, max_tokens):
        self.calls.append((prompt, model, max_tokens))
        return {"ok": True, "text": json.dumps({
            "claim_key": "STOCK", "before_value": 25, "after_value": self.value,
            "source_ids": ["STOCK-LEDGER", "STOCK-OLD"],
            "explanation": "Removing the current records exposes the older stock declaration.",
        }), "raw_id": "unit-only", "route_receipt": {"routed_model": self.routed}}


class FakeUnavailableProvider(FakeLocalProvider):
    def chat(self, prompt, model, max_tokens):
        self.calls.append((prompt, model, max_tokens))
        return {"ok": False, "http": 400, "text": None}


class FakeTemplateTextProvider(FakeLocalProvider):
    def chat(self, prompt, model, max_tokens):
        self.calls.append((prompt, model, max_tokens))
        return {"ok": True, "text": json.dumps({
            "explanation": "The untrusted DATA record changed from 25 to 12 using before_value."
        }), "raw_id": "unit-only", "route_receipt": {"routed_model": self.routed}}


class LocalProposalTests(unittest.TestCase):
    def setUp(self):
        self.report = investigate_case(example_case("warehouse"),
                                       withdrawn_source_ids=["STOCK-CHECK", "STOCK-LEDGER"])

    def test_accepted_structure_cannot_change_deterministic_claim(self):
        provider = FakeLocalProvider()
        before = json.dumps(self.report, sort_keys=True)
        result = propose_local_explanation(self.report, provider)
        self.assertEqual(result["status"], "STRUCTURE_ACCEPTED_PROSE_UNVERIFIED")
        self.assertEqual(result["proposal"]["before_value"], 25)
        self.assertEqual(result["proposal"]["after_value"], 12)
        self.assertFalse(result["proposal"]["explanation_semantics_independently_verified"])
        self.assertEqual(provider.calls[0][1:], ("meterless/local", 80))
        self.assertIn("natural English sentence", provider.calls[0][0])
        self.assertIn("before_value", provider.calls[0][0])
        self.assertIn("Never print JSON field names", provider.calls[0][0])
        self.assertEqual(json.dumps(self.report, sort_keys=True), before)

    def test_wrong_value_or_nonlocal_route_is_rejected(self):
        self.assertEqual(propose_local_explanation(
            self.report, FakeLocalProvider(value=40))["status"],
            "PROPOSAL_REJECTED_BY_DETERMINISTIC_CHECK")
        self.assertEqual(propose_local_explanation(
            self.report, FakeLocalProvider(routed="cloud/unit"))["status"],
            "LOCAL_ROUTE_NOT_PROVEN")

    def test_prompt_meta_and_placeholder_text_is_rejected(self):
        result = propose_local_explanation(self.report, FakeTemplateTextProvider())
        self.assertEqual(result["status"], "PROPOSAL_REJECTED_BY_DETERMINISTIC_CHECK")
        self.assertEqual(result["rejection_code"], "EXPLANATION_META_OR_PLACEHOLDER_TEXT")

    def test_rejected_runtime_request_is_not_counted_as_model_completion(self):
        result = propose_local_explanation(self.report, FakeUnavailableProvider())
        self.assertEqual(result["status"], "CHAT_UNAVAILABLE")
        self.assertTrue(result["request_attempted"])
        self.assertFalse(result["model_called"])
        self.assertEqual(result["http"], 400)

    def test_cli_opt_in_writes_separate_model_receipt(self):
        from run_case_investigation import main
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "result.json"
            with patch("run_case_investigation.propose_local_explanation",
                       return_value={"status": "STRUCTURE_ACCEPTED_PROSE_UNVERIFIED",
                                     "model_called": True, "request_id": "injected-only"}) as probe:
                code = main(["--example", "warehouse", "--withdraw", "STOCK-CHECK",
                             "STOCK-LEDGER", "--local-nightshift", "--receipt", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(probe.call_count, 1)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["experiment"]["selected_claims_after"]["STOCK"]["value"], 12)
            self.assertTrue(saved["model_called"])
            self.assertEqual(saved["nightshift_local_proposal"]["request_id"], "injected-only")


if __name__ == "__main__":
    unittest.main()
