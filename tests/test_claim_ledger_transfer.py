"""Case-independent ledger: Milton transfer, new issuer, malicious manifests.

Every test is OFFLINE over manually curated source metadata, not a real
government feed, Zetaris query, human outcome or vendor model completion.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import unittest

from evidencetrail.claim_ledger import (
    ClaimLedgerRefusal, ClaimRule, SourcePin, evaluate_claim_ledger,
)
from evidencetrail.cross_issuer_milton import _fl_metadata, _fl_safe_after
from evidencetrail.external_milton import _load as load_nhc
from evidencetrail.models import (
    ProvenanceQuality, RecordKind, ReplayMode, SourceRecord, iso, parse_iso,
)
from evidencetrail.zetaris_cross_issuer import _canonical_rows
from run_zetaris_cross_issuer import import_rows


def curated_milton():
    nhc_sql, fl_sql = import_rows()
    rows = _canonical_rows(nhc_sql, fl_sql)  # offline fixture, NOT live SQL
    _, nrows = load_nhc()
    _, flmeta = _fl_metadata()
    pins = {}
    for row in nrows:
        pins[row.source_id] = SourcePin(
            source_id=row.source_id, locator=row.locator,
            publisher=row.publisher, excerpt_sha256=row.excerpt_sha256,
            issuer_family="NOAA_NHC", claim_key="NHC_WIND",
            expected_value=row.observation_fields[
                "reported_maximum_sustained_wind_mph"],
            record_kind=RecordKind.GOVERNMENT_NEWS,
            provenance_quality=row.provenance_quality,
            claimed_issue_utc=iso(row.issued_at_claimed_utc),
        )
    for item in flmeta:
        kind = item["claim_type"]
        key = "FL_ORDER" if kind == "florida_counties_under_emergency" else "FL_PRESS"
        pins[item["id"]] = SourcePin(
            source_id=item["id"], locator=item["url"],
            publisher="Florida Executive Office of the Governor",
            excerpt_sha256=sha256(item["description"].encode()).hexdigest(),
            issuer_family="FLORIDA_GOVERNOR", claim_key=key,
            expected_value=item["value"],
            record_kind=RecordKind.GOVERNMENT_NEWS,
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            displayed_local_day=item["displayed_date_local"],
            curator_not_before_utc=iso(_fl_safe_after(item["displayed_date_local"])),
            local_utc_offset_minutes=-240,
        )
    rules = [
        ClaimRule("NHC_WIND","NOAA_NHC","maximum_sustained_wind_mph",
                  "value","mph","NOAA reported sustained wind"),
        ClaimRule("FL_ORDER","FLORIDA_GOVERNOR",
                  "florida_counties_under_emergency",
                  "value","counties","Florida emergency order county count"),
        ClaimRule("FL_PRESS","FLORIDA_GOVERNOR",
                  "florida_governor_press_wind_mph_reported_asof_11am_et",
                  "value","mph","Florida press reported wind"),
    ]
    return rows, pins, rules


def fresh_issuer_source(*, source_id="TEST-LAB-001", clock="2024-10-07T08:00:00Z",
                        value=7, publisher="Fictional Water Agency for Unit Tests",
                        kind=RecordKind.GOVERNMENT_NEWS):
    excerpt = "FICTIONAL UNIT TEST lab reading of 7 arbitrary units"
    issue = parse_iso(clock)
    prov = (ProvenanceQuality.SYNTHETIC
            if kind == RecordKind.SYNTHETIC_CAPACITY
            else ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN)
    row=SourceRecord(
        source_id=source_id,record_kind=kind,
        locator=("synthetic://unit-test/"+source_id if kind==RecordKind.SYNTHETIC_CAPACITY
                 else "https://example.org/fictional/"+source_id),
        publisher=publisher,paraphrase=excerpt,excerpt=excerpt,
        excerpt_sha256=sha256(excerpt.encode()).hexdigest(),
        published_at_displayed_utc=issue,observed_at_utc=None,
        issued_at_claimed_utc=issue,first_availability_proven_utc=None,
        retrieved_at_utc=None,provenance_quality=prov,
        historical_admin_vintage="2024",spatial_scope=["test"],
        named_districts_2024=[],granularity="test",
        observation_fields={"issuer_family":"TEST_LAB","claim_type":"lab_reading",
                            "reading":value},
    )
    pin=SourcePin(
        source_id=source_id,locator=row.locator,publisher=publisher,
        excerpt_sha256=row.excerpt_sha256,
        issuer_family="TEST_LAB",claim_key="LAB_READING",
        expected_value=7,record_kind=kind,provenance_quality=prov,
        claimed_issue_utc=clock,
    )
    rule=ClaimRule("LAB_READING","TEST_LAB","lab_reading","reading",
                   "test_units","Unit test lab reading")
    return row,pin,rule


class TransferableLedgerTests(unittest.TestCase):
    def setUp(self):
        self.rows,self.pins,self.rules=curated_milton()

    def evaluate(self, when="2024-10-07T11:00:00Z",strict=False):
        return evaluate_claim_ledger(
            self.rows,self.pins,self.rules,as_of_utc=when,
            mode=(ReplayMode.STRICT_AS_OF_2024 if strict else
                  ReplayMode.REPORTED_DATELINE_REPLAY))

    def test_noaa_florida_11am_chooses_100_and_51_and_suppresses_future_press(self):
        r=self.evaluate()
        self.assertEqual(r["status"],"CLAIMS_SELECTED")
        self.assertEqual(
            {c["claim_key"]:c["value"] for c in r["typed_claims"]},
            {"NHC_WIND":100,"FL_ORDER":51})
        self.assertEqual(r["issuer_independence_count"],2)
        self.assertNotIn("NHC-AL142024-PUBLIC-010",r["source_ids_eligible"])
        self.assertNotIn("155 mph",r["trusted_template_explanation"])
        self.assertFalse(r["attested_original_publication"])
        self.assertFalse(r["model_or_sponsor_called"])

    def test_early_clock_blocks_noaa_and_latest_florida_51(self):
        r=self.evaluate("2024-10-07T03:59:00Z")
        self.assertEqual({c["claim_key"]:c["value"] for c in r["typed_claims"]},
                         {"FL_ORDER":35})
        self.assertEqual(r["issuer_independence_count"],1)

    def test_florida_day_only_policy_boundary_is_exact(self):
        early=self.evaluate("2024-10-07T03:59:59Z")
        later=self.evaluate("2024-10-07T04:00:00Z")
        self.assertEqual(early["typed_claims"][0]["value"],35)
        self.assertEqual(later["typed_claims"][0]["value"],51)
        self.assertIn("CURATOR_DATE_ONLY_NOT_BEFORE_UTC",
                      later["typed_claims"][0]["clock_basis"])

    def test_future_clock_pins_update_claim_without_peak_forecast(self):
        r=self.evaluate("2024-10-07T15:00:00Z")
        claims={c["claim_key"]:c["value"] for c in r["typed_claims"]}
        self.assertEqual(claims["NHC_WIND"],155)
        self.assertEqual(claims["FL_ORDER"],51)

    def test_strict_all_abstains_without_archive_evidence(self):
        r=self.evaluate("2024-10-08T04:00:00Z",strict=True)
        self.assertEqual(r["status"],"ABSTAIN_NO_ADMISSIBLE_CLAIMS")
        self.assertEqual(r["typed_claims"],[])
        self.assertEqual(len(r["excluded"]),7)
        self.assertIn("STRICT_ORIGINAL_FIRST_AVAILABILITY",
                      r["excluded"][0]["reason"])

    def test_manifest_order_independence(self):
        a=self.evaluate()
        other=evaluate_claim_ledger(list(reversed(self.rows)),self.pins,
                                    self.rules,as_of_utc="2024-10-07T11:00:00Z")
        self.assertEqual(a["typed_claims"],other["typed_claims"])

    def test_unpinned_third_party_source_refused_not_independent_corrob(self):
        row,_,_=fresh_issuer_source()
        with self.assertRaisesRegex(ClaimLedgerRefusal,"MANIFEST_COVERAGE"):
            evaluate_claim_ledger(self.rows+[row],self.pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_future_alias_cannot_be_hidden_by_time_filter(self):
        mutated=deepcopy(self.rows)
        target=next(r for r in mutated if r.source_id=="NHC-AL142024-PUBLIC-023")
        target.excerpt=mutated[0].excerpt
        target.excerpt_sha256=mutated[0].excerpt_sha256
        with self.assertRaisesRegex(ClaimLedgerRefusal,"IDENTITY_ALIAS"):
            evaluate_claim_ledger(mutated,self.pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_forged_number_even_with_resigned_excerpt_refused(self):
        rows=deepcopy(self.rows)
        target=next(r for r in rows if r.source_id=="NHC-AL142024-PUBLIC-008")
        target.observation_fields["value"]=155
        target.excerpt="FAKE altered content"
        target.excerpt_sha256=sha256(target.excerpt.encode()).hexdigest()
        with self.assertRaises(ClaimLedgerRefusal):
            evaluate_claim_ledger(rows,self.pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_date_only_cannot_gain_fake_issued_at(self):
        rows=deepcopy(self.rows)
        target=next(r for r in rows if r.source_id=="FL-EO-24-215")
        target.issued_at_claimed_utc=parse_iso("2024-10-06T00:00:00Z")
        with self.assertRaisesRegex(ClaimLedgerRefusal,"DATE_ONLY"):
            evaluate_claim_ledger(rows,self.pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_unsafe_rules_or_clock_rejected(self):
        with self.assertRaisesRegex(ClaimLedgerRefusal,"CLAIM_RULE_LABEL"):
            evaluate_claim_ledger(self.rows,self.pins,
                [replace(self.rules[0],label="<script>alert(1)</script>")],
                as_of_utc="2024-10-07T11:00:00Z")
        with self.assertRaisesRegex(ClaimLedgerRefusal,"PIN_CLOCK"):
            evaluate_claim_ledger(self.rows,self.pins,self.rules,
                                  as_of_utc="2024-10-07 11:00:00")

    def test_pin_clock_revision_requires_curator_policy_change(self):
        pins=dict(self.pins)
        sid="NHC-AL142024-PUBLIC-008"
        pins[sid]=replace(pins[sid],claimed_issue_utc="2024-10-07T05:00:00Z")
        with self.assertRaisesRegex(ClaimLedgerRefusal,"ISSUE_CLOCK_MISMATCH"):
            evaluate_claim_ledger(self.rows,pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_bad_value_types_and_pinned_numbers(self):
        for value in (True,100.0,"100",-1):
            with self.subTest(value=value):
                rows=deepcopy(self.rows)
                next(r for r in rows if r.source_id=="NHC-AL142024-PUBLIC-008").observation_fields["value"]=value
                with self.assertRaises(ClaimLedgerRefusal):
                    evaluate_claim_ledger(rows,self.pins,self.rules,
                                          as_of_utc="2024-10-07T11:00:00Z")

    def test_day_only_gate_cannot_be_placed_before_end_of_local_day(self):
        sid="FL-EO-24-215"
        pins=dict(self.pins)
        pins[sid]=replace(pins[sid],
                          curator_not_before_utc="2024-10-07T00:00:00Z")
        with self.assertRaisesRegex(ClaimLedgerRefusal,"DATE_ONLY_GATE_PREMATURE"):
            evaluate_claim_ledger(self.rows,pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_malformed_timezone_offset_refused(self):
        sid="FL-EO-24-215"
        for offset in (None,True,-1000,901,5):
            with self.subTest(offset=offset):
                pins=dict(self.pins)
                pins[sid]=replace(pins[sid],local_utc_offset_minutes=offset)
                with self.assertRaisesRegex(ClaimLedgerRefusal,"UTC_OFFSET_REQUIRED"):
                    evaluate_claim_ledger(self.rows,pins,self.rules,
                                          as_of_utc="2024-10-07T11:00:00Z")

    def test_malicious_source_identifier_not_renderable(self):
        rows=deepcopy(self.rows)
        rows[0].source_id="<script>"
        with self.assertRaises(ClaimLedgerRefusal):
            evaluate_claim_ledger(rows,self.pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_pin_disallows_alias_source_id_and_bad_https_scheme(self):
        sid="NHC-AL142024-PUBLIC-008"
        pins=dict(self.pins)
        pins[sid]=replace(pins[sid],locator="javascript:alert(1)")
        with self.assertRaises(ClaimLedgerRefusal):
            evaluate_claim_ledger(self.rows,pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_unknown_pin_claim_does_not_get_assumed(self):
        sid="NHC-AL142024-PUBLIC-008"
        pins=dict(self.pins)
        pins[sid]=replace(pins[sid],claim_key="INVENTED")
        with self.assertRaisesRegex(ClaimLedgerRefusal,"UNREGISTERED"):
            evaluate_claim_ledger(self.rows,pins,self.rules,
                                  as_of_utc="2024-10-07T11:00:00Z")

    def test_repeat_same_claim_rule_identifier_refused(self):
        with self.assertRaisesRegex(ClaimLedgerRefusal,"RULE_KEY_ALIAS"):
            evaluate_claim_ledger(self.rows,self.pins,self.rules+[self.rules[0]],
                                  as_of_utc="2024-10-07T11:00:00Z")


class CompletelyDifferentIssuerTransferTests(unittest.TestCase):
    def test_generic_non_milton_issuer(self):
        row,pin,rule=fresh_issuer_source()
        result=evaluate_claim_ledger([row],{row.source_id:pin},[rule],
                                      as_of_utc="2024-10-07T08:01:00Z")
        self.assertEqual(result["typed_claims"][0]["value"],7)
        self.assertEqual(result["typed_claims"][0]["unit"],"test_units")
        self.assertEqual(result["issuer_independence_count"],1)
        self.assertFalse(result["independent_source_fact_check"])
        self.assertIn("Historical research only",result["trusted_template_explanation"])

    def test_generic_issuer_timeline_refuses_future(self):
        row,pin,rule=fresh_issuer_source()
        report=evaluate_claim_ledger([row],{row.source_id:pin},[rule],
                                     as_of_utc="2024-10-07T07:59:59Z")
        self.assertEqual(report["typed_claims"],[])
        self.assertEqual(report["status"],"ABSTAIN_NO_ADMISSIBLE_CLAIMS")

    def test_fictional_capacity_never_counted_independent_government(self):
        row,pin,rule=fresh_issuer_source(kind=RecordKind.SYNTHETIC_CAPACITY)
        r=evaluate_claim_ledger([row],{row.source_id:pin},[rule],
                                 as_of_utc="2024-10-07T08:01:00Z")
        self.assertTrue(r["typed_claims"][0]["fictional"])
        self.assertEqual(r["issuer_independence_count"],0)
        self.assertIn("[FICTIONAL]",r["trusted_template_explanation"])

    def test_injected_fictional_record_as_government_rejected(self):
        row,pin,rule=fresh_issuer_source(kind=RecordKind.SYNTHETIC_CAPACITY)
        row.record_kind=RecordKind.GOVERNMENT_NEWS
        with self.assertRaisesRegex(ClaimLedgerRefusal,"PINNED_SOURCE_IDENTITY"):
            evaluate_claim_ledger([row],{row.source_id:pin},[rule],
                                  as_of_utc="2024-10-07T08:01:00Z")


if __name__=="__main__":
    unittest.main()
