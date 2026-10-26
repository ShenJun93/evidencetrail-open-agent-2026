"""Safely diagnose the stopped EXISTING Zetaris Docker stack.

Owner terminal: py -3 diagnose_zetaris_recovery.py

READ ONLY. Never starts, stops, creates, removes or rebuilds containers.
Never enters WSL, reads user files/secrets, or contacts an external server.
Docker CLI calls are gated to a local Docker endpoint.
Only sanitized Docker status/health/mount counts are printed, not env or paths.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "acceptance" / "zetaris-recovery-inspection.json"
NAMES = [
    "zetaris-postgres-1",
    "zetaris-driver-1",
    "zetaris-api-1",
    "zetaris-ui-1",
    "zetaris-init-1",
    "zetaris-bootstrap-1",
]
# Pinned official Zetaris installation guide specifies 8 GB (decimal)
# RECOMMENDED, and preflight fails below 6 GB. Previous 8 GiB gate was
# stricter than sponsor requirements; 7.76 GiB is ~8.33 GB decimal.
MIN_RAM_RECOMMENDED_BYTES = 8_000_000_000
MIN_RAM_PREFLIGHT_BYTES = 6_000_000_000
MIN_CPUS = 4


class DockerUnavailable(Exception):
    pass


def exec_local(*args: str, timeout: int = 12) -> str:
    """Call a single fixed-purpose Docker CLI operation, suppress all stderr."""
    try:
        p = subprocess.run(
            ["docker", *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            check=False, shell=False, cwd=ROOT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DockerUnavailable(type(exc).__name__) from exc
    if p.returncode != 0:
        raise DockerUnavailable("DOCKER_COMMAND_FAILED")
    if len(p.stdout.encode("utf-8")) > 64 * 1024:
        raise DockerUnavailable("OVERSIZED_DOCKER_RESPONSE")
    return p.stdout.strip()


def local_docker_host(host: str) -> bool:
    host = host.strip().lower()
    if host.startswith("npipe:"):
        # Never admit a Windows named pipe pointing to another host.
        return host.startswith(("npipe:////./pipe/", "npipe://./pipe/"))
    if host.startswith("unix:///"):
        return True
    return host.startswith((
        "tcp://localhost:", "tcp://127.0.0.1:", "tcp://[::1]:",
    ))


def verify_endpoint() -> dict[str, Any]:
    # Context inspection is local and has no Docker engine side effects.
    try:
        context = exec_local(
            "context", "inspect", "--format",
            "{{json .Endpoints.docker.Host}}",
        )
        endpoint = json.loads(context)
    except (DockerUnavailable, ValueError, TypeError):
        return {"permitted": False, "reason": "DOCKER_CONTEXT_UNVERIFIED"}
    override = os.environ.get("DOCKER_HOST", "").strip()
    if not isinstance(endpoint, str) or not local_docker_host(endpoint):
        return {"permitted": False, "reason": "REMOTE_OR_UNKNOWN_DOCKER_ENDPOINT"}
    if override and not local_docker_host(override):
        return {"permitted": False, "reason": "REMOTE_DOCKER_HOST_OVERRIDE"}
    # DOCKER_CONTEXT can choose a different context than defaults; docker context
    # inspect without explicit name inspects whichever context Docker selected.
    return {
        "permitted": True,
        "engine_endpoint_type": (
            "LOCAL_NAMED_PIPE_OR_SOCKET" if endpoint.startswith(("npipe://", "unix://"))
            else "LOCAL_LOOPBACK_TCP"
        ),
    }


def formatted(fmt: str, name: str) -> str:
    # No arbitrary command inputs. Names come from the trusted list above.
    return exec_local("inspect", "--format", fmt, name)


def safe_json(fmt: str, name: str) -> Any:
    return json.loads(formatted(fmt, name))


def inspect_container(name: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name}
    try:
        state = safe_json("{{json .State}}", name)
        if not isinstance(state, dict):
            raise ValueError("State was not JSON object")
        mounts = safe_json("{{json .Mounts}}", name)
        if not isinstance(mounts, list):
            raise ValueError("Mounts was not JSON array")
        project = formatted('{{index .Config.Labels "com.docker.compose.project"}}', name)
        service = formatted('{{index .Config.Labels "com.docker.compose.service"}}', name)
        entry.update({
            "found": True,
            "status": str(state.get("Status", ""))[:40],
            "exit_code": state.get("ExitCode"),
            "oom_killed": state.get("OOMKilled") is True,
            "health": str((state.get("Health") or {}).get("Status") or "NOT_CONFIGURED"),
            "compose_project": project[:120],
            "compose_service": service[:120],
            "mount_count": len(mounts),
            "persistent_mount_count": sum(
                isinstance(m, dict) and m.get("Type") in {"volume", "bind"}
                for m in mounts
            ),
            "volume_mount_count": sum(
                isinstance(m, dict) and m.get("Type") == "volume" for m in mounts
            ),
            # Never print mount sources/destinations/volume names or Docker Env.
        })
    except (DockerUnavailable, ValueError, TypeError):
        entry.update({"found": False, "inspection_error": "MISSING_OR_BLOCKED"})
    return entry


def tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.65):
            return True
    except OSError:
        return False


def inspect_docker_resources() -> dict[str, Any]:
    try:
        raw = exec_local("info", "--format", "{{.MemTotal}}|{{.NCPU}}|{{.OSType}}")
        mem, cpus, os_type = raw.split("|", 2)
        memory = int(mem)
        cores = int(cpus)
    except (DockerUnavailable, ValueError, TypeError):
        return {"available": False}
    return {
        "available": True,
        "memory_gib": round(memory / 1024**3, 2),
        "memory_gb_decimal": round(memory / 10**9, 2),
        "cpus": cores,
        "docker_server_linux": os_type.strip().lower() == "linux",
        "meets_recommended_8gb_4cpu": (
            memory >= MIN_RAM_RECOMMENDED_BYTES and cores >= MIN_CPUS
        ),
        "meets_zetaris_preflight_6gb_minimum": (
            memory >= MIN_RAM_PREFLIGHT_BYTES
        ),
    }


def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "purpose": "READ_ONLY_DOCKER_ZETARIS_EXISTING_STACK_RECOVERY_DIAGNOSIS",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "mutations": "NONE",
        "cloud_calls": "NONE",
        "credentials": "NOT_REQUESTED",
        "status": "UNKNOWN",
        "docker_context": verify_endpoint(),
    }
    if not report["docker_context"]["permitted"]:
        report["status"] = "BLOCKED_DOCKER_CONTEXT_NOT_LOCAL"
        return report

    report["resources"] = inspect_docker_resources()
    report["containers"] = [inspect_container(name) for name in NAMES]
    report["ports"] = {
        str(port): tcp_open(port)
        for port in (3000, 8888, 10000)
    }
    try:
        report["project_drive_free_gb"] = round(
            shutil.disk_usage(ROOT).free / 1024**3, 2
        )
    except OSError:
        report["project_drive_free_gb"] = None
    report["project_drive_is_not_necessarily_docker_storage"] = True

    services = {x["name"]: x for x in report["containers"]}
    missing = [n for n in NAMES if not services[n].get("found")]
    projects = {
        services[n].get("compose_project") for n in NAMES
        if services[n].get("found")
    }
    # Docker label is essential for proving these 6 belong to the same
    # previously created Compose stack. Do NOT invent a project name.
    expected_project = projects.pop() if len(projects) == 1 else None
    labels_ok = bool(expected_project) and expected_project not in {"<no value>", "null"}
    postgres = services["zetaris-postgres-1"]
    driver = services["zetaris-driver-1"]
    report["warnings"] = []
    if missing:
        report["warnings"].append("MISSING_OR_UNINSPECTABLE_CONTAINERS")
    if not labels_ok:
        report["warnings"].append("INCONSISTENT_COMPOSE_PROJECT_LABELS")
    if postgres.get("persistent_mount_count", 0) == 0:
        report["warnings"].append("POSTGRES_PERSISTENCE_NOT_VERIFIED_DO_NOT_RECREATE")
    if driver.get("exit_code") == 137:
        report["warnings"].append(
            "DRIVER_EXIT_137_OOM_CONFIRMED"
            if driver.get("oom_killed")
            else "DRIVER_EXIT_137_CAUSE_UNCONFIRMED"
        )
    if report["resources"].get("available") and not report["resources"].get(
        "meets_recommended_8gb_4cpu"
    ):
        report["warnings"].append("DOCKER_RESOURCES_BELOW_SPONSOR_RECOMMENDED_8GB_4CPU")
    if not report["resources"].get("available"):
        report["warnings"].append("DOCKER_MEMORY_CPU_UNVERIFIED")
    if any(s.get("oom_killed") for s in services.values()):
        report["warnings"].append("ONE_OR_MORE_CONTAINERS_OOM_KILLED")

    report["same_compose_project"] = labels_ok
    report["compose_project"] = expected_project if labels_ok else None
    report["postgres_persistent_mount_present"] = (
        postgres.get("persistent_mount_count", 0) > 0
    )
    if missing or not labels_ok or not report["postgres_persistent_mount_present"]:
        report["status"] = "STOP_REVIEW_STACK_IDENTITY_OR_PERSISTENCE"
    elif (
        not report["resources"].get("meets_zetaris_preflight_6gb_minimum")
        or not report["resources"].get("meets_recommended_8gb_4cpu")
        or not report["resources"].get("docker_server_linux")
        or any(s.get("oom_killed") for s in services.values())
    ):
        report["status"] = "STOP_REVIEW_OOM_OR_DOCKER_RESOURCES"
    elif all(services[n].get("status") == "exited" for n in NAMES):
        report["status"] = "STOPPED_STACK_VERIFIED_MANUAL_START_CAN_BE_CONSIDERED"
    elif any(services[n].get("status") == "running" for n in NAMES):
        report["status"] = "PARTIAL_OR_RUNNING_STACK_REVIEW_HEALTH_BEFORE_CHANGES"
    else:
        report["status"] = "NEEDS_OWNER_REVIEW"
    report["proposed_action_if_approved"] = (
        "Use original existing Compose project or explicitly start only "
        "postgres, driver, api, ui; DO NOT rerun init/bootstrap and "
        "NEVER use docker compose down -v. No action was performed."
    )
    return report


def main() -> None:
    result = build_report()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    brief = {
        "status": result["status"],
        "docker_context": result["docker_context"],
        "resources": result.get("resources"),
        "containers": result.get("containers", []),
        "warnings": result.get("warnings", []),
        "postgres_persistent_mount_present": result.get(
            "postgres_persistent_mount_present"
        ),
        "report": str(OUT.relative_to(ROOT)),
    }
    print(json.dumps(brief, ensure_ascii=False))


if __name__ == "__main__":
    main()
