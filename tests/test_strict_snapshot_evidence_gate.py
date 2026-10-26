"""Strict historical firewall: index discovery is not article authentication.

This test uses synthetic dataclass mutations. Cases that mark a SourceRecord
AUTHENTICATED_2024_SNAPSHOT are artificial unit fixtures, NEVER a claim that
any actual Yagi page has authenticated immutable 2024 bytes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import unittest

from evidencetrail.catalog import all_catalog
from evidencetrail.firewall import availability_reason, filter_sources
from evidencetrail.models import ProvenanceQuality, RecordKind, ReplayMode

ICT_1630 = datetime(2024, 9, 8, 9, 30, tzinfo=timezone.utc)
ICT_1645 = datetime(2024, 9, 8, 9, 45, tzinfo=timezone.utc)
WAYBACK_CAPTURE_1637 = datetime(2024, 9, 8, 11, 21, 46, tzinfo=timezone.utc)
AFTER_CAPTURE_1830 = datetime(2024, 9, 8, 11, 30, tzinfo=timezone.utc)


def record(source_id):
    return next(s for s in all_catalog() if s.source_id == source_id)


class StrictSnapshotEvidenceAuthorityTests(unittest.TestCase):
    def test_backdated_claim_inside_curated_source_does_not_grant_strict_access(self):
        source = replace(
            record("GOV-2024-09-08-1637"),
            first_availability_proven_utc=datetime(2024, 9, 8, 8, 0, tzinfo=timezone.utc),
        )
        result = availability_reason(source, ICT_1630, ReplayMode.STRICT_AS_OF_2024)
        self.assertEqual(result, "STRICT_AS_OF_2024_snapshot_provenance_not_authenticated")

    def test_wayback_cdx_capture_time_alone_is_not_an_attestation(self):
        source = replace(
            record("GOV-2024-09-08-1637"),
            first_availability_proven_utc=WAYBACK_CAPTURE_1637,
        )
        for clock in (ICT_1645, AFTER_CAPTURE_1830):
            with self.subTest(clock=clock):
                self.assertEqual(
                    availability_reason(source, clock, ReplayMode.STRICT_AS_OF_2024),
                    "STRICT_AS_OF_2024_snapshot_provenance_not_authenticated",
                )

    def test_provenance_label_without_verified_clock_is_still_insufficient(self):
        source = replace(
            record("GOV-2024-09-08-1637"),
            provenance_quality=ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT,
            first_availability_proven_utc=None,
        )
        self.assertEqual(
            availability_reason(source, AFTER_CAPTURE_1830, ReplayMode.STRICT_AS_OF_2024),
            "STRICT_AS_OF_2024_unproven_first_availability",
        )

    def test_artificial_fully_verified_fixture_not_eligible_before_capture(self):
        source = replace(
            record("GOV-2024-09-08-1637"),
            provenance_quality=ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT,
            first_availability_proven_utc=WAYBACK_CAPTURE_1637,
        )
        self.assertEqual(
            availability_reason(source, ICT_1645, ReplayMode.STRICT_AS_OF_2024),
            "STRICT_AS_OF_2024_proven_availability_after_as_of",
        )
        # This tests the reducer only. It does NOT authenticate real Yagi HTML.
        self.assertIsNone(
            availability_reason(source, AFTER_CAPTURE_1830, ReplayMode.STRICT_AS_OF_2024)
        )

    def test_existing_real_catalog_has_no_promoted_strict_government_source(self):
        for source in all_catalog():
            if source.record_kind == RecordKind.GOVERNMENT_NEWS:
                with self.subTest(source=source.source_id):
                    self.assertNotEqual(
                        source.provenance_quality,
                        ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT,
                    )
                    self.assertIsNone(source.first_availability_proven_utc)
        eligible, excluded = filter_sources(
            all_catalog(), AFTER_CAPTURE_1830, ReplayMode.STRICT_AS_OF_2024
        )
        self.assertFalse(any(s.record_kind == RecordKind.GOVERNMENT_NEWS for s in eligible))
        self.assertTrue(any(x["source_id"] == "GOV-2024-09-08-1637" for x in excluded))

    def test_synthetic_capacity_still_distinct_not_public_evidence(self):
        source = record("SYN-CAP-YAGI-ALPHA-LUCYEN")
        self.assertEqual(source.record_kind, RecordKind.SYNTHETIC_CAPACITY)
        self.assertIsNone(
            availability_reason(source, ICT_1630, ReplayMode.STRICT_AS_OF_2024)
        )

    def test_retrospective_hindcast_cannot_use_false_verified_snapshot_label(self):
        hindcast = next(
            s for s in all_catalog() if s.record_kind == RecordKind.RETROSPECTIVE_HINDCAST
        )
        source = replace(
            hindcast,
            provenance_quality=ProvenanceQuality.AUTHENTICATED_2024_SNAPSHOT,
            first_availability_proven_utc=ICT_1630,
        )
        self.assertEqual(
            availability_reason(source, AFTER_CAPTURE_1830, ReplayMode.STRICT_AS_OF_2024),
            "RETROSPECTIVE_HINDCAST_not_operational_2024_forecast",
        )


if __name__ == "__main__":
    unittest.main()
