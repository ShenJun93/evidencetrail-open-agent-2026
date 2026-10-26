"""Local judge dossier contract: no browser-triggered live sponsor calls."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from evidencetrail.api import DEMO_HTML, MAX_REQUEST_BYTES


class JudgeDemoStaticContractTests(unittest.TestCase):
    def test_bundled_html_exists_with_no_remote_assets(self):
        raw = DEMO_HTML.read_text(encoding="utf-8")
        self.assertIn('fetch("/run"', raw)
        self.assertIn("sample_mode:true", raw)
        self.assertIn("16:37 source:", raw)
        self.assertIn("a 16:37 article", raw)
        self.assertNotIn("does not exist yet", raw)
        self.assertIn("REPORTED_DATELINE_REPLAY", raw)
        self.assertIn("STRICT_AS_OF_2024", raw)
        self.assertNotIn('src="https://', raw)
        self.assertNotIn('href="https://fonts', raw)

    def test_renderer_uses_text_content_not_source_html(self):
        raw = DEMO_HTML.read_text(encoding="utf-8")
        self.assertIn("textContent", raw)
        self.assertNotIn("innerHTML", raw)

    def test_separate_proof_labels_are_not_live_browser_claims(self):
        from evidencetrail.api import PROOF_HTML
        raw = PROOF_HTML.read_text(encoding="utf-8")
        self.assertIn("3 curated government", raw)
        self.assertIn("1 synthetic", raw)
        self.assertIn("NOT VERIFIED", raw)
        self.assertIn("Nightshift", raw)
        self.assertIn("OFFLINE SAMPLE", raw)
        self.assertNotIn('src="https://', raw)

    def test_demo_links_to_separate_local_proof(self):
        self.assertIn('href="/proof"', DEMO_HTML.read_text(encoding="utf-8"))

    def test_request_bound_is_explicit(self):
        self.assertLessEqual(MAX_REQUEST_BYTES, 65536)
