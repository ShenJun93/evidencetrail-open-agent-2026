"""Full localhost API and UI contract for the dynamic independence challenge."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from evidencetrail.api import DEMO_HTML, create_local_server
from evidencetrail.integrity_challenge import run_evidence_integrity_challenge
from evidencetrail.pipeline import EvidenceTrailPipeline


class IntegrityChallengeTests(unittest.TestCase):
    def test_actual_adversarial_matrix_and_unguarded_false_watch(self):
        report = run_evidence_integrity_challenge()
        self.assertEqual(report["case_count"], 7)
        self.assertEqual(report["passed_count"], 7)
        self.assertTrue(report["all_cases_pass"])
        self.assertEqual(report["unguarded_backdated_url_clone_rule_verdict"], "WARN")
        self.assertFalse(report["unguarded_clone_is_external_competitor"])
        self.assertFalse(report["historical_publication_authenticated"])
        self.assertFalse(report["real_vendor_model_called"])
        self.assertFalse(report["sponsor_eligibility_certified"])
        attacks = [x for x in report["cases"] if x["attempted_source_manipulation"]]
        self.assertEqual(len(attacks), 4)
        self.assertTrue(all(x["observed_boundary"].endswith("_REFUSED") for x in attacks))

    def test_challenge_never_reads_live_sponsor_or_memory(self):
        with patch("evidencetrail.adapters.zetaris.ZetarisAdapter.fetch_two_logical_sources",
                   side_effect=AssertionError("no Zetaris network")), patch(
             "evidencetrail.adapters.meterless.MeterlessRuntimeProvider.chat",
                   side_effect=AssertionError("no Meterless model")), patch(
             "evidencetrail.adapters.hmem.HMemAdapter.query",
                   side_effect=AssertionError("no H-MEM state")):
            report = run_evidence_integrity_challenge()
        self.assertEqual(report["passed_count"], 7)

    def test_local_http_challenge_and_demo_are_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = EvidenceTrailPipeline(
                sample_mode=True, persist_dir=Path(tmp)/"hmem",
                log_dir=Path(tmp)/"logs")
            server = create_local_server("127.0.0.1", 0, pipeline=pipeline)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/integrity", timeout=10) as resp:
                    self.assertEqual(resp.status, 200)
                    report = json.loads(resp.read().decode("utf8"))
                self.assertEqual(report["kind"],
                    "EVIDENCETRAIL_OFFLINE_SOURCE_INDEPENDENCE_CHALLENGE_V1")
                self.assertTrue(report["all_cases_pass"])
                with urlopen(base + "/demo", timeout=5) as resp:
                    html = resp.read().decode("utf8")
                self.assertIn('id="integrityLab"', html)
                self.assertIn('fetch("/integrity"', html)
                self.assertEqual(list((Path(tmp)/"logs").glob("run-*.json")), [])
                self.assertEqual(list((Path(tmp)/"logs").glob("trace-*.jsonl")), [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_browser_contract_renders_text_only_and_labels_truth(self):
        text = DEMO_HTML.read_text("utf8")
        self.assertIn('id="integrityCases"', text)
        self.assertIn('id="unguardedAttack"', text)
        self.assertIn('id="protectedAttack"', text)
        self.assertIn('data.case_count!==(data.cases||[]).length', text)
        self.assertIn("sponsor_eligibility_certified!==false", text)
        self.assertNotIn("innerHTML", text)
        self.assertIn("textContent", text)
        self.assertNotIn('src="https://', text)


if __name__ == "__main__":
    unittest.main()
