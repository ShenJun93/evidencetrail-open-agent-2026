"""Initial source identity conflicts must fail closed before decision and audit."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from evidencetrail.catalog import all_catalog
from evidencetrail.models import RunRequest, SponsorOutcome, Verdict
from evidencetrail.pipeline import EvidenceTrailPipeline

TARGET = "GOV-2024-09-08-1637"
CAPACITY = "SYN-CAP-YAGI-ALPHA-LUCYEN"


def replay(rows, clock: str):
    payload = json.loads(
        Path(f"samples/inputs/yagi_{clock}_lucyen.json").read_text(encoding="utf-8")
    )
    request = RunRequest.from_dict(payload)
    with tempfile.TemporaryDirectory(prefix="evidencetrail-duplicate-id-") as tmp:
        root = Path(tmp)
        pipeline = EvidenceTrailPipeline(
            sample_mode=True, catalog_override=rows,
            persist_dir=root / "mem", log_dir=root / "logs",
        )
        result = pipeline.run(request)
        traces = list((root / "logs").glob("trace-*.jsonl"))
        events = [json.loads(s) for t in traces for s in t.read_text(encoding="utf-8").splitlines()]
    return result, events


class InitialSourceIdentityGateTests(unittest.TestCase):
    def test_previously_fail_open_backdated_duplicate_article_now_abstains(self):
        rows = all_catalog()
        article = next(r for r in rows if r.source_id == TARGET)
        rows.insert(0, replace(article, published_at_displayed_utc=article.observed_at_utc))
        result, events = replay(rows, "1630")
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.eligible_source_ids, [])
        self.assertTrue(any("duplicate_initial_source_ids" in json.dumps(e) for e in events))
        self.assertFalse(any(
            c.outcome == SponsorOutcome.REAL_SUCCESS for c in result.sponsor_calls
        ))

    def test_conflicting_duplicate_capacity_also_blocks_simulated_warn(self):
        rows = all_catalog()
        cap = next(r for r in rows if r.source_id == CAPACITY)
        predicates = dict(cap.plan_predicates)
        predicates["coordinator_watch_authorized"] = False
        rows.insert(0, replace(cap, plan_predicates=predicates))
        result, _ = replay(rows, "1645")
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.eligible_source_ids, [])

    def test_unambiguous_normal_data_still_produces_simulated_watch(self):
        result, _ = replay(all_catalog(), "1645")
        self.assertEqual(result.verdict, Verdict.WARN)
        self.assertIn(TARGET, result.eligible_source_ids)
        self.assertIn(CAPACITY, result.eligible_source_ids)


if __name__ == "__main__":
    unittest.main()
