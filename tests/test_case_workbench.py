"""Behavioral tests of operator authoring, not source authentication."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from evidencetrail.case_workbench import (
    DraftRefusal, append_case_evidence, prepare_case_draft,
)


def source(sid="ENTRY-A", value="17", issue="2025-02-04T08:00:00Z"):
    return {"source_id": sid, "claim_key": "STOCK", "issuer_family": "TEST_LOG",
            "unit": "pallets", "value": value, "publisher": "Fictional test log",
            "locator": "synthetic://test/"+sid, "excerpt": f"FICTIONAL {sid}: {value} pallets.",
            "source_type": "fictional", "clock_type": "precise", "issued_at": issue}


def draft():
    return {"case_id": "REVIEWER-NEW-CASE", "title": "A newly entered stock review",
            "question": "Which records change this declared stock?",
            "as_of_utc": "2025-02-04T09:00:00Z", "sources": [source()]}


class CaseWorkbenchTests(unittest.TestCase):
    def test_form_values_build_a_valid_case_without_manual_hashes(self):
        raw = draft(); saved = deepcopy(raw)
        with patch("urllib.request.urlopen", side_effect=AssertionError("NO NETWORK")):
            result = prepare_case_draft(raw)
        self.assertEqual(raw, saved)
        self.assertEqual(result["investigation"]["why"]["selected_claims"]["STOCK"]["value"], 17)
        self.assertEqual(result["pin_origin"], "GENERATED_FROM_OPERATOR_ENTRIES_NOT_INDEPENDENT_MANIFEST")
        self.assertFalse(result["external_source_authentication_performed"])
        self.assertFalse(result["model_or_sponsor_called"])
        self.assertEqual(result["preview_sources"][0]["admission_clock_utc"], "2025-02-04T08:00:00Z")

    def test_row_errors_have_safe_field_and_index_not_caller_text(self):
        raw = draft(); raw["sources"][0]["value"] = "<secret-invalid-value>"
        with self.assertRaises(DraftRefusal) as raised: prepare_case_draft(raw)
        issue = raised.exception.issues[0]
        self.assertEqual((issue["row"], issue["field"]), (1, "value"))
        self.assertNotIn("secret-invalid", str(raised.exception.issues))

    def test_numeric_types_and_nonfinite_or_fractional_values_are_refused(self):
        for value in (True, -1, 1.2, "1e4", "17.0", "", "100000001", float("nan")):
            raw = draft(); raw["sources"][0]["value"] = value
            with self.subTest(value=value), self.assertRaises(DraftRefusal): prepare_case_draft(raw)

    def test_date_only_cutoff_uses_declared_offset_without_inventing_issue_time(self):
        raw = draft(); row = source("DAY", "30")
        row.pop("issued_at"); row.update(clock_type="local_day", local_day="2025-02-04", utc_offset_minutes=420)
        raw["sources"].append(row); raw["as_of_utc"] = "2025-02-04T16:59:59Z"
        before = prepare_case_draft(raw)
        pack = before["case_pack"]
        self.assertIsNone(pack["sources"][1]["issued_at_claimed_utc"])
        self.assertEqual(pack["pins"][1]["curator_not_before_utc"], "2025-02-04T17:00:00Z")
        self.assertFalse(before["preview_sources"][1]["admitted_at_requested_policy"])
        raw["as_of_utc"] = "2025-02-04T17:00:00Z"
        after = prepare_case_draft(raw)
        self.assertEqual(after["investigation"]["why"]["selected_claims"]["STOCK"]["value"], 30)

    def test_naive_and_impossible_or_ambiguous_clocks_are_refused(self):
        for clocks in ({"issued_at": "2025-02-04T08:00:00"},
                       {"clock_type": "local_day", "local_day": "2025-02-30", "utc_offset_minutes": 420},
                       {"clock_type": "local_day", "local_day": "2025-02-04", "utc_offset_minutes": True}):
            raw = draft(); raw["sources"][0].update(clocks)
            with self.subTest(clocks=clocks), self.assertRaises(DraftRefusal): prepare_case_draft(raw)

    def test_same_claim_cannot_have_incompatible_units_or_issuer(self):
        for field, value in (("unit", "boxes"), ("issuer_family", "OTHER")):
            raw = draft(); extra = source("ENTRY-B", "19"); extra[field] = value; raw["sources"].append(extra)
            with self.subTest(field=field), self.assertRaises(DraftRefusal): prepare_case_draft(raw)

    def test_unknown_privileged_fields_and_external_locator_are_refused(self):
        for change in ({"first_availability_proven_utc": "2025-01-01T00:00:00Z"},
                       {"source_type": "authenticated"}, {"locator": "https://user:key@example.org/"}):
            raw = draft(); raw["sources"][0].update(change)
            with self.subTest(change=change), self.assertRaises(DraftRefusal): prepare_case_draft(raw)

    def test_append_preserves_original_records_and_compares_same_clock(self):
        original = prepare_case_draft(draft())["case_pack"]; saved = deepcopy(original)
        added = source("ENTRY-B", "29", "2025-02-04T08:30:00Z")
        report = append_case_evidence(original, [added])
        self.assertEqual(original, saved)
        self.assertEqual(report["case_pack"]["sources"][:1], saved["sources"])
        self.assertEqual(report["case_pack"]["pins"][:1], saved["pins"])
        self.assertEqual(report["before"]["why"]["as_of_utc"], report["after"]["why"]["as_of_utc"])
        self.assertEqual(report["comparison"]["changed_claims"][0]["after"]["value"], 29)
        self.assertTrue(report["comparison"]["value_or_availability_changed"])
        self.assertEqual(report["new_admitted_source_ids"], ["ENTRY-B"])
        self.assertEqual(report["evidence_update_origin"], "OPERATOR_ADDITION_NOT_AUTONOMOUS_REQUERY")
        self.assertFalse(report["model_or_sponsor_called"])

    def test_future_addition_does_not_change_the_current_claim(self):
        original = prepare_case_draft(draft())["case_pack"]
        result = append_case_evidence(original, [source("FUTURE", "99", "2025-02-04T10:00:00Z")])
        self.assertFalse(result["comparison"]["value_or_availability_changed"])
        self.assertEqual(result["new_admitted_source_ids"], [])

    def test_conflicting_new_source_causes_abstention_not_convenient_fallback(self):
        original = prepare_case_draft(draft())["case_pack"]
        result = append_case_evidence(original, [source("CONFLICT", "99")])
        self.assertNotIn("STOCK", result["after"]["why"]["selected_claims"])
        self.assertTrue(result["after"]["why"]["unresolved_claim_conflicts"])

    def test_original_corruption_and_reused_identity_cannot_be_repaired_by_addition(self):
        original = prepare_case_draft(draft())["case_pack"]
        with self.assertRaises(DraftRefusal): append_case_evidence(original, [source()])
        original["sources"][0]["excerpt"] = "changed without review"
        with self.assertRaises(DraftRefusal): append_case_evidence(original, [source("NEW")])

    def test_strict_addition_is_not_an_external_attestation(self):
        original = prepare_case_draft(draft())["case_pack"]
        result = append_case_evidence(original, [source("NEW", "29")], strict=True)
        self.assertEqual(result["before"]["why"]["selected_claims"], {})
        self.assertEqual(result["after"]["why"]["selected_claims"], {})
        self.assertFalse(result["comparison"]["value_or_availability_changed"])

    def test_generated_case_and_addition_bounds_are_enforced(self):
        raw = draft(); raw["sources"] = [source(f"ROW-{i}") for i in range(13)]
        with self.assertRaises(DraftRefusal): prepare_case_draft(raw)
        raw["sources"] = [source(f"ROW-{i}") for i in range(12)]
        pack = prepare_case_draft(raw)["case_pack"]
        with self.assertRaises(DraftRefusal): append_case_evidence(pack, [source("EXTRA")])


if __name__ == "__main__": unittest.main()
