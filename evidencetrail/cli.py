from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evidencetrail.adapters.meterless import live_status as meterless_live_status
from evidencetrail.adapters.zetaris import ZetarisAdapter
from evidencetrail.models import RunRequest
from evidencetrail.pipeline import EvidenceTrailPipeline


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    import os

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidencetrail", description="EvidenceTrail Yagi replay CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="POST-equivalent JSON run")
    run_p.add_argument("--input", required=True, help="JSON request path")
    run_p.add_argument("--out", default="logs")
    modes = run_p.add_mutually_exclusive_group()
    modes.add_argument("--sample-mode", action="store_true", default=False)
    modes.add_argument("--live", action="store_true", default=False)

    sub.add_parser("probe-sponsors", help="Honest sponsor probes; never forge PASS")
    serve = sub.add_parser("serve", help="JSON HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8077)
    serve.add_argument("--enable-local-nightshift", action="store_true",
                       help="enable one user-clicked local Runtime proposal route; never loads env files")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
        # Explicit CLI --live is the ONLY way to permit sponsor traffic.
        # An input fixture's sample_mode=false must never escalate authority.
        sample = not args.live
        if not sample:
            _load_env_file(Path(".env.local"))
            _load_env_file(Path(".env"))
        raw["sample_mode"] = sample
        request = RunRequest.from_dict(raw)
        pipe = EvidenceTrailPipeline(sample_mode=sample, log_dir=args.out)
        result = pipe.run(request)
        json.dump(result.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.cmd == "probe-sponsors":
        _load_env_file(Path(".env.local"))
        _load_env_file(Path(".env"))
        z = ZetarisAdapter(sample_mode=False).probe()
        m = meterless_live_status()
        payload = {
            "zetaris": z.to_dict(),
            "meterless_runtime_v4": m,
            "note": "SAMPLE_CACHE/UNAVAILABLE/NOT_CONFIGURED are not PASS. LIVE_NIGHTSHIFT_BLOCKED until trusted runtime answers.",
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.cmd == "serve":
        from evidencetrail.api import serve

        if args.enable_local_nightshift:
            serve(args.host, args.port, enable_local_nightshift=True)
        else:
            serve(args.host, args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
