from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any
from uuid import uuid4


class ReplayMode(str, Enum):
    STRICT_AS_OF_2024 = "STRICT_AS_OF_2024"
    REPORTED_DATELINE_REPLAY = "REPORTED_DATELINE_REPLAY"


class Verdict(str, Enum):
    WARN = "WARN"
    NO_WARN = "NO_WARN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RecordKind(str, Enum):
    GOVERNMENT_NEWS = "GOVERNMENT_NEWS"
    SYNTHETIC_CAPACITY = "SYNTHETIC_CAPACITY"
    RETROSPECTIVE_HINDCAST = "RETROSPECTIVE_HINDCAST"
    IMPORTED_ARCHIVE = "IMPORTED_ARCHIVE"
    PREVIOUS_SIMULATED_DECISION = "PREVIOUS_SIMULATED_DECISION"


class ProvenanceQuality(str, Enum):
    AUTHENTICATED_2024_SNAPSHOT = "AUTHENTICATED_2024_SNAPSHOT"
    ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN = (
        "ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN"
    )
    IMPORTED_2024_DATELINE_ON_2026_PORTAL = "IMPORTED_2024_DATELINE_ON_2026_PORTAL"
    RETROSPECTIVE_2026_HINDCAST = "RETROSPECTIVE_2026_HINDCAST"
    SYNTHETIC = "SYNTHETIC"


class SponsorOutcome(str, Enum):
    REAL_SUCCESS = "REAL_SUCCESS"
    REAL_PROBE_ONLY = "REAL_PROBE_ONLY"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    SAMPLE_CACHE = "SAMPLE_CACHE"
    UNIT_CONTRACT_ONLY = "UNIT_CONTRACT_ONLY"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime rejected: {value}")
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class SourceRecord:
    source_id: str
    record_kind: RecordKind
    locator: str
    publisher: str
    paraphrase: str
    excerpt: str
    excerpt_sha256: str
    published_at_displayed_utc: datetime | None
    observed_at_utc: datetime | None
    issued_at_claimed_utc: datetime | None
    first_availability_proven_utc: datetime | None
    retrieved_at_utc: datetime | None
    provenance_quality: ProvenanceQuality
    historical_admin_vintage: str
    spatial_scope: list[str]
    named_districts_2024: list[str]
    granularity: str
    scenario_id: str | None = None
    plan_predicates: dict[str, bool] = field(default_factory=dict)
    metadata_conflicts: list[str] = field(default_factory=list)
    observation_fields: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in (
            "published_at_displayed_utc",
            "observed_at_utc",
            "issued_at_claimed_utc",
            "first_availability_proven_utc",
            "retrieved_at_utc",
        ):
            d[key] = iso(getattr(self, key))
        d["record_kind"] = self.record_kind.value
        d["provenance_quality"] = self.provenance_quality.value
        return d


@dataclass
class Citation:
    source_id: str
    excerpt_sha256: str
    claim: str


@dataclass
class RunRequest:
    schema_version: str
    as_of_utc: datetime
    mode: ReplayMode
    mission_id: str
    scenario_id: str
    province_2024: str
    district_2024: str | None
    granularity: str
    question: str
    sample_mode: bool = True
    max_retries: int = 2
    run_id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RunRequest":
        if raw.get("schema_version") != "1":
            raise ValueError("unsupported schema_version")
        as_of = parse_iso(raw["as_of_utc"])
        if as_of is None:
            raise ValueError("as_of_utc required")
        run_id = raw.get("run_id") or str(uuid4())
        if (not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", run_id)
            or ".." in run_id):
            raise ValueError("unsafe_run_id_rejected")
        district = raw.get("district_2024") or None
        granularity = raw.get("granularity") or ("district" if district else "province")
        return cls(
            schema_version=raw["schema_version"],
            as_of_utc=as_of,
            mode=ReplayMode(raw.get("mode", ReplayMode.REPORTED_DATELINE_REPLAY.value)),
            mission_id=raw["mission_id"],
            scenario_id=raw["scenario_id"],
            province_2024=raw["province_2024"],
            district_2024=district,
            granularity=granularity,
            question=raw["question"],
            sample_mode=bool(raw.get("sample_mode", True)),
            max_retries=int(raw.get("max_retries", 2)),
            run_id=run_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "as_of_utc": iso(self.as_of_utc),
            "mode": self.mode.value,
            "mission_id": self.mission_id,
            "scenario_id": self.scenario_id,
            "province_2024": self.province_2024,
            "district_2024": self.district_2024,
            "granularity": self.granularity,
            "question": self.question,
            "sample_mode": self.sample_mode,
            "max_retries": self.max_retries,
        }


@dataclass
class SponsorCall:
    provider: str
    engine: str
    outcome: SponsorOutcome
    detail: str
    invocation_id: str | None = None
    row_count: int | None = None
    contract_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "engine": self.engine,
            "outcome": self.outcome.value,
            "detail": self.detail,
            "invocation_id": self.invocation_id,
            "row_count": self.row_count,
            "contract_label": self.contract_label,
        }


@dataclass
class AgentHandoff:
    from_agent: str
    to_agent: str
    shared_state_digest: str
    notes: list[str]


@dataclass
class DecisionDraft:
    nominated_verdict: Verdict
    rationale: str
    citations: list[Citation]
    missing_facts: list[str]
    model_route: str
    used_source_ids: list[str]


@dataclass
class AuditResult:
    accepted: bool
    blocked_reasons: list[str]
    requery_hints: list[str]
    verified_citations: list[Citation]


@dataclass
class RunResult:
    request: RunRequest
    verdict: Verdict
    rationale: str
    missing_facts: list[str]
    eligible_source_ids: list[str]
    excluded: list[dict[str, Any]]
    citations: list[Citation]
    caveats: list[str]
    agents: list[str]
    handoffs: list[AgentHandoff]
    sponsor_calls: list[SponsorCall]
    memory_ids: list[str]
    disclaimer: str
    research_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.request.schema_version,
            "run_id": self.request.run_id,
            "research_only": True,
            "disclaimer": self.disclaimer,
            "verdict": self.verdict.value,
            "rationale": self.rationale,
            "missing_facts": self.missing_facts,
            "as_of_utc": iso(self.request.as_of_utc),
            "mode": self.request.mode.value,
            "mission_id": self.request.mission_id,
            "province_2024": self.request.province_2024,
            "district_2024": self.request.district_2024,
            "eligible_source_ids": self.eligible_source_ids,
            "excluded": self.excluded,
            "citations": [asdict(c) for c in self.citations],
            "caveats": self.caveats,
            "agents": self.agents,
            "handoffs": [asdict(h) for h in self.handoffs],
            "sponsor_calls": [s.to_dict() for s in self.sponsor_calls],
            "memory_ids": self.memory_ids,
            "sample_mode": self.request.sample_mode,
        }
