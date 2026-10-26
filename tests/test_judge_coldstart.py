"""Pure offline checks for the single-command cold judge runner.

Mock all subprocess execution: this suite NEVER launches Python/Node,
accesses a sponsor API, opens a credential file or starts Edge.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_judge_coldstart as cold


class JudgeColdstartContractTests(unittest.TestCase):
    def test_child_environment_drops_secrets_and_forces_all_sponsor_flags_off(self):
        original = {
            "PATH": r"C:\Windows\System32",
            "SYSTEMROOT": r"C:\Windows",
            "NEBIUS_API_KEY": "fixture_secret_never_forwarded",
            "NVIDIA_API_KEY": "fixture_secret_two_never_forwarded",
            "ZETARIS_API_KEY": "fixture_secret_three_never_forwarded",
            "METERLESS_RUNTIME_TOKEN": "fixture_secret_four_never_forwarded",
            "EVIDENCETRAIL_NEBIUS_ENABLED": "true",
            "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "true",
            "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED": "true",
            "OPENAI_API_KEY": "another_fake_secret",
        }
        cleaned = cold.safe_environment(original)
        self.assertEqual(cleaned["PATH"], original["PATH"])
        self.assertEqual(cleaned["SAMPLE_MODE"], "true")
        for key in (
            "NEBIUS_API_KEY", "NVIDIA_API_KEY", "ZETARIS_API_KEY",
            "METERLESS_RUNTIME_TOKEN", "OPENAI_API_KEY",
        ):
            self.assertNotIn(key, cleaned)
        for key in (
            "EVIDENCETRAIL_NEBIUS_ENABLED",
            "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED",
            "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED",
            "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT",
            "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT",
        ):
            self.assertEqual(cleaned[key], "false")

    def test_python_parser_never_accepts_lost_or_failing_results(self):
        valid = {
            "test_status": "PASS", "test_total": 279,
            "sample_cases": 3, "failures": 0, "errors": 0,
        }
        stream = "untrusted preceding output\n" + json.dumps(valid) + "\n"
        okay, detail = cold.check_acceptance(stream, 0)
        self.assertTrue(okay)
        self.assertEqual(detail["python_tests"], 279)
        self.assertFalse(cold.check_acceptance(stream, 1)[0])
        self.assertFalse(cold.check_acceptance("not JSON", 0)[0])
        valid["errors"] = 1
        self.assertFalse(cold.check_acceptance(json.dumps(valid), 0)[0])

    def test_chronology_parser_requires_20_gold_cases(self):
        base = {
            "kind": "OFFLINE_ADVERSARIAL_CHRONOLOGY_BENCHMARK_V1",
            "pass": 20, "total": 20, "failed_cases": [],
        }
        self.assertTrue(cold.check_chronology(json.dumps(base), 0)[0])
        base["pass"] = 19
        self.assertFalse(cold.check_chronology(json.dumps(base), 0)[0])

    def test_edge_parser_requires_all_three_scenarios(self):
        stream = "\n".join(cold.EDGE_MARKERS) + "\n"
        self.assertTrue(cold.check_edge(stream, 0)[0])
        self.assertFalse(cold.check_edge(stream, 1)[0])
        self.assertFalse(cold.check_edge("EDGE_COUNTERFACTUAL_ALL_PASS", 0)[0])

    def test_why_edge_parser_requires_source_map_and_failure_markers(self):
        stream = "\n".join(cold.WHY_EDGE_MARKERS) + "\n"
        okay, evidence = cold.check_why_edge(stream, 0)
        self.assertTrue(okay)
        self.assertEqual(evidence["evidence_map_interaction"], "PASS")
        self.assertFalse(cold.check_why_edge(stream, 1)[0])
        self.assertFalse(cold.check_why_edge("WHY_EDGE_ASOF_11AM_PASS_100_51", 0)[0])

    def test_success_with_dirty_worktree_cannot_be_clean_checkout_proof(self):
        accepted = json.dumps({
            "test_status": "PASS", "test_total": 279,
            "failures": 0, "errors": 0, "sample_cases": 3,
        })
        chrono = json.dumps({
            "kind": "OFFLINE_ADVERSARIAL_CHRONOLOGY_BENCHMARK_V1",
            "pass": 20, "total": 20, "failed_cases": [],
        })
        edge = "\n".join(cold.EDGE_MARKERS)
        why_edge = "\n".join(cold.WHY_EDGE_MARKERS)
        calls = []
        def fake_execute(command, *, env, timeout):
            calls.append(command)
            return 0, (accepted, chrono, edge, why_edge)[len(calls) - 1]
        with tempfile.TemporaryDirectory() as temp, patch.object(
            cold, "OUTPUT", Path(temp) / "receipt.json"
        ), patch.object(
            cold, "git_baseline", return_value={
                "head": "a" * 40, "tracked_clean_before_tests": False
            }
        ), patch.object(cold, "execute", side_effect=fake_execute):
            exit_code = cold.main([])
            receipt = json.loads((Path(temp) / "receipt.json").read_text("utf8"))
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 4)
        self.assertEqual(receipt["status"], "PASS")
        self.assertFalse(receipt["independent_clean_checkout_proven"])
        self.assertFalse(receipt["external_sponsor_requests_authorized"])
        self.assertFalse(receipt["key_file_read_by_this_runner"])

    def test_skipped_browser_is_partial_not_full_pass(self):
        accepted = json.dumps({
            "test_status": "PASS", "test_total": 279,
            "failures": 0, "errors": 0, "sample_cases": 3,
        })
        chrono = json.dumps({
            "kind": "OFFLINE_ADVERSARIAL_CHRONOLOGY_BENCHMARK_V1",
            "pass": 20, "total": 20, "failed_cases": [],
        })
        outputs = [accepted, chrono]
        with tempfile.TemporaryDirectory() as temp, patch.object(
            cold, "OUTPUT", Path(temp) / "receipt.json"
        ), patch.object(
            cold, "git_baseline", return_value={
                "head": "a" * 40, "tracked_clean_before_tests": True
            }
        ), patch.object(
            cold, "execute", side_effect=lambda cmd, **kw: (0, outputs.pop(0))
        ):
            ret = cold.main(["--skip-edge"])
            receipt = json.loads((Path(temp) / "receipt.json").read_text("utf8"))
        self.assertEqual(ret, 0)
        self.assertEqual(receipt["status"], "PARTIAL_EDGE_SKIPPED")
        self.assertEqual(receipt["steps"]["edge_e2e"]["status"], "SKIPPED")
        self.assertEqual(receipt["steps"]["why_edge_e2e"]["status"], "SKIPPED")
        self.assertFalse(receipt["independent_clean_checkout_proven"])


if __name__ == "__main__":
    unittest.main()
