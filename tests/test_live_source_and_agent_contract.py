"""Regression contracts, fake transports only. NOT live sponsor acceptance."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.meterless import MeterlessRuntimeProvider
from evidencetrail.adapters.zetaris import ZetarisAdapter
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.catalog import all_catalog
from evidencetrail.firewall import filter_memories
from evidencetrail.models import (
    RecordKind, RunRequest, SponsorCall, SponsorOutcome, Verdict,
)
from evidencetrail.pipeline import EvidenceTrailPipeline
from evidencetrail.traces import JsonlTrace


def request_at(hour: int, minute: int, sample_mode: bool = True) -> RunRequest:
    from datetime import datetime, timezone
    return RunRequest.from_dict({
        "schema_version": "1", "mission_id": "yagi-yenbai-2024",
        "scenario_id": "yagi-replay-alpha",
        "as_of_utc": datetime(2024, 9, 8, hour - 7, minute, tzinfo=timezone.utc).isoformat(),
        "mode": "REPORTED_DATELINE_REPLAY",
        "province_2024": "yen bai", "district_2024": "luc yen",
        "question": "simulated coordinator watch?", "sample_mode": sample_mode,
        "max_retries": 2,
    })


class ZetarisTruthTests(unittest.TestCase):
    def test_unconfigured_live_queries_cannot_fallback_to_cache(self):
        with patch.dict(os.environ, {
            "ZETARIS_REST_URL": "http://127.0.0.1:8888/api/v1.0",
            "ZETARIS_PUBLIC_SQL": "", "ZETARIS_CAPACITY_SQL": "",
        }):
            adapter = ZetarisAdapter(sample_mode=False)
            rows, calls = adapter.fetch_two_logical_sources()
        self.assertEqual(rows, [])
        self.assertFalse(any(c.outcome == SponsorOutcome.REAL_SUCCESS for c in calls))
        self.assertTrue(any(c.outcome == SponsorOutcome.NOT_CONFIGURED for c in calls))

    def test_source_row_decoding_requires_real_rows_and_hash(self):
        source = next(s for s in all_catalog() if s.record_kind == RecordKind.GOVERNMENT_NEWS)
        payload = json.dumps({"rows": [source.to_public_dict()]}).encode("utf-8")
        result = ZetarisAdapter._decode_rows(payload, RecordKind.GOVERNMENT_NEWS)
        self.assertEqual(result[0].source_id, source.source_id)
        self.assertEqual(result[0].excerpt_sha256, source.excerpt_sha256)
        self.assertIsNone(result[0].first_availability_proven_utc)

    def test_select_one_or_non_source_response_is_not_sponsor_success(self):
        with self.assertRaises(ValueError):
            ZetarisAdapter._decode_rows(
                json.dumps({"rows": [{"evidencetrail_probe": 1}]}).encode(),
                RecordKind.GOVERNMENT_NEWS,
            )
        self.assertFalse(ZetarisAdapter._read_only_select("SELECT 1"))
        self.assertFalse(ZetarisAdapter._read_only_select("DELETE FROM warnings"))
        self.assertFalse(ZetarisAdapter._read_only_select("SELECT * FROM warnings; DROP TABLE warnings"))
        self.assertTrue(ZetarisAdapter._read_only_select("SELECT * FROM warnings"))

    def test_sql_row_must_not_self_certify_2024_snapshot(self):
        source = next(s for s in all_catalog() if s.record_kind == RecordKind.GOVERNMENT_NEWS)
        row = source.to_public_dict()
        row["provenance_quality"] = "AUTHENTICATED_2024_SNAPSHOT"
        with self.assertRaises(ValueError):
            ZetarisAdapter._decode_rows(json.dumps({"data": [row]}).encode(), RecordKind.GOVERNMENT_NEWS)


    def test_official_zetaris_opensqlquery_request_shape(self):
        """Fake transport. Official REST guide uses select/pageLimit, not sql."""
        from unittest.mock import patch
        source = next(s for s in all_catalog() if s.record_kind == RecordKind.GOVERNMENT_NEWS)
        payload = json.dumps({"rows": [source.to_public_dict()]}).encode("utf-8")

        class DummyReply:
            status = 200
            headers = {}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, count):
                return payload[:count]

        with patch.dict(os.environ, {
            "ZETARIS_QUERY_URL": "http://127.0.0.1:8899/DBQuery/OpenSqlQuery",
        }):
            adapter = ZetarisAdapter(sample_mode=False)
            with patch(
                "evidencetrail.adapters.zetaris.urllib.request.urlopen",
                return_value=DummyReply(),
            ) as call:
                rows, receipt = adapter._query_rows(
                    "SELECT * FROM government_warnings", "government-news",
                    RecordKind.GOVERNMENT_NEWS,
                )
        self.assertEqual(len(rows), 1)
        request = call.call_args.args[0]
        sent = json.loads(request.data.decode("utf-8"))
        self.assertIn("select", sent)
        self.assertEqual(sent["pageLimit"], 100)
        self.assertNotIn("sql", sent)
        # This is a mocked API response; NOT a real sponsor call receipt.
        self.assertEqual(receipt.row_count, 1)


class MemoryScopeTests(unittest.TestCase):
    def test_same_mission_but_different_scenario_must_be_excluded(self):
        from datetime import datetime, timezone
        rec = {
            "id": "mem-9", "source": "evidencetrail.decision",
            "missionId": "yagi-yenbai-2024",
            "content": "simulated WARN as_of=2024-09-08T08:00:00Z",
            "tags": [
                "prior_decision_as_of:2024-09-08T08:00:00Z",
                "source:GOV-2024-09-08-1530", "scenario:other-scenario",
            ],
        }
        kept, dropped = filter_memories(
            [rec], "yagi-yenbai-2024",
            datetime(2024, 9, 8, 9, 30, tzinfo=timezone.utc),
            {"GOV-2024-09-08-1530"}, scenario_id="yagi-replay-alpha",
        )
        self.assertEqual(kept, [])
        self.assertIn("cross_scenario_or_untagged", dropped[0]["reasons"])

    def test_missing_prior_timestamp_and_untrusted_origin_fail_closed(self):
        from datetime import datetime, timezone
        rec = {"id": "mem-bad", "source": "external-prompt", "missionId": "m", "tags": []}
        kept, dropped = filter_memories(
            [rec], "m", datetime(2024, 9, 8, 9, 30, tzinfo=timezone.utc),
            set(), scenario_id="s",
        )
        self.assertEqual(kept, [])
        self.assertIn("missing_prior_as_of", dropped[0]["reasons"])
        self.assertIn("untrusted_memory_origin", dropped[0]["reasons"])


class RequeryContractTests(unittest.TestCase):
    def test_auditor_requery_must_add_a_distinct_admissible_source(self):
        catalog = all_catalog()
        added = next(s for s in catalog if s.source_id == "GOV-2024-09-08-1637")
        original = [s for s in catalog if s.source_id != added.source_id]
        with tempfile.TemporaryDirectory() as tmp:
            pipe = EvidenceTrailPipeline(
                sample_mode=True, persist_dir=Path(tmp) / "memory",
                log_dir=Path(tmp) / "logs",
            )
            pipe.zetaris.fetch_two_logical_sources = lambda: (
                original,
                [SponsorCall("zetaris", "contract-cache", SponsorOutcome.SAMPLE_CACHE, "unit fixture")],
            )
            pipe.zetaris.fetch_targeted_sources = lambda: (
                [added],
                [SponsorCall("zetaris", "targeted-fake", SponsorOutcome.UNIT_CONTRACT_ONLY, "unit fixture")][0],
            )
            result = pipe.run(request_at(16, 45))
            self.assertEqual(result.verdict, Verdict.WARN)
            self.assertIn(added.source_id, result.eligible_source_ids)
            self.assertTrue(any(h.from_agent == "EvidenceAuditorAgent"
                                and h.to_agent == "EvidenceCollectorAgent" for h in result.handoffs))
            trace = (Path(tmp) / "logs" / f"trace-{result.request.run_id}.jsonl").read_text()
            self.assertIn("zetaris_targeted_query", trace)
            self.assertIn("new_source_ids", trace)

    def test_no_new_source_cannot_be_logged_as_a_successful_requery(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipe = EvidenceTrailPipeline(
                sample_mode=True, persist_dir=Path(tmp) / "memory",
                log_dir=Path(tmp) / "logs",
            )
            result = pipe.run(request_at(16, 30))
            self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
            text = (Path(tmp) / "logs" / f"trace-{result.request.run_id}.jsonl").read_text()
            self.assertIn("no_new_admissible_evidence", text)


class ModelRouteContractTests(unittest.TestCase):
    @staticmethod
    def make_provider(source_ids: list[str], verdict: str) -> MeterlessRuntimeProvider:
        def fake_transport(url, method, headers, body, timeout):
            if url.endswith("/models"):
                return 200, {}, json.dumps({"data": [{"id": "meterless/auto"}]}).encode()
            return 200, {}, json.dumps({
                "id": "fake-model-receipt-NOT-LIVE",
                "choices": [{"message": {"content": json.dumps({
                    "proposed_verdict": verdict,
                    "rationale": "Synthetic watch rationale from UNIT fake transport",
                    "source_ids": source_ids,
                })}}],
            }).encode()
        return MeterlessRuntimeProvider(
            token="unit-only-local-test-token", transport=fake_transport,
        )

    def test_injected_provider_cannot_claim_live_nightshift(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = DecisionAgent(
                JsonlTrace(Path(tmp) / "run.jsonl", "unit-run"),
                provider=self.make_provider(["GOV-2024-09-08-1637"], "WARN"),
            )
            result = agent.run(request_at(16, 45, sample_mode=False), all_catalog())
        self.assertEqual(result.nominated_verdict, Verdict.WARN)
        self.assertEqual(result.model_route, "meterless/auto_injected_unit_transport")
        self.assertTrue(agent.sponsor_calls)
        self.assertEqual(agent.sponsor_calls[0].outcome, SponsorOutcome.UNIT_CONTRACT_ONLY)

    def test_fake_model_hallucinated_citation_triggers_abstain(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = DecisionAgent(
                JsonlTrace(Path(tmp) / "run.jsonl", "unit-hallucination"),
                provider=self.make_provider(["GOV-INVENTED"], "WARN"),
            )
            result = agent.run(request_at(16, 45, sample_mode=False), all_catalog())
        self.assertEqual(result.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("model_citation_not_in_eligible_source_set", result.missing_facts)
