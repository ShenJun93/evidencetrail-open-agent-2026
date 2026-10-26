"""H-MEM TS reference bridge contract tests (fake runner; NO vendor claims)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidencetrail.adapters.hmem import HMemAdapter
from evidencetrail.adapters.hmem_official import OfficialHMemReference, OfficialHMemError
from evidencetrail.models import SponsorOutcome


class FakeResult:
    def __init__(self, content: dict, returncode: int = 0):
        self.returncode = returncode
        self.stdout = json.dumps(content)
        self.stderr = ""


class HMemOfficialBridgeTests(unittest.TestCase):
    def test_sample_mode_never_spawns_vendor_even_when_env_opted_in(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"HMEM_ENGINE_MODE": "official_reference"}):
                memory = HMemAdapter(persist_dir=td, sample_mode=True)
                self.assertFalse(memory.official_enabled)
                x = memory.add_decision(
                    "safe simulated decision", "evidencetrail.decision",
                    "mission-a", "run-a", ["scenario:a"],
                )
                self.assertTrue(x["id"])
                self.assertEqual(
                    memory.status_call().outcome, SponsorOutcome.UNIT_CONTRACT_ONLY
                )

    def test_missing_official_checkout_never_reports_success(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"HMEM_ENGINE_MODE": "official_reference"}):
                with patch.object(
                    OfficialHMemReference, "_verify_local_checkout",
                    side_effect=OfficialHMemError("reference not provisioned"),
                ):
                    memory = HMemAdapter(persist_dir=td, sample_mode=False)
                    response = memory.query("prior decision")
                    self.assertEqual(response["hits"], [])
                    self.assertEqual(response.get("error"), "OFFICIAL_HMEM_UNAVAILABLE")
                    output = memory.add_decision(
                        "watch", "evidencetrail.decision",
                        "mission-a", "run-a", ["scenario:a"],
                    )
                    self.assertIsNone(output["id"])
                    self.assertEqual(
                        memory.status_call().outcome, SponsorOutcome.UNAVAILABLE
                    )

    def test_injected_runner_add_query_ledger_remains_unit_only(self):
        operations = []
        fake_record = {
            "id": "mem-1", "content": "simulated WARN as_of=2024-09-08T09:45:00Z",
            "source": "evidencetrail.decision",
            "missionId": "mission-a", "goalRunId": "run-a",
            "tags": ["scenario:a", "prior_decision_as_of:2024-09-08T09:45:00Z"],
        }

        def runner(command, **kwargs):
            request = json.loads(kwargs["input"])
            operations.append(request["op"])
            self.assertEqual(command[1:3], ["--import", "tsx"])
            self.assertNotIn("NVIDIA_API_KEY", kwargs["env"])
            base = {
                "ok": True,
                "implementation": "meterless-official-ts-reference",
                "conformance": "NOT_RUN_BY_BRIDGE",
                "ledgerLen": len(operations),
            }
            if request["op"] == "add":
                base["record"] = fake_record
                base["createLedgerCount"] = 1
            elif request["op"] == "query":
                base["hits"] = [{**fake_record, "score": 0.9}]
                base["upstreamAsOfFilter"] = "NONE_UPSTREAM"
            else:
                base["actions"] = [{"memoryId": "mem-1", "action": "create"}]
            return FakeResult(base)

        with tempfile.TemporaryDirectory() as td:
            bridge = OfficialHMemReference(td, runner=runner)
            with patch.object(bridge, "_verify_local_checkout", return_value=None):
                rec = bridge.add_decision(
                    fake_record["content"], fake_record["source"],
                    "mission-a", "run-a", fake_record["tags"],
                )
                memory = bridge.query("simulated WARN")
                ledger = bridge.verify_ledger(rec["id"])
            self.assertEqual(rec["id"], "mem-1")
            self.assertEqual(memory["hits"][0]["missionId"], "mission-a")
            self.assertEqual(ledger["actions"][0]["action"], "create")
            self.assertEqual(operations, ["add", "query", "ledger"])
            self.assertEqual(
                bridge.status_call().outcome, SponsorOutcome.UNIT_CONTRACT_ONLY
            )

    def test_injected_malformed_reference_never_reports_success(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = OfficialHMemReference(
                td, runner=lambda *_args, **_kwargs: FakeResult({
                    "ok": True,
                    "implementation": "wrong-impl",
                    "ledgerLen": 12,
                }),
            )
            with patch.object(bridge, "_verify_local_checkout", return_value=None):
                with self.assertRaises(RuntimeError):
                    bridge.query("memory")
            self.assertNotEqual(
                bridge.status_call().outcome, SponsorOutcome.REAL_SUCCESS
            )

    def test_nonzero_reference_exit_refused_without_stderr_leak(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = OfficialHMemReference(
                td, runner=lambda *_args, **_kwargs: FakeResult({}, returncode=3),
            )
            with patch.object(bridge, "_verify_local_checkout", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "nonzero exit"):
                    bridge.query("memory")
            self.assertNotEqual(
                bridge.status_call().outcome, SponsorOutcome.REAL_SUCCESS
            )
