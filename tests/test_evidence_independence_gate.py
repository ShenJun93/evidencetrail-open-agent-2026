"""Initial multi-source integrity is a product trust boundary, not an extra mock."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from evidencetrail.catalog import all_catalog
from evidencetrail.counterfactual import counterfactual_dossier
from evidencetrail.evidence_integrity import initial_source_integrity_issues
from evidencetrail.models import RunRequest, Verdict
from evidencetrail.pipeline import EvidenceTrailPipeline

PIVOT = "GOV-2024-09-08-1637"
CAP = "SYN-CAP-YAGI-ALPHA-LUCYEN"


def request(clock="1630"):
    raw = json.loads(Path(f"samples/inputs/yagi_{clock}_lucyen.json").read_text("utf8"))
    return RunRequest.from_dict(raw)


def replay(catalog, clock="1630"):
    with tempfile.TemporaryDirectory() as td:
        pipeline = EvidenceTrailPipeline(
            sample_mode=True, catalog_override=catalog,
            persist_dir=Path(td)/"mem", log_dir=Path(td)/"logs",
        )
        result = pipeline.run(request(clock))
        trace = "\n".join(p.read_text("utf8") for p in
                          (Path(td)/"logs").glob("trace-*.jsonl"))
        return result, trace


class IndependentSourceGateTests(unittest.TestCase):
    def test_canonical_replay_remains_one_decisive_watch_pair(self):
        catalog = all_catalog()
        self.assertEqual(initial_source_integrity_issues(catalog, request("1645")), [])
        result, _ = replay(catalog, "1645")
        self.assertEqual(result.verdict, Verdict.WARN)

    def test_fresh_id_same_original_locator_cannot_backdate_future_bulletin(self):
        catalog = all_catalog()
        article = next(r for r in catalog if r.source_id == PIVOT)
        clone = replace(article, source_id="FAKE-NEW-INDEPENDENT-ID",
                        published_at_displayed_utc=request().as_of_utc,
                        excerpt="mutated excerpt with earlier clock",
                        excerpt_sha256=hashlib.sha256(b"mutated excerpt with earlier clock").hexdigest())
        catalog.append(clone)
        issues = initial_source_integrity_issues(catalog, request())
        self.assertIn("SOURCE_LOCATOR_ALIAS_REFUSED", {x["code"] for x in issues})
        actual, trace = replay(catalog)
        self.assertEqual(actual.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertEqual(actual.eligible_source_ids, [])
        self.assertIn("SOURCE_LOCATOR_ALIAS_REFUSED", trace)
        with self.assertRaisesRegex(ValueError, "SOURCE_LOCATOR_ALIAS_REFUSED"):
            counterfactual_dossier(request(), catalog)

    def test_same_excerpt_new_locator_is_not_second_independent_witness(self):
        catalog = all_catalog()
        article = next(r for r in catalog if r.source_id == PIVOT)
        catalog.append(replace(
            article, source_id="FAKE-NEW-LOCATOR",
            locator="https://example.invalid/mirrored-article",
            published_at_displayed_utc=request().as_of_utc))
        issues = initial_source_integrity_issues(catalog, request())
        self.assertIn("SOURCE_EXCERPT_ALIAS_REFUSED", {x["code"] for x in issues})
        result, _ = replay(catalog)
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        with self.assertRaisesRegex(ValueError, "SOURCE_EXCERPT_ALIAS_REFUSED"):
            counterfactual_dossier(request(), catalog)

    def test_later_out_of_scope_source_alias_is_detected_before_filters(self):
        catalog = all_catalog()
        article = next(r for r in catalog if r.source_id == PIVOT)
        catalog.append(replace(
            article, source_id="FAKE-GEOGRAPHIC-TWIN",
            locator=article.locator,
            excerpt="changed claim", excerpt_sha256=hashlib.sha256(b"changed claim").hexdigest(),
            spatial_scope=["hanoi"], named_districts_2024=[],
        ))
        result, _ = replay(catalog, "1645")
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)

    def test_conflicting_same_scenario_capacity_fails_closed_both_orders(self):
        base = all_catalog()
        original = next(r for r in base if r.source_id == CAP)
        denied = dict(original.plan_predicates)
        denied["coordinator_watch_authorized"] = False
        alias = replace(original, source_id="SIM-SECOND-PLAN",
                        locator="evidencetrail://synthetic/second-plan",
                        excerpt="Different scenario plan, authorization denied",
                        excerpt_sha256=hashlib.sha256(b"Different scenario plan, authorization denied").hexdigest(),
                        plan_predicates=denied)
        for rows in (base+[alias], [alias]+base):
            with self.subTest(first=rows[0].source_id):
                issues = initial_source_integrity_issues(rows, request("1645"))
                self.assertIn("AMBIGUOUS_SCENARIO_CAPACITY_REFUSED",
                              {i["code"] for i in issues})
                result, _ = replay(rows, "1645")
                self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
                with self.assertRaisesRegex(ValueError, "AMBIGUOUS_SCENARIO_CAPACITY_REFUSED"):
                    counterfactual_dossier(request("1645"), rows)

    def test_separate_scenarios_do_not_conflict(self):
        base = all_catalog()
        original = next(r for r in base if r.source_id == CAP)
        other = replace(original, source_id="OTHER-SCENARIO-CAP",
                        scenario_id="unrelated-scenario",
                        locator="evidencetrail://synthetic/unrelated",
                        excerpt="Different scenario entirely",
                        excerpt_sha256=hashlib.sha256(b"Different scenario entirely").hexdigest())
        rows = base + [other]
        self.assertEqual(initial_source_integrity_issues(rows, request("1645")), [])
        result, _ = replay(rows, "1645")
        self.assertEqual(result.verdict, Verdict.WARN)

    def test_two_disjoint_district_plans_are_selected_by_scope_not_sql_order(self):
        base = all_catalog()
        original = next(r for r in base if r.source_id == CAP)
        bad = replace(
            original, source_id="AA-OTHER-DISTRICT-CAPACITY",
            named_districts_2024=["van yen"],
            locator="evidencetrail://synthetic/yagi-replay-alpha/van-yen",
            excerpt="Another district, watch not authorized",
            excerpt_sha256=hashlib.sha256(b"Another district, watch not authorized").hexdigest(),
            plan_predicates={**original.plan_predicates,
                             "coordinator_watch_authorized": False},
        )
        for rows in ([bad] + base, base + [bad]):
            with self.subTest(first=rows[0].source_id):
                self.assertEqual(initial_source_integrity_issues(rows, request("1645")), [])
                result, _ = replay(rows, "1645")
                self.assertEqual(result.verdict, Verdict.WARN)
                proof = counterfactual_dossier(request("1645"), rows)
                self.assertEqual(proof["current"]["rule_verdict"], "WARN")
                witness = {r["source_id"] for r in
                           proof["current"]["minimum_sufficient_source_set"]}
                self.assertIn(CAP, witness)
                self.assertNotIn("AA-OTHER-DISTRICT-CAPACITY", witness)

    def test_excerpts_must_match_their_claimed_sha256(self):
        base = all_catalog()
        pivot = next(x for x in base if x.source_id == PIVOT)
        tampered = [
            replace(x, excerpt="Adversarially altered government paragraph")
            if x.source_id == PIVOT else x for x in base
        ]
        self.assertEqual(
            initial_source_integrity_issues(tampered, request("1645"))[0]["code"],
            "SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED",
        )
        result, trace = replay(tampered, "1645")
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED", result.missing_facts)
        self.assertIn("SOURCE_INTEGRITY_REFUSED", result.rationale)
        self.assertIn("SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED", trace)
        with self.assertRaisesRegex(ValueError, "SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED"):
            counterfactual_dossier(request("1645"), tampered)

    def test_empty_locator_fails_closed_without_accidental_certification(self):
        rows = all_catalog()
        original = next(x for x in rows if x.source_id == PIVOT)
        rows = [replace(x, locator="") if x.source_id == PIVOT else x
                for x in rows]
        self.assertIn("SOURCE_IDENTITY_FIELD_INVALID_REFUSED",
                      {x["code"] for x in initial_source_integrity_issues(rows, request("1645"))})
        result, _ = replay(rows, "1645")
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("SOURCE_IDENTITY_FIELD_INVALID_REFUSED", result.missing_facts)

    def test_duplicate_ids_still_refused(self):
        base = all_catalog()
        pivot = next(x for x in base if x.source_id == PIVOT)
        result, trace = replay(base + [pivot], "1645")
        self.assertEqual(result.verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertIn("duplicate_initial_source_ids", trace)


if __name__ == "__main__":
    unittest.main()
