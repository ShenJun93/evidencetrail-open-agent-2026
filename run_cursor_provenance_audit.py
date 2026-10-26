"""Privacy-preserving local Cursor Agent authoring metadata audit.

Read ONLY local Cursor's workspace.json and global SQLite composer *headers*.
Do not export composer IDs, session titles, prompts, file contents, account
names, local user paths, chat messages, authentication or hidden settings.

Cursor's own filesChangedCount/linesAdded are NOT independently measured Git
diffs. Report them as local self-reported workspace session metadata only.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RECEIPT = Path("acceptance/logs/cursor-agent-edit-evidence-20261023.json")
BUILD_START_MS = int(datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp() * 1000)
BUILD_END_MS = int(datetime(2026, 10, 27, 23, 45, tzinfo=timezone.utc).timestamp() * 1000)
MAX_WORKSPACES = 150
MAX_HEADER_ROWS = 1000
MAX_VALUE_BYTES = 32_768


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _utc(when_ms: int) -> str:
    return datetime.fromtimestamp(when_ms / 1000, timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def matched_workspace_ids(state_root: Path, project_name: str) -> set[str]:
    ids: set[str] = set()
    folder = state_root / "workspaceStorage"
    if not folder.is_dir():
        return ids
    try:
        candidates = list(folder.glob("*/workspace.json"))[:MAX_WORKSPACES]
    except OSError:
        return ids
    for path in candidates:
        try:
            if path.stat().st_size > 16_384:
                continue
            obj = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                continue
            # Compare the basename as an exact path component; simply finding
            # the term inside a session title would be insufficient.
            joined = str(obj.get("folder", obj.get("workspace", "")))
            canonical = joined.replace("\\", "/").rstrip("/").casefold()
            if canonical.split("/")[-1] == project_name.casefold():
                ids.add(path.parent.name)
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
    return ids


def summarize_header(
    *,
    workspace_id: object,
    created_at: object,
    last_updated_at: object,
    value: object,
    allowed_ids: set[str],
) -> dict | None:
    if not isinstance(workspace_id, str) or workspace_id not in allowed_ids:
        return None
    created = _positive_int(created_at)
    updated = _positive_int(last_updated_at)
    if created is None or not (BUILD_START_MS <= created <= BUILD_END_MS):
        return None
    if isinstance(value, bytes):
        if len(value) > MAX_VALUE_BYTES:
            return None
        try:
            value = value.decode("utf-8")
        except UnicodeError:
            return None
    if not isinstance(value, str) or len(value) > MAX_VALUE_BYTES:
        return None
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("unifiedMode") != "agent":
        return None
    if data.get("forceMode") != "edit":
        return None
    added = _positive_int(data.get("totalLinesAdded"))
    removed = _positive_int(data.get("totalLinesRemoved"))
    changed = _positive_int(data.get("filesChangedCount"))
    if added is None or removed is None or changed is None:
        return None
    if changed <= 0 or added + removed <= 0:
        return None
    return {
        "cursor_agent_mode": "agent",
        "cursor_force_mode": "edit",
        "started_at_utc": _utc(created),
        "last_updated_at_utc": _utc(updated) if updated is not None else None,
        "self_reported_files_changed": changed,
        "self_reported_lines_added": added,
        "self_reported_lines_removed": removed,
        "inside_official_build_window": True,
        "project_workspace_id_matched": True,
        "independent_diff_authentication": False,
        "source_kind": "CURSOR_LOCAL_GLOBALSTORAGE_COMPOSER_HEADER",
    }


def audit_cursor(repo_root: Path, state_root: Path) -> dict:
    slug = repo_root.resolve().name
    ids = matched_workspace_ids(state_root, slug)
    base = {
        "project_slug": slug,
        "kind": "CURSOR_AGENT_EDIT_SESSION_METADATA_NOT_FULL_DIFF_PROOF",
        "local_cursor_workspace_found": bool(ids),
        "local_agent_edit_session_count": 0,
        "sessions": [],
        "raw_chat_messages_exported": False,
        "session_titles_exported": False,
        "session_ids_exported": False,
        "secrets_exported": False,
        "all_repo_commits_authored_by_cursor": False,
        "proof_limitation": (
            "Local Cursor-owned SQLite metadata, not an independently "
            "verified per-file source diff or full authoring transcript."
        ),
    }
    if not ids:
        base["status"] = "NO_MATCHING_CURSOR_WORKSPACE"
        return base
    db = state_root / "globalStorage" / "state.vscdb"
    if not db.exists():
        base["status"] = "GLOBAL_STORAGE_NOT_FOUND"
        return base
    try:
        con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=3)
        try:
            cursor = con.execute(
                "SELECT workspaceId,createdAt,lastUpdatedAt,value "
                "FROM composerHeaders ORDER BY createdAt DESC LIMIT ?",
                (MAX_HEADER_ROWS,),
            )
            sessions = []
            for workspace, created, updated, value in cursor:
                info = summarize_header(
                    workspace_id=workspace,
                    created_at=created,
                    last_updated_at=updated,
                    value=value,
                    allowed_ids=ids,
                )
                if info:
                    sessions.append(info)
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        base["status"] = "CURSOR_SQLITE_READ_FAILED_CLOSED"
        return base
    base["sessions"] = sessions
    base["local_agent_edit_session_count"] = len(sessions)
    base["status"] = (
        "CURSOR_AGENT_EDIT_SESSION_LOCAL_METADATA_CONFIRMED"
        if sessions else "NO_ELIGIBLE_CURSOR_EDIT_SESSION_IN_LOCAL_HEADERS"
    )
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent)
    default_state = Path(os.environ.get("APPDATA", "__APPDATA_NOT_FOUND__")) / "Cursor" / "User"
    parser.add_argument("--state-root", type=Path, default=default_state)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    result = audit_cursor(args.repo_root, args.state_root)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "sessions": result["local_agent_edit_session_count"],
        "session_metadata": result["sessions"],
        "receipt": str(args.receipt),
        "disclosure": result["proof_limitation"],
    }, ensure_ascii=False))
    return 0 if result["local_agent_edit_session_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
