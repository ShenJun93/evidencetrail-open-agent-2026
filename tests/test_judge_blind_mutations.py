"""Judges' blind mutation gates: time alone never causes a simulated WARN.

All cases use the actual offline EvidenceTrail pipeline and a mutated catalog.
No vendor traffic, emergency advice, or sponsor acceptance is claimed.
"""
from __future__ import annotations

from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from evidencetrail.catalog import all_catalog
from evidencetrail.models import RecordKind, RunRequest
from evidencetrail.pipeline import EvidenceTrailPipeline

TARGET = "GOV-2024-09-08-1637"


def run_1645(rows):
    request = RunRequest.from_dict({
        "schema_version": "1",
        "mission_id": "yagi-yenbai-2024",
        "scenario_id": "yagi-replay-alpha",
        "as_of_utc": "2024-09-08T09:45:00Z",
        "mode": "REPORTED_DATELINE_REPLAY",
        "province_2024": "yen bai",
        "district_2024": "luc yen",
        "granularity": "district",
        "question": "Fictional coordinator watch at the reported dateline?",
        "sample_mode": True,
    })
    with tempfile.TemporaryDirectory(prefix="evidencetrail-judge-mutation-") as temp:
        pipe = EvidenceTrailPipeline(
            sample_mode=True,
            catalog_override=rows,
            persist_dir=Path(temp) / "memory",
            log_dir=Path(temp) / "logs",
        )
        return pipe.run(request)


class NoHardcodedWarnMutationTests(unittest.TestCase):
    def test_unmodified_1645_is_simulated_warn(self):
        result = run_1645(deepcopy(all_catalog()))
        self.assertEqual(result.verdict.value, "WARN")
        self.assertIn(TARGET, result.eligible_source_ids)
        self.assertIn("SIMULATED", result.rationale)

    def test_1645_without_district_named_article_must_abstain(self):
        rows = deepcopy(all_catalog())
        for row in rows:
            if row.source_id == TARGET:
                row.named_districts_2024 = ["van yen"]
        result = run_1645(rows)
        self.assertEqual(result.verdict.value, "INSUFFICIENT_EVIDENCE")
        self.assertIn(TARGET, result.eligible_source_ids)
        self.assertTrue(any("public source naming district" in x for x in result.missing_facts))

    def test_1645_without_synthetic_watch_authorization_must_abstain(self):
        rows = deepcopy(all_catalog())
        found = False
        for row in rows:
            if row.record_kind == RecordKind.SYNTHETIC_CAPACITY:
                row.plan_predicates["coordinator_watch_authorized"] = False
                found = True
        self.assertTrue(found)
        result = run_1645(rows)
        self.assertEqual(result.verdict.value, "INSUFFICIENT_EVIDENCE")
        self.assertTrue(any("coordinator_watch_authorized" in x for x in result.missing_facts))

    def test_1645_other_scenario_capacity_must_abstain(self):
        rows = deepcopy(all_catalog())
        for row in rows:
            if row.record_kind == RecordKind.SYNTHETIC_CAPACITY:
                row.scenario_id = "different-scenario"
        result = run_1645(rows)
        self.assertEqual(result.verdict.value, "INSUFFICIENT_EVIDENCE")
        self.assertTrue(any("scenario-bound" in x for x in result.missing_facts))

    def test_1645_missing_capacity_must_abstain(self):
        rows = [row for row in deepcopy(all_catalog())
                if row.record_kind != RecordKind.SYNTHETIC_CAPACITY]
        result = run_1645(rows)
        self.assertEqual(result.verdict.value, "INSUFFICIENT_EVIDENCE")
        self.assertTrue(any("scenario-bound" in x for x in result.missing_facts))


if __name__ == "__main__":
    unittest.main()
