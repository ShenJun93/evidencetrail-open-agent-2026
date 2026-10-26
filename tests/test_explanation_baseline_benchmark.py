"""Policy-gold comparative benchmark with explicitly unsafe internal control."""
from __future__ import annotations

import unittest

from run_explanation_baseline_benchmark import (
    explanation_checks, run_comparison, weak_time_blind_control,
)
from run_judge_chronology_stress_benchmark import test_matrix


class BaselineComparisonTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_comparison()

    def test_exact_20_existing_hand_authored_policy_gold_cases(self):
        self.assertEqual(self.report["case_count"], 20)
        self.assertEqual(self.report["evidencetrail_policy_gold_passes"], 20)
        self.assertTrue(self.report["all_evidencetrail_policy_checks_pass"])

    def test_weak_baseline_demonstrates_observation_time_trap(self):
        first = test_matrix()[0]
        self.assertEqual(first.name, "01_baseline_1630_abstains")
        self.assertEqual(first.gold_verdict, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(weak_time_blind_control(first), "WARN")
        self.assertGreaterEqual(self.report["own_weak_control_false_warn_cases"], 1)

    def test_adversarial_baseline_not_fraudulently_called_external_agent(self):
        self.assertFalse(self.report["baseline_is_rival_product_or_external_llm"])
        self.assertFalse(self.report["benchmark_is_external_field_test"])
        self.assertFalse(self.report["benchmark_is_storm_prediction_accuracy"])
        self.assertFalse(self.report["model_vendor_or_paid_api_called"])
        self.assertEqual(self.report["baseline"],
                         "OWN_DELIBERATELY_UNSAFE_NO_TEMPORAL_OR_ORIGIN_FIREWALL")
        self.assertLess(self.report["own_weak_control_policy_gold_passes"], 20)

    def test_three_explanation_gold_checks_pass_without_new_evidence(self):
        rows = explanation_checks()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(x["passed"] for x in rows))
        self.assertEqual(self.report["additional_plan_gold_passes"], 3)

    def test_all_case_verdicts_labeled_with_real_source_policy_gold(self):
        self.assertEqual(len(self.report["cases"]), len(test_matrix()))
        for case in self.report["cases"]:
            self.assertIn(case["policy_gold_verdict"], {"WARN", "INSUFFICIENT_EVIDENCE"})
            self.assertIn(case["evidencetrail_actual_verdict"],
                          {"WARN", "INSUFFICIENT_EVIDENCE"})
            self.assertIn(case["time_blind_own_control_verdict"],
                          {"WARN", "INSUFFICIENT_EVIDENCE"})
            self.assertTrue(case["evidencetrail_matches_gold_and_safety"])


if __name__ == "__main__":
    unittest.main()
