"""Guided operator entry and append-only evidence updates. No external I/O.

Generated pins check the entries' later consistency; they do not independently
verify a publisher, a quantity's meaning or original availability.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import re

from evidencetrail.case_investigator import (
    MAX_CASE_BYTES, CaseRefusal, _locator, _parse_case, _text,
    investigate_case, make_case_pack,
)
from evidencetrail.claim_ledger import ClaimLedgerRefusal, ClaimRule, SourcePin, _validate_pins
from evidencetrail.models import ProvenanceQuality, RecordKind, SourceRecord, iso, parse_iso
from evidencetrail.why_counterfactual import _changes, _value_signature

PIN_ORIGIN = "GENERATED_FROM_OPERATOR_ENTRIES_NOT_INDEPENDENT_MANIFEST"
UPDATE_ORIGIN = "OPERATOR_ADDITION_NOT_AUTONOMOUS_REQUERY"
COMMON = {"source_id", "claim_key", "issuer_family", "unit", "value", "publisher",
          "locator", "excerpt", "source_type", "clock_type"}
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}\Z")


class DraftRefusal(ValueError):
    def __init__(self, code, *, row=None, field="case"):
        super().__init__(code)
        self.issues = [{"row": row, "field": field, "code": code}]


def _fail(code, row=None, field="case"):
    raise DraftRefusal(code, row=row, field=field)


def _bounded(value):
    try:
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_CASE_BYTES:
            _fail("DRAFT_BYTES_LIMIT_60000")
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, DraftRefusal): raise
        _fail("DRAFT_JSON_INVALID")


def _string(value, row, field, limit=200):
    try: return _text(value, limit).strip()
    except CaseRefusal: _fail("DRAFT_TEXT_REQUIRED_OR_TOO_LONG", row, field)


def _clock(value, row=None, field="as_of_utc"):
    try:
        if not isinstance(value, str) or not value.strip() or len(value) > 64: raise ValueError()
        result = parse_iso(value)
        if result is None: raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError):
        _fail("DRAFT_AWARE_ISO_CLOCK_REQUIRED", row, field)


def _investigate(pack, **options):
    try: return investigate_case(pack, **options)
    except (CaseRefusal, ClaimLedgerRefusal, ValueError, TypeError) as exc:
        code = str(exc)
        _fail(code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", code) else "DRAFT_CASE_INVALID")


def _entries(entries, rules):
    if not isinstance(entries, list) or not 1 <= len(entries) <= 12:
        _fail("DRAFT_SOURCE_COUNT_1_TO_12")
    rows, pins = [], {}
    for index, raw in enumerate(entries, 1):
        if not isinstance(raw, dict): _fail("DRAFT_SOURCE_FIELDS_REFUSED", index)
        clock_type = raw.get("clock_type")
        clocks = {"issued_at"} if clock_type == "precise" else {"local_day", "utc_offset_minutes"}
        if clock_type not in {"precise", "local_day"}:
            _fail("DRAFT_CLOCK_KIND_REQUIRED", index, "clock_type")
        if set(raw) != COMMON | clocks: _fail("DRAFT_SOURCE_FIELDS_REFUSED", index)
        identifiers = {}
        for field in ("source_id", "claim_key", "issuer_family", "unit"):
            value = _string(raw[field], index, field, 80)
            if not NAME.fullmatch(value): _fail("DRAFT_IDENTIFIER_INVALID", index, field)
            identifiers[field] = value
        sid, key = identifiers["source_id"], identifiers["claim_key"]
        if sid in pins: _fail("DRAFT_DUPLICATE_SOURCE_ID", index, "source_id")
        value = raw["value"]
        if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,8}", value): value = int(value)
        if type(value) is not int or not 0 <= value <= 100000000:
            _fail("DRAFT_WHOLE_NUMBER_0_TO_100000000", index, "value")
        if raw["source_type"] not in {"fictional", "government_original"}:
            _fail("DRAFT_SOURCE_TYPE_REFUSED", index, "source_type")
        fictional = raw["source_type"] == "fictional"
        kind = RecordKind.SYNTHETIC_CAPACITY if fictional else RecordKind.GOVERNMENT_NEWS
        quality = (ProvenanceQuality.SYNTHETIC if fictional else
                   ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN)
        locator = _string(raw["locator"], index, "locator", 2048)
        try: _locator(locator)
        except CaseRefusal: _fail("DRAFT_SAFE_SOURCE_LOCATOR_REQUIRED", index, "locator")
        if not fictional and not locator.startswith("https://"):
            _fail("DRAFT_ORIGINAL_REQUIRES_HTTPS_REFERENCE", index, "locator")
        excerpt = _string(raw["excerpt"], index, "excerpt", 12000)
        publisher = _string(raw["publisher"], index, "publisher")
        rule = rules.get(key)
        if rule is not None and (rule.issuer_family != identifiers["issuer_family"] or
                                 rule.unit != identifiers["unit"]):
            _fail("DRAFT_CLAIM_ISSUER_OR_UNIT_CONFLICT", index, "claim_key")
        if rule is None:
            rule = ClaimRule(key, identifiers["issuer_family"], "operator_declared_quantity",
                             "value", identifiers["unit"], "Claim "+key)
            rules[key] = rule
        if len(rules) > 12: _fail("DRAFT_RULE_LIMIT_12")
        fields = {"issuer_family": rule.issuer_family, "claim_type": rule.claim_type,
                  rule.value_field: value}
        day_fields = {}
        if clock_type == "precise":
            issue = _clock(raw["issued_at"], index, "issued_at")
            day_fields["claimed_issue_utc"] = iso(issue)
        else:
            issue = None
            offset = raw["utc_offset_minutes"]
            if type(offset) is not int or not -720 <= offset <= 840 or offset % 15:
                _fail("DRAFT_EXPLICIT_UTC_OFFSET_REQUIRED", index, "utc_offset_minutes")
            try:
                day = date.fromisoformat(raw["local_day"])
                if day.isoformat() != raw["local_day"]: raise ValueError()
                cutoff = datetime.combine(day+timedelta(days=1), time.min,
                                          timezone(timedelta(minutes=offset))).astimezone(timezone.utc)
            except (ValueError, TypeError, OverflowError): _fail("DRAFT_LOCAL_DAY_INVALID", index, "local_day")
            day_fields.update(displayed_local_day=day.isoformat(),
                              curator_not_before_utc=iso(cutoff), local_utc_offset_minutes=offset)
            fields["displayed_date_local"] = day.isoformat()
        digest = sha256(excerpt.encode("utf-8")).hexdigest()
        rows.append(SourceRecord(
            sid, kind, locator, publisher, excerpt, excerpt, digest, issue, None,
            issue, None, None, quality, "operator-declared", ["operator-declared"],
            [], "operator-declared", observation_fields=fields))
        pins[sid] = SourcePin(sid, locator, publisher, digest, rule.issuer_family, key,
                              value, kind, quality, **day_fields)
    return rows, pins


def _preview(pack, report):
    rows, pins, rules = _parse_case(pack)
    prepared = _validate_pins(rows, pins, rules)
    admitted = set(report["resilience"]["withdrawal_candidate_source_ids"])
    return [{"source_id": row.source_id, "publisher": row.publisher, "locator": row.locator,
             "claim_key": pins[row.source_id].claim_key,
             "declared_value": pins[row.source_id].expected_value,
             "unit": prepared[row.source_id][0].unit,
             "excerpt": row.excerpt, "fictional": row.record_kind == RecordKind.SYNTHETIC_CAPACITY,
             "admission_clock_utc": iso(prepared[row.source_id][1]),
             "clock_basis": prepared[row.source_id][2],
             "admitted_at_requested_policy": row.source_id in admitted} for row in rows]


def prepare_case_draft(raw, *, strict=False, search_depth=2):
    _bounded(raw)
    if not isinstance(raw, dict) or set(raw) != {"case_id", "title", "question", "as_of_utc", "sources"}:
        _fail("DRAFT_CASE_FIELDS_REFUSED")
    case_id = _string(raw["case_id"], None, "case_id", 80)
    title = _string(raw["title"], None, "title", 160)
    question = _string(raw["question"], None, "question", 1000)
    clock = iso(_clock(raw["as_of_utc"]))
    rules = {}
    rows, pins = _entries(raw["sources"], rules)
    pack = make_case_pack(case_id, title, question, clock, rows, pins, list(rules.values()))
    report = _investigate(pack, strict=strict, search_depth=search_depth)
    return {"kind": "EVIDENCETRAIL_CASE_DRAFT_PREVIEW_V1", "case_pack": pack,
            "investigation": report, "preview_sources": _preview(pack, report),
            "pin_origin": PIN_ORIGIN, "external_source_authentication_performed": False,
            "model_or_sponsor_called": False,
            "notice": "Pins and hashes were generated from your entries. Review the values and clocks; "
                      "no source was fetched or independently verified."}


def append_case_evidence(pack, entries, *, as_of_utc=None, strict=False, search_depth=2):
    _bounded(entries)
    before = _investigate(pack, as_of_utc=as_of_utc, strict=strict, search_depth=search_depth)
    rules = {raw["key"]: ClaimRule(**raw) for raw in pack["rules"]}
    rows, pins = _entries(entries, rules)
    for index, row in enumerate(rows, 1):
        if row.source_id in {p["source_id"] for p in pack["pins"]}:
            _fail("DRAFT_ADDITION_MUST_HAVE_NEW_SOURCE_ID", index, "source_id")
    augmented = deepcopy(pack)
    augmented["sources"].extend(row.to_public_dict() for row in rows)
    augmented["pins"].extend(asdict(pin) for pin in pins.values())
    augmented["rules"] = [asdict(rule) for rule in rules.values()]
    clock = before["why"]["as_of_utc"]
    after = _investigate(augmented, as_of_utc=clock, strict=strict, search_depth=search_depth)
    was, now = before["why"]["selected_claims"], after["why"]["selected_claims"]
    ids = sorted(pins)
    return {"kind": "EVIDENCETRAIL_OPERATOR_EVIDENCE_UPDATE_V1", "case_pack": augmented,
            "before": before, "after": after, "new_source_ids": ids,
            "new_admitted_source_ids": sorted(set(ids) & set(after["resilience"]["withdrawal_candidate_source_ids"])),
            "preview_sources": _preview(augmented, after)[len(pack["sources"]):],
            "comparison": {"changed_claims": _changes(was, now),
                           "value_or_availability_changed": any(
                               _value_signature(was.get(key)) != _value_signature(now.get(key))
                               for key in set(was) | set(now)),
                           "as_of_utc": clock, "policy": before["why"]["policy"]},
            "evidence_update_origin": UPDATE_ORIGIN, "new_pin_origin": PIN_ORIGIN,
            "external_source_authentication_performed": False, "model_or_sponsor_called": False,
            "execution_trace": [
                {"action": "VALIDATE_UNCHANGED_ORIGINAL_BATCH", "source_count": len(pack["sources"])},
                {"action": "PREPARE_OPERATOR_ADDITION", "new_source_ids": ids},
                {"action": "VALIDATE_FULL_AUGMENTED_BATCH", "source_count": len(augmented["sources"])},
                {"action": "REPLAY_SAME_CLOCK_AND_POLICY", "as_of_utc": clock,
                 "policy": before["why"]["policy"]},
                {"action": "COMPARE_SELECTED_CLAIMS", "changed_claim_count": len(_changes(was, now))}],
            "notice": "Operator added evidence; no autonomous collection, SQL or model request occurred."}
