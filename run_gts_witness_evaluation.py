"""Offline four-bulletin relay-clock audit. No SQL, AI model, network or file writes."""
from __future__ import annotations

import argparse
import json
from evidencetrail.gts_witness import compare_gts_vs_bulletin_clocks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2024-10-07T11:49:00Z")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = compare_gts_vs_bulletin_clocks(args.as_of, strict=args.strict)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "REFUSED_INPUT_OR_CORPUS",
                          "error_code": type(exc).__name__,
                          "model_or_sponsor_called": False}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
