"""Isolated Milton Zetaris registration is opt-in and never mutates Yagi."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import register_zetaris_milton_filestore as reg


class IsolatedRegistrationGuardTests(unittest.TestCase):
    def test_only_three_allowlisted_create_statements(self):
        self.assertEqual(len(reg.SQL), 3)
        self.assertTrue(reg.SQL[0].startswith(
            "CREATE LIGHTNING DATABASE EVIDENCETRAIL_MILTON"))
        for query in reg.SQL[1:]:
            self.assertTrue(query.startswith("CREATE LIGHTNING FILESTORE TABLE "))
            self.assertIn("FROM EVIDENCETRAIL_MILTON FORMAT CSV OPTIONS",query)
            self.assertIn("/home/zetaris/customer-data/shared/evidencetrail-milton-2024/",query)
        for query in reg.SQL:
            self.assertNotIn("EVIDENCETRAIL_YAGI",query)
            self.assertNotIn("DROP ",query.upper())
            self.assertNotIn("TRUNCATE ",query.upper())
            self.assertNotIn("ALTER ",query.upper())

    def test_dry_run_does_not_open_network_or_load_env(self):
        with tempfile.TemporaryDirectory() as td, patch.object(
            reg,"REPORT",Path(td)/"receipt.json"
        ), patch("sys.argv",["register_zetaris_milton_filestore.py"]), patch.object(
            reg,"read_local_env",side_effect=AssertionError("no secrets")
        ), patch.object(reg,"send_sql",side_effect=AssertionError("no network")):
            self.assertEqual(reg.main(),0)
            receipt=json.loads((Path(td)/"receipt.json").read_text())
            self.assertEqual(receipt["status"],"DRY_RUN_NO_NETWORK")
            self.assertFalse(receipt["yagi_modified"])

    def test_no_database_write_without_approved_opt_in(self):
        with tempfile.TemporaryDirectory() as td, patch.object(
            reg,"REPORT",Path(td)/"receipt.json"
        ), patch("sys.argv",[
            "register_zetaris_milton_filestore.py","--execute"
        ]),patch.object(reg,"read_local_env",side_effect=AssertionError("no secret read")
        ),patch.object(reg,"send_sql",side_effect=AssertionError("no query")):
            self.assertEqual(reg.main(),2)
            data=json.loads((Path(td)/"receipt.json").read_text())
            self.assertEqual(data["status"],"REFUSED_APPROVAL_OR_EXPLICIT_CONFIG_MISSING")

    def test_preexisting_milton_namespace_must_not_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td, patch.object(
            reg,"REPORT",Path(td)/"receipt.json"
        ),patch("sys.argv",[
            "register_zetaris_milton_filestore.py","--execute",
            "--approve-isolated-new-tables","--env-file",".env.local"
        ]),patch.object(reg,"read_local_env",return_value={"ZETARIS_API_KEY":"mock-key"}
        ),patch.object(reg,"exists",return_value=True),patch.object(
            reg,"send_sql",side_effect=AssertionError("no DDL allowed")):
            self.assertEqual(reg.main(),2)
            data=json.loads((Path(td)/"receipt.json").read_text())
            self.assertEqual(data["status"],"REFUSED_TARGET_DATABASE_ALREADY_EXISTS")
            self.assertFalse(data["yagi_modified"])

    def test_query_allowlist_rejects_arbitrary_sql_before_any_url_open(self):
        with patch.object(reg,"validate_config",side_effect=AssertionError("called")):
            with self.assertRaisesRegex(ValueError,"UNAPPROVED_SQL_STATEMENT"):
                reg.send_sql("DROP DATABASE EVIDENCETRAIL_YAGI",{})


if __name__=="__main__":
    unittest.main()
