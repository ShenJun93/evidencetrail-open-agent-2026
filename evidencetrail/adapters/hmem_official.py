"""Opt-in Python client for the actual Meterless TypeScript H-MEM reference.

NOT the proprietary Nightshift Runtime, NOT a conformance certificate.
The reference source and its tsx dependency must be explicitly provisioned
locally under ignored vendor/meterless/; this code never downloads anything.
No shell, network, unsigned installer, or automatic npm install is used.

The reference is invoked in a separate Node process per operation. Its
persistDir and append-only ledger survive re-instantiation across processes.
Only a real, successfully completed process call is an engine-execution receipt.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from evidencetrail.models import SponsorCall, SponsorOutcome

ROOT = Path(__file__).resolve().parents[2]


class OfficialHMemError(RuntimeError):
    """Official reference unavailable or its bridge rejected an operation."""


class OfficialHMemReference:
    def __init__(
        self,
        persist_dir: str | Path,
        reference_dir: str | Path | None = None,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        # Deliberately restrict executable source to the project's ignored
        # owner-reviewed vendor checkout. No arbitrary external JS paths.
        self.reference_dir = Path(
            reference_dir or ROOT / "vendor" / "meterless" / "engines" / "hmem" / "reference"
        ).resolve()
        self.persist_dir = Path(persist_dir).resolve()
        self.script = ROOT / "evidencetrail" / "official_hmem_bridge.mts"
        self.runner = runner
        self._calls: dict[str, int] = {"add": 0, "query": 0, "ledger": 0}
        self._last_ledger_len = 0
        self._last_error: str | None = None

    def _verify_local_checkout(self) -> None:
        vendor = (ROOT / "vendor").resolve()
        if not self.reference_dir.is_relative_to(vendor):
            raise OfficialHMemError("H-MEM reference must be under ignored project vendor/")
        if not (self.reference_dir / "src" / "index.ts").is_file():
            raise OfficialHMemError("Official reference checkout is absent; NOT an engine PASS")
        if not (self.reference_dir / "node_modules" / "tsx").exists():
            raise OfficialHMemError("tsx is not locally provisioned; no auto-install performed")
        if not self.script.is_file():
            raise OfficialHMemError("EvidenceTrail bridge source is missing")

    def _rpc(self, op: str, **args: Any) -> dict[str, Any]:
        self._verify_local_checkout()
        request = {"op": op, "persistDir": str(self.persist_dir), **args}
        raw = json.dumps(request, ensure_ascii=False)
        if len(raw.encode("utf-8")) > 32768:
            raise OfficialHMemError("bridge payload exceeds 32 KiB")

        # Avoid giving the subprocess unrelated cloud/sponsor credentials.
        permitted_keys = (
            "PATH", "Path", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP",
            "USERPROFILE", "APPDATA", "LOCALAPPDATA", "ComSpec",
        )
        restricted_env = {key: os.environ[key] for key in permitted_keys if key in os.environ}
        command = [
            os.environ.get("HMEM_NODE_EXECUTABLE", "node"),
            "--import", "tsx", str(self.script),
        ]
        invoke = self.runner or subprocess.run
        try:
            result = invoke(
                command, input=raw, capture_output=True, text=True,
                encoding="utf-8", cwd=str(self.reference_dir),
                env=restricted_env, timeout=25, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._last_error = type(exc).__name__
            raise OfficialHMemError(
                "H-MEM reference process unavailable: " + type(exc).__name__
            ) from exc
        if result.returncode != 0:
            self._last_error = "REFERENCE_PROCESS_FAILED"
            # Deliberately do not relay Node stderr: it may contain private data.
            raise OfficialHMemError("official H-MEM reference returned nonzero exit status")
        if len(result.stdout.encode("utf-8")) > 1024 * 1024:
            raise OfficialHMemError("reference response too large")
        try:
            response = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise OfficialHMemError("reference response was not valid JSON") from exc
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise OfficialHMemError("invalid reference response status")
        if response.get("implementation") != "meterless-official-ts-reference":
            raise OfficialHMemError("reference implementation identity mismatch")
        ledger_len = response.get("ledgerLen")
        if type(ledger_len) is not int or ledger_len < 0:
            raise OfficialHMemError("reference response lacks ledger count")
        self._last_ledger_len = ledger_len
        self._calls[op] = self._calls.get(op, 0) + 1
        self._last_error = None
        return response

    def add_decision(
        self,
        content: str,
        source: str,
        mission_id: str,
        run_id: str,
        tags: list[str],
    ) -> dict[str, Any]:
        result = self._rpc(
            "add", content=content, source=source,
            missionId=mission_id, goalRunId=run_id, tags=tags,
        )
        record = result.get("record")
        if not isinstance(record, dict) or not record.get("id"):
            raise OfficialHMemError("reference add did not return a persisted record ID")
        if not result.get("createLedgerCount"):
            raise OfficialHMemError("reference add lacks a create-ledger audit entry")
        return record

    def query(self, text: str) -> dict[str, Any]:
        result = self._rpc("query", text=text, topN=8)
        hits = result.get("hits")
        if not isinstance(hits, list) or any(
            not isinstance(hit, dict) or not hit.get("id") for hit in hits
        ):
            raise OfficialHMemError("reference query returned invalid hits")
        return {
            "hits": hits,
            "as_of_filter": "NONE_UPSTREAM",
            "disclaimer": (
                "Real Meterless TS reference query; still UNTRUSTED context. "
                "Temporal, mission and scenario postfilters are mandatory. "
                "Conformance suite was NOT executed by this bridge."
            ),
        }

    def ledger_len(self) -> int:
        return self._last_ledger_len

    def verify_ledger(self, memory_id: str) -> dict[str, Any]:
        return self._rpc("ledger", memoryId=memory_id)

    def status_call(self) -> SponsorCall:
        if self._last_error:
            return SponsorCall(
                provider="meterless", engine="hmem-official-ts-reference",
                outcome=SponsorOutcome.UNAVAILABLE,
                detail="Official TS reference operation failed: " + self._last_error,
                contract_label="REFERENCE_EXECUTION_FAILED",
            )
        exercised = self._calls["add"] > 0 and self._calls["query"] > 0
        if not exercised:
            return SponsorCall(
                provider="meterless", engine="hmem-official-ts-reference",
                outcome=SponsorOutcome.NOT_CONFIGURED,
                detail="Official reference has NOT completed add and query in this process",
                contract_label="NO_ENGINE_EXECUTION_PROOF",
            )
        return SponsorCall(
            provider="meterless", engine="hmem-official-ts-reference",
            outcome=(
                SponsorOutcome.UNIT_CONTRACT_ONLY if self.runner is not None
                else SponsorOutcome.REAL_PROBE_ONLY
            ),
            detail=(
                "Actual official Meterless TS reference add/query completed with "
                "persisted ledger; full upstream conformance and multi-process "
                "acceptance STILL REQUIRED. This is NOT Nightshift inference."
                if self.runner is None
                else "Injected fake bridge runner used: UNIT TEST ONLY"
            ),
            row_count=self._last_ledger_len,
            contract_label=(
                "TEST_INJECTED_REFERENCE_ONLY"
                if self.runner is not None else
                "OFFICIAL_TS_REF_ADD_QUERY_PENDING_CONFORMANCE"
            ),
        )
