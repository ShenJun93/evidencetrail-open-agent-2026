"""Offline, randomized cross-over analyst study (PUBLIC curated history only).

Generates respondent-only HTML packets WITHOUT gold answers. Results are
self-reported browser timing, never independent human proof by themselves.
No participant identifiers, names, emails, API keys or provider calls.
The reference arm is FAIR: it shows all dated sources, NOT an intentionally
false answer or a fabricated baseline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import statistics
from typing import Any

from evidencetrail.cross_issuer_milton import _fl_metadata, run_cross_issuer_milton
from evidencetrail.external_milton import _load as load_nhc

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "studies" / "analyst_participant.html"
KIND_PACKET = "EVIDENCETRAIL_BLIND_ANALYST_PACKET_V1"
KIND_RESULT = "EVIDENCETRAIL_BLIND_ANALYST_RESULT_V1"
GOLD_CLOCKS = (
    "2024-10-07T03:59:00Z",
    "2024-10-07T04:00:00Z",
    "2024-10-07T11:00:00Z",
    "2024-10-07T15:00:00Z",
)
ARMS = ("REFERENCE_ONLY", "CHRONOLOGY_ASSISTED")
SHA = re.compile(r"[0-9a-f]{64}\Z")
SESSION = re.compile(r"[0-9a-f]{24}\Z")
TASK = re.compile(r"T[0-3]\Z")
MAX_RESULT_BYTES = 32768


class StudyValidationError(ValueError):
    pass


def source_cards() -> list[dict]:
    """Only manually curated public sources, never source gold."""
    _, nhc = load_nhc()
    _, fl = _fl_metadata()
    cards = []
    for row in nhc:
        cards.append({
            "source_id": row.source_id,
            "issuer": "NOAA/NHC",
            "source_url": row.locator,
            "claim_type": "Reported maximum sustained wind",
            "claim_value": row.observation_fields["reported_maximum_sustained_wind_mph"],
            "unit": "mph",
            "claimed_issue_utc": row.issued_at_claimed_utc.isoformat().replace("+00:00", "Z"),
            "printed_local_date": None,
            "date_only": False,
            "source_first_publication_authenticated": False,
        })
    for row in fl:
        cards.append({
            "source_id": row["id"],
            "issuer": "Florida Governor",
            "source_url": row["url"],
            "claim_type": row["claim_type"].replace("_", " "),
            "claim_value": row["value"],
            "unit": "counties" if row["claim_type"] == "florida_counties_under_emergency" else "mph",
            "claimed_issue_utc": None,
            "printed_local_date": row["displayed_date_local"],
            "date_only": True,
            "source_first_publication_authenticated": False,
        })
    return sorted(cards, key=lambda item: item["source_id"])


def assignment(slot: int) -> list[tuple[int, str]]:
    """8 balanced Latin-style sequences.

    Across one complete block, each of the four cases appears twice in each
    arm, and each arm appears equally often in position 1 and 2.
    """
    if type(slot) is not int or not 0 <= slot < 1_000_000:
        raise StudyValidationError("ASSIGNMENT_SLOT_INVALID")
    template = (
        ((0, "REFERENCE_ONLY"), (3, "CHRONOLOGY_ASSISTED")),
        ((3, "CHRONOLOGY_ASSISTED"), (0, "REFERENCE_ONLY")),
        ((0, "CHRONOLOGY_ASSISTED"), (3, "REFERENCE_ONLY")),
        ((3, "REFERENCE_ONLY"), (0, "CHRONOLOGY_ASSISTED")),
        ((1, "REFERENCE_ONLY"), (2, "CHRONOLOGY_ASSISTED")),
        ((2, "CHRONOLOGY_ASSISTED"), (1, "REFERENCE_ONLY")),
        ((1, "CHRONOLOGY_ASSISTED"), (2, "REFERENCE_ONLY")),
        ((2, "REFERENCE_ONLY"), (1, "CHRONOLOGY_ASSISTED")),
    )
    return list(template[slot % len(template)])


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def packet_for_slot(slot: int, *, token: str | None = None) -> dict:
    token = secrets.token_hex(12) if token is None else token
    if not isinstance(token, str) or not SESSION.fullmatch(token):
        raise StudyValidationError("SESSION_TOKEN_INVALID")
    cards = source_cards()
    tasks = []
    for idx, arm in assignment(slot):
        clock = GOLD_CLOCKS[idx]
        details: dict[str, Any] = {
            "task_id": f"T{idx}",
            "as_of_utc": clock,
            "arm": arm,
            "arm_label": ("Reference documents" if arm == "REFERENCE_ONLY"
                          else "Chronology-assisted documents"),
            "cards": cards,
        }
        if arm == "CHRONOLOGY_ASSISTED":
            report = run_cross_issuer_milton(clock)
            eligible = sorted(
                report["nhc_admitted_ids"] +
                [item["id"] for item in report["florida_admitted"]]
            )
            # Assistance gives provenance admission flags, NOT answer key,
            # and does not change what source cards are shown.
            details["admission_overlay"] = {
                "admitted_source_ids": eligible,
                "policy": "REPORTED_DATELINE_REPLAY",
                "date_only_conservative_utc_offset": "-04:00",
                "first_original_publication_proven": False,
            }
        tasks.append(details)
    packet = {
        "kind": KIND_PACKET, "session_token": token,
        "assignment_slot_mod8": slot % 8, "tasks": tasks,
        "voluntary_no_personal_data": True,
        "participant_procedure": (
            "Two short retrospective historical evidence questions, one "
            "with a chronology overlay and one without. No live weather "
            "recommendations. You may stop at any time without submitting. "
            "Do not open other tabs or view the answer key until finished."
        ),
        "first_publication_unverified": True,
        "historical_disaster_advice_authorized": False,
    }
    # Digest includes the secret session token, full references, assignment
    # and assisted overlay but NO model result / grading gold.
    packet["packet_sha256"] = hashlib.sha256(_canonical(packet)).hexdigest()
    return packet


def render_packet(packet: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    placeholder = "__STUDY_PACKET_JSON__"
    if template.count(placeholder) != 1:
        raise StudyValidationError("STUDY_TEMPLATE_PLACEHOLDER_INVALID")
    # Never interpolate source text/URL into HTML: script JSON is escaped
    # against script-tag termination; UI inserts it via textContent.
    encoded = json.dumps(packet, ensure_ascii=True).replace("<", "\\u003c")
    return template.replace(placeholder, encoded)


def _as_int_or_none(value):
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 999:
        raise StudyValidationError("ANSWER_INT_OR_NULL_INVALID")
    return value


def validate_result(obj: dict, packet: dict) -> dict:
    """Strictly validate browser-export schema against researcher packet.

    Packet's expected identity must be the researcher's disk packet, NOT a
    packet copied from the respondent's untrusted result document.
    """
    if not isinstance(obj, dict) or obj.get("kind") != KIND_RESULT:
        raise StudyValidationError("RESULT_KIND_INVALID")
    if (obj.get("session_token") != packet["session_token"]
            or obj.get("packet_sha256") != packet["packet_sha256"]
            or obj.get("assignment_slot_mod8") != packet["assignment_slot_mod8"]):
        raise StudyValidationError("RESULT_PACKET_BINDING_INVALID")
    answers = obj.get("answers")
    if not isinstance(answers, list) or len(answers) != 2:
        raise StudyValidationError("RESULT_ANSWER_COUNT_INVALID")
    outputs = []
    for actual, task in zip(answers, packet["tasks"]):
        if not isinstance(actual, dict) or set(actual) != {
            "task_id", "arm", "as_of_utc", "nhc_wind_mph",
            "florida_counties", "source_ids", "elapsed_ms"
        }:
            raise StudyValidationError("RESULT_SCHEMA_FIELDS_INVALID")
        if (actual["task_id"] != task["task_id"]
                or actual["arm"] != task["arm"]
                or actual["as_of_utc"] != task["as_of_utc"]):
            raise StudyValidationError("RESULT_TASK_ASSIGNMENT_MISMATCH")
        wind = _as_int_or_none(actual["nhc_wind_mph"])
        counties = _as_int_or_none(actual["florida_counties"])
        ids = actual["source_ids"]
        possible = {x["source_id"] for x in task["cards"]}
        if (not isinstance(ids, list) or len(ids) != len(set(ids))
                or len(ids) > 7 or any(not isinstance(x, str) or x not in possible for x in ids)):
            raise StudyValidationError("RESULT_CITATION_IDENTIFIERS_INVALID")
        elapsed = actual["elapsed_ms"]
        if type(elapsed) is not int or not 1000 <= elapsed <= 900000:
            raise StudyValidationError("RESULT_TIME_IMPLAUSIBLE_OR_INVALID")
        # Gold stays completely separate from exported participant HTML.
        from evidencetrail.cross_issuer_milton import run_cross_issuer_milton
        report = run_cross_issuer_milton(task["as_of_utc"])
        wanted_wind = report["latest_nhc_selected_wind_mph"]
        wanted_count = report["florida_counties_under_emergency_in_selected_order"]
        pivotal = set()
        if wanted_wind is not None:
            pivotal.add(report["nhc_admitted_ids"][-1])
        admitted_orders = [r for r in report["florida_admitted"]
                          if r["claim_type"] == "florida_counties_under_emergency"]
        if wanted_count is not None and admitted_orders:
            pivotal.add(sorted(admitted_orders,key=lambda r:(r["displayed_local_date"],r["id"]))[-1]["id"])
        reported_ids=set(ids)
        outputs.append({
            "task_id":task["task_id"],
            "arm":task["arm"],
            "numbers_correct":int(wind == wanted_wind) + int(counties == wanted_count),
            "numbers_possible":2,
            "pivotal_citation_precision":(
                len(pivotal & reported_ids) / len(reported_ids) if ids else
                (1.0 if not pivotal else 0.0)),
            "pivotal_citation_recall":(
                len(pivotal & reported_ids) / len(pivotal) if pivotal else
                (1.0 if not ids else 0.0)),
            "future_or_irrelevant_citations":len(reported_ids - pivotal),
            "exact_pivotal_citations":reported_ids == pivotal,
            "elapsed_ms_self_reported":elapsed,
        })
    return {
        "session_token":packet["session_token"],
        "valid_packet_bound_responses":True,
        "independent_human_verified":False,
        "automated_or_fabricated_response_excluded_from_human_n":True,
        "scores":outputs,
    }


def score_dir(directory: Path, packets_dir: Path) -> dict:
    records = []
    rejects = []
    seen=set()
    for path in sorted(directory.glob("*.json")):
        try:
            if path.stat().st_size > MAX_RESULT_BYTES:
                raise StudyValidationError("RESULT_SIZE_EXCEEDED")
            result=json.loads(path.read_text(encoding="utf-8"))
            tok=result.get("session_token") if isinstance(result,dict) else None
            if not isinstance(tok,str) or not SESSION.fullmatch(tok) or tok in seen:
                raise StudyValidationError("UNKNOWN_OR_DUPLICATE_SESSION_TOKEN")
            packet_path=packets_dir/(tok+".json")
            if not packet_path.is_file():
                raise StudyValidationError("MATCHING_RESEARCHER_PACKET_ABSENT")
            packet=json.loads(packet_path.read_text(encoding="utf-8"))
            trusted_digest=packet.pop("packet_sha256",None)
            if not isinstance(trusted_digest,str) or not SHA.fullmatch(trusted_digest):
                raise StudyValidationError("PACKET_HASH_INVALID")
            if hashlib.sha256(_canonical(packet)).hexdigest()!=trusted_digest:
                raise StudyValidationError("RESEARCHER_PACKET_TAMPERED")
            packet["packet_sha256"]=trusted_digest
            evaluated=validate_result(result,packet)
            seen.add(tok)
            records.append(evaluated)
        except (StudyValidationError,ValueError,UnicodeError,TypeError,
                KeyError, OSError) as exc:
            rejects.append({"file":path.name,"safe_reason":(
                str(exc) if isinstance(exc,StudyValidationError)
                else "MALFORMED_OR_UNAVAILABLE_JSON")})
    results = [score for r in records for score in r["scores"]]
    # Cross-over contrasts are descriptives on unverified submissions.
    # Neither assignment balancing nor browser timing authenticates people.
    paired = []
    for rec in records:
        arms = {s["arm"]: s for s in rec["scores"]}
        if set(arms) == set(ARMS):
            a = arms["CHRONOLOGY_ASSISTED"]
            b = arms["REFERENCE_ONLY"]
            paired.append({
                "numeric_accuracy_delta_assisted_minus_reference":
                    a["numbers_correct"]-b["numbers_correct"],
                "exact_citation_delta_assisted_minus_reference":
                    int(a["exact_pivotal_citations"])-int(b["exact_pivotal_citations"]),
                "elapsed_ms_delta_assisted_minus_reference":
                    a["elapsed_ms_self_reported"]-b["elapsed_ms_self_reported"],
            })
    summary = {}
    for arm in ARMS:
        values=[v for v in results if v["arm"]==arm]
        summary[arm]={
            "unverified_submitted_task_count":len(values),
            "number_accuracy_percent_on_submissions":(
                round(100*sum(v["numbers_correct"] for v in values)/
                      (2*len(values)),1) if values else None),
            "exact_citation_percent_on_submissions":(
                round(100*sum(v["exact_pivotal_citations"] for v in values)/
                      len(values),1) if values else None),
            "median_elapsed_ms_self_reported":(
                statistics.median(v["elapsed_ms_self_reported"] for v in values)
                if values else None),
        }
    return {
        "kind":"EVIDENCETRAIL_ANALYST_BLIND_SCORING_V1",
        "status":"NO_INDEPENDENT_HUMAN_VALIDATION" if records else "NO_RESPONSES",
        "unverified_packet_bound_sessions":len(records),
        "independently_verified_human_participants":0,
        "human_impact_claim_authorized":False,
        "rejected_file_count":len(rejects),
        "rejected":rejects,
        "arm_descriptives_unverified":summary,
        "paired_differences_unverified": {
            "paired_session_count":len(paired),
            "average_numeric_correct_delta":(
                round(statistics.fmean(x["numeric_accuracy_delta_assisted_minus_reference"]
                                       for x in paired),3) if paired else None),
            "average_exact_pivotal_citation_delta":(
                round(statistics.fmean(x["exact_citation_delta_assisted_minus_reference"]
                                       for x in paired),3) if paired else None),
            "median_browser_elapsed_ms_delta":(
                statistics.median(x["elapsed_ms_delta_assisted_minus_reference"]
                                  for x in paired) if paired else None),
            "both_cases_differ_per_participant":True,
            "cross_case_difficulty_and_practice_can_confound_differences":True,
            "formal_significance_test_or_causal_effect_established":False,
        },
        "pre_registered_metrics":["numeric_correct_0_to_2",
                                  "exact_pivotal_citations",
                                  "future_or_irrelevant_citations",
                                  "browser_self_reported_elapsed_ms"],
        "uncertainty":"No recruitment/authenticity attestations, no causal estimate",
        "model_or_sponsor_called":False,
        "no_operational_weather_advice":True,
    }


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    pack=sub.add_parser("prepare")
    pack.add_argument("--slot",type=int,required=True)
    pack.add_argument("--out",type=Path,required=True)
    pack.add_argument("--registry",type=Path,
                      default=Path("acceptance/logs/blind-study-private-registry"))
    score=sub.add_parser("score")
    score.add_argument("--responses",type=Path,required=True)
    score.add_argument("--packets",type=Path,required=True)
    score.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    if args.command=="prepare":
        # Private registry is kept separate from the respondent-only HTML.
        if args.out.exists() or args.out.suffix.lower()!=".html":
            raise SystemExit("REFUSE_OVERWRITE_OR_NONHTML_PACKET")
        packet=packet_for_slot(args.slot)
        registry=args.registry/(packet["session_token"]+".json")
        if registry.exists() or args.registry.resolve()==args.out.parent.resolve():
            raise SystemExit("REFUSE_REGISTRY_COLLISION_OR_SHARED_PACKET_DIRECTORY")
        args.registry.mkdir(parents=True,exist_ok=True)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        registry.write_text(json.dumps(packet,indent=2)+"\n",encoding="utf-8")
        args.out.write_text(render_packet(packet),encoding="utf-8")
        print(json.dumps({"status":"STUDY_PACKET_PREPARED","slot_mod8":args.slot%8,
                          "html":str(args.out),"private_registry":str(args.registry),
                          "private_packet_file_created":True,
                          "independent_human_participants":0,"gold_in_html":False}))
        return 0
    if args.output.exists():
        raise SystemExit("REFUSE_OVERWRITE_SCORING_REPORT")
    report=score_dir(args.responses,args.packets)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],
                      "verified_independent_human_n":0,
                      "unverified_sessions":report["unverified_packet_bound_sessions"],
                      "rejected":report["rejected_file_count"],
                      "report":str(args.output)}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
