"""Read-only diagnosis of the EXISTING local Zetaris installation on MAIN-PC.

Usage: py -3 inspect_local_zetaris.py

No downloads, Docker starts/stops, container changes, credential inspection,
login, internet requests or Windows security setting changes. The only network
activity is TCP connect probes to 127.0.0.1 ports 3000, 8888 and 10000.

The report is a local readiness diagnostic, NOT Zetaris integration proof.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "acceptance" / "zetaris-local-readiness.json"
RELEVANT = re.compile(
    r"zetaris|lightning|z[\-_]?spark|data[\-_]?steward|zetarishackathon",
    flags=re.IGNORECASE,
)


def run_readonly(argv: list[str], timeout: int = 10) -> tuple[str, str]:
    """Return only CLI stdout and a generic status; never expose raw stderr."""
    try:
        proc = subprocess.run(
            argv, cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            shell=False, check=False,
        )
    except FileNotFoundError:
        return "", "COMMAND_NOT_INSTALLED"
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT"
    except (OSError, ValueError):
        return "", "EXECUTION_BLOCKED"
    if proc.returncode != 0:
        return "", "NONZERO_EXIT"
    if len(proc.stdout) > 256 * 1024:
        return "", "OUTPUT_TOO_LARGE"
    return proc.stdout, "OK"


def socket_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.9):
            return True
    except OSError:
        return False


def is_local_docker_endpoint(raw: str) -> bool:
    """Only local named pipe, unix socket or loopback TCP, never cloud SSH."""
    addr = raw.strip().lower()
    if addr.startswith(("npipe://", "unix://")):
        return True
    return any(
        addr.startswith(prefix)
        for prefix in (
            "tcp://127.0.0.1:", "tcp://localhost:", "tcp://[::1]:",
        )
    )


def parse_containers(raw: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in raw.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("Names") or "")[:150]
        image = str(item.get("Image") or "")[:150]
        if not RELEVANT.search(name + " " + image):
            continue
        state = str(item.get("State") or "")
        status = str(item.get("Status") or "")[:100]
        entries.append({
            "name": name, "state": state[:50], "status": status,
            # Image repository labels are omitted (may expose private registries).
        })
    return entries[:80]


def parse_compose_projects(raw: str) -> list[dict[str, str]]:
    try:
        values = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(values, list):
        return []
    out = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "")[:120]
        paths = str(item.get("ConfigFiles") or "")
        if not RELEVANT.search(name + " " + paths):
            continue
        out.append({
            "name": name,
            "status": str(item.get("Status") or "")[:100],
            "compose_config_located": bool(paths),
            # Do NOT print the real Windows/WSL installation path automatically.
        })
    return out[:30]


def run() -> dict[str, Any]:
    report: dict[str, Any] = {
        "purpose": "READ_ONLY_LOCAL_ZETARIS_RECOVERY",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "changes_to_machine": "NONE",
        "cloud_requests": "NONE",
        "credential_access": "NONE",
        "status": "NOT_VERIFIED",
    }

    # TCP checks do not authenticate, read data, or make product API calls.
    report["local_tcp_open"] = {
        "zetaris_ui_candidate_3000": socket_open(3000),
        "zetaris_rest_candidate_8888": socket_open(8888),
        "zetaris_jdbc_candidate_10000": socket_open(10000),
        "meterless_power_candidate_8088": socket_open(8088),
    }

    context_raw, context_result = run_readonly(["docker", "context", "show"], timeout=6)
    report["docker_context_check"] = context_result
    if context_result == "OK":
        # Docker context is a local alias, not a user secret.
        report["docker_context"] = context_raw.strip()[:120]

    endpoint_raw, endpoint_check = run_readonly(
        ["docker", "context", "inspect",
         "--format", "{{json .Endpoints.docker.Host}}"], timeout=6,
    )
    report["docker_endpoint_check"] = endpoint_check
    try:
        current_endpoint = json.loads(endpoint_raw.strip())
    except (ValueError, TypeError):
        current_endpoint = None
    # DOCKER_HOST can override CLI context. Neither remote Docker host nor SSH
    # should be contacted even for a supposedly read-only "docker ps".
    host_override = os.environ.get("DOCKER_HOST", "").strip()
    valid_endpoint = isinstance(current_endpoint, str) and (
        is_local_docker_endpoint(current_endpoint)
    )
    if host_override and not is_local_docker_endpoint(host_override):
        valid_endpoint = False
    report["docker_endpoint_local_only"] = valid_endpoint

    if valid_endpoint:
        ps_raw, ps_status = run_readonly(
            ["docker", "ps", "-a", "--format", "{{json .}}"], timeout=12,
        )
        projects_raw, projects_status = run_readonly(
            ["docker", "compose", "ls", "--format", "json"], timeout=12,
        )
    else:
        ps_raw, ps_status = "", "BLOCKED_REMOTE_OR_UNKNOWN_DOCKER_CONTEXT"
        projects_raw, projects_status = "", "BLOCKED_REMOTE_OR_UNKNOWN_DOCKER_CONTEXT"

    report["docker_ps_check"] = ps_status
    report["zetaris_related_containers"] = (
        parse_containers(ps_raw) if ps_status == "OK" else []
    )
    report["docker_compose_check"] = projects_status
    report["zetaris_related_compose_projects"] = (
        parse_compose_projects(projects_raw) if projects_status == "OK" else []
    )

    # Windows-specific capability check, without entering WSL or running Linux
    # commands. Do not report the names of unrelated Linux user distros.
    wsl_raw, wsl_status = run_readonly(["wsl", "--list", "--quiet"], timeout=7)
    report["wsl_distro_check"] = wsl_status
    if wsl_status == "OK":
        normalized = wsl_raw.replace("\x00", "")
        report["ubuntu_wsl_present"] = any(
            "ubuntu" in line.lower() for line in normalized.splitlines()
        )

    ports = report["local_tcp_open"]
    containers = report["zetaris_related_containers"]
    if ports["zetaris_ui_candidate_3000"] or ports["zetaris_rest_candidate_8888"]:
        report["status"] = "LOCAL_PORT_OPEN_REQUIRES_ZETARIS_IDENTITY_AND_SQL_CHECK"
    elif any(
        c["state"].lower() == "running"
        or c["status"].lower().startswith("up ")
        for c in containers
    ):
        report["status"] = "CONTAINERS_RUNNING_BUT_LOCAL_PORTS_CLOSED"
    elif containers or report["zetaris_related_compose_projects"]:
        report["status"] = "EXISTING_ZETARIS_STACK_FOUND_BUT_NOT_SERVING"
    elif ps_status != "OK":
        report["status"] = "DOCKER_UNAVAILABLE_OR_BLOCKED_IN_THIS_TERMINAL"
    else:
        report["status"] = "NO_ZETARIS_STACK_IN_CURRENT_DOCKER_CONTEXT"

    report["important"] = (
        "Historical Zetaris 9/9 setup does NOT prove a live app source query. "
        "This diagnostic never starts containers; review existing compose "
        "directory, resource limits and project before an owner-approved start."
    )
    return report


if __name__ == "__main__":
    result = run()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary = {
        "status": result["status"],
        "local_ports": result["local_tcp_open"],
        "docker_ps": result["docker_ps_check"],
        "matching_containers": result["zetaris_related_containers"],
        "compose_projects": result["zetaris_related_compose_projects"],
        "report": str(REPORT_PATH.relative_to(ROOT)),
    }
    print(json.dumps(summary, ensure_ascii=False))
