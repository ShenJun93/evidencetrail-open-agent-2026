"""Finite-lived hazard bulletin vs archive capture timestamp.

No historical alert is minted from a dated URL or simulated clock. These
pure tests contain no original government article bytes or live sponsor calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from evidencetrail.temporal_validity import assess_time_limited_warning

UTC = timezone.utc
CAPTURE = datetime(2024, 9, 7, 16, 29, 30, tzinfo=UTC)
ASOF_1630_NEXT_DAY = datetime(2024, 9, 8, 9, 30, tzinfo=UTC)
ASOF_1645_NEXT_DAY = datetime(2024, 9, 8, 9, 45, tzinfo=UTC)


class ForecastHorizonSafetyTests(unittest.TestCase):
    def assess(self, asof, issued=None, horizon=6):
        return assess_time_limited_warning(
            archived_at_utc=CAPTURE,
            as_of_utc=asof,
            max_forecast_hours=horizon,
            issued_at_independently_verified_utc=issued,
        )

    def test_verified_sept7_archive_not_active_sept8_1630(self):
        result = self.assess(ASOF_1630_NEXT_DAY)
        self.assertTrue(result["archive_body_available_by_asof"])
        self.assertEqual(result["state"], "WARNING_EXPIRED_BY_PROVEN_UPPER_BOUND")
        self.assertFalse(result["risk_warning_verified_active"])
        self.assertEqual(result["latest_possible_expiry_utc"], "2024-09-07T22:29:30Z")

    def test_verified_sept7_archive_not_active_sept8_1645(self):
        result = self.assess(ASOF_1645_NEXT_DAY)
        self.assertEqual(result["state"], "WARNING_EXPIRED_BY_PROVEN_UPPER_BOUND")
        self.assertTrue(result["archive_body_available_by_asof"])

    def test_capture_plus_three_hours_does_not_prove_still_active(self):
        result = self.assess(CAPTURE + timedelta(hours=3))
        self.assertEqual(result["state"], "WARNING_MAY_BE_ACTIVE_BUT_ISSUANCE_UNVERIFIED")
        self.assertFalse(result["risk_warning_verified_active"])

    def test_at_capture_alone_does_not_prove_new_warning_active(self):
        result = self.assess(CAPTURE)
        self.assertEqual(result["state"], "WARNING_MAY_BE_ACTIVE_BUT_ISSUANCE_UNVERIFIED")
        self.assertFalse(result["risk_warning_verified_active"])

    def test_before_archive_not_established_available(self):
        result = self.assess(CAPTURE - timedelta(seconds=1))
        self.assertEqual(result["state"], "ARCHIVE_NOT_YET_AVAILABLE")
        self.assertFalse(result["archive_body_available_by_asof"])

    def test_authenticated_issued_time_can_prove_active_in_hypothetical_fixture(self):
        issued = CAPTURE - timedelta(hours=1)
        result = self.assess(CAPTURE + timedelta(hours=1), issued=issued)
        self.assertTrue(result["risk_warning_verified_active"])
        self.assertEqual(result["state"], "WARNING_ACTIVE_WITH_INDEPENDENT_ISSUANCE_PROOF")
        expired = self.assess(CAPTURE + timedelta(hours=6), issued=issued)
        self.assertEqual(expired["state"], "WARNING_EXPIRED_BY_PROVEN_UPPER_BOUND")

    def test_issued_after_capture_rejected(self):
        with self.assertRaisesRegex(ValueError, "contradictory"):
            self.assess(CAPTURE, issued=CAPTURE + timedelta(seconds=1))

    def test_untrusted_naive_datetimes_are_rejected(self):
        for naive_capture, naive_asof in (
            (CAPTURE.replace(tzinfo=None), ASOF_1630_NEXT_DAY),
            (CAPTURE, ASOF_1630_NEXT_DAY.replace(tzinfo=None)),
        ):
            with self.subTest(cap=naive_capture, asof=naive_asof):
                with self.assertRaisesRegex(ValueError, "timezone_aware"):
                    assess_time_limited_warning(
                        archived_at_utc=naive_capture, as_of_utc=naive_asof,
                        max_forecast_hours=6,
                    )

    def test_bounded_positive_hours_rejects_bool_zero_negative_huge(self):
        for hours in (True, 0, -1, 73, 9000):
            with self.subTest(hours=hours):
                with self.assertRaisesRegex(ValueError, "bounded_positive"):
                    self.assess(ASOF_1630_NEXT_DAY, horizon=hours)


if __name__ == "__main__":
    unittest.main()
