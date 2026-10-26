"""Guarded loopback-only WHY route integration. Offline only."""
from __future__ import annotations

from contextlib import contextmanager
import json
import threading
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from evidencetrail.api import create_local_server
from evidencetrail.case_investigator import example_case


@contextmanager
def server(*, enable_local_nightshift=False):
    with create_local_server("127.0.0.1",0,
                             enable_local_nightshift=enable_local_nightshift) as s:
        thread=threading.Thread(target=s.serve_forever,daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{s.server_port}"
        finally:
            s.shutdown()
            thread.join(timeout=5)


def post(base,path,body):
    req=Request(base+path,data=json.dumps(body).encode(),
                headers={"Content-Type":"application/json"},method="POST")
    try:
        with urlopen(req,timeout=10) as f:
            return f.status,json.load(f)
    except HTTPError as ex:
        try:
            return ex.code,json.loads(ex.read())
        finally:
            ex.close()


class WhyLoopbackHttpTests(TestCase):
    def test_shared_ui_assets_are_fixed_local_routes(self):
        with server() as url:
            with urlopen(url+"/ui.css?view=local") as response:
                self.assertEqual(response.headers.get_content_type(), "text/css")
                self.assertIn(b"--font-body:",response.read())
            for path in ("/ui.css/../README.md", "/demo/ui.css"):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(url+path)
                self.assertEqual(caught.exception.code,404)
                caught.exception.close()

    def test_missing_shared_asset_has_a_recoverable_error(self):
        from pathlib import Path
        original=Path.read_bytes
        def read(path):
            if path.name=="ui.css":
                raise OSError("missing")
            return original(path)
        with patch.object(Path,"read_bytes",read), server() as url:
            with self.assertRaises(HTTPError) as caught:
                urlopen(url+"/ui.css")
            self.assertEqual(caught.exception.code,503)
            self.assertEqual(json.load(caught.exception),{"error":"ui_asset_unavailable"})
            caught.exception.close()

    def test_public_page_and_discovery_local_only(self):
        with server() as url:
            with urlopen(url+"/health") as response:
                health=json.load(response)
            self.assertEqual(health["source_counterfactual_post"],"/why-counterfactual")
            self.assertEqual(health["source_counterfactual_page"],"/why")
            self.assertTrue(health["sample_mode_only"])
            with urlopen(url+"/why") as response:
                html=response.read().decode()
                self.assertEqual(response.status,200)
                self.assertIn('id="removed"',html)
                self.assertIn('id="timeline"',html)
                self.assertIn("/why-counterfactual",html)
                self.assertIn('id="confirmLocalNightshift"',html)
                self.assertIn('id="askLocalNightshift"',html)
                self.assertIn("/case-local-nightshift",html)
                self.assertIn("localNightshiftEnabled",html)
                self.assertIn("textContent",html)
                self.assertIn("Deterministic summary:",html)
                self.assertIn("text-quality check",html)

    def test_chatgpt_tracking_query_must_not_break_readonly_why_page(self):
        # Shared links can append ?utm_source=chatgpt.com. Previously the
        # API treated that whole string as an unknown path and returned 404.
        with server() as url:
            for route in ("/why?utm_source=chatgpt.com",
                          "/why/?utm_source=chatgpt.com",
                          "/demo?utm_source=chatgpt.com",
                          "/health?utm_source=chatgpt.com"):
                with self.subTest(route=route):
                    with urlopen(url+route) as response:
                        self.assertEqual(response.status,200)
                        self.assertTrue(response.read())
            # POST must retain its strict exact endpoint. A link click may
            # display a page but must not mutate the inference request route.
            code,resp=post(url,"/why-counterfactual?utm_source=chatgpt.com",{
                "as_of_utc":"2024-10-07T11:00:00Z"
            })
            self.assertEqual(code,404)
            self.assertEqual(resp["error"],"not_found")

    def test_live_inference_and_zetaris_cannot_be_called_from_why(self):
        with patch("evidencetrail.api.why_offline_rows") as fixture:
            from run_zetaris_cross_issuer import import_rows
            fixture.side_effect=import_rows
            with patch("evidencetrail.zetaris_cross_issuer.query_sql_editor",
                       side_effect=AssertionError("Zetaris is forbidden")), patch(
                       "evidencetrail.adapters.nvidia_lightning.official_transport",
                       side_effect=AssertionError("NVIDIA is forbidden")):
                with server() as url:
                    code,out=post(url,"/why-counterfactual",{
                        "as_of_utc":"2024-10-07T11:00:00Z"
                    })
        self.assertEqual(code,200)
        self.assertEqual(out["selected_claims"]["NHC_WIND"]["value"],100)
        self.assertFalse(out["model_or_sponsor_called"])
        self.assertTrue(fixture.called)

    def test_local_nightshift_route_is_absent_from_default_offline_server(self):
        with patch("evidencetrail.api.propose_local_explanation",
                   side_effect=AssertionError("NO MODEL REQUEST")) as proposal:
            with server() as base:
                with urlopen(base+"/health") as response:
                    health=json.load(response)
                code,out=post(base,"/case-local-nightshift",{
                    "case":{"unknown":"never parsed on disabled route"},
                    "confirm_local_nightshift":True})
        self.assertTrue(health["sample_mode_only"])
        self.assertFalse(health["local_nightshift_enabled"])
        self.assertEqual(code,404)
        self.assertEqual(out["error"],"not_found")
        proposal.assert_not_called()

    def test_local_nightshift_requires_server_and_user_opt_in_and_keeps_verdict(self):
        fake={"status":"STRUCTURE_ACCEPTED_PROSE_UNVERIFIED","model_called":True,
              "request_attempted":True,"requested_mode":"meterless/local",
              "routed_model":"local-runtime/unit","route_identity_independently_verified":False,
              "proposal":{"claim_key":"STOCK","before_value":25,"after_value":12,
                          "source_ids":["STOCK-LEDGER","STOCK-OLD"],
                          "explanation":"Removing the current records exposes the older declaration.",
                          "explanation_semantics_independently_verified":False}}
        with patch("evidencetrail.api.propose_local_explanation",return_value=fake) as proposal:
            with server(enable_local_nightshift=True) as base:
                with urlopen(base+"/health") as response:
                    health=json.load(response)
                payload={"case":example_case("warehouse"),
                         "withdrawn_source_ids":["STOCK-CHECK","STOCK-LEDGER"]}
                refused,out=post(base,"/case-local-nightshift",payload)
                self.assertEqual(refused,400)
                self.assertEqual(out["error"],"invalid_request")
                proposal.assert_not_called()
                accepted,report=post(base,"/case-local-nightshift",{
                    **payload,"confirm_local_nightshift":True})
        self.assertFalse(health["sample_mode_only"])
        self.assertTrue(health["local_nightshift_enabled"])
        self.assertEqual(accepted,200)
        proposal.assert_called_once()
        self.assertEqual(report["kind"],"EVIDENCETRAIL_OPEN_CASE_INVESTIGATION_V1")
        self.assertEqual(report["why"]["selected_claims"]["STOCK"]["value"],25)
        self.assertEqual(report["experiment"]["selected_claims_after"]["STOCK"]["value"],12)
        self.assertEqual(report["nightshift_local_proposal"],fake)
        self.assertTrue(report["model_called"])
        self.assertTrue(report["model_or_sponsor_called"])
        self.assertTrue(report["execution_trace"][-1]["deterministic_verdict_unchanged"])

    def test_local_nightshift_rejects_provider_or_transport_overrides(self):
        with patch("evidencetrail.api.propose_local_explanation",
                   side_effect=AssertionError("NO MODEL REQUEST")) as proposal:
            with server(enable_local_nightshift=True) as base:
                code,out=post(base,"/case-local-nightshift",{
                    "case":example_case("warehouse"),"confirm_local_nightshift":True,
                    "provider":"cloud","url":"https://attacker.example"})
        self.assertEqual(code,400)
        self.assertEqual(out["error"],"invalid_request")
        proposal.assert_not_called()

    def test_pivotal_and_future_source_counterfactual_in_actual_http(self):
        with server() as url:
            code,out=post(url,"/why-counterfactual",{
                "as_of_utc":"2024-10-07T11:00:00Z"})
        self.assertEqual(code,200)
        pivot={x["removed_source_id"]:x for x in
               out["source_withdrawal_interventions"]}
        self.assertEqual(len(pivot),7)
        self.assertFalse(pivot["NHC-AL142024-PUBLIC-010"]["changed_claims"])
        fl=pivot["FL-EO-24-215"]["changed_claims"][0]
        self.assertEqual(fl["before"]["value"],51)
        self.assertEqual(fl["after"]["value"],35)

    def test_strict_policy_is_fail_closed(self):
        with server() as url:
            code,out=post(url,"/why-counterfactual",{
                "as_of_utc":"2024-10-07T11:00:00Z","strict":True})
        self.assertEqual(code,200)
        self.assertEqual(out["status"],"ABSTAIN_NO_ADMISSIBLE_CLAIMS")
        self.assertEqual(out["selected_claims"],{})
        self.assertEqual(out["clock_boundary_interventions"],[])

    def test_arbitrary_source_and_provider_injection_refused_before_data_load(self):
        invalid=[
            {"as_of_utc":"2024-10-07T11:00:00Z","sample_mode":False},
            {"as_of_utc":"2024-10-07T11:00:00Z","source_rows":[]},
            {"as_of_utc":"2024-10-07T11:00:00Z","nvidia":True},
            {"as_of_utc":"2024-10-07T11:00:00Z","strict":"false"},
            {"as_of_utc":"2024-10-07T11:00:00Z","strict":1},
            {"as_of_utc":"2099-01-01T00:00:00Z"},
            {"as_of_utc":"2024-10-07T11:00:01Z"},
            {"strict":False}
        ]
        with patch("evidencetrail.api.why_offline_rows",
                   side_effect=AssertionError("must block before source read")):
            with server() as url:
                for request in invalid:
                    with self.subTest(request=request):
                        code,res=post(url,"/why-counterfactual",request)
                        self.assertEqual(code,400)
                        self.assertEqual(res["error"],"invalid_request")

    def test_why_ui_does_not_consume_untrusted_model_prose(self):
        with server() as url:
            with urlopen(url+"/why") as response:
                html=response.read().decode()
        self.assertIn('node("div","effect"',html)
        self.assertNotIn("innerHTML=",html)
        self.assertIn("original 2024 first-publication",html.lower())


if __name__=="__main__":
    import unittest
    unittest.main()
