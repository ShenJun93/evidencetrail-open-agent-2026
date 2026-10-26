"""Counterfactual claim-integrity attacks: numeric citations alone do not prove prose."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from unittest import TestCase

from evidencetrail.adapters.nvidia_lightning import (
    NvidiaLightningError, _parse_output, _narrative_risk_flags,
    _source_bound_input, chat_public_evidence, check_grounding,
)
from tests.test_nvidia_lightning_zetaris import case, response


KEY = "unit-test-is-not-an-actual-api-key-1234"


def invoke(truth, rows, reply=None):
    calls = []
    def mock_transport(req):
        calls.append(req)
        return 200, response(proposal=reply)
    result = chat_public_evidence(key=KEY, truth=truth, selected_rows=rows,
                                  transport=mock_transport)
    return result, calls


class ClaimFaithfulnessAdversarialTests(TestCase):
    def setUp(self):
        self.truth, self.rows = case()

    def test_verbatim_rationale_never_shown_as_verified_explanation(self):
        p = json.loads(json.loads(response())["choices"][0]["message"]["content"])
        p["rationale"] = (
            "The original source was authenticated and residents must evacuate, "
            "and 155 mph from a future advisory is valid now."
        )
        r, calls = invoke(self.truth, self.rows, p)
        self.assertEqual(len(calls), 1)
        self.assertEqual(r["status"], "INJECTED_CONTRACT_ONLY")
        self.assertTrue(r["grounding"]["grounded_against_sql_selection"])
        self.assertTrue(r["model_rationale_quarantined"])
        self.assertFalse(r["grounding"]["model_rationale_exposed_as_trusted_explanation"])
        self.assertFalse(r["grounding"]["semantic_entailment_of_arbitrary_model_text_proven"])
        self.assertIn("AMBIGUOUS_AUTHENTICATION_ASSERTION",
                      r["grounding"]["model_rationale_risk_flags"])
        self.assertIn("UNSUPPORTED_OPERATIONAL_RECOMMENDATION",
                      r["grounding"]["model_rationale_risk_flags"])
        self.assertNotIn("must evacuate",json.dumps(r))
        self.assertNotIn("155 mph",r["trusted_explanation"]["explanation"])
        self.assertTrue(r["trusted_explanation"]["derived_without_model_free_text"])
        self.assertEqual(r["grounding"]["model_rationale_sha256"],
                         sha256(p["rationale"].encode()).hexdigest())

    def test_trusted_claims_are_typed_and_not_a_forecast(self):
        result,_ = invoke(self.truth, self.rows)
        claims=result["trusted_explanation"]["typed_claims"]
        self.assertEqual(len(claims),2)
        self.assertEqual([c["value"] for c in claims],[100,51])
        self.assertEqual([c["source_id"] for c in claims],
                         ["NHC-AL142024-PUBLIC-008","FL-EO-24-215"])
        self.assertEqual(claims[0]["issue_clock"],"2024-10-07T09:00:00Z")
        self.assertIsNone(claims[1].get("issue_clock"))
        self.assertEqual(claims[1]["clock_kind"],"DISPLAYED_LOCAL_CALENDAR_DATE_ONLY")
        self.assertFalse(claims[0]["first_publication_authenticated"])
        self.assertFalse(result["trusted_explanation"]["arbitrary_llm_narrative_entailment_proven"])
        self.assertIn("NOT an emergency warning",result["trusted_explanation"]["explanation"])

    def test_forged_wind_field_refused_before_provider(self):
        altered=deepcopy(self.rows)
        target=next(r for r in altered if r["source_id"]=="NHC-AL142024-PUBLIC-008")
        target["value_int"]="155"
        with self.assertRaisesRegex(NvidiaLightningError,"SELECTED_SQL_SOURCE_BINDING_REFUSED"):
            invoke(self.truth,altered)

    def test_forged_florida_count_refused_before_provider(self):
        altered=deepcopy(self.rows)
        target=next(r for r in altered if r["source_id"]=="FL-EO-24-215")
        target["value_int"]=99
        with self.assertRaisesRegex(NvidiaLightningError,"SELECTED_SQL_SOURCE_BINDING_REFUSED"):
            invoke(self.truth,altered)

    def test_laundered_earlier_clock_refused_before_provider(self):
        altered=deepcopy(self.rows)
        altered[0]["issue_utc"]="2024-10-07T07:00:00Z"
        with self.assertRaises(NvidiaLightningError):
            invoke(self.truth,altered)

    def test_false_official_link_and_issuer_refused(self):
        for field,value in [
            ("locator","https://example.invalid/same-case"),
            ("issuer_family","NOAA_NHC"),
            ("claim_type","maximum_sustained_wind_mph")
        ]:
            with self.subTest(field=field):
                altered=deepcopy(self.rows)
                row=next(r for r in altered if r["source_id"]=="FL-EO-24-215")
                row[field]=value
                with self.assertRaisesRegex(NvidiaLightningError,"SELECTED_SQL_SOURCE_BINDING_REFUSED"):
                    invoke(self.truth,altered)

    def test_tampered_excerpt_and_resigned_digest_still_refused(self):
        for resign in [False,True]:
            altered=deepcopy(self.rows)
            altered[0]["excerpt"]="The Governor has confirmed an unsupported new claim."
            if resign:
                altered[0]["excerpt_sha256"]=sha256(altered[0]["excerpt"].encode()).hexdigest()
            with self.subTest(resign=resign),self.assertRaisesRegex(
                NvidiaLightningError,"SELECTED_SQL_EXCERPT_DIGEST_REFUSED"
            ):
                invoke(self.truth,altered)

    def test_suspicious_authenticated_word_from_original_live_receipt_quarantined(self):
        phrase=("The latest authenticated NHC maximum sustained wind is 100 mph "
                "but the original webpage public posting has no proof")
        self.assertEqual(_narrative_risk_flags(phrase),
                         ["AMBIGUOUS_AUTHENTICATION_ASSERTION"])
        p=json.loads(json.loads(response())["choices"][0]["message"]["content"])
        p["rationale"]=phrase
        result,_=invoke(self.truth,self.rows,p)
        self.assertNotIn("latest authenticated",json.dumps(result).lower())

    def test_safe_sounding_prose_is_still_not_semantically_proven(self):
        r,_=invoke(self.truth,self.rows)
        self.assertFalse(r["grounding"]["model_rationale_is_authoritatively_verified"])
        self.assertFalse(r["trusted_explanation"]["arbitrary_llm_narrative_entailment_proven"])
        self.assertEqual(r["grounding"]["model_rationale_risk_flags"],[])

    def test_false_first_publication_and_dangerous_guidance_flags(self):
        flags=_narrative_risk_flags(
            "The source was first published at 09:00, independently verified. "
            "It is safe to stay at home.")
        self.assertIn("UNSUPPORTED_FIRST_PUBLICATION_ASSERTION",flags)
        self.assertIn("AMBIGUOUS_AUTHENTICATION_ASSERTION",flags)
        self.assertIn("UNSUPPORTED_OPERATIONAL_RECOMMENDATION",flags)

    def test_no_extra_citation_from_future_claim(self):
        p=json.loads(json.loads(response())["choices"][0]["message"]["content"])
        p["source_ids"].append("NHC-AL142024-PUBLIC-010")
        r,_=invoke(self.truth,self.rows,p)
        self.assertFalse(r["grounding"]["grounded_against_sql_selection"])
        self.assertIsNone(r["trusted_explanation"])
        self.assertEqual(r["status"],"INJECTED_CONTRACT_ONLY")

    def test_response_mode_envelope_still_requires_exact_identity(self):
        r,_=invoke(self.truth,self.rows)
        self.assertTrue(r["injected_transport"])
        self.assertFalse(r["real_nvidia_network_called"])
        self.assertFalse(r["organizer_sponsor_eligibility_certified"])


if __name__=="__main__":
    import unittest
    unittest.main()
