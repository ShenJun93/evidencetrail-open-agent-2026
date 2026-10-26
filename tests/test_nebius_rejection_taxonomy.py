"""Nebius fixed-code diagnosis: mock fixtures only, zero external inference."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.nebius_token_factory import (
    MODEL, NebiusTokenFactory,
)
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.models import SponsorOutcome, Verdict
from evidencetrail.nebius_proposal_contract import (
    DIAGNOSTIC_CODES, NebiusProposalViolation, validate_nebius_proposal,
)
from evidencetrail.traces import JsonlTrace
from run_nvidia_nemotron_preflight import public_sample_case
from run_nebius_one_shot_preflight import main as one_shot

KEY = "UNIT_PLACEHOLDER_KEY_NOT_VALID_01234567890123"
FLAGS = {
    "NEBIUS_API_KEY": KEY,
    "EVIDENCETRAIL_NEBIUS_ENABLED": "true",
    "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT": "true",
    "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED": "true",
}
PUB = "GOV-2024-09-08-1637"
CAP = "SYN-CAP-YAGI-ALPHA-LUCYEN"


def valid():
    return {
        "proposed_verdict": "WARN",
        "rationale": "FICTIONAL Yagi public-research watch, not emergency advice",
        "source_ids": [PUB, CAP],
    }


def wrapped(text: str) -> bytes:
    return json.dumps({
        "id": "chatcmpl-taxonomy-unit-0123456789",
        "model": MODEL,
        "choices": [{
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": text},
        }],
    }).encode("utf8")


class NebiusTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self.request, self.eligible = public_sample_case()
        self.assertFalse(self.request.sample_mode)

    def parse(self, candidate):
        raw = candidate if candidate is None or isinstance(candidate, str) else json.dumps(candidate)
        return validate_nebius_proposal(
            raw, self.request, self.eligible, Verdict.WARN,
        )

    def reject(self, candidate, code):
        self.assertIn(code, DIAGNOSTIC_CODES)
        with self.assertRaises(NebiusProposalViolation) as ctx:
            self.parse(candidate)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(str(ctx.exception), code)
        self.assertNotIn("FICTIONAL Yagi", str(ctx.exception))

    def test_valid_fixture_accepted_without_using_model_as_source(self):
        self.assertEqual(self.parse(valid()), valid())

    def test_missing_text(self):
        self.reject(None, "JSON_TEXT_MISSING")

    def test_fenced_json_cannot_be_silently_repaired(self):
        fence = chr(96) * 3
        self.reject(fence + "json\n" + json.dumps(valid()) + "\n" + fence,
                    "JSON_SYNTAX_INVALID")

    def test_duplicate_field_rejected(self):
        text = json.dumps(valid())
        dup = text.replace('"proposed_verdict": "WARN",',
                           '"proposed_verdict": "WARN", "proposed_verdict": "WARN",')
        self.reject(dup, "JSON_DUPLICATE_KEY")

    def test_nonfinite_json_rejected(self):
        text = json.dumps(valid()).replace('"WARN"', 'NaN', 1)
        self.reject(text, "JSON_NONFINITE_CONSTANT")

    def test_deeply_nested_json_fails_closed_without_traceback_or_payload(self):
        self.reject("[" * 2200 + "0" + "]" * 2200, "JSON_NESTING_LIMIT_EXCEEDED")

    def test_excessive_json_text_is_refused_before_parsing(self):
        self.reject('"' + "x" * 20001 + '"', "JSON_TEXT_TOO_LONG")

    def test_brackets_inside_json_strings_do_not_count_as_nesting(self):
        obj = valid()
        obj["rationale"] = "scenario [{{{{ [[[ safe string"
        self.assertEqual(self.parse(obj), obj)

    def test_nonobject_json_rejected(self):
        self.reject("[]", "JSON_OBJECT_REQUIRED")

    def test_extra_key_rejected(self):
        obj = valid()
        obj["invented_confidence"] = 1.0
        self.reject(obj, "JSON_FIELDS_MISMATCH")

    def test_invalid_verdict_type_rejected(self):
        obj = valid()
        obj["proposed_verdict"] = ["WARN"]
        self.reject(obj, "JSON_VERDICT_INVALID")

    def test_empty_rationale_rejected(self):
        obj = valid()
        obj["rationale"] = "   "
        self.reject(obj, "JSON_RATIONALE_INVALID")

    def test_nonlist_ids_rejected(self):
        obj = valid()
        obj["source_ids"] = PUB
        self.reject(obj, "JSON_CITATIONS_SHAPE_INVALID")

    def test_forged_citation_rejected(self):
        obj = valid()
        obj["source_ids"] = [PUB, "HALLUCINATED_ID"]
        self.reject(obj, "CITATION_NOT_TIME_ELIGIBLE")

    def test_government_witness_missing_rejected(self):
        obj = valid()
        obj["source_ids"] = [CAP]
        self.reject(obj, "WARN_PUBLIC_DISTRICT_WITNESS_MISSING")

    def test_fictional_capacity_missing_rejected(self):
        obj = valid()
        obj["source_ids"] = [PUB]
        self.reject(obj, "WARN_FICTIONAL_CAPACITY_WITNESS_MISSING")

    def test_injected_rejection_has_only_fixed_code_in_receipt(self):
        content = json.dumps({**valid(), "source_ids": [PUB]})
        fake = NebiusTokenFactory(transport=lambda req: (200, wrapped(content)))
        with tempfile.TemporaryDirectory() as tmp:
            agent = DecisionAgent(
                JsonlTrace(Path(tmp) / "trace.jsonl", self.request.run_id),
                nebius_provider=fake,
            )
            with patch.dict(os.environ, FLAGS, clear=True):
                draft = agent.run(self.request, self.eligible, memories=[])
            self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
            self.assertEqual(
                agent.nebius_rejection_reason_code,
                "WARN_FICTIONAL_CAPACITY_WITNESS_MISSING",
            )
            receipt = agent.sponsor_calls[-1]
            self.assertEqual(receipt.outcome, SponsorOutcome.BLOCKED)
            self.assertEqual(
                receipt.contract_label, "NEBIUS_THIRD_PARTY_STRUCTURED_REPLY_REFUSED"
            )
            self.assertIn(agent.nebius_rejection_reason_code, receipt.detail)
            serial = (Path(tmp) / "trace.jsonl").read_text("utf8")
            self.assertNotIn(content, serial)
            self.assertNotIn(KEY, serial)
            self.assertIn(agent.nebius_rejection_reason_code, serial)
            self.assertFalse(agent.nebius_transport_receipt["network_called"])

    def test_one_shot_fixture_receipt_is_sanitized_and_not_vendor_proof(self):
        content = json.dumps({**valid(), "source_ids": ["INELIGIBLE_FAKE_ID"]})
        fake = NebiusTokenFactory(transport=lambda req: (200, wrapped(content)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with patch.dict(os.environ, {"NEBIUS_API_KEY": KEY}, clear=True), patch(
                "evidencetrail.agents.decision.NebiusTokenFactory",
                return_value=fake,
            ):
                result = one_shot([
                    "--live", "--confirm-nebius-third-party-host",
                    "--confirm-public-research-egress",
                    "--approve-possible-token-charges",
                    "--env-file", str(path / "missing.env"),
                    "--receipt", str(path / "public-receipt.json"),
                    "--trace", str(path / "raw-trace.jsonl"),
                ])
            self.assertEqual(result, 2)
            data = json.loads((path / "public-receipt.json").read_text("utf8"))
            self.assertEqual(
                data["structured_rejection_reason_code"],
                "CITATION_NOT_TIME_ELIGIBLE",
            )
            self.assertFalse(data["network_called"])
            self.assertFalse(data["nvidia_direct_sponsor_receipt"])
            self.assertEqual(data["status"], "NEBIUS_NOT_ACCEPTED_OR_BLOCKED")
            self.assertNotIn(KEY, json.dumps(data))
            self.assertNotIn(content, json.dumps(data))


if __name__ == "__main__":
    unittest.main()
