"""Open typed case investigation. No network, models, credentials or persistence.

Records and separate expectations are operator declarations. Matching them
establishes a local consistency contract, never external source authenticity.
"""
from __future__ import annotations

from dataclasses import asdict, fields
from hashlib import sha256
import json
from urllib.parse import urlsplit

from evidencetrail.claim_ledger import ClaimRule, SourcePin
from evidencetrail.models import (
    ProvenanceQuality, RecordKind, ReplayMode, SourceRecord, iso, parse_iso,
)
from evidencetrail.why_counterfactual import (
    _changes, _claim_view, _evaluate, _value_signature,
    explain_source_sets, explain_why,
)

MAX_CASE_BYTES = 60_000
MAX_CASE_SOURCES = 12
TRUST_BASIS = "OPERATOR_DECLARED_NOT_EXTERNALLY_VERIFIED"


class CaseRefusal(ValueError):
    """Safe code only; never include untrusted source text in an exception."""


def _text(value, maximum: int) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise CaseRefusal("CASE_TEXT_INVALID")
    return value


def _object(raw, cls):
    if not isinstance(raw, dict) or set(raw) - {field.name for field in fields(cls)}:
        raise CaseRefusal("CASE_FIELDS_REFUSED")
    try:
        return cls(**raw)
    except (TypeError, ValueError):
        raise CaseRefusal("CASE_RECORD_SCHEMA_INVALID") from None


def _locator(value) -> None:
    if not isinstance(value, str) or len(value) > 2048:
        raise CaseRefusal("CASE_LOCATOR_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise CaseRefusal("CASE_LOCATOR_INVALID") from None
    if (parsed.scheme not in {"https", "synthetic"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or any(ord(c) <= 32 for c in value)):
        raise CaseRefusal("CASE_LOCATOR_REFUSED")


def _parse_case(pack: dict):
    allowed = {"schema_version", "case_id", "title", "question", "as_of_utc",
               "sources", "pins", "rules"}
    if not isinstance(pack, dict) or set(pack) != allowed:
        raise CaseRefusal("CASE_TOP_LEVEL_FIELDS_REFUSED")
    if pack["schema_version"] != "evidencetrail.case.v1":
        raise CaseRefusal("CASE_SCHEMA_VERSION_REFUSED")
    for key, maximum in (("case_id", 80), ("title", 160), ("question", 1000)):
        _text(pack[key], maximum)
    try:
        if not isinstance(pack["as_of_utc"], str) or parse_iso(pack["as_of_utc"]) is None:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise CaseRefusal("CASE_CLOCK_INVALID") from None
    try:
        if len(json.dumps(pack, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_CASE_BYTES:
            raise CaseRefusal("CASE_BYTES_LIMIT_60000")
    except (TypeError, OverflowError, RecursionError):
        raise CaseRefusal("CASE_JSON_INVALID") from None
    if (not isinstance(pack["sources"], list) or
            not 1 <= len(pack["sources"]) <= MAX_CASE_SOURCES or
            not isinstance(pack["pins"], list) or
            len(pack["pins"]) != len(pack["sources"]) or
            not isinstance(pack["rules"], list) or not 1 <= len(pack["rules"]) <= 12):
        raise CaseRefusal("CASE_RECORD_COUNTS_REFUSED")
    rules = [_object(item, ClaimRule) for item in pack["rules"]]
    rows, pins = [], {}
    for item in pack["sources"]:
        row = _object(item, SourceRecord)
        try:
            row.record_kind = RecordKind(row.record_kind)
            row.provenance_quality = ProvenanceQuality(row.provenance_quality)
        except (TypeError, ValueError):
            raise CaseRefusal("CASE_SOURCE_ENUM_REFUSED") from None
        if (row.first_availability_proven_utc is not None or
                row.provenance_quality == ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT):
            raise CaseRefusal("CASE_CALLER_ATTESTATION_REFUSED")
        permitted_origins = {
            RecordKind.GOVERNMENT_NEWS:
                ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            RecordKind.SYNTHETIC_CAPACITY: ProvenanceQuality.SYNTHETIC,
        }
        if permitted_origins.get(row.record_kind) != row.provenance_quality:
            raise CaseRefusal("CASE_KIND_ORIGIN_COMBINATION_REFUSED")
        for clock in ("published_at_displayed_utc", "observed_at_utc",
                      "issued_at_claimed_utc", "retrieved_at_utc"):
            value = getattr(row, clock)
            if value is not None and not isinstance(value, str):
                raise CaseRefusal("CASE_CLOCK_TYPE_REFUSED")
            try:
                setattr(row, clock, parse_iso(value))
            except (ValueError, TypeError, OverflowError):
                raise CaseRefusal("CASE_CLOCK_INVALID") from None
        _locator(row.locator)
        _text(row.publisher, 200)
        rows.append(row)
    for item in pack["pins"]:
        pin = _object(item, SourcePin)
        if not isinstance(pin.source_id, str) or pin.source_id in pins:
            raise CaseRefusal("CASE_PIN_IDENTITY_REFUSED")
        try:
            pin = SourcePin(**{**asdict(pin), "record_kind": RecordKind(pin.record_kind),
                              "provenance_quality": ProvenanceQuality(pin.provenance_quality)})
        except (TypeError, ValueError):
            raise CaseRefusal("CASE_PIN_ENUM_REFUSED") from None
        pins[pin.source_id] = pin
    return rows, pins, rules


def investigate_case(pack: dict, *, as_of_utc: str | None = None, strict: bool = False,
                     withdrawn_source_ids=(), search_depth: int = 2) -> dict:
    if type(strict) is not bool:
        raise CaseRefusal("CASE_STRICT_REQUIRES_BOOL")
    if type(search_depth) is not int or not 1 <= search_depth <= 3:
        raise CaseRefusal("CASE_SEARCH_DEPTH_1_TO_3_REQUIRED")
    if not isinstance(withdrawn_source_ids, (list, tuple)) or not all(
            isinstance(sid, str) for sid in withdrawn_source_ids):
        raise CaseRefusal("CASE_WITHDRAWALS_INVALID")
    if len(withdrawn_source_ids) != len(set(withdrawn_source_ids)):
        raise CaseRefusal("CASE_DUPLICATE_WITHDRAWAL_REFUSED")
    rows, pins, rules = _parse_case(pack)
    clock = pack["as_of_utc"] if as_of_utc is None else as_of_utc
    mode = ReplayMode.STRICT_AS_OF_2024 if strict else ReplayMode.REPORTED_DATELINE_REPLAY
    # Full original validation first, including withheld/future records.
    why = explain_why(rows, pins, rules, as_of_utc=clock, mode=mode,
                      max_counterfactual_sources=MAX_CASE_SOURCES)
    removed = set(withdrawn_source_ids)
    if not removed.issubset(pins):
        raise CaseRefusal("CASE_UNKNOWN_WITHDRAWAL_REFUSED")
    resilience = explain_source_sets(rows, pins, rules, as_of_utc=clock,
                                     mode=mode, search_depth=search_depth)
    before = why["selected_claims"]
    after = _claim_view(_evaluate(
        [row for row in rows if row.source_id not in removed],
        {sid: pin for sid, pin in pins.items() if sid not in removed}, rules,
        why["as_of_utc"], mode))
    value_changed = any(_value_signature(before.get(key)) != _value_signature(after.get(key))
                        for key in set(before) | set(after))
    return {
        "kind": "EVIDENCETRAIL_OPEN_CASE_INVESTIGATION_V1",
        "case_id": pack["case_id"], "title": pack["title"], "question": pack["question"],
        "question_is_descriptive_not_a_natural_language_policy": True,
        "trust_basis": TRUST_BASIS,
        "external_source_authentication_performed": False,
        "model_or_sponsor_called": False, "independent_human_participants": 0,
        "why": why, "resilience": resilience,
        "experiment": {
            "removed_source_ids": sorted(removed), "selected_claims_after": after,
            "changed_claims": _changes(before, after),
            "value_or_availability_changed": value_changed,
            "simulated_not_an_actual_publisher_retraction": True,
        },
        "execution_trace": [
            {"action": "VALIDATE_FULL_CASE", "source_count": len(rows),
             "rule_count": len(rules), "status": "LOCAL_CONSISTENCY_PASS"},
            {"action": "APPLY_TIME_POLICY", "eligible_source_count":
             len(resilience["withdrawal_candidate_source_ids"]), "as_of_utc": why["as_of_utc"]},
            {"action": "SEARCH_JOINT_WITHDRAWALS", "subsets_evaluated":
             resilience["subsets_evaluated"], "max_size": resilience["searched_max_withdrawal_size"]},
            {"action": "SIMULATE_SELECTED_WITHDRAWALS", "removed_source_ids": sorted(removed),
             "value_or_availability_changed": value_changed},
        ],
        "notice": "Deterministic typed-case investigation. Operator pins are not source truth. "
                  "Source-set resilience is conditional on this corpus and policy, not confidence.",
    }


def make_case_pack(case_id: str, title: str, question: str, clock: str,
                   rows: list[SourceRecord], pins: dict[str, SourcePin],
                   rules: list[ClaimRule]) -> dict:
    """Serialize declarations; admission still requires investigate_case."""
    return {"schema_version": "evidencetrail.case.v1", "case_id": case_id,
            "title": title, "question": question, "as_of_utc": clock,
            "rules": [asdict(rule) for rule in rules],
            "sources": [row.to_public_dict() for row in rows],
            "pins": [asdict(pin) for pin in pins.values()]}


def example_case(name: str) -> dict:
    if name == "milton":
        from evidencetrail.claim_ledger_milton import curated_milton_manifest
        from evidencetrail.zetaris_cross_issuer import _canonical_rows
        from run_zetaris_cross_issuer import import_rows
        rows = _canonical_rows(*import_rows())
        pins, rules = curated_milton_manifest()
        case_id, title, clock = "MILTON-CURATED", "Milton curated-source research", "2024-10-07T11:00:00Z"
        question = "Which selected evidence supports the wind and emergency-order claims?"
    elif name == "warehouse":
        rule = ClaimRule("STOCK", "WAREHOUSE_LOG", "declared_stock", "value", "pallets",
                         "Fictional warehouse stock")
        rows, pins, rules = [], {}, [rule]
        for sid, value, hour in (("STOCK-OLD", 12, 8), ("STOCK-LEDGER", 25, 9),
                                 ("STOCK-CHECK", 25, 9), ("STOCK-FUTURE", 40, 10)):
            text = f"FICTIONAL warehouse exercise: {sid} declares {value} pallets."
            issue = f"2026-10-24T{hour:02d}:00:00Z"
            row = SourceRecord(
                source_id=sid, record_kind=RecordKind.SYNTHETIC_CAPACITY,
                locator="synthetic://warehouse/"+sid, publisher="Fictional Warehouse Log",
                paraphrase=text, excerpt=text, excerpt_sha256=sha256(text.encode()).hexdigest(),
                published_at_displayed_utc=parse_iso(issue), observed_at_utc=None,
                issued_at_claimed_utc=parse_iso(issue), first_availability_proven_utc=None,
                retrieved_at_utc=None, provenance_quality=ProvenanceQuality.SYNTHETIC,
                historical_admin_vintage="2026", spatial_scope=["fictional warehouse"],
                named_districts_2024=[], granularity="declared_inventory",
                observation_fields={"issuer_family": rule.issuer_family,
                                    "claim_type": rule.claim_type, "value": value})
            rows.append(row)
            pins[sid] = SourcePin(sid, row.locator, row.publisher, row.excerpt_sha256,
                                  rule.issuer_family, rule.key, value, row.record_kind,
                                  row.provenance_quality, claimed_issue_utc=issue)
        case_id, title, clock = "WAREHOUSE-FICTIONAL", "Fictional warehouse: hidden redundancy", "2026-10-24T09:30:00Z"
        question = "Does one missing record change stock, or must both current records disappear?"
    else:
        raise CaseRefusal("CASE_EXAMPLE_NOT_REGISTERED")
    return make_case_pack(case_id, title, question, clock, rows, pins, rules)
