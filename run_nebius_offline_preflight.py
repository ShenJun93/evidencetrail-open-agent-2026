"""Nebius key presence and route readiness only. NEVER performs a network call.

Usage: py -3 run_nebius_offline_preflight.py --check
No --live mode exists: Nebius public inference can incur per-token charges.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrail.adapters.nebius_token_factory import (
    ENDPOINT, MAX_TOKENS, MODEL, gates
)
from evidencetrail.cli import _load_env_file


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="local-only, default")
    p.add_argument("--env-file", default=".env.local")
    p.add_argument("--receipt", default="acceptance/logs/nebius-offline-preflight.json")
    args = p.parse_args(argv)
    _load_env_file(Path(args.env_file))
    g = gates()
    report = {
        "kind": "NEBIUS_TOKEN_FACTORY_OFFLINE_READINESS",
        "provider": "nebius",
        "requested_model": MODEL,
        "official_endpoint": ENDPOINT,
        "max_generated_tokens": MAX_TOKENS,
        **g,
        "key_value_logged": False,
        "raw_model_output_logged": False,
        "external_network_calls": 0,
        "possible_paid_usage": True,
        "nvidia_direct_sponsor_receipt": False,
        "organizer_sponsor_eligibility": "NOT_VERIFIED",
        "status": ("KEY_PRESENT_NETWORK_BLOCKED_BY_DEFAULT"
                   if g["nebius_api_key_present"] else
                   "BLOCKED_NEBIUS_API_KEY_MISSING"),
    }
    path = Path(args.receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
