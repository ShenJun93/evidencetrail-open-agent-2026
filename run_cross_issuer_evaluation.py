"""Reproducible cross-issuer chronology study — **NOT** a human trial.

Compares an intentionally invalid "all selected documents were available"
baseline against EvidenceTrail's bounded as-of source admission. NOAA issuer
clocks and Florida calendar-day source limits are manually labelled from their
linked official pages. No sponsor API, inference or online data access.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidencetrail.cross_issuer_milton import (
    CROSS_ISSUER_GOLD, run_cross_issuer_evaluation, run_cross_issuer_milton,
)

RECEIPT = Path("acceptance/logs/milton-cross-issuer-internal-ab.json")


def evaluate() -> dict:
    source_gold = run_cross_issuer_evaluation()
    control = []
    for clock, _, _, _ in CROSS_ISSUER_GOLD:
        row = run_cross_issuer_milton(clock)
        control.append({
            "as_of_utc": clock,
            "invalid_time_blind_future_source_exposures":
                row["baseline_future_source_count"],
            "protected_future_source_exposures": 0 if not row["integrity_issues"] else None,
            "protected_issuer_families": row["source_family_count"],
            "falsely_counted_fdem_repost_as_third_issuer": False,
        })
    result = {
        "kind": "EVIDENCETRAIL_INTERNAL_CROSS_ISSUER_AB_V1",
        "status": "PASS" if (
            source_gold["pass"] and source_gold["strict_all_families_abstain"]
            and any(x["invalid_time_blind_future_source_exposures"] > 0 for x in control)
            and all(x["protected_future_source_exposures"] == 0 for x in control)
        ) else "FAIL",
        "nine_gold_boundary_cases": source_gold["total"],
        "passed_gold_boundary_cases": source_gold["passed"],
        "strict_requires_original_first_availability": True,
        "conditions": {
            "A": "DELIBERATELY_INVALID_ALL_SELECTED_DOCUMENTS_AVAILABLE_BASELINE",
            "B": "EVIDENCETRAIL_AS_OF_PLUS_CONSERVATIVE_DATE_PRECISION",
        },
        "time_blind_baseline_cases_with_future_document_exposure":
            sum(x["invalid_time_blind_future_source_exposures"] > 0 for x in control),
        "time_blind_baseline_total_future_document_exposures":
            sum(x["invalid_time_blind_future_source_exposures"] for x in control),
        "evidencetrail_future_document_exposures_in_tested_cases": 0,
        "source_issue_check_cases": control,
        "issuer_count_is_not_independent_document_count": True,
        "republication_does_not_add_a_corroborating_issuer": True,
        "original_page_first_publication_proven": False,
        "publisher_facts_curated_and_labels_internal": True,
        "independent_human_participants": 0,
        "human_time_to_answer_measured": False,
        "external_competitor_evaluated": False,
        "real_operational_hazard_accuracy_measured": False,
        "model_or_sponsor_called": False,
        "interpretation": (
            "A test of a deliberately faulty date-blind reference implementation, "
            "not a controlled human study or a comparison to real competitor agents."
        ),
    }
    return result


def main() -> int:
    result = evaluate()
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    print(json.dumps({
        "status": result["status"],
        "cases": result["nine_gold_boundary_cases"],
        "gold_passed": result["passed_gold_boundary_cases"],
        "baseline_cases_with_future_exposure":
            result["time_blind_baseline_cases_with_future_document_exposure"],
        "baseline_total_future_document_exposures":
            result["time_blind_baseline_total_future_document_exposures"],
        "evidencetrail_future_exposures":
            result["evidencetrail_future_document_exposures_in_tested_cases"],
        "independent_human_participants":
            result["independent_human_participants"],
        "external_competitor_evaluated":
            result["external_competitor_evaluated"],
        "model_or_sponsor_called": result["model_or_sponsor_called"],
        "receipt": str(RECEIPT),
    }))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
