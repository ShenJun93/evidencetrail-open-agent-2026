from __future__ import annotations

from evidencetrail.adapters.hmem import HMemAdapter
from evidencetrail.evidence_integrity import initial_source_integrity_issues
from evidencetrail.adapters.zetaris import ZetarisAdapter
from evidencetrail.firewall import filter_memories, filter_sources, jurisdiction_ok
from evidencetrail.models import RunRequest, SourceRecord
from evidencetrail.traces import JsonlTrace, digest


class EvidenceCollectorAgent:
    name = "EvidenceCollectorAgent"

    def __init__(self, zetaris: ZetarisAdapter, hmem: HMemAdapter, trace: JsonlTrace):
        self.zetaris = zetaris
        self.hmem = hmem
        self.trace = trace

    def _safe_memory(self, request: RunRequest, eligible: list[SourceRecord]) -> tuple[list, list]:
        raw = self.hmem.query(request.question)
        kept, dropped = filter_memories(
            raw.get("hits") or [], request.mission_id, request.as_of_utc,
            {s.source_id for s in eligible}, scenario_id=request.scenario_id,
        )
        self.trace.emit(
            "FETCH", "hmem_query_and_postfilter", "ok",
            raw_hits=len(raw.get("hits") or []), kept=len(kept), dropped=dropped,
            disclaimer=raw.get("disclaimer"),
        )
        return kept, dropped

    def run(self, request: RunRequest) -> dict:
        rows, sponsor_calls = self.zetaris.fetch_two_logical_sources()
        # A second ID/URL is not proof of independent corroboration.
        # Check the FULL initial batch before time or geography filters hide
        # a future twin, and refuse overlapping synthetic capacity plans.
        issues = initial_source_integrity_issues(rows, request)
        if issues:
            if any(x["code"] == "DUPLICATE_SOURCE_ID_REFUSED" for x in issues):
                self.trace.emit(
                    "FETCH", "duplicate_initial_source_ids", "blocked",
                    conflicting_ids=sorted(set(
                        sid for x in issues
                        if x["code"] == "DUPLICATE_SOURCE_ID_REFUSED"
                        for sid in x["source_ids"]
                    )), row_count=len(rows),
                    reason="ambiguous source identity; no record can be trusted",
                )
            self.trace.emit(
                "FETCH", "initial_source_independence_gate", "blocked",
                issues=issues, row_count=len(rows),
                reason="duplicated provenance or ambiguous scenario plan",
            )
        # Defence in depth: only TWO distinct, successful, correctly typed
        # data-source receipts count. Repeating a successful public query twice
        # must never masquerade as the separate capacity dataset.
        required_engines = {"query:government-news", "query:synthetic-capacity"}
        live_queries = [c for c in sponsor_calls if c.engine.startswith("query:")]
        by_engine = {c.engine: c for c in live_queries}
        fetched_kinds = {row.record_kind.value for row in rows}
        data_ready = not issues and (self.zetaris.sample_mode or (
            bool(rows) and len(live_queries) == 2
            and set(by_engine) == required_engines
            and all(c.outcome.value == "REAL_SUCCESS" for c in by_engine.values())
            and {"GOVERNMENT_NEWS", "SYNTHETIC_CAPACITY"} <= fetched_kinds
        ))
        self.trace.emit(
            "FETCH", "zetaris_two_logical_sources",
            "ok" if data_ready else "blocked",
            row_count=len(rows), sponsor=[c.to_dict() for c in sponsor_calls],
        )
        # A partial or failed LIVE sponsor fetch is not a usable source set.
        # Keep transport receipts but never decide with only one of two tables.
        if not data_ready:
            self.trace.emit(
                "FETCH", "incomplete_live_source_set_rejected", "blocked",
                reason=(
                    "initial_source_integrity_refused" if issues
                    else "both authenticated logical source queries required"
                ),
            )
            rows = []
        in_scope = [r for r in rows if jurisdiction_ok(r, request.province_2024, request.district_2024)]
        eligible, excluded = filter_sources(in_scope, request.as_of_utc, request.mode)
        self.trace.emit(
            "NORMALIZE", "as_of_firewall_before_memory", "ok",
            eligible=[s.source_id for s in eligible], excluded=excluded,
        )
        kept, dropped = self._safe_memory(request, eligible)
        state = {
            "eligible": eligible, "excluded": excluded,
            "memories": kept, "dropped_memories": dropped,
            "sponsor_calls": sponsor_calls,
            "catalog_ids": [r.source_id for r in rows],
            "catalog_hashes": {r.source_id: r.excerpt_sha256 for r in rows},
            "catalog_locators": {r.locator: r.source_id for r in rows},
            "data_ready": data_ready,
            "initial_integrity_issues": issues,
        }
        self.trace.emit(
            "HANDOFF", "collector_to_decision", "ok",
            digest=digest([s.source_id for s in eligible]),
            prior_memory_ids=[m.get("id") for m in kept],
        )
        return state

    def requery(self, request: RunRequest, state: dict, hints: list[str]) -> bool:
        """Genuine separate SQL attempt only; never claim a repeat-cache hit."""
        if not hints:
            return False
        if state.get("initial_integrity_issues"):
            self.trace.emit(
                "REPLAN_TARGETED", "initial_source_integrity_unresolved", "blocked",
                reason="cannot repair an ambiguous initial catalog by adding later sources",
                issues=state["initial_integrity_issues"],
            )
            return False
        if not self.zetaris.sample_mode and not state.get("data_ready", False):
            self.trace.emit(
                "REPLAN_TARGETED", "initial_two_source_contract_not_met", "blocked",
                hints=hints, reason="targeted public requery cannot replace missing base capacity",
            )
            return False
        fresh, receipt = self.zetaris.fetch_targeted_sources()
        state["sponsor_calls"].append(receipt)
        # A failing LIVE transport cannot introduce new evidence.
        if not self.zetaris.sample_mode and receipt.outcome.value != "REAL_SUCCESS":
            self.trace.emit(
                "REPLAN_TARGETED", "targeted_transport_not_verified", "blocked",
                hints=hints, sponsor=receipt.to_dict(),
            )
            return False
        # Track every originally seen source including FUTURE/EXCLUDED rows.
        # Requery must never rewrite the same ID to an earlier dateline.
        seen_hashes: dict[str, str] = state.setdefault(
            "catalog_hashes", {s.source_id: s.excerpt_sha256 for s in state["eligible"]}
        )
        seen_locators: dict[str, str] = state.setdefault("catalog_locators", {})
        seen_excerpt_hashes = set(seen_hashes.values())
        new_candidates: list[SourceRecord] = []
        conflicting: list[str] = []
        duplicate: list[str] = []
        aliased: list[str] = []
        wrong_kind: list[str] = []
        for row in fresh:
            if row.source_id in seen_hashes:
                duplicate.append(row.source_id)
                if seen_hashes[row.source_id] != row.excerpt_sha256:
                    conflicting.append(row.source_id)
                continue
            # New ID alone is not independent evidence: preserve stable URL
            # and exact excerpt fingerprints across the full initial catalog,
            # including withheld future items.
            if row.locator in seen_locators or row.excerpt_sha256 in seen_excerpt_hashes:
                aliased.append(row.source_id)
                continue
            if row.record_kind.value != "GOVERNMENT_NEWS":
                wrong_kind.append(row.source_id)
                continue
            seen_hashes[row.source_id] = row.excerpt_sha256
            seen_locators[row.locator] = row.source_id
            seen_excerpt_hashes.add(row.excerpt_sha256)
            if jurisdiction_ok(row, request.province_2024, request.district_2024):
                new_candidates.append(row)
        admissible, excluded = filter_sources(new_candidates, request.as_of_utc, request.mode)
        unique = []
        seen = {source.source_id for source in state["eligible"]}
        for row in admissible:
            if row.source_id not in seen:
                unique.append(row)
                seen.add(row.source_id)
        state["eligible"].extend(unique)
        state["excluded"].extend(excluded)
        state["catalog_ids"].extend(s.source_id for s in fresh if s.source_id not in state["catalog_ids"])
        state["memories"], state["dropped_memories"] = self._safe_memory(request, state["eligible"])
        self.trace.emit(
            "REPLAN_TARGETED", "zetaris_targeted_query",
            "ok" if unique else "no_new_admissible_evidence",
            hints=hints, new_source_ids=[s.source_id for s in unique],
            excluded=excluded, duplicate_prior_catalog_ids=duplicate,
            conflicting_source_versions=conflicting, aliased_prior_sources=aliased,
            wrong_record_kinds=wrong_kind,
            sponsor=receipt.to_dict(),
        )
        return bool(unique)
