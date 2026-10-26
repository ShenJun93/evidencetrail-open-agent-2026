"""Nebius one-shot research preflight. OFFLINE by default; possible billed use.

--live requires 3 NEW explicit consents; this file alone does not authorize
outbound inference. ONLY public Yagi paraphrases + FICTIONAL capacity.
A Nebius completion is NOT a NVIDIA-direct hackathon sponsor receipt.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from evidencetrail.adapters.nebius_token_factory import ENDPOINT, MODEL, MAX_TOKENS, gates
from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.cli import _load_env_file
from evidencetrail.traces import JsonlTrace
from run_nvidia_nemotron_preflight import public_sample_case

# Public Nebius Token Factory model listing (23 Oct 2026). Informational,
# not an account quote and NOT a maximum possible charge.
LIST_USD_PER_M_INPUT = 0.30
LIST_USD_PER_M_OUTPUT = 0.90


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--live", action="store_true")
    p.add_argument("--confirm-nebius-third-party-host", action="store_true")
    p.add_argument("--confirm-public-research-egress", action="store_true")
    p.add_argument("--approve-possible-token-charges", action="store_true")
    p.add_argument("--env-file", default=".env.local")
    p.add_argument("--receipt", default="acceptance/logs/nebius-one-shot-preflight.json")
    p.add_argument("--trace", default="acceptance/logs/nebius-one-shot-trace.jsonl")
    args = p.parse_args(argv)
    _load_env_file(Path(args.env_file))
    key_exists = gates()["nebius_api_key_present"]
    outcome = {
        "kind": "NEBIUS_ONE_SHOT_OWNER_CONSENT_PREFLIGHT",
        "provider": "nebius",
        "model": MODEL, "endpoint": ENDPOINT, "max_output_tokens": MAX_TOKENS,
        "public_list_input_usd_per_m_tokens": LIST_USD_PER_M_INPUT,
        "public_list_output_usd_per_m_tokens": LIST_USD_PER_M_OUTPUT,
        "account_credit_balance_known": False, "fee_cap_guaranteed": False,
        "possible_usage_charge": True, "key_present": key_exists,
        "key_value_logged": False, "model_raw_text_logged": False,
        "public_sample_and_fictional_capacity_only": True,
        "owner_third_party_consent": bool(args.live and args.confirm_nebius_third_party_host),
        "owner_public_egress_consent": bool(args.live and args.confirm_public_research_egress),
        "owner_possible_charges_consent": bool(args.live and args.approve_possible_token_charges),
        "network_called": False,
        "nvidia_direct_sponsor_receipt": False,
        "organizer_eligibility_confirmed": False,
        "status": "NOT_RUN",
        "structured_rejection_reason_code": None,
    }

    def done(exit_code):
        path = Path(args.receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(outcome, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf8")
        print(json.dumps(outcome, ensure_ascii=False))
        return exit_code

    if not args.live:
        outcome["status"] = ("KEY_PRESENT_OWNER_PAID_APPROVAL_REQUIRED"
                             if key_exists else "BLOCKED_NEBIUS_KEY_MISSING")
        return done(0)

    if not (key_exists and args.confirm_nebius_third_party_host
            and args.confirm_public_research_egress
            and args.approve_possible_token_charges):
        outcome["status"] = "BLOCKED_NEW_OWNER_CHARGE_OR_EGRESS_APPROVAL_MISSING"
        return done(2)

    # Per-process approval only. Explicitly prohibit dual external routes.
    os.environ["EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED"] = "false"
    os.environ["EVIDENCETRAIL_NEBIUS_ENABLED"] = "true"
    os.environ["EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT"] = "true"
    os.environ["EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED"] = "true"
    request, eligible = public_sample_case()
    agent = DecisionAgent(JsonlTrace(Path(args.trace), request.run_id))
    draft = agent.run(request, eligible, memories=[])
    reply_receipts = [s for s in agent.sponsor_calls if s.provider == "nebius"]
    receipt = agent.nebius_transport_receipt
    outcome["network_called"] = bool(receipt and receipt.get("network_called"))
    outcome["verdict"] = draft.nominated_verdict.value
    outcome["model_route"] = draft.model_route
    outcome["accepted_source_ids"] = [c.source_id for c in draft.citations]
    # Fixed allowlisted enum only; no model output, prompt or exception text.
    outcome["structured_rejection_reason_code"] = agent.nebius_rejection_reason_code
    if len(reply_receipts) != 1:
        outcome["status"] = "BLOCKED_NO_SINGLE_NEBIUS_RECEIPT"
    else:
        outcome["nebius_contract"] = reply_receipts[0].to_dict()
        outcome["status"] = (
            "THIRD_PARTY_ANSWERED_NOT_NVIDIA_SPONSOR_PROOF"
            if outcome["network_called"]
            and reply_receipts[0].outcome.value == "REAL_PROBE_ONLY"
            else "NEBIUS_NOT_ACCEPTED_OR_BLOCKED"
        )
    return done(0 if outcome["status"].startswith("THIRD_PARTY_ANSWERED_") else 2)


if __name__ == "__main__":
    raise SystemExit(main())
