"""Real loopback cases, never external data/model/provider execution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from evidencetrail.case_investigator import example_case
from tests.test_why_local_api import post, server


class OpenCaseHttpTests(unittest.TestCase):
    def test_example_and_joint_withdrawal_through_real_local_http(self):
        with server() as base:
            with urlopen(base+"/case-examples/warehouse") as response:
                case = json.load(response)
            code, result = post(base, "/case-investigation", {
                "case": case, "withdrawn_source_ids": ["STOCK-CHECK", "STOCK-LEDGER"]})
        self.assertEqual(code, 200)
        self.assertEqual(result["why"]["selected_claims"]["STOCK"]["value"], 25)
        self.assertEqual(result["experiment"]["selected_claims_after"]["STOCK"]["value"], 12)
        self.assertFalse(result["model_or_sponsor_called"])

    def test_new_arbitrary_clock_supported_without_relaxing_original_demo_route(self):
        with server() as base:
            code, result = post(base, "/case-investigation", {
                "case": example_case("warehouse"), "as_of_utc": "2026-10-24T10:17:32Z"})
            old_code, _ = post(base, "/why-counterfactual", {"as_of_utc": "2026-10-24T10:17:32Z"})
        self.assertEqual(code, 200)
        self.assertEqual(result["why"]["selected_claims"]["STOCK"]["value"], 40)
        self.assertEqual(old_code, 400)

    def test_privileged_options_malformed_inputs_and_unknown_example_refused(self):
        with server() as base:
            for extra in ({"sample_mode": False}, {"provider": "nvidia"},
                          {"strict": "false"}, {"search_depth": 4},
                          {"withdrawn_source_ids": ["UNKNOWN"]}):
                code, out = post(base, "/case-investigation", {"case": example_case("warehouse"), **extra})
                self.assertEqual(code, 400)
                self.assertEqual(out["error"], "invalid_request")
            code, _ = post(base, "/case-investigation", {"case": []})
            self.assertEqual(code, 400)
            with self.assertRaises(HTTPError) as error:
                urlopen(base+"/case-examples/private-key-path", timeout=5)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

    def test_cli_refuses_receipt_overwrite_and_stays_offline(self):
        from run_case_investigation import main
        with tempfile.TemporaryDirectory() as td:
            packet, receipt = Path(td)/"unseen.case.json", Path(td)/"result.json"
            packet.write_text(json.dumps(example_case("warehouse")), encoding="utf-8")
            with patch("urllib.request.build_opener", side_effect=AssertionError("NO NETWORK")):
                self.assertEqual(main(["--case", str(packet), "--receipt", str(receipt),
                                       "--withdraw", "STOCK-CHECK", "STOCK-LEDGER"]), 0)
                original = receipt.read_bytes()
                self.assertEqual(main(["--case", str(packet), "--receipt", str(receipt)]), 2)
                self.assertEqual(receipt.read_bytes(), original)
            report = json.loads(original)
            self.assertFalse(report["model_or_sponsor_called"])
            self.assertEqual(report["experiment"]["selected_claims_after"]["STOCK"]["value"], 12)

    def test_cli_local_sql_requires_opt_in_before_key_read(self):
        from run_case_investigation import main
        with tempfile.TemporaryDirectory() as td, patch(
                "run_case_investigation.read_local_env", side_effect=AssertionError("NO KEY READ")):
            self.assertEqual(main(["--local-zetaris", "--receipt", str(Path(td)/"refused.json")]), 2)

    def test_cli_local_sql_has_no_fixture_fallback_and_discloses_partial_success(self):
        from run_case_investigation import main
        from run_zetaris_cross_issuer import import_rows
        nhc, florida = import_rows()
        for fail_second in (False, True):
            with self.subTest(fail_second=fail_second), tempfile.TemporaryDirectory() as td:
                target = Path(td)/"injected-local-contract-not-vendor-proof.json"
                results = [(nhc, "unit-1", "unit-query-1"),
                           ValueError("SOURCE_HTTP_ERROR") if fail_second else
                           (florida, "unit-2", "unit-query-2")]
                with patch("run_case_investigation.read_local_env", return_value={
                    "ZETARIS_REST_URL": "http://127.0.0.1:8888/api/v1.0",
                    "ZETARIS_ORG_ID": "1", "ZETARIS_API_KEY": "unit-only",
                }), patch("run_case_investigation.query_sql_editor", side_effect=results):
                    code = main(["--local-zetaris", "--approve-local-zetaris", "--receipt", str(target)])
                self.assertEqual(code, 2 if fail_second else 0)
                self.assertEqual(target.exists(), not fail_second)
                if not fail_second:
                    report = json.loads(target.read_text())
                    self.assertEqual(report["zetaris_queries_completed"], 2)
                    self.assertTrue(report["model_or_sponsor_called"])
                    self.assertFalse(report["model_called"])
                    self.assertEqual(report["source_origin"], "REAL_LOCAL_ZETARIS_ROWS_CURATED_METADATA")


if __name__ == "__main__": unittest.main()
