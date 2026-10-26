"""Real localhost HTTP contract and offline security for Counterfactual Lab."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from evidencetrail.api import DEMO_HTML, create_local_server
from evidencetrail.pipeline import EvidenceTrailPipeline


class CounterfactualLocalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log_dir = Path(self.temp.name) / "runlogs"
        self.memory_dir = Path(self.temp.name) / "memory"
        self.pipeline = EvidenceTrailPipeline(
            sample_mode=True, persist_dir=self.memory_dir, log_dir=self.log_dir
        )
        self.server = create_local_server(
            "127.0.0.1", 0, pipeline=self.pipeline
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, path, payload):
        url = f"http://127.0.0.1:{self.server.server_port}{path}"
        request = Request(
            url, method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf8"))
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read().decode("utf8"))

    @staticmethod
    def payload(stamp="1645"):
        return json.loads(
            Path(f"samples/inputs/yagi_{stamp}_lucyen.json").read_text("utf8")
        )

    def test_real_http_counterfactual_reports_minimal_pivotal_and_policy(self):
        code, report = self.post("/counterfactual", self.payload())
        self.assertEqual(code, 200)
        self.assertEqual(report["kind"],
                         "OFFLINE_DETERMINISTIC_COUNTERFACTUAL_DOSSIER_V1")
        self.assertEqual(report["current"]["rule_verdict"], "WARN")
        self.assertEqual(report["earlier_same_policy"]["rule_verdict"],
                         "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report["same_clock_other_policy"]["rule_verdict"],
                         "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report["current"]["minimum_set_cardinality"], 2)
        self.assertEqual(len(report["current"]["pivotal_source_ids"]), 2)
        self.assertTrue(report["offline_sample_only"])
        plan = report["current"]["research_action_plan"]
        self.assertEqual(plan["kind"], "OFFLINE_HUMAN_REVIEW_RESEARCH_PLAN_V1")
        self.assertFalse(plan["model_or_vendor_called"])
        self.assertFalse(plan["new_evidence_collected"])
        self.assertEqual(set(plan["pivotal_source_ids"]), {
            "GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"
        })

    def test_browser_cannot_enable_network_in_counterfactual(self):
        payload = self.payload()
        payload["sample_mode"] = False
        with patch.object(
            self.pipeline, "run",
            side_effect=AssertionError("No /run call from /counterfactual"),
        ):
            code, report = self.post("/counterfactual", payload)
        self.assertEqual(code, 200)
        self.assertFalse(report["real_zetaris_query_performed"])
        self.assertFalse(report["first_party_hmem_called"])
        self.assertFalse(report["official_meterless_nightshift_called"])
        self.assertEqual(list(self.log_dir.glob("run-*.json")), [])
        self.assertEqual(list(self.log_dir.glob("trace-*.jsonl")), [])

    def test_real_http_own_weak_baseline_comparison_labels_no_external_agent(self):
        from urllib.request import urlopen
        url = f"http://127.0.0.1:{self.server.server_port}/comparison"
        with urlopen(url, timeout=35) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read(150_000).decode("utf8"))
        self.assertEqual(data["kind"],
                         "EVIDENCETRAIL_OFFLINE_INTERNAL_BASELINE_COMPARISON_V1")
        self.assertEqual(data["case_count"], 20)
        self.assertEqual(data["evidencetrail_policy_gold_passes"], 20)
        self.assertGreaterEqual(data["own_weak_control_false_warn_cases"], 1)
        self.assertFalse(data["baseline_is_rival_product_or_external_llm"])
        self.assertFalse(data["model_vendor_or_paid_api_called"])

    def test_real_http_counterfactual_1630_returns_missing_district(self):
        code, report = self.post("/counterfactual", self.payload("1630"))
        self.assertEqual(code, 200)
        self.assertEqual(report["current"]["rule_verdict"],
                         "INSUFFICIENT_EVIDENCE")
        self.assertIn("MISSING_DISTRICT_NAMED_BULLETIN", {
            x["code"] for x in report["current"]["next_evidence_requirements"]
        })

    def test_invalid_requested_time_window_rejected_with_400(self):
        payload = self.payload()
        for minutes in (0, 500, "15"):
            with self.subTest(minutes=minutes):
                payload["earlier_by_minutes"] = minutes
                code, response = self.post("/counterfactual", payload)
                self.assertEqual(code, 400)
                self.assertEqual(response["error"], "invalid_request")

    def test_untrusted_run_id_cannot_inject_file_paths_or_log_separators(self):
        for unsafe in ("../outside", "..\\outside", "x/y",
                       "x\\y", "new\nline", "a"*65, ".."):
            with self.subTest(value=repr(unsafe)):
                request = self.payload()
                request["run_id"] = unsafe
                code_run, out_run = self.post("/run", request)
                code_cf, out_cf = self.post("/counterfactual", request)
                self.assertEqual(code_run, 400)
                self.assertEqual(code_cf, 400)
                self.assertEqual(out_run["error"], "invalid_request")
                self.assertEqual(out_cf["error"], "invalid_request")
        self.assertEqual(list(self.log_dir.glob("trace-*")), [])

    def test_unknown_endpoint_does_not_call_counterfactual(self):
        code, payload = self.post("/invalid-counterfactual", self.payload())
        self.assertEqual(code, 404)
        self.assertEqual(payload["error"], "not_found")

    def test_real_http_regular_pipeline_remains_computed(self):
        code, report = self.post("/run", self.payload("1630"))
        self.assertEqual(code, 200)
        self.assertEqual(report["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(report["sample_mode"])
        self.assertFalse(any(
            call["outcome"] == "REAL_SUCCESS" for call in report["sponsor_calls"]
        ))

    def test_loopback_only_even_for_injected_test_pipeline(self):
        with self.assertRaisesRegex(ValueError, "LOCALHOST_BIND_REQUIRED"):
            create_local_server("0.0.0.0", 0, pipeline=self.pipeline)
        bad = EvidenceTrailPipeline(
            sample_mode=False,
            log_dir=Path(self.temp.name) / "badlogs",
        )
        with self.assertRaisesRegex(ValueError, "INJECTED_LIVE_PIPELINE_REFUSED"):
            create_local_server("127.0.0.1", 0, pipeline=bad)


class CounterfactualBrowserUiContractTests(unittest.TestCase):
    def test_proof_lab_is_a_real_dynamic_network_action(self):
        html = DEMO_HTML.read_text(encoding="utf8")
        self.assertIn('id="counter"', html)
        self.assertIn('fetch("/counterfactual"', html)
        self.assertIn('id="cfAblations"', html)
        self.assertIn('id="cfRequirements"', html)
        self.assertIn('id="cfActionPlan"', html)
        self.assertIn('id="compareBaseline"', html)
        self.assertIn('fetch("/comparison"', html)
        self.assertIn("minimum_sufficient_source_set", html)
        self.assertIn("without_source_rule_verdict", html)
        self.assertIn("Promise.all([execute(clock),executeCounterfactual(clock)])", html)

    def test_markup_does_not_add_remote_scripts_or_xss_unsafe_rendering(self):
        html = DEMO_HTML.read_text(encoding="utf8")
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn('src="https://', html)
        self.assertNotIn('script src=', html)
        self.assertIn("FICTIONAL capacity", html)
        self.assertIn("not causation", html.lower())

    def test_counterfactual_browser_client_refuses_non_sample_payload(self):
        html = DEMO_HTML.read_text(encoding="utf8")
        self.assertIn("body.offline_sample_only!==true", html)
        self.assertIn("OFFLINE_DETERMINISTIC_COUNTERFACTUAL_DOSSIER_V1", html)
        self.assertIn("COUNTERFACTUAL", html.upper())


if __name__ == "__main__":
    unittest.main()
