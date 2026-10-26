"""Meterless Runtime provider contract v4 (Power). Isolated from live Nightshift."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

FORBIDDEN_TOKEN = "rt-local"
DEFAULT_BASE = "http://127.0.0.1:8088/v1"
DETECT_PORTS = (8088, 8090, 8787, 11434)
DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")
MAX_RESPONSE_BYTES = 1_048_576
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ALLOWED_PATHS = frozenset({"", "/", "/v1", "/v1/", "/v1/models", "/v1/chat/completions", "/healthz"})
ROUTED_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$")
STABLE_APP_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def parse_routed_receipt(data: dict[str, Any]) -> dict[str, str] | None:
    """Sanitise only the self-reported route; not proof of vendor identity.

    Runtime responses have used both a direct meterless object and a nested
    receipt. Never preserve full response metadata: it can contain auth keys,
    URLs, user inputs or arbitrary untrusted fields.
    """
    raw = data.get("meterless")
    if not isinstance(raw, dict):
        return None
    # Nightshift v1.2.3 puts routed_model beside its full receipt envelope.
    # Older responses placed it inside receipt. Reject conflicting claims.
    nested = raw.get("receipt")
    if nested is not None and not isinstance(nested, dict):
        return None
    direct_route = raw.get("routed_model")
    nested_route = nested.get("routed_model") if nested is not None else None
    if direct_route is not None and nested_route is not None and direct_route != nested_route:
        return None
    routed = direct_route if direct_route is not None else nested_route
    if not isinstance(routed, str) or not ROUTED_MODEL.fullmatch(routed):
        return None
    info = {"routed_model": routed}
    provider_model = raw.get("provider_model")
    if provider_model is None and nested is not None:
        provider_model = nested.get("provider_model")
    if isinstance(provider_model, str) and ROUTED_MODEL.fullmatch(provider_model):
        info["provider_model"] = provider_model
    return info


KNOWN_MODES = {
    "meterless/auto",
    "meterless/fast",
    "meterless/deep",
    "meterless/cheap",
    "meterless/local",
    "meterless/fusion",
}


def normalize_v1_base(raw: str | None) -> str:
    """Canonicalize approved loopback Runtime hosts; never send a bearer remotely."""
    text = (raw or DEFAULT_BASE).strip() or DEFAULT_BASE
    if "://" not in text:
        text = "http://" + text
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("METERLESS_LOCAL_RUNTIME_BASE_INVALID") from exc
    if (parsed.scheme != "http" or parsed.hostname not in _LOCAL_HOSTS
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment or parsed.path not in _ALLOWED_PATHS):
        raise ValueError("METERLESS_LOCAL_RUNTIME_BASE_INVALID")
    host = "[::1]" if parsed.hostname == "::1" else parsed.hostname
    return f"http://{host}{f':{port}' if port is not None else ''}/v1"

def reject_placeholder_token(token: str | None) -> str | None:
    if token is None:
        return None
    stripped = token.strip()
    if not stripped:
        return None
    if stripped == FORBIDDEN_TOKEN:
        raise ValueError("meterless_runtime_token must not be the placeholder rt-local")
    # Authorization bearer credentials must be a single visible ASCII value.
    # Refuse copied headers/config snippets and embedded clipboard line breaks
    # before urllib sees the secret-bearing header.
    if any(ord(char) < 0x21 or ord(char) > 0x7E for char in stripped):
        raise ValueError("METERLESS_RUNTIME_TOKEN_INVALID")
    return stripped


Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, dict[str, str], bytes]]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("METERLESS_REDIRECT_WITH_TOKEN_REFUSED")


def _urllib_transport(
    url: str, method: str, headers: dict[str, str], body: bytes | None, timeout: float
) -> tuple[int, dict[str, str], bytes]:
    """Disable proxy and redirects, enforce loopback, bound received bytes."""
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in _LOCAL_HOSTS:
        raise ValueError("METERLESS_NON_LOOPBACK_TRANSPORT_REFUSED")
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as resp:
            payload = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ValueError("METERLESS_RESPONSE_TOO_LARGE")
            return resp.status, dict(resp.headers), payload
    except urllib.error.HTTPError as exc:
        payload = exc.read(MAX_RESPONSE_BYTES + 1) if exc.fp else b""
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("METERLESS_RESPONSE_TOO_LARGE")
        return exc.code, dict(exc.headers or {}), payload

@dataclass
class ProbeResult:
    status: str  # online | unauthorized | offline | not_connected
    detail: str
    base: str
    models: list[str]


class MeterlessRuntimeProvider:
    """Official v4 adapter. Contract unit tests inject a fake transport."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        app: str = "evidencetrail",
        timeout_sec: float = 180,
        transport: Transport | None = None,
    ):
        self.base = normalize_v1_base(base_url or os.environ.get("METERLESS_BASE_URL") or DEFAULT_BASE)
        self.token = reject_placeholder_token(
            token if token is not None else os.environ.get("METERLESS_RUNTIME_TOKEN")
        )
        self.app = app or os.environ.get("METERLESS_APP", "evidencetrail")
        if not isinstance(self.app, str) or not STABLE_APP_ID.fullmatch(self.app):
            raise ValueError("METERLESS_APP_ID_MUST_BE_STABLE_LOWERCASE")
        self.timeout = float(os.environ.get("METERLESS_TIMEOUT_SEC", timeout_sec))
        self.transport = transport or _urllib_transport

    def _headers(self, chat: bool = False) -> dict[str, str]:
        headers = {"meterless-app": self.app, "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if chat:
            headers["meterless-scope"] = "user"
            headers["Content-Type"] = "application/json"
        return headers

    def classify_models_response(self, status: int, body: bytes) -> ProbeResult:
        if status in (401, 403):
            return ProbeResult("unauthorized", f"HTTP {status}", self.base, [])
        if status != 200:
            return ProbeResult("offline", f"HTTP {status}", self.base, [])
        try:
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("models response not object")
            items = data.get("data", data.get("models", []))
            if not isinstance(items, list) or len(items) > 200:
                raise ValueError("models response missing bounded list")
            ids = []
            for item in items:
                mid = item.get("id") if isinstance(item, dict) else item
                if isinstance(mid, str) and 0 < len(mid) <= 160:
                    ids.append(mid)
        except (UnicodeError, ValueError, TypeError):
            return ProbeResult("offline", "models JSON invalid", self.base, [])
        modes = [m for m in ids if re.fullmatch(r"meterless/[a-zA-Z0-9_./-]{1,100}", m)]
        if modes:
            return ProbeResult("online", "HTTP 200 with meterless ids", self.base, modes)
        return ProbeResult("offline", "HTTP 200 without meterless/* ids", self.base, ids)

    def models(self) -> ProbeResult:
        if not self.token:
            return ProbeResult("not_connected", "meterless_runtime_token absent", self.base, [])
        status, _, body = self.transport(
            f"{self.base}/models", "GET", self._headers(), None, min(self.timeout, 8)
        )
        return self.classify_models_response(status, body)

    def healthz(self) -> str:
        try:
            status, _, _ = self.transport(
                self.base.replace("/v1", "/healthz"), "GET", self._headers(), None, 3
            )
            return f"process_http_{status}"
        except Exception as exc:
            return f"healthz_error:{type(exc).__name__}"

    def chat(self, prompt: str, model: str = "meterless/auto",
             max_tokens: int | None = None) -> dict[str, Any]:
        if not self.token:
            return {"ok": False, "status": "not_connected", "text": None}
        if not isinstance(model, str) or not re.fullmatch(r"meterless/[A-Za-z0-9_./-]{1,100}", model):
            raise ValueError("INVALID_METERLESS_MODEL_ID")
        if not isinstance(prompt, str) or len(prompt) > 16000:
            raise ValueError("METERLESS_PROMPT_TOO_LARGE")
        if max_tokens is not None and (type(max_tokens) is not int or not 1 <= max_tokens <= 1024):
            raise ValueError("METERLESS_MAX_TOKENS_INVALID")
        request = {
            "model": model, "messages": [{"role": "user", "content": prompt}]
        }
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        payload = json.dumps(request).encode("utf-8")
        status, _, body = self.transport(
            f"{self.base}/chat/completions", "POST", self._headers(chat=True),
            payload, self.timeout
        )
        if status != 200:
            label = "unauthorized" if status in (401, 403) else "offline"
            return {"ok": False, "status": label, "http": status, "text": None}
        try:
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("chat response not object")
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise ValueError("invalid choices")
            msg = choices[0].get("message")
            text = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                raise ValueError("empty or invalid completion")
        except (UnicodeError, ValueError, KeyError, TypeError, AttributeError):
            return {"ok": False, "status": "invalid_response", "text": None}
        request_id = data.get("id")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", request_id):
            request_id = None
        route = parse_routed_receipt(data)
        return {
            "ok": True, "status": "online", "text": text,
            "raw_id": request_id, "route_receipt": route,
            "route_identity_independently_verified": False,
        }

    def autodetect(self) -> ProbeResult:
        """Loopback only. First online or unauthorized hit wins."""
        for host in DETECT_HOSTS:
            for port in DETECT_PORTS:
                host_url = f"http://{host}:{port}/v1"
                probe = MeterlessRuntimeProvider(
                    base_url=host_url,
                    token=self.token,
                    app=self.app,
                    timeout_sec=2,
                    transport=self.transport,
                )
                try:
                    result = probe.models()
                except Exception as exc:
                    result = ProbeResult("offline", str(exc), host_url, [])
                if result.status in ("online", "unauthorized"):
                    return result
        return ProbeResult("offline", "no loopback runtime found", self.base, [])


def live_status() -> dict[str, Any]:
    try:
        provider = MeterlessRuntimeProvider()
    except ValueError as exc:
        return {
            "provider": "meterless",
            "engine": "runtime-v4",
            "outcome": "BLOCKED",
            "detail": str(exc),
            "contract_label": "ADAPTER_CONTRACT_ONLY",
            "live_inference": "LIVE_NIGHTSHIFT_BLOCKED",
        }
    try:
        models = provider.models()
    except Exception as exc:
        models = ProbeResult("offline", f"{type(exc).__name__}: {exc}", provider.base, [])
    health = provider.healthz() if provider.token else "not_checked_no_token"
    outcome = {
        "online": "REAL_PROBE_ONLY",
        "unauthorized": "UNAUTHORIZED",
        "not_connected": "NOT_CONFIGURED",
        "offline": "UNAVAILABLE",
    }.get(models.status, "UNAVAILABLE")
    return {
        "provider": "meterless",
        "engine": "runtime-v4",
        "outcome": outcome,
        "detail": f"{models.detail}; healthz={health}",
        "contract_label": "ADAPTER_CONTRACT_ONLY" if models.status != "online" else "LIVE_MODELS_PROBE_ONLY_NO_CHAT",
        "live_inference": "LIVE_NIGHTSHIFT_BLOCKED" if models.status != "online" else "MODELS_ONLINE_CHAT_NOT_ASSERTED",
        "models": models.models,
        "base": models.base,
    }
