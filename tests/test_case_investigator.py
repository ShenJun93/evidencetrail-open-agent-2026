"""Unseen, operator-declared cases and bounded joint source withdrawal.

Fictional records only; no model, sponsor, external publication or human proof.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import unittest
from unittest.mock import patch

from evidencetrail.case_investigator import (
    CaseRefusal, example_case, investigate_case,
)
from evidencetrail.models import RecordKind, ReplayMode
from tests.test_claim_ledger_transfer import fresh_issuer_source


def unknown_case():
    sources, pins = [], []
    for sid, value, hour in [("OLD", 3, 7), ("BACKUP-A", 17, 8),
                             ("BACKUP-B", 17, 8), ("FUTURE", 99, 10)]:
        row, pin, rule = fresh_issuer_source(
            source_id=sid, clock=f"2025-02-04T{hour:02d}:00:00Z",
            kind=RecordKind.SYNTHETIC_CAPACITY)
        row.excerpt = row.paraphrase = f"FICTIONAL unseen source {sid}: {value} units"
        row.excerpt_sha256 = sha256(row.excerpt.encode()).hexdigest()
        row.observation_fields["reading"] = value
        pin = replace(pin, expected_value=value, excerpt_sha256=row.excerpt_sha256)
        sources.append(row.to_public_dict()); pins.append(asdict(pin))
    return {
        "schema_version": "evidencetrail.case.v1", "case_id": "UNSCRIPTED-CASE",
        "title": "An independently authored fictional test case",
        "question": "Which source combination changes this declared reading?",
        "as_of_utc": "2025-02-04T09:00:00Z",
        "rules": [asdict(rule)], "sources": sources, "pins": pins,
    }


class CaseInvestigatorTests(unittest.TestCase):
    def test_unseen_case_uses_actual_values_and_names_not_fixed_milton_answers(self):
        result = investigate_case(unknown_case())
        claim = result["why"]["selected_claims"]["LAB_READING"]
        self.assertEqual(claim["value"], 17)
        self.assertTrue(claim["fictional"])
        self.assertEqual(result["case_id"], "UNSCRIPTED-CASE")
        self.assertEqual(result["trust_basis"], "OPERATOR_DECLARED_NOT_EXTERNALLY_VERIFIED")
        self.assertFalse(result["model_or_sponsor_called"])
        self.assertFalse(result["external_source_authentication_performed"])
        self.assertEqual(result["execution_trace"][0]["action"], "VALIDATE_FULL_CASE")

    def test_joint_withdrawal_exposes_redundancy_hidden_by_single_source_removal(self):
        result = investigate_case(unknown_case(), withdrawn_source_ids=["BACKUP-A", "BACKUP-B"])
        resilience = result["resilience"]["claims"]["LAB_READING"]
        self.assertEqual(resilience["minimum_withdrawals_to_change_value_or_availability"], 2)
        sets = resilience["minimal_withdrawal_sets"]
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]["removed_source_ids"], ["BACKUP-A", "BACKUP-B"])
        self.assertEqual(sets[0]["after"]["value"], 3)
        self.assertEqual(result["experiment"]["changed_claims"][0]["after"]["value"], 3)

    def test_attribution_change_does_not_count_as_a_numeric_claim_failure(self):
        result = investigate_case(unknown_case(), withdrawn_source_ids=["BACKUP-B"])
        self.assertEqual(result["experiment"]["changed_claims"][0]["effect"],
                         "SOURCE_ATTRIBUTION_CHANGED_SAME_VALUE")
        self.assertFalse(result["experiment"]["value_or_availability_changed"])

    def test_fictional_label_change_is_not_falsely_counted_as_a_numeric_change(self):
        case = unknown_case()
        row, pin = case["sources"][1], case["pins"][1]
        for item in (row, pin):
            item["record_kind"] = "GOVERNMENT_NEWS"
            item["provenance_quality"] = "ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN"
            item["locator"] = "https://example.org/fictional-test-backup-a"
        result = investigate_case(case, withdrawn_source_ids=["BACKUP-B"])
        self.assertFalse(result["experiment"]["value_or_availability_changed"])
        self.assertFalse(result["experiment"]["selected_claims_after"]["LAB_READING"]["fictional"])

    def test_depth_one_is_honestly_bounded_not_a_claim_of_global_resilience(self):
        result = investigate_case(unknown_case(), search_depth=1)
        search = result["resilience"]
        claim = search["claims"]["LAB_READING"]
        self.assertEqual(search["searched_max_withdrawal_size"], 1)
        self.assertFalse(search["all_source_subsets_examined"])
        self.assertEqual(search["subsets_evaluated"], 3)
        self.assertIsNone(claim["minimum_withdrawals_to_change_value_or_availability"])
        self.assertEqual(claim["proven_minimum_lower_bound"], 2)
        self.assertFalse(search["resilience_is_statistical_confidence"])

    def test_exhaustive_small_case_marks_completeness_and_inclusion_minimality(self):
        result = investigate_case(unknown_case(), search_depth=3)
        search = result["resilience"]
        self.assertTrue(search["all_source_subsets_examined"])
        self.assertEqual(search["subsets_evaluated"], 7)
        self.assertEqual(len(search["claims"]["LAB_READING"]["minimal_withdrawal_sets"]), 1)
        self.assertNotIn("FUTURE", search["withdrawal_candidate_source_ids"])

    def test_full_batch_integrity_cannot_be_repaired_by_withdrawing_forged_future_row(self):
        case = unknown_case()
        case["sources"][-1]["excerpt"] = "tampered future text"
        with self.assertRaises(ValueError):
            investigate_case(case, withdrawn_source_ids=["FUTURE"])

    def test_strict_never_promotes_declared_pins_to_availability_attestation(self):
        result = investigate_case(unknown_case(), strict=True)
        self.assertEqual(result["why"]["selected_claims"], {})
        self.assertEqual(result["resilience"]["subsets_evaluated"], 0)
        self.assertFalse(result["external_source_authentication_performed"])

    def test_caller_authenticated_provenance_and_first_availability_are_refused(self):
        for mutate in (lambda s:s.update(first_availability_proven_utc="2024-01-01T00:00:00Z"),
                       lambda s:s.update(provenance_quality="AUTHENTICATED_2024_SNAPSHOT")):
            case = unknown_case(); mutate(case["sources"][0])
            with self.assertRaises(CaseRefusal):
                investigate_case(case)

    def test_unknown_controls_duplicate_unknown_withdrawals_and_bad_depth_refused(self):
        for ids in (["NOT-REGISTERED"], ["OLD", "OLD"], "OLD", [1]):
            with self.subTest(ids=ids), self.assertRaises(CaseRefusal):
                investigate_case(unknown_case(), withdrawn_source_ids=ids)
        for depth in (0, 4, True, "2"):
            with self.subTest(depth=depth), self.assertRaises(CaseRefusal):
                investigate_case(unknown_case(), search_depth=depth)
        case = unknown_case(); case["provider"] = "call-a-model"
        with self.assertRaises(CaseRefusal):
            investigate_case(case)

    def test_urls_are_never_fetched_and_input_is_not_mutated(self):
        case = unknown_case(); saved = deepcopy(case)
        with patch("urllib.request.urlopen", side_effect=AssertionError("NO NETWORK")), patch(
                "urllib.request.build_opener", side_effect=AssertionError("NO NETWORK")):
            result = investigate_case(case)
        self.assertEqual(case, saved)
        self.assertFalse(result["model_or_sponsor_called"])

    def test_arbitrary_asof_changes_unseen_answer_and_rejects_naive_clock(self):
        result = investigate_case(unknown_case(), as_of_utc="2025-02-04T10:00:00Z")
        self.assertEqual(result["why"]["selected_claims"]["LAB_READING"]["value"], 99)
        with self.assertRaises(ValueError):
            investigate_case(unknown_case(), as_of_utc="2025-02-04T10:00:00")

    def test_original_pack_clock_must_be_aware_even_with_a_valid_override(self):
        case = unknown_case(); case["as_of_utc"] = "2025-02-04T09:00:00"
        with self.assertRaises(CaseRefusal):
            investigate_case(case, as_of_utc="2025-02-04T09:00:00Z")

    def test_fractional_asof_is_preserved_at_a_fractional_source_boundary(self):
        case = unknown_case(); case["as_of_utc"] = "2025-02-04T08:00:00.500000Z"
        for idx in (1, 2):
            for key in ("published_at_displayed_utc", "issued_at_claimed_utc"):
                case["sources"][idx][key] = "2025-02-04T08:00:00.250000Z"
            case["pins"][idx]["claimed_issue_utc"] = "2025-02-04T08:00:00.250000Z"
        result = investigate_case(case)
        self.assertEqual(result["why"]["selected_claims"]["LAB_READING"]["value"], 17)
        self.assertEqual(result["why"]["as_of_utc"], case["as_of_utc"])

    def test_matching_pins_cannot_retype_retrospective_or_imported_origin_as_news(self):
        for origin in ("RETROSPECTIVE_2026_HINDCAST", "IMPORTED_2024_DATELINE_ON_2026_PORTAL"):
            case = unknown_case()
            for item in (case["sources"][0], case["pins"][0]):
                item["record_kind"] = "GOVERNMENT_NEWS"
                item["provenance_quality"] = origin
                item["locator"] = "https://example.org/retyped-retrospective"
            with self.subTest(origin=origin), self.assertRaises(CaseRefusal):
                investigate_case(case)

    def test_separate_manifest_cannot_be_silently_rebuilt_from_mutated_values(self):
        case = unknown_case(); case["sources"][1]["observation_fields"]["reading"] = 999
        with self.assertRaises(ValueError):
            investigate_case(case)

    def test_case_size_count_and_unsafe_locator_refused(self):
        case = unknown_case(); case["question"] = "x"*60001
        with self.assertRaises(CaseRefusal): investigate_case(case)
        case = unknown_case(); case["sources"] *= 4
        with self.assertRaises(CaseRefusal): investigate_case(case)
        case = unknown_case()
        case["sources"][0]["locator"] = case["pins"][0]["locator"] = "https://a:b@example.org/"
        with self.assertRaises(CaseRefusal): investigate_case(case)

    def test_fictional_example_and_existing_milton_both_use_generic_workflow(self):
        warehouse = investigate_case(example_case("warehouse"))
        self.assertTrue(all(c["fictional"] for c in warehouse["why"]["selected_claims"].values()))
        milton = investigate_case(example_case("milton"))
        self.assertEqual(milton["why"]["selected_claims"]["NHC_WIND"]["value"], 100)
        self.assertEqual(milton["why"]["selected_claims"]["FL_ORDER"]["value"], 51)

    def test_order_does_not_change_minimal_withdrawal_findings(self):
        case = unknown_case(); before = investigate_case(case)
        case["sources"].reverse(); case["pins"].reverse()
        after = investigate_case(case)
        self.assertEqual(before["resilience"], after["resilience"])


if __name__ == "__main__": unittest.main()
