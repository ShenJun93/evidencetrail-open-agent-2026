"""Offline privacy and spoofing tests for Cursor local authoring metadata.

Fixtures are synthetic SQLite composer headers; only owner-machine CLI
execution is real evidence of Cursor's local application session.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from run_cursor_provenance_audit import (
    BUILD_START_MS, audit_cursor, matched_workspace_ids, summarize_header,
)


class CursorMetadataEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "BH-0028-openagent-evidencetrail"
        self.repo.mkdir()
        self.state = self.base / "Cursor" / "User"
        self.workspace = self.state / "workspaceStorage" / "fixture-workspace-hash"
        self.workspace.mkdir(parents=True)
        (self.workspace / "workspace.json").write_text(
            json.dumps({
                "folder": "file:///E:/Projects/BH-0028-openagent-evidencetrail"
            }), encoding="utf-8"
        )
        self.global_state = self.state / "globalStorage"
        self.global_state.mkdir()
        self.db = self.global_state / "state.vscdb"
        connection = sqlite3.connect(self.db)
        connection.execute(
            "CREATE TABLE composerHeaders("
            "workspaceId TEXT,createdAt INTEGER,lastUpdatedAt INTEGER,value TEXT)"
        )
        connection.commit()
        connection.close()

    def insert(
        self, *, workspace="fixture-workspace-hash",
        created=BUILD_START_MS + 195_000, mode="agent", forced="edit",
        files=31, added=2557, removed=0, secret="confidential-not-exportable",
    ):
        conn = sqlite3.connect(self.db)
        data = {
            "unifiedMode": mode, "forceMode": forced,
            "filesChangedCount": files, "totalLinesAdded": added,
            "totalLinesRemoved": removed,
            "name": secret,
            "subtitle": "Hidden chat title unrelated to evidence",
            "prompt": "This should never reach the output",
            "composerId": "personal-session-id-123",
        }
        conn.execute(
            "INSERT INTO composerHeaders VALUES(?,?,?,?)",
            (workspace, created, created + 600_000, json.dumps(data))
        )
        conn.commit()
        conn.close()

    def test_reproducible_2026_edit_session_detected_without_private_fields(self):
        self.insert()
        result = audit_cursor(self.repo, self.state)
        self.assertEqual(result["status"],
                         "CURSOR_AGENT_EDIT_SESSION_LOCAL_METADATA_CONFIRMED")
        self.assertEqual(result["local_agent_edit_session_count"], 1)
        session = result["sessions"][0]
        self.assertEqual(session["self_reported_files_changed"], 31)
        self.assertEqual(session["self_reported_lines_added"], 2557)
        self.assertTrue(session["inside_official_build_window"])
        self.assertFalse(session["independent_diff_authentication"])
        serialized = json.dumps(result)
        for forbidden in ("confidential-not-exportable",
                          "personal-session-id-123", "Hidden chat title",
                          "This should never reach"):
            self.assertNotIn(forbidden, serialized)

    def test_unrelated_workspace_does_not_prove_project_authorship(self):
        self.insert(workspace="some-other-workspace")
        result = audit_cursor(self.repo, self.state)
        self.assertEqual(result["local_agent_edit_session_count"], 0)

    def test_pre_window_cursor_session_not_eligible(self):
        self.insert(created=BUILD_START_MS - 60_000)
        result = audit_cursor(self.repo, self.state)
        self.assertEqual(result["local_agent_edit_session_count"], 0)

    def test_ask_plan_and_zero_file_modes_not_counted_as_code_edit(self):
        for mode, forced, files, added in (
            ("agent", "plan", 10, 20),
            ("ask", "edit", 10, 20),
            ("agent", "edit", 0, 100),
            ("agent", "edit", 2, 0),
        ):
            with self.subTest(mode=mode, forced=forced, files=files):
                data = {"unifiedMode": mode, "forceMode": forced,
                        "filesChangedCount": files, "totalLinesAdded": added,
                        "totalLinesRemoved": 0}
                row = summarize_header(
                    workspace_id="fixture-workspace-hash",
                    created_at=BUILD_START_MS + 100_000,
                    last_updated_at=None, value=json.dumps(data),
                    allowed_ids={"fixture-workspace-hash"},
                )
                self.assertIsNone(row)

    def test_false_filename_prefix_does_not_match_workspace(self):
        path = self.workspace / "workspace.json"
        path.write_text(json.dumps({
            "folder": "file:///E:/Projects/BH-0028-openagent-evidencetrail-fake"
        }), encoding="utf8")
        self.assertEqual(matched_workspace_ids(self.state, self.repo.name), set())

    def test_invalid_numeric_or_bogus_json_fail_closed(self):
        for payload in (
            "not json",
            json.dumps({"unifiedMode": "agent",
                        "forceMode": "edit",
                        "filesChangedCount": True,
                        "totalLinesAdded": 100, "totalLinesRemoved": 0}),
            json.dumps({"unifiedMode": "agent",
                        "forceMode": "edit",
                        "filesChangedCount": 31,
                        "totalLinesAdded": -5, "totalLinesRemoved": 0}),
        ):
            self.assertIsNone(summarize_header(
                workspace_id="fixture-workspace-hash",
                created_at=BUILD_START_MS + 500,
                last_updated_at=None,
                value=payload, allowed_ids={"fixture-workspace-hash"},
            ))

    def test_missing_database_reports_not_found_instead_of_success(self):
        self.db.unlink()
        result = audit_cursor(self.repo, self.state)
        self.assertEqual(result["status"], "GLOBAL_STORAGE_NOT_FOUND")
        self.assertEqual(result["local_agent_edit_session_count"], 0)


if __name__ == "__main__":
    unittest.main()
