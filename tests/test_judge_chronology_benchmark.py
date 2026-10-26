"""Cold-judge regression of user-visible historical reasoning policy.

Explicit policy gold labels come from run_judge_chronology_stress_benchmark.py;
the full sample-only EvidenceTrail agent pipeline has to agree. The unsafe
baseline is our own intentionally invalid input; no external field accuracy.
"""
from __future__ import annotations

import json
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from urllib.request import urlopen

from evidencetrail.api import create_local_server
from evidencetrail.catalog import all_catalog
from evidencetrail.firewall import availability_reason, jurisdiction_ok
from evidencetrail.models import ProvenanceQuality, RecordKind, ReplayMode
from run_judge_chronology_stress_benchmark import (
    ABSTAIN, TARGET, WARN, evaluate, run_benchmark, test_matrix,
)


def source(sid=TARGET):
    return next(s for s in all_catalog() if s.source_id == sid)


UTC_1645 = datetime(2024, 9, 8, 9, 45, tzinfo=timezone.utc)


class TypedProvenanceSecurityTests(unittest.TestCase):
    def test_imported_2026_portal_cannot_impersonate_2024_government_source(self):
        page = replace(
            source(), provenance_quality=
            ProvenanceQuality.IMPORTED_2024_DATELINE_ON_2026_PORTAL,
        )
        self.assertEqual(
            availability_reason(page, UTC_1645, ReplayMode.REPORTED_DATELINE_REPLAY),
            "PUBLIC_NEWS_ORIGIN_LABEL_CONFLICT_REJECTED",
        )

    def test_fake_synthetic_provenance_cannot_be_retyped_as_government(self):
        page = replace(source(), provenance_quality=ProvenanceQuality.SYNTHETIC)
        self.assertEqual(
            availability_reason(page, UTC_1645, ReplayMode.REPORTED_DATELINE_REPLAY),
            "PUBLIC_NEWS_ORIGIN_LABEL_CONFLICT_REJECTED",
        )

    def test_synthetic_plan_must_be_accurately_declared_fictional(self):
        cap = source("SYN-CAP-YAGI-ALPHA-LUCYEN")
        self.assertEqual(cap.record_kind, RecordKind.SYNTHETIC_CAPACITY)
        pretender = replace(
            cap, provenance_quality=ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT,
        )
        self.assertEqual(
            availability_reason(
                pretender, UTC_1645, ReplayMode.REPORTED_DATELINE_REPLAY
            ),
            "SYNTHETIC_CAPACITY_ORIGIN_LABEL_CONFLICT_REJECTED",
        )

    def test_mislocated_province_cannot_be_approved_by_inconsistent_district(self):
        bad = replace(source(), spatial_scope=["lao cai"])
        self.assertIn("luc yen", bad.named_districts_2024)
        self.assertFalse(jurisdiction_ok(bad, "yen bai", "luc yen"))
        self.assertTrue(jurisdiction_ok(source(), "yen bai", "luc yen"))

    def test_real_fixture_still_permits_legitimate_synthetic_capacity(self):
        cap = source("SYN-CAP-YAGI-ALPHA-LUCYEN")
        self.assertIsNone(
            availability_reason(cap, UTC_1645, ReplayMode.REPORTED_DATELINE_REPLAY)
        )


class ChronologyStressEvidenceTests(unittest.TestCase):
    def test_matrix_is_fixed_has_20_distinct_gold_labels(self):
        matrix = test_matrix()
        self.assertEqual(len(matrix), 20)
        self.assertEqual(len({c.name for c in matrix}), 20)
        self.assertTrue(all(c.gold_verdict in {ABSTAIN, WARN} for c in matrix))
        self.assertTrue(any(c.mode == "STRICT_AS_OF_2024" for c in matrix))

    def test_all_20_cases_run_same_agent_pipeline_to_golden_contract(self):
        result = run_benchmark()
        self.assertEqual(result["cases_total"], 20)
        self.assertEqual(result["cases_failed"], 0)
        self.assertEqual(result["cases_passed"], 20)
        self.assertTrue(result["all_cases_pass"])
        self.assertFalse(result["meterless_or_zetaris_network_called"])
        self.assertFalse(result["direct_NVIDIA_Nemotron_called"])
        self.assertFalse(result["benchmark_is_real_operational_accuracy"])
        self.assertEqual(
            result["own_unsafe_negative_control"][
                "actual_verdict_from_invalid_input"
            ], WARN,
        )
        self.assertFalse(result["own_unsafe_negative_control"][
            "independent_external_system_evaluated"
        ])

    def test_five_pre_hardening_metadata_attacks_now_fail_closed(self):
        cases = test_matrix()
        vulnerable = [c for c in cases if c.name.startswith((
            "13_", "14_", "15_", "16_", "17_"
        ))]
        self.assertEqual(len(vulnerable), 5)
        for c in vulnerable:
            with self.subTest(case=c.name):
                outcome = evaluate(c)
                self.assertTrue(outcome["passed"])
                self.assertEqual(outcome["actual_agent_verdict"], ABSTAIN)

    def test_negative_control_shows_exact_1500_vs_1637_trap(self):
        actual = [c for c in test_matrix() if c.name.startswith("08_")][0]
        self.assertEqual(evaluate(actual)["actual_agent_verdict"], ABSTAIN)
        self.assertFalse(evaluate(actual)["forbidden_admitted_source_ids"])


class BenchmarkActualLocalHttpTests(unittest.TestCase):
    def test_get_benchmark_is_real_local_sample_cpu_request(self):
        server = create_local_server("127.0.0.1", 0)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with urlopen(
                "http://127.0.0.1:" + str(server.server_port) + "/benchmark",
                timeout=9,
            ) as res:
                self.assertEqual(res.status, 200)
                info = json.loads(res.read(65_536).decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=3)
        self.assertEqual(info["kind"],
                         "OFFLINE_ADVERSARIAL_CHRONOLOGY_BENCHMARK_V1")
        self.assertEqual(info["cases_passed"], 20)
        self.assertEqual(info["cases_failed"], 0)
        self.assertEqual(len(info["cases"]), 20)
        self.assertFalse(info["lives_saved_or_deployment_claim"])


if __name__ == "__main__":
    unittest.main()
