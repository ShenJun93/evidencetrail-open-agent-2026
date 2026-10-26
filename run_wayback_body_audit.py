"""Bounded Wayback *body* verification for three pinned Yagi 2024 articles.

The publisher's actual 2024 archived HTTP payload may itself be GZIP encoded.
Check SHA1/Base32 of ORIGINAL fetched bytes against the 2024 CDX digest BEFORE
bounded decompression. Inspect decoded publisher article text, write only
hashes/boolean checks to gitignored acceptance/logs, and NEVER automatically
promote a curated source to STRICT_AS_OF_2024.

No arbitrary URLs, user credentials, installer, external uploads, or HTML in Git.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import html
import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from run_wayback_index_audit import (
    NoRedirect, SOURCES, parse_cdx, read_cdx, url_for_source,
)

OUTPUT = Path("acceptance/logs/yagi-2024-archive-bodies.json")
PROOF_CLOCKS = {
    "16:30_ICT": "2024-09-08T09:30:00+00:00",
    "16:45_ICT": "2024-09-08T09:45:00+00:00",
    "18:30_ICT": "2024-09-08T11:30:00+00:00",
}
MAX_RAW_BYTES = 2_000_000
MAX_DECODED_BYTES = 3_000_000
TEXT_MARKERS = {
    "GOV-2024-09-08-1530": {
        "flood_or_landslide": ("lũ quét", "sạt lở"),
        "yen_bai": ("yên bái",),
    },
    "GOV-2024-09-08-1621": {
        "flood_or_landslide": ("lũ quét", "sạt lở"),
        "yen_bai": ("yên bái",),
    },
    "GOV-2024-09-08-1637": {
        "district_luc_yen": ("lục yên",),
        "river_thao": ("thao",),
        "river_ngoi_thia": ("thia",),
        "level_3140": ("31,40", "31.40"),
        "level_4598": ("45,98", "45.98"),
        "observation_1500": ("15 giờ", "15:00", "15h00"),
    },
}


def allowed_capture(source_id: str, cdx_entry: dict) -> str:
    """Derive one exact immutable Wayback URL from a validated CDX record."""
    original, _ = url_for_source(source_id)
    candidate = cdx_entry.get("first_capture_archive_url", "")
    expected_prefix = "https://web.archive.org/web/"
    expected_tail = "id_/" + original
    if (not isinstance(candidate, str)
        or not candidate.startswith(expected_prefix)
        or not candidate.endswith(expected_tail)):
        raise ValueError("ARCHIVE_URL_OUTSIDE_PINNED_CDX")
    between = candidate[len(expected_prefix):-len(expected_tail)]
    if not re.fullmatch(r"2024[0-9]{10}", between):
        raise ValueError("ARCHIVE_CAPTURE_TIMESTAMP_INVALID")
    if (cdx_entry.get("first_2024_cdx_digest") is None
        or not re.fullmatch(r"[A-Z2-7]{32}", cdx_entry["first_2024_cdx_digest"])):
        raise ValueError("ARCHIVE_CDX_DIGEST_INVALID")
    return candidate


def fetch_archived_payload(source_id: str, cdx_entry: dict, *, get=None) -> bytes:
    url = allowed_capture(source_id, cdx_entry)
    if get is not None:
        raw = get(url)
        if not isinstance(raw, bytes):
            raise ValueError("ARCHIVE_TEST_TRANSPORT_NOT_BYTES")
    else:
        req = urllib.request.Request(url, headers={
            "User-Agent": "EvidenceTrail-Archived-Bytes-Audit/1.0",
            "Accept": "text/html",
            "Accept-Encoding": "identity",
        })
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )
        with opener.open(req, timeout=18) as resp:
            if resp.status != 200:
                raise ValueError("ARCHIVE_PAYLOAD_HTTP_NOT_200")
            raw = resp.read(MAX_RAW_BYTES + 1)
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("ARCHIVE_RAW_BYTES_TOO_LARGE")
    return raw


def decode_body(raw: bytes) -> tuple[bytes, str]:
    if raw.startswith(b"\x1f\x8b"):
        # GzipFile streams at most MAX_DECODED_BYTES + 1 bytes;
        # a tiny zip-bomb cannot exhaust RAM.
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as fp:
                plain = fp.read(MAX_DECODED_BYTES + 1)
        except (OSError, EOFError) as exc:
            raise ValueError("ARCHIVE_GZIP_CORRUPTED") from exc
        encoding = "gzip"
    else:
        plain, encoding = raw, "plain"
    if len(plain) > MAX_DECODED_BYTES:
        raise ValueError("ARCHIVE_DECOMPRESSED_BYTES_TOO_LARGE")
    return plain, encoding


def publisher_text(plain: bytes) -> str:
    """Conservative content check excluding code, CSS and HTML comments."""
    text = plain.decode("utf-8-sig", errors="replace")
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1\s*>", " ", text)
    text = html.unescape(re.sub(r"(?s)<[^>]*>", " ", text))
    return re.sub(r"\s+", " ", text).casefold()


def verify_capture(source_id: str, cdx_entry: dict, raw: bytes) -> dict:
    allowed_capture(source_id, cdx_entry)
    digest = base64.b32encode(hashlib.sha1(raw).digest()).decode("ascii").rstrip("=")
    cdxdigest = cdx_entry["first_2024_cdx_digest"]
    digest_matches = digest == cdxdigest
    plain, encoding = decode_body(raw)
    text = publisher_text(plain)
    markers = {
        key: any(phrase.casefold() in text for phrase in phrases)
        for key, phrases in TEXT_MARKERS[source_id].items()
    }
    # An exact CDX payload digest PLUS visible content evidence warrants
    # "ARCHIVED_BODY_CORROBORATED", not original first-publication proof.
    body_corroborated = bool(digest_matches and all(markers.values()))
    captured_at = datetime.fromisoformat(
        cdx_entry["first_2024_capture_utc"].replace("Z", "+00:00")
    )
    # Archive proof is an upper-bound on *known* article existence,
    # never evidence that it DID NOT exist before a crawl, nor proof of
    # first publisher release.
    coverage = {
        label: bool(
            body_corroborated and captured_at <= datetime.fromisoformat(clock)
        )
        for label, clock in PROOF_CLOCKS.items()
    }
    return {
        "source_id": source_id,
        "first_2024_capture_utc": cdx_entry["first_2024_capture_utc"],
        "archive_url": cdx_entry["first_capture_archive_url"],
        "archive_original_url": cdx_entry["original"],
        "archive_cdx_sha1_base32": cdxdigest,
        "saved_payload_sha1_base32_matches_cdx": digest_matches,
        "saved_payload_sha256": hashlib.sha256(raw).hexdigest(),
        "saved_payload_bytes": len(raw),
        "saved_payload_encoding": encoding,
        "decoded_publisher_html_sha256": hashlib.sha256(plain).hexdigest(),
        "decoded_publisher_html_bytes": len(plain),
        "publisher_body_content_markers": markers,
        "archived_body_corroborated": body_corroborated,
        "2024_body_proven_by_archive_asof": coverage,
        "historical_first_publication_time_verified": False,
        "official_editorial_revision_history_verified": False,
        "strict_asof_2024_source_promoted": False,
        "third_independent_source_created": False,
        "evidence_level": (
            "ARCHIVED_BODY_CORROBORATED_NOT_FIRST_PUBLICATION"
            if body_corroborated else "ARCHIVED_BODY_UNVERIFIED"
        ),
    }


def audit_source(source_id: str, *, get_cdx=None, get_body=None) -> dict:
    if source_id not in SOURCES:
        raise ValueError("UNKNOWN_ARCHIVE_SOURCE")
    cdx = parse_cdx(source_id, read_cdx(source_id, get=get_cdx))
    if cdx["first_2024_capture_utc"] is None:
        return {
            "source_id": source_id,
            "archived_body_corroborated": False,
            "2024_body_proven_by_archive_asof": {key: False for key in PROOF_CLOCKS},
            "evidence_level": "NO_2024_WAYBACK_CAPTURE",
            "historical_first_publication_time_verified": False,
            "strict_asof_2024_source_promoted": False,
        }
    raw = fetch_archived_payload(source_id, cdx, get=get_body)
    return verify_capture(source_id, cdx, raw)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", choices=tuple(SOURCES), default=None)
    p.add_argument("--receipt", default=str(OUTPUT))
    args = p.parse_args()
    items = (args.source,) if args.source else tuple(SOURCES)
    results = []
    for source_id in items:
        try:
            results.append(audit_source(source_id))
        except (OSError, ValueError, TimeoutError) as exc:
            # Fail closed but preserve sources that did verify. Avoid printing
            # arbitrary exception text containing potential response contents.
            results.append({
                "source_id": source_id,
                "archived_body_corroborated": False,
                "2024_body_proven_by_archive_asof": {key: False for key in PROOF_CLOCKS},
                "evidence_level": "ARCHIVE_PROBE_FAILED_CLOSED",
                "reason_type": type(exc).__name__,
                "historical_first_publication_time_verified": False,
                "strict_asof_2024_source_promoted": False,
            })
    receipt = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "WAYBACK_ARCHIVED_BODY_CORROBORATION_NOT_FIRST_PUBLICATION",
        "sources": results,
        "strict_asof_2024_sources_promoted": 0,
        "installer_or_api_keys_used": False,
        "copyrighted_html_persisted": False,
        "not_an_independent_zetaris_table": True,
    }
    output = Path(args.receipt)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "kind": receipt["kind"],
        "sources": [{
            "source_id": r["source_id"],
            "evidence_level": r["evidence_level"],
            "digest_match": r.get("saved_payload_sha1_base32_matches_cdx"),
            "body_markers": r.get("publisher_body_content_markers"),
            "first_capture_utc": r.get("first_2024_capture_utc"),
            "archive_proof_by_clock": r.get("2024_body_proven_by_archive_asof"),
        } for r in results],
        "strict_sources_promoted": 0,
        "receipt": str(output),
    }, ensure_ascii=False))
    return 0 if all(x["archived_body_corroborated"] for x in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
