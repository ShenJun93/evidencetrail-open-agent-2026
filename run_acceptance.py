"""Offline EvidenceTrail judge acceptance, no sponsor/network/paid inference.

Run in an ordinary Cursor integrated terminal, without Cursor Agent credits:
    py -3 run_acceptance.py
or:
    python run_acceptance.py

It is NOT an H-MEM vendor, Zetaris live, Nightshift, or NVIDIA proof.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from evidencetrail.models import RunRequest, SponsorOutcome
from evidencetrail.pipeline import EvidenceTrailPipeline

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "acceptance"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    # Force genuine offline/sample execution, regardless of .env.local.
    os.environ["SAMPLE_MODE"] = "true"
    os.environ["EVIDENCETRAIL_ALLOW_NVIDIA"] = "false"
    os.environ.pop("METERLESS_RUNTIME_TOKEN", None)
    os.environ.pop("ZETARIS_API_KEY", None)

    log = io.StringIO()
    with redirect_stdout(log), redirect_stderr(log):
        tests = unittest.TestLoader().discover("tests")
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(tests)
    (OUT / "offline-tests.txt").write_text(log.getvalue(), encoding="utf-8")

    report = {
        "mode": "OFFLINE_SAMPLE_ONLY",
        "test_total": result.testsRun,
        "test_failures": len(result.failures),
        "test_errors": len(result.errors),
        "test_skipped": len(result.skipped),
        "test_status": "PASS" if result.wasSuccessful() else "FAIL",
        "source_code_written_by": "Cursor initial build; WAG Local follow-up patch (disclose both)",
        "sponsor_live_receipts": "NONE_IN_THIS_SCRIPT",
        "cases": [],
    }
    paths = sorted((ROOT / "samples" / "inputs").glob("*.json"))
    with tempfile.TemporaryDirectory(prefix="evidencetrail-offline-") as temp:
        pipeline = EvidenceTrailPipeline(
            sample_mode=True, persist_dir=Path(temp) / "hmem",
            log_dir=OUT / "logs",
        )
        for path in paths:
            request_data = json.loads(path.read_text(encoding="utf-8"))
            request_data["sample_mode"] = True
            request = RunRequest.from_dict(request_data)
            output = pipeline.run(request)
            sponsor = [s.to_dict() for s in output.sponsor_calls]
            if any(s.outcome == SponsorOutcome.REAL_SUCCESS for s in output.sponsor_calls):
                raise RuntimeError("Offline mode incorrectly asserted REAL_SUCCESS sponsor")
            target = OUT / (path.stem + ".output.json")
            target.write_text(
                json.dumps(output.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report["cases"].append({
                "input": str(path.relative_to(ROOT)),
                "output": str(target.relative_to(ROOT)),
                "verdict": output.verdict.value,
                "eligible_source_ids": output.eligible_source_ids,
                "sponsor_outcomes": [
                    {"provider": row["provider"], "outcome": row["outcome"],
                     "contract_label": row.get("contract_label")}
                    for row in sponsor
                ],
                "note": "SIMULATED historical-replay study; NOT emergency advice",
            })
    (OUT / "offline-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "test_status": report["test_status"], "test_total": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "sample_cases": len(report["cases"]),
        "report": str((OUT / "offline-report.json").relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
