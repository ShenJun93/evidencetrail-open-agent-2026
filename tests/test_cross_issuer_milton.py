"""Cross-issuer time precision, origin-family and security regression tests."""
from __future__ import annotations

from dataclasses import replace
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from evidencetrail.cross_issuer_milton import (
    _fl_metadata, _as_source, _fl_safe_after, run_cross_issuer_milton,
    run_cross_issuer_evaluation,
)
from evidencetrail.external_milton import _load
from evidencetrail.api import create_local_server
from evidencetrail.pipeline import EvidenceTrailPipeline


class CrossIssuerCoreTests(unittest.TestCase):
    def test_nine_issuance_boundaries_from_two_official_publishers(self):
        data=run_cross_issuer_evaluation()
        self.assertEqual(data["total"],9)
        self.assertEqual(data["passed"],9)
        self.assertTrue(data["pass"])
        self.assertTrue(data["strict_all_families_abstain"])
        self.assertFalse(data["independent_human_outcomes_measured"])
        self.assertFalse(data["sponsor_calls_performed"])

    def test_october_date_only_does_not_become_midnight_utc(self):
        self.assertEqual(
            _fl_safe_after("2024-10-06").isoformat(),
            "2024-10-07T04:00:00+00:00"
        )
        pre=run_cross_issuer_milton("2024-10-07T03:59:00Z")
        post=run_cross_issuer_milton("2024-10-07T04:00:00Z")
        self.assertEqual(pre["florida_counties_under_emergency_in_selected_order"],35)
        self.assertEqual(post["florida_counties_under_emergency_in_selected_order"],51)
        self.assertEqual(post["source_family_count"],1)

    def test_storm_wind_and_emergency_orders_remain_separate_claim_types(self):
        answer=run_cross_issuer_milton("2024-10-07T11:00:00Z")
        self.assertEqual(answer["latest_nhc_selected_wind_mph"],100)
        self.assertEqual(answer["florida_counties_under_emergency_in_selected_order"],51)
        self.assertIsNone(answer["florida_governor_11am_et_press_wind_mph"])
        self.assertEqual(answer["source_family_count"],2)
        self.assertEqual(answer["baseline_time_blind_sources_considered"],7)
        self.assertGreater(answer["baseline_future_source_count"],0)
        self.assertFalse(answer["original_2024_first_publication_authenticated"])

    def test_date_only_fl_press_11am_is_not_publishing_at_11am(self):
        earlier=run_cross_issuer_milton("2024-10-07T15:30:00Z")
        later=run_cross_issuer_milton("2024-10-08T04:00:00Z")
        self.assertIsNone(earlier["florida_governor_11am_et_press_wind_mph"])
        self.assertEqual(later["florida_governor_11am_et_press_wind_mph"],155)
        self.assertEqual(later["source_family_count"],2)
        self.assertFalse(later["florida_republication"]["adds_independent_corroboration"])

    def test_fdem_repost_is_not_third_issuer(self):
        fixture,items=_fl_metadata()
        self.assertEqual(fixture["issuer_families"],["NOAA_NHC","FLORIDA_GOVERNOR"])
        self.assertIn("ICYMI",items[-1]["syndicated_references"][0]["relationship"])
        result=run_cross_issuer_milton("2024-10-08T05:00:00Z")
        self.assertEqual(result["independent_issuer_families_in_corpus"],2)
        self.assertEqual(result["source_family_count"],2)
        self.assertFalse(result["florida_republication"]["independent_issuer_family"])

    def test_duplicate_foreign_source_alias_fails_closed(self):
        _,nhc=_load()
        cloned=replace(nhc[0],source_id="NHC-FAKE-COPIED-SOURCE-ID")
        r=run_cross_issuer_milton(
            "2024-10-07T11:00:00Z",extra_sources=[cloned])
        self.assertTrue(r["refused"])
        self.assertEqual(r["source_family_count"],0)
        self.assertIn("SOURCE_LOCATOR_ALIAS_REFUSED",
                      {x["code"] for x in r["integrity_issues"]})

    def test_bad_source_sha_fails_closed(self):
        _,fl=_fl_metadata()
        bad=replace(_as_source(fl[0]),source_id="TAMPERED-FL",
                    excerpt="Modified excerpt but original hash")
        out=run_cross_issuer_milton(
            "2024-10-07T11:00:00Z",extra_sources=[bad])
        self.assertTrue(out["refused"])
        self.assertIn("SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED",
                      {x["code"] for x in out["integrity_issues"]})

    def test_strict_refuses_all_without_original_2024_bytes(self):
        out=run_cross_issuer_milton("2024-10-08T05:00:00Z",strict=True)
        self.assertEqual(out["source_family_count"],0)
        self.assertIsNone(out["florida_counties_under_emergency_in_selected_order"])
        self.assertIsNone(out["latest_nhc_selected_wind_mph"])
        self.assertEqual(len(out["florida_admitted"]),0)

    def test_invalid_clocks_and_type_safety(self):
        for at in ("2024-10-05T23:59:00Z","2024-10-11T00:01:00Z",
                   "2024-10-07T11:00:00", "nope"):
            with self.subTest(at=at),self.assertRaises(ValueError):
                run_cross_issuer_milton(at)
        with self.assertRaises(ValueError):
            run_cross_issuer_milton(strict="false")
        for value in ("2024-03-10","2024-10-06T11","2024-11-01"):
            with self.subTest(date=value),self.assertRaises(ValueError):
                _fl_safe_after(value)

    def test_no_vendor_network_or_model_called(self):
        with patch("evidencetrail.adapters.zetaris.ZetarisAdapter.fetch_two_logical_sources",
                   side_effect=AssertionError("no sponsor network")),patch(
             "evidencetrail.adapters.meterless.MeterlessRuntimeProvider.chat",
                   side_effect=AssertionError("no AI calls")),patch(
             "evidencetrail.adapters.hmem.HMemAdapter.query",
                   side_effect=AssertionError("no memory calls")):
            d=run_cross_issuer_milton()
        self.assertFalse(d["sponsor_calls_performed"])


class CrossIssuerHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pipe=EvidenceTrailPipeline(
            sample_mode=True,
            persist_dir=Path(self.tmp.name)/"mem",
            log_dir=Path(self.tmp.name)/"logs")
        self.server=create_local_server("127.0.0.1",0,pipeline=pipe)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self,payload):
        req=Request(
            f"http://127.0.0.1:{self.server.server_port}/cross-issuer",
            method="POST",
            data=json.dumps(payload).encode("utf8"),
            headers={"Content-Type":"application/json"})
        try:
            with urlopen(req,timeout=9) as response:
                return response.status,json.loads(response.read().decode("utf8"))
        except HTTPError as error:
            with error:
                return error.code,json.loads(error.read().decode("utf8"))

    def test_real_http_cross_issuer_and_strict(self):
        status,result=self.post({"as_of_utc":"2024-10-07T11:00:00Z"})
        self.assertEqual(status,200)
        self.assertEqual(result["kind"],"EVIDENCETRAIL_CROSS_ISSUER_MILTON_V1")
        self.assertEqual(result["latest_nhc_selected_wind_mph"],100)
        self.assertEqual(result["florida_counties_under_emergency_in_selected_order"],51)
        self.assertEqual(result["source_family_count"],2)
        self.assertFalse(result["sponsor_calls_performed"])
        strict_status,strict=self.post({
            "as_of_utc":"2024-10-07T11:00:00Z","strict":True})
        self.assertEqual(strict_status,200)
        self.assertEqual(strict["source_family_count"],0)
        self.assertEqual(list((Path(self.tmp.name)/"logs").glob("run-*.json")),[])

    def test_request_rejects_fake_sources_and_nonboolean_strict(self):
        for payload in (
            {"as_of_utc":"2024-10-07T11:00:00Z","records":[{"url":"evil"}]},
            {"as_of_utc":"2024-10-07T11:00:00Z","sample_mode":False},
            {"as_of_utc":"2024-10-07T11:00:00Z","strict":"false"},
        ):
            with self.subTest(payload=payload):
                status,body=self.post(payload)
                self.assertEqual(status,400)
                self.assertEqual(body["error"],"invalid_request")


if __name__=="__main__":
    unittest.main()
