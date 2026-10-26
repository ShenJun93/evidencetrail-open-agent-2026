"""A falsifiable, offline comparison with OUR deliberately weak baseline.

NOT a test of GPT/Claude/other products, and NOT operational forecast accuracy.
Policy-gold labels are authored independently in the existing 20-case matrix.
The weak control deliberately skips publication-time and provenance filtering.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from evidencetrail.catalog import all_catalog
from evidencetrail.counterfactual import counterfactual_dossier
from evidencetrail.firewall import jurisdiction_ok
from evidencetrail.models import RecordKind, ReplayMode
from evidencetrail.reducer import decide
from run_judge_chronology_stress_benchmark import (
    ABSTAIN, WARN, request, run_benchmark, test_matrix,
)

DEFAULT_REPORT = Path("acceptance/logs/own-baseline-comparative-benchmark.json")


def weak_time_blind_control(case) -> str:
    """Deliberately INVALID baseline; cannot establish admissible evidence."""
    req = request(case.clock, case.mode)
    rows = case.mutate(copy.deepcopy(all_catalog()))
    # Same reducer; omit the crucial temporal firewall and source-origin gates.
    # Exclude known non-operational record TYPES (not their typed provenance).
    # A 16:37 article will now be mistakenly available at 16:30.
    purported = [
        row for row in rows
        if row.record_kind in (RecordKind.GOVERNMENT_NEWS, RecordKind.SYNTHETIC_CAPACITY)
        and jurisdiction_ok(row, req.province_2024, req.district_2024)
    ]
    return decide(req, purported)[0].value


def explanation_checks() -> list[dict]:
    checks = []
    fixtures = [
        ("reported_1630", "16:30", ReplayMode.REPORTED_DATELINE_REPLAY,
         "MISSING_DISTRICT_NAMED_BULLETIN", None),
        ("reported_1645", "16:45", ReplayMode.REPORTED_DATELINE_REPLAY,
         "VERIFY_PIVOTAL_PUBLICATION_PROVENANCE",
         {"GOV-2024-09-08-1637", "SYN-CAP-YAGI-ALPHA-LUCYEN"}),
        ("strict_1645", "16:45", ReplayMode.STRICT_AS_OF_2024,
         "HISTORICAL_AVAILABILITY_NOT_AUTHENTICATED", None),
    ]
    for label, clock, mode, required_action, pivots in fixtures:
        req = request(clock, mode.value)
        result = counterfactual_dossier(req, all_catalog())["current"]
        plan = result["research_action_plan"]
        codes = {x["code"] for x in plan["next_evidence_steps"]}
        got_pivots = set(plan["pivotal_source_ids"])
        passed = (
            required_action in codes
            and (pivots is None or got_pivots == pivots)
            and plan["new_evidence_collected"] is False
            and plan["model_or_vendor_called"] is False
            and plan["operational_emergency_action_authorized"] is False
        )
        checks.append({
            "case": label,
            "required_next_action": required_action,
            "gold_pivotal_source_ids": sorted(pivots) if pivots is not None else None,
            "result_pivotal_source_ids": sorted(got_pivots),
            "passed": passed,
        })
    return checks


def run_comparison() -> dict:
    matrix = test_matrix()
    original = run_benchmark()
    if original["cases_total"] != len(matrix):
        raise ValueError("SOURCE_BENCHMARK_CASE_COUNT_CHANGED")
    comparisons = []
    for case, genuine in zip(matrix, original["cases"]):
        if genuine["case"] != case.name:
            raise ValueError("SOURCE_BENCHMARK_CASE_ORDER_CHANGED")
        weak = weak_time_blind_control(case)
        comparisons.append({
            "case": case.name,
            "category": case.category,
            "policy_gold_verdict": case.gold_verdict,
            "evidencetrail_actual_verdict": genuine["actual_agent_verdict"],
            "time_blind_own_control_verdict": weak,
            "evidencetrail_matches_gold_and_safety": genuine["passed"],
            "time_blind_own_control_matches_gold": weak == case.gold_verdict,
            "weak_control_false_warn": weak == WARN and case.gold_verdict == ABSTAIN,
        })
    n = len(comparisons)
    checks = explanation_checks()
    strong = sum(c["evidencetrail_matches_gold_and_safety"] for c in comparisons)
    weak = sum(c["time_blind_own_control_matches_gold"] for c in comparisons)
    false_warn = sum(c["weak_control_false_warn"] for c in comparisons)
    all_policies_pass = strong == n and all(c["passed"] for c in checks)
    return {
        "kind": "EVIDENCETRAIL_OFFLINE_INTERNAL_BASELINE_COMPARISON_V1",
        "sample_only": True,
        "case_count": n,
        "cases": comparisons,
        "evidencetrail_policy_gold_passes": strong,
        "own_weak_control_policy_gold_passes": weak,
        "own_weak_control_false_warn_cases": false_warn,
        "additional_plan_gold_checks": checks,
        "additional_plan_gold_passes": sum(x["passed"] for x in checks),
        "all_evidencetrail_policy_checks_pass": all_policies_pass,
        "baseline": "OWN_DELIBERATELY_UNSAFE_NO_TEMPORAL_OR_ORIGIN_FIREWALL",
        "baseline_is_rival_product_or_external_llm": False,
        "benchmark_is_external_field_test": False,
        "benchmark_is_storm_prediction_accuracy": False,
        "model_vendor_or_paid_api_called": False,
        "actual_2024_first_publication_authenticated": False,
        "notice": (
            "These 20 cases use hand-authored local policy labels and synthetic "
            "adversarial mutations of one historical Yagi research fixture. "
            "The naive baseline is OUR intentionally unsafe ablation, not a real "
            "competing agent. The 3 action-plan checks use declared policy fixtures. "
            "This does not measure real disaster impact, model intelligence, or other products."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args()
    report = run_comparison()
    if not report["all_evidencetrail_policy_checks_pass"]:
        print(json.dumps({"status": "FAIL", "case_count": report["case_count"]}))
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    print(json.dumps({
        "status": "OFFLINE_POLICY_COMPARISON_PASS",
        "cases": report["case_count"],
        "evidencetrail_passes": report["evidencetrail_policy_gold_passes"],
        "own_unsafe_baseline_passes": report["own_weak_control_policy_gold_passes"],
        "own_unsafe_baseline_false_warns": report["own_weak_control_false_warn_cases"],
        "explanation_plan_checks_passed": report["additional_plan_gold_passes"],
        "NOT_external_comparison_or_forecast_accuracy": True,
        "report": str(args.report),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
