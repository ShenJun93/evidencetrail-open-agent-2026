from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from evidencetrail.cli import main
from evidencetrail.models import RunRequest
from evidencetrail.pipeline import EvidenceTrailPipeline


class CliSampleTests(unittest.TestCase):
    def test_cli_run_sample_input(self):
        with tempfile.TemporaryDirectory() as td:
            code = main(["run", "--input", "samples/inputs/yagi_1630_lucyen.json", "--out", td, "--sample-mode"])
        self.assertEqual(code, 0)


class ApiTests(unittest.TestCase):
    def test_post_run(self):
        pipeline = EvidenceTrailPipeline(
            sample_mode=True, persist_dir=tempfile.mkdtemp(), log_dir=tempfile.mkdtemp()
        )
        raw = json.loads(Path("samples/inputs/yagi_1500_lucyen.json").read_text(encoding="utf-8"))

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or "0")
                data = json.loads(self.rfile.read(n).decode())
                result = pipeline.run(RunRequest.from_dict(data))
                body = json.dumps(result.to_dict()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        try:
            req = Request(
                f"http://127.0.0.1:{port}/run",
                data=json.dumps(raw).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode())
            self.assertEqual(body["verdict"], "INSUFFICIENT_EVIDENCE")
            self.assertNotIn("GOV-2024-09-08-1637", body["eligible_source_ids"])
        finally:
            httpd.shutdown()
