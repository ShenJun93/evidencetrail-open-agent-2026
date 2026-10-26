"""Retrospective NARRATIVE audit of the ONE prior NVIDIA Lightning live receipt.

Does not call NVIDIA/Zetaris, read API keys, reload model text, alter the
original immutable report, or retroactively certify semantic entailment.
The old receipt stored the model's free-text rationale but not its full
structured proposal; only stored evidence can be audited here.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from evidencetrail.adapters.nvidia_lightning import (
    MODEL, _narrative_risk_flags,
)

LEGACY = Path("acceptance/logs/nvidia-lightning-zetaris-one-shot-20261024.json")
OUTPUT = Path("acceptance/logs/nvidia-lightning-narrative-retrospective-20261024.json")
EXPECTED_IDS = [
    "NHC-AL142024-PUBLIC-008", "FL-EO-24-214", "FL-EO-24-215"
]


def audit_legacy_receipt(document: dict) -> dict:
    """Policy assessment, NOT a second inference or original HTTP attestation."""
    if not isinstance(document, dict):
        raise ValueError("LEGACY_RECEIPT_INVALID_OBJECT")
    m = document.get("model_result")
    if not isinstance(m, dict):
        raise ValueError("LEGACY_MODEL_RESULT_MISSING")
    g = m.get("grounding")
    if not isinstance(g, dict):
        raise ValueError("LEGACY_GROUNDING_MISSING")
    if not (
        document.get("kind") == "EVIDENCETRAIL_NVIDIA_LIGHTNING_TWO_ISSUER_V1"
        and document.get("requested_model") == MODEL
        and document.get("status") == "REAL_NVIDIA_RESPONSE_GROUNDED"
        and document.get("nvidia_network_requests_attempted") == 1
        and document.get("zetaris_query_attempts") == 2
        and document.get("sql_rows_actual") == {"NOAA_NHC": 4, "FLORIDA_GOVERNOR": 3}
        and document.get("admissible_source_ids") == EXPECTED_IDS
        and m.get("returned_model") == MODEL
        and m.get("real_nvidia_network_called") is True
        and m.get("injected_transport") is False
        and g.get("grounded_against_sql_selection") is True
    ):
        raise ValueError("LEGACY_NOT_THE_ACCEPTED_SQL_VENDOR_CASE")
    rationale = g.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 1800:
        raise ValueError("LEGACY_RATIONALE_NOT_RETAINED")
    flags = _narrative_risk_flags(rationale)
    return {
        "kind": "EVIDENCETRAIL_RETROSPECTIVE_MODEL_RATIONALE_QUARANTINE_V1",
        "status": "LEGACY_LIVE_CALL_RATIONALE_QUARANTINED",
        "model_from_prior_receipt": MODEL,
        "prior_model_receipt_had_real_network_call": True,
        "new_nvidia_calls": 0,
        "new_zetaris_queries": 0,
        "replayed_full_original_model_response": False,
        "historical_response_envelope_independently_reauthenticated": False,
        "prior_typed_values_and_citations_passed_old_gate": True,
        "old_gate_proved_semantic_entailment": False,
        "model_rationale_untrusted_and_not_shown_as_verified": True,
        "ambiguous_or_unsupported_phrasing_detected": bool(flags),
        "rationale_risk_flags": flags,
        "rationale_sha256": sha256(rationale.encode("utf-8")).hexdigest(),
        "model_rationale_logged_verbatim_in_new_report": False,
        "fresh_independent_analyst_validation_performed": False,
        "organizer_sponsor_approval": "NOT_VERIFIED",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=LEGACY)
    p.add_argument("--output", type=Path, default=OUTPUT)
    args = p.parse_args(argv)
    try:
        receipt = json.loads(args.input.read_text(encoding="utf-8"))
        report = audit_legacy_receipt(receipt)
    except (ValueError, TypeError, OSError, UnicodeError):
        print(json.dumps({
            "status": "LEGACY_RECEIPT_ABSENT_OR_INVALID",
            "new_nvidia_calls": 0, "new_zetaris_queries": 0,
        }))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        print(json.dumps({
            "status": "REFUSE_OVERWRITE_AUDIT_RECEIPT",
            "new_nvidia_calls": 0, "new_zetaris_queries": 0,
        }))
        return 2
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "risk_flags": report["rationale_risk_flags"],
        "new_nvidia_calls": 0,
        "new_zetaris_queries": 0,
        "receipt": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
