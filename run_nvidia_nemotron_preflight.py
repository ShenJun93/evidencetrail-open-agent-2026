"""Owner-controlled NVIDIA Nemotron direct preflight (offline by default).

--check NEVER makes a network call or prints a token.
--live requires THREE explicit CLI acknowledgements, an actual NVIDIA API key,
and sends only a publicly described, synthetic-labelled 2024 research fixture.

A real model response is not proof of organizer eligibility, live Zetaris
source use, official H-MEM, or operational flood-warning correctness.
The complete --live EvidenceTrail CLI remains a SEPARATE acceptance gate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from evidencetrail.agents.decision import DecisionAgent
from evidencetrail.catalog import all_catalog
from evidencetrail.cli import _load_env_file
from evidencetrail.firewall import filter_sources, jurisdiction_ok
from evidencetrail.models import RunRequest, iso
from evidencetrail.traces import JsonlTrace
from evidencetrail.adapters.nvidia_nim import (
    ENDPOINT, MODEL, MAX_TOKENS, gates,
)

OUTPUT = Path("acceptance/logs/nvidia-nemotron-direct-preflight.json")
SOURCE_SAMPLE = Path("samples/inputs/yagi_1645_lucyen.json")


def public_sample_case() -> tuple[RunRequest, list]:
    raw = json.loads(SOURCE_SAMPLE.read_text(encoding="utf8"))
    # For this isolated public sample/model-only preflight the live-call flag
    # does NOT mean the catalog, capacity or source backend is live.
    raw["sample_mode"] = False
    req = RunRequest.from_dict(raw)
    selected = [
        row for row in all_catalog()
        if jurisdiction_ok(row, req.province_2024, req.district_2024)
    ]
    eligible, _ = filter_sources(selected, req.as_of_utc, req.mode)
    if not any(r.record_kind.value == "SYNTHETIC_CAPACITY" for r in eligible):
        raise ValueError("SYNTHETIC_RESEARCH_SCENARIO_EXPECTED")
    if not any(r.source_id == "GOV-2024-09-08-1637" for r in eligible):
        raise ValueError("SOURCE_FIXTURE_MISSING_1637")
    return req, eligible


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true",
                       help="offline check, default; NEVER call NVIDIA")
    modes.add_argument("--live", action="store_true",
                       help="one explicit public research model inference")
    parser.add_argument("--env-file", default=".env.local",
                        help="local gitignored secret file, NEVER copied")
    parser.add_argument("--confirm-public-research-egress",
                        action="store_true",
                        help="consent to send public 2024 sample paraphrases to NVIDIA")
    parser.add_argument("--confirm-free-developer-endpoint",
                        action="store_true",
                        help="confirm approved developer/free API access")
    parser.add_argument("--confirm-nemotron-35-vl-model",
                        action="store_true",
                        help="explicit approval of the new NVIDIA Nemotron 3.5 model")
    parser.add_argument("--receipt", default=str(OUTPUT))
    args = parser.parse_args(argv)

    # Existing environment always takes precedence over the optional ignored
    # secret file. No key value ever enters model output or Git.
    _load_env_file(Path(args.env_file))
    g = gates()
    result = {
        "kind": "NVIDIA_NEMOTRON_DIRECT_PREFLIGHT",
        "requested_model": MODEL,
        "official_endpoint": ENDPOINT,
        "max_generated_tokens": MAX_TOKENS,
        "research_catalog": "PUBLIC_YAGI_FIXTURE_WITH_FICTIONAL_CAPACITY",
        "real_zetaris_network_called": False,
        "official_hmem_engine_called": False,
        "nightshift_called": False,
        "real_world_emergency_use": False,
        "organizer_eligibility_confirmed": False,
        "nvidia_api_key_present": g["nvidia_api_key_present"],
        "replacement_model_approval_for_this_call": bool(
            args.live and args.confirm_nemotron_35_vl_model
        ),
        "api_key_value_logged": False,
        "model_raw_text_logged": False,
        "network_called": False,
        "status": "NOT_RUN",
    }
    path = Path(args.receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not args.live:
        result["status"] = (
            "OWNER_KEY_PRESENT_NEW_MODEL_APPROVAL_REQUIRED"
            if g["nvidia_api_key_present"] else
            "BLOCKED_NVIDIA_API_KEY_MISSING"
        )
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf8",
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if not (args.confirm_public_research_egress and
            args.confirm_free_developer_endpoint and
            args.confirm_nemotron_35_vl_model and
            g["nvidia_api_key_present"]):
        result["status"] = (
            "BLOCKED_MISSING_OWNER_CONSENT_OR_KEY"
            if not g["nvidia_api_key_present"] else
            "BLOCKED_NEW_MODEL_CONSENT_REQUIRED"
        )
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf8",
        )
        print(json.dumps(result, ensure_ascii=False))
        return 2

    # Owner consent is limited to this process; flags never persist in Git.
    os.environ["EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED"] = "true"
    os.environ["EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT"] = "true"
    os.environ["EVIDENCETRAIL_NVIDIA_35_VL_APPROVED"] = "true"
    request, eligible = public_sample_case()
    trace = JsonlTrace(
        Path("acceptance/logs/nvidia-nemotron-preflight-trace.jsonl"),
        request.run_id,
    )
    agent = DecisionAgent(trace)
    draft = agent.run(request, eligible, memories=[])
    receipts = [s for s in agent.sponsor_calls if s.provider == "nvidia"]
    if len(receipts) != 1:
        result["status"] = "BLOCKED_NO_SINGLE_NVIDIA_MODEL_RECEIPT"
    else:
        sponsor = receipts[0]
        result["status"] = (
            "DIRECT_NEMOTRON_MODEL_ANSWERED_NOT_ORGANIZER_CERTIFIED"
            if sponsor.outcome.value == "REAL_SUCCESS" else
            "DIRECT_NEMOTRON_NOT_ACCEPTED_OR_BLOCKED"
        )
        result["nvidia_model_contract"] = sponsor.to_dict()
        result["network_called"] = bool(
            agent.nvidia_transport_receipt
            and agent.nvidia_transport_receipt.get("network_called")
        )
        result["network_request_attempted"] = result["network_called"]
        result["rule_verdict"] = draft.nominated_verdict.value
        result["model_route"] = draft.model_route
        result["cited_source_ids"] = [c.source_id for c in draft.citations]
        result["as_of_utc"] = iso(request.as_of_utc)
        result["official_sponsor_recognition"] = "NOT_VERIFIED"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"].startswith(
        "DIRECT_NEMOTRON_MODEL_ANSWERED_"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
