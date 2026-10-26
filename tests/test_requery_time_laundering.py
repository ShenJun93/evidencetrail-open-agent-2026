"""Audit-grade adversarial tests for time-laundered SQL requery IDs.

These are offline/local unit fixtures, NOT real Zetaris or sponsor proofs.
The first query's excluded source IDs must remain immutable to a later agent.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from evidencetrail.agents.collector import EvidenceCollectorAgent
from evidencetrail.catalog import all_catalog, sha
from evidencetrail.models import (
    RecordKind, RunRequest, SponsorCall, SponsorOutcome, Verdict,
)
from evidencetrail.pipeline import EvidenceTrailPipeline
from evidencetrail.traces import JsonlTrace

FUTURE_ID = "GOV-2024-09-08-1637"


def request_at(hour: int, minute: int, sample_mode: bool) -> RunRequest:
    from datetime import datetime, timezone
    asof = datetime(2024, 9, 8, hour - 7, minute, tzinfo=timezone.utc)
    return RunRequest.from_dict({
        "schema_version": "1", "as_of_utc": asof.isoformat(),
        "mode": "REPORTED_DATELINE_REPLAY",
        "mission_id": "yagi-yenbai-2024",
        "scenario_id": "yagi-replay-alpha",
        "province_2024": "yen bai", "district_2024": "luc yen",
        "granularity": "district", "question": "Research-only simulated watch",
        "sample_mode": sample_mode, "max_retries": 2,
    })


class SyntheticPriorSourceRequeryTests(unittest.TestCase):
    @staticmethod
    def sample_replay(fresh):
        with TemporaryDirectory() as td:
            pipe = EvidenceTrailPipeline(
                sample_mode=True,
                persist_dir=Path(td) / "memory", log_dir=Path(td) / "logs",
            )
            # Initial first FETCH includes the original FUTURE source, which
            # MUST remain excluded at 16:30 even if requery changes metadata.
            original = deepcopy(all_catalog())
            pipe.zetaris.fetch_two_logical_sources = lambda: (
                original,
                [SponsorCall("zetaris", "contract-fixture", SponsorOutcome.SAMPLE_CACHE,
                             "fixture only")],
            )
            pipe.zetaris.fetch_targeted_sources = lambda: (
                fresh,
                SponsorCall("zetaris", "targeted-unit", SponsorOutcome.UNIT_CONTRACT_ONLY,
                            "fake SQL response, not a sponsor receipt"),
            )
            result = pipe.run(request_at(16, 30, True))
            trace = (Path(td) / "logs" / f"trace-{result.request.run_id}.jsonl").read_text()
        return result, trace

    def test_requery_cannot_backdate_a_previously_excluded_future_id(self):
        future = deepcopy(next(s for s in all_catalog() if s.source_id == FUTURE_ID))
        future.published_at_displayed_utc -= timedelta(hours=1)
        result, trace = self.sample_replay([future])
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertNotIn(FUTURE_ID, result.eligible_source_ids)
        self.assertTrue(any(x["source_id"] == FUTURE_ID for x in result.excluded))
        self.assertIn("duplicate_prior_catalog_ids", trace)
        self.assertIn("no_new_admissible_evidence", trace)

    def test_requery_cannot_replace_excluded_id_with_changed_hash(self):
        future = deepcopy(next(s for s in all_catalog() if s.source_id == FUTURE_ID))
        future.published_at_displayed_utc -= timedelta(hours=1)
        future.excerpt = "Tampered article falsely claims it was available at 15:00."
        future.excerpt_sha256 = sha(future.excerpt)
        result, trace = self.sample_replay([future])
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertNotIn(FUTURE_ID, result.eligible_source_ids)
        self.assertIn("conflicting_source_versions", trace)
        self.assertIn(FUTURE_ID, trace)


    def test_requery_cannot_alias_excluded_article_with_new_source_id(self):
        future = deepcopy(next(s for s in all_catalog() if s.source_id == FUTURE_ID))
        future.source_id = "GOV-UNIT-ALIAS-OF-FUTURE"
        future.published_at_displayed_utc -= timedelta(hours=1)
        result, trace = self.sample_replay([future])
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertNotIn(future.source_id, result.eligible_source_ids)
        self.assertIn("aliased_prior_sources", trace)
        self.assertIn(future.source_id, trace)

    def test_requery_cannot_rebrand_same_excerpt_with_new_url(self):
        future = deepcopy(next(s for s in all_catalog() if s.source_id == FUTURE_ID))
        future.source_id = "GOV-UNIT-DUPLICATE-EXCERPT"
        future.locator = "https://example.invalid/different-address"
        future.published_at_displayed_utc -= timedelta(hours=1)
        result, trace = self.sample_replay([future])
        self.assertNotIn(future.source_id, result.eligible_source_ids)
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("aliased_prior_sources", trace)


class LiveSponsorCompletenessGateTests(unittest.TestCase):
    @staticmethod
    def fake_collector(rows, receipts, sample_mode=False):
        class NoHistory:
            def query(self, question):
                return {"hits": [], "disclaimer": "mock"}
        zeta = SimpleNamespace(
            sample_mode=sample_mode,
            fetch_two_logical_sources=lambda: (rows, receipts),
        )
        return zeta, NoHistory()

    @staticmethod
    def receipt(label, outcome):
        return SponsorCall("zetaris", f"query:{label}", outcome, "UNIT FIXTURE")

    def test_one_of_two_live_sources_failed_drops_every_row(self):
        rows = deepcopy(all_catalog())
        calls = [
            self.receipt("government-news", SponsorOutcome.REAL_SUCCESS),
            self.receipt("synthetic-capacity", SponsorOutcome.NOT_CONFIGURED),
        ]
        with TemporaryDirectory() as td:
            zeta, hmem = self.fake_collector(rows, calls)
            collector = EvidenceCollectorAgent(
                zeta, hmem, JsonlTrace(Path(td) / "trace.jsonl", "partial-live")
            )
            state = collector.run(request_at(16, 45, False))
            trace = (Path(td) / "trace.jsonl").read_text()
        self.assertFalse(state["data_ready"])
        self.assertEqual(state["eligible"], [])
        self.assertEqual(state["catalog_ids"], [])
        self.assertIn("incomplete_live_source_set_rejected", trace)

    def test_both_live_sources_succeed_keeps_firewall_working(self):
        rows = deepcopy(all_catalog())
        calls = [
            self.receipt("government-news", SponsorOutcome.REAL_SUCCESS),
            self.receipt("synthetic-capacity", SponsorOutcome.REAL_SUCCESS),
        ]
        with TemporaryDirectory() as td:
            zeta, hmem = self.fake_collector(rows, calls)
            collector = EvidenceCollectorAgent(
                zeta, hmem, JsonlTrace(Path(td) / "trace.jsonl", "two-sources")
            )
            state = collector.run(request_at(16, 45, False))
        self.assertTrue(state["data_ready"])
        self.assertIn(FUTURE_ID, state["catalog_ids"])
        self.assertIn(FUTURE_ID, [s.source_id for s in state["eligible"]])

    def test_partial_live_source_set_does_not_allow_requery_recovery(self):
        rows = deepcopy(all_catalog())
        calls = [
            self.receipt("government-news", SponsorOutcome.REAL_SUCCESS),
            self.receipt("synthetic-capacity", SponsorOutcome.UNAVAILABLE),
        ]
        attempted = []
        with TemporaryDirectory() as td:
            zeta, hmem = self.fake_collector(rows, calls)
            zeta.fetch_targeted_sources = lambda: attempted.append("called")
            collector = EvidenceCollectorAgent(
                zeta, hmem, JsonlTrace(Path(td) / "trace.jsonl", "partial-requery")
            )
            state = collector.run(request_at(16, 30, False))
            result = collector.requery(
                request_at(16, 30, False), state,
                ["requery_public_sources_for_named_district_at_as_of"],
            )
            trace = (Path(td) / "trace.jsonl").read_text()
        self.assertFalse(result)
        self.assertEqual(attempted, [])
        self.assertIn("initial_two_source_contract_not_met", trace)


    def test_fake_two_successes_for_same_table_do_not_complete_live_contract(self):
        rows = deepcopy(all_catalog())
        calls = [
            self.receipt("government-news", SponsorOutcome.REAL_SUCCESS),
            self.receipt("government-news", SponsorOutcome.REAL_SUCCESS),
        ]
        with TemporaryDirectory() as td:
            zeta, hmem = self.fake_collector(rows, calls)
            collector = EvidenceCollectorAgent(
                zeta, hmem, JsonlTrace(Path(td) / "trace.jsonl", "replayed-query")
            )
            state = collector.run(request_at(16, 45, False))
        self.assertFalse(state["data_ready"])
        self.assertEqual(state["eligible"], [])

    def test_source_receipts_cannot_replace_missing_capacity_rows(self):
        public_only = [
            r for r in deepcopy(all_catalog())
            if r.record_kind == RecordKind.GOVERNMENT_NEWS
        ]
        calls = [
            self.receipt("government-news", SponsorOutcome.REAL_SUCCESS),
            self.receipt("synthetic-capacity", SponsorOutcome.REAL_SUCCESS),
        ]
        with TemporaryDirectory() as td:
            zeta, hmem = self.fake_collector(public_only, calls)
            collector = EvidenceCollectorAgent(
                zeta, hmem, JsonlTrace(Path(td) / "trace.jsonl", "missing-capacity")
            )
            state = collector.run(request_at(16, 45, False))
        self.assertFalse(state["data_ready"])
        self.assertEqual(state["eligible"], [])

    def test_nonreal_targeted_receipt_cannot_admit_invented_row(self):
        rows = deepcopy(all_catalog())
        extra = replace(
            next(s for s in rows if s.source_id == FUTURE_ID),
            source_id="GOV-UNIT-NEVER-AUTHENTICATED",
        )
        calls = [
            self.receipt("government-news", SponsorOutcome.REAL_SUCCESS),
            self.receipt("synthetic-capacity", SponsorOutcome.REAL_SUCCESS),
        ]
        with TemporaryDirectory() as td:
            zeta, hmem = self.fake_collector(rows, calls)
            zeta.fetch_targeted_sources = lambda: (
                [extra],
                SponsorCall("zetaris", "targeted-unit", SponsorOutcome.UNIT_CONTRACT_ONLY,
                            "non-real unit-only SQL"),
            )
            collector = EvidenceCollectorAgent(
                zeta, hmem, JsonlTrace(Path(td) / "trace.jsonl", "targeted-invalid")
            )
            state = collector.run(request_at(16, 45, False))
            prior_len = len(state["eligible"])
            outcome = collector.requery(
                request_at(16, 45, False), state,
                ["requery_public_sources_for_named_district_at_as_of"],
            )
            trace = (Path(td) / "trace.jsonl").read_text()
        self.assertFalse(outcome)
        self.assertEqual(len(state["eligible"]), prior_len)
        self.assertNotIn(extra.source_id, [s.source_id for s in state["eligible"]])
        self.assertIn("targeted_transport_not_verified", trace)


if __name__ == "__main__":
    unittest.main()
