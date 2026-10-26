"""Inspect why admitted claims change when a pinned source is removed.

OFFLINE by default. Opt-in local Zetaris SQL mode uses the existing read-only
two issuer adapters. Neither mode calls NVIDIA/Nightshift/other models, edits
source records or claims external first-publication timestamps.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from evidencetrail.claim_ledger_milton import curated_milton_manifest
from evidencetrail.why_counterfactual import explain_why
from evidencetrail.zetaris_cross_issuer import _canonical_rows, query_sql_editor
from evidencetrail.models import ReplayMode
from run_zetaris_cross_issuer import import_rows
from run_zetaris_preflight import read_local_env

DEFAULT_CLOCK = "2024-10-07T11:00:00Z"
DEFAULT_RECEIPT=Path("acceptance/logs/why-source-counterfactual.json")


def evaluate(nhc: list[dict],florida: list[dict],*,
             as_of_utc: str=DEFAULT_CLOCK,strict: bool=False) -> dict:
    if type(strict) is not bool:
        raise ValueError("WHY_STRICT_REQUIRES_BOOL")
    # The original seven-row production manifest is enforced BEFORE deletion
    # simulations; no caller-provided replacement pins, sources or clocks.
    sources=_canonical_rows(nhc,florida)
    pins,rules=curated_milton_manifest()
    result=explain_why(
        sources,pins,rules,as_of_utc=as_of_utc,
        mode=(ReplayMode.STRICT_AS_OF_2024 if strict
              else ReplayMode.REPORTED_DATELINE_REPLAY),
    )
    result["dataset_identity"]="CURATED_NOAA_NHC_AND_FLORIDA_GOVERNOR_7_ROWS"
    result["simulation_not_a_live_disaster_warning"]=True
    return result


def main(argv: list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of",default=DEFAULT_CLOCK)
    parser.add_argument("--strict",action="store_true")
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--approve-local-zetaris",action="store_true")
    parser.add_argument("--receipt",type=Path,default=DEFAULT_RECEIPT)
    args=parser.parse_args(argv)
    if args.receipt.exists():
        print(json.dumps({"status":"REFUSE_OVERWRITE_RECEIPT","sponsor_called":False}))
        return 2
    if args.live and not args.approve_local_zetaris:
        print(json.dumps({"status":"LOCAL_ZETARIS_APPROVAL_REQUIRED","sponsor_called":False}))
        return 2
    receipts=[]
    try:
        if args.live:
            config=read_local_env(".env.local")
            opts={
                "base_url":config["ZETARIS_REST_URL"],
                "org_id":config["ZETARIS_ORG_ID"],
                "api_key":config["ZETARIS_API_KEY"],
            }
            nhc,id1,sql1=query_sql_editor("NOAA_NHC",**opts)
            receipts.append({"request_id_sha12":sha256(id1.encode()).hexdigest()[:12],
                             "sql_sha12":sql1})
            fl,id2,sql2=query_sql_editor("FLORIDA_GOVERNOR",**opts)
            receipts.append({"request_id_sha12":sha256(id2.encode()).hexdigest()[:12],
                             "sql_sha12":sql2})
        else:
            nhc,fl=import_rows()
        report=evaluate(nhc,fl,as_of_utc=args.as_of,strict=args.strict)
        report["data_origin"]=(
            "TWO_ACTUAL_LOCAL_ZETARIS_READ_ONLY_QUERIES" if args.live
            else "OFFLINE_CURATED_FIXTURE_NOT_LIVE_SQL")
        report["sql_receipts_redacted"]=receipts
        report["raw_sql_rows_stored"]=False
        report["human_participants"]=0
        report["evaluated_at_utc"]=datetime.now(timezone.utc).isoformat()
        status="PASS"
        code=0
    except (ValueError,TypeError,KeyError,OSError) as err:
        status="FAIL_CLOSED_"+type(err).__name__
        report={
            "kind":"EVIDENCETRAIL_SOURCE_WITHDRAWAL_AND_TIME_WHY_V1",
            "status":status,"details_withheld_to_avoid_secrets":True,
            "human_participants":0,"model_or_sponsor_called":False,
        }
        code=2
    # The pure engine calls no providers, but this CLI wrapper may have made
    # real local sponsor SQL requests. Preserve partial success on failure.
    # A failed live attempt with no completion cannot attest zero network calls.
    sponsor_called=True if receipts else (None if args.live else False)
    report["model_or_sponsor_called"]=sponsor_called
    report["model_called"]=False
    report["local_sql_queries_completed"]=len(receipts)
    report["sql_receipts_redacted"]=receipts
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    if code==0:
        changes=sum(bool(x["changed_claims"])
                    for x in report["source_withdrawal_interventions"])
        chrono=sum(bool(x["changed_claims"])
                   for x in report["clock_boundary_interventions"])
    else:
        changes=chrono=None
    print(json.dumps({
        "status":status,
        "data_origin":report.get("data_origin"),
        "source_withdrawal_cases":len(report.get("source_withdrawal_interventions",[])),
        "source_withdrawal_cases_changing_claims":changes,
        "clock_boundary_cases":len(report.get("clock_boundary_interventions",[])),
        "clock_boundaries_changing_claims":chrono,
        "sponsor_called":sponsor_called,
        "model_called":False,
        "local_sql_queries_completed":len(receipts),
        "verified_human_impact_n":0,
        "receipt":str(args.receipt),
    }))
    return code


if __name__=="__main__":
    raise SystemExit(main())
