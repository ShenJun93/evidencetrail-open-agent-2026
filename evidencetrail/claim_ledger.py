"""Reusable, bounded source-pinned claim ledger for historical evidence.

Not an NLP entailment checker, archive attestation or current warning service.
A separately curated manifest pins source identity, excerpts, claim values and
the *admission policy clock*. Never infer public availability from file names,
article URLs, retrieval times, model replies, or observation timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import re
from typing import Mapping

from evidencetrail.models import (
    ProvenanceQuality, RecordKind, ReplayMode, SourceRecord, iso, parse_iso
)

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}\Z")
_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9_ /().-]{0,95}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_SOURCES = 80
_MAX_RULES = 12


class ClaimLedgerRefusal(ValueError):
    """Stable, safe, non-secret error code (never arbitrary source text)."""


@dataclass(frozen=True)
class ClaimRule:
    key: str
    issuer_family: str
    claim_type: str
    value_field: str
    unit: str
    label: str

    def validate(self):
        for value in (self.key, self.issuer_family, self.claim_type,
                      self.value_field, self.unit):
            if not isinstance(value, str) or not _NAME.fullmatch(value):
                raise ClaimLedgerRefusal("CLAIM_RULE_IDENTIFIER_INVALID")
        if not isinstance(self.label, str) or not _LABEL.fullmatch(self.label):
            raise ClaimLedgerRefusal("CLAIM_RULE_LABEL_INVALID")


@dataclass(frozen=True)
class SourcePin:
    """Operator-curated, source-specific expectations — NOT an external signature.

    Date-only items require a separately declared conservative not-before UTC
    instant, and must NOT carry a fabricated precise issue timestamp.
    """
    source_id: str
    locator: str
    publisher: str
    excerpt_sha256: str
    issuer_family: str
    claim_key: str
    expected_value: int
    record_kind: RecordKind
    provenance_quality: ProvenanceQuality
    claimed_issue_utc: str | None = None
    displayed_local_day: str | None = None
    curator_not_before_utc: str | None = None
    local_utc_offset_minutes: int | None = None


def _clock(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ClaimLedgerRefusal("PIN_CLOCK_NOT_STRING")
    try:
        dt = parse_iso(value)
    except (ValueError, TypeError, OverflowError):
        raise ClaimLedgerRefusal("PIN_CLOCK_INVALID_UTC") from None
    if dt is None:
        raise ClaimLedgerRefusal("PIN_CLOCK_INVALID_UTC")
    return dt


def _validate_pins(rows: list[SourceRecord], pins: Mapping[str, SourcePin],
                   rules: list[ClaimRule]) -> dict[str, tuple[ClaimRule, datetime, str]]:
    if not isinstance(rows, list) or not (1 <= len(rows) <= _MAX_SOURCES):
        raise ClaimLedgerRefusal("SOURCE_BATCH_SIZE_INVALID")
    if not isinstance(pins, Mapping) or set(pins) != {
        r.source_id for r in rows
    } or len(pins) != len(rows):
        raise ClaimLedgerRefusal("SOURCE_MANIFEST_COVERAGE_REFUSED")
    if not isinstance(rules, list) or not (1 <= len(rules) <= _MAX_RULES):
        raise ClaimLedgerRefusal("CLAIM_RULES_INVALID")
    for rule in rules:
        if not isinstance(rule, ClaimRule):
            raise ClaimLedgerRefusal("CLAIM_RULE_TYPE_INVALID")
        rule.validate()
    if len({r.key for r in rules}) != len(rules):
        raise ClaimLedgerRefusal("CLAIM_RULE_KEY_ALIAS")
    rules_by_key = {r.key: r for r in rules}
    ids, urls, excerpts = set(), set(), set()
    prepared = {}
    for row in rows:
        if not isinstance(row, SourceRecord):
            raise ClaimLedgerRefusal("SOURCE_ROW_TYPE_INVALID")
        if not isinstance(row.source_id,str) or not _NAME.fullmatch(row.source_id):
            raise ClaimLedgerRefusal("SOURCE_ID_SYNTAX_REFUSED")
        p = pins.get(row.source_id)
        if not isinstance(p, SourcePin):
            raise ClaimLedgerRefusal("PIN_TYPE_INVALID")
        for s, val in ((ids, row.source_id), (urls, row.locator),
                       (excerpts, row.excerpt_sha256)):
            if not isinstance(val, str) or not val.strip() or val in s:
                raise ClaimLedgerRefusal("SOURCE_IDENTITY_ALIAS_REFUSED")
            s.add(val)
        if (not isinstance(row.excerpt, str) or not row.excerpt.strip()
                or len(row.excerpt.encode("utf-8")) > 16384
                or not isinstance(row.excerpt_sha256, str)
                or not _SHA.fullmatch(row.excerpt_sha256)
                or sha256(row.excerpt.encode("utf-8")).hexdigest()
                   != row.excerpt_sha256):
            raise ClaimLedgerRefusal("SOURCE_EXCERPT_DIGEST_REFUSED")
        if (p.source_id != row.source_id
                or p.locator != row.locator
                or p.publisher != row.publisher
                or p.excerpt_sha256 != row.excerpt_sha256
                or p.record_kind != row.record_kind
                or p.provenance_quality != row.provenance_quality):
            raise ClaimLedgerRefusal("PINNED_SOURCE_IDENTITY_MISMATCH")
        if (p.record_kind not in (RecordKind.GOVERNMENT_NEWS,
                                  RecordKind.SYNTHETIC_CAPACITY)
                or (p.record_kind == RecordKind.SYNTHETIC_CAPACITY)
                   != (p.provenance_quality == ProvenanceQuality.SYNTHETIC)):
            raise ClaimLedgerRefusal("SOURCE_KIND_PROVENANCE_CONFLICT")
        if (not isinstance(p.locator, str) or
                not p.locator.startswith(("https://", "synthetic://"))):
            raise ClaimLedgerRefusal("PIN_URL_SCHEME_REFUSED")
        rule = rules_by_key.get(p.claim_key)
        if rule is None or p.issuer_family != rule.issuer_family:
            raise ClaimLedgerRefusal("PIN_ISSUER_OR_CLAIM_UNREGISTERED")
        fields = row.observation_fields
        if not isinstance(fields, dict):
            raise ClaimLedgerRefusal("SOURCE_CLAIM_FIELDS_INVALID")
        if (fields.get("issuer_family") != p.issuer_family
                or fields.get("claim_type") != rule.claim_type
                or type(fields.get(rule.value_field)) is not int
                or type(p.expected_value) is not int
                or not (0 <= p.expected_value <= 100000000)
                or fields[rule.value_field] != p.expected_value):
            raise ClaimLedgerRefusal("SOURCE_CLAIM_VALUE_OR_TYPE_MISMATCH")
        precise = _clock(p.claimed_issue_utc)
        day_bound = _clock(p.curator_not_before_utc)
        if precise is not None and (p.displayed_local_day is not None
                                    or day_bound is not None
                                    or p.local_utc_offset_minutes is not None):
            raise ClaimLedgerRefusal("SOURCE_CLOCK_PRECISION_CONFLICT")
        if precise is None:
            if (p.displayed_local_day is None or day_bound is None
                    or row.issued_at_claimed_utc is not None
                    or row.published_at_displayed_utc is not None
                    or fields.get("displayed_date_local") != p.displayed_local_day):
                raise ClaimLedgerRefusal("SOURCE_DATE_ONLY_BOUND_MISSING")
            try:
                local_date = date.fromisoformat(p.displayed_local_day)
            except (TypeError, ValueError):
                raise ClaimLedgerRefusal("SOURCE_LOCAL_DATE_INVALID") from None
            minutes = p.local_utc_offset_minutes
            if (type(minutes) is not int or not -720 <= minutes <= 840
                    or minutes % 15):
                raise ClaimLedgerRefusal("SOURCE_LOCAL_UTC_OFFSET_REQUIRED")
            # Date-specific explicit offset; no guessed publication hour.
            # Wait until *all* of the printed local date has elapsed.
            min_gate = datetime.combine(
                local_date + timedelta(days=1), time.min,
                tzinfo=timezone(timedelta(minutes=minutes))
            ).astimezone(timezone.utc)
            if day_bound < min_gate:
                raise ClaimLedgerRefusal("SOURCE_DATE_ONLY_GATE_PREMATURE")
            basis = "CURATOR_DATE_ONLY_NOT_BEFORE_UTC_NOT_PUBLISHER_CLOCK"
            gate = day_bound
        else:
            if (row.issued_at_claimed_utc != precise
                    or row.published_at_displayed_utc != precise):
                raise ClaimLedgerRefusal("SOURCE_CLAIMED_ISSUE_CLOCK_MISMATCH")
            basis = "REPORTED_ISSUER_CLOCK_NOT_FIRST_PUBLICATION"
            gate = precise
        if gate.tzinfo is None or gate.utcoffset() is None:
            raise ClaimLedgerRefusal("SOURCE_NAIVE_GATE_REFUSED")
        prepared[p.source_id] = (rule, gate, basis)
    return prepared


def evaluate_claim_ledger(
    rows: list[SourceRecord], pins: Mapping[str, SourcePin],
    rules: list[ClaimRule], *, as_of_utc: str,
    mode: ReplayMode = ReplayMode.REPORTED_DATELINE_REPLAY,
) -> dict:
    """Case-independent explainable claim selection with fail-closed manifest.

    All rows and pins are validated BEFORE any as-of selection, so a future
    duplicate excerpt/ID cannot be hidden by filtering. Strict historical
    mode intentionally abstains until an external authenticated snapshot
    verifier exists; a self-declared quality enum is not archive proof.
    """
    if not isinstance(mode, ReplayMode):
        raise ClaimLedgerRefusal("LEDGER_MODE_INVALID")
    at = _clock(as_of_utc)
    if at is None:
        raise ClaimLedgerRefusal("LEDGER_AS_OF_REQUIRED")
    prepared = _validate_pins(rows, pins, rules)
    eligible: dict[str, list[tuple[datetime, SourceRecord, ClaimRule, str]]] = {}
    excluded = []
    for row in rows:
        rule, gate, basis = prepared[row.source_id]
        if mode == ReplayMode.STRICT_AS_OF_2024:
            reason = "STRICT_ORIGINAL_FIRST_AVAILABILITY_NOT_EXTERNALLY_ATTESTED"
        elif gate > at:
            reason = "POLICY_ISSUE_OR_DATE_BOUND_AFTER_AS_OF"
        else:
            reason = None
        if reason:
            excluded.append({"source_id": row.source_id, "reason": reason})
        else:
            eligible.setdefault(rule.key, []).append((gate, row, rule, basis))
    claims = []
    conflicts = []
    for rule in rules:
        pool = eligible.get(rule.key, [])
        if not pool:
            continue
        latest_gate = max(item[0] for item in pool)
        latest = [item for item in pool if item[0] == latest_gate]
        # An ID is not a revision number or an authority ranking. Date-only
        # sources can share a conservative gate without a known issue order.
        # Never resolve incompatible latest values by lexical ID or fall back
        # to an older, conveniently unambiguous value.
        if len({item[1].observation_fields[rule.value_field]
                for item in latest}) > 1:
            conflicts.append({
                "claim_key": rule.key,
                "reason": "CONFLICTING_LATEST_PINNED_VALUES",
                "policy_admissible_after_utc": iso(latest_gate),
                "source_ids": sorted(item[1].source_id for item in latest),
            })
            continue
        gate, row, _, basis = max(latest, key=lambda item: item[1].source_id)
        claim = {
            "claim_key": rule.key, "claim_type": rule.claim_type,
            "issuer_family": rule.issuer_family, "source_id": row.source_id,
            "source_url": row.locator, "source_excerpt_sha256":row.excerpt_sha256,
            "value": row.observation_fields[rule.value_field], "unit":rule.unit,
            "policy_admissible_after_utc": iso(gate), "clock_basis":basis,
            "curated_source_metadata_not_original_bytes":True,
            "original_first_publication_authenticated":False,
            "fictional": row.record_kind == RecordKind.SYNTHETIC_CAPACITY,
        }
        claims.append(claim)
    # Fully deterministic explanation; never echo excerpts, operator data,
    # model free-text, HTML markup, or claims from excluded future sources.
    if claims:
        summary = "; ".join(
            c["claim_key"] + " = " + str(c["value"]) + " " + c["unit"] +
            " (" + c["source_id"] + ", " + c["clock_basis"] + ")" +
            (" [FICTIONAL]" if c["fictional"] else "")
            for c in claims
        )
    else:
        summary = "No source-pinned claims admitted at this as-of time"
    if conflicts:
        summary += "; Abstained on conflicting latest sources for: " + ", ".join(
            item["claim_key"] for item in conflicts)
    return {
        "kind":"EVIDENCETRAIL_CASE_INDEPENDENT_CLAIM_LEDGER_V1",
        "status": ("PARTIAL_CLAIMS_WITH_CONFLICTS" if claims and conflicts else
                   "ABSTAIN_CONFLICTING_CLAIMS" if conflicts else
                   "CLAIMS_SELECTED" if claims else "ABSTAIN_NO_ADMISSIBLE_CLAIMS"),
        "as_of_utc":iso(at), "mode":mode.value,
        "examined_source_count":len(rows),
        "selected_source_count":len(claims),
        "source_ids_eligible":sorted(
            r.source_id for r in rows
            if not any(e["source_id"]==r.source_id for e in excluded)
        ),
        "excluded":sorted(excluded,key=lambda e:e["source_id"]),
        "typed_claims":claims,
        "unresolved_claim_conflicts":conflicts,
        "trusted_template_explanation":(
            "As of "+iso(at)+": "+summary+
            ". Source metadata and excerpts are curator-pinned, not "
            "independently authenticated original publisher bytes. "
            "Original first-publication availability is not established. "
            "Historical research only; NOT an operational advisory."
        ),
        "issuer_independence_count":len({
            c["issuer_family"] for c in claims
            if not c["fictional"]
        }),
        "issuer_family_count_is_not_independent_corroboration_proof":True,
        "attested_original_publication":False,
        "independent_source_fact_check":False,
        "operator_curated_manifest_is_not_independent_proof":True,
        "model_or_sponsor_called":False,
        "independent_human_outcomes_measured":False,
        "general_natural_language_entailment_proven":False,
    }
