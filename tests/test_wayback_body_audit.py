"""Isolated fake archive bytes. None of these fixtures is a real Yagi attestation."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import unittest
from datetime import datetime

from run_wayback_index_audit import SOURCES, url_for_source
from run_wayback_body_audit import (
    MAX_DECODED_BYTES, allowed_capture, audit_source, decode_body,
    fetch_archived_payload, publisher_text, verify_capture,
)

SID = "GOV-2024-09-08-1637"
URL, _ = url_for_source(SID)
HTML = (
    "<!doctype html><html><head><title>Bão Yagi 08/09/2024</title></head>"
    "<body><main><article>Lục Yên, Sông Thao 31,40m, Ngòi Thia 45,98m, "
    "observed at 15 giờ, published 16:37 ICT</article></main></body></html>"
).encode("utf-8")


def fixture(raw: bytes, source_id=SID, clock="20240908112146"):
    original, _ = url_for_source(source_id)
    digest = base64.b32encode(hashlib.sha1(raw).digest()).decode("ascii").rstrip("=")
    cdx = json.dumps([
        ["timestamp", "original", "statuscode", "digest"],
        [clock, original, "200", digest],
    ]).encode()
    return cdx


def cdx_info(raw: bytes):
    from run_wayback_index_audit import parse_cdx
    return parse_cdx(SID, fixture(raw))


class ArchiveSavedPayloadSafetyTests(unittest.TestCase):
    def test_plain_original_bytes_match_cdx_and_check_article_body(self):
        info = cdx_info(HTML)
        result = verify_capture(SID, info, HTML)
        self.assertTrue(result["saved_payload_sha1_base32_matches_cdx"])
        self.assertTrue(result["archived_body_corroborated"])
        self.assertEqual(result["saved_payload_encoding"], "plain")
        self.assertFalse(result["historical_first_publication_time_verified"])
        self.assertFalse(result["strict_asof_2024_source_promoted"])
        self.assertEqual(result["first_2024_capture_utc"], "2024-09-08T11:21:46Z")

    def test_original_gzip_digest_matches_before_bounded_decompression(self):
        raw = gzip.compress(HTML)
        info = cdx_info(raw)
        result = verify_capture(SID, info, raw)
        self.assertTrue(result["saved_payload_sha1_base32_matches_cdx"])
        self.assertTrue(result["archived_body_corroborated"])
        self.assertEqual(result["saved_payload_encoding"], "gzip")
        self.assertEqual(result["decoded_publisher_html_sha256"], hashlib.sha256(HTML).hexdigest())
        self.assertNotEqual(result["saved_payload_sha256"], result["decoded_publisher_html_sha256"])

    def test_tampered_body_same_cdx_fails_corroboration(self):
        body = HTML.replace(b"31,40m", b"33,90m")
        info = cdx_info(HTML)
        result = verify_capture(SID, info, body)
        self.assertFalse(result["saved_payload_sha1_base32_matches_cdx"])
        self.assertFalse(result["archived_body_corroborated"])

    def test_script_and_comment_only_keywords_cannot_pass_visible_content(self):
        script = (b"<html><!--L\xc3\xbac Y\xc3\xaan 31,40 Ng\xc3\xb2i Thia 45,98 15 gi\xe1\xbb\x9d-->"
                  b"<script>var a='L\xc3\xbac Y\xc3\xaan S\xc3\xb4ng Thao 31,40 Ng\xc3\xb2i Thia 45,98 15 gi\xe1\xbb\x9d'</script>"
                  b"<body>Not the article</body></html>")
        result = verify_capture(SID, cdx_info(script), script)
        self.assertFalse(result["archived_body_corroborated"])

    def test_gzip_bomb_bounded(self):
        raw = gzip.compress(b"x" * (MAX_DECODED_BYTES + 5))
        with self.assertRaisesRegex(ValueError, "DECOMPRESSED_BYTES_TOO_LARGE"):
            decode_body(raw)

    def test_bad_gzip_rejected(self):
        with self.assertRaises(ValueError):
            decode_body(b"\x1f\x8bbroken")

    def test_capture_url_pin_prevents_network_to_alternate_host(self):
        info = cdx_info(HTML)
        info["first_capture_archive_url"] = "https://evil.invalid/archive"
        with self.assertRaisesRegex(ValueError, "ARCHIVE_URL_OUTSIDE_PINNED_CDX"):
            fetch_archived_payload(
                SID, info, get=lambda _: self.fail("External access not allowed")
            )

    def test_reject_alternate_archive_timestamp_path(self):
        info = cdx_info(HTML)
        info["first_capture_archive_url"] = info["first_capture_archive_url"].replace(
            "20240908112146", "20250908112146"
        )
        with self.assertRaisesRegex(ValueError, "ARCHIVE_CAPTURE_TIMESTAMP_INVALID"):
            allowed_capture(SID, info)

    def test_missing_cdx_rows_cannot_probe_html(self):
        header_only = json.dumps([
            ["timestamp", "original", "statuscode", "digest"]
        ]).encode()
        result = audit_source(
            SID, get_cdx=lambda url: header_only,
            get_body=lambda _: self.fail("No CDX row should not fetch HTML"),
        )
        self.assertFalse(result["archived_body_corroborated"])
        self.assertEqual(result["evidence_level"], "NO_2024_WAYBACK_CAPTURE")

    def test_live_like_fake_warc_gzip_fetch_uses_only_2024_fixed_source(self):
        archive = gzip.compress(HTML)
        seen = []
        result = audit_source(
            SID, get_cdx=lambda url: fixture(archive),
            get_body=lambda url: (seen.append(url), archive)[1],
        )
        self.assertEqual(len(seen), 1)
        self.assertIn(SOURCES[SID]["path"], seen[0])
        self.assertTrue(result["archived_body_corroborated"])

    def test_oversize_raw_test_transport_rejected(self):
        info = cdx_info(HTML)
        with self.assertRaisesRegex(ValueError, "RAW_BYTES_TOO_LARGE"):
            fetch_archived_payload(
                SID, info, get=lambda _: b"a" * 2_000_001
            )

    def test_body_proof_timeline_uses_capture_not_article_dateline(self):
        # Hypothetical trusted 2024 capture: news displayed at 16:37 must
        # NOT be counted at 16:45 when actual archive body is from 18:21.
        result = verify_capture(SID, cdx_info(HTML), HTML)
        self.assertEqual(result["2024_body_proven_by_archive_asof"], {
            "16:30_ICT": False, "16:45_ICT": False, "18:30_ICT": True,
        })

    def test_archive_content_mismatch_prevents_any_proof_time(self):
        corrupted = HTML + b"<!-- a later edit -->"
        result = verify_capture(SID, cdx_info(HTML), corrupted)
        self.assertFalse(any(result["2024_body_proven_by_archive_asof"].values()))

    def test_valid_early_capture_is_visible_only_after_early_crawl(self):
        early_id = "GOV-2024-09-08-1530"
        raw = b"<article>Yen Bai canh bao lu quet va sat lo luc 15:30</article>"
        original, _ = url_for_source(early_id)
        dig = base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")
        from run_wayback_index_audit import parse_cdx
        cdx = json.dumps([
            ["timestamp", "original", "statuscode", "digest"],
            ["20240908085144", original, "200", dig],
        ]).encode()
        info = parse_cdx(early_id, cdx)
        # Fixture is intentionally ASCII so its Vietnamese article-marker
        # requirements fail; nothing may be promoted from an exact digest alone.
        result = verify_capture(early_id, info, raw)
        self.assertFalse(any(result["2024_body_proven_by_archive_asof"].values()))

    def test_later_capture_not_original_publication_clock(self):
        result = verify_capture(SID, cdx_info(HTML), HTML)
        self.assertFalse(result["historical_first_publication_time_verified"])
        self.assertFalse(result["third_independent_source_created"])


if __name__ == "__main__":
    unittest.main()
