"""Unit fixtures for opt-in, no-decision live archive-to-strict firewall gate.

These fake receipt dictionaries are NOT independent Wayback attestations.
Production CLI must fetch and verify original archived bytes itself.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from evidencetrail.catalog import by_id
from evidencetrail.models import ProvenanceQuality
from run_wayback_attested_firewall import (
    PINNED_ARCHIVE, bind_verified_source, build_strict_source_matrix,
)
from run_wayback_index_audit import url_for_source


def fake_receipt(sid: str):
    clock, cdx, rawsha, htmlsha = PINNED_ARCHIVE[sid]
    original, _ = url_for_source(sid)
    return {
        "source_id": sid,
        "archived_body_corroborated": True,
        "saved_payload_sha1_base32_matches_cdx": True,
        "historical_first_publication_time_verified": False,
        "strict_asof_2024_source_promoted": False,
        "first_2024_capture_utc": clock,
        "archive_cdx_sha1_base32": cdx,
        "saved_payload_sha256": rawsha,
        "decoded_publisher_html_sha256": htmlsha,
        "archive_original_url": original,
        "publisher_body_content_markers": {"fictional_unit_marker": True},
    }


class ReviewedArchiveBodyBindingTests(unittest.TestCase):
    def test_real_firewall_receives_archival_capture_clocks_not_datelines(self):
        receipts = {sid: fake_receipt(sid) for sid in PINNED_ARCHIVE}
        result = build_strict_source_matrix(receipts)
        levels = result["by_asof"]
        self.assertEqual(levels["16:30_ICT"]["archive_attested_source_ids"],
                         ["GOV-2024-09-08-1530"])
        self.assertEqual(levels["16:45_ICT"]["archive_attested_source_ids"],
                         ["GOV-2024-09-08-1530", "GOV-2024-09-08-1621"])
        self.assertEqual(levels["18:30_ICT"]["archive_attested_source_ids"],
                         list(PINNED_ARCHIVE))
        for level in levels.values():
            self.assertEqual(level["verdict"], "NOT_COMPUTED_PROVENANCE_ONLY")
            self.assertEqual(level["live_sponsor_receipt"], "NONE")
        self.assertFalse(result["default_catalog_modified"])
        self.assertFalse(result["decisional_pipeline_invoked"])

    def test_binding_is_ephemeral_and_original_catalog_remains_unpromoted(self):
        sid = "GOV-2024-09-08-1637"
        bound = bind_verified_source(sid, fake_receipt(sid))
        self.assertEqual(bound.provenance_quality, ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT)
        self.assertEqual(bound.first_availability_proven_utc.isoformat(),
                         "2024-09-08T11:21:46+00:00")
        catalog = by_id(sid)
        self.assertNotEqual(catalog.provenance_quality, bound.provenance_quality)
        self.assertIsNone(catalog.first_availability_proven_utc)

    def test_pinned_decoded_html_hash_change_is_rejected(self):
        sid = "GOV-2024-09-08-1637"
        fake = fake_receipt(sid)
        fake["decoded_publisher_html_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "ARCHIVED_BYTES_DIFFER"):
            bind_verified_source(sid, fake)

    def test_pinned_cdx_rawhash_and_capture_clock_changes_rejected(self):
        sid = "GOV-2024-09-08-1621"
        for field, value in (
            ("archive_cdx_sha1_base32", "A" * 32),
            ("saved_payload_sha256", "b" * 64),
            ("first_2024_capture_utc", "2024-09-08T09:20:00Z"),
        ):
            with self.subTest(field=field):
                fake = fake_receipt(sid)
                fake[field] = value
                with self.assertRaises(ValueError):
                    bind_verified_source(sid, fake)

    def test_wrong_or_unreviewed_original_origin_denied(self):
        sid = "GOV-2024-09-08-1530"
        fake = fake_receipt(sid)
        fake["archive_original_url"] = "https://evil.invalid/future-report"
        with self.assertRaisesRegex(ValueError, "ARCHIVE_ORIGIN_MISMATCH"):
            bind_verified_source(sid, fake)
        with self.assertRaisesRegex(ValueError, "SOURCE_NOT_IN_PINNED_ARCHIVE"):
            bind_verified_source("GOV-OTHER", fake)

    def test_fake_body_markers_or_unverified_body_denied(self):
        sid = "GOV-2024-09-08-1637"
        for field, value in (
            ("publisher_body_content_markers", {"lục_yên": False}),
            ("archived_body_corroborated", False),
            ("saved_payload_sha1_base32_matches_cdx", False),
        ):
            with self.subTest(field=field):
                fake = fake_receipt(sid)
                fake[field] = value
                with self.assertRaises(ValueError):
                    bind_verified_source(sid, fake)

    def test_partial_three_source_cannot_produce_strict_timeline(self):
        receipts = {sid: fake_receipt(sid) for sid in PINNED_ARCHIVE}
        receipts.pop("GOV-2024-09-08-1637")
        with self.assertRaisesRegex(ValueError, "THREE_DISTINCT"):
            build_strict_source_matrix(receipts)


if __name__ == "__main__":
    unittest.main()
