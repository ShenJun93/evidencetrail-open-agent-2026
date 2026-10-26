"""Observation-before-publication trap: 15:00 gauges in a 16:37 source."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evidencetrail.catalog import all_catalog, ict
from evidencetrail.firewall import filter_sources
from evidencetrail.models import ReplayMode, RunRequest
from evidencetrail.pipeline import EvidenceTrailPipeline


def _req(as_of: str, mode: str = "REPORTED_DATELINE_REPLAY") -> RunRequest:
    return RunRequest.from_dict(
        {
            "schema_version": "1",
            "mission_id": "yagi-yenbai-2024",
            "scenario_id": "yagi-replay-alpha",
            "as_of_utc": as_of,
            "mode": mode,
            "province_2024": "yen bai",
            "district_2024": "luc yen",
            "granularity": "district",
            "question": "district simulated watch?",
            "sample_mode": True,
        }
    )


class Yagi1637TrapTests(unittest.TestCase):
    def test_firewall_1630_excludes_1637_despite_1500_observation(self):
        as_of = ict(2024, 9, 8, 16, 30)
        eligible, excluded = filter_sources(all_catalog(), as_of, ReplayMode.REPORTED_DATELINE_REPLAY)
        ids = {s.source_id for s in eligible}
        self.assertIn("GOV-2024-09-08-1530", ids)
        self.assertIn("GOV-2024-09-08-1621", ids)
        self.assertNotIn("GOV-2024-09-08-1637", ids)
        reasons = {e["source_id"]: e for e in excluded}
        self.assertEqual(reasons["GOV-2024-09-08-1637"]["reason"], "published_at_displayed_after_as_of")
        self.assertIn("observation_time_is_not_publication_time", reasons["GOV-2024-09-08-1637"]["advisories"])

    def test_firewall_1634_still_excludes_despite_url_1631_digits(self):
        as_of = ict(2024, 9, 8, 16, 34)
        eligible, excluded = filter_sources(all_catalog(), as_of, ReplayMode.REPORTED_DATELINE_REPLAY)
        self.assertNotIn("GOV-2024-09-08-1637", {s.source_id for s in eligible})
        row = next(e for e in excluded if e["source_id"] == "GOV-2024-09-08-1637")
        self.assertIn("url_slug_or_id_is_not_publication_time", row["advisories"])

    def test_firewall_1645_admits_1637(self):
        as_of = ict(2024, 9, 8, 16, 45)
        eligible, _ = filter_sources(all_catalog(), as_of, ReplayMode.REPORTED_DATELINE_REPLAY)
        self.assertIn("GOV-2024-09-08-1637", {s.source_id for s in eligible})

    def test_pipeline_1630_insufficient_and_excludes_gauges(self):
        with tempfile.TemporaryDirectory() as td:
            pipe = EvidenceTrailPipeline(sample_mode=True, persist_dir=Path(td) / "m", log_dir=Path(td) / "l")
            result = pipe.run(_req("2024-09-08T09:30:00Z"))
        self.assertEqual(result.verdict.value, "INSUFFICIENT_EVIDENCE")
        self.assertNotIn("GOV-2024-09-08-1637", result.eligible_source_ids)
        self.assertTrue(any(e["source_id"] == "GOV-2024-09-08-1637" for e in result.excluded))
        self.assertTrue(any("district" in m.lower() for m in result.missing_facts))

    def test_pipeline_1645_includes_1637_with_replay_caveat(self):
        with tempfile.TemporaryDirectory() as td:
            pipe = EvidenceTrailPipeline(sample_mode=True, persist_dir=Path(td) / "m", log_dir=Path(td) / "l")
            result = pipe.run(_req("2024-09-08T09:45:00Z"))
        self.assertIn("GOV-2024-09-08-1637", result.eligible_source_ids)
        self.assertTrue(any("edit history" in c.lower() for c in result.caveats))
        self.assertEqual(result.verdict.value, "WARN")
        self.assertIn("SIMULATED", result.rationale)
        cite_ids = [c.source_id for c in result.citations]
        self.assertIn("GOV-2024-09-08-1637", cite_ids)

    def test_strict_mode_abstains_even_at_1645(self):
        with tempfile.TemporaryDirectory() as td:
            pipe = EvidenceTrailPipeline(sample_mode=True, persist_dir=Path(td) / "m", log_dir=Path(td) / "l")
            result = pipe.run(_req("2024-09-08T09:45:00Z", mode="STRICT_AS_OF_2024"))
        self.assertEqual(result.verdict.value, "INSUFFICIENT_EVIDENCE")
        self.assertTrue(any("AUTHENTICATED_2024" in m or "first_availability" in m for m in result.missing_facts))

    def test_blind_mutation_earlier_publication_changes_1630(self):
        catalog = all_catalog()
        mutated = []
        for row in catalog:
            if row.source_id == "GOV-2024-09-08-1637":
                row.published_at_displayed_utc = ict(2024, 9, 8, 16, 20)
            mutated.append(row)
        with tempfile.TemporaryDirectory() as td:
            pipe = EvidenceTrailPipeline(
                sample_mode=True,
                persist_dir=Path(td) / "m",
                log_dir=Path(td) / "l",
                catalog_override=mutated,
            )
            result = pipe.run(_req("2024-09-08T09:30:00Z"))
        self.assertIn("GOV-2024-09-08-1637", result.eligible_source_ids)
        self.assertEqual(result.verdict.value, "WARN")
