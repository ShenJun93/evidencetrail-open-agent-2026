"""Adversarial rule-counterfactual tests: no sponsor call, no fake warning.

Validate the UNIQUE added source and the exact minimum sufficient subset for
the 16:30 -> 16:45 change; ensure a fictional capacity can never be passed off
as a real operational capability or signed archived 2024 source.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from evidencetrail.catalog import all_catalog, ict
from evidencetrail.counterfactual import counterfactual_dossier
from evidencetrail.models import ReplayMode, RunRequest, Verdict
from evidencetrail.reducer import decide


def sample(at: str = "1645", *, policy=ReplayMode.REPORTED_DATELINE_REPLAY):
    data = json.loads(
        Path(f"samples/inputs/yagi_{at}_lucyen.json").read_text(encoding="utf8")
    )
    data["mode"] = policy.value
    return RunRequest.from_dict(data)


class CounterfactualRuleLabTests(unittest.TestCase):
    def test_synthetic_watch_minimum_exactly_two_sources_at_1645(self):
        result = counterfactual_dossier(sample(), all_catalog())
        current = result["current"]
        self.assertEqual(current["rule_verdict"], "WARN")
        self.assertEqual(current["minimum_set_cardinality"], 2)
        witness = [x["source_id"] for x in current["minimum_sufficient_source_set"]]
        self.assertEqual(witness, [
            "GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"
        ])
        self.assertTrue(current["minimum_sufficient_source_set"][1]["synthetic_scenario"])
        self.assertFalse(current["minimum_sufficient_source_set"][0][
            "first_archive_proof_verified_in_default_catalog"
        ])
        self.assertTrue(result["simulation_not_historical_warning"])

    def test_remove_each_pivotal_source_inverts_the_rule_only(self):
        r = counterfactual_dossier(sample(), all_catalog())["current"]
        self.assertEqual(set(r["pivotal_source_ids"]), {
            "GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"
        })
        for row in r["source_removal_tests"]:
            if row["changes_rule_verdict"]:
                self.assertEqual(row["without_source_rule_verdict"],
                                 Verdict.INSUFFICIENT_EVIDENCE.value)
            else:
                self.assertEqual(row["without_source_rule_verdict"], Verdict.WARN.value)

    def test_1630_abstains_and_requests_a_district_source(self):
        report = counterfactual_dossier(sample("1630"), all_catalog())
        now = report["current"]
        self.assertEqual(now["rule_verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(now["minimum_set_proven"])
        self.assertIsNone(now["minimum_set_cardinality"])
        self.assertEqual(now["minimum_sufficient_source_set"], [])
        self.assertIn("MISSING_DISTRICT_NAMED_BULLETIN", {
            r["code"] for r in now["next_evidence_requirements"]
        })
        self.assertNotIn("GOV-2024-09-08-1637", now["eligible_source_ids"])

    def test_1645_time_and_strict_policy_contrast(self):
        report = counterfactual_dossier(sample(), all_catalog())
        self.assertEqual(report["earlier_same_policy"]["rule_verdict"],
                         "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report["earlier_by_minutes"], 15)
        self.assertEqual(report["newly_eligible_source_ids"],
                         ["GOV-2024-09-08-1637"])
        self.assertTrue(report["time_changed_rule_verdict"])
        self.assertEqual(report["same_clock_other_policy"]["rule_verdict"],
                         "INSUFFICIENT_EVIDENCE")
        self.assertTrue(report["policy_changed_rule_verdict"])

    def test_strict_makes_no_original_2024_proof_claim(self):
        report = counterfactual_dossier(
            sample(policy=ReplayMode.STRICT_AS_OF_2024), all_catalog()
        )
        self.assertEqual(report["current"]["rule_verdict"],
                         "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report["same_clock_other_policy"]["rule_verdict"], "WARN")
        self.assertIn("HISTORICAL_AVAILABILITY_NOT_AUTHENTICATED", {
            r["code"] for r in report["current"]["next_evidence_requirements"]
        })
        self.assertFalse(report["historical_source_first_publication_authenticated"])

    def test_newly_published_source_would_not_be_admitted_before_dateline(self):
        before = sample("1630")
        future = all_catalog()
        future_1637 = next(s for s in future if s.source_id == "GOV-2024-09-08-1637")
        self.assertLess(future_1637.observed_at_utc, before.as_of_utc)
        self.assertGreater(future_1637.published_at_displayed_utc, before.as_of_utc)
        self.assertNotIn(future_1637.source_id,
                         counterfactual_dossier(before, future)["current"]["eligible_source_ids"])

    def test_fake_capacity_cannot_become_real_by_more_public_sources(self):
        current = counterfactual_dossier(sample(), all_catalog())["current"]
        reqs = {r["code"] for r in current["next_evidence_requirements"]}
        self.assertIn("MISSING_REAL_SITE_POPULATION", reqs)
        self.assertIn("MISSING_VERIFIED_ROUTE_SAFETY", reqs)
        self.assertFalse(current["minimum_sufficient_source_set"][1][
            "first_archive_proof_verified_in_default_catalog"
        ])

    def test_remove_scenario_capacity_requires_a_new_plan_not_fake_warning(self):
        catalog = [s for s in all_catalog() if s.source_id != "SYN-CAP-YAGI-ALPHA-LUCYEN"]
        r = counterfactual_dossier(sample(), catalog)["current"]
        self.assertEqual(r["rule_verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("MISSING_SCENARIO_BOUND_CAPACITY", {
            x["code"] for x in r["next_evidence_requirements"]
        })

    def test_no_mutation_of_canonical_evidence_or_request(self):
        request = sample()
        original_asof = request.as_of_utc
        catalog = all_catalog()
        before = [x.to_public_dict() for x in catalog]
        counterfactual_dossier(request, catalog)
        self.assertEqual(original_asof, request.as_of_utc)
        self.assertEqual(before, [x.to_public_dict() for x in catalog])

    def test_offline_only_even_with_live_request_flag(self):
        request = sample()
        request.sample_mode = False
        with self.assertRaisesRegex(ValueError, "OFFLINE_SAMPLE_ONLY"):
            counterfactual_dossier(request, all_catalog())

    def test_invalid_time_window_and_large_catalog_rejected(self):
        for minutes in (-4, 0, 181, True, "15"):
            with self.subTest(minutes=minutes):
                with self.assertRaisesRegex(ValueError, "EARLIER_MINUTES_INVALID"):
                    counterfactual_dossier(sample(), all_catalog(),
                                           minutes_earlier=minutes)
        with self.assertRaisesRegex(ValueError, "CATALOG_LIMIT"):
            counterfactual_dossier(sample(), all_catalog() * 15)

    def test_duplicate_admissible_ids_fail_closed_instead_of_spoofing_minimum(self):
        catalog = all_catalog()
        culprit = next(s for s in catalog if s.source_id == "GOV-2024-09-08-1637")
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SOURCE"):
            counterfactual_dossier(sample(), catalog+[deepcopy(culprit)])

    def test_duplicate_id_excluded_by_time_still_refused_before_ablation(self):
        catalog = all_catalog()
        article = next(s for s in catalog if s.source_id == "GOV-2024-09-08-1637")
        # One copy is time-ineligible at 16:30 and the forged copy would
        # otherwise make a false simulated WARN, unlike the actual Collector.
        catalog.append(replace(
            article, published_at_displayed_utc=article.observed_at_utc
        ))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SOURCE_ID_REFUSED"):
            counterfactual_dossier(sample("1630"), catalog)

    def test_duplicate_id_filtered_out_by_geography_still_refused(self):
        catalog = all_catalog()
        article = next(s for s in catalog if s.source_id == "GOV-2024-09-08-1637")
        catalog.append(replace(
            article, spatial_scope=["lao cai"], named_districts_2024=["sa pa"]
        ))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SOURCE_ID_REFUSED"):
            counterfactual_dossier(sample("1645"), catalog)

    def test_reducer_is_the_actual_production_one(self):
        request = sample()
        catalog = all_catalog()
        report = counterfactual_dossier(request, catalog)
        from evidencetrail.firewall import filter_sources, jurisdiction_ok
        available, _ = filter_sources(
            [s for s in catalog if jurisdiction_ok(
                s, request.province_2024, request.district_2024
            )], request.as_of_utc, request.mode
        )
        expected = decide(request, available)[0].value
        self.assertEqual(report["current"]["rule_verdict"], expected)

    def test_no_sponsor_or_memory_called_during_analysis(self):
        request = sample()
        with patch("evidencetrail.adapters.zetaris.ZetarisAdapter.fetch_two_logical_sources",
                   side_effect=AssertionError("no sponsor data transport")), patch(
                   "evidencetrail.adapters.hmem.HMemAdapter.query",
                   side_effect=AssertionError("no model-memory transport")), patch(
                   "evidencetrail.adapters.meterless.MeterlessRuntimeProvider.chat",
                   side_effect=AssertionError("no Nightshift")):
            report = counterfactual_dossier(request, all_catalog())
        self.assertTrue(report["offline_sample_only"])
        self.assertFalse(report["official_meterless_nightshift_called"])
        self.assertFalse(report["first_party_hmem_called"])
        self.assertFalse(report["real_zetaris_query_performed"])

    def test_earlier_comparison_uses_user_clock_not_fixed_1645(self):
        request = sample("1630")
        result = counterfactual_dossier(request, all_catalog(), minutes_earlier=30)
        self.assertEqual(result["earlier_same_policy"]["as_of_utc"],
                         "2024-09-08T09:00:00Z")
        self.assertEqual(result["current"]["as_of_utc"], "2024-09-08T09:30:00Z")


if __name__ == "__main__":
    unittest.main()
