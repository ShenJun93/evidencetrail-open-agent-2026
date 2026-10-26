"""Explicit opt-in NVIDIA Nemotron NIM transport, with no fallback billing.

OFFLINE by default. Production transport is pinned to NVIDIA's documented
HTTPS host and exact Nemotron model. No user-supplied URL or model can turn
a fake loopback response into NVIDIA sponsor success. Injected transports
return UNIT_CONTRACT_ONLY even if their JSON looks correct.

A real HTTPS response proves network transport, *not* contest sponsor
acceptance or that the model's proposed disaster decision is valid.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
MAX_PROMPT_CHARS = 12_000
MAX_RESPONSE_BYTES = 262_144
MAX_TOKENS = 768
TIMEOUT_SECONDS = 35


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class NvidiaResult:
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
            "provider": "nvidia",
            "engine": "nemotron-direct-nim",
            "requested_model": MODEL,
            "returned_model": self.returned_model,
            "status": self.status,
            "request_id": self.request_id,
            "network_called": self.network_called,
            "injected_transport": self.test_transport,
            "usage": self.usage,
            "detail": self.detail,
            "contest_sponsor_acceptance_verified": False,
            "model_output_is_independently_safe": False,
        }


def _env_yes(key: str) -> bool:
    return os.environ.get(key, "").strip().casefold() == "true"


def gates() -> dict[str, bool]:
    """Booleans only; never print the key or include it in evidence files."""
    return {
        "explicit_nvidia_direct_enabled": _env_yes(
            "EVIDENCETRAIL_NVIDIA_DIRECT_ENABLED"
        ),
        "explicit_external_research_data_consent": _env_yes(
            "EVIDENCETRAIL_NVIDIA_EXTERNAL_DATA_CONSENT"
        ),
        "explicit_replacement_model_approval": _env_yes(
            "EVIDENCETRAIL_NVIDIA_35_VL_APPROVED"
        ),
        "nvidia_api_key_present": bool(
            os.environ.get("NVIDIA_API_KEY", "").strip()
        ),
    }


def _validate_messages(messages: list[dict[str, str]]) -> None:
    if (not isinstance(messages, list) or not (1 <= len(messages) <= 2)
        or not all(isinstance(m, dict) for m in messages)):
        raise ValueError("NVIDIA_PROMPT_SHAPE_REFUSED")
    total = 0
    for m in messages:
        if set(m) != {"role", "content"} or m["role"] not in {"system", "user"}:
            raise ValueError("NVIDIA_PROMPT_ROLES_REFUSED")
        text = m["content"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("NVIDIA_PROMPT_EMPTY")
        total += len(text)
    if total > MAX_PROMPT_CHARS:
        raise ValueError("NVIDIA_PROMPT_SIZE_REFUSED")
    if messages[-1]["role"] != "user":
        raise ValueError("NVIDIA_LAST_MESSAGE_NOT_USER")


def _parse_response(body: bytes) -> tuple[str, str, str, dict[str, int] | None]:
    if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("NVIDIA_REPLY_OVERSIZE_OR_NOT_BYTES")
    outer = json.loads(body.decode("utf-8"))
    if not isinstance(outer, dict):
        raise ValueError("NVIDIA_REPLY_NOT_OBJECT")
    model = outer.get("model")
    rid = outer.get("id")
    choices = outer.get("choices")
    if model != MODEL or not isinstance(rid, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{6,128}", rid
    ):
        raise ValueError("NVIDIA_REPLY_MODEL_IDENTITY_INVALID")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("NVIDIA_REPLY_CHOICE_SHAPE_INVALID")
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
        raise ValueError("NVIDIA_REPLY_UNFINISHED")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ValueError("NVIDIA_REPLY_ROLE_INVALID")
    content = message.get("content")
    if not isinstance(content, str) or not (1 <= len(content) <= 20_000):
        raise ValueError("NVIDIA_REPLY_TEXT_INVALID")
    raw_usage = outer.get("usage")
    usage = None
    if isinstance(raw_usage, dict):
        candidates = ("prompt_tokens", "completion_tokens", "total_tokens")
        if all(type(raw_usage.get(k)) is int and 0 <= raw_usage[k] <= 2_000_000
               for k in candidates):
            usage = {k: raw_usage[k] for k in candidates}
    return content, model, rid, usage


def _real_transport(request: urllib.request.Request) -> tuple[int, bytes]:
    # Disable ambient proxy configurations. TLS peer validation is performed
    # by the standard Python urllib SSL context. Redirects are blocked.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        status = int(response.status)
        body = response.read(MAX_RESPONSE_BYTES + 1)
    return status, body


class NvidiaNemotronDirect:
    def __init__(
        self,
        *,
        transport: Callable[[urllib.request.Request], tuple[int, bytes]] | None = None,
    ):
        self._transport = transport or _real_transport
        self.injected = transport is not None

    def chat(self, messages: list[dict[str, str]]) -> NvidiaResult:
        config = gates()
        if not config["explicit_nvidia_direct_enabled"]:
            return NvidiaResult(
                "BLOCKED", None, None, None, "NVIDIA_DIRECT_NOT_OPTED_IN",
                False, self.injected,
            )
        if not config["explicit_external_research_data_consent"]:
            return NvidiaResult(
                "BLOCKED", None, None, None, "NVIDIA_REMOTE_DATA_CONSENT_MISSING",
                False, self.injected,
            )
        if not config["explicit_replacement_model_approval"]:
            return NvidiaResult(
                "BLOCKED", None, None, None, "NVIDIA_35_VL_MODEL_APPROVAL_MISSING",
                False, self.injected,
            )
        key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if not key:
            return NvidiaResult(
                "NOT_CONFIGURED", None, None, None, "NVIDIA_API_KEY_NOT_SET",
                False, self.injected,
            )
        if not (10 <= len(key) <= 512) or re.search(r"\s", key):
            return NvidiaResult(
                "BLOCKED", None, None, None, "NVIDIA_API_KEY_INVALID_FORMAT",
                False, self.injected,
            )
        try:
            _validate_messages(messages)
        except (ValueError, TypeError):
            return NvidiaResult(
                "BLOCKED", None, None, None, "NVIDIA_SAFE_PROMPT_REJECTED",
                False, self.injected,
            )
        payload = json.dumps({
            "model": MODEL,
            "messages": messages,
            "temperature": 1.0,
            "top_p": 0.95,
            # Hosted API documents reasoning_effort=none; NIM quickstart
            # also documents an explicit chat-template switch to prevent
            # reasoning from consuming all tokens before visible JSON output.
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
            "max_tokens": MAX_TOKENS,
            "stream": False,
            # NVIDIA's model-specific API documents json_schema output.
            # This constrains proposal SHAPE, not source eligibility,
            # returned model identity, finish status, or sponsor certification.
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "proposed_verdict": {
                                "type": "string",
                                "enum": [
                                    "WARN", "NO_WARN", "INSUFFICIENT_EVIDENCE"
                                ],
                            },
                            "rationale": {"type": "string"},
                            "source_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "proposed_verdict", "rationale", "source_ids"
                        ],
                        "additionalProperties": False,
                    },
                },
            },
        }, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            ENDPOINT,
            method="POST",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer " + key,
                "User-Agent": "EvidenceTrail-Nemotron-PublicResearch/1",
            },
        )
        try:
            status, body = self._transport(request)
        except urllib.error.HTTPError as exc:
            code = int(exc.code)
            exc.close()
            return NvidiaResult(
                "UNAUTHORIZED" if code in (401, 403) else (
                    "NO_FREE_CREDITS" if code == 402 else (
                        "RATE_LIMITED" if code == 429 else "UNAVAILABLE")),
                None, None, None,
                f"NVIDIA_HTTP_{code}_NO_ACCEPTED_MODEL_OUTPUT",
                not self.injected, self.injected,
            )
        except (urllib.error.URLError, OSError, TimeoutError, ValueError, TypeError):
            return NvidiaResult(
                "UNAVAILABLE", None, None, None,
                "NVIDIA_NETWORK_OR_RESPONSE_TRANSPORT_FAILED",
                not self.injected, self.injected,
            )
        if status != 200:
            return NvidiaResult(
                "UNAVAILABLE", None, None, None,
                f"NVIDIA_HTTP_{status}_NO_ACCEPTED_MODEL_OUTPUT",
                not self.injected, self.injected,
            )
        try:
            content, model, rid, usage = _parse_response(body)
        except (ValueError, TypeError, UnicodeError, KeyError):
            return NvidiaResult(
                "BLOCKED", None, None, None,
                "NVIDIA_UNTRUSTED_OR_INCOMPLETE_REPLY_REFUSED",
                not self.injected, self.injected,
            )
        return NvidiaResult(
            "UNIT_CONTRACT_ONLY" if self.injected else "REAL_MODEL_RESPONSE",
            content, model, rid,
            "Injected fixture, NOT official NVIDIA inference" if self.injected else
            "Pinned official NVIDIA HTTPS endpoint returned requested Nemotron "
            "model with finished text; sponsor eligibility and decision safety "
            "require separate checks",
            not self.injected, self.injected, usage,
        )
