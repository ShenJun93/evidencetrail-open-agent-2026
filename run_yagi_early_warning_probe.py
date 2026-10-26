"""Read-only independent Yagi 2024 warning candidate with an expiry-safe gate.

Do NOT import this bulletin into Zetaris or use it as a current operational
warning. Its main body names Luc Yen in a NEXT SIX HOURS hazard table archived
the previous night. Source existence does not extend the risk horizon.

No credentials, arbitrary remote URLs, installer, full article persistence,
model call or default EvidenceTrail catalog mutation.
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
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from evidencetrail.temporal_validity import assess_time_limited_warning

ORIGINAL = (
    "https://xaydungchinhsach.chinhphu.vn/"
    "bao-yagi-giat-cap-15-huong-vao-vinh-bac-bo-1192409021359583.htm"
)
STAMP = "20240907162930"
CAPTURE_UTC = datetime(2024, 9, 7, 16, 29, 30, tzinfo=timezone.utc)
CDX_SHA1_B32 = "4BZFSNM5CAGLWXI6MQMQWHJAQZHDS2BY"
RAW_SHA256 = "cd6be20ae2fdd569bd838a65f5e1b4bd2ce34a47835e12c6337c16dd6151092b"
HTML_SHA256 = "d0c5c8d5545ac6893860330e0fd2e4059e59d92797139d7c1c2395d6a9866e9d"
ARCHIVE_URL = f"https://web.archive.org/web/{STAMP}id_/{ORIGINAL}"
CDX_URL = (
    "https://web.archive.org/cdx/search/cdx?"
    + urllib.parse.urlencode({
        "url": ORIGINAL, "output": "json", "from": "2024", "to": "2024",
        "fl": "timestamp,original,statuscode,digest", "limit": "100",
    })
)
OUT = Path("acceptance/logs/yagi-independent-early-2024-warning.json")
MAX_RAW = 2_000_000
MAX_DECODED = 3_000_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_pinned(url: str, max_bytes: int, *, fake_get=None) -> bytes:
    if url not in (CDX_URL, ARCHIVE_URL) or max_bytes not in (50_000, MAX_RAW):
        raise ValueError("UNPINNED_WAYBACK_ENDPOINT_REFUSED")
    if fake_get is not None:
        body = fake_get(url)
    else:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )
        with opener.open(
            urllib.request.Request(url, headers={
                "User-Agent": "EvidenceTrail-2024-Research-Only/1.0",
                "Accept-Encoding": "identity",
            }), timeout=16,
        ) as resp:
            if resp.status != 200:
                raise ValueError("ARCHIVE_RESPONSE_NOT_200")
            body = resp.read(max_bytes + 1)
    if not isinstance(body, bytes) or len(body) > max_bytes:
        raise ValueError("ARCHIVE_RESPONSE_INVALID_OR_TOO_LARGE")
    return body


def validate_cdx(raw: bytes) -> None:
    rows = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(rows, list) or not rows or rows[0] != [
        "timestamp", "original", "statuscode", "digest"
    ]:
        raise ValueError("CDX_INDEX_STRUCTURE_INVALID")
    seen = [row for row in rows[1:]
            if isinstance(row, list) and len(row) == 4
            and row[0] == STAMP and row[1] == ORIGINAL]
    if len(seen) != 1 or seen[0][2:] != ["200", CDX_SHA1_B32]:
        raise ValueError("CDX_PINNED_ARCHIVE_CAPTURE_MISMATCH")


def article_warning_marker(plaintext_html: bytes) -> dict[str, bool]:
    decoded = plaintext_html.decode("utf-8-sig", errors="replace")
    decoded = re.sub(r"(?is)<!--.*?-->", " ", decoded)
    decoded = re.sub(
        r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1\s*>",
        " ", decoded
    )
    article = unicodedata.normalize(
        "NFC", html.unescape(re.sub(r"(?s)<[^>]*>", " ", decoded))
    ).casefold()
    article = re.sub(r"\s+", " ", article)
    idx = article.find("lục yên")
    prefix = article[max(0, idx - 2800):idx] if idx >= 0 else ""
    return {
        "named_district_luc_yen": idx >= 0,
        "district_in_hazard_table_not_just_footer": (
            idx >= 0
            and "danh sách các khu vực" in prefix
            and "lũ quét" in prefix and "sạt lở đất" in prefix
        ),
        "warning_horizon_next_6_hours_before_district": (
            "06 giờ tới" in prefix if prefix else False
        ),
    }


def attest_saved_snapshot(cdx: bytes, saved: bytes) -> dict:
    validate_cdx(cdx)
    if base64.b32encode(hashlib.sha1(saved).digest()).decode().rstrip("=") != CDX_SHA1_B32:
        raise ValueError("SAVED_ORIGINAL_DIGEST_NOT_MATCH_CDX")
    if hashlib.sha256(saved).hexdigest() != RAW_SHA256:
        raise ValueError("SAVED_ORIGINAL_SHA256_REVIEW_PIN_MISMATCH")
    if not saved.startswith(b"\x1f\x8b"):
        raise ValueError("ARCHIVED_GZIP_ENCODING_CHANGED")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(saved)) as g:
            plain = g.read(MAX_DECODED + 1)
    except (OSError, EOFError) as exc:
        raise ValueError("ARCHIVED_BODY_DECOMPRESSION_FAILURE") from exc
    if len(plain) > MAX_DECODED or hashlib.sha256(plain).hexdigest() != HTML_SHA256:
        raise ValueError("ARCHIVED_HTML_SHA256_REVIEW_PIN_MISMATCH")
    flags = article_warning_marker(plain)
    if not all(flags.values()):
        raise ValueError("HISTORICAL_WARNING_CONTEXT_NOT_CORROBORATED")
    return {
        "source": "GOVPOLICY-2024-09-07-LUCYEN-6H",
        "publisher": "xaydungchinhsach.chinhphu.vn",
        "archive_capture_utc": CAPTURE_UTC.isoformat().replace("+00:00", "Z"),
        "archive_url": ARCHIVE_URL,
        "original_url": ORIGINAL,
        "saved_gzip_sha256": RAW_SHA256,
        "decoded_html_sha256": HTML_SHA256,
        "index_digest_verified": True,
        "publisher_main_article_warning_markers": flags,
        "archive_bytes_correlated_with_cdx": True,
        "first_publisher_publication_verified": False,
        "warning_issuance_clock_independently_verified": False,
        "warning_horizon_hours": 6,
        "live_zetaris_sql_query": False,
        "new_source_added_to_default_catalog": False,
    }


def build_report(cdx: bytes, archived_bytes: bytes) -> dict:
    report = attest_saved_snapshot(cdx, archived_bytes)
    for label, asof in (
        ("16:30_08SEP_ICT", datetime(2024, 9, 8, 9, 30, tzinfo=timezone.utc)),
        ("16:45_08SEP_ICT", datetime(2024, 9, 8, 9, 45, tzinfo=timezone.utc)),
    ):
        report[label] = assess_time_limited_warning(
            archived_at_utc=CAPTURE_UTC,
            as_of_utc=asof,
            max_forecast_hours=6,
        )
    report["verdict"] = "NOT_COMPUTED_RESEARCH_ONLY"
    report["recommendation"] = (
        "A 2024 archival source exists but its six-hour forecast horizon cannot "
        "justify a next-day operational WARN. Keep it historical only."
    )
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", default=str(OUT))
    a = p.parse_args()
    verified = build_report(
        fetch_pinned(CDX_URL, 50_000), fetch_pinned(ARCHIVE_URL, MAX_RAW)
    )
    dest = Path(a.receipt)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(verified, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({
        "source": verified["source"],
        "archive_capture": verified["archive_capture_utc"],
        "warning_1630": verified["16:30_08SEP_ICT"]["state"],
        "warning_1645": verified["16:45_08SEP_ICT"]["state"],
        "normal_model_decision": verified["verdict"],
        "new_source_in_zetaris": False,
        "receipt": str(dest),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
