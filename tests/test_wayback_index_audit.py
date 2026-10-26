"""Offline CDX metadata coverage is not an automatic strict evidence upgrade."""
from __future__ import annotations

import json
import unittest

from run_wayback_index_audit import (
    SOURCES, build_report, parse_cdx, url_for_source,
)


def response(source_id):
    original, _ = url_for_source(source_id)
    indexed = {
        "GOV-2024-09-08-1530": [
            ["20240908085144", original, "200", "A"*32],
            ["20240909012802", original, "200", "B"*32],
        ],
        "GOV-2024-09-08-1621": [
            ["20240908093833", original, "200", "C"*32],
        ],
        "GOV-2024-09-08-1637": [
            ["20240908112146", original, "200", "D"*32],
        ],
    }
    return json.dumps([
        ["timestamp", "original", "statuscode", "digest"], *indexed[source_id]
    ]).encode()


class ArchivedIndexCoverageTests(unittest.TestCase):
    def test_three_captures_define_different_conservative_asof_clocks(self):
        for sid, expected in (
            ("GOV-2024-09-08-1530", (True, True, True)),
            ("GOV-2024-09-08-1621", (False, True, True)),
            ("GOV-2024-09-08-1637", (False, False, True)),
        ):
            with self.subTest(sid=sid):
                row = parse_cdx(sid, response(sid))
                self.assertEqual(tuple(row["coverage_at_clocks"].values()), expected)
                self.assertFalse(row["strict_content_eligible"])
                self.assertFalse(row["archived_html_verified"])

    def test_different_cdx_digests_are_not_first_publication_proof(self):
        r = parse_cdx("GOV-2024-09-08-1530", response("GOV-2024-09-08-1530"))
        self.assertTrue(r["multiple_observed_2024_content_digests"])
        self.assertFalse(r["strict_content_eligible"])

    def test_wrong_url_200_capture_is_rejected(self):
        sid = "GOV-2024-09-08-1637"
        arr = json.loads(response(sid))
        arr[1][1] = "https://spoof.invalid/article"
        r = parse_cdx(sid, json.dumps(arr).encode())
        self.assertIsNone(r["first_2024_capture_utc"])
        self.assertFalse(any(r["coverage_at_clocks"].values()))

    def test_non_200_timestamp_or_digest_invalid_cannot_count(self):
        sid = "GOV-2024-09-08-1637"
        arr = json.loads(response(sid))
        for index, invalid in ((2, "404"), (0, "20230908112146"), (3, "NOT_SHA1")):
            altered = json.loads(response(sid))
            altered[1][index] = invalid
            with self.subTest(invalid=invalid):
                result = parse_cdx(sid, json.dumps(altered).encode())
                self.assertEqual(result["known_2024_capture_count"], 0)

    def test_no_external_arbitrary_archive_source_allowed(self):
        with self.assertRaises(ValueError):
            url_for_source("https://evil.invalid/")

    def test_metadata_only_report_never_licenses_strict_sources(self):
        response_by_url = {url_for_source(sid)[1]: response(sid) for sid in SOURCES}
        report = build_report(lambda url: response_by_url[url])
        self.assertEqual(len(report["sources"]), 3)
        self.assertFalse(report["first_publication_minutes_verified"])
        self.assertEqual(report["strict_source_promotion"], "NOT_AUTHORIZED_BY_CDX_ALONE")
        self.assertTrue(all(not x["strict_content_eligible"] for x in report["sources"]))


if __name__ == "__main__":
    unittest.main()
