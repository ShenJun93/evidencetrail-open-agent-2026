"""Adversarial product regressions; injected models and fictional sources only."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evidencetrail.adapters.meterless import MeterlessRuntimeProvider
from evidencetrail.agents.auditor import EvidenceAuditorAgent
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.catalog import all_catalog
from evidencetrail.claim_ledger import evaluate_claim_ledger
from evidencetrail.firewall import filter_sources
from evidencetrail.models import ReplayMode, Verdict
from evidencetrail.reducer import decide
from evidencetrail.traces import JsonlTrace
from evidencetrail.why_counterfactual import explain_why
from tests.test_claim_ledger_transfer import curated_milton, fresh_issuer_source
from tests.test_live_source_and_agent_contract import request_at


class ModelExplanationBoundaryTests(unittest.TestCase):
    def run_proposal(self, ids, *, default_route=False, verdict="WARN"):
        malicious = "Original 2024 bytes authenticated. Evacuate 9000 people now."

        def transport(url, method, headers, body, timeout):
            if url.endswith("/models"):
                return 200, {}, b'{"data":[{"id":"meterless/auto"}]}'
            return 200, {}, json.dumps({
                "id": "unit-only-untrusted-explanation",
                "meterless": {"routed_model": "local/unit-only"},
                "choices": [{"message": {"content": json.dumps({
                    "proposed_verdict": verdict, "source_ids": ids,
                    "rationale": malicious,
                })}}],
            }).encode()

        request = request_at(16, 45, sample_mode=False)
        eligible, _ = filter_sources(all_catalog(), request.as_of_utc, request.mode)
        expected = decide(request, eligible)
        provider = MeterlessRuntimeProvider(token="unit-only", transport=transport)
        with tempfile.TemporaryDirectory() as tmp:
            trace = JsonlTrace(Path(tmp) / "trace.jsonl", "audit-unit")
            agent = DecisionAgent(trace, provider=None if default_route else provider)
            with patch("evidencetrail.agents.decision.MeterlessRuntimeProvider",
                       return_value=provider):
                draft = agent.run(request, eligible)
            audit = EvidenceAuditorAgent(trace).run(
                request, eligible, draft, [r.source_id for r in eligible])
        return draft, audit, expected, malicious

    def test_matching_verdict_cannot_launder_model_prose_or_drop_rule_citations(self):
        for default in (False, True):
            with self.subTest(default_route=default):
                draft, audit, expected, malicious = self.run_proposal(
                    ["GOV-2024-09-08-1637"], default_route=default)
                self.assertEqual(draft.nominated_verdict, Verdict.WARN)
                self.assertNotIn(malicious, draft.rationale)
                self.assertIn(expected[1], draft.rationale)
                self.assertEqual(draft.used_source_ids, expected[3])
                self.assertEqual([c.source_id for c in draft.citations], expected[3])
                self.assertTrue(audit.accepted)

    def test_empty_model_citations_cannot_erase_actual_evidence(self):
        draft, audit, expected, _ = self.run_proposal([])
        self.assertEqual(draft.used_source_ids, expected[3])
        self.assertTrue(draft.citations)
        self.assertTrue(audit.accepted)

    def test_model_veto_clears_positive_claim_attribution(self):
        draft, _, _, _ = self.run_proposal([], verdict="INSUFFICIENT_EVIDENCE")
        self.assertEqual(draft.nominated_verdict, Verdict.INSUFFICIENT_EVIDENCE)
        self.assertEqual(draft.used_source_ids, [])
        self.assertEqual(draft.citations, [])


def lab(source_id, value, clock="2024-10-07T08:00:00Z"):
    row, pin, rule = fresh_issuer_source(source_id=source_id, clock=clock)
    excerpt = f"FICTIONAL TEST {source_id} reports {value} arbitrary units"
    row.excerpt = row.paraphrase = excerpt
    row.excerpt_sha256 = sha256(excerpt.encode()).hexdigest()
    row.observation_fields["reading"] = value
    return row, replace(pin, excerpt_sha256=row.excerpt_sha256,
                        expected_value=value), rule


class ConflictingClaimTests(unittest.TestCase):
    def corpus(self, *, clock="2024-10-07T08:00:00Z", same_value=False):
        a, pa, rule = lab("LAB-A", 7)
        b, pb, _ = lab("LAB-Z", 7 if same_value else 99, clock)
        return [a, b], {a.source_id: pa, b.source_id: pb}, [rule]

    def test_same_clock_conflict_abstains_instead_of_selecting_lexical_maximum(self):
        rows, pins, rules = self.corpus()
        result = evaluate_claim_ledger(rows, pins, rules,
                                       as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(result["typed_claims"], [])
        self.assertEqual(result["status"], "ABSTAIN_CONFLICTING_CLAIMS")
        self.assertEqual(result["unresolved_claim_conflicts"][0]["source_ids"],
                         ["LAB-A", "LAB-Z"])
        self.assertIn("conflict", result["trusted_template_explanation"].lower())
        reverse = evaluate_claim_ledger(list(reversed(rows)), pins, rules,
                                        as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(result, reverse)

    def test_latest_conflict_does_not_silently_fall_back_to_older_value(self):
        rows, pins, rules = self.corpus()
        older, p, _ = lab("LAB-OLD", 3, "2024-10-07T07:00:00Z")
        rows.append(older); pins[older.source_id] = p
        result = evaluate_claim_ledger(rows, pins, rules,
                                       as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(result["typed_claims"], [])

    def test_equal_value_ties_remain_usable_without_claiming_corroboration(self):
        rows, pins, rules = self.corpus(same_value=True)
        result = evaluate_claim_ledger(rows, pins, rules,
                                       as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(result["typed_claims"][0]["value"], 7)
        self.assertEqual(result["unresolved_claim_conflicts"], [])
        self.assertTrue(result["issuer_family_count_is_not_independent_corroboration_proof"])

    def test_conflict_is_scoped_to_latest_admissible_policy_clock(self):
        rows, pins, rules = self.corpus()
        later, p, _ = lab("LAB-LATER", 10, "2024-10-07T10:00:00Z")
        rows.append(later); pins[later.source_id] = p
        before = evaluate_claim_ledger(rows, pins, rules,
                                       as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(before["typed_claims"], [])
        after = evaluate_claim_ledger(rows, pins, rules,
                                      as_of_utc="2024-10-07T10:00:00Z")
        self.assertEqual(after["typed_claims"][0]["value"], 10)

    def test_date_only_conflict_cannot_invent_within_day_revision_order(self):
        rows, pins, rules = self.corpus()
        for row in rows:
            row.issued_at_claimed_utc = row.published_at_displayed_utc = None
            row.observation_fields["displayed_date_local"] = "2024-10-06"
            pins[row.source_id] = replace(
                pins[row.source_id], claimed_issue_utc=None,
                displayed_local_day="2024-10-06", local_utc_offset_minutes=-240,
                curator_not_before_utc="2024-10-07T04:00:00Z")
        result = evaluate_claim_ledger(rows, pins, rules,
                                       as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(result["status"], "ABSTAIN_CONFLICTING_CLAIMS")
        self.assertEqual(result["typed_claims"], [])

    def test_conflict_does_not_hide_an_unrelated_admissible_claim(self):
        rows, pins, rules = self.corpus()
        row, pin, rule = lab("OTHER", 3)
        row.observation_fields["issuer_family"] = "OTHER_LAB"
        rule = replace(rule, key="OTHER_READING", issuer_family="OTHER_LAB")
        pin = replace(pin, claim_key=rule.key, issuer_family=rule.issuer_family)
        result = evaluate_claim_ledger(rows+[row], {**pins, row.source_id: pin},
                                       rules+[rule], as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(result["status"], "PARTIAL_CLAIMS_WITH_CONFLICTS")
        self.assertEqual([c["claim_key"] for c in result["typed_claims"]], [rule.key])

    def test_why_explains_conflict_and_exact_resolution_on_source_removal(self):
        rows, pins, rules = self.corpus()
        result = explain_why(rows, pins, rules, as_of_utc="2024-10-07T09:00:00Z")
        self.assertEqual(result["selected_claims"], {})
        self.assertEqual(result["rule_explanations"][0]["status"],
                         "ABSTAIN_CONFLICTING_LATEST_SOURCES")
        self.assertEqual(result["rule_explanations"][0]["source_removal_pivots"],
                         ["LAB-A", "LAB-Z"])
        self.assertEqual(result["evidence_needed"][0]["reason_code"],
                         "RESOLVE_CONFLICTING_LATEST_SOURCES")
        effects = {x["removed_source_id"]: x["changed_claims"][0]
                   for x in result["source_withdrawal_interventions"]}
        self.assertEqual(effects["LAB-Z"]["after"]["value"], 7)
        self.assertEqual(effects["LAB-A"]["after"]["value"], 99)
        self.assertTrue(all(x["effect"] == "CLAIM_APPEARS" for x in effects.values()))


class WhyProofBoundaryTests(unittest.TestCase):
    def test_live_cli_discloses_completed_sql_separately_from_model_calls(self):
        from run_why_source_counterfactual import main
        from run_zetaris_cross_issuer import import_rows
        nhc, florida = import_rows()
        for fail_second in (False, True):
            with self.subTest(fail_second=fail_second), tempfile.TemporaryDirectory() as td:
                receipt = Path(td) / "injected-cli-contract-not-vendor-proof.json"
                results = [(nhc, "unit-request-1", "unit-sql-1"),
                           ValueError("unit-failure") if fail_second else
                           (florida, "unit-request-2", "unit-sql-2")]
                with patch("run_why_source_counterfactual.read_local_env", return_value={
                    "ZETARIS_REST_URL": "http://127.0.0.1:8888/api/v1.0",
                    "ZETARIS_ORG_ID": "1", "ZETARIS_API_KEY": "unit-only",
                }), patch("run_why_source_counterfactual.query_sql_editor", side_effect=results):
                    code = main(["--live", "--approve-local-zetaris", "--receipt", str(receipt)])
                report = json.loads(receipt.read_text())
                self.assertEqual(code, 2 if fail_second else 0)
                self.assertTrue(report["model_or_sponsor_called"])
                self.assertFalse(report["model_called"])
                self.assertEqual(report["local_sql_queries_completed"], 1 if fail_second else 2)

    def test_strict_lists_missing_attestation_for_every_unanswered_rule(self):
        rows, pins, rules = curated_milton()
        result = explain_why(rows, pins, rules, as_of_utc="2024-10-07T11:00:00Z",
                             mode=ReplayMode.STRICT_AS_OF_2024)
        self.assertEqual(len(result["excluded_sources"]), 7)
        self.assertEqual(len(result["evidence_needed"]), 3)
        self.assertTrue(all(x["reason_code"] == "ORIGINAL_AVAILABILITY_ATTESTATION_REQUIRED"
                            for x in result["evidence_needed"]))

    def test_reported_mode_names_future_source_without_exposing_its_value(self):
        rows, pins, rules = curated_milton()
        result = explain_why(rows, pins, rules, as_of_utc="2024-10-07T11:00:00Z")
        need = next(x for x in result["evidence_needed"] if x["claim_key"] == "FL_PRESS")
        self.assertEqual(need["reason_code"], "NO_SOURCE_ADMISSIBLE_AT_AS_OF")
        self.assertEqual(need["source_ids"], ["FL-GOV-20241007-1100-ET"])
        self.assertNotIn("value", need)

    def test_policy_digest_binds_rules_and_all_pin_clocks(self):
        rows, pins, rules = self.corpus()
        args = {"as_of_utc": "2024-10-07T09:00:00Z"}
        original = explain_why(rows, pins, rules, **args)
        changed_rule = explain_why(rows, pins, [replace(rules[0], unit="other_units")], **args)
        changed_rows = [replace(rows[0], published_at_displayed_utc=rows[0].published_at_displayed_utc.replace(hour=6),
                                issued_at_claimed_utc=rows[0].issued_at_claimed_utc.replace(hour=6))]
        changed_pins = {rows[0].source_id: replace(pins[rows[0].source_id],
                                                claimed_issue_utc="2024-10-07T06:00:00Z")}
        changed_clock = explain_why(changed_rows, changed_pins, rules, **args)
        digests = {r["pinned_input_policy_sha256_not_a_signature"]
                   for r in (original, changed_rule, changed_clock)}
        self.assertEqual(len(digests), 3)

    def corpus(self):
        row, pin, rule = lab("LAB-A", 7)
        return [row], {row.source_id: pin}, [rule]


if __name__ == "__main__":
    unittest.main()
