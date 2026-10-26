from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evidencetrail.models import utc_now, iso


class JsonlTrace:
    def __init__(self, path: Path, run_id: str):
        self.path = path
        self.run_id = run_id
        self.seq = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()

    def emit(self, stage: str, action: str, status: str, **payload: Any) -> dict[str, Any]:
        self.seq += 1
        event = {
            "run_id": self.run_id,
            "sequence": self.seq,
            "ts": iso(utc_now()),
            "stage": stage,
            "action": action,
            "status": status,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event


def digest(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]
