from __future__ import annotations

import os
from pathlib import Path

from evidencetrail.adapters.hmem import HMemAdapter
from evidencetrail.adapters.meterless import live_status as meterless_live_status
from evidencetrail.adapters.zetaris import ZetarisAdapter
from evidencetrail.agents.auditor import EvidenceAuditorAgent
from evidencetrail.agents.collector import EvidenceCollectorAgent
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.models import (
    AgentHandoff,
    ReplayMode,
    RunRequest,
    RunResult,
    SponsorCall,
    SponsorOutcome,
    Verdict,
    iso,
)
from evidencetrail.traces import JsonlTrace, digest

DISCLAIMER = (
    "RESEARCH-ONLY simulated triage. Not public hazard guidance, not a 2024 warning system, "
    "and not proof of historical first-availability of web pages. Displayed datelines have "
    "unknown edit history. 2024 Yen Bai is not 2026 Lao Cai."
)


class EvidenceTrailPipeline:
    def __init__(
        self,
        sample_mode: bool = True,
        persist_dir: str | Path | None = None,
        log_dir: str | Path = "logs",
        catalog_override=None,
    ):
        self.sample_mode = sample_mode
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.zetaris = ZetarisAdapter(sample_mode=sample_mode)
        if catalog_override is not None and not sample_mode:
            raise ValueError("catalog_override cannot masquerade as live Zetaris data")
        if catalog_override is not None:
            self.zetaris.fetch_two_logical_sources = lambda: (  # type: ignore[method-assign]
                catalog_override,
                [
                    SponsorCall(
                        provider="zetaris",
                        engine="catalog-override",
                        outcome=SponsorOutcome.SAMPLE_CACHE,
                        detail="test catalog override",
                        row_count=len(catalog_override),
                    )
                ],
            )
        self.hmem = HMemAdapter(persist_dir=persist_dir, sample_mode=sample_mode)

    def run(self, request: RunRequest) -> RunResult:
        # Pipeline mode is authoritative; untrusted API input cannot switch
        # an offline server into live cloud/service calls.
        request.sample_mode = self.sample_mode
        trace_path = self.log_dir / f"trace-{request.run_id}.jsonl"
        trace = JsonlTrace(trace_path, request.run_id)
        trace.emit("INIT", "run_start", "ok", input=request.to_dict(), sample_mode=self.sample_mode)
        collector = EvidenceCollectorAgent(self.zetaris, self.hmem, trace)
        decision_agent = DecisionAgent(trace)
        auditor = EvidenceAuditorAgent(trace)

        state = collector.run(request)
        handoffs = [
            AgentHandoff(
                from_agent=collector.name,
                to_agent=decision_agent.name,
                shared_state_digest=digest([s.source_id for s in state["eligible"]]),
                notes=["as-of firewall applied; cross-scenario H-MEM filtered"],
            )
        ]
        draft = decision_agent.run(request, state["eligible"], state["memories"])
        audit = auditor.run(
            request, state["eligible"], draft,
            [s.source_id for s in state["eligible"]],
        )
        handoffs.append(
            AgentHandoff(
                from_agent=decision_agent.name,
                to_agent=auditor.name,
                shared_state_digest=digest([c.source_id for c in draft.citations]),
                notes=["independent citation verifier; model cannot self-certify"],
            )
        )

        # Genuine retry requires a new Zetaris SELECT with NEW admissible rows.
        # In SAMPLE_MODE there is no external query, so we log the attempted
        # critique and stop; repeating the same reducer is not collaboration.
        retry_limit = min(max(request.max_retries, 0), 2)
        for attempt in range(1, retry_limit + 1):
            if audit.accepted and not audit.requery_hints:
                break
            hints = audit.requery_hints
            handoffs.append(AgentHandoff(
                from_agent=auditor.name,
                to_agent=collector.name,
                shared_state_digest=digest(hints),
                notes=["auditor requested a targeted second evidence query"],
            ))
            trace.emit(
                "REPLAN_TARGETED", "auditor_requery", "requested",
                attempt=attempt, hints=hints, original_blocks=audit.blocked_reasons,
            )
            if not collector.requery(request, state, hints):
                trace.emit(
                    "REPLAN_TARGETED", "no_additional_admissible_source", "blocked",
                    attempt=attempt, reason="No new time-eligible records; no fake retry success",
                )
                if not audit.accepted:
                    audit.blocked_reasons.append("targeted_requery_no_new_admissible_evidence")
                break
            handoffs.append(AgentHandoff(
                from_agent=collector.name,
                to_agent=decision_agent.name,
                shared_state_digest=digest([s.source_id for s in state["eligible"]]),
                notes=[f"new real source accepted on retry {attempt}"],
            ))
            draft = decision_agent.run(request, state["eligible"], state["memories"])
            audit = auditor.run(
                request, state["eligible"], draft,
                [s.source_id for s in state["eligible"]],
            )
            handoffs.append(AgentHandoff(
                from_agent=decision_agent.name,
                to_agent=auditor.name,
                shared_state_digest=digest([c.source_id for c in draft.citations]),
                notes=[f"auditor reviewed new evidence on retry {attempt}"],
            ))

        verdict = draft.nominated_verdict
        citations = audit.verified_citations
        missing = list(draft.missing_facts)
        rationale = draft.rationale
        if not audit.accepted:
            verdict = Verdict.INSUFFICIENT_EVIDENCE
            missing = list(dict.fromkeys(missing + audit.blocked_reasons))
            rationale = "EvidenceAuditorAgent blocked the draft: " + "; ".join(audit.blocked_reasons)
            citations = []

        # Identity aliases or contradictory input plans are disclosed as a
        # first-class abstention reason. The auditor must never turn an
        # ambiguous original source batch into an ordinary 'missing bulletin'.
        integrity_issues = state.get("initial_integrity_issues") or []
        if integrity_issues:
            verdict = Verdict.INSUFFICIENT_EVIDENCE
            citations = []
            integrity_codes = [issue["code"] for issue in integrity_issues]
            missing = list(dict.fromkeys(missing + integrity_codes))
            rationale = (
                "SOURCE_INTEGRITY_REFUSED: ambiguous initial evidence set; "
                "independent source verification is required before a decision. "
                + ", ".join(integrity_codes)
            )

        mem = self.hmem.add_decision(
            content=(
                f"simulated {verdict.value} as_of={iso(request.as_of_utc)} "
                f"district={request.district_2024} decided for mission {request.mission_id}"
            ),
            source="evidencetrail.decision",
            mission_id=request.mission_id,
            run_id=request.run_id,
            tags=[
                f"prior_decision_as_of:{iso(request.as_of_utc)}",
                f"scenario:{request.scenario_id}",
                *[f"source:{c.source_id}" for c in citations],
            ],
        )
        memory_written = bool(mem.get("id"))
        trace.emit(
            "WRITE_ARTIFACTS", "hmem_add_decision",
            "ok" if memory_written else "blocked",
            memory_id=mem.get("id"), ledger=self.hmem.ledger_len(),
            implementation=self.hmem.implementation,
        )
        if not memory_written:
            verdict = Verdict.INSUFFICIENT_EVIDENCE
            citations = []
            missing = list(dict.fromkeys(missing + ["mandatory_hmem_write_unavailable"]))
            rationale = "Mandatory memory write failed: cannot certify decision durability."

        sponsor_calls = list(state["sponsor_calls"])
        sponsor_calls.extend(decision_agent.sponsor_calls)
        hmem_receipt = self.hmem.status_call()
        sponsor_calls.append(hmem_receipt)
        if (
            not self.sample_mode
            and hmem_receipt.outcome not in
            (SponsorOutcome.REAL_PROBE_ONLY, SponsorOutcome.REAL_SUCCESS)
        ):
            verdict = Verdict.INSUFFICIENT_EVIDENCE
            citations = []
            missing = list(dict.fromkeys(missing + ["real_hmem_engine_not_available"]))
            rationale = "Official H-MEM engine add/query not demonstrated; fail closed."
        if self.sample_mode:
            sponsor_calls.append(SponsorCall(
                provider="meterless", engine="runtime-v4",
                outcome=SponsorOutcome.SKIPPED,
                detail="SAMPLE_MODE is offline: NO /healthz, /models or inference requests",
                contract_label="OFFLINE_SAMPLE_NO_NETWORK",
            ))
        else:
            meterless = meterless_live_status()
            sponsor_calls.append(SponsorCall(
                provider=meterless["provider"], engine=meterless["engine"],
                outcome=(
                    SponsorOutcome(meterless["outcome"])
                    if meterless["outcome"] in SponsorOutcome._value2member_map_
                    else SponsorOutcome.BLOCKED
                ),
                detail=meterless["detail"],
                contract_label=meterless.get("contract_label"),
            ))
        # A true direct NVIDIA NIM attempt must be reported by DecisionAgent,
        # not silently overwritten with the old unconditional SKIPPED claim.
        # All mocked/injected provider attempts are UNIT_CONTRACT_ONLY.
        nvidia_calls = [
            c for c in decision_agent.sponsor_calls if c.provider == "nvidia"
        ]
        if not nvidia_calls:
            sponsor_calls.append(SponsorCall(
                provider="nvidia",
                engine="nemotron",
                outcome=SponsorOutcome.SKIPPED,
                detail=(
                    "No direct NVIDIA Nemotron call in sample mode or absent "
                    "explicit EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED=true. "
                    "No sponsor receipt; never label a Meterless localhost "
                    "probe as NVIDIA model inference."
                ),
                contract_label="NO_NVIDIA_DIRECT_REQUEST",
            ))

        caveats = [
            DISCLAIMER,
            f"mode={request.mode.value}",
            "publication displayed time != observation time != URL slug time != retrieval time",
            "H-MEM query has no upstream as-of filter; application post-filter is mandatory",
            "H-MEM implementation=" + self.hmem.implementation
            + "; official TypeScript reference still requires upstream conformance proof",
            f"model_route={draft.model_route}",
        ]
        if request.mode == ReplayMode.REPORTED_DATELINE_REPLAY:
            caveats.append("REPORTED_DATELINE_REPLAY: original page edit history unverified")

        result = RunResult(
            request=request,
            verdict=verdict,
            rationale=rationale,
            missing_facts=missing,
            eligible_source_ids=[s.source_id for s in state["eligible"]],
            excluded=state["excluded"],
            citations=citations,
            caveats=caveats,
            agents=[collector.name, decision_agent.name, auditor.name],
            handoffs=handoffs,
            sponsor_calls=sponsor_calls,
            memory_ids=[mem["id"]] if memory_written else [],
            disclaimer=DISCLAIMER,
        )
        out_json = self.log_dir / f"run-{request.run_id}.json"
        out_json.write_text(
            __import__("json").dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        trace.emit("COMPLETE", "run_end", "ok", verdict=verdict.value, artifact=str(out_json))
        return result
