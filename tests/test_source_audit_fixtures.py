"""False-positive and true-positive safety tests for release manifest scanner."""
import unittest
from run_submission_source_audit import classify


class FixtureClassificationTests(unittest.TestCase):
    def test_synthetic_nvidia_unit_fixture_is_review_not_public_certification(self):
        looks_like = b"nv" + b"api-" + b"FAKE_ONLY_FOR_OFFLINE_UNIT_TEST_2026"
        self.assertEqual(
            classify(b'KEY="' + looks_like + b'"', "tests/test_case.py"),
            ([], ["SYNTHETIC_NVIDIA_TEST_TOKEN"])
        )

    def test_unmarked_nvidia_token_is_blocker_even_in_tests(self):
        looks_like = b"nv" + b"api-" + b"Z" * 36
        self.assertEqual(
            classify(b'KEY="' + looks_like + b'"', "tests/test_case.py"),
            (["NVIDIA_CREDENTIAL"], [])
        )

    def test_fake_token_is_never_exempted_in_production_source(self):
        looks_like = b"nv" + b"api-" + b"FAKE_ONLY_FOR_OFFLINE_UNIT_TEST_2026"
        self.assertEqual(
            classify(b'KEY="' + looks_like + b'"', "evidencetrail/app.py"),
            (["NVIDIA_CREDENTIAL"], [])
        )


if __name__ == "__main__":
    unittest.main()
