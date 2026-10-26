"""The reusable source-pinned ledger is required before ANY NVIDIA egress.

All calls in these tests are injected stubs. Do not claim vendor inference.
"""
from __future__ import annotations

from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

import run_nvidia_lightning_zetaris as runner
from evidencetrail.adapters.nvidia_lightning import NvidiaLightningError
from run_zetaris_cross_issuer import import_rows


CONF={
    "NVIDIA_API_KEY":"offline-mock-nvidia-key-1234567890",
    "ZETARIS_REST_URL":"http://127.0.0.1:8888/api/v1.0",
    "ZETARIS_ORG_ID":"unit-org",
    "ZETARIS_API_KEY":"offline-mock-zetaris-key-1234567890",
}


def fake_sql(issuer, **kwargs):
    nhc,fl=import_rows()
    return (nhc if issuer=="NOAA_NHC" else fl, "unit-request-"+issuer, "unit-sql-digest")


class LedgerBeforeNvidiaEgressTests(TestCase):
    def test_valid_offline_sql_contract_allows_only_injected_stub(self):
        captured=[]
        def fake_chat(**kwargs):
            captured.append(kwargs)
            return {"status":"INJECTED_CONTRACT_ONLY",
                    "grounding":{"grounded_against_sql_selection":True}}
        with patch.object(runner,"query_sql_editor",side_effect=fake_sql) as sql,patch.object(
            runner,"chat_public_evidence",side_effect=fake_chat):
            report=runner.one_real_run(CONF)
        self.assertEqual(sql.call_count,2)
        self.assertEqual(len(captured),1)
        self.assertEqual(report["status"],"INJECTED_CONTRACT_ONLY")
        self.assertEqual(report["claim_ledger_gate"]["status"],
                         "PASSED_SOURCE_PINNED_REPORTED_DATE_REPLAY_ONLY")
        self.assertEqual(report["claim_ledger_gate"]["typed_claim_keys"],
                         ["FL_ORDER","NHC_WIND"])
        self.assertFalse(report["claim_ledger_gate"]["source_first_publication_authenticated"])

    def test_bad_ledger_result_never_calls_model(self):
        fake={"status":"CLAIMS_SELECTED","issuer_independence_count":2,
              "attested_original_publication":False,
              "typed_claims":[
                  {"claim_key":"NHC_WIND","value":155,
                   "original_first_publication_authenticated":False},
                  {"claim_key":"FL_ORDER","value":51,
                   "original_first_publication_authenticated":False}
              ]}
        with patch.object(runner,"query_sql_editor",side_effect=fake_sql),patch.object(
            runner,"evaluate_milton_sql_claims",return_value=fake),patch.object(
            runner,"chat_public_evidence",side_effect=AssertionError("model called")):
            with self.assertRaisesRegex(NvidiaLightningError,"GENERIC_CLAIM_LEDGER_EGRESS_REFUSED"):
                runner.one_real_run(CONF)

    def test_ledger_cannot_claim_original_historical_authentication(self):
        fake={"status":"CLAIMS_SELECTED","issuer_independence_count":2,
              "attested_original_publication":True,
              "typed_claims":[
                  {"claim_key":"NHC_WIND","value":100,
                   "original_first_publication_authenticated":True},
                  {"claim_key":"FL_ORDER","value":51,
                   "original_first_publication_authenticated":False}
              ]}
        with patch.object(runner,"query_sql_editor",side_effect=fake_sql),patch.object(
            runner,"evaluate_milton_sql_claims",return_value=fake),patch.object(
            runner,"chat_public_evidence",side_effect=AssertionError("model called")):
            with self.assertRaisesRegex(NvidiaLightningError,"GENERIC_CLAIM_LEDGER_EGRESS_REFUSED"):
                runner.one_real_run(CONF)

    def test_missing_new_source_fails_closed_before_egress(self):
        def source(issuer,**kwargs):
            rows,mid,digest=fake_sql(issuer,**kwargs)
            if issuer=="FLORIDA_GOVERNOR":
                rows=rows[:2]
            return rows,mid,digest
        with patch.object(runner,"query_sql_editor",side_effect=source),patch.object(
            runner,"chat_public_evidence",side_effect=AssertionError("model called")):
            with self.assertRaises(Exception):
                runner.one_real_run(CONF)

    def test_source_number_changed_after_sql_does_not_egress(self):
        def mutated(issuer,**kwargs):
            rows,mid,digest=fake_sql(issuer,**kwargs)
            rows=deepcopy(rows)
            if issuer=="NOAA_NHC":
                next(r for r in rows if r["source_id"]==
                     "NHC-AL142024-PUBLIC-008")["value_int"]=155
            return rows,mid,digest
        with patch.object(runner,"query_sql_editor",side_effect=mutated),patch.object(
            runner,"chat_public_evidence",side_effect=AssertionError("model called")):
            with self.assertRaises(Exception):
                runner.one_real_run(CONF)

    def test_missing_nvidia_key_blocks_sql_and_model(self):
        conf=dict(CONF)
        conf["NVIDIA_API_KEY"]=""
        with patch.object(runner,"query_sql_editor",side_effect=AssertionError("SQL")),patch.object(
            runner,"chat_public_evidence",side_effect=AssertionError("model")):
            r=runner.one_real_run(conf)
            self.assertEqual(r["status"],"KEY_OR_ZETARIS_CONFIG_MISSING")
            self.assertEqual(r["zetaris_query_attempts"],0)


if __name__=="__main__":
    import unittest
    unittest.main()
