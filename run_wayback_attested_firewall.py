"""Opt-in proof-only replay: genuinely checked 2024 archived bytes -> STRICT temporal firewall.

Only read real original archived bytes through run_wayback_body_audit.py, match
three immutable checkout-review pins, then use the SAME evidencetrail.firewall
filter_sources() as the real app. NEVER pass promoted copies to DecisionAgent,
Zetaris, or the default offline/browser replay. Outputs only a source
admissibility table, not a disaster verdict or sponsor receipt.

This proves original archive BODY corroboration by a crawl timestamp, NOT the
original minute of first publisher publication, editorial history or rescue.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from evidencetrail.catalog import by_id
from evidencetrail.firewall import filter_sources
from evidencetrail.models import ProvenanceQuality, ReplayMode
from run_wayback_body_audit import audit_source
from run_wayback_index_audit import SOURCES

OUTPUT = Path("acceptance/logs/attested-wayback-strict-firewall-20261023.json")

# Exact source+first observed 2024 archive body hashes reviewed on 23 October
# (not a signature by the government publisher). Any changed publisher body,
# CDX digest, first crawl timestamp or URL fails this optional gate closed.
PINNED_ARCHIVE = {
    "GOV-2024-09-08-1530": (
        "2024-09-08T08:51:44Z",
        "LGHHQCXUR6PZFU3KMWNNC4RHWH5SUHJD",
        "ff257eba6022c7cefa835a2184c972efc1d79ee586ada8ac5476203bf958131d",
        "69958037b7dc6bd315be3361d5b510890d292a4712ffdf5e23ffb60d238be6b3",
    ),
    "GOV-2024-09-08-1621": (
        "2024-09-08T09:38:33Z",
        "QAUO2QPMKFIDQ6HKKW5YYO3G3JWJFJ7R",
        "90d4cb402dab416ad1265d5175f8d112998fc5eaac0469b15726d972f67acc70",
        "9ca4d5027a41cb3fcd7ee95fb79a20233809a2a17412be0ccbc904bf93a6cf33",
    ),
    "GOV-2024-09-08-1637": (
        "2024-09-08T11:21:46Z",
        "DOXKQ47JPI4GYDAY5XWRPEUCYF5H7FHY",
        "31b956cf38d5d1b7fe978982982a267a469570a5ebc8a02dad00278896a11ab2",
        "596d7aa1647bc32c5197cefe3502bb48d9b0620e2e2a3336dd69d0344ef7bace",
    ),
}
CLOCKS = {
    "16:30_ICT": "2024-09-08T09:30:00+00:00",
    "16:45_ICT": "2024-09-08T09:45:00+00:00",
    "18:30_ICT": "2024-09-08T11:30:00+00:00",
}


def bind_verified_source(source_id: str, receipt: dict):
    """Ephemeral corroboration ONLY; no persisted promoted catalog records."""
    if source_id not in PINNED_ARCHIVE or source_id not in SOURCES:
        raise ValueError("SOURCE_NOT_IN_PINNED_ARCHIVE")
    if not isinstance(receipt, dict) or receipt.get("source_id") != source_id:
        raise ValueError("ARCHIVE_RECEIPT_WRONG_SOURCE")
    if (receipt.get("archived_body_corroborated") is not True
        or receipt.get("saved_payload_sha1_base32_matches_cdx") is not True
        or receipt.get("historical_first_publication_time_verified") is not False
        or receipt.get("strict_asof_2024_source_promoted") is not False):
        raise ValueError("ARCHIVE_RECEIPT_NOT_BODY_CORROBORATED")
    clock, cdx, rawsha, htmlsha = PINNED_ARCHIVE[source_id]
    if (
        receipt.get("first_2024_capture_utc") != clock
        or receipt.get("archive_cdx_sha1_base32") != cdx
        or receipt.get("saved_payload_sha256") != rawsha
        or receipt.get("decoded_publisher_html_sha256") != htmlsha
        or not isinstance(receipt.get("publisher_body_content_markers"), dict)
        or not receipt["publisher_body_content_markers"]
        or not all(v is True for v in receipt["publisher_body_content_markers"].values())
    ):
        raise ValueError("ARCHIVED_BYTES_DIFFER_FROM_PINNED_2024_FIRST_CAPTURE")
    record = by_id(source_id)
    if record is None or receipt.get("archive_original_url") != record.locator:
        raise ValueError("ARCHIVE_ORIGIN_MISMATCH")
    capture = datetime.fromisoformat(clock.replace("Z", "+00:00"))
    return replace(
        record,
        provenance_quality=ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT,
        first_availability_proven_utc=capture,  # first *proven*, not first published
        metadata_conflicts=record.metadata_conflicts + [
            "WAYBACK_2024_SNAPSHOT_ATTESTED_TO_ARCHIVE_CRAWL_ONLY",
            "ORIGINAL_FIRST_PUBLICATION_AND_FULL_EDIT_HISTORY_UNVERIFIED",
        ],
    )


def build_strict_source_matrix(receipts: dict[str, dict]) -> dict:
    if set(receipts) != set(PINNED_ARCHIVE):
        raise ValueError("THREE_DISTINCT_ARCHIVE_BODIES_REQUIRED")
    ephemeral = [
        bind_verified_source(sid, receipts[sid]) for sid in PINNED_ARCHIVE
    ]
    report = {}
    for label, clock in CLOCKS.items():
        asof = datetime.fromisoformat(clock)
        eligible, excluded = filter_sources(
            ephemeral, asof, ReplayMode.STRICT_AS_OF_2024
        )
        report[label] = {
            "archive_attested_source_ids": [s.source_id for s in eligible],
            "not_yet_proven_by_archive_capture": [r["source_id"] for r in excluded],
            "verdict": "NOT_COMPUTED_PROVENANCE_ONLY",
            "live_sponsor_receipt": "NONE",
        }
    return {
        "kind": "ARCHIVED_BODY_TO_ACTUAL_STRICT_FIREWALL_PROOF_ONLY",
        "checked_archive_source_count": len(ephemeral),
        "by_asof": report,
        "first_publisher_publication_verified": False,
        "full_curated_paraphrase_independently_authenticated": False,
        "decisional_pipeline_invoked": False,
        "default_catalog_modified": False,
        "meterless_nightshift_called": False,
        "historical_rescue_or_lives_saved_claim": False,
        "notice": "Only first proven archival existence is bound in-memory; not first publisher publication. No WARN/NO_WARN issued.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", default=str(OUTPUT))
    args = p.parse_args()
    # Verification is performed NOW against the pinned Wayback CDX and saved
    # gzip HTTP payloads. Never trust a caller-supplied JSON receipt as proof.
    receipts = {source_id: audit_source(source_id) for source_id in PINNED_ARCHIVE}
    report = build_strict_source_matrix(receipts)
    dest = Path(args.receipt)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "kind": report["kind"], "by_asof": report["by_asof"],
        "first_publisher_publication_verified": False,
        "runtime_sponsor_calls": 0,
        "receipt": str(dest),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
