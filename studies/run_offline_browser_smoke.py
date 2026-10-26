"""Run TWO REAL Microsoft Edge study UI smokes from a clean checkout.

Creates only ignored *automated participant fixtures*. The browser test
deletes its simulated downloaded answers. NEVER counts human participation.
Safe environment excludes API keys and paid vendor configuration.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "acceptance" / "logs"


def main() -> int:
    from evidencetrail.blind_study import main as study_cli
    from run_judge_coldstart import safe_environment

    LOG.mkdir(parents=True, exist_ok=True)
    registry = LOG / "blind-study-private-registry"
    for slot in (0, 6):
        path = LOG / ("blind-study-pilot-slot" + str(slot) + ".html")
        if not path.exists():
            rc = study_cli([
                "prepare", "--slot", str(slot), "--out", str(path),
                "--registry", str(registry),
            ])
            if rc != 0:
                print("BLIND_STUDY_CLEAN_PREPARATION_FAILED")
                return 2
    try:
        result = subprocess.run(
            ["node", str(ROOT / "studies" / "verify_participant_browser.mjs")],
            cwd=ROOT, env=safe_environment(), timeout=100,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        print("BLIND_STUDY_EDGE_EXECUTION_UNAVAILABLE")
        return 2
    for line in result.stdout.splitlines():
        if line.startswith("BLIND_STUDY_REAL_EDGE_"):
            print(line)
    good = (result.returncode == 0
            and "BLIND_STUDY_REAL_EDGE_ALL_PASS_NO_HUMAN_OUTCOMES"
                in result.stdout
            and result.stdout.count("BLIND_STUDY_REAL_EDGE_FLOW_PASS") == 2)
    print("BLIND_STUDY_CLEAN_NO_KEYS_NO_HUMAN_CLAIM_PASS" if good
          else "BLIND_STUDY_CLEAN_NO_KEYS_FAIL")
    return 0 if good else 2


if __name__ == "__main__":
    raise SystemExit(main())
