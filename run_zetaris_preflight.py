"""Explicit Zetaris two-source preflight. No network unless --live is supplied.

From the project root:
    py -3 run_zetaris_preflight.py --check
    py -3 run_zetaris_preflight.py --check --env-file .env.local
    py -3 run_zetaris_preflight.py --live --env-file .env.local --sponsor-access-confirmed

Credentials must never be pasted into chat, committed, or printed. The real
HTTP contract and Zetaris sponsor-origin attestation are SEPARATE gates.
This tool does NOT call Meterless, Nightshift, NVIDIA or any paid API.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from evidencetrail.adapters.zetaris import ZetarisAdapter
from evidencetrail.firewall import filter_sources, jurisdiction_ok
from evidencetrail.models import RunRequest, SponsorOutcome
from evidencetrail.reducer import decide

ROOT = Path(__file__).resolve().parent
REQUIRED = (
    "ZETARIS_QUERY_URL",
    "ZETARIS_API_KEY",
    "ZETARIS_PUBLIC_SQL",
    "ZETARIS_CAPACITY_SQL",
)
ALLOW_ENV = set(REQUIRED + (
    "ZETARIS_TARGETED_PUBLIC_SQL", "ZETARIS_REST_URL",
    "ZETARIS_REST_MODE", "ZETARIS_ORG_ID",
))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def read_local_env(path: str | None) -> dict[str, str]:
    """Only an owner-supplied ignored .env.local in THIS project, never auto-read."""
    if not path:
        return {}
    selected = (ROOT / path).resolve()
    if selected != (ROOT / ".env.local").resolve() or selected.name != ".env.local":
        raise ValueError("only the project .env.local may be explicitly loaded")
    if selected.stat().st_size > 65536:
        raise ValueError("local config exceeds 64KiB")
    config: dict[str, str] = {}
    for line in selected.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in ALLOW_ENV:
            continue
        if len(value) > 8192:
            raise ValueError("oversized Zetaris configuration value")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        config[key] = value
    return config


def _relation(sql: str) -> str:
    match = re.search(r"\bfrom\s+([A-Za-z_][\w.$]*)\b", sql, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def validate_config(config: dict[str, str], allow_loopback: bool = False) -> dict:
    issues: list[str] = []
    mode = config.get("ZETARIS_REST_MODE", "open_sql_query").strip().lower() or "open_sql_query"
    if mode == "sql_editor":
        from evidencetrail.adapters.zetaris_sql_editor import (
            validate_config as validate_local_sql_api,
            SqlEditorContractError,
        )
        url = config.get("ZETARIS_REST_URL", "").strip()
        try:
            validate_local_sql_api(
                url,
                config.get("ZETARIS_ORG_ID", ""),
                config.get("ZETARIS_API_KEY", ""),
            )
        except SqlEditorContractError as exc:
            issues.append(str(exc))
        if not allow_loopback:
            issues.append("local_loopback_requires_explicit_opt_in")
    else:
        url = config.get("ZETARIS_QUERY_URL", "").strip()
        if mode != "open_sql_query":
            issues.append("unsupported_ZETARIS_REST_MODE")
        parsed_old = urlsplit(url)
        old_host = (parsed_old.hostname or "").lower()
        if not url:
            issues.append("missing_ZETARIS_QUERY_URL")
        elif (
            parsed_old.scheme not in {"https", "http"}
            or not old_host
            or parsed_old.username is not None
            or parsed_old.password is not None
            or bool(parsed_old.query)
            or bool(parsed_old.fragment)
        ):
            issues.append("unsafe_or_invalid_endpoint_URL")
        else:
            is_loopback = old_host in {"localhost", "127.0.0.1", "::1"}
            try:
                is_loopback = is_loopback or ipaddress.ip_address(old_host).is_loopback
            except ValueError:
                pass
            if parsed_old.scheme != "https" and not (allow_loopback and is_loopback):
                issues.append("remote_HTTP_disallowed_or_loopback_not_opted_in")
            if parsed_old.path in {"", "/"}:
                issues.append("endpoint_has_no_OpenSqlQuery_path")
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()

    token = config.get("ZETARIS_API_KEY", "").strip()
    if not token or token.lower() in {"null", "none", "changeme", "your-token", "<redacted>"}:
        issues.append("missing_actual_ZETARIS_API_KEY")

    queries: dict[str, dict] = {}
    for label, key in (("public", "ZETARIS_PUBLIC_SQL"), ("synthetic_capacity", "ZETARIS_CAPACITY_SQL")):
        sql = config.get(key, "").strip()
        if mode == "sql_editor":
            from evidencetrail.adapters.zetaris_sql_editor import (
                validate_sql, SqlEditorContractError,
            )
            from evidencetrail.models import RecordKind
            kind = (RecordKind.GOVERNMENT_NEWS
                    if label == "public" else RecordKind.SYNTHETIC_CAPACITY)
            try:
                validate_sql(sql, kind)
                shape_ok = True
            except SqlEditorContractError:
                shape_ok = False
        else:
            shape_ok = bool(sql) and ZetarisAdapter._read_only_select(sql)
        relation = _relation(sql) if shape_ok else ""
        if not shape_ok or not relation:
            issues.append(f"missing_or_invalid_readonly_{key}")
        queries[label] = {
            "sql_configured": bool(sql),
            "readonly_shape": bool(shape_ok and relation),
            "sql_sha16": digest(sql) if sql else None,
            "source_table_sha16": digest(relation) if relation else None,
        }
    public = _relation(config.get("ZETARIS_PUBLIC_SQL", ""))
    capacity = _relation(config.get("ZETARIS_CAPACITY_SQL", ""))
    if public and capacity and public == capacity:
        issues.append("public_and_synthetic_must_read_distinct_tables")
    if public and capacity and (
        config.get("ZETARIS_PUBLIC_SQL", "").strip().lower()
        == config.get("ZETARIS_CAPACITY_SQL", "").strip().lower()
    ):
        issues.append("duplicate_SQL_query")

    return {
        "status": "READY_FOR_EXPLICIT_LIVE_ATTEMPT" if not issues else "BLOCKED_NOT_CONFIGURED",
        "issues": list(dict.fromkeys(issues)),
        "url_scheme": parsed.scheme or None,
        # No raw host, endpoint path, SQL or bearer token in any JSON/console.
        "endpoint_host_sha16": digest(host) if host else None,
        "token_present": bool(token),
        "queries": queries,
        "not_a_sponsor_attestation": True,
        "rest_mode": mode,
    }


def replay_over_real_rows(rows: list) -> dict:
    """Actual as-of/jurisdiction firewall + deterministic decision; NO H-MEM."""
    results = {}
    for name in ("yagi_1630_lucyen", "yagi_1645_lucyen"):
        source = ROOT / "samples" / "inputs" / (name + ".json")
        req_raw = json.loads(source.read_text(encoding="utf-8"))
        req_raw["sample_mode"] = False
        req = RunRequest.from_dict(req_raw)
        local = [r for r in rows if jurisdiction_ok(r, req.province_2024, req.district_2024)]
        eligible, excluded = filter_sources(local, req.as_of_utc, req.mode)
        verdict, _rationale, missing, used = decide(req, eligible)
        results[name] = {
            "verdict": verdict.value,
            "eligible_count": len(eligible),
            "excluded_count": len(excluded),
            "cited_count": len(used),
            "cited_source_hashes": [digest(sid) for sid in used],
            "missing_fact_count": len(missing),
            "source_mode": "TWO_REAL_HTTP_ROWSETS_IF_LIVE_EXECUTION_SUCCEEDED",
            "no_memory_or_model_calls": True,
        }
    return results


def run(config: dict[str, str], live: bool, allow_loopback: bool,
        sponsor_access_confirmed: bool) -> tuple[dict, int]:
    summary = validate_config(config, allow_loopback=allow_loopback)
    report: dict = {
        "schema_version": "1",
        "mode": "EXPLICIT_LIVE_ZETARIS_TWO_SQL" if live else "CONFIG_CHECK_NO_NETWORK",
        "preflight": summary,
        "network_called": False,
        "instance_identity_independently_verified": False,
        "sponsor_eligibility": "NOT_VERIFIED",
        "meterless_engine": "NOT_CALLED",
        "nightshift": "NOT_CALLED",
        "nvidia": "NOT_CALLED",
    }
    if summary["status"] != "READY_FOR_EXPLICIT_LIVE_ATTEMPT":
        report["result"] = "BLOCKED_CONFIGURATION"
        return report, 2
    if not live:
        report["result"] = "READY_TO_TEST_NOT_YET_QUERIED"
        return report, 0
    if not sponsor_access_confirmed:
        report["result"] = "BLOCKED_EVENT_ACCESS_NOT_CONFIRMED"
        return report, 2

    # Explicit owner-supplied environment, not an implicit dotenv auto-load.
    # ZetarisAdapter internally bounds both response bodies and validates kinds.
    keys = tuple(sorted(ALLOW_ENV))
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ.update({key: config.get(key, "") for key in keys})
        adapter = ZetarisAdapter(sample_mode=False)
        rows, calls = adapter.fetch_two_logical_sources()
    finally:
        for key, before in previous.items():
            if before is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = before

    report["network_called"] = True
    report["http_contract_calls"] = [
        {
            "engine": call.engine,
            "transport_outcome": call.outcome.value,
            "contract_label": call.contract_label,
            "row_count": call.row_count,
            "invocation_id_sha16": digest(call.invocation_id) if call.invocation_id else None,
        }
        for call in calls
    ]
    sql_queries = [c for c in calls if c.engine.startswith("query:")]
    accepted = (
        len(sql_queries) == 2
        and all(c.outcome == SponsorOutcome.REAL_SUCCESS for c in sql_queries)
        and len(rows) > 1
    )
    # Exactly a full page without pagination is incomplete evidence.
    if any(c.row_count is not None and c.row_count >= 100 for c in sql_queries):
        accepted = False
        report["pagination_limit"] = "100_ROWS_PAGINATION_NOT_VERIFIED"
    if not accepted:
        report["result"] = "LIVE_QUERY_TRANSPORT_OR_SCHEMA_BLOCKED"
        return report, 1
    report["source_counts"] = {
        "government": sum(r.record_kind.value == "GOVERNMENT_NEWS" for r in rows),
        "synthetic_capacity": sum(r.record_kind.value == "SYNTHETIC_CAPACITY" for r in rows),
    }
    report["computed_replays_without_memory_or_model"] = replay_over_real_rows(rows)
    report["result"] = "LIVE_SQL_ROWS_CONSUMED_INSTANCE_ORIGIN_STILL_NEEDS_INDEPENDENT_EVIDENCE"
    return report, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Redacted Zetaris two-source readiness")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="no network (default)")
    group.add_argument("--live", action="store_true", help="attempt exactly two real SQL queries")
    parser.add_argument("--env-file", help="explicitly load only ignored project .env.local")
    parser.add_argument("--allow-loopback", action="store_true", help="HTTP permitted only on loopback")
    parser.add_argument("--sponsor-access-confirmed", action="store_true",
                        help="owner confirms no-cost hackathon instance access")
    args = parser.parse_args(argv)
    try:
        config = {key: os.environ.get(key, "") for key in ALLOW_ENV}
        config.update(read_local_env(args.env_file))
        report, exit_code = run(config, args.live, args.allow_loopback,
                                args.sponsor_access_confirmed)
    except (OSError, ValueError, KeyError) as exc:
        report, exit_code = {
            "mode": "CONFIG_FAILURE",
            "result": "BLOCKED_CONFIG_PARSING",
            "error_type": type(exc).__name__,
            "secrets_exposed": False,
        }, 2
    out = ROOT / "acceptance" / (
        "zetaris-live-contract-receipt.json" if args.live
        else "zetaris-config-preflight.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "network_called": report.get("network_called", False),
        "sponsor_eligibility": report.get("sponsor_eligibility", "NOT_VERIFIED"),
        "report": str(out.relative_to(ROOT)),
    }, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
