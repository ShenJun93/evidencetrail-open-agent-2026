from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evidencetrail.catalog import all_catalog
from evidencetrail.citation import CitationVerifier
from evidencetrail.hmem_port import HMEM
from evidencetrail.models import Citation, ReplayMode, RunRequest, Verdict
from evidencetrail.pipeline import EvidenceTrailPipeline


class CitationVerifierTests(unittest.TestCase):
    def test_rejects_invented_source_id(self):
        eligible = all_catalog()[:2]
        verifier = CitationVerifier()
        fake = Citation(source_id="GOV-INVENTED", excerpt_sha256="abc", claim="nope")
        ok, blocked = verifier.verify([fake], eligible, [eligible[0].source_id])
        self.assertEqual(ok, [])
        self.assertTrue(any("citation_not_in_eligible_set" in b for b in blocked))

    def test_rejects_hash_mismatch(self):
        src = all_catalog()[1]
        verifier = CitationVerifier()
        bad = Citation(source_id=src.source_id, excerpt_sha256="deadbeef", claim="x")
        ok, blocked = verifier.verify([bad], [src], [src.source_id])
        self.assertEqual(ok, [])
        self.assertTrue(any("excerpt_hash_mismatch" in b for b in blocked))


class HmemIsolationTests(unittest.TestCase):
    def test_persist_across_processes(self):
        with tempfile.TemporaryDirectory() as td:
            a = HMEM(persist_dir=td)
            rec = a.add("triage decided for luc yen", source="test", mission_id="m1", tags=["source:GOV-2024-09-08-1530"])
            mid = rec["id"]
            b = HMEM(persist_dir=td)
            self.assertIn(mid, b.records)
            self.assertEqual(b.records[mid]["content"], rec["content"])
            self.assertGreaterEqual(len(b.ledger.entries), 1)

    def test_future_memory_poisoning_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            persist = Path(td) / "h"
            logs = Path(td) / "l"
            pipe = EvidenceTrailPipeline(sample_mode=True, persist_dir=persist, log_dir=logs)
            later = RunRequest.from_dict(
                {
                    "schema_version": "1",
                    "mission_id": "yagi-yenbai-2024",
                    "scenario_id": "yagi-replay-alpha",
                    "as_of_utc": "2024-09-08T09:30:00Z",
                    "mode": "REPORTED_DATELINE_REPLAY",
                    "province_2024": "yen bai",
                    "district_2024": "luc yen",
                    "question": "later",
                    "sample_mode": True,
                }
            )
            pipe.run(later)
            pipe.hmem.add_decision(
                content="future bulletin 16:21 should leak into 15:00",
                source="poison",
                mission_id="yagi-yenbai-2024",
                run_id="poison-run",
                tags=["prior_decision_as_of:2024-09-08T09:30:00Z", "source:GOV-2024-09-08-1621"],
            )
            earlier = RunRequest.from_dict(
                {
                    "schema_version": "1",
                    "mission_id": "yagi-yenbai-2024",
                    "scenario_id": "yagi-replay-alpha",
                    "as_of_utc": "2024-09-08T08:00:00Z",
                    "mode": "REPORTED_DATELINE_REPLAY",
                    "province_2024": "yen bai",
                    "district_2024": "luc yen",
                    "question": "earlier",
                    "sample_mode": True,
                }
            )
            result = pipe.run(earlier)
            self.assertNotIn("GOV-2024-09-08-1621", result.eligible_source_ids)
            self.assertNotIn("GOV-2024-09-08-1637", result.eligible_source_ids)
            self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)

    def test_wrong_mission_memory_not_trusted(self):
        from evidencetrail.firewall import filter_memories
        from evidencetrail.catalog import ict
        from datetime import timezone
        from datetime import datetime

        memories = [
            {"id": "mem-x", "missionId": "other-mission", "tags": ["source:GOV-2024-09-08-1530"]},
            {"id": "mem-y", "missionId": None, "tags": ["source:GOV-2024-09-08-1530"]},
        ]
        kept, dropped = filter_memories(
            memories,
            "yagi-yenbai-2024",
            datetime(2024, 9, 8, 9, 30, tzinfo=timezone.utc),
            {"GOV-2024-09-08-1530"},
        )
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 2)
        self.assertTrue(all("cross_mission" in d["reasons"] for d in dropped))


class NoHardcodeTests(unittest.TestCase):
    def test_three_clocks_are_not_identical_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            pipe = EvidenceTrailPipeline(sample_mode=True, persist_dir=Path(td) / "m", log_dir=Path(td) / "l")
            r1500 = pipe.run(
                RunRequest.from_dict(
                    {
                        "schema_version": "1",
                        "mission_id": "yagi-yenbai-2024",
                        "scenario_id": "yagi-replay-alpha",
                        "as_of_utc": "2024-09-08T08:00:00Z",
                        "mode": "REPORTED_DATELINE_REPLAY",
                        "province_2024": "yen bai",
                        "district_2024": "luc yen",
                        "question": "q",
                        "sample_mode": True,
                    }
                )
            )
            r1630 = pipe.run(
                RunRequest.from_dict(
                    {
                        "schema_version": "1",
                        "mission_id": "yagi-yenbai-2024",
                        "scenario_id": "yagi-replay-alpha",
                        "as_of_utc": "2024-09-08T09:30:00Z",
                        "mode": "REPORTED_DATELINE_REPLAY",
                        "province_2024": "yen bai",
                        "district_2024": "luc yen",
                        "question": "q",
                        "sample_mode": True,
                    }
                )
            )
            r1645 = pipe.run(
                RunRequest.from_dict(
                    {
                        "schema_version": "1",
                        "mission_id": "yagi-yenbai-2024",
                        "scenario_id": "yagi-replay-alpha",
                        "as_of_utc": "2024-09-08T09:45:00Z",
                        "mode": "REPORTED_DATELINE_REPLAY",
                        "province_2024": "yen bai",
                        "district_2024": "luc yen",
                        "question": "q",
                        "sample_mode": True,
                    }
                )
            )
        self.assertNotEqual(set(r1500.eligible_source_ids), set(r1630.eligible_source_ids))
        self.assertNotEqual(set(r1630.eligible_source_ids), set(r1645.eligible_source_ids))
        self.assertNotEqual(r1630.verdict, r1645.verdict)
