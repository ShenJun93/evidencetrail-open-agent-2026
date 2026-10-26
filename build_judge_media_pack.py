"""Build a local, static judge media packet from *actual* cold-judge Edge evidence.

No HTTP, models, secrets, screenshots invented, Git changes or browser control.
Requires a successful keyless cold-judge receipt and 3 real Edge screenshots
created within THIS EXACT checked-out commit by run_judge_coldstart.py.

Usage (after the cold judge run):
  py -3 build_judge_media_pack.py

Output (Git-ignored): acceptance/logs/judge-media-pack/index.html
"""
from __future__ import annotations

import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RECEIPT = Path("acceptance/logs/judge-coldstart-replay.json")
BROWSER = Path("acceptance/logs/counterfactual-ui")
OUTPUT = Path("acceptance/logs/judge-media-pack")
FILES = (
    ("counterfactual-1630-reported.png", "16:30 / Reported dateline",
     "INSUFFICIENT EVIDENCE",
     "The district report is not yet eligible at this replay clock; the rule abstains."),
    ("counterfactual-1645-reported.png", "16:45 / Reported dateline",
     "SIMULATED WARN — FICTIONAL CAPACITY",
     "A 16:37 datelined report plus fictional capacity are both pivotal. Remove either and the rule abstains."),
    ("counterfactual-1645-strict.png", "16:45 / Strict as-of 2024",
     "INSUFFICIENT EVIDENCE",
     "A later archive capture cannot authenticate when the publisher first made the report available."),
)


class MediaPackError(ValueError):
    """Fail closed without reading user configuration, prompt or model text."""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > 64_000:
        raise MediaPackError("REQUIRED_JSON_MISSING_OR_OVERSIZE")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise MediaPackError("REQUIRED_JSON_INVALID") from None
    if not isinstance(value, dict):
        raise MediaPackError("REQUIRED_JSON_OBJECT_EXPECTED")
    return value


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", timeout=8, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise MediaPackError("GIT_HEAD_UNAVAILABLE") from None
    head = result.stdout.strip()
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise MediaPackError("GIT_HEAD_INVALID")
    return head


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_sources(root: Path) -> tuple[dict[str, Any], list[tuple[str, bytes]], dict[str, Any]]:
    """Validate first, without writing anything, then return sanitized proofs."""
    receipt_file = root / RECEIPT
    receipt = _load_json(receipt_file)
    head = _git_head(root)
    if receipt.get("kind") != "EVIDENCETRAIL_COLD_JUDGE_REPLAY_V1":
        raise MediaPackError("JUDGE_RECEIPT_KIND_INVALID")
    if receipt.get("source_git_head") != head:
        raise MediaPackError("JUDGE_RECEIPT_HEAD_MISMATCH")
    if (receipt.get("status") != "PASS"
            or receipt.get("clean_keyless_source_replay") is not True
            or receipt.get("tracked_clean_before_tests") is not True
            or receipt.get("worktree_clean_before_tests") is not True
            or receipt.get("ignored_env_file_present_before_tests") is not False
            or receipt.get("meterless_vendor_present_before_tests") is not False
            or receipt.get("external_sponsor_requests_authorized") is not False
            or receipt.get("key_file_read_by_this_runner") is not False):
        raise MediaPackError("COLD_JUDGE_PROOF_NOT_KEYLESS_PASS")
    steps = receipt.get("steps")
    if not isinstance(steps, dict):
        raise MediaPackError("JUDGE_STAGES_MISSING")
    for step in ("python_acceptance", "chronology", "edge_e2e"):
        value = steps.get(step)
        if not isinstance(value, dict) or value.get("status") != "PASS" or value.get("exit_code") != 0:
            raise MediaPackError("JUDGE_STAGE_NOT_PASS")
    if (type(steps["python_acceptance"].get("python_tests")) is not int
            or steps["python_acceptance"]["python_tests"] < 309
            or steps["chronology"].get("pass") != 20
            or steps["chronology"].get("total") != 20
            or steps["edge_e2e"].get("scenarios") != 3):
        raise MediaPackError("JUDGE_STAGE_COUNTS_INVALID")
    if (receipt.get("nvidia_direct_sponsor_verified") is not False
            or receipt.get("nebius_structured_inference_verified") is not False
            or receipt.get("organizer_eligibility_verified") is not False
            or receipt.get("actual_disaster_forecast_accuracy_verified") is not False):
        raise MediaPackError("SPONSOR_OR_REAL_FORECAST_CLAIMS_NOT_SUPPORTED")
    smoke = _load_json(root / BROWSER / "counterfactual-browser-smoke.json")
    if (smoke.get("status") != "REAL_EDGE_BROWSER_3_SCENARIOS_PASS"
            or smoke.get("sample_only") is not True
            or smoke.get("no_real_nightshift_or_zetaris_call") is not True):
        raise MediaPackError("EDGE_SMOKE_PROOF_MISSING")
    expected_cases = [
        "16:45 reported WARN simulated minimum2 pivotal2",
        "16:45 strict INSUFFICIENT_EVIDENCE",
        "16:30 reported INSUFFICIENT_EVIDENCE",
    ]
    if smoke.get("scenarios") != expected_cases:
        raise MediaPackError("EDGE_SMOKE_CASES_INVALID")
    photos: list[tuple[str, bytes]] = []
    hashes: set[str] = set()
    for name, _, _, _ in FILES:
        source = root / BROWSER / name
        if not source.is_file() or not (12_000 <= source.stat().st_size <= 4_000_000):
            raise MediaPackError("EDGE_SCREENSHOT_MISSING_OR_WRONG_SIZE")
        data = source.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise MediaPackError("EDGE_SCREENSHOT_NOT_PNG")
        digest = _sha256(data)
        if digest in hashes:
            raise MediaPackError("EDGE_SCREENSHOTS_DUPLICATE")
        hashes.add(digest)
        photos.append((name, data))
    metadata = {
        "kind": "EVIDENCETRAIL_OFFLINE_MEDIA_PACK_V1",
        "source_git_head": head,
        "judge_receipt_sha256": _sha256(receipt_file.read_bytes()),
        "sample_only": True,
        "actual_storm_prediction_validated": False,
        "nvidia_nemotron_inference_verified": False,
        "organizer_eligibility_verified": False,
        "python_tests": steps["python_acceptance"]["python_tests"],
        "chronology_cases": 20,
        "real_isolated_edge_scenarios": 3,
        "screenshots": [{"filename": name, "sha256": _sha256(data)}
                        for name, data in photos],
    }
    return metadata, photos, smoke


def _render(meta: dict[str, Any]) -> str:
    cards: list[str] = []
    for i, (name, clock, verdict, reason) in enumerate(FILES, start=1):
        cards.append(
            '<article class="case">'
            f'<p class="eyebrow">SCENARIO {i} / REAL EDGE CAPTURE</p>'
            f'<h2>{html.escape(clock)}</h2>'
            f'<p class="verdict">{html.escape(verdict)}</p>'
            f'<img src="assets/{html.escape(name, quote=True)}" '
            f'alt="{html.escape(clock + " — " + verdict, quote=True)}">'
            f'<p>{html.escape(reason)}</p>'
            '</article>'
        )
    head = html.escape(meta["source_git_head"])
    digest = html.escape(meta["judge_receipt_sha256"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EvidenceTrail — Actual Offline Judge Media</title>
<style>
:root{{--bg:#101c25;--panel:#162b35;--ink:#f3efe6;--soft:#b5c5c6;--line:#46616a;--gold:#eab875}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,Segoe UI,sans-serif;margin:0}}
main{{max-width:1160px;margin:0 auto;padding:24px}}
h1,h2{{font-family:Georgia,serif;font-weight:500}}h1{{font-size:clamp(36px,5vw,64px);line-height:1.08;margin:14px 0}}
.kicker,.eyebrow{{color:var(--gold);font-size:12px;font-weight:750;letter-spacing:.09em;text-transform:uppercase}}
.summary{{color:var(--soft);max-width:950px}}
.banner{{border-left:4px solid var(--gold);padding:13px 17px;background:var(--panel);margin:22px 0}}
.case{{background:var(--panel);padding:18px 22px;margin:22px 0;border:1px solid var(--line);border-radius:8px}}
.case h2{{font-size:30px;margin:5px 0}}.case p{{max-width:950px}}
.verdict{{font-weight:800;letter-spacing:.02em;color:var(--gold)}}
img{{width:100%;height:auto;display:block;border:1px solid var(--line);background:#fff}}
code{{overflow-wrap:anywhere;font-size:12px;color:var(--soft)}}
footer{{border-top:1px solid var(--line);padding:22px 0;color:var(--soft)}}
</style></head><body><main>
<p class="kicker">Open Agent Hackathon 2026 / Track 02 / Authentic local artifacts</p>
<h1>Evidence available. Evidence missing. Explain why.</h1>
<p class="summary">Actual screenshots taken by the isolated Microsoft Edge localhost
smoke test, copied without editing from the same commit as the cold-judge receipt.
The three images show a historical research replay — not a real emergency
warning, not a cloud Nemotron inference and not a claimed award.</p>
<div class="banner"><strong>PROVEN OFFLINE:</strong> {meta["python_tests"]}/{meta["python_tests"]} Python;
20/20 adversarial chronology; 3/3 actual isolated Edge actions.
<strong>NOT PROVEN:</strong> real disaster forecast accuracy, NVIDIA inference,
official Zetaris sponsorship, Nightshift execution, or competition eligibility.</div>
{''.join(cards)}
<section class="case"><h2>Record a truthful demo</h2>
<p>Use the real interactive <code>http://127.0.0.1:8077/demo</code> UI for the
1–4 minute submission video. These images are audit references, not a substitute
for demonstrating real clicks. Show 16:30 abstention, 16:45
<strong>SIMULATED WARN with FICTIONAL capacity</strong>, the two pivotal source
ablations, and strict-as-of abstention. Do not cover simulated labels or
suggest these screenshots prove sponsor model inference.</p></section>
<footer><p>Source Git HEAD: <code>{head}</code></p>
<p>Sanitized cold-judge receipt SHA-256: <code>{digest}</code></p>
<p>Source screens are hashed in <code>manifest.json</code>. The manifest does
not certify organizer acceptance and makes no claim of network isolation beyond
the runner's stated scope.</p></footer>
</main></body></html>
"""


def build(root: Path = ROOT) -> dict[str, Any]:
    meta, images, _ = validate_sources(root)
    out = root / OUTPUT
    assets = out / "assets"
    # Do not overwrite ANY existing files, even in Git-ignored directories.
    # Refuse a pre-existing output or symlink; the owner manages prior packs.
    if out.exists() or out.is_symlink():
        raise MediaPackError("MEDIA_PACK_OUTPUT_ALREADY_EXISTS")
    # Validation finishes above before any output is generated.
    assets.mkdir(parents=True, exist_ok=False)
    for name, data in images:
        (assets / name).write_bytes(data)
    (out / "index.html").write_text(_render(meta), encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        "status": "OFFLINE_MEDIA_PACK_BUILT",
        "source_git_head": meta["source_git_head"],
        "python_tests": meta["python_tests"],
        "edge_scenarios": meta["real_isolated_edge_scenarios"],
        "sample_only": True,
        "sponsor_inference_verified": False,
        "output": OUTPUT.as_posix() + "/index.html",
    }


def main() -> int:
    try:
        result = build()
    except (MediaPackError, OSError) as exc:
        # Error codes, not raw file/trace/model contents.
        name = str(exc) if isinstance(exc, MediaPackError) else "LOCAL_MEDIA_IO_FAILED"
        print(json.dumps({"status": "BLOCKED", "reason": name}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
