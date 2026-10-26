"""Offline fake official-text contracts for the Nightshift release admission gate."""
from __future__ import annotations

import json
import unittest

from run_nightshift_release_gate import evaluate_release, read_publisher_text

SHA = "b" * 64
SETUP = "Nightshift_1.2.2_x64-setup.exe"


def fixture(sha=SHA, signature="NotSigned", build_sha=SHA, sums_sha=SHA, setup=SETUP):
    manifest = json.dumps({
        "release": "2026.10.22-win.11",
        "components": [{"artifacts": [{
            "file": setup, "method": "nsis", "size": 654031748, "sha256": sha
        }]}],
    })
    build = (f"artifact:      {setup}\n"
             f"size:          654031748 bytes\n"
             f"sha256:        {build_sha}\n"
             f"signature:     {signature}\n")
    sums = f"{sums_sha}  {setup}\n"
    return manifest, build, sums


class NoUnsignedInstallerBailoutTests(unittest.TestCase):
    def test_metadata_consistent_but_unsigned_is_still_blocked(self):
        r = evaluate_release(*fixture())
        self.assertTrue(r["metadata_hashes_and_size_consistent"])
        self.assertEqual(r["status"], "INSTALL_BLOCKED_UNSIGNED")
        self.assertFalse(r["installer_downloaded"])
        self.assertFalse(r["local_authenticode_trust_verified"])
        self.assertEqual(r["runtime_chat_completion"], "NOT_CALLED")
        self.assertEqual(r["organizer_eligibility"], "NOT_VERIFIED")

    def test_mismatch_in_publisher_hashes_blocks(self):
        r = evaluate_release(*fixture(build_sha="c" * 64))
        self.assertFalse(r["metadata_hashes_and_size_consistent"])
        self.assertEqual(r["status"], "INSTALL_BLOCKED_METADATA_MISMATCH")

    def test_manifest_and_sums_mismatch_blocks(self):
        r = evaluate_release(*fixture(sums_sha="c" * 64))
        self.assertEqual(r["status"], "INSTALL_BLOCKED_METADATA_MISMATCH")

    def test_publisher_says_signed_still_not_a_verified_binary(self):
        r = evaluate_release(*fixture(signature="Signed"))
        self.assertEqual(r["status"], "INSTALL_BLOCKED_BINARY_NOT_VERIFIED")

    def test_reject_missing_or_ambiguous_windows_artifact(self):
        for broken in (
            fixture(setup="unrelated.exe"),
            (json.dumps({"components": [
                {"artifacts": [{"file": SETUP, "size": 1, "sha256": SHA},
                               {"file": SETUP, "size": 1, "sha256": SHA}]}
            ]}), "", ""),
        ):
            with self.assertRaises(ValueError):
                evaluate_release(*broken)

    def test_remote_fetch_is_not_a_generic_file_downloader(self):
        with self.assertRaises(ValueError):
            read_publisher_text("Nightshift_1.2.2_x64-setup.exe")
