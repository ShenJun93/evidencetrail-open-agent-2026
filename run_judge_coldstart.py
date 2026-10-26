"""Re-run EvidenceTrail's zero-key offline judge suite in one command.

Usage:
  py -3 run_judge_coldstart.py
  py -3 run_judge_coldstart.py --skip-edge

This entrypoint invokes only the existing sample-mode Python acceptance,
offline chronology benchmark and isolated localhost Edge UI smoke.
It does NOT request sponsor inference, load .env.local or grant paid usage.
A dirty working tree is never described as independent clean-checkout proof.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "acceptance" / "logs" / "judge-coldstart-replay.json"
EDGE_MARKERS = (
    "REPORTED_1645_BROWSER_PASS_WARN_MIN2_PIVOTAL2",
    "STRICT_1645_BROWSER_PASS_ABSTAIN",
    "REPORTED_1630_BROWSER_PASS_ABSTAIN",
    "SOURCE_INDEPENDENCE_BROWSER_PASS_7_OF_7",
    "NOAA_EXTERNAL_MILTON_BROWSER_PASS_ASOF_100_NOT_FUTURE_155",
    "NOAA_EXTERNAL_MILTON_BROWSER_PASS_STRICT_ABSTAIN",
    "CROSS_ISSUER_BROWSER_PASS_100_51_TWO_FAMILIES",
    "CROSS_ISSUER_BROWSER_PASS_DATE_ONLY_NO_BACKDATE",
    "CROSS_ISSUER_BROWSER_PASS_STRICT_ABSTAIN",
    "EDGE_COUNTERFACTUAL_ALL_PASS",
)
WHY_EDGE_MARKERS = (
    "WHY_EDGE_ASOF_11AM_PASS_100_51",
    "WHY_EDGE_EVIDENCE_MAP_SOURCE_TO_CLAIM_AND_WITHDRAWAL_PASS",
    "WHY_EDGE_FAILED_REPLAY_CLEARS_STALE_RESULT_PASS",
    "WHY_REAL_EDGE_ALL_PASS_NO_SPONSOR_NO_HUMANS",
)
EXPECTED_CASES = {
    "yagi_1500_lucyen": "INSUFFICIENT_EVIDENCE",
    "yagi_1630_lucyen": "INSUFFICIENT_EVIDENCE",
    "yagi_1645_lucyen": "WARN",
}
# Windows Python launcher/Edge require these non-secret OS paths. Do NOT pass
# the parent's environment through to tests or localhost browser processes.
PASS_ENV = (
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "COMSPEC",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
    "HOMEDRIVE", "HOMEPATH",
)


def safe_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(os.environ if source is None else source)
    clean = {key: source[key] for key in PASS_ENV if key in source}
    clean.update({
        "SAMPLE_MODE": "true",
        "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED": "false",
        "EVIDENCETRAIL_NEBIUS_ENABLED": "false",
        "EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT": "false",
        "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED": "false",
        "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT": "false",
        "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    return clean


def execute(command: list[str], *, env: dict[str, str], timeout: int) -> tuple[int, str]:
    """Capture bounded local test output; never record trace/model text."""
    try:
        proc = subprocess.run(
            command, cwd=ROOT, env=env, timeout=timeout, check=False,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return proc.returncode, proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 99, ""


def last_json(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                return value
        except ValueError:
            continue
    return None


def check_acceptance(stdout: str, exit_code: int) -> tuple[bool, dict[str, Any]]:
    record = last_json(stdout) or {}
    passed = (
        exit_code == 0
        and record.get("test_status") == "PASS"
        and type(record.get("test_total")) is int
        and record["test_total"] >= 279
        and record.get("failures") == 0
        and record.get("errors") == 0
        and record.get("sample_cases") == 3
    )
    return passed, {
        "status": "PASS" if passed else "FAIL",
        "python_tests": record.get("test_total") if passed else None,
        "sample_cases": record.get("sample_cases") if passed else None,
        "exit_code": exit_code,
        "claim": "OFFLINE_SAMPLE_ONLY",
    }


def check_chronology(stdout: str, exit_code: int) -> tuple[bool, dict[str, Any]]:
    record = last_json(stdout) or {}
    passed = (
        exit_code == 0
        and record.get("kind") == "OFFLINE_ADVERSARIAL_CHRONOLOGY_BENCHMARK_V1"
        and record.get("pass") == 20
        and record.get("total") == 20
        and record.get("failed_cases") == []
    )
    return passed, {
        "status": "PASS" if passed else "FAIL",
        "pass": record.get("pass") if passed else None,
        "total": record.get("total") if passed else None,
        "exit_code": exit_code,
        "claim": "INTERNAL_RESEARCH_BENCHMARK_NOT_FORECAST_ACCURACY",
    }


def check_edge(stdout: str, exit_code: int) -> tuple[bool, dict[str, Any]]:
    markers = stdout.splitlines()
    passed = exit_code == 0 and all(marker in markers for marker in EDGE_MARKERS)
    return passed, {
        "status": "PASS" if passed else "FAIL",
        "scenarios": 6 if passed else None,
        "exit_code": exit_code,
        "claim": "LOCALHOST_ISOLATED_EDGE_SAMPLE_ONLY",
    }


def check_why_edge(stdout: str, exit_code: int) -> tuple[bool, dict[str, Any]]:
    markers = stdout.splitlines()
    passed = exit_code == 0 and all(marker in markers for marker in WHY_EDGE_MARKERS)
    return passed, {
        "status": "PASS" if passed else "FAIL",
        "evidence_map_interaction": "PASS" if passed else None,
        "exit_code": exit_code,
        "claim": "LOCALHOST_ISOLATED_EDGE_WHY_SAMPLE_ONLY",
    }


def git_baseline(env: dict[str, str]) -> dict[str, Any]:
    if not shutil.which("git", path=env.get("PATH")):
        return {"head": None, "tracked_clean_before_tests": None}
    code, head = execute(
        ["git", "rev-parse", "HEAD"], env=env, timeout=10,
    )
    status_code, status = execute(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        env=env, timeout=10,
    )
    return {
        "head": head.strip() if code == 0 and len(head.strip()) == 40 else None,
        "tracked_clean_before_tests": (
            status.strip() == "" if status_code == 0 else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-edge", action="store_true",
        help="run the 2 Python suites only; result is PARTIAL, never full PASS",
    )
    args = parser.parse_args(argv)
    env = safe_environment()
    baseline = git_baseline(env)
    report: dict[str, Any] = {
        "kind": "EVIDENCETRAIL_COLD_JUDGE_REPLAY_V1",
        "source_git_head": baseline["head"],
        "tracked_clean_before_tests": baseline["tracked_clean_before_tests"],
        "independent_clean_checkout_proven": False,
        "worktree_clean_before_tests": baseline["tracked_clean_before_tests"],
        "ignored_env_file_present_before_tests": (ROOT / ".env.local").is_file(),
        "meterless_vendor_present_before_tests": (ROOT / "vendor" / "meterless").exists(),
        "clean_keyless_source_replay": False,
        "external_sponsor_requests_authorized": False,
        "key_file_read_by_this_runner": False,
        "network_claim": "Only the pre-existing isolated browser localhost test; "
                         "no sponsor API or independent network packet monitoring",
        "nvidia_direct_sponsor_verified": False,
        "nebius_structured_inference_verified": False,
        "organizer_eligibility_verified": False,
        "actual_disaster_forecast_accuracy_verified": False,
        "status": "NOT_RUN",
        "steps": {},
    }
    stages = [
        ("python_acceptance", [sys.executable, str(ROOT / "run_acceptance.py")],
         check_acceptance, 240),
        ("chronology", [sys.executable, str(ROOT / "run_judge_chronology_stress_benchmark.py")],
         check_chronology, 120),
    ]
    if not args.skip_edge:
        stages.append((
            "edge_e2e", ["node", str(ROOT / "verify_counterfactual_browser.mjs")],
            check_edge, 180,
        ))
        stages.append((
            "why_edge_e2e", ["node", str(ROOT / "demo" / "verify_why_browser.mjs")],
            check_why_edge, 300,
        ))
    else:
        report["steps"]["edge_e2e"] = {
            "status": "SKIPPED", "reason": "--skip-edge",
        }
        report["steps"]["why_edge_e2e"] = {
            "status": "SKIPPED", "reason": "--skip-edge",
        }

    everything_passed = True
    for name, command, check, timeout in stages:
        code, stdout = execute(command, env=env, timeout=timeout)
        okay, evidence = check(stdout, code)
        report["steps"][name] = evidence
        everything_passed = everything_passed and okay
        print(name + "=" + evidence["status"], flush=True)
        if not okay:
            # Stop before more tests and preserve only sanitized statuses.
            break

    full = everything_passed and not args.skip_edge
    report["status"] = "PASS" if full else (
        "PARTIAL_EDGE_SKIPPED" if everything_passed else "FAIL"
    )
    # Git cleanliness is not proof that the checkout was independently made.
    # Ignore neither untracked files nor the presence of ignored secrets/vendor.
    report["clean_keyless_source_replay"] = bool(
        full and baseline["head"]
        and baseline["tracked_clean_before_tests"] is True
        and not report["ignored_env_file_present_before_tests"]
        and not report["meterless_vendor_present_before_tests"]
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if everything_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
