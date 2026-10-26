"""Adversarial and factual test cases for source-withdrawal WHY explanations."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from evidencetrail.claim_ledger import ClaimLedgerRefusal
from evidencetrail.models import ReplayMode
from evidencetrail.why_counterfactual import explain_why
from run_why_source_counterfactual import evaluate,main
from run_zetaris_cross_issuer import import_rows
from tests.test_claim_ledger_transfer import (
    curated_milton, fresh_issuer_source,
)


def corpus(when="2024-10-07T11:00:00Z", *, strict=False):
    rows,pins,rules=curated_milton()
    return rows,pins,rules,explain_why(
        rows,pins,rules,as_of_utc=when,
        mode=ReplayMode.STRICT_AS_OF_2024 if strict
             else ReplayMode.REPORTED_DATELINE_REPLAY)


def removed(result,source_id):
    return next(x for x in result["source_withdrawal_interventions"]
                if x["removed_source_id"]==source_id)


def boundary(result,clock):
    return next(x for x in result["clock_boundary_interventions"]
                if x["at_boundary_utc"]==clock)


class SourceCounterfactualTests(unittest.TestCase):
    def test_11am_noaa_and_florida_attribution(self):
        _,_,_,r=corpus()
        self.assertEqual(r["status"],"CLAIMS_SELECTED")
        self.assertEqual(r["selected_claims"]["NHC_WIND"]["value"],100)
        self.assertEqual(r["selected_claims"]["NHC_WIND"]["source_id"],
                         "NHC-AL142024-PUBLIC-008")
        self.assertEqual(r["selected_claims"]["FL_ORDER"]["value"],51)
        self.assertEqual(r["selected_claims"]["FL_ORDER"]["source_id"],"FL-EO-24-215")
        self.assertFalse(r["publisher_first_publication_authenticated"])
        self.assertFalse(r["model_or_sponsor_called"])

    def test_pivotal_noaa_removal_causes_abstention(self):
        _,_,_,r=corpus()
        item=removed(r,"NHC-AL142024-PUBLIC-008")
        self.assertEqual(item["outcome"],"COUNTERFACTUAL_CLAIM_CHANGES")
        self.assertEqual(item["changed_claims"][0]["claim_key"],"NHC_WIND")
        self.assertEqual(item["changed_claims"][0]["effect"],"CLAIM_ABSTAINS")
        self.assertIsNone(item["changed_claims"][0]["after"])
        self.assertFalse(item["genuine_publisher_action_or_retraction_observed"])

    def test_pivotal_florida_removal_falls_back_to_35(self):
        _,_,_,r=corpus()
        changes=removed(r,"FL-EO-24-215")["changed_claims"]
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]["effect"],"VALUE_CHANGED")
        self.assertEqual(changes[0]["before"]["value"],51)
        self.assertEqual(changes[0]["after"]["value"],35)
        self.assertEqual(changes[0]["after"]["source_id"],"FL-EO-24-214")

    def test_all_other_sources_have_no_attribution_impact_at_11(self):
        _,_,_,r=corpus()
        pivots=sorted(x["removed_source_id"] for x in
                      r["source_withdrawal_interventions"]
                      if x["changed_claims"])
        self.assertEqual(pivots,["FL-EO-24-215","NHC-AL142024-PUBLIC-008"])
        self.assertFalse(removed(r,"NHC-AL142024-PUBLIC-010")[
            "source_was_admissible_before_removal"])
        self.assertEqual(len(r["clock_boundary_interventions"]),7)

    def test_source_order_does_not_change_causal_trace(self):
        rows,pins,rules,a=corpus()
        b=explain_why(list(reversed(rows)),pins,rules,
                      as_of_utc="2024-10-07T11:00:00Z")
        self.assertEqual(a,b)

    def test_nhc_155_at_15_falls_back_to_125_after_removal(self):
        _,_,_,r=corpus("2024-10-07T15:00:00Z")
        effect=removed(r,"NHC-AL142024-PUBLIC-010")["changed_claims"]
        self.assertEqual(len(effect),1)
        self.assertEqual(effect[0]["effect"],"VALUE_CHANGED")
        self.assertEqual(effect[0]["before"]["value"],155)
        self.assertEqual(effect[0]["after"]["value"],125)
        self.assertEqual(effect[0]["after"]["source_id"],
                         "NHC-AL142024-PUBLIC-009")

    def test_exact_issuer_and_day_only_boundaries(self):
        _,_,_,r=corpus()
        nhc=boundary(r,"2024-10-07T09:00:00Z")
        self.assertEqual(nhc["crossed_source_ids"],["NHC-AL142024-PUBLIC-008"])
        self.assertEqual(nhc["changed_claims"][0]["effect"],"CLAIM_APPEARS")
        self.assertEqual(nhc["changed_claims"][0]["after"]["value"],100)
        fl=boundary(r,"2024-10-07T04:00:00Z")
        self.assertEqual(fl["crossed_source_ids"],["FL-EO-24-215"])
        self.assertEqual(fl["changed_claims"][0]["effect"],"VALUE_CHANGED")
        self.assertEqual(fl["changed_claims"][0]["before"]["value"],35)
        self.assertEqual(fl["changed_claims"][0]["after"]["value"],51)
        self.assertTrue(fl["clock_is_policy_or_claimed_issuer_time_not_verified_first_publication"])

    def test_strict_mode_all_abstains_even_under_interventions(self):
        _,_,_,r=corpus("2024-10-08T04:00:00Z",strict=True)
        self.assertEqual(r["status"],"ABSTAIN_NO_ADMISSIBLE_CLAIMS")
        self.assertEqual(r["selected_claims"],{})
        self.assertEqual(r["clock_boundary_interventions"],[])
        self.assertTrue(all(not x["changed_claims"]
                            for x in r["source_withdrawal_interventions"]))

    def test_future_source_rehashed_alteration_refused_before_interventions(self):
        rows,pins,rules,_=corpus()
        target=next(x for x in rows if x.source_id=="NHC-AL142024-PUBLIC-010")
        target.excerpt="Fake future official report"
        target.excerpt_sha256=sha256(target.excerpt.encode()).hexdigest()
        with self.assertRaises(ClaimLedgerRefusal):
            explain_why(rows,pins,rules,as_of_utc="2024-10-07T11:00:00Z")

    def test_missing_pin_or_extra_unknown_source_refused(self):
        rows,pins,rules,_=corpus()
        changed=dict(pins)
        changed.pop("FL-EO-24-215")
        with self.assertRaisesRegex(ClaimLedgerRefusal,"MANIFEST_COVERAGE"):
            explain_why(rows,changed,rules,as_of_utc="2024-10-07T11:00:00Z")
        row,_,_=fresh_issuer_source()
        with self.assertRaisesRegex(ClaimLedgerRefusal,"MANIFEST_COVERAGE"):
            explain_why(rows+[row],pins,rules,as_of_utc="2024-10-07T11:00:00Z")

    def test_unpinned_altered_source_clock_refused(self):
        rows,pins,rules,_=corpus()
        affected=next(x for x in rows if x.source_id=="NHC-AL142024-PUBLIC-008")
        affected.issued_at_claimed_utc=affected.issued_at_claimed_utc.replace(hour=5)
        with self.assertRaises(ClaimLedgerRefusal):
            explain_why(rows,pins,rules,as_of_utc="2024-10-07T11:00:00Z")

    def test_bad_simulation_limits_refused(self):
        rows,pins,rules,_=corpus()
        for cap in (0,True,81):
            with self.subTest(cap=cap),self.assertRaisesRegex(
                ClaimLedgerRefusal,"SIMULATION_LIMIT"):
                explain_why(rows,pins,rules,as_of_utc="2024-10-07T11:00:00Z",
                            max_counterfactual_sources=cap)
        with self.assertRaisesRegex(ClaimLedgerRefusal,"TOO_MANY"):
            explain_why(rows,pins,rules,as_of_utc="2024-10-07T11:00:00Z",
                        max_counterfactual_sources=6)

    def test_generic_fictional_issuer_counterfactual_clearly_marked(self):
        row,pin,rule=fresh_issuer_source(kind=__import__(
            "evidencetrail.models",fromlist=["RecordKind"]).RecordKind.SYNTHETIC_CAPACITY)
        result=explain_why([row],{row.source_id:pin},[rule],
                           as_of_utc="2024-10-07T09:00:00Z")
        self.assertTrue(result["selected_claims"]["LAB_READING"]["fictional"])
        self.assertEqual(removed(result,row.source_id)["changed_claims"][0][
            "effect"],"CLAIM_ABSTAINS")
        self.assertFalse(result["issuer_names_are_not_independent_fact_attestation"] is False)

    def test_malicious_html_or_extra_fields_never_enter_policy(self):
        rows,pins,rules,_=corpus()
        sid="FL-EO-24-215"
        pins=dict(pins);pins[sid]=replace(pins[sid],publisher="<script>alert(1)</script>")
        with self.assertRaises(ClaimLedgerRefusal):
            explain_why(rows,pins,rules,as_of_utc="2024-10-07T11:00:00Z")

    def test_offline_cli_does_not_require_vendor(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"report.json"
            with patch("run_why_source_counterfactual.query_sql_editor",
                       side_effect=AssertionError("unexpected SQL")):
                self.assertEqual(main(["--receipt",str(path)]),0)
            loaded=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["data_origin"],
                             "OFFLINE_CURATED_FIXTURE_NOT_LIVE_SQL")
            self.assertFalse(loaded["model_or_sponsor_called"])
            self.assertEqual(main(["--receipt",str(path)]),2)

    def test_unauthorized_local_sql_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("run_why_source_counterfactual.query_sql_editor",
                       side_effect=AssertionError("unexpected SQL")):
                self.assertEqual(main(["--live","--receipt",
                                       str(Path(td)/"missing.json")]),2)

    def test_json_serializable_bounded_and_pinned_digest(self):
        _,_,_,r=corpus()
        self.assertTrue(len(json.dumps(r))<100000)
        self.assertEqual(len(r["pinned_input_policy_sha256_not_a_signature"]),64)
        self.assertEqual(r["audited_full_batch_source_count"],7)
        self.assertFalse(r["independent_human_participants"])


if __name__=="__main__":
    unittest.main()
