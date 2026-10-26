from __future__ import annotations

import os
from pathlib import Path

from evidencetrail.hmem_port import HMEM, EMBEDDING_DISCLAIMER, UPSTREAM_COMMIT
from evidencetrail.adapters.hmem_official import OfficialHMemError, OfficialHMemReference
from evidencetrail.models import SponsorCall, SponsorOutcome


class HMemAdapter:
    def __init__(self, persist_dir: str | Path | None = None, sample_mode: bool = True):
        default = os.environ.get("HMEM_PERSIST_DIR", "./hmem_data")
        self.persist_dir = Path(persist_dir or default)
        self.sample_mode = sample_mode
        self.official_enabled = (
            not self.sample_mode and
            os.environ.get("HMEM_ENGINE_MODE", "python_port").strip().lower()
            == "official_reference"
        )
        self._last_error: str | None = None
        if self.official_enabled:
            self.engine = OfficialHMemReference(self.persist_dir)
            self.implementation = "meterless_official_ts_reference_opt_in"
        else:
            self.engine = HMEM(persist_dir=self.persist_dir)
            self.implementation = "python_port_of_meterless_hmem_reference"

    def status_call(self) -> SponsorCall:
        if self.official_enabled:
            if self._last_error:
                return SponsorCall(
                    provider="meterless", engine="hmem-official-ts-reference",
                    outcome=SponsorOutcome.UNAVAILABLE,
                    detail="H-MEM official reference unavailable: " + self._last_error,
                    contract_label="OFFICIAL_REFERENCE_CALL_FAILED",
                )
            return self.engine.status_call()
        return SponsorCall(
            provider="meterless",
            engine="hmem-python-reference-port",
            outcome=SponsorOutcome.UNIT_CONTRACT_ONLY,
            detail=(
                f"Application Python reference port executed; persistDir={self.persist_dir}; "
                f"upstream={UPSTREAM_COMMIT}; {EMBEDDING_DISCLAIMER} "
                "The official Node Meterless H-MEM engine has NOT been invoked. "
                "Port add/query/ledger behavior is NOT live sponsor-engine acceptance."
            ),
            invocation_id=None,
            contract_label="HMEM_PORT_ONLY_NOT_VENDOR_ENGINE",
        )

    def add_decision(self, content: str, source: str, mission_id: str, run_id: str, tags: list[str]) -> dict:
        if self.official_enabled:
            try:
                result = self.engine.add_decision(content, source, mission_id, run_id, tags)
                self._last_error = None
                return result
            except OfficialHMemError as exc:
                self._last_error = type(exc).__name__
                return {"id": None, "persisted": False}
        return self.engine.add(
            content=content,
            source=source,
            mission_id=mission_id,
            goal_run_id=run_id,
            tags=tags,
        )

    def query(self, text: str) -> dict:
        if self.official_enabled:
            try:
                result = self.engine.query(text)
                self._last_error = None
                return result
            except OfficialHMemError as exc:
                self._last_error = type(exc).__name__
                return {"hits": [], "error": "OFFICIAL_HMEM_UNAVAILABLE",
                        "disclaimer": "Official TS reference failed; not live memory proof"}
        return self.engine.query(text)

    def ledger_len(self) -> int:
        if self.official_enabled:
            return self.engine.ledger_len()
        return len(self.engine.ledger.entries)
