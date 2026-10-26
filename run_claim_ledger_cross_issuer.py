"""Run case-independent typed claim selection over Zetaris NOAA+Florida rows.

Defaults to OFFLINE curated metadata. Explicit --live reads exactly the two
existing local read-only Zetaris SQL Editor projections. Never calls NVIDIA,
Nightshift, Nemotron or any remote model. No database writes or DDL.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from evidencetrail.claim_ledger_milton import evaluate_milton_sql_claims
from evidencetrail.cross_issuer_milton import CROSS_ISSUER_GOLD
from evidencetrail.zetaris_cross_issuer import query_sql_editor
from run_zetaris_cross_issuer import import_rows
from run_zetaris_preflight import read_local_env

DEFAULT_RECEIPT = Path("acceptance/logs/claim-ledger-two-issuer-first-live.json")


def build_evaluation(nhc_rows: list[dict], florida_rows: list[dict], *,
                     actual_sql: bool) -> dict:
    cases = []
    for at, wind, counties, issuer_count in CROSS_ISSUER_GOLD:
        report = evaluate_milton_sql_claims(nhc_rows,florida_rows,as_of_utc=at)
        selected = {c["claim_key"]:c["value"] for c in report["typed_claims"]}
        matched = (
            selected.get("NHC_WIND") == wind
            and selected.get("FL_ORDER") == counties
            and report["issuer_independence_count"] == issuer_count
            and all(not c["original_first_publication_authenticated"]
                    for c in report["typed_claims"])
        )
        cases.append({
            "as_of_utc":at,
            "gold_pass":matched,
            "admissible_issuer_family_count":issuer_count,
            "pinned_claim_values":selected,
            "excluded_source_count":len(report["excluded"]),
            "date_only_conservative_policy_used":True,
        })
    strict = evaluate_milton_sql_claims(
        nhc_rows, florida_rows,
        as_of_utc="2024-10-08T04:00:00Z", strict=True)
    if strict["typed_claims"]:
        raise ValueError("STRICT_NOT_ABSTAINING")
    return {
        "kind":"EVIDENCETRAIL_GENERIC_CLAIM_LEDGER_CROSS_ISSUER_V1",
        "status":("PASS" if all(c["gold_pass"] for c in cases) else "FAIL"),
        "source_data_origin":("TWO_ACTUAL_LOCAL_ZETARIS_SQL_RESPONSES" if actual_sql
                              else "OFFLINE_CURATED_FIXTURE_NOT_LIVE_SQL"),
        "model_or_sponsor_called":False,
        "zetaris_sql_called":actual_sql,
        "nine_internal_gold_cases":len(cases),
        "gold_passed":sum(c["gold_pass"] for c in cases),
        "strict_abstains_without_original_page_byte_proof":True,
        "cases":cases,
        "independent_original_publisher_first_publication_proven":False,
        "externally_blind_user_outcomes_measured":False,
        "historical_metadata_manually_curated":True,
        "issuer_family_count_is_not_document_independence_proof":True,
        "general_language_entailment_proven":False,
        "no_operational_forecast":True,
        "checked_at_utc":datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approve-local-zetaris",action="store_true")
    parser.add_argument("--env-file",default=".env.local")
    parser.add_argument("--receipt",type=Path,default=DEFAULT_RECEIPT)
    args=parser.parse_args(argv)
    # Reject overwrites BEFORE opening any authenticated transport.
    if args.receipt.exists():
        print(json.dumps({"status":"REFUSE_OVERWRITE_RECEIPT",
                          "zetaris_sql_called":False,"model_or_sponsor_called":False}))
        return 2
    if args.live and (
        not args.approve_local_zetaris or args.env_file != ".env.local"):
        print(json.dumps({"status":"REFUSE_UNAPPROVED_LOCAL_SQL",
                          "zetaris_sql_called":False,"model_or_sponsor_called":False}))
        return 2
    receipts = []
    try:
        if args.live:
            conf=read_local_env(args.env_file)
            settings={
                "base_url":conf["ZETARIS_REST_URL"],
                "org_id":conf["ZETARIS_ORG_ID"],
                "api_key":conf["ZETARIS_API_KEY"],
            }
            nhc, id1, q1=query_sql_editor("NOAA_NHC",**settings)
            florida,id2,q2=query_sql_editor("FLORIDA_GOVERNOR",**settings)
            receipts=[{
                "query_id_sha12":sha256(x.encode()).hexdigest()[:12],
                "sql_sha12":digest,
            } for x,digest in [(id1,q1),(id2,q2)]]
        else:
            nhc,florida=import_rows()
        result=build_evaluation(nhc,florida,actual_sql=args.live)
        result["sql_receipts_redacted"]=receipts
        result["raw_sql_rows_stored"]=False
        result["api_key_ever_logged"]=False
        code=0 if result["status"]=="PASS" else 2
    except (OSError,ValueError,TypeError,KeyError) as exc:
        result={
            "kind":"EVIDENCETRAIL_GENERIC_CLAIM_LEDGER_CROSS_ISSUER_V1",
            "status":"FAIL_CLOSED_" + type(exc).__name__,
            "model_or_sponsor_called":False,
            "original_publisher_byte_proof":False,
            "detail_omitted_to_avoid_credentials_in_errors":True,
        }
        code=2
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(result,indent=2)+"\n","utf-8")
    print(json.dumps({
        "status":result["status"],
        "data_origin":result.get("source_data_origin"),
        "internal_cases":result.get("nine_internal_gold_cases"),
        "passed":result.get("gold_passed"),
        "strict_abstained":result.get("strict_abstains_without_original_page_byte_proof"),
        "sponsor_called":False,
        "receipt":str(args.receipt),
    }))
    return code


if __name__=="__main__":
    raise SystemExit(main())
