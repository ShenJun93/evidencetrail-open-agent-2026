"""Zetaris Milton two-issuer bridge: exact transport, no false sponsor proofs."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from evidencetrail.adapters.zetaris_sql_editor import SqlEditorContractError
from evidencetrail.zetaris_cross_issuer import (
    SQL, COLS, _canonical_rows, evaluate_sql_rows, query_sql_editor,
)
from run_zetaris_cross_issuer import import_rows, write_stage


class _FakeResponse:
    status=200
    def __init__(self,data):
        self.data=json.dumps({"data":data}).encode("utf8")
    def __enter__(self):return self
    def __exit__(self,*args):return None
    def read(self,n):return self.data[:n]


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.nhc,self.fl=import_rows()

    def test_curated_rows_are_actual_data_not_dummy_select_one(self):
        self.assertEqual((len(self.nhc),len(self.fl)),(4,3))
        self.assertEqual(len(SQL),2)
        self.assertTrue(all(" FROM EVIDENCETRAIL_MILTON." in q for q in SQL.values()))
        self.assertTrue(all(q.startswith("SELECT ") for q in SQL.values()))
        self.assertEqual(len(_canonical_rows(self.nhc,self.fl)),7)
        self.assertTrue(all(row["excerpt_sha256"] == sha256(
            row["excerpt"].encode()).hexdigest()
            for row in self.nhc+self.fl))

    def test_cross_claim_replay_mirrors_original_explanation_without_fallback(self):
        early=evaluate_sql_rows(self.nhc,self.fl,clock="2024-10-07T03:59:00Z")
        at=evaluate_sql_rows(self.nhc,self.fl,clock="2024-10-07T11:00:00Z")
        self.assertIsNone(early["latest_noaa_wind_mph"])
        self.assertEqual(early["latest_florida_emergency_counties"],35)
        self.assertEqual(at["latest_noaa_wind_mph"],100)
        self.assertEqual(at["latest_florida_emergency_counties"],51)
        self.assertEqual(at["selected_issuer_families"],["FLORIDA_GOVERNOR","NOAA_NHC"])
        self.assertNotIn("NHC-AL142024-PUBLIC-010",at["selected_original_ids"])
        self.assertFalse(at["original_2024_first_publication_authenticated"])
        self.assertFalse(at["zetaris_server_identity_independently_attested"])

    def test_strict_requires_real_2024_publication_attestation(self):
        r=evaluate_sql_rows(self.nhc,self.fl,clock="2024-10-08T04:00:00Z",strict=True)
        self.assertEqual(r["selected_original_ids"],[])
        self.assertIsNone(r["latest_florida_emergency_counties"])
        self.assertIsNone(r["latest_noaa_wind_mph"])

    def test_missing_rows_never_backfilled_from_fixture(self):
        with self.assertRaisesRegex(SqlEditorContractError,"MISSING_CURATED_ROWS"):
            evaluate_sql_rows(self.nhc[:-1],self.fl)

    def test_wrong_source_hash_and_origin_both_rejected(self):
        fake=deepcopy(self.nhc)
        fake[0]["excerpt"]="tampered"
        with self.assertRaisesRegex(SqlEditorContractError,"EXCERPT_INVALID"):
            evaluate_sql_rows(fake,self.fl)
        fake=deepcopy(self.nhc)
        fake[0]["locator"]="https://evil.invalid/altered"
        with self.assertRaisesRegex(SqlEditorContractError,"METADATA_DOES_NOT_MATCH"):
            evaluate_sql_rows(fake,self.fl)

    def test_issuer_spoof_and_duplicate_rejected(self):
        fake=deepcopy(self.nhc)
        fake[0]["issuer_family"]="FLORIDA_GOVERNOR"
        with self.assertRaisesRegex(SqlEditorContractError,"METADATA_DOES_NOT_MATCH"):
            evaluate_sql_rows(fake,self.fl)
        fake=deepcopy(self.nhc)
        fake[0]["source_id"]=fake[1]["source_id"]
        with self.assertRaises(SqlEditorContractError):
            evaluate_sql_rows(fake,self.fl)

    def test_read_only_sql_editor_transport_has_real_rows_and_required_headers(self):
        observed=[]
        def opener(request,timeout):
            observed.append({
                "url":request.full_url,
                "method":request.get_method(),
                "body":json.loads(request.data.decode("utf8")),
                "headers":dict(request.header_items()),
                "timeout":timeout
            })
            return _FakeResponse(self.nhc)
        rows,rid,digest=query_sql_editor(
            "NOAA_NHC",base_url="http://127.0.0.1:8888/api/v1.0",
            org_id="1",api_key="secret-for-local-test",opener=opener)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0]["source_id"],self.nhc[0]["source_id"])
        self.assertTrue(rid)
        self.assertEqual(len(digest),12)
        self.assertEqual(observed[0]["method"],"POST")
        self.assertTrue(observed[0]["url"].endswith("/sql-editor/sqls/run"))
        self.assertEqual(observed[0]["body"]["sql"],SQL["NOAA_NHC"])
        self.assertEqual(observed[0]["headers"]["Authorization"],"Bearer secret-for-local-test")
        self.assertEqual(observed[0]["headers"]["X-org-id"],"1")

    def test_refuse_cloud_host_without_opening_any_connection(self):
        def opener(*args,**kwargs):
            raise AssertionError("HTTP must not happen")
        with self.assertRaisesRegex(SqlEditorContractError,"LOCAL_SQL_EDITOR_API_BASE_REQUIRED"):
            query_sql_editor("NOAA_NHC",base_url="https://evil.invalid/v1",
                             org_id="1",api_key="fake",opener=opener)
        with self.assertRaisesRegex(SqlEditorContractError,"UNAPPROVED_ISSUER_QUERY"):
            query_sql_editor("NO_OTHER_SOURCE",base_url="http://127.0.0.1:8888/api/v1.0",
                             org_id="1",api_key="fake",opener=opener)

    def test_wrong_columns_and_unrecognized_rows_refused(self):
        with self.assertRaisesRegex(SqlEditorContractError,"SOURCE_COLUMNS_MISMATCH"):
            query_sql_editor("NOAA_NHC",base_url="http://127.0.0.1:8888/api/v1.0",
                             org_id="1",api_key="dummy",
                             opener=lambda r,timeout: _FakeResponse([{"not":"rows"}]))
        with self.assertRaisesRegex(SqlEditorContractError,"SOURCE_RESULT_MISSING_OR_PAGINATED"):
            query_sql_editor("NOAA_NHC",base_url="http://127.0.0.1:8888/api/v1.0",
                             org_id="1",api_key="dummy",
                             opener=lambda r,timeout: _FakeResponse([]))

    def test_invalid_asof_and_boolean_are_refused(self):
        for t in ("2024-10-05T00:00:00Z","2025-01-01T00:00:00Z","invalid"):
            with self.subTest(t=t),self.assertRaises(ValueError):
                evaluate_sql_rows(self.nhc,self.fl,clock=t)
        with self.assertRaises(ValueError):
            evaluate_sql_rows(self.nhc,self.fl,strict="no")

    def test_local_stage_is_not_sponsor_pass(self):
        report=write_stage()
        self.assertEqual(report["status"],"NEEDS_OPERATOR_REGISTER_APPROVED_DATASOURCE")
        self.assertEqual(report["expected_row_counts"],
                         {"NOAA_NHC":4,"FLORIDA_GOVERNOR":3})
        self.assertFalse(report["file_is_automatically_visible_inside_zetaris"])
        self.assertFalse(report["source_organization_verification_or_original_2024_publication"])


if __name__ == "__main__":
    unittest.main()
