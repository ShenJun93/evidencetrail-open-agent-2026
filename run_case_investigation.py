"""Investigate a typed case; optional explicit local Zetaris and Nightshift.

Example: py -3 run_case_investigation.py --example warehouse --withdraw STOCK-CHECK STOCK-LEDGER
Input packs and output receipts stay local. Model calls require --local-nightshift.
Refuse receipt overwrite. The deterministic verdict never depends on model prose.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from hashlib import sha256
import re

from evidencetrail.case_investigator import (
    MAX_CASE_BYTES, example_case, investigate_case, make_case_pack,
)
from evidencetrail.case_nightshift import propose_local_explanation
from evidencetrail.claim_ledger_milton import curated_milton_manifest
from evidencetrail.zetaris_cross_issuer import _canonical_rows, query_sql_editor
from run_zetaris_preflight import read_local_env


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--case", type=Path)
    source.add_argument("--example", choices=("warehouse", "milton"))
    source.add_argument("--local-zetaris", action="store_true",
                        help="explicitly query the two fixed loopback Milton tables; never call a model")
    parser.add_argument("--approve-local-zetaris", action="store_true")
    parser.add_argument("--local-nightshift", action="store_true",
                        help="ask only a local Nightshift lane for a checked explanation proposal")
    parser.add_argument("--as-of")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--withdraw", nargs="*", default=[])
    parser.add_argument("--search-depth", type=int, default=2)
    parser.add_argument("--receipt", type=Path,
                        default=Path("acceptance/logs/open-case-investigation.json"))
    args = parser.parse_args(argv)
    if args.receipt.exists():
        print(json.dumps({"status": "REFUSE_RECEIPT_OVERWRITE", "model_or_sponsor_called": False}))
        return 2
    if args.local_zetaris and not args.approve_local_zetaris:
        print(json.dumps({"status": "LOCAL_ZETARIS_APPROVAL_REQUIRED", "model_or_sponsor_called": False}))
        return 2
    sql_receipts = []
    model_called = False
    nightshift = None
    try:
        if args.local_zetaris:
            config = read_local_env(".env.local")
            options = {"base_url": config["ZETARIS_REST_URL"],
                       "org_id": config["ZETARIS_ORG_ID"], "api_key": config["ZETARIS_API_KEY"]}
            data = []
            for issuer in ("NOAA_NHC", "FLORIDA_GOVERNOR"):
                rows, request_id, sql_digest = query_sql_editor(issuer, **options)
                data.append(rows)
                sql_receipts.append({"request_id_sha12": sha256(request_id.encode()).hexdigest()[:12],
                                     "sql_sha12": sql_digest})
            records = _canonical_rows(*data)
            pins, rules = curated_milton_manifest()
            pack = make_case_pack("MILTON-LOCAL-SQL", "Local Zetaris curated Milton case",
                                  "Which claims survive joint withdrawal of the selected sources?",
                                  "2024-10-07T11:00:00Z", records, pins, rules)
            origin = "REAL_LOCAL_ZETARIS_ROWS_CURATED_METADATA"
        elif args.case:
            if args.case.stat().st_size > MAX_CASE_BYTES:
                raise ValueError("CASE_BYTES_LIMIT_60000")
            pack = json.loads(args.case.read_text(encoding="utf-8-sig"))
            origin = "OPERATOR_CASE_FILE_NOT_LIVE_DATA"
        else:
            pack = example_case(args.example)
            origin = "OFFLINE_CURATED_OR_FICTIONAL_EXAMPLE"
        report = investigate_case(pack, as_of_utc=args.as_of, strict=args.strict,
                                  withdrawn_source_ids=args.withdraw,
                                  search_depth=args.search_depth)
        nightshift = (propose_local_explanation(report) if args.local_nightshift else None)
        model_called = bool(nightshift and nightshift["model_called"])
        nightshift_request_attempted = bool(
            nightshift and nightshift.get("request_attempted", model_called))
        report.update({"source_origin": origin, "model_called": model_called,
                       "model_or_sponsor_called": bool(sql_receipts) or nightshift_request_attempted,
                       "nightshift_request_attempted": nightshift_request_attempted,
                       "zetaris_queries_completed": len(sql_receipts),
                       "sql_receipts_redacted": sql_receipts})
        if nightshift is not None:
            report["nightshift_local_proposal"] = nightshift
            report["execution_trace"].append({
                "action": "CHECK_LOCAL_NIGHTSHIFT_PROPOSAL", "status": nightshift["status"],
                "model_called": model_called, "request_attempted": nightshift_request_attempted,
                "deterministic_verdict_unchanged": True,
            })
        if sql_receipts:
            report["execution_trace"].insert(0, {"action": "READ_REAL_LOCAL_ZETARIS",
                                                  "completed_read_only_queries": len(sql_receipts)})
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError) as exc:
        code = str(exc)
        print(json.dumps({
            "status": "CASE_INVESTIGATION_REFUSED",
            "reason_code": code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", code) else "CASE_VALIDATION_REFUSED",
            "model_or_sponsor_called": True if sql_receipts else (None if args.local_zetaris or args.local_nightshift else False),
            "model_called": model_called, "zetaris_queries_completed": len(sql_receipts),
        }))
        return 2
    print(json.dumps({"status": "LOCAL_CASE_INVESTIGATION_COMPLETE",
                      "case_id": report["case_id"], "trust_basis": report["trust_basis"],
                      "selected_claim_count": len(report["why"]["selected_claims"]),
                      "subsets_evaluated": report["resilience"]["subsets_evaluated"],
                      "source_origin": origin, "model_called": model_called,
                      "nightshift_request_attempted": nightshift_request_attempted,
                      "nightshift_status": nightshift["status"] if nightshift else "NOT_REQUESTED",
                      "model_or_sponsor_called": bool(sql_receipts) or nightshift_request_attempted,
                      "zetaris_queries_completed": len(sql_receipts), "receipt": str(args.receipt)}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
