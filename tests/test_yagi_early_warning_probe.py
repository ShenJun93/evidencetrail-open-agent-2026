"""Fixed historical publisher candidate must not become a new operational alert.

The positive archived-byte proof is done only by the CLI against the real
2024 Wayback HTTP payload. No mocked network transport constitutes a live
Zetaris or Meterless sponsor call.
"""
from __future__ import annotations

import json
import unittest

from run_yagi_early_warning_probe import (
    ARCHIVE_URL, CDX_SHA1_B32, CDX_URL, MAX_RAW, ORIGINAL, STAMP,
    article_warning_marker, attest_saved_snapshot, fetch_pinned, validate_cdx,
)


def fake_cdx(digest=CDX_SHA1_B32, url=ORIGINAL, code="200", stamp=STAMP):
    return json.dumps([
        ["timestamp", "original", "statuscode", "digest"],
        [stamp, url, code, digest],
    ]).encode()


class IndependentArchivedWarningProofTests(unittest.TestCase):
    def test_fixed_cdx_entry_accepts_only_expected_2024_clock_and_digest(self):
        validate_cdx(fake_cdx())

    def test_altered_cdx_digest_date_status_or_source_rejected(self):
        samples = (
            fake_cdx(digest="A" * 32),
            fake_cdx(url="https://example.invalid/stolen"),
            fake_cdx(code="302"),
            fake_cdx(stamp="20240908162930"),
            b"not json",
        )
        for blob in samples:
            with self.subTest(blob=blob[:45]):
                with self.assertRaises(ValueError):
                    validate_cdx(blob)

    def test_only_fixed_2024_wayback_url_allowed(self):
        cases = (
            "http://web.archive.org/web/20240907162930id_/https://example.invalid",
            "https://web.archive.org/web/20250907162930id_/" + ORIGINAL,
            "https://example.invalid/api/keys",
        )
        for url in cases:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "UNPINNED_WAYBACK"):
                    fetch_pinned(url, MAX_RAW, fake_get=lambda _: self.fail("network called"))

    def test_modified_html_with_fake_valid_index_cannot_be_attested(self):
        with self.assertRaisesRegex(ValueError, "DIGEST_NOT_MATCH_CDX"):
            attest_saved_snapshot(fake_cdx(), b"modified data")

    def test_allowlisted_fake_transport_response_bounded(self):
        with self.assertRaisesRegex(ValueError, "INVALID_OR_TOO_LARGE"):
            fetch_pinned(ARCHIVE_URL, MAX_RAW, fake_get=lambda _: b"x" * (MAX_RAW + 1))
        self.assertEqual(
            fetch_pinned(CDX_URL, 50_000, fake_get=lambda _: b"[]"),
            b"[]",
        )

    def test_district_warning_must_be_inside_hazard_six_hour_context(self):
        html = (
            "<h3>Danh sách các khu vực có nguy cơ xảy ra lũ quét, "
            "sạt lở đất trong 06 giờ tới</h3>"
            "<table><tr><td>Yên Bái</td><td>Lục Yên, Văn Chấn</td></tr></table>"
        ).encode()
        flags = article_warning_marker(html)
        self.assertTrue(all(flags.values()))

    def test_footer_luc_yen_does_not_count_as_2024_warning(self):
        html = b"<p>Random city text</p><footer>" + (
            "Lục Yên - tin liên quan".encode()
        ) + b"</footer>"
        flags = article_warning_marker(html)
        self.assertTrue(flags["named_district_luc_yen"])
        self.assertFalse(flags["district_in_hazard_table_not_just_footer"])
        self.assertFalse(flags["warning_horizon_next_6_hours_before_district"])

    def test_missing_six_hour_horizon_never_yields_risk_signal(self):
        html = "<h3>Danh sách các khu vực có nguy cơ lũ quét, sạt lở đất</h3><p>Lục Yên</p>".encode()
        flags = article_warning_marker(html)
        self.assertFalse(flags["warning_horizon_next_6_hours_before_district"])


if __name__ == "__main__":
    unittest.main()
