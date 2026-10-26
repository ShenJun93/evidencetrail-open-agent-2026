"""Nebius Token Factory (THIRD-PARTY) model adapter, disabled by default.

Nebius invoices public endpoints per token unless the account has credits.
A Nebius-hosted NVIDIA open model is NOT an NVIDIA-direct sponsor receipt.
No network without three owner-controlled approval flags, even when a key exists.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

# Officially published Nebius Token Factory global OpenAI-compatible host and
# one Nebius-advertised model ID. No environment host/model override.
ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3-super-120b-a12b"
MAX_PROMPT_CHARS = 12000
MAX_TOKENS = 512
MAX_RESPONSE_BYTES = 262144
TIMEOUT_SECONDS = 35


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _yes(key: str) -> bool:
    return os.environ.get(key, "").strip().casefold() == "true"


def gates() -> dict[str, bool]:
    return {
        "nebius_api_key_present": bool(os.environ.get("NEBIUS_API_KEY", "").strip()),
        "explicit_nebius_enabled": _yes("EVIDENCETRAIL_NEBIUS_ENABLED"),
        "public_research_egress_approved": _yes("EVIDENCETRAIL_NEBIUS_PUBLIC_DATA_CONSENT"),
        "possible_usage_charges_approved": _yes(
            "EVIDENCETRAIL_NEBIUS_POSSIBLE_CHARGES_APPROVED"
        ),
    }


@dataclass(frozen=True)
class NebiusResult:
    status: str
    text: str | None
    returned_model: str | None
    request_id: str | None
    detail: str
    network_called: bool
    test_transport: bool
    usage: dict[str, int] | None = None

    def public_receipt(self) -> dict[str, Any]:
        return {
            "provider": "nebius",
            "engine": "token-factory-third-party-chat",
            "requested_model": MODEL,
            "returned_model": self.returned_model,
            "status": self.status,
            "request_id": None if self.test_transport else self.request_id,
            "detail": self.detail,
            "network_called": self.network_called,
            "injected_transport": self.test_transport,
            "usage": self.usage,
            "nvidia_direct_sponsor_receipt": False,
            "contest_organizer_eligibility_verified": False,
            "independent_disaster_decision_validated": False,
        }


def _validate_messages(messages: list[dict[str, str]]) -> bool:
    if not isinstance(messages, list) or not (1 <= len(messages) <= 2):
        return False
    if not all(isinstance(m, dict) and set(m) == {"role", "content"}
               and m["role"] in {"system", "user"}
               and isinstance(m["content"], str) and m["content"].strip()
               for m in messages):
        return False
    return (messages[-1]["role"] == "user"
            and sum(len(m["content"]) for m in messages) <= MAX_PROMPT_CHARS)


def _parse(body: bytes) -> tuple[str, str, str, dict[str, int] | None]:
    if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("NEBIUS_OVERSIZE")
    outer = json.loads(body.decode("utf8"))
    if not isinstance(outer, dict) or outer.get("model") != MODEL:
        raise ValueError("NEBIUS_MODEL_IDENTITY_REFUSED")
    rid = outer.get("id")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{6,128}", rid):
        raise ValueError("NEBIUS_REQUEST_ID_REFUSED")
    choices = outer.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("NEBIUS_CHOICES_REFUSED")
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
        raise ValueError("NEBIUS_UNFINISHED")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ValueError("NEBIUS_MESSAGE_REFUSED")
    content = message.get("content")
    if not isinstance(content, str) or not (1 <= len(content) <= 20000):
        raise ValueError("NEBIUS_CONTENT_REFUSED")
    usage = outer.get("usage")
    if not isinstance(usage, dict) or not all(
        type(usage.get(k)) is int and 0 <= usage[k] <= 2000000
        for k in ("prompt_tokens", "completion_tokens", "total_tokens")
    ):
        usage = None
    else:
        usage = {k: usage[k] for k in
                 ("prompt_tokens", "completion_tokens", "total_tokens")}
    return content, MODEL, rid, usage


def _real_transport(request: urllib.request.Request) -> tuple[int, bytes]:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        return int(response.status), response.read(MAX_RESPONSE_BYTES + 1)


class NebiusTokenFactory:
    def __init__(
        self, *, transport: Callable[[urllib.request.Request],
                                     tuple[int, bytes]] | None = None
    ):
        self._transport = transport or _real_transport
        self.injected = transport is not None

    def chat(self, messages: list[dict[str, str]]) -> NebiusResult:
        g = gates()
        for check, reason in (
            ("explicit_nebius_enabled", "NEBIUS_NOT_OPTED_IN"),
            ("public_research_egress_approved", "NEBIUS_PUBLIC_DATA_CONSENT_MISSING"),
            ("possible_usage_charges_approved", "NEBIUS_USAGE_CHARGES_NOT_APPROVED"),
        ):
            if not g[check]:
                return NebiusResult("BLOCKED", None, None, None,
                                    reason, False, self.injected)
        key = os.environ.get("NEBIUS_API_KEY", "").strip()
        if not key:
            return NebiusResult("NOT_CONFIGURED", None, None, None,
                                "NEBIUS_API_KEY_MISSING", False, self.injected)
        if not (10 <= len(key) <= 512) or re.search(r"\s", key):
            return NebiusResult("BLOCKED", None, None, None,
                                "NEBIUS_KEY_FORMAT_REFUSED", False, self.injected)
        if not _validate_messages(messages):
            return NebiusResult("BLOCKED", None, None, None,
                                "NEBIUS_PROMPT_REFUSED", False, self.injected)
        payload = json.dumps({
            "model": MODEL,
            "messages": messages,
            "max_tokens": MAX_TOKENS,
            # Nebius supports JSON mode; model-specific behavior remains
            # unverified. Existing strict safety/citation rules are unchanged.
            "response_format": {"type": "json_object"},
            "stream": False,
        }, ensure_ascii=False, separators=(",", ":")).encode("utf8")
        request = urllib.request.Request(
            ENDPOINT, method="POST", data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
                "User-Agent": "EvidenceTrail-Nebius-PublicResearch/1",
            },
        )
        try:
            status, body = self._transport(request)
        except urllib.error.HTTPError as exc:
            code = int(exc.code)
            exc.close()
            return NebiusResult(
                "UNAUTHORIZED" if code in (401, 403) else (
                    "RATE_LIMITED" if code == 429 else "UNAVAILABLE"),
                None, None, None,
                f"NEBIUS_HTTP_{code}_NO_ACCEPTED_MODEL_REPLY",
                not self.injected, self.injected,
            )
        except (urllib.error.URLError, OSError, TimeoutError,
                ValueError, TypeError):
            return NebiusResult(
                "UNAVAILABLE", None, None, None, "NEBIUS_NETWORK_FAILED",
                not self.injected, self.injected,
            )
        if status != 200:
            return NebiusResult(
                "UNAVAILABLE", None, None, None,
                f"NEBIUS_HTTP_{status}_NO_ACCEPTED_MODEL_REPLY",
                not self.injected, self.injected,
            )
        try:
            content, model, rid, usage = _parse(body)
        except (ValueError, KeyError, TypeError, UnicodeError):
            return NebiusResult(
                "BLOCKED", None, None, None,
                "NEBIUS_UNTRUSTED_OR_INCOMPLETE_REPLY_REFUSED",
                not self.injected, self.injected,
            )
        return NebiusResult(
            "UNIT_CONTRACT_ONLY" if self.injected else "REAL_THIRD_PARTY_MODEL_RESPONSE",
            content, model, rid,
            "Fixture only; no vendor inference" if self.injected else
            "Authenticated Nebius HTTPS response; neither NVIDIA-direct sponsor "
            "proof nor contest eligibility",
            not self.injected, self.injected, usage,
        )
