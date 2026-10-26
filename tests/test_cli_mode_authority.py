"""CLI authorization gates: input JSON must never promote SAMPLE_MODE to LIVE."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from evidencetrail.cli import main


class CliModeAuthorityTests(unittest.TestCase):
    def _run_fixture(self, additional: list[str]):
        source = json.loads(Path("samples/inputs/yagi_1630_lucyen.json").read_text(encoding="utf-8"))
        # Deliberately untrusted input asserts it wants real sponsor traffic.
        source["sample_mode"] = False
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "input.json"
            inp.write_text(json.dumps(source), encoding="utf-8")
            out = io.StringIO()
            with patch("evidencetrail.cli.EvidenceTrailPipeline") as pipeline, redirect_stdout(out):
                pipeline.return_value.run.return_value.to_dict.return_value = {
                    "sample_mode": not ("--live" in additional), "verdict": "INSUFFICIENT_EVIDENCE"
                }
                if "--live" in additional:
                    with patch("evidencetrail.cli._load_env_file") as loader:
                        code = main(["run", "--input", str(inp), "--out", td] + additional)
                        self.assertEqual(loader.call_count, 2)
                else:
                    with patch("evidencetrail.cli._load_env_file",
                               side_effect=AssertionError("sample must not read secrets")):
                        code = main(["run", "--input", str(inp), "--out", td] + additional)
                self.assertEqual(code, 0)
                expected_sample = "--live" not in additional
                self.assertIs(pipeline.call_args.kwargs["sample_mode"], expected_sample)
                self.assertIs(pipeline.return_value.run.call_args.args[0].sample_mode, expected_sample)
            return json.loads(out.getvalue())

    def test_sample_flag_overrides_input_trying_to_force_live(self):
        self.assertIs(self._run_fixture(["--sample-mode"])["sample_mode"], True)

    def test_default_is_sample_even_if_input_requests_live(self):
        self.assertIs(self._run_fixture([])["sample_mode"], True)

    def test_explicit_live_is_the_only_remote_authorization(self):
        self.assertIs(self._run_fixture(["--live"])["sample_mode"], False)

    def test_serve_never_loads_secrets(self):
        with patch("evidencetrail.cli._load_env_file",
                   side_effect=AssertionError("serve must not read secrets")):
            with patch("evidencetrail.api.serve") as server:
                self.assertEqual(main(["serve", "--port", "8077"]), 0)
                server.assert_called_once_with("127.0.0.1", 8077)

    def test_serve_nightshift_is_an_explicit_opt_in(self):
        with patch("evidencetrail.api.serve") as server:
            self.assertEqual(main(["serve", "--port", "8077", "--enable-local-nightshift"]), 0)
            server.assert_called_once_with("127.0.0.1", 8077, enable_local_nightshift=True)

    def test_sample_and_live_flags_mutually_exclusive(self):
        with redirect_stdout(io.StringIO()), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as exc:
                main(["run", "--input", "not_used.json", "--sample-mode", "--live"])
        self.assertEqual(exc.exception.code, 2)
