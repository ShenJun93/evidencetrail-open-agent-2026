"""No-cost adversarial tests for pinned NVIDIA Nemotron 3.5 Lightning route."""
from __future__ import annotations

from copy import deepcopy
import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from evidencetrail.adapters.nvidia_lightning import (
    MODEL, ENDPOINT, NvidiaLightningError,
    _parse_output, chat_public_evidence, check_grounding,
)
from evidencetrail.zetaris_cross_issuer import evaluate_sql_rows
from run_zetaris_cross_issuer import import_rows
import run_nvidia_lightning_zetaris as runner


def case():
    nhc, florida = import_rows()
    actual = evaluate_sql_rows(nhc, florida, clock=runner.CLOCK)
    source_set = set(actual["selected_original_ids"])
    rows = [x for x in nhc + florida if x["source_id"] in source_set]
    return actual, rows


def response(*, model=MODEL, finish="stop", proposal=None):
    if proposal is None:
        proposal = {
            "latest_nhc_mph": 100,
            "florida_emergency_counties": 51,
            "source_ids": ["NHC-AL142024-PUBLIC-008", "FL-EO-24-215"],
            "historical_first_publication_authenticated": False,
            "rationale": "Reported as-of metadata only; original first-publication is unproven.",
        }
    return json.dumps({
        "id": "chatcmpl-fixture-contract-123456",
        "model": model,
        "choices": [{
            "finish_reason": finish,
            "message": {"role": "assistant", "content": json.dumps(proposal)},
        }],
        "usage": {"prompt_tokens": 220, "completion_tokens": 70, "total_tokens": 290},
    }).encode("utf-8")


class LightningPinnedTransportTests(TestCase):
    def test_exact_url_model_and_input_derived_from_selected_sql(self):
        truth, selected = case()
        calls = []
        def mock_transport(request):
            calls.append(request)
            return 200, response()
        result = chat_public_evidence(key="unit-test-non-secret-placeholder",
                                      truth=truth, selected_rows=selected,
                                      transport=mock_transport)
        self.assertEqual(result["status"], "INJECTED_CONTRACT_ONLY")
        self.assertFalse(result["real_nvidia_network_called"])
        self.assertTrue(result["grounding"]["grounded_against_sql_selection"])
        self.assertFalse(result["organizer_sponsor_eligibility_certified"])
        self.assertEqual(len(calls), 1)
        req=calls[0]
        self.assertEqual(req.full_url, ENDPOINT)
        payload=json.loads(req.data.decode("utf8"))
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["stream"], False)
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        messages=str(payload["messages"])
        self.assertIn("FL-EO-24-215", messages)
        self.assertNotIn("NHC-AL142024-PUBLIC-010", messages)

    def test_wrong_model_identity_is_fatal(self):
        truth, selected = case()
        with self.assertRaisesRegex(NvidiaLightningError,"MODEL_IDENTITY_MISMATCH"):
            chat_public_evidence(key="unit-test-key-placeholder",truth=truth,
                selected_rows=selected,transport=lambda r:(200,response(model="fake/lightning")))

    def test_incomplete_model_completion_is_fatal(self):
        truth, selected = case()
        with self.assertRaisesRegex(NvidiaLightningError,"NOT_COMPLETE"):
            chat_public_evidence(key="unit-test-key-placeholder",truth=truth,
                selected_rows=selected,transport=lambda r:(200,response(finish="length")))

    def test_invented_future_sources_and_overclaim_fail_grounding(self):
        truth,selected=case()
        p=json.loads(json.loads(response())["choices"][0]["message"]["content"])
        p["source_ids"].append("NHC-AL142024-PUBLIC-010")
        fake=_parse_output(response(proposal=p))
        self.assertFalse(check_grounding(fake,truth)["grounded_against_sql_selection"])
        p["source_ids"].remove("NHC-AL142024-PUBLIC-010")
        p["historical_first_publication_authenticated"]=True
        fake=_parse_output(response(proposal=p))
        self.assertFalse(check_grounding(fake,truth)["grounded_against_sql_selection"])

    def test_wrong_numbers_and_pivotal_citation_are_not_accepted(self):
        truth, selected=case()
        p=json.loads(json.loads(response())["choices"][0]["message"]["content"])
        p["latest_nhc_mph"]=155
        self.assertFalse(check_grounding(_parse_output(response(proposal=p)),truth)[
            "grounded_against_sql_selection"])
        p["latest_nhc_mph"]=100
        p["source_ids"]=["FL-EO-24-214"]
        self.assertFalse(check_grounding(_parse_output(response(proposal=p)),truth)[
            "grounded_against_sql_selection"])

    def test_strict_or_local_fixture_does_not_authorize_vendor(self):
        truth,selected=case()
        truth=deepcopy(truth)
        truth["sql_decoded_issuer_row_counts"]={"NOAA_NHC":0,"FLORIDA_GOVERNOR":0}
        with self.assertRaisesRegex(NvidiaLightningError,"REQUIRED_REAL_SQL_TRUTH"):
            chat_public_evidence(key="unit-test-key-placeholder",
                truth=truth,selected_rows=selected,
                transport=lambda r:(_ for _ in ()).throw(
                    AssertionError("should not contact provider")))
        truth,selected=case()
        with self.assertRaisesRegex(NvidiaLightningError,"SOURCE_SELECTION_MISMATCH"):
            chat_public_evidence(key="unit-test-key-placeholder",
                truth=truth,selected_rows=selected[:2],
                transport=lambda r:(_ for _ in ()).throw(
                    AssertionError("should not contact provider")))

    def test_no_free_or_curated_egress_approval_means_no_query(self):
        with tempfile.TemporaryDirectory() as td, patch.object(
                runner,"read_local_env",return_value={"NVIDIA_API_KEY":"unit-test-api",
                "ZETARIS_REST_URL":"http://127.0.0.1:8888/api/v1.0",
                "ZETARIS_ORG_ID":"1","ZETARIS_API_KEY":"unit-test-zeta"}),patch.object(
                runner,"query_sql_editor",side_effect=AssertionError("no SQL allowed")
              ):
            rc=runner.main(["--live","--receipt",str(Path(td)/"gate.json")])
            self.assertEqual(rc,2)
            report=json.loads((Path(td)/"gate.json").read_text())
            self.assertEqual(report["status"],"BLOCKED_USER_APPROVAL_FLAGS_MISSING")
            self.assertEqual(report["nvidia_network_requests_attempted"],0)
            self.assertEqual(report["zetaris_query_attempts"],0)

    def test_offline_preflight_never_calls_any_provider(self):
        with tempfile.TemporaryDirectory() as td,patch.object(
                runner,"read_local_env",return_value={}),patch.object(
                runner,"query_sql_editor",side_effect=AssertionError("offline query")),patch.object(
                runner,"chat_public_evidence",side_effect=AssertionError("offline model")):
            receipt=Path(td)/"check.json"
            code=runner.main(["--check","--receipt",str(receipt)])
            self.assertEqual(code,0)
            self.assertEqual(json.loads(receipt.read_text())["status"],
                             "OFFLINE_CONFIG_CHECK_ONLY")

    def test_bad_response_envelope_rejected_without_fallback(self):
        for raw in (b"",b"{}",b"[]",b"not json",response(model="private/nvidia/lightning"),
                    response(finish="length"),response(proposal={"a":"b"})):
            with self.subTest(raw=raw[:20]),self.assertRaises(NvidiaLightningError):
                _parse_output(raw)


if __name__=="__main__":
    import unittest
    unittest.main()
