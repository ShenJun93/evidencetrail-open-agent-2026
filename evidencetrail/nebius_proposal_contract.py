"""Nebius research proposal verifier. Pure, strict and non-disclosing.

Vendor-produced text is never a historical source. This module returns only
validated structured data or a FIXED diagnostic enum. Exception strings carry
NO output snippets, source IDs, key values, prompts or model text.
"""
from __future__ import annotations

import json
from typing import Any

from evidencetrail.models import RunRequest, SourceRecord, Verdict

# Fixed public-safe diagnostic codes. Do not put model-generated text here.
DIAGNOSTIC_CODES = frozenset({
    "JSON_TEXT_MISSING",
    "JSON_TEXT_TOO_LONG",
    "JSON_NESTING_LIMIT_EXCEEDED",
    "JSON_SYNTAX_INVALID",
    "JSON_DUPLICATE_KEY",
    "JSON_NONFINITE_CONSTANT",
    "JSON_OBJECT_REQUIRED",
    "JSON_FIELDS_MISMATCH",
    "JSON_VERDICT_INVALID",
    "JSON_RATIONALE_INVALID",
    "JSON_CITATIONS_SHAPE_INVALID",
    "CITATION_NOT_TIME_ELIGIBLE",
    "WARN_PUBLIC_DISTRICT_WITNESS_MISSING",
    "WARN_FICTIONAL_CAPACITY_WITNESS_MISSING",
})


class NebiusProposalViolation(ValueError):
    def __init__(self, code: str):
        if code not in DIAGNOSTIC_CODES:
            raise ValueError("UNRECOGNIZED_DIAGNOSTIC_CODE")
        self.code = code
        super().__init__(code)


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NebiusProposalViolation("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> Any:
    del value
    raise NebiusProposalViolation("JSON_NONFINITE_CONSTANT")


MAX_JSON_CHARS = 20000
MAX_JSON_DEPTH = 64


def _guard_json_complexity(text: str) -> None:
    """Bound nesting without parsing and never examine braces inside JSON strings.

    Python versions may differ in how deeply nested JSON is handled.
    The guard provides a stable fail-closed category BEFORE json.loads().
    """
    if len(text) > MAX_JSON_CHARS:
        raise NebiusProposalViolation("JSON_TEXT_TOO_LONG")
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise NebiusProposalViolation("JSON_NESTING_LIMIT_EXCEEDED")
        elif char in "]}":
            depth -= 1
            # json.loads remains authoritative for bracket matching.
            if depth < 0:
                break


def validate_nebius_proposal(
    text: str | None, request: RunRequest,
    eligible: list[SourceRecord], allowed_verdict: Verdict,
) -> dict[str, Any]:
    """Enforce exact JSON shape, time-eligible citations and both WARN witnesses.

    The returned model rationale is NEVER used as historic evidence or as the
    reducer's authoritative rationale; the model may only agree or veto.
    """
    if not isinstance(text, str) or not text.strip():
        raise NebiusProposalViolation("JSON_TEXT_MISSING")
    _guard_json_complexity(text)
    try:
        parsed = json.loads(
            text, object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except NebiusProposalViolation:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise NebiusProposalViolation("JSON_SYNTAX_INVALID") from None

    if not isinstance(parsed, dict):
        raise NebiusProposalViolation("JSON_OBJECT_REQUIRED")
    if set(parsed) != {"proposed_verdict", "rationale", "source_ids"}:
        raise NebiusProposalViolation("JSON_FIELDS_MISMATCH")

    verdict = parsed["proposed_verdict"]
    if not isinstance(verdict, str) or verdict not in {v.value for v in Verdict}:
        raise NebiusProposalViolation("JSON_VERDICT_INVALID")

    rationale = parsed["rationale"]
    if not isinstance(rationale, str) or not 1 <= len(rationale.strip()) <= 1200:
        raise NebiusProposalViolation("JSON_RATIONALE_INVALID")

    citations = parsed["source_ids"]
    if (not isinstance(citations, list)
        or len(citations) > 20
        or any(not isinstance(sid, str) for sid in citations)):
        raise NebiusProposalViolation("JSON_CITATIONS_SHAPE_INVALID")

    eligible_ids = {src.source_id for src in eligible}
    if any(sid not in eligible_ids for sid in citations):
        raise NebiusProposalViolation("CITATION_NOT_TIME_ELIGIBLE")

    if allowed_verdict == Verdict.WARN:
        ids = set(citations)
        has_public = (
            request.district_2024 is not None and any(
                src.source_id in ids
                and src.record_kind.value == "GOVERNMENT_NEWS"
                and request.district_2024.casefold() in {
                    district.casefold()
                    for district in src.named_districts_2024
                }
                for src in eligible
            )
        )
        if not has_public:
            raise NebiusProposalViolation("WARN_PUBLIC_DISTRICT_WITNESS_MISSING")
        if not any(
            src.source_id in ids
            and src.record_kind.value == "SYNTHETIC_CAPACITY"
            and src.scenario_id == request.scenario_id
            for src in eligible
        ):
            raise NebiusProposalViolation("WARN_FICTIONAL_CAPACITY_WITNESS_MISSING")

    return parsed
