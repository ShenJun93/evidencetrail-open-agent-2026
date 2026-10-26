"""Read ONLY official Nightshift Windows TEXT metadata and enforce a no-install gate.

Does not retrieve the installer, execute it, sign it, bypass SmartScreen, access
accounts/tokens, or assert organizer eligibility. Intended as an independently
repeatable release-admission *preflight*, not Runtime live acceptance.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://meterless.ai/Nightshift/WIN/"
FILES = ("manifest.json", "APP_BUILD_INFO.txt", "SHA256SUMS")
MAX_TEXT_BYTES = 200_000
DEFAULT_RECEIPT = Path("acceptance/logs/nightshift-release-gate-2026-10-23.json")
WIN_SETUP = re.compile(r"^Nightshift_[0-9]+\.[0-9]+\.[0-9]+_x64-setup\.exe$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("SPONSOR_METADATA_REDIRECT_REFUSED")


def read_publisher_text(name: str) -> str:
    if name not in FILES:
        raise ValueError("UNAPPROVED_REMOTE_FILE")
    req = urllib.request.Request(BASE + name, headers={
        "Accept": "application/json, text/plain",
        "User-Agent": "EvidenceTrail-Local-Metadata-Safety-Check/1.0",
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=10) as resp:
        if resp.status != 200:
            raise ValueError("SPONSOR_METADATA_HTTP_NOT_200")
        raw = resp.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("SPONSOR_METADATA_TOO_LARGE")
    return raw.decode("utf-8-sig")


def _required_line(text: str, field: str) -> str:
    m = re.search(r"(?im)^\s*" + re.escape(field) + r":\s*([^\r\n]+?)\s*$", text)
    if m is None:
        raise ValueError("BUILD_INFO_MISSING_" + field.upper())
    return m.group(1).strip()


def evaluate_release(manifest_text: str, build_info: str, sums_text: str) -> dict:
    manifest = json.loads(manifest_text)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("components"), list):
        raise ValueError("INVALID_MANIFEST")
    setups = [
        art for component in manifest["components"]
        if isinstance(component, dict) and isinstance(component.get("artifacts"), list)
        for art in component["artifacts"]
        if isinstance(art, dict) and WIN_SETUP.fullmatch(str(art.get("file", "")))
    ]
    if len(setups) != 1:
        raise ValueError("EXPECTED_EXACTLY_ONE_WINDOWS_NSIS_ARTIFACT")
    file = setups[0]["file"]
    manifest_hash = str(setups[0].get("sha256", "")).lower()
    manifest_size = setups[0].get("size")
    if not HEX64.fullmatch(manifest_hash) or type(manifest_size) is not int or manifest_size <= 0:
        raise ValueError("MANIFEST_SHA_OR_SIZE_INVALID")
    build_file = _required_line(build_info, "artifact")
    build_hash = _required_line(build_info, "sha256").lower()
    build_size = int(_required_line(build_info, "size").split()[0])
    signature = _required_line(build_info, "signature")
    sums = {}
    for line in sums_text.splitlines():
        m = re.match(r"^([a-f0-9]{64})\s+\*?([^\s]+)\s*$", line.strip().lower())
        if m is not None:
            sums[m.group(2)] = m.group(1)
    sum_hash = sums.get(file.lower())
    hashes_agree = (
        build_file == file and manifest_hash == build_hash == sum_hash
        and manifest_size == build_size
    )
    if not hashes_agree:
        status = "INSTALL_BLOCKED_METADATA_MISMATCH"
    elif signature.lower() == "notsigned":
        status = "INSTALL_BLOCKED_UNSIGNED"
    else:
        # Publisher metadata cannot prove the Authenticode status of a binary
        # that has not been downloaded and verified on the owner PC.
        status = "INSTALL_BLOCKED_BINARY_NOT_VERIFIED"
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "publisher_base": BASE,
        "publisher_release": str(manifest.get("release", "unversioned")),
        "artifact": file,
        "artifact_declared_bytes": manifest_size,
        "published_sha256": manifest_hash,
        "metadata_hashes_and_size_consistent": hashes_agree,
        "publisher_signature_label": signature,
        "installer_downloaded": False,
        "local_binary_sha256_measured": False,
        "local_authenticode_trust_verified": False,
        "runtime_models_probe": "NOT_CALLED",
        "runtime_chat_completion": "NOT_CALLED",
        "organizer_eligibility": "NOT_VERIFIED",
        "status": status,
        "notice": "A matching publisher hash is not a trusted executable signature. "
                  "This check NEVER installs a binary or authorizes security bypass.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", default=str(DEFAULT_RECEIPT))
    args = parser.parse_args()
    # Only these three bounded public metadata endpoints are fetched.
    manifest, build, sums = [read_publisher_text(name) for name in FILES]
    report = evaluate_release(manifest, build, sums)
    out = Path(args.receipt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "release": report["publisher_release"],
        "artifact": report["artifact"],
        "metadata_consistent": report["metadata_hashes_and_size_consistent"],
        "status": report["status"],
        "installer_downloaded": report["installer_downloaded"],
        "organizer_eligibility": report["organizer_eligibility"],
        "receipt": str(out),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
