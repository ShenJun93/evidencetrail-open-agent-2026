"""Local-only EvidenceTrail JSON API and judge dossier.

The default server is offline/sample-only. A separate, explicit startup flag
may enable one user-clicked local Nightshift proposal route for imported cases.
That route is loopback-only, never reads env files, never contacts cloud APIs,
and never changes the deterministic verdict. This is not a production service.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from evidencetrail.models import RunRequest
from evidencetrail.catalog import all_catalog
from evidencetrail.counterfactual import counterfactual_dossier
from evidencetrail.integrity_challenge import run_evidence_integrity_challenge
from evidencetrail.external_milton import run_milton_external_replay
from evidencetrail.cross_issuer_milton import run_cross_issuer_milton
from run_why_source_counterfactual import evaluate as evaluate_source_why
from run_zetaris_cross_issuer import import_rows as why_offline_rows
from run_judge_chronology_stress_benchmark import run_benchmark
from run_explanation_baseline_benchmark import run_comparison
from evidencetrail.pipeline import EvidenceTrailPipeline
from evidencetrail.case_investigator import example_case, investigate_case
from evidencetrail.case_nightshift import propose_local_explanation
from evidencetrail.case_workbench import DraftRefusal, append_case_evidence, prepare_case_draft

MAX_REQUEST_BYTES = 65_536
DEMO_HTML = Path(__file__).resolve().parent.parent / "demo" / "index.html"
PROOF_HTML = Path(__file__).resolve().parent.parent / "demo" / "proof.html"
WHY_HTML = Path(__file__).resolve().parent.parent / "demo" / "why.html"
WHY_DEMO_CLOCKS = frozenset({"2024-10-07T03:59:00Z","2024-10-07T04:00:00Z",
                              "2024-10-07T11:00:00Z","2024-10-07T15:00:00Z",
                              "2024-10-08T04:00:00Z"})


def create_local_server(host: str, port: int, *, pipeline: EvidenceTrailPipeline | None = None,
                        enable_local_nightshift: bool = False) -> ThreadingHTTPServer:
    """Loopback sample server with an optional explicit local inference lane."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("DEMO_LOCALHOST_BIND_REQUIRED")
    if type(enable_local_nightshift) is not bool:
        raise ValueError("LOCAL_NIGHTSHIFT_FLAG_REQUIRES_BOOL")
    if pipeline is not None and not pipeline.sample_mode:
        raise ValueError("DEMO_INJECTED_LIVE_PIPELINE_REFUSED")
    pipeline = pipeline or EvidenceTrailPipeline(sample_mode=True)

    class Handler(BaseHTTPRequestHandler):
        def _write(self, code: int, data: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _send(self, code: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._write(code, data, "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            # Click-through clients can append tracking query parameters
            # (e.g. ?utm_source=chatgpt.com). GET routes are read-only;
            # normalize ONLY their path while keeping POST routes exact.
            route = self.path.split("?", 1)[0]
            if route in ("/health", "/"):
                self._send(200, {"ok": True, "service": "evidencetrail",
                                 "post": "/run", "demo": "/demo", "proof": "/proof",
                                 "counterfactual_post": "/counterfactual",
                                 "benchmark_get": "/benchmark",
                                 "comparison_get": "/comparison",
                                 "integrity_challenge_get": "/integrity",
                                 "external_nhc_post": "/external-milton",
                                 "cross_issuer_post": "/cross-issuer",
                                 "source_counterfactual_post": "/why-counterfactual",
                                 "source_counterfactual_page": "/why",
                                 "case_investigation_post": "/case-investigation",
                                 "sample_mode_only": not enable_local_nightshift,
                                 "local_nightshift_enabled": enable_local_nightshift})
                return
            if route in ("/case-examples/warehouse", "/case-examples/milton"):
                self._send(200, example_case(route.rsplit("/", 1)[-1]))
                return
            if route == "/integrity":
                try:
                    report = run_evidence_integrity_challenge()
                except Exception as exc:
                    self._send(503, {"error": "integrity_challenge_unavailable",
                                     "exception_type": type(exc).__name__})
                    return
                self._send(200, report)
                return
            if route == "/comparison":
                try:
                    report = run_comparison()
                except Exception as exc:
                    self._send(503, {"error": "comparison_unavailable",
                                     "exception_type": type(exc).__name__})
                    return
                self._send(200, report)
                return
            if route == "/benchmark":
                try:
                    report = run_benchmark()  # 20 fixed local CPU sample cases
                except Exception as exc:
                    self._send(503, {"error": "benchmark_unavailable",
                                     "exception_type": type(exc).__name__})
                    return
                # Never signal success merely because we returned HTTP 200.
                # The browser must also inspect all_cases_pass, 20/20 and
                # the deliberately unsafe negative control.
                self._send(200, report)
                return
            if route in ("/demo", "/demo/"):
                try:
                    data = DEMO_HTML.read_bytes()
                except OSError:
                    self._send(503, {"error": "demo_asset_unavailable"})
                    return
                self._write(200, data, "text/html; charset=utf-8")
                return
            if route in ("/why", "/why/"):
                try:
                    data = WHY_HTML.read_bytes()
                except OSError:
                    self._send(503, {"error": "why_asset_unavailable"})
                    return
                self._write(200, data, "text/html; charset=utf-8")
                return
            if route in ("/case-workbench.js", "/ui.css"):
                asset, content_type = {
                    "/case-workbench.js": ("case-workbench.js", "application/javascript; charset=utf-8"),
                    "/ui.css": ("ui.css", "text/css; charset=utf-8"),
                }[route]
                try:
                    data = (WHY_HTML.parent / asset).read_bytes()
                except OSError:
                    self._send(503, {"error": "ui_asset_unavailable"})
                    return
                self._write(200, data, content_type)
                return
            if route in ("/proof", "/proof/"):
                try:
                    data = PROOF_HTML.read_bytes()
                except OSError:
                    self._send(503, {"error": "proof_asset_unavailable"})
                    return
                self._write(200, data, "text/html; charset=utf-8")
                return
            self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in ("/run", "/counterfactual", "/external-milton", "/cross-issuer", "/why-counterfactual", "/case-investigation", "/case-local-nightshift", "/case-draft", "/case-evidence"):
                self._send(404, {"error": "not_found"})
                return
            if self.path == "/case-local-nightshift" and not enable_local_nightshift:
                self._send(404, {"error": "not_found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > MAX_REQUEST_BYTES:
                    self._send(413, {"error": "invalid_or_oversized_request"})
                    return
                raw = json.loads(self.rfile.read(size).decode("utf-8"))
                if not isinstance(raw, dict):
                    self._send(400, {"error": "expected_json_object"})
                    return
                if self.path in ("/case-draft", "/case-evidence"):
                    # These pure authoring routes cannot read keys or fetch a locator.
                    allowed = ({"draft", "strict", "search_depth"} if self.path == "/case-draft" else
                               {"case", "sources", "as_of_utc", "strict", "search_depth"})
                    if set(raw) - allowed: raise ValueError("WORKBENCH_FIELDS_REFUSED")
                    options = {"strict": raw.get("strict", False), "search_depth": raw.get("search_depth", 2)}
                    result = (prepare_case_draft(raw["draft"], **options) if self.path == "/case-draft" else
                              append_case_evidence(raw["case"], raw["sources"],
                                                   as_of_utc=raw.get("as_of_utc"), **options))
                elif self.path == "/case-investigation":
                    # Deliberately separate from the fixed demo's allowlist.
                    # Imports remain untrusted local data, with no provider,
                    # filesystem, SQL, URL fetching or live-mode authority.
                    if set(raw) - {"case", "as_of_utc", "strict", "withdrawn_source_ids", "search_depth"}:
                        raise ValueError("CASE_REQUEST_FIELDS_REFUSED")
                    result = investigate_case(
                        raw["case"], as_of_utc=raw.get("as_of_utc"),
                        strict=raw.get("strict", False),
                        withdrawn_source_ids=raw.get("withdrawn_source_ids", []),
                        search_depth=raw.get("search_depth", 2))
                elif self.path == "/case-local-nightshift":
                    # This is a separate, doubly opt-in route. It accepts no
                    # URLs, provider selection, SQL, filesystem paths or client
                    # tokens. The user explicitly clicks in the UI, and the
                    # server must separately start with --enable-local-nightshift.
                    allowed = {"case", "as_of_utc", "strict", "withdrawn_source_ids",
                               "search_depth", "confirm_local_nightshift"}
                    if set(raw) - allowed or raw.get("confirm_local_nightshift") is not True:
                        raise ValueError("LOCAL_NIGHTSHIFT_OPT_IN_REQUIRED")
                    result = investigate_case(
                        raw["case"], as_of_utc=raw.get("as_of_utc"),
                        strict=raw.get("strict", False),
                        withdrawn_source_ids=raw.get("withdrawn_source_ids", []),
                        search_depth=raw.get("search_depth", 2))
                    proposal = propose_local_explanation(result)
                    result["nightshift_local_proposal"] = proposal
                    result["model_called"] = bool(proposal.get("model_called"))
                    result["nightshift_request_attempted"] = bool(
                        proposal.get("request_attempted", result["model_called"]))
                    result["model_or_sponsor_called"] = result["nightshift_request_attempted"]
                    result["execution_trace"].append({
                        "action": "CHECK_LOCAL_NIGHTSHIFT_PROPOSAL",
                        "status": proposal.get("status", "UNKNOWN"),
                        "model_called": result["model_called"],
                        "request_attempted": result["nightshift_request_attempted"],
                        "deterministic_verdict_unchanged": True,
                    })
                elif self.path == "/why-counterfactual":
                    # NO source injection, keys, providers or arbitrary clocks.
                    if (set(raw) - {"as_of_utc", "strict"}
                            or raw.get("as_of_utc") not in WHY_DEMO_CLOCKS
                            or type(raw.get("strict", False)) is not bool):
                        raise ValueError("WHY_DEMO_FIELDS_OR_CLOCK_REFUSED")
                    nhc, florida = why_offline_rows()
                    result = evaluate_source_why(
                        nhc, florida,
                        as_of_utc=raw["as_of_utc"], strict=raw.get("strict", False)
                    )
                elif self.path == "/cross-issuer":
                    # Always offline; no caller supplied source list, transport,
                    # AI provider, memory or account context is permitted.
                    if set(raw) - {"as_of_utc", "strict"}:
                        raise ValueError("CROSS_ISSUER_FIELDS_NOT_ALLOWED")
                    result = run_cross_issuer_milton(
                        raw["as_of_utc"], strict=raw.get("strict", False)
                    )
                elif self.path == "/external-milton":
                    # This endpoint NEVER executes a model, H-MEM, SQL query
                    # or Yagi coordinator watch. Reject all caller-supplied
                    # source rows and unexpected transport options.
                    if set(raw) - {"as_of_utc", "strict"}:
                        raise ValueError("EXTERNAL_REPLAY_FIELDS_NOT_ALLOWED")
                    result = run_milton_external_replay(
                        raw["as_of_utc"], strict=raw.get("strict", False)
                    )
                else:
                    # Public demo never has live sponsor authority, even if a
                    # client explicitly posts sample_mode=false.
                    raw["sample_mode"] = True
                    request = RunRequest.from_dict(raw)
                    if self.path == "/counterfactual":
                        # Pure CPU replay on shipped sample catalog, no H-MEM,
                        # external sponsor credentials or model transport.
                        minutes = raw.get("earlier_by_minutes", 15)
                        result = counterfactual_dossier(
                            request, all_catalog(), minutes_earlier=minutes
                        )
                    else:
                        result = pipeline.run(request)
            except DraftRefusal as exc:
                self._send(422, {"error": "draft_refused", "issues": exc.issues,
                                 "model_or_sponsor_called": False})
                return
            except (ValueError, UnicodeError, KeyError, TypeError) as exc:
                self._send(400, {"error": "invalid_request",
                                 "exception_type": type(exc).__name__})
                return
            except Exception as exc:
                self._send(500, {"error": "pipeline_failure",
                                 "exception_type": type(exc).__name__})
                return
            self._send(
                200,
                result if self.path in ("/counterfactual", "/external-milton", "/cross-issuer", "/why-counterfactual", "/case-investigation", "/case-local-nightshift", "/case-draft", "/case-evidence")
                else result.to_dict(),
            )

        def log_message(self, fmt: str, *args) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str, port: int, *, enable_local_nightshift: bool = False) -> None:
    httpd = create_local_server(host, port, enable_local_nightshift=enable_local_nightshift)
    print(f"evidencetrail LOCAL OFFLINE demo http://{host}:{port}/demo", flush=True)
    httpd.serve_forever()
