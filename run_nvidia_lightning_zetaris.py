"""EvidenceTrail official NVIDIA Lightning + authenticated Zetaris two-issuer proof.

OFFLINE preflight by default; --live calls two read-only local Zetaris SQL
projections followed by exactly ONE remote NVIDIA free prototype model request.
No retries; no fallback to hand-curated local files after any SQL/AI error.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from evidencetrail.adapters.nvidia_lightning import (
    MODEL, ENDPOINT, NvidiaLightningError, chat_public_evidence,
)
from evidencetrail.zetaris_cross_issuer import query_sql_editor, evaluate_sql_rows
from evidencetrail.claim_ledger_milton import evaluate_milton_sql_claims
from run_zetaris_preflight import read_local_env
from evidencetrail.cli import _load_env_file

CLOCK = "2024-10-07T11:00:00Z"
REPORT = Path("acceptance/logs/nvidia-lightning-zetaris-one-shot.json")


def _public_base_status(conf: dict) -> dict:
    return {
        "kind": "EVIDENCETRAIL_NVIDIA_LIGHTNING_TWO_ISSUER_V1",
        "requested_model": MODEL, "official_url": ENDPOINT,
        "as_of_utc": CLOCK, "NVIDIA_key_present":bool(conf.get("NVIDIA_API_KEY", "").strip()),
        "local_zetaris_config_present":all(bool(conf.get(k, "").strip()) for k in
              ("ZETARIS_REST_URL","ZETARIS_ORG_ID","ZETARIS_API_KEY")),
        "nvidia_api_key_value_logged": False,
        "zetaris_api_key_value_logged": False,
        "remote_sponsor_credits_or_billing_certified_free": False,
        "historical_original_2024_publisher_publication_authenticated": False,
        "independent_human_impact_study_performed": False,
        "organizer_sponsor_eligibility_certified": False,
        "nightshift_called": False,
        "nvidia_network_requests_attempted": 0,
        "zetaris_query_attempts": 0,
        "status":"NOT_RUN",
    }


def one_real_run(conf: dict) -> dict:
    base = _public_base_status(conf)
    if not base["NVIDIA_key_present"] or not base["local_zetaris_config_present"]:
        base["status"] = "KEY_OR_ZETARIS_CONFIG_MISSING"
        return base
    # Never allow a remote Zetaris target. Adapter validates strict loopback.
    args = {
        "base_url":conf["ZETARIS_REST_URL"],
        "org_id":conf["ZETARIS_ORG_ID"],
        "api_key":conf["ZETARIS_API_KEY"],
    }
    base["zetaris_query_attempts"] = 1
    nhc, nhc_req, q1 = query_sql_editor("NOAA_NHC", **args)
    base["zetaris_query_attempts"] = 2
    florida, fl_req, q2 = query_sql_editor("FLORIDA_GOVERNOR", **args)
    truth = evaluate_sql_rows(nhc, florida, clock=CLOCK)
    if (truth["latest_noaa_wind_mph"] != 100
            or truth["latest_florida_emergency_counties"] != 51
            or truth.get("original_2024_first_publication_authenticated") is not False):
        raise NvidiaLightningError("SQL_FACTS_FAILED_CONSERVATIVE_REPLAY")
    # Source-pinned, reusable claim ledger MUST pass before cloud egress;
    # the old two-value reducer by itself cannot authorize another model call.
    ledger = evaluate_milton_sql_claims(nhc, florida, as_of_utc=CLOCK)
    ledger_claims = {c["claim_key"]: c["value"] for c in ledger["typed_claims"]}
    if (ledger.get("status") != "CLAIMS_SELECTED"
            or ledger_claims.get("NHC_WIND") != 100
            or ledger_claims.get("FL_ORDER") != 51
            or ledger.get("issuer_independence_count") != 2
            or ledger.get("attested_original_publication") is not False
            or any(c.get("original_first_publication_authenticated") is not False
                   for c in ledger["typed_claims"])):
        raise NvidiaLightningError("GENERIC_CLAIM_LEDGER_EGRESS_REFUSED")
    base["claim_ledger_gate"] = {
        "status": "PASSED_SOURCE_PINNED_REPORTED_DATE_REPLAY_ONLY",
        "typed_claim_keys": sorted(ledger_claims),
        "selected_issuer_family_count": ledger["issuer_independence_count"],
        "source_first_publication_authenticated": False,
        "model_free_text_entailment_proven": False,
    }
    source_set = set(truth["selected_original_ids"])
    data = [r for r in nhc + florida if r["source_id"] in source_set]
    base["sql_rows_actual"] = truth["sql_decoded_issuer_row_counts"]
    base["admissible_source_ids"] = truth["selected_original_ids"]
    base["sql_request_id_sha12"] = [
        hashlib.sha256(x.encode()).hexdigest()[:12] for x in (nhc_req,fl_req)]
    base["sql_statement_sha12"] = [q1,q2]
    # Call at most once, no retries, no agent or paid service fallback.
    base["nvidia_network_requests_attempted"] = 1
    result = chat_public_evidence(
        key=conf["NVIDIA_API_KEY"], truth=truth, selected_rows=data)
    base["model_result"] = result
    base["status"] = result["status"]
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="offline, default")
    group.add_argument("--live", action="store_true", help="one authorized NVIDIA trial")
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--confirm-free-prototype", action="store_true",
                        help="owner explicitly permits one free NVIDIA trial API call")
    parser.add_argument("--confirm-public-curated-research-egress",
                        action="store_true",
                        help="send only selected public official-source claim metadata")
    parser.add_argument("--receipt", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    if args.env_file != ".env.local":
        raise SystemExit("ONLY_OWNER_IGNORED_ENV_LOCAL_ALLOWED")
    try:
        # Zetaris allowlist intentionally excludes NVIDIA_API_KEY; load it
        # from the explicitly selected ignored file, never print the value.
        _load_env_file(Path(args.env_file))
        conf = dict(os.environ)
        fromfile = read_local_env(args.env_file)
        for k in ("NVIDIA_API_KEY","ZETARIS_REST_URL","ZETARIS_ORG_ID","ZETARIS_API_KEY"):
            if fromfile.get(k):
                conf[k] = fromfile[k]
        record = _public_base_status(conf)
        if not args.live:
            record["status"] = "OFFLINE_CONFIG_CHECK_ONLY"
            code = 0
        elif not (args.confirm_free_prototype
                  and args.confirm_public_curated_research_egress):
            record["status"] = "BLOCKED_USER_APPROVAL_FLAGS_MISSING"
            code = 2
        else:
            try:
                record = one_real_run(conf)
                code = 0 if record["status"] == "REAL_NVIDIA_SQL_CLAIMS_BOUNDED" else 2
            except NvidiaLightningError as e:
                record["status"] = "NO_ACCEPTED_NVIDIA_INFERENCE"
                record["safe_failure_code"] = str(e)
                code = 2
            except Exception as e:
                record["status"] = "LIVE_SQL_OR_TRANSPORT_BLOCKED"
                record["safe_failure_class"] = type(e).__name__
                code = 2
    except (OSError, ValueError) as error:
        record = _public_base_status({})
        record["status"] = "LOCAL_CONFIG_UNAVAILABLE"
        record["safe_failure_class"] = type(error).__name__
        code = 2
    record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    if args.receipt.exists():
        raise SystemExit("REFUSE_OVERWRITE_EXISTING_TRIAL_RECEIPT")
    args.receipt.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({
        "status":record["status"],
        "model":MODEL,
        "key_present":record["NVIDIA_key_present"],
        "local_zetaris_config_present":record["local_zetaris_config_present"],
        "nvidia_requests_attempted":record["nvidia_network_requests_attempted"],
        "zetaris_query_attempts":record["zetaris_query_attempts"],
        "grounded":record.get("model_result",{}).get("grounding",{}).get(
            "grounded_against_sql_selection"),
        "safe_failure_code":record.get("safe_failure_code"),
        "safe_failure_class":record.get("safe_failure_class"),
        "receipt":str(args.receipt),
    },ensure_ascii=False))
    return code


if __name__=="__main__":
    raise SystemExit(main())
