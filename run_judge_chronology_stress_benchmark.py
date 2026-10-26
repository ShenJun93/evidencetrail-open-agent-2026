"""Reproducible, adversarial, offline EvidenceTrail chronology benchmark.

Gold labels are explicitly authored from the EvidenceTrail research policy,
NOT computed by the reducer under test. Cases include deliberately forged
records/metadata; these are synthetic mutations, NOT real Yagi 2024 sources.

Compares *our own* observation-as-publication mistake as a transparent
pedagogic negative control. It is NOT a claim about rival products, external
human evaluators, operational forecast accuracy, or lives saved.
"""
from __future__ import annotations

import argparse
import copy
import json
import tempfile
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Callable

from evidencetrail.catalog import all_catalog
from evidencetrail.models import (
    ProvenanceQuality, RecordKind, RunRequest, Verdict,
)
from evidencetrail.pipeline import EvidenceTrailPipeline

OUTPUT = Path("acceptance/logs/chronology-blind-stress-20261023.json")
TARGET = "GOV-2024-09-08-1637"
CAPACITY = "SYN-CAP-YAGI-ALPHA-LUCYEN"
WARN = "WARN"
ABSTAIN = "INSUFFICIENT_EVIDENCE"

@dataclass(frozen=True)
class Case:
    name: str
    clock: str
    mode: str
    mutate: Callable[[list], list]
    gold_verdict: str
    # ID(s) that must not be admitted, to guard against adversarial spoofing
    forbidden_eligible: tuple[str, ...] = ()
    category: str = "adversarial_mutation"


def identity(rows):
    return rows


def edit(target_id: str, **attrs):
    def perform(rows):
        return [
            replace(row, **attrs) if row.source_id == target_id else row
            for row in rows
        ]
    return perform


def delete(target_id: str):
    return lambda rows: [row for row in rows if row.source_id != target_id]


def mutate_cap(**attrs):
    return edit(CAPACITY, **attrs)


def target():
    return next(r for r in all_catalog() if r.source_id == TARGET)


def test_matrix() -> tuple[Case, ...]:
    article = target()
    later = article.published_at_displayed_utc + timedelta(minutes=9)
    return (
        Case("01_baseline_1630_abstains", "16:30", "REPORTED_DATELINE_REPLAY",
             identity, ABSTAIN, (TARGET,), "control"),
        Case("02_baseline_1637_may_warn_simulated", "16:37", "REPORTED_DATELINE_REPLAY",
             identity, WARN, (), "control"),
        Case("03_baseline_1645_may_warn_simulated", "16:45", "REPORTED_DATELINE_REPLAY",
             identity, WARN, (), "control"),
        Case("04_strict_1645_abstains_without_body_proof", "16:45", "STRICT_AS_OF_2024",
             identity, ABSTAIN, (TARGET,), "control"),
        Case("05_remove_pivotal_district_article", "16:45", "REPORTED_DATELINE_REPLAY",
             delete(TARGET), ABSTAIN),
        Case("06_remove_fictional_capacity", "16:45", "REPORTED_DATELINE_REPLAY",
             delete(CAPACITY), ABSTAIN),
        Case("07_article_publication_after_asof", "16:45", "REPORTED_DATELINE_REPLAY",
             edit(TARGET, published_at_displayed_utc=later), ABSTAIN, (TARGET,)),
        Case("08_observed_before_asof_cannot_backdate_article", "16:30",
             "REPORTED_DATELINE_REPLAY",
             edit(TARGET, observed_at_utc=article.observed_at_utc - timedelta(hours=1)),
             ABSTAIN, (TARGET,)),
        Case("09_url_slug_1631_not_publication_proof", "16:30",
             "REPORTED_DATELINE_REPLAY",
             edit(TARGET, locator="https://baochinhphu.vn/fake-1631-source"),
             ABSTAIN, (TARGET,)),
        Case("10_article_names_different_district", "16:45",
             "REPORTED_DATELINE_REPLAY",
             edit(TARGET, named_districts_2024=["van yen"]), ABSTAIN),
        Case("11_capacity_other_scenario", "16:45", "REPORTED_DATELINE_REPLAY",
             mutate_cap(scenario_id="test-not-user-mission"), ABSTAIN),
        Case("12_capacity_watch_authorization_false", "16:45",
             "REPORTED_DATELINE_REPLAY", mutate_false_authorization, ABSTAIN),
        Case("13_archive_2026_masquerades_as_government_article", "16:45",
             "REPORTED_DATELINE_REPLAY",
             edit(TARGET, provenance_quality=
                  ProvenanceQuality.IMPORTED_2024_DATELINE_ON_2026_PORTAL),
             ABSTAIN, (TARGET,)),
        Case("14_synthetic_provenance_masquerades_as_government", "16:45",
             "REPORTED_DATELINE_REPLAY",
             edit(TARGET, provenance_quality=ProvenanceQuality.SYNTHETIC),
             ABSTAIN, (TARGET,)),
        Case("15_untrusted_plan_masquerades_as_authenticated_archive", "16:45",
             "REPORTED_DATELINE_REPLAY",
             mutate_cap(provenance_quality=
                        ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT),
             ABSTAIN, (CAPACITY,)),
        Case("16_mislocated_provincial_article_names_requested_district", "16:45",
             "REPORTED_DATELINE_REPLAY",
             edit(TARGET, spatial_scope=["lao cai"]), ABSTAIN, (TARGET,)),
        Case("17_imported_archive_relabelled_as_historical_government", "16:45",
             "REPORTED_DATELINE_REPLAY", repurpose_imported, ABSTAIN),
        Case("18_real_hindcast_remains_nonoperational", "16:45",
             "REPORTED_DATELINE_REPLAY", identity, WARN,
             ("HINDCAST-ECMWF-49R1-SEP2024",), "negative_source_control"),
        Case("19_future_provincial_lao_cai_article_ignored", "16:45",
             "REPORTED_DATELINE_REPLAY", identity, WARN,
             ("GOV-2024-09-09-1540",), "negative_source_control"),
        Case("20_imported_portal_never_cites_original_2024_availability", "16:45",
             "REPORTED_DATELINE_REPLAY", identity, WARN,
             ("ARCHIVE-PCTT-LAOCAI-YENBAI-2024-MIGRATION",),
             "negative_source_control"),
    )


def mutate_false_authorization(rows):
    output = []
    for row in rows:
        if row.source_id == CAPACITY:
            predicates = dict(row.plan_predicates)
            predicates["coordinator_watch_authorized"] = False
            output.append(replace(row, plan_predicates=predicates))
        else:
            output.append(row)
    return output


def repurpose_imported(rows):
    """Create only a synthetic forged record in an isolated fixture."""
    imported = next(r for r in rows if r.record_kind == RecordKind.IMPORTED_ARCHIVE)
    # The metadata remains the true reason for rejection, notwithstanding
    # an attacker's malicious retyping as a government article.
    forged = replace(
        imported, source_id=TARGET + "-SPOOF-2026-PORTAL",
        record_kind=RecordKind.GOVERNMENT_NEWS,
        named_districts_2024=["luc yen"],
        spatial_scope=["yen bai"],
    )
    filtered = [r for r in rows if r.source_id != TARGET]
    return filtered + [forged]


def request(clock: str, mode: str) -> RunRequest:
    stamp = f"2024-09-08T{clock}:00+07:00"
    return RunRequest.from_dict({
        "schema_version": "1",
        "mission_id": "yagi-yenbai-2024",
        "scenario_id": "yagi-replay-alpha",
        "as_of_utc": stamp,
        "mode": mode,
        "province_2024": "yen bai",
        "district_2024": "luc yen",
        "question": "Is a RESEARCH-ONLY SIMULATED coordinator watch supported?",
        "sample_mode": True,
        "max_retries": 0,
    })


def evaluate(case: Case) -> dict:
    req = request(case.clock, case.mode)
    rows = case.mutate(copy.deepcopy(all_catalog()))
    # Per-case fully isolated memory/logs; tests are the REAL sample-only
    # EvidenceTrail agent pipeline, not merely a second handwritten reducer.
    with tempfile.TemporaryDirectory(prefix="evidencetrail-blind-stress-") as path:
        p = Path(path)
        pipeline = EvidenceTrailPipeline(
            sample_mode=True, catalog_override=rows,
            persist_dir=p / "mem", log_dir=p / "logs",
        )
        result = pipeline.run(req)
    eligible = set(result.eligible_source_ids)
    forbidden_breached = sorted(eligible.intersection(case.forbidden_eligible))
    fake_sponsor_success = any(
        s.outcome.value == "REAL_SUCCESS" for s in result.sponsor_calls
    )
    accepted = (
        result.verdict.value == case.gold_verdict
        and not forbidden_breached
        and not fake_sponsor_success
    )
    return {
        "case": case.name,
        "category": case.category,
        "case_gold_verdict": case.gold_verdict,
        "actual_agent_verdict": result.verdict.value,
        "expected_rejected_source_ids": list(case.forbidden_eligible),
        "forbidden_admitted_source_ids": forbidden_breached,
        "simulated_sponsor_success_count": int(fake_sponsor_success),
        "passed": accepted,
    }


def baseline_observation_trap() -> dict:
    """Disclosure: internally constructed unsafe control, NOT a competitor."""
    fake_catalog = edit(
        TARGET, published_at_displayed_utc=target().observed_at_utc
    )(copy.deepcopy(all_catalog()))
    b = Case(
        "UNSAFE_observation_as_publication_control", "16:30",
        "REPORTED_DATELINE_REPLAY", lambda rows: fake_catalog,
        ABSTAIN, (TARGET,), "synthetic_unsafe_control",
    )
    comparison = evaluate(b)
    return {
        "name": "UNSAFE_OBSERVATION_AS_PUBLICATION",
        "description": "In the same own pipeline, deliberately replace 16:37 article's "
                       "publication clock with its 15:00 measurement clock",
        "actual_verdict_from_invalid_input": comparison["actual_agent_verdict"],
        "unsafe_control_falsely_admitted_article": bool(
            comparison["forbidden_admitted_source_ids"]
        ),
        "independent_external_system_evaluated": False,
    }


def run_benchmark() -> dict:
    cases = [evaluate(c) for c in test_matrix()]
    passed = sum(1 for c in cases if c["passed"])
    return {
        "kind": "OFFLINE_ADVERSARIAL_CHRONOLOGY_BENCHMARK_V1",
        "cases_total": len(cases),
        "cases_passed": passed,
        "cases_failed": len(cases) - passed,
        "all_cases_pass": passed == len(cases),
        "cases": cases,
        "own_unsafe_negative_control": baseline_observation_trap(),
        "frozen_2024_Yagi_research_fixture": True,
        "synthetic_attack_mutations_only": True,
        "public_policy_expected_labels_hand_authored_not_derived_from_reducer": True,
        "direct_NVIDIA_Nemotron_called": False,
        "meterless_or_zetaris_network_called": False,
        "benchmark_is_real_operational_accuracy": False,
        "benchmark_is_comparison_with_competitors": False,
        "historical_first_publication_authenticated": False,
        "lives_saved_or_deployment_claim": False,
        "notice": "Measures consistency with specified temporal/provenance rules on "
                  "synthetic adversarial mutations of a curated dateline dataset. "
                  "Not a retrospective flood prediction validation or external field study.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, default=OUTPUT)
    args = ap.parse_args(argv)
    report = run_benchmark()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf8",
    )
    print(json.dumps({
        "kind": report["kind"],
        "pass": report["cases_passed"],
        "total": report["cases_total"],
        "failed_cases": [c["case"] for c in report["cases"] if not c["passed"]],
        "naive_control_verdict": report[
            "own_unsafe_negative_control"
        ]["actual_verdict_from_invalid_input"],
        "receipt": str(args.report),
    }))
    return 0 if report["all_cases_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
