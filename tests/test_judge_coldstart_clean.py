"""Additional offline purity gates for judge replay receipt (no subprocess)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import run_judge_coldstart as cold


class CleanJudgeReplayGates(unittest.TestCase):
    def test_untracked_files_count_as_dirty_source(self):
        calls = []
        def fake(command, *, env, timeout):
            calls.append(command)
            if "rev-parse" in command:
                return 0, "a" * 40 + "\n"
            return 0, "?? injected_source.py\n"
        with patch.object(cold.shutil, "which", return_value="git"), patch.object(
            cold, "execute", side_effect=fake
        ):
            baseline = cold.git_baseline(cold.safe_environment({"PATH": "mock"}))
        self.assertFalse(baseline["tracked_clean_before_tests"])
        self.assertTrue(any("--untracked-files=all" in cmd for cmd in calls))

    def test_full_replay_never_certifies_independent_checkout_without_review(self):
        python = json.dumps({
            "test_status": "PASS", "test_total": 279,
            "failures": 0, "errors": 0, "sample_cases": 3,
        })
        chronology = json.dumps({
            "kind": "OFFLINE_ADVERSARIAL_CHRONOLOGY_BENCHMARK_V1",
            "pass": 20, "total": 20, "failed_cases": [],
        })
        for blocker in ("none", "ignored-env", "vendor"):
            with self.subTest(blocker=blocker), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                if blocker == "ignored-env":
                    (root / ".env.local").write_text("DUMMY_VALUE_ONLY\n", "utf8")
                if blocker == "vendor":
                    (root / "vendor" / "meterless").mkdir(parents=True)
                outputs = [
                    python, chronology, "\n".join(cold.EDGE_MARKERS),
                    "\n".join(cold.WHY_EDGE_MARKERS),
                ]
                with patch.object(cold, "ROOT", root), patch.object(
                    cold, "OUTPUT", root / "receipt.json"
                ), patch.object(cold, "git_baseline", return_value={
                    "head": "a" * 40, "tracked_clean_before_tests": True
                }), patch.object(
                    cold, "execute", side_effect=lambda cmd, **kw: (
                        0, outputs.pop(0)
                    )
                ):
                    exit_code = cold.main([])
                    receipt = json.loads((root / "receipt.json").read_text("utf8"))
                self.assertEqual(exit_code, 0)
                self.assertEqual(receipt["status"], "PASS")
                self.assertFalse(receipt["independent_clean_checkout_proven"])
                self.assertEqual(
                    receipt["clean_keyless_source_replay"], blocker == "none"
                )
                self.assertEqual(
                    receipt["ignored_env_file_present_before_tests"],
                    blocker == "ignored-env"
                )
                self.assertEqual(
                    receipt["meterless_vendor_present_before_tests"],
                    blocker == "vendor"
                )


if __name__ == "__main__":
    unittest.main()
