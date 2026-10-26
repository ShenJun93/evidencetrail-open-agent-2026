"""Forensic retrospective audit never calls provider and never promotes old prose."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest import TestCase

from evidencetrail.adapters.nvidia_lightning import MODEL, NvidiaLightningError, _parse_output
from run_nvidia_claim_boundary_audit import audit_legacy_receipt, main
from tests.test_nvidia_lightning_zetaris import response


def legacy_document():
    return {
        "kind": "EVIDENCETRAIL_NVIDIA_LIGHTNING_TWO_ISSUER_V1",
        "requested_model": MODEL,
        "status": "REAL_NVIDIA_RESPONSE_GROUNDED",
        "nvidia_network_requests_attempted": 1,
        "zetaris_query_attempts": 2,
        "sql_rows_actual": {"NOAA_NHC": 4, "FLORIDA_GOVERNOR": 3},
        "admissible_source_ids": [
            "NHC-AL142024-PUBLIC-008","FL-EO-24-214","FL-EO-24-215",
        ],
        "model_result": {
            "real_nvidia_network_called": True,
            "injected_transport": False,
            "returned_model": MODEL,
            "grounding": {
                "grounded_against_sql_selection": True,
                "rationale": (
                    "The latest authenticated NHC wind is 100 mph; first "
                    "web publication time is not established."
                ),
            },
        },
    }


class ForensicNoNewInferenceTests(TestCase):
    def test_legacy_trusted_numbers_dont_certify_free_prose(self):
        result=audit_legacy_receipt(legacy_document())
        self.assertEqual(result["status"],"LEGACY_LIVE_CALL_RATIONALE_QUARANTINED")
        self.assertFalse(result["old_gate_proved_semantic_entailment"])
        self.assertIn("AMBIGUOUS_AUTHENTICATION_ASSERTION",result["rationale_risk_flags"])
        self.assertEqual(result["new_nvidia_calls"],0)
        self.assertTrue(result["model_rationale_untrusted_and_not_shown_as_verified"])
        self.assertNotIn("latest authenticated",json.dumps(result).lower())

    def test_legacy_receipt_is_not_authenticated_by_mock(self):
        for part,value in [
            ("status","MOCK"),
            ("nvidia_network_requests_attempted",0),
            ("sql_rows_actual",{"NOAA_NHC":0,"FLORIDA_GOVERNOR":0}),
        ]:
            d=legacy_document()
            d[part]=value
            with self.subTest(part=part),self.assertRaises(ValueError):
                audit_legacy_receipt(d)

    def test_old_injected_transport_must_be_refused(self):
        d=legacy_document()
        d["model_result"]["injected_transport"]=True
        with self.assertRaisesRegex(ValueError,"LEGACY_NOT_THE_ACCEPTED"):
            audit_legacy_receipt(d)

    def test_cli_uses_ignored_report_and_refuses_overwriting(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"old.json"
            q=Path(td)/"audit.json"
            p.write_text(json.dumps(legacy_document()),encoding="utf-8")
            self.assertEqual(main(["--input",str(p),"--output",str(q)]),0)
            self.assertEqual(main(["--input",str(p),"--output",str(q)]),2)
            out=json.loads(q.read_text(encoding="utf-8"))
            self.assertEqual(out["new_nvidia_calls"],0)
            self.assertFalse(out["model_rationale_logged_verbatim_in_new_report"])

    def test_blank_rationale_envelope_is_rejected(self):
        p=json.loads(json.loads(response())["choices"][0]["message"]["content"])
        p["rationale"]="   "
        with self.assertRaisesRegex(NvidiaLightningError,"MODEL_RATIONALE_INVALID"):
            _parse_output(response(proposal=p))


if __name__=="__main__":
    import unittest
    unittest.main()
