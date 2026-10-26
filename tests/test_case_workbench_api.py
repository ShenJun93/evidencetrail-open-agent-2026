"""Real local HTTP, no vendor calls or participant claims."""
import unittest
from tests.test_case_workbench import draft, source
from tests.test_why_local_api import post, server


class CaseWorkbenchApiTests(unittest.TestCase):
    def test_prepare_and_add_evidence_over_real_http(self):
        with server() as base:
            code, preview = post(base, "/case-draft", {"draft": draft()})
            self.assertEqual(code, 200)
            code, update = post(base, "/case-evidence", {
                "case": preview["case_pack"], "sources": [source("NEW", "29", "2025-02-04T08:30:00Z")]})
            self.assertEqual(code, 200)
            self.assertTrue(update["comparison"]["value_or_availability_changed"])
            self.assertFalse(update["model_or_sponsor_called"])

    def test_invalid_preview_has_actionable_safe_row_error(self):
        raw = draft(); raw["sources"][0]["issued_at"] = "no-zone-secret"
        with server() as base:
            code, result = post(base, "/case-draft", {"draft": raw})
        self.assertEqual(code, 422)
        self.assertEqual(result["issues"][0]["field"], "issued_at")
        self.assertEqual(result["issues"][0]["row"], 1)
        self.assertNotIn("no-zone-secret", str(result))

    def test_authoring_does_not_grant_provider_or_live_options(self):
        with server() as base:
            for route, payload in (("/case-draft", {"draft": draft(), "provider": "nvidia"}),
                                   ("/case-evidence", {"case": {}, "sources": [], "live": True})):
                code, _ = post(base, route, payload)
                self.assertEqual(code, 400)


if __name__ == "__main__": unittest.main()
