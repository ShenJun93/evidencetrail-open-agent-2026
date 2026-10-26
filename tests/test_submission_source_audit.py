"""Offline no-key tests for publish-preflight selection and scan boundaries."""
from __future__ import annotations
import unittest

from run_submission_source_audit import classify, select_files


class ReleaseAuditTests(unittest.TestCase):
    def test_export_keeps_study_runtime_template_but_excludes_participant_data(self):
        required = ["studies/analyst_participant.html", "studies/README.md",
                    "studies/run_offline_browser_smoke.py",
                    "studies/verify_participant_browser.mjs",
                    "register_zetaris_milton_filestore.py",
                    "PRIZE_AUDIT_2026-10-24.md", "SUBMISSION_PACKET.md",
                    "DESIGN.md", "UX-CONTRACT.md", "premium-ui.json",
                    "submission/description.txt", "submission/PUBLIC_README.md",
                    "submission/CLAIM_LEDGER.md", "submission/DEMO_SCRIPT.md",
                    "submission/video-scenes.json"]
        selected = select_files(required + [
            "studies/responses/private.json", "studies/private-registry/session.json",
            "studies/participants/slot-0.html", "submission/private-roster.json",
            "submission/raw-runtime-receipt.json", "submission/artifacts/private.mp4"])
        self.assertEqual(selected, sorted(required))

    def test_select_source_and_run_scripts_without_internal_notes(self):
        selected = select_files([
            "README.md", "evidencetrail/agents/collector.py",
            "demo/index.html", "samples/inputs/example.json",
            "tests/test_release.py", "run_judge_coldstart.py",
            "notes/99_internal_draft.md", "acceptance/logs/private.json",
            "local-operator-notes.md",
        ])
        self.assertEqual(selected, sorted([
            "README.md", "evidencetrail/agents/collector.py",
            "demo/index.html", "samples/inputs/example.json",
            "tests/test_release.py", "run_judge_coldstart.py",
        ]))

    def test_refuses_committed_private_env(self):
        for name in (".env", ".env.local", "evidencetrail/.env",
                     "vendor/meterless/lib.py", "hmem_data/state.json"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    select_files([name])

    def test_refuses_path_traversal_and_windows_style(self):
        for name in ("../settings.env", "/etc/passwd", "evidencetrail/../a.py",
                     "evidencetrail\\api.py"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    select_files([name])

    def test_catches_production_looking_tokens_without_logging_values(self):
        cases = [
            b"token=gh" + b"p_" + b"A"*32,
            b"token=github_" + b"pat_" + b"B"*46,
            b"token=sk-" + b"proj-" + b"C"*40,
            b"token=nv" + b"api-" + b"D"*30,
            b"-----BEGIN " + b"OPENSSH PRIVATE KEY-----",
        ]
        for case in cases:
            found, warnings = classify(case, "README.md")
            self.assertTrue(found)
            self.assertEqual(warnings, [])
            self.assertFalse(any(case.decode(errors="replace") in item for item in found))

    def test_normal_placeholders_do_not_count_as_secrets(self):
        source = (b"METERLESS_RUNTIME_TOKEN=your-nightshift-runtime-token"
                  b"\nMETERLESS_MODEL=meterless/auto")
        self.assertEqual(classify(source, ".env.example"), ([], []))

    def test_local_machine_path_is_review_warning(self):
        fixture_path = b"Source E:\\Projects" + b"\\Fixture"
        found, warn = classify(fixture_path, "README.md")
        self.assertFalse(found)
        self.assertEqual(warn, ["LOCAL_PROJECT_PATH"])


if __name__ == "__main__":
    unittest.main()
