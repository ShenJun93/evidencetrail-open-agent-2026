"""Read-only September 2024 Wayback CDX coverage audit for three Yagi sources.

CDX timestamps establish that a URL was captured no later than the archived
crawl time. CDX metadata ALONE does NOT certify the article's archived content,
first-ever publication or editorial revision history. No content is promoted
to STRICT_AS_OF_2024 without separate original-byte checks.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = "https://baochinhphu.vn/"
CDX = "https://web.archive.org/cdx/search/cdx"
OUTPUT = Path("acceptance/logs/yagi-2024-archive-index.json")
LIMIT = 50_000
SOURCES = {
    "GOV-2024-09-08-1530": {
        "path": "canh-bao-16-tinh-co-nguy-co-lu-quet-sat-lo-dat-da-trong-6-gio-toi-102240908152851068.htm",
        "displayed_utc": "2024-09-08T08:30:00Z",
    },
    "GOV-2024-09-08-1621": {
        "path": "canh-bao-lu-quet-va-sat-lo-dat-tai-yen-bai-102240908160432222.htm",
        "displayed_utc": "2024-09-08T09:21:00Z",
    },
    "GOV-2024-09-08-1637": {
        "path": "tang-so-nguoi-bi-thuong-do-bao-yagi-102240908163127919.htm",
        "displayed_utc": "2024-09-08T09:37:00Z",
    },
}
CLOCKS = {
    "16:30_ICT": "2024-09-08T09:30:00Z",
    "16:45_ICT": "2024-09-08T09:45:00Z",
    "18:30_ICT": "2024-09-08T11:30:00Z",
}
DIGEST = re.compile(r"^[A-Z2-7]{32}$")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def url_for_source(source_id: str) -> tuple[str, str]:
    if source_id not in SOURCES:
        raise ValueError("UNKNOWN_ARCHIVE_SOURCE")
    original = ROOT + SOURCES[source_id]["path"]
    query = urlencode({
        "url": original,
        "output": "json",
        "filter": "statuscode:200",
        "from": "2024", "to": "2024",
        "fl": "timestamp,original,statuscode,digest",
        "limit": "15",
    })
    return original, CDX + "?" + query


def read_cdx(source_id: str, get=None) -> bytes:
    _, url = url_for_source(source_id)
    if get is not None:
        data = get(url)
        if not isinstance(data, bytes):
            raise ValueError("BAD_TEST_TRANSPORT_BYTES")
    else:
        request = urllib.request.Request(url, headers={
            "User-Agent": "EvidenceTrail-Wayback-CDX-Only/1.0",
            "Accept": "application/json",
        })
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )
        with opener.open(request, timeout=18) as response:
            if response.status != 200:
                raise ValueError("CDX_HTTP_NOT_200")
            data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("CDX_RESPONSE_EXCEEDS_LIMIT")
    return data


def to_datetime(value: str) -> datetime:
    if not re.fullmatch(r"2024[0-1][0-9][0-3][0-9][0-2][0-9][0-5][0-9][0-5][0-9]", value):
        raise ValueError("INVALID_CAPTURE_CLOCK")
    result = datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    if result.year != 2024:
        raise ValueError("CAPTURE_OUTSIDE_YEAR")
    return result


def parse_cdx(source_id: str, payload: bytes) -> dict:
    original, _ = url_for_source(source_id)
    try:
        rows = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("INVALID_CDX_JSON") from exc
    if not isinstance(rows, list) or not rows or rows[0] != [
        "timestamp", "original", "statuscode", "digest"
    ]:
        raise ValueError("INVALID_CDX_SCHEMA")
    candidates = []
    for row in rows[1:]:
        if not isinstance(row, list) or len(row) != 4:
            continue
        ts, url, code, digest = row
        if (
            url == original and code == "200" and isinstance(ts, str)
            and isinstance(digest, str) and DIGEST.fullmatch(digest)
        ):
            try:
                dt = to_datetime(ts)
            except ValueError:
                continue
            candidates.append((dt, ts, digest))
    if not candidates:
        return {
            "source_id": source_id, "original": original,
            "first_2024_capture_utc": None, "first_2024_cdx_digest": None,
            "known_2024_capture_count": 0,
            "multiple_observed_2024_content_digests": False,
            "coverage_at_clocks": {k: False for k in CLOCKS},
            "archived_html_verified": False, "strict_content_eligible": False,
        }
    candidates.sort()
    first, ts, digest = candidates[0]
    return {
        "source_id": source_id, "original": original,
        "displayed_publication_utc": SOURCES[source_id]["displayed_utc"],
        "first_2024_capture_utc": first.isoformat().replace("+00:00", "Z"),
        "first_2024_cdx_digest": digest,
        "first_capture_archive_url": f"https://web.archive.org/web/{ts}id_/{original}",
        "known_2024_capture_count": len(candidates),
        "multiple_observed_2024_content_digests": len({v[2] for v in candidates}) > 1,
        "coverage_at_clocks": {
            k: first <= datetime.fromisoformat(iso.replace("Z", "+00:00"))
            for k, iso in CLOCKS.items()
        },
        # Every source still needs a separate archived-original-content check.
        "archived_html_verified": False,
        "strict_content_eligible": False,
    }


def build_report(get=None) -> dict:
    rows = [parse_cdx(sid, read_cdx(sid, get)) for sid in SOURCES]
    return {
        "kind": "ARCHIVE_INDEX_COVERAGE_ONLY",
        "scope": "fixed three government Yagi articles, 2024 captures",
        "sources": rows,
        "first_publication_minutes_verified": False,
        "article_bytes_republished": False,
        "strict_source_promotion": "NOT_AUTHORIZED_BY_CDX_ALONE",
        "third_independent_zetaris_table": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", default=str(OUTPUT))
    args = p.parse_args()
    report = build_report()
    out = Path(args.receipt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "kind": report["kind"], "capture_utc": {
            x["source_id"]: x["first_2024_capture_utc"] for x in report["sources"]
        }, "strict_source_promotion": report["strict_source_promotion"],
        "receipt": str(out),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
