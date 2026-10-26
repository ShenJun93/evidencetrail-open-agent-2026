"""Reproduce the independently published NOAA/NHC issue-clock case (offline).

Usage: py -3 run_external_noaa_evaluation.py
No network requests, model calls, secrets, weather prediction or live warnings.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidencetrail.external_milton import run_external_chronology_checks

OUTPUT = Path("acceptance/logs/external-noaa-milton-issue-clock.json")


def main() -> int:
    result = run_external_chronology_checks()
    status = (
        result["all_pass"]
        and result["case_count"] == 8
        and result["passed"] == 8
        and result["strict_abstains_without_authenticated_first_availability"]
        and result["sponsor_inference_called"] is False
        and result["external_user_validation_or_prediction_accuracy"] is False
    )
    result["status"] = "PASS" if status else "FAIL"
    result["external_first_publication_authenticated"] = False
    result["noaa_source_pages_fetched_by_this_script"] = False
    result["evaluation_requires_human_ground_truth_review"] = True
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "kind": result["kind"], "status": result["status"],
        "case_count": result["case_count"], "passed": result["passed"],
        "strict_abstains_without_authenticated_first_availability":
            result["strict_abstains_without_authenticated_first_availability"],
        "sponsor_inference_called": result["sponsor_inference_called"],
        "external_user_validation_or_prediction_accuracy":
            result["external_user_validation_or_prediction_accuracy"],
        "receipt": str(OUTPUT),
    }))
    return 0 if status else 2


if __name__ == "__main__":
    raise SystemExit(main())
