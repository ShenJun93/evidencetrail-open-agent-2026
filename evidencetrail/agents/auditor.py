from __future__ import annotations

from evidencetrail.citation import CitationVerifier
from evidencetrail.firewall import availability_reason
from evidencetrail.models import AuditResult, DecisionDraft, RunRequest, SourceRecord
from evidencetrail.traces import JsonlTrace


class EvidenceAuditorAgent:
    name = "EvidenceAuditorAgent"

    def __init__(self, trace: JsonlTrace):
        self.trace = trace
        self.verifier = CitationVerifier()

    def run(
        self,
        request: RunRequest,
        eligible: list[SourceRecord],
        draft: DecisionDraft,
        collector_ids: list[str],
    ) -> AuditResult:
        blocked: list[str] = []
        hints: list[str] = []
        verified, cite_blocks = self.verifier.verify(draft.citations, eligible, collector_ids)
        blocked.extend(cite_blocks)
        for src in eligible:
            reason = availability_reason(src, request.as_of_utc, request.mode)
            if reason:
                blocked.append(f"eligible_set_contains_future_or_invalid:{src.source_id}:{reason}")
        if request.granularity == "district" and draft.nominated_verdict.value == "WARN":
            named = any(
                request.district_2024 and request.district_2024.lower() in [d.lower() for d in s.named_districts_2024]
                for s in eligible
            )
            if not named:
                blocked.append("WARN_without_district_named_source")
                hints.append("requery_public_sources_for_named_district_at_as_of")
        # A valid abstention may still request a narrowly scoped second query.
        # This is a REAL requery hint, not a second call to the same reducer.
        if request.granularity == "district" and any(
            "public source naming district" in item for item in draft.missing_facts
        ):
            hints.append("requery_public_sources_for_named_district_at_as_of")
        hints = list(dict.fromkeys(hints))
        accepted = not blocked
        self.trace.emit(
            "CRITIQUE",
            "independent_citation_and_chronology_audit",
            "ok" if accepted else "block",
            blocked=blocked,
            verified=[c.source_id for c in verified],
            hints=hints,
        )
        return AuditResult(
            accepted=accepted,
            blocked_reasons=blocked,
            requery_hints=hints,
            verified_citations=verified,
        )
