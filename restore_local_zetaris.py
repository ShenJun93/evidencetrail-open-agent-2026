"""Guarded recovery of EXISTING Zetaris containers, without recreation.

Defaults to a READ-ONLY plan:
    py -3 restore_local_zetaris.py --check

OWNER-EXECUTED ONLY after inspecting current results:
    py -3 restore_local_zetaris.py --start

No cloud, images, pull, create, compose up, init/bootstrap, passwords,
configuration edits, rm, volume deletion, or Windows security changes.
Starts EXACTLY four existing containers in order and stops advancing if
a dependency is not healthy. Partial recovery is retained for inspection;
this script NEVER stops or removes services.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from diagnose_zetaris_recovery import (
    DockerUnavailable,
    NAMES,
    build_report,
    exec_local,
    inspect_container,
    tcp_open,
)

ROOT = Path(__file__).resolve().parent
RECEIPT = ROOT / "acceptance" / "zetaris-recovery-attempt.json"
REQUIRED_PROJECT = "zetaris"
ORDER = [
    ("zetaris-postgres-1", "postgres"),
    ("zetaris-driver-1", "driver"),
    ("zetaris-api-1", "api"),
    ("zetaris-ui-1", "ui"),
]
ONE_SHOT = {"zetaris-init-1": "init", "zetaris-bootstrap-1": "bootstrap"}
MAX_WAIT_SECONDS = {"postgres": 90, "driver": 105, "api": 90, "ui": 75}


def preflight_reasons(report: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    endpoint = report.get("docker_context") or {}
    resources = report.get("resources") or {}
    if not endpoint.get("permitted"):
        blockers.append("DOCKER_CONTEXT_NOT_LOCAL")
    if not resources.get("available") or not resources.get("docker_server_linux"):
        blockers.append("LOCAL_LINUX_DOCKER_UNAVAILABLE")
    if not resources.get("meets_recommended_8gb_4cpu"):
        blockers.append("DOCKER_BELOW_OFFICIAL_RECOMMENDED_8GB_OR_4CPU")
    if not resources.get("meets_zetaris_preflight_6gb_minimum"):
        blockers.append("DOCKER_BELOW_OFFICIAL_PREFLIGHT_6GB")

    if report.get("compose_project") != REQUIRED_PROJECT or not report.get("same_compose_project"):
        blockers.append("NOT_ORIGINAL_ZETARIS_COMPOSE_PROJECT")

    containers = {v.get("name"): v for v in report.get("containers", []) if isinstance(v, dict)}
    if set(containers) != set(NAMES):
        blockers.append("EXPECTED_SIX_CONTAINERS_NOT_FOUND")

    for name, service in ORDER + list(ONE_SHOT.items()):
        item = containers.get(name) or {}
        if not item.get("found"):
            blockers.append("CONTAINER_NOT_VERIFIED_" + service.upper())
            continue
        if item.get("compose_project") != REQUIRED_PROJECT or item.get("compose_service") != service:
            blockers.append("WRONG_COMPOSE_IDENTITY_" + service.upper())
        if item.get("oom_killed"):
            blockers.append("DOCKER_RECORDED_OOM_" + service.upper())
        if item.get("status") not in {"exited", "running"}:
            blockers.append("UNEXPECTED_CONTAINER_STATE_" + service.upper())

    postgres = containers.get("zetaris-postgres-1") or {}
    if not report.get("postgres_persistent_mount_present") or postgres.get("volume_mount_count", 0) < 1:
        blockers.append("POSTGRES_VOLUME_NOT_VERIFIED")

    for name, service in ONE_SHOT.items():
        job = containers.get(name) or {}
        if job.get("status") != "exited" or job.get("exit_code") != 0:
            blockers.append("ONE_SHOT_JOB_NOT_COMPLETED_" + service.upper())

    if report.get("status") not in {
        "STOPPED_STACK_VERIFIED_MANUAL_START_CAN_BE_CONSIDERED",
        "PARTIAL_OR_RUNNING_STACK_REVIEW_HEALTH_BEFORE_CHANGES",
    }:
        blockers.append("DOCKER_PREFLIGHT_STATUS_NOT_READY")

    return list(dict.fromkeys(blockers))


def state_of(name: str) -> dict[str, Any]:
    raw = exec_local("inspect", "--format", "{{json .State}}", name, timeout=8)
    state = json.loads(raw)
    if not isinstance(state, dict):
        raise DockerUnavailable("INVALID_CONTAINER_STATE")
    health = state.get("Health") or {}
    return {
        "status": str(state.get("Status", ""))[:30],
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled") is True,
        "health": str(health.get("Status") or "NOT_CONFIGURED")[:30],
    }


def await_health(name: str, service: str) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_WAIT_SECONDS[service]
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = state_of(name)
        if last["status"] != "running":
            return {"state": last, "ready": False, "reason": "PROCESS_NOT_RUNNING"}
        if last["oom_killed"]:
            return {"state": last, "ready": False, "reason": "OOM_RECORDED"}
        if last["health"] == "healthy":
            return {"state": last, "ready": True}
        # Some vendor images have no healthcheck; ensure process exists and
        # gate externally on relevant port for final UI readiness.
        if last["health"] == "NOT_CONFIGURED":
            return {"state": last, "ready": True, "healthcheck": "NOT_CONFIGURED"}
        time.sleep(3)
    return {
        "state": last,
        "ready": False,
        "reason": "HEALTH_NOT_READY_IN_BOUNDED_OBSERVATION",
    }


def receipt(status: str, before: dict[str, Any], started: list[str],
            observations: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    return {
        "purpose": "EXISTING_ZETARIS_CONTAINERS_GUARDED_START",
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "docker_compose_project": "zetaris" if before.get("same_compose_project") else None,
        "memory_gb_decimal": (before.get("resources") or {}).get("memory_gb_decimal"),
        "memory_gib": (before.get("resources") or {}).get("memory_gib"),
        "cpus": (before.get("resources") or {}).get("cpus"),
        "allowed_services": [name for name, _ in ORDER],
        "one_shot_services_never_started": list(ONE_SHOT),
        "started_in_this_attempt": started,
        "observations": observations,
        "blockers": blockers,
        "volume_actions": "NONE",
        "images_or_containers_created": False,
        "download_or_external_api": "NONE",
        "sponsor_sql_eligibility": "NOT_TESTED",
    }


def execute(start: bool) -> tuple[dict[str, Any], int]:
    before = build_report()
    blockers = preflight_reasons(before)
    if blockers:
        return receipt("BLOCKED_BEFORE_START", before, [], [], blockers), 2
    if not start:
        return receipt("READY_OWNER_MUST_EXPLICITLY_OPT_IN_TO_START",
                       before, [], [], []), 0

    started: list[str] = []
    observations: list[dict[str, Any]] = []
    for name, service in ORDER:
        try:
            # Recheck original Compose labels and volume presence at every step.
            fresh = inspect_container(name)
            if (
                not fresh.get("found")
                or fresh.get("compose_project") != REQUIRED_PROJECT
                or fresh.get("compose_service") != service
                or fresh.get("oom_killed")
            ):
                blockers.append("SERVICE_IDENTITY_CHANGED_" + service.upper())
                break
            if service == "postgres" and fresh.get("volume_mount_count", 0) < 1:
                blockers.append("POSTGRES_VOLUME_DISAPPEARED")
                break
            if fresh["status"] == "exited":
                print("START_EXISTING_" + service.upper(), flush=True)
                exec_local("start", name, timeout=25)
                started.append(name)
            elif fresh["status"] != "running":
                blockers.append("UNEXPECTED_SERVICE_STATUS_" + service.upper())
                break
            checked = await_health(name, service)
            observations.append({
                "service": service,
                "state": checked["state"],
                "ready": checked["ready"],
                "reason": checked.get("reason"),
            })
            print(
                ("HEALTH_READY_" if checked["ready"] else "HEALTH_BLOCKED_")
                + service.upper(),
                flush=True,
            )
            if not checked["ready"]:
                blockers.append("SERVICE_NOT_READY_" + service.upper())
                break
        except (DockerUnavailable, ValueError, TypeError):
            blockers.append("DOCKER_START_OR_HEALTH_FAILURE_" + service.upper())
            break

    if blockers:
        status = "PARTIAL_START_STOP_ADVANCING_REVIEW_MANUALLY"
        code = 1
    elif not tcp_open(3000):
        status = "ALL_RUNNING_UI_PORT_3000_NOT_YET_READY"
        code = 1
    else:
        status = "FOUR_EXISTING_SERVICES_HEALTHY_UI_PORT_OPEN"
        code = 0
    return receipt(status, before, started, observations, blockers), code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    opt = parser.add_mutually_exclusive_group()
    opt.add_argument("--check", action="store_true", help="default, read-only")
    opt.add_argument("--start", action="store_true", help="start only existing four services")
    args = parser.parse_args(argv)
    result, code = execute(start=args.start)
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "resources_gb": result.get("memory_gb_decimal"),
        "started": result["started_in_this_attempt"],
        "blockers": result["blockers"],
        "observations": result["observations"],
        "report": str(RECEIPT.relative_to(ROOT)),
    }, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
