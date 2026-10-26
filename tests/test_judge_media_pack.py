"""No-network fixtures for the generated judge media pack; no vendor credentials."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_judge_media_pack as media


PNG = b"\x89PNG\r\n\x1a\n"


class MediaPackContracts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / media.RECEIPT).parent.mkdir(parents=True, exist_ok=True)
        (self.root / media.BROWSER).mkdir(parents=True, exist_ok=True)
        self.head = "a" * 40
        self.receipt = {
            "kind": "EVIDENCETRAIL_COLD_JUDGE_REPLAY_V1",
            "source_git_head": self.head,
            "status": "PASS",
            "tracked_clean_before_tests": True,
            "worktree_clean_before_tests": True,
            "clean_keyless_source_replay": True,
            "ignored_env_file_present_before_tests": False,
            "meterless_vendor_present_before_tests": False,
            "external_sponsor_requests_authorized": False,
            "key_file_read_by_this_runner": False,
            "nvidia_direct_sponsor_verified": False,
            "nebius_structured_inference_verified": False,
            "organizer_eligibility_verified": False,
            "actual_disaster_forecast_accuracy_verified": False,
            "steps": {
                "python_acceptance": {"status": "PASS", "python_tests": 309, "exit_code": 0},
                "chronology": {"status": "PASS", "pass": 20, "total": 20, "exit_code": 0},
                "edge_e2e": {"status": "PASS", "scenarios": 3, "exit_code": 0},
            },
        }
        self.smoke = {
            "status": "REAL_EDGE_BROWSER_3_SCENARIOS_PASS",
            "sample_only": True,
            "no_real_nightshift_or_zetaris_call": True,
            "scenarios": [
                "16:45 reported WARN simulated minimum2 pivotal2",
                "16:45 strict INSUFFICIENT_EVIDENCE",
                "16:30 reported INSUFFICIENT_EVIDENCE",
            ],
        }
        for i, (name, _, _, _) in enumerate(media.FILES):
            (self.root / media.BROWSER / name).write_bytes(
                PNG + bytes([i + 1]) * 13000
            )
        self.write_inputs()

    def write_inputs(self):
        (self.root / media.RECEIPT).write_text(
            json.dumps(self.receipt), encoding="utf8"
        )
        (self.root / media.BROWSER / "counterfactual-browser-smoke.json").write_text(
            json.dumps(self.smoke), encoding="utf8"
        )

    def invoke(self):
        with patch("build_judge_media_pack._git_head", return_value=self.head):
            return media.build(self.root)

    def test_success_creates_real_capture_gallery_and_sanitized_manifest(self):
        result = self.invoke()
        self.assertEqual(result["status"], "OFFLINE_MEDIA_PACK_BUILT")
        dest = self.root / media.OUTPUT
        page = (dest / "index.html").read_text("utf8")
        manifest = json.loads((dest / "manifest.json").read_text("utf8"))
        self.assertIn("SIMULATED WARN", page)
        self.assertIn("FICTIONAL", page)
        self.assertIn("NOT PROVEN", page)
        self.assertEqual(len(manifest["screenshots"]), 3)
        self.assertFalse(manifest["nvidia_nemotron_inference_verified"])
        self.assertEqual(result["python_tests"], 309)
        self.assertNotIn("Authorization", page)
        self.assertNotIn("NVIDIA_API_KEY", page)
        for entry in manifest["screenshots"]:
            self.assertEqual(
                (dest / "assets" / entry["filename"]).read_bytes(),
                (self.root / media.BROWSER / entry["filename"]).read_bytes(),
            )

    def test_preexisting_output_is_preserved_and_not_overwritten(self):
        dest = self.root / media.OUTPUT
        dest.mkdir(parents=True)
        (dest / "user-note.txt").write_text("PRESERVE OWNER DATA", encoding="utf8")
        with self.assertRaisesRegex(media.MediaPackError, "ALREADY_EXISTS"):
            self.invoke()
        self.assertEqual(
            (dest / "user-note.txt").read_text("utf8"), "PRESERVE OWNER DATA"
        )

    def test_wrong_git_head_fails_closed_before_writing(self):
        self.receipt["source_git_head"] = "b" * 40
        self.write_inputs()
        with self.assertRaisesRegex(media.MediaPackError, "HEAD_MISMATCH"):
            self.invoke()
        self.assertFalse((self.root / media.OUTPUT).exists())

    def test_non_keyless_or_skipped_browser_fails_closed(self):
        for field, value in [
            ("clean_keyless_source_replay", False),
            ("ignored_env_file_present_before_tests", True),
            ("external_sponsor_requests_authorized", True),
        ]:
            with self.subTest(field=field):
                saved = self.receipt[field]
                self.receipt[field] = value
                self.write_inputs()
                with self.assertRaises(media.MediaPackError):
                    self.invoke()
                self.receipt[field] = saved
        self.receipt["steps"]["edge_e2e"]["status"] = "SKIPPED"
        self.write_inputs()
        with self.assertRaises(media.MediaPackError):
            self.invoke()
        self.assertFalse((self.root / media.OUTPUT).exists())

    def test_duplicate_or_missing_browser_images_are_refused(self):
        first = media.FILES[0][0]
        second = media.FILES[1][0]
        (self.root / media.BROWSER / second).write_bytes(
            (self.root / media.BROWSER / first).read_bytes()
        )
        with self.assertRaisesRegex(media.MediaPackError, "DUPLICATE"):
            self.invoke()
        (self.root / media.BROWSER / second).unlink()
        with self.assertRaisesRegex(media.MediaPackError, "MISSING"):
            self.invoke()

    def test_smoke_fixtures_and_sponsor_success_cannot_be_published(self):
        self.smoke["sample_only"] = False
        self.write_inputs()
        with self.assertRaisesRegex(media.MediaPackError, "EDGE_SMOKE"):
            self.invoke()
        self.smoke["sample_only"] = True
        self.receipt["nvidia_direct_sponsor_verified"] = True
        self.write_inputs()
        with self.assertRaisesRegex(media.MediaPackError, "SPONSOR"):
            self.invoke()


if __name__ == "__main__":
    unittest.main()
