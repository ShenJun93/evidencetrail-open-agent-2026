"""Stage strictly-curated Milton records for Zetaris; NEVER import automatically.

Default: generate two CSV files under gitignored acceptance/logs for an admin
to register through a previously approved Zetaris-accessible data source.
--live requires explicit no-fee access confirmation and only performs TWO
read-only SQL Editor SELECT calls, never DDL/DML, Docker start, or AI calls.
"""
from __future__ import annotations

import argparse
import csv
from io import StringIO
from hashlib import sha256
import json
import os
from pathlib import Path
import socket

from evidencetrail.cross_issuer_milton import _fl_metadata
from evidencetrail.external_milton import _load as nhc_catalog
from evidencetrail.zetaris_cross_issuer import (
    COLS, SQL, evaluate_sql_rows, query_sql_editor,
)

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"acceptance"/"logs"/"zetaris-cross-issuer"


def import_rows() -> tuple[list[dict],list[dict]]:
    _, nhc=nhc_catalog()
    _, florida=_fl_metadata()
    a=[]
    for record in nhc:
        a.append(dict(
            source_id=record.source_id,issuer_family="NOAA_NHC",
            claim_type="maximum_sustained_wind_mph",locator=record.locator,
            excerpt=record.excerpt,excerpt_sha256=sha256(record.excerpt.encode()).hexdigest(),
            value_int=record.observation_fields["reported_maximum_sustained_wind_mph"],
            issue_utc=record.issued_at_claimed_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            displayed_date_local=None,
        ))
    b=[]
    for record in florida:
        excerpt=record["description"]
        b.append(dict(
            source_id=record["id"],issuer_family="FLORIDA_GOVERNOR",
            claim_type=record["claim_type"],locator=record["url"],
            excerpt=excerpt,excerpt_sha256=sha256(excerpt.encode()).hexdigest(),
            value_int=record["value"],issue_utc=None,
            displayed_date_local=record["displayed_date_local"],
        ))
    return a,b


def write_stage() -> dict:
    nhc,fl=import_rows()
    OUT.mkdir(parents=True,exist_ok=True)
    names=("nhc_selected_advisories.csv","florida_governor_records.csv")
    # Never overwrite an operator-modified staged file. Only write if absent
    # or byte-for-byte identical to the reproducible curated content.
    for filename,rows in zip(names,(nhc,fl)):
        buf=StringIO(newline="")
        wr=csv.DictWriter(buf,fieldnames=COLS)
        wr.writeheader()
        wr.writerows(rows)
        target=OUT/filename
        newbytes=buf.getvalue().encode("utf-8")
        if target.exists():
            if target.read_bytes()!=newbytes:
                raise ValueError("STAGED_CSV_CHANGED_REFUSE_OVERWRITE")
        else:
            target.write_bytes(newbytes)
    return {
        "state":"CURATED_CSV_STAGED_NO_ZETARIS_WRITE",
        "files":[str(OUT/n) for n in names],
        "expected_row_counts":{"NOAA_NHC":len(nhc),"FLORIDA_GOVERNOR":len(fl)},
        "target_tables":["EVIDENCETRAIL_MILTON.nhc_selected_advisories",
                         "EVIDENCETRAIL_MILTON.florida_governor_records"],
        "file_is_automatically_visible_inside_zetaris":False,
        "source_articles_are_curated_paraphrases_not_immutable_original_bytes":True,
        "sql_digest_sha12":{k:sha256(v.encode()).hexdigest()[:12] for k,v in SQL.items()},
        "source_organization_verification_or_original_2024_publication":False,
        "status":"NEEDS_OPERATOR_REGISTER_APPROVED_DATASOURCE",
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prepare",action="store_true",help="default; CSV only; no network")
    p.add_argument("--check",action="store_true",help="read-only loopback port check; no credentials")
    p.add_argument("--live",action="store_true",help="two real local read-only SQL queries")
    p.add_argument("--approve-local-zetaris",action="store_true")
    p.add_argument("--sponsor-access-confirmed",action="store_true")
    p.add_argument("--at",default="2024-10-07T11:00:00Z")
    p.add_argument("--strict",action="store_true")
    p.add_argument("--env-file",help="explicit ignored project .env.local; never printed")
    args=p.parse_args()
    if sum((args.prepare,args.check,args.live))>1:
        p.error("choose one mode")
    report=write_stage()
    code=0
    if args.check:
        with socket.socket() as s:
            s.settimeout(0.5)
            listening=(s.connect_ex(("127.0.0.1",8888))==0)
        report.update({
            "status":"LOCAL_REST_PORT_OPEN_NOT_YET_AUTHENTICATED"
                    if listening else "LOCAL_REST_PORT_UNAVAILABLE",
            "loopback_8888_open":listening,
            "live_sql_requests_made":0,
        })
    if args.live:
        if not (args.approve_local_zetaris and args.sponsor_access_confirmed):
            report.update({"status":"BLOCKED_MISSING_EXPLICIT_LIVE_AUTHORIZATION",
                           "live_sql_requests_made":0})
            code=2
        else:
            # Explicit user-owned ignored config, never auto-read and never
            # placed in a receipt, subprocess argument or exception output.
            config={k:os.environ.get(k,"") for k in
                    ("ZETARIS_REST_URL","ZETARIS_ORG_ID","ZETARIS_API_KEY")}
            if args.env_file:
                from run_zetaris_preflight import read_local_env
                allowed=read_local_env(args.env_file)
                for k in config:
                    if k in allowed:
                        config[k]=allowed[k]
            url=config["ZETARIS_REST_URL"]
            org=config["ZETARIS_ORG_ID"]
            key=config["ZETARIS_API_KEY"]
            attempt=0
            try:
                attempt+=1
                nhc,id_a,digest_a=query_sql_editor(
                    "NOAA_NHC",base_url=url,org_id=org,api_key=key)
                attempt+=1
                fl,id_b,digest_b=query_sql_editor(
                    "FLORIDA_GOVERNOR",base_url=url,org_id=org,api_key=key)
                replay=evaluate_sql_rows(nhc,fl,clock=args.at,strict=args.strict)
                report.update({
                    "status":"TWO_LOCAL_SQL_RESPONSES_CONSUMED_NOT_ORIGIN_ATTESTED",
                    "live_sql_requests_made":attempt,
                    "result":replay,
                    "sql_invocation_id_sha12":[sha256(x.encode()).hexdigest()[:12]
                                                 for x in (id_a,id_b)],
                    "real_sql_transport_claim_requires_actual_local_server":True,
                    "nightshift_called":False,
                    "sponsor_eligibility_certified":False,
                })
            except Exception as exc:
                report.update({
                    "status":"BLOCKED_LIVE_SQL_OR_ROW_CONTRACT",
                    "error_class":type(exc).__name__,
                    "sql_requests_attempted":attempt,
                    "raw_error_message_hidden_to_protect_credentials":True,
                })
                code=2
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"last-preflight.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":report["status"],
        "expected_row_counts":report["expected_row_counts"],
        "local_8888_open":report.get("loopback_8888_open"),
        "sql_queries_attempted":report.get("sql_requests_attempted",
                                          report.get("live_sql_requests_made",0)),
        "receipt":str(OUT/"last-preflight.json"),
    }))
    return code


if __name__=="__main__":
    raise SystemExit(main())
