"""Application port of Meterless H-MEM reference add/query/ledger.

Upstream: Meterless/Meterless commit 1742dec56a66e58eef9dda2d2b865823758ca8cd
engines/hmem/reference (Apache-2.0). Deterministic 64-d token-hash embeddings.
JSON state + unsigned JSONL ledger. NOT a cryptographic audit log.
This is a Python port of the documented contract so SAMPLE_MODE and tests run
without Node. Live Node vendor remains preferred when installed; see adapters/hmem.py.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Callable

DIM = 64
UPSTREAM_COMMIT = "1742dec56a66e58eef9dda2d2b865823758ca8cd"
EMBEDDING_DISCLAIMER = (
    "H-MEM reference embeddings are deterministic token-hash mocks, not semantic vectors. "
    f"Python port of Meterless engines/hmem/reference @ {UPSTREAM_COMMIT}. "
    "Ledger JSONL is unsealed (not cryptographically signed)."
)


def tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return [t for t in cleaned.split() if len(t) > 1]


def fnv1a(s: str) -> int:
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for token in tokenize(text):
        h = fnv1a(token)
        idx = h % DIM
        sign = 1 if ((h >> 8) % 2 == 0) else -1
        mag = 1 + ((h >> 16) % 8) / 8
        vec[idx] += sign * mag
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class TrustLedger:
    def __init__(self, persist_dir: Path | None, clock: Callable[[], int]):
        self.clock = clock
        self.path = persist_dir / "ledger.jsonl" if persist_dir else None
        self.entries: list[dict[str, Any]] = []
        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.entries.append(json.loads(line))

    def log(self, memory_id: str, action: str, actor: str, payload: dict[str, Any]) -> None:
        entry = {
            "ts": self.clock(),
            "memory_id": memory_id,
            "action": action,
            "actor": actor,
            "payload": payload,
            "integrity": "UNSEALED_JSONL",
        }
        self.entries.append(entry)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


class HMEM:
    """add / query / mine / ledger. query has NO as-of filter (upstream)."""

    def __init__(self, persist_dir: str | Path | None = None, clock: Callable[[], int] | None = None):
        self.clock = clock or (lambda: int(__import__("time").time() * 1000))
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.ledger = TrustLedger(self.persist_dir, self.clock)
        self.records: dict[str, dict[str, Any]] = {}
        self.seq = 0
        self.state_file = self.persist_dir / "state.json" if self.persist_dir else None
        if self.state_file and self.state_file.exists():
            saved = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.seq = saved.get("seq", 0)
            for rec in saved.get("records", []):
                self.records[rec["id"]] = rec

    def persist(self) -> None:
        if not self.state_file:
            return
        records = sorted(self.records.values(), key=lambda r: r["id"])
        self.state_file.write_text(
            json.dumps({"seq": self.seq, "records": records}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def add(
        self,
        content: str,
        source: str,
        tags: list[str] | None = None,
        mission_id: str | None = None,
        goal_run_id: str | None = None,
        chat_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not source or not str(source).strip():
            raise ValueError("H-MEM: a memory record with no source must be rejected by construction")
        now = self.clock()
        self.seq += 1
        rec = {
            "id": f"mem-{self.seq}",
            "content": content,
            "source": source,
            "tags": list(tags or []),
            "timestamp": now,
            "lastAccessed": now,
            "accessCount": 0,
            "embedding": embed(content),
            "missionId": mission_id,
            "goalRunId": goal_run_id,
            "chatId": chat_id,
            "provenance": provenance
            or {"origin": "evidencetrail", "learnedAt": now, "label": source, "engine_clock_not_source_published_at": True},
            "embedding_kind": "token_hash_mock_64d",
        }
        self.records[rec["id"]] = rec
        self.ledger.log(rec["id"], "create", "evidencetrail", {"source": source, "missionId": mission_id})
        self.persist()
        return rec

    def query(self, query: str, top_n: int = 8, chat_id: str | None = None) -> dict[str, Any]:
        qv = embed(query)
        scored = []
        for rec in self.records.values():
            if chat_id and rec.get("chatId") not in (None, chat_id):
                continue
            score = cosine(qv, rec.get("embedding") or embed(rec["content"]))
            scored.append({**{k: v for k, v in rec.items() if k != "embedding"}, "score": score})
        scored.sort(key=lambda r: r["score"], reverse=True)
        return {
            "query": query,
            "hits": scored[:top_n],
            "as_of_filter": "NONE_UPSTREAM",
            "disclaimer": EMBEDDING_DISCLAIMER,
        }

    def mine(self, text: str) -> list[dict[str, Any]]:
        kept = []
        for sentence in re.split(r"[.!?]+", text):
            s = sentence.strip()
            if 20 <= len(s) <= 300 and re.search(r"\b(decided|important|should|remember)\b", s, re.I):
                kept.append(self.add(s, source="hmem.mine", tags=["mined"]))
        return kept
