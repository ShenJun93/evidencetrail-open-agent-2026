"""Judge-facing proof claims must match verified engineering receipts.

These are STATIC content-regression tests + actual loopback HTTP reads.
Passing them does not independently authenticate a provider/sponsor/human.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
from unittest import TestCase
from urllib.request import urlopen

from tests.test_why_local_api import server

ROOT=Path(__file__).resolve().parent.parent


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self.labels=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            href=dict(attrs).get("href")
            self.links.append(href)
    def handle_data(self,data):
        if data.strip():
            self.labels.append(data.strip())


class ProofRegisterTransparencyTests(TestCase):
    def test_proof_identifies_one_real_model_response_with_exact_identity(self):
        raw=(ROOT/"demo"/"proof.html").read_text(encoding="utf-8")
        self.assertIn("One actual accepted HTTPS chat completion",raw)
        self.assertIn("nvidia/nemotron-3.5-lightning-30b-a3b",raw)
        self.assertIn("637 prompt + 159 completion = 796 tokens",raw)
        self.assertIn("77a261bfcf1a",raw)
        self.assertIn("100 mph",raw)
        self.assertIn("51 Florida counties",raw)
        self.assertIn("one dated local receipt",raw)
        self.assertIn("nvidia-lightning-zetaris-one-shot-20261024.json",raw)

    def test_rejects_historical_stale_denial_and_overclaims(self):
        raw=(ROOT/"demo"/"proof.html").read_text(encoding="utf-8")
        for outdated in (
            "0/4 Nemotron 3.5 proposals were accepted",
            "No accepted NVIDIA/Nebius model decision",
            "315/315 Python PASS",
            "No NVIDIA/Nebius hosted model inference accepted",
        ):
            with self.subTest(outdated=outdated):
                self.assertNotIn(outdated,raw)
        self.assertIn("One accepted cloud-model response",raw)
        self.assertIn("predates",raw)
        self.assertIn("not</em> every phrase",raw)
        self.assertIn("One local Nightshift adapter completion",raw)
        self.assertIn("rcpt_req_io484m5c",raw)
        self.assertIn("not a full browser case verdict",raw)
        self.assertIn("Independent analyst n = 0",raw)
        self.assertIn("580 Python tests",raw)
        self.assertIn("20/20 internal chronology",raw)
        self.assertIn("6 isolated Edge scenarios",raw)
        self.assertIn("dirty working tree",raw)
        self.assertIn("Evidence Map",raw)
        self.assertIn("656088d0ee063dfec00eb49dbc72886927c11688",raw)
        self.assertIn("not by an external evaluator",raw)
        self.assertIn("524 Python tests",raw)
        self.assertIn("No sponsor prize eligibility has been certified",raw)

    def test_proof_honors_separate_issuer_provenance_and_source_limits(self):
        raw=(ROOT/"demo"/"proof.html").read_text(encoding="utf-8")
        self.assertIn("four NOAA/NHC advisories",raw)
        self.assertIn("three Florida Governor records",raw)
        self.assertIn("authenticated original 2024",raw)
        self.assertIn("Simulated deletion",raw)
        self.assertIn("not a real publisher retraction",raw)
        self.assertIn("strict",raw.lower())
        self.assertIn("Strict original-publication policy",raw)

    def test_crosslink_judge_journey_and_no_remote_scripts(self):
        main=(ROOT/"demo"/"index.html").read_text(encoding="utf-8")
        proof=(ROOT/"demo"/"proof.html").read_text(encoding="utf-8")
        why=(ROOT/"demo"/"why.html").read_text(encoding="utf-8")
        for label,html in (("demo",main),("proof",proof),("why",why)):
            with self.subTest(label=label):
                self.assertIn('href="/proof"' if label=="demo" else "EvidenceTrail",html)
        self.assertIn('href="/why"',main)
        self.assertIn('href="/proof"',main)
        self.assertIn('href="/demo"',proof)
        self.assertIn('href="/why"',proof)
        self.assertIn('href="/demo"',why)
        self.assertIn("script-src 'none'",proof)
        self.assertNotIn("<script",proof.lower())

    def test_server_serves_updated_proof_and_normalized_readonly_links(self):
        with server() as base:
            for route,expected in [
                ("/proof","One actual accepted HTTPS chat completion"),
                ("/proof?utm_source=chatgpt.com","796 tokens"),
                ("/demo?utm_source=chatgpt.com",'aria-label="EvidenceTrail views"'),
                ("/why?utm_source=chatgpt.com",'id="conclusion"'),
            ]:
                with self.subTest(route=route):
                    with urlopen(base+route,timeout=10) as res:
                        self.assertEqual(res.status,200)
                        self.assertIn(expected,res.read().decode("utf-8"))
            with urlopen(base+"/health",timeout=10) as res:
                api=json.load(res)
            self.assertTrue(api["sample_mode_only"])
            self.assertEqual(api["source_counterfactual_post"],"/why-counterfactual")


if __name__=="__main__":
    import unittest
    unittest.main()
