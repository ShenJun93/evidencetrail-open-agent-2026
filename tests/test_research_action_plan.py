"""Research plans must explain missing proof without fabricating evidence or execution."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.catalog import all_catalog
from evidencetrail.counterfactual import counterfactual_dossier
from evidencetrail.models import RunRequest, ReplayMode


def report(at: str = "1645", mode: ReplayMode = ReplayMode.REPORTED_DATELINE_REPLAY):
    raw = json.loads(Path(f"samples/inputs/yagi_{at}_lucyen.json").read_text("utf8"))
    raw["mode"] = mode.value
    return counterfactual_dossier(RunRequest.from_dict(raw), all_catalog())


class ResearchActionPlanContracts(unittest.TestCase):
    def test_early_abstention_prioritizes_missing_district_evidence(self):
        result = report("1630")
        plan = result["current"]["research_action_plan"]
        codes = [a["code"] for a in plan["next_evidence_steps"]]
        self.assertEqual(plan["current_rule_verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("MISSING_DISTRICT_NAMED_BULLETIN", codes)
        self.assertIn("publication proof", str(plan).lower())
        self.assertTrue(all(not x["perform_network_or_field_action_now"]
                            for x in plan["next_evidence_steps"]))
        self.assertFalse(plan["model_or_vendor_called"])

    def test_simulated_warn_pivotal_inputs_and_provenance_action(self):
        plan = report()["current"]["research_action_plan"]
        self.assertEqual(plan["current_rule_verdict"], "WARN")
        self.assertTrue(plan["simulated_rule_warning_only"])
        self.assertEqual(set(plan["pivotal_source_ids"]), {
            "GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"
        })
        codes = {a["code"] for a in plan["next_evidence_steps"]}
        self.assertIn("VERIFY_PIVOTAL_PUBLICATION_PROVENANCE", codes)
        self.assertIn("RECHECK_PIVOTAL_FICTIONAL_CAPACITY", codes)
        self.assertFalse(plan["operational_emergency_action_authorized"])
        self.assertFalse(plan["external_field_accuracy_demonstrated"])

    def test_strict_mode_requires_archive_authentication(self):
        plan = report(mode=ReplayMode.STRICT_AS_OF_2024)["current"]["research_action_plan"]
        codes = {x["code"] for x in plan["next_evidence_steps"]}
        self.assertIn("HISTORICAL_AVAILABILITY_NOT_AUTHENTICATED", codes)
        self.assertFalse(plan["simulated_rule_warning_only"])
        self.assertTrue(plan["requires_human_review"])

    def test_time_and_policy_contrast_do_not_claim_causation(self):
        plan = report()["current"]["research_action_plan"]
        self.assertTrue(plan["time_comparison"]["changed"])
        self.assertEqual(plan["time_comparison"]["newly_eligible_source_ids"],
                         ["GOV-2024-09-08-1637"])
        self.assertTrue(plan["policy_comparison"]["differs"])
        self.assertFalse(plan["new_evidence_collected"])

    def test_no_sponsor_transport_used_even_if_configured(self):
        with patch("evidencetrail.adapters.nvidia_nim.NvidiaNemotronDirect.chat",
                   side_effect=AssertionError("No NVIDIA permitted")), patch(
                   "evidencetrail.adapters.meterless.MeterlessRuntimeProvider.chat",
                   side_effect=AssertionError("No Meterless permitted")):
            plan = report()["current"]["research_action_plan"]
        self.assertFalse(plan["model_or_vendor_called"])

    def test_plan_is_readable_through_existing_sample_local_api_contract(self):
        p = report()["current"]["research_action_plan"]
        self.assertTrue(p["priority_one"].startswith(("MISSING_", "VERIFY_", "HISTORICAL_")))
        self.assertGreater(len(p["next_evidence_steps"]), 1)
        self.assertTrue(all(x["human_approval_required"] for x in p["next_evidence_steps"]))


if __name__ == "__main__":
    unittest.main()
