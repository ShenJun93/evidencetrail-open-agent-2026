"""Executable source-laundering challenge for judges; STRICTLY OFFLINE sample.

These checks mutate only fresh copies of public sample source records and run
the same Counterfactual Lab integrity boundary used by the Collector.
They do not prove external data truth, model performance, or sponsor inference.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path

from evidencetrail.catalog import all_catalog
from evidencetrail.counterfactual import counterfactual_dossier
from evidencetrail.firewall import filter_sources, jurisdiction_ok
from evidencetrail.models import ReplayMode, RunRequest
from evidencetrail.reducer import decide


def _request(clock: str, *, strict: bool = False) -> RunRequest:
    path = Path(__file__).resolve().parent.parent / "samples" / "inputs" / f"yagi_{clock}_lucyen.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if strict:
        raw["mode"] = ReplayMode.STRICT_AS_OF_2024.value
    return RunRequest.from_dict(raw)


def _case(label: str, request: RunRequest, catalog: list,
          expected: str, *, attack: bool) -> dict:
    try:
        result = counterfactual_dossier(request, catalog)
        observed = result["current"]["rule_verdict"]
    except ValueError as exc:
        observed = str(exc)
    passed = observed == expected
    return {
        "challenge": label,
        "attempted_source_manipulation": attack,
        "expected_boundary": expected,
        "observed_boundary": observed,
        "passed": passed,
        "computed_by_same_production_source_integrity_gate": True,
        "real_live_sponsor_network_called": False,
    }


def run_evidence_integrity_challenge() -> dict:
    catalog = all_catalog()
    early = _request("1630")
    late = _request("1645")
    pivot = next(row for row in catalog if row.source_id == "GOV-2024-09-08-1637")
    capacity = next(row for row in catalog
                    if row.source_id == "SYN-CAP-YAGI-ALPHA-LUCYEN")

    fake_text = "ADVERSARIAL fixture: false earlier dateline under reused URL"
    url_alias = replace(
        pivot, source_id="ATTACK-FRESH-ID-REUSED-URL",
        published_at_displayed_utc=early.as_of_utc - timedelta(minutes=1),
        excerpt=fake_text, excerpt_sha256=sha256(fake_text.encode()).hexdigest()
    )
    copied = replace(
        pivot, source_id="ATTACK-MIRRORED-ARTICLE",
        locator="https://example.invalid/copy-with-fresh-url",
        published_at_displayed_utc=early.as_of_utc - timedelta(minutes=1)
    )
    new_plan_text = "ADVERSARIAL fixture: second plan denies simulated watch"
    plan = replace(
        capacity, source_id="ATTACK-CONFLICTING-CAPACITY",
        locator="evidencetrail://synthetic/adversarial-capacity",
        excerpt=new_plan_text,
        excerpt_sha256=sha256(new_plan_text.encode()).hexdigest(),
        plan_predicates={**capacity.plan_predicates,
                         "coordinator_watch_authorized": False},
    )
    cases = [
        _case("Clean evidence: 16:30 abstains", early, catalog,
              "INSUFFICIENT_EVIDENCE", attack=False),
        _case("Clean evidence: 16:45 simulated watch", late, catalog,
              "WARN", attack=False),
        _case("Strict archive proof: abstain", _request("1645", strict=True),
              catalog, "INSUFFICIENT_EVIDENCE", attack=False),
        _case("ID replay and backdate", early, catalog + [replace(
            pivot, published_at_displayed_utc=early.as_of_utc)],
              "DUPLICATE_SOURCE_ID_REFUSED", attack=True),
        _case("Independent-ID laundering through one URL", early,
              catalog + [url_alias], "SOURCE_LOCATOR_ALIAS_REFUSED",
              attack=True),
        _case("Copied text under a different URL", early,
              catalog + [copied], "SOURCE_EXCERPT_ALIAS_REFUSED",
              attack=True),
        _case("Contradictory capacity plan on the same district", late,
              catalog + [plan], "AMBIGUOUS_SCENARIO_CAPACITY_REFUSED",
              attack=True),
    ]
    # Expose the real failure mode that the new gate prevents. This control
    # skips ONLY the independence check, not time or jurisdiction filtering.
    unsafe_rows, _ = filter_sources(
        [row for row in catalog + [url_alias] if jurisdiction_ok(
            row, early.province_2024, early.district_2024
        )], early.as_of_utc, early.mode,
    )
    unguarded = decide(early, unsafe_rows)[0].value
    return {
        "kind": "EVIDENCETRAIL_OFFLINE_SOURCE_INDEPENDENCE_CHALLENGE_V1",
        "offline_sample_only": True,
        "input_origin": "BUNDLED_SAMPLE_PLUS_LOCAL_ADVERSARIAL_MUTATIONS",
        "cases": cases,
        "case_count": len(cases),
        "passed_count": sum(x["passed"] for x in cases),
        "all_cases_pass": all(x["passed"] for x in cases),
        "unguarded_backdated_url_clone_rule_verdict": unguarded,
        "unguarded_clone_is_external_competitor": False,
        "historical_publication_authenticated": False,
        "real_vendor_model_called": False,
        "real_hazard_prediction_validated": False,
        "sponsor_eligibility_certified": False,
        "notice": (
            "These are deterministic fail-closed sample attacks, not external "
            "penetration testing. Duplicate source identifiers, aliases and "
            "ambiguous fictional plans are refused BEFORE as-of filtering "
            "and decision. A real archive or vendor completion is not proven."
        ),
    }
