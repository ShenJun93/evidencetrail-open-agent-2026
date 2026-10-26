"""Fail-closed initial catalog independence and conflicting-plan admission gate.

Applies to the ENTIRE initially retrieved batch, including future and
geographically out-of-scope rows. Otherwise filtering can hide a second
version of an originally ambiguous piece of evidence.

This is a deterministic data-integrity gate, not verification of publisher
identity, original publication date, or source truth.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256

from evidencetrail.models import RecordKind, RunRequest, SourceRecord


def _collisions(rows: list[SourceRecord], attr: str, code: str) -> list[dict]:
    groups: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        key = getattr(row, attr)
        if not isinstance(key, str) or not key.strip():
            # Handled separately as a malformed/empty identity field.
            continue
        # Empty provenance identifiers are not independent corroboration.
        groups[key].add(row.source_id)
        counts[key] += 1
    return [
        {"code": code, "source_ids": sorted(groups[key])}
        for key in sorted(groups)
        if counts[key] > 1
    ]


def _overlap(a: SourceRecord, b: SourceRecord) -> bool:
    left = {d.strip().casefold() for d in a.named_districts_2024}
    right = {d.strip().casefold() for d in b.named_districts_2024}
    # An unnamed plan cannot establish it is disjoint from a named one.
    return not left or not right or bool(left & right)


def initial_source_integrity_issues(
    rows: list[SourceRecord],
    request: RunRequest,
) -> list[dict]:
    """Report ambiguity without selecting a convenient row or order.

    A shared URL or exact excerpt fingerprint under multiple IDs is a SOURCE
    ALIAS, not a second independent witness. Two synthetic plans for the
    requested scenario covering an overlapping 2024 district are ambiguous
    inputs for a reducer that would otherwise use the first capacity record.
    """
    issues: list[dict] = []
    for row in rows:
        fields = (row.source_id, row.locator, row.excerpt_sha256, row.excerpt)
        if not all(isinstance(x, str) and x.strip() for x in fields):
            issues.append({
                "code": "SOURCE_IDENTITY_FIELD_INVALID_REFUSED",
                "source_ids": [str(row.source_id)[:64]],
            })
            continue
        # A hash copied from a different article cannot become verified
        # citation provenance just because the model and Auditor agree on it.
        if sha256(row.excerpt.encode("utf-8")).hexdigest() != row.excerpt_sha256:
            issues.append({
                "code": "SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED",
                "source_ids": [row.source_id],
            })
    issues.extend(_collisions(rows, "source_id", "DUPLICATE_SOURCE_ID_REFUSED"))
    issues.extend(_collisions(rows, "locator", "SOURCE_LOCATOR_ALIAS_REFUSED"))
    issues.extend(_collisions(rows, "excerpt_sha256", "SOURCE_EXCERPT_ALIAS_REFUSED"))

    plans = sorted(
        [
            row for row in rows
            if row.record_kind == RecordKind.SYNTHETIC_CAPACITY
            and row.scenario_id == request.scenario_id
        ],
        key=lambda row: row.source_id,
    )
    for idx, a in enumerate(plans):
        for b in plans[idx + 1:]:
            if _overlap(a, b):
                issues.append({
                    "code": "AMBIGUOUS_SCENARIO_CAPACITY_REFUSED",
                    "source_ids": sorted([a.source_id, b.source_id]),
                })
    issues.sort(key=lambda x: (
        ["SOURCE_IDENTITY_FIELD_INVALID_REFUSED",
         "SOURCE_EXCERPT_DIGEST_MISMATCH_REFUSED",
         "DUPLICATE_SOURCE_ID_REFUSED", "SOURCE_LOCATOR_ALIAS_REFUSED",
         "SOURCE_EXCERPT_ALIAS_REFUSED",
         "AMBIGUOUS_SCENARIO_CAPACITY_REFUSED"].index(x["code"]),
        x["source_ids"],
    ))
    return issues
def matching_scenario_capacities(
    request: RunRequest, eligible: list[SourceRecord],
) -> list[SourceRecord]:
    """Choose only this scenario's target district, independent of SQL row order."""
    return [
        row for row in eligible
        if row.record_kind == RecordKind.SYNTHETIC_CAPACITY
        and row.scenario_id == request.scenario_id
        and (
            request.granularity != "district"
            or not request.district_2024
            or request.district_2024.casefold()
            in {name.casefold() for name in row.named_districts_2024}
        )
    ]
