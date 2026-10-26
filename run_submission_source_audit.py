"""Build a private judge-source candidate from an immutable Git commit.

No network, credential read, ignored-file read, push, or submission. The JSON
receipt contains rule IDs/counts only and never captured secret substrings.
A PASS here does not independently certify safe publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

PATTERNS = {
    "PRIVATE_KEY_MATERIAL": re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "GITHUB_CREDENTIAL": re.compile(rb"(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{45,})"),
    "OPENAI_CREDENTIAL": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "NVIDIA_CREDENTIAL": re.compile(rb"nvapi-[A-Za-z0-9_-]{24,}"),
    "AWS_ACCESS_KEY": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "GOOGLE_API_KEY": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "SLACK_CREDENTIAL": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{30,}"),
}
PRIVACY_WARNINGS = {
    "WINDOWS_HOME_PATH": re.compile(rb"(?i)C:\\\\Users\\\\[^\\\\\s\"']+"),
    "LOCAL_PROJECT_PATH": re.compile(rb"(?i)[A-Z]:\\+Projects\\+"),
    "LOCAL_ACCOUNT_EMAIL": re.compile(
        rb"(?i)\b(?:owner|personal|account)[ _-]?(?:email|address)\s*[:=]\s*[^\s@]+@[^\s@]+"
    ),
}
TEXT_SUFFIXES = frozenset({
    ".py", ".js", ".mjs", ".mts", ".ts", ".html", ".css", ".md", ".json",
    ".txt", ".toml", ".yml", ".yaml", ".csv", ".ps1", ".sh", ".template",
    ".example", ".gitignore",
})
ROOT_FILES = frozenset({
    "README.md", "JUDGE_START_HERE.md", "SUBMISSION_READY_START_HERE.md",
    "PRIZE_AUDIT_2026-10-24.md",
    "SUBMISSION_DRAFT_TRACK02_EVIDENCETRAIL_2026-10-24.md",
    "SUBMISSION_PACKET.md", "DESIGN.md", "UX-CONTRACT.md", "premium-ui.json",
    "LICENSE", ".gitignore", ".env.example", "pyproject.toml",
    "nebius-token-factory.env.template", "nvidia-nim.env.template",
    "nvidia-nim-35.env.template",
})
ROOT_SCRIPT_PREFIXES = ("run_", "make_", "mix_", "record_", "verify_")
ROOT_SCRIPT_EXACT = frozenset({
    "inspect_local_zetaris.py", "restore_local_zetaris.py",
    "diagnose_zetaris_recovery.py", "build_judge_media_pack.py",
    "register_zetaris_milton_filestore.py",
})
DIRS = ("evidencetrail/", "demo/", "samples/", "tests/")
# The study engine reads this HTML at runtime. Export its source/protocol,
# never a whole studies tree that might later contain volunteer responses.
STUDY_FILES = frozenset({
    "studies/analyst_participant.html", "studies/README.md",
    "studies/run_offline_browser_smoke.py", "studies/verify_participant_browser.mjs",
})
SUBMISSION_FILES = frozenset({
    "submission/description.txt", "submission/PUBLIC_README.md",
    "submission/CLAIM_LEDGER.md", "submission/DEMO_SCRIPT.md",
    "submission/video-scenes.json",
})
MAX_BLOB = 2_000_000


def select_files(tracked: list[str]) -> list[str]:
    """Fail closed on unsafe Git paths; export only reproducible source/docs."""
    result = []
    for raw in tracked:
        if not raw or "\\" in raw:
            raise ValueError("UNSAFE_TRACKED_PATH")
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("UNSAFE_TRACKED_PATH")
        if path.name in {".env", ".env.local"} or any(
            part in {"hmem_data", "node_modules", ".git", "vendor"} for part in path.parts
        ):
            raise ValueError("UNEXPECTED_PRIVATE_TRACKED_PATH")
        allowed = (
            raw in ROOT_FILES or raw in STUDY_FILES or raw in SUBMISSION_FILES
            or raw.startswith(DIRS)
            or (len(path.parts) == 1 and raw.endswith((".py", ".ps1", ".mjs"))
                and (raw.startswith(ROOT_SCRIPT_PREFIXES) or raw in ROOT_SCRIPT_EXACT))
        )
        if allowed:
            result.append(raw)
    return sorted(result)


def classify(blob: bytes, path: str) -> tuple[list[str], list[str]]:
    if len(blob) > MAX_BLOB:
        return ["OVERSIZED_TRACKED_BLOB"], []
    if PurePosixPath(path).suffix not in TEXT_SUFFIXES and path not in {".gitignore", "LICENSE"}:
        return [], []
    blocked = []
    review = [rule for rule, rx in PRIVACY_WARNINGS.items() if rx.search(blob)]
    for rule, rx in PATTERNS.items():
        matches = list(rx.finditer(blob))
        if not matches:
            continue
        # Clearly labelled nonfunctional NVIDIA fixtures occur in unit tests.
        # They still require human review; no real-looking unlabelled key is
        # ever automatically exempted, including one placed inside a test.
        if (rule == "NVIDIA_CREDENTIAL" and path.startswith("tests/")
                and all(any(label in m.group().upper() for label in (
                    b"FAKE", b"DUMMY", b"TEST"
                )) for m in matches)):
            review.append("SYNTHETIC_NVIDIA_TEST_TOKEN")
        else:
            blocked.append(rule)
    return blocked, review


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def audit(head: str | None = None) -> dict:
    commit = git("rev-parse", "HEAD").decode().strip() if head is None else head
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("INVALID_COMMIT")
    paths = git("ls-tree", "-r", "-z", "--name-only", commit).decode("utf-8").split("\0")
    selected = select_files([p for p in paths if p])
    if not selected:
        raise ValueError("EMPTY_SOURCE_SELECTION")
    blocks = []
    warnings = []
    by_name = []
    for name in selected:
        blob = git("show", f"{commit}:{name}")
        found, review = classify(blob, name)
        if found:
            blocks.append({"file": name, "rule_ids": found})
        if review:
            warnings.append({"file": name, "rule_ids": review})
        by_name.append(name)
    return {
        "source_commit": commit,
        "tracked_file_count": len(paths) - 1,
        "selected_source_file_count": len(selected),
        "selected_files": by_name,
        "secret_pattern_blocker_count": len(blocks),
        "secret_pattern_blockers": blocks,
        "privacy_review_file_count": len(warnings),
        "privacy_review_files": warnings,
        "ignored_and_untracked_included": False,
        "source_from_commit_not_working_tree": True,
        "automated_scan_scope": "known-patterns-and-local-paths-only",
        "human_security_and_licence_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", action="store_true", help="Make LOCAL REVIEW ZIP (never publish)")
    parser.add_argument("--receipt", default="acceptance/logs/source-publication-preflight.json")
    args = parser.parse_args()
    report = audit()
    if args.archive and not report["secret_pattern_blocker_count"]:
        target = Path("acceptance/logs") / ("EvidenceTrail_Track02_SOURCE_REVIEW_"
                                          + report["source_commit"][:8] + ".zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "archive", "--format=zip", "-o", str(target),
             report["source_commit"], *report["selected_files"]],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        with ZipFile(target) as z:
            # git-archive emits harmless directory records as well as files.
            # Ignore only directory entries; exact selected file equality is
            # mandatory. Close ZIP before any Windows cleanup or replacement.
            zip_files = sorted(name for name in z.namelist()
                               if not name.endswith("/"))
        if zip_files != report["selected_files"]:
            target.unlink(missing_ok=True)
            raise ValueError("ARCHIVE_CONTENT_MISMATCH")
        report["archive_local_path"] = str(target)
        report["archive_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        report["archive_is_public"] = False
    report["publication_approval"] = "HUMAN_REVIEW_REQUIRED"
    receipt = Path(args.receipt)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "commit": report["source_commit"][:12],
        "selected_files": report["selected_source_file_count"],
        "secret_pattern_blockers": report["secret_pattern_blocker_count"],
        "privacy_review_files": report["privacy_review_file_count"],
        "review_archive_created": bool(report.get("archive_local_path")),
        "publication": "NOT_AUTHORIZED",
        "receipt": str(receipt)
    }))
    return 2 if report["secret_pattern_blocker_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
