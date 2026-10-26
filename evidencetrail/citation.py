from __future__ import annotations

from evidencetrail.models import Citation, SourceRecord


class CitationVerifier:
    """Independent of DecisionAgent. Model text cannot authorize a cite."""

    def verify(
        self,
        citations: list[Citation],
        eligible: list[SourceRecord],
        nominated_ids: list[str],
    ) -> tuple[list[Citation], list[str]]:
        by_id = {s.source_id: s for s in eligible}
        ok: list[Citation] = []
        blocked: list[str] = []
        for cite in citations:
            src = by_id.get(cite.source_id)
            if src is None:
                blocked.append(f"citation_not_in_eligible_set:{cite.source_id}")
                continue
            if cite.source_id not in nominated_ids:
                blocked.append(f"citation_not_on_collector_receipt:{cite.source_id}")
                continue
            if cite.excerpt_sha256 != src.excerpt_sha256:
                blocked.append(f"excerpt_hash_mismatch:{cite.source_id}")
                continue
            ok.append(cite)
        return ok, blocked
