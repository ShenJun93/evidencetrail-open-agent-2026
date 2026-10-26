"""Create ONLY a never-before-existing Milton namespace and two CSV filestore tables.

Exact vendor Lightning SQL command templates, locally authenticated SQL Editor.
Intentionally no DROP, DELETE, INSERT, ALTER, TRUNCATE or permission changes.
Never reads a token except from a specifically selected ignored .env.local.
Does not restart Docker or alter the Yagi namespace.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import urllib.error
import urllib.request
from uuid import uuid4

from evidencetrail.adapters.zetaris_sql_editor import (
    SqlEditorContractError, NoRedirect, validate_config,
)
from run_zetaris_preflight import read_local_env
from evidencetrail.zetaris_cross_issuer import query_sql_editor, evaluate_sql_rows

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "acceptance" / "logs" / "zetaris-cross-issuer" / "registration-receipt.json"
BASE = "/home/zetaris/customer-data/shared/evidencetrail-milton-2024"
DATABASE = "EVIDENCETRAIL_MILTON"
SQL = (
    'CREATE LIGHTNING DATABASE EVIDENCETRAIL_MILTON DESCRIBE BY '
    '"Curated NOAA NHC and Florida Governor 2024 advisory chronology, not raw signed 2024 archive" '
    'OPTIONS ()',
    'CREATE LIGHTNING FILESTORE TABLE nhc_selected_advisories '
    'FROM EVIDENCETRAIL_MILTON FORMAT CSV OPTIONS ('
    'path "' + BASE + '/nhc_selected_advisories.csv", '
    'header "true", inferSchema "true")',
    'CREATE LIGHTNING FILESTORE TABLE florida_governor_records '
    'FROM EVIDENCETRAIL_MILTON FORMAT CSV OPTIONS ('
    'path "' + BASE + '/florida_governor_records.csv", '
    'header "true", inferSchema "true")',
)


def send_sql(sql: str, conf: dict[str, str]) -> dict:
    """Literal allowlist only, single statement, local REST no redirects."""
    if sql not in (*SQL, "SHOW LIGHTNING DATABASES"):
        raise ValueError("UNAPPROVED_SQL_STATEMENT")
    validate_config(conf["ZETARIS_REST_URL"], conf["ZETARIS_ORG_ID"],
                    conf["ZETARIS_API_KEY"])
    req = urllib.request.Request(
        conf["ZETARIS_REST_URL"].rstrip("/") + "/sql-editor/sqls/run",
        data=json.dumps({"queryId":str(uuid4()),"sql":sql,
                         "source":"SqlEditor","limit":20},
                        separators=(",",":")).encode(),
        method="POST",
        headers={
            "Content-Type":"application/json",
            "Authorization":"Bearer " + conf["ZETARIS_API_KEY"],
            "X-Org-ID":conf["ZETARIS_ORG_ID"],
            "X-Request-ID":str(uuid4()),
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
            if response.status != 200:
                raise SqlEditorContractError("SQL_REGISTRATION_HTTP_NOT_200")
            body = response.read(256001)
    except urllib.error.HTTPError as e:
        raise SqlEditorContractError("SQL_REGISTRATION_HTTP_" + str(e.code)) from None
    except OSError:
        raise SqlEditorContractError("SQL_REGISTRATION_CONNECTION_FAILED") from None
    if len(body) > 256000:
        raise SqlEditorContractError("SQL_REGISTRATION_RESPONSE_TOO_LARGE")
    try:
        payload=json.loads(body)
    except (ValueError,UnicodeError):
        raise SqlEditorContractError("SQL_REGISTRATION_RESPONSE_NOT_JSON") from None
    if not isinstance(payload,dict) or "error" in payload or payload.get("success") is False:
        raise SqlEditorContractError("SQL_REGISTRATION_APPLICATION_ERROR")
    return payload


def exists(conf: dict[str,str]) -> bool:
    rows=send_sql("SHOW LIGHTNING DATABASES",conf).get("data")
    if not isinstance(rows,list):
        raise SqlEditorContractError("DATABASE_INVENTORY_RESPONSE_INVALID")
    names={str(row[0]).strip().upper() if isinstance(row,list) and row
           else str(row.get("name","")).upper() if isinstance(row,dict)
           else "" for row in rows}
    return DATABASE in names


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--approve-isolated-new-tables",action="store_true")
    parser.add_argument("--env-file",default=None,
                        help="explicitly select project's ignored .env.local")
    args=parser.parse_args()
    report={
        "kind":"EVIDENCETRAIL_ISOLATED_MILTON_LIGHTNING_FILESTORE_REGISTRATION_V1",
        "status":"DRY_RUN_NO_NETWORK",
        "sql_sha12":[sha256(q.encode()).hexdigest()[:12] for q in SQL],
        "schema":DATABASE,
        "table_names":["nhc_selected_advisories","florida_governor_records"],
        "file_paths":[BASE+"/nhc_selected_advisories.csv",
                      BASE+"/florida_governor_records.csv"],
        "schema_modified":["NONE"],
        "yagi_modified":False,
        "original_publisher_2024_first_availability_proven":False,
        "instance_sponsor_eligibility_proven":False,
        "authentication_value_in_receipt":False,
    }
    exit_code=0
    if args.execute:
        if not args.approve_isolated_new_tables or args.env_file!=".env.local":
            report["status"]="REFUSED_APPROVAL_OR_EXPLICIT_CONFIG_MISSING"
            exit_code=2
        else:
            try:
                conf=read_local_env(args.env_file)
                if exists(conf):
                    report["status"]="REFUSED_TARGET_DATABASE_ALREADY_EXISTS"
                    exit_code=2
                else:
                    report["status"]="REGISTRATION_ATTEMPT_STARTED"
                    for i,query in enumerate(SQL):
                        # SQL statement is a literal project-owned allowlist.
                        send_sql(query,conf)
                        report["completed_statement_count"]=i+1
                        report["schema_modified"]=["EVIDENCETRAIL_MILTON"]
                    if not exists(conf):
                        raise SqlEditorContractError("DATABASE_NOT_IN_CATALOG_AFTER_CREATE")
                    # Independent actual SQL data consumption is a second gate.
                    nhc,nhc_id,nhc_digest=query_sql_editor(
                        "NOAA_NHC",base_url=conf["ZETARIS_REST_URL"],
                        org_id=conf["ZETARIS_ORG_ID"],
                        api_key=conf["ZETARIS_API_KEY"])
                    fl,fl_id,fl_digest=query_sql_editor(
                        "FLORIDA_GOVERNOR",base_url=conf["ZETARIS_REST_URL"],
                        org_id=conf["ZETARIS_ORG_ID"],
                        api_key=conf["ZETARIS_API_KEY"])
                    actual=evaluate_sql_rows(nhc,fl,clock="2024-10-07T11:00:00Z")
                    report["actual_sql_source_rows_consumed"]=actual[
                        "sql_decoded_issuer_row_counts"]
                    report["actual_replay_latest_nhc_mph"]=actual["latest_noaa_wind_mph"]
                    report["actual_replay_latest_florida_counties"]=actual[
                        "latest_florida_emergency_counties"]
                    report["status"]="TWO_NEW_REAL_SQL_ROWSETS_CONSUMED_LOCAL_ONLY"
            except (SqlEditorContractError,KeyError,OSError,ValueError) as exc:
                report["status"]="REGISTRATION_OR_SQL_RECEIPT_BLOCKED"
                report["safe_error_code"]=(
                    str(exc) if isinstance(exc,SqlEditorContractError) else
                    type(exc).__name__)
                exit_code=2
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":report["status"],
        "completed_statements":report.get("completed_statement_count",0),
        "actual_rows":report.get("actual_sql_source_rows_consumed"),
        "safe_error_code":report.get("safe_error_code"),
        "receipt":str(REPORT),
    }))
    return exit_code


if __name__=="__main__":
    raise SystemExit(main())
