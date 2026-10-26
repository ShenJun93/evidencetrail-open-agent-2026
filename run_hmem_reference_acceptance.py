"""Opt-in real Meterless TypeScript reference add/query/ledger acceptance.

This is NOT run by the offline Python test suite and NEVER installs dependencies.
Only run after an authorized local vendor checkout and a local tsx installation:

  $env:HMEM_ENGINE_MODE = 'official_reference'
  py -3 run_hmem_reference_acceptance.py

It checks separate Node processes, persistence, read audit, and mission filtering.
This is NOT the upstream H-MEM conformance suite or Nightshift inference.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from evidencetrail.adapters.hmem_official import OfficialHMemError, OfficialHMemReference
from evidencetrail.firewall import filter_memories

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "acceptance" / "hmem-official-reference-receipt.json"


def run() -> int:
    if os.environ.get("HMEM_ENGINE_MODE", "").lower() != "official_reference":
        print("BLOCKED: HMEM_ENGINE_MODE=official_reference required", file=sys.stderr)
        return 2

    session_id = "acceptance-" + uuid4().hex[:12]
    persist = ROOT / "hmem_data" / ("official-reference-" + session_id)
    question = "simulated luc yen source chronology decision memory"
    tags = [
        "scenario:" + session_id,
        "prior_decision_as_of:2024-09-08T09:45:00Z",
        "source:GOV-2024-09-08-1637",
    ]
    payload = "simulated WARN as_of=2024-09-08T09:45:00Z district=luc yen"
    report = {
        "mode": "OFFICIAL_HMEM_TYPESCRIPT_REFERENCE_OPT_IN",
        "source_checkout": "vendor/meterless/engines/hmem/reference",
        "conformance_suite": "NOT_RUN_BY_THIS_ACCEPTANCE",
        "nightshift_inference": "NOT_TESTED",
        "zetaris_live": "NOT_TESTED",
        "memory_sample_is_synthetic": True,
        "session_id": session_id,
        "cross_process_add_query_ledger": "BLOCKED",
    }

    try:
        first = OfficialHMemReference(persist)
        record = first.add_decision(
            payload, "evidencetrail.decision", session_id,
            "test-run-" + session_id, tags,
        )
        second = OfficialHMemReference(persist)
        recalled = second.query(question)["hits"]
        matching = [mem for mem in recalled if mem.get("id") == record["id"]]
        if len(matching) != 1:
            raise OfficialHMemError("persisted memory not recalled in second Node process")

        third = OfficialHMemReference(persist)
        audit = third.verify_ledger(record["id"])
        actions = [item.get("action") for item in audit.get("actions") or []]
        if "create" not in actions or "read" not in actions:
            raise OfficialHMemError("create/read ledger entries missing across processes")

        timepoint = datetime(2024, 9, 8, 9, 45, tzinfo=timezone.utc)
        kept, rejected = filter_memories(
            matching, session_id, timepoint,
            {"GOV-2024-09-08-1637"}, scenario_id=session_id,
        )
        if len(kept) != 1 or rejected:
            raise OfficialHMemError("valid same-scope historical memory rejected")

        futurepoint = datetime(2024, 9, 8, 9, 30, tzinfo=timezone.utc)
        future_kept, future_dropped = filter_memories(
            matching, session_id, futurepoint,
            {"GOV-2024-09-08-1530"}, scenario_id=session_id,
        )
        if future_kept or not future_dropped:
            raise OfficialHMemError("future/time-scope memory was not rejected")

        report.update({
            "cross_process_add_query_ledger": "PASS",
            "memory_id": record["id"],
            "ledger_actions": actions,
            "ledger_entries": audit["ledgerLen"],
            "same_scope_recall": "PASS",
            "earlier_replay_rejects_future": "PASS",
            "sponsor_evidence_level": (
                "ACTUAL_REFERENCE_ENGINE_OPERATIONS; UPSTREAM_CONFORMANCE_PENDING"
            ),
        })
        status = 0
    except (OfficialHMemError, ValueError, OSError) as exc:
        report["cross_process_add_query_ledger"] = "FAIL_OR_NOT_CONFIGURED"
        report["blocker_type"] = type(exc).__name__
        status = 1

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "cross_process": report["cross_process_add_query_ledger"],
        "reference_acceptance_report": str(REPORT.relative_to(ROOT)),
        "upstream_conformance": report["conformance_suite"],
    }))
    return status


if __name__ == "__main__":
    raise SystemExit(run())
