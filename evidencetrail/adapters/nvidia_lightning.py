"""Single-model, direct NVIDIA Lightning trial; separate from existing Super-VL.

A REAL result requires NVIDIA's pinned HTTPS endpoint, expected model ID,
successful final chat completion and externally obtained Zetaris data.
Injected test transports are *never* considered a real NVIDIA completion.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Callable

ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
MAX_REPLY_BYTES = 131072
TIMEOUT_SECONDS = 65


class NvidiaLightningError(Exception):
    """Non-secret contract failure code only."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        return None


def official_transport(req: urllib.request.Request) -> tuple[int, bytes]:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()
    )
    with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
        return int(response.status), response.read(MAX_REPLY_BYTES + 1)


def _parse_output(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or len(raw) > MAX_REPLY_BYTES:
        raise NvidiaLightningError("RESPONSE_BYTES_INVALID")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise NvidiaLightningError("RESPONSE_JSON_INVALID") from None
    if not isinstance(obj, dict):
        raise NvidiaLightningError("RESPONSE_OBJECT_REQUIRED")
    if obj.get("model") != MODEL:
        raise NvidiaLightningError("RESPONSE_MODEL_IDENTITY_MISMATCH")
    rid = obj.get("id")
    if not isinstance(rid, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{6,160}", rid):
        raise NvidiaLightningError("RESPONSE_REQUEST_ID_INVALID")
    options = obj.get("choices")
    if not isinstance(options, list) or len(options) != 1:
        raise NvidiaLightningError("RESPONSE_CHOICES_INVALID")
    item = options[0]
    if not isinstance(item, dict) or item.get("finish_reason") != "stop":
        raise NvidiaLightningError("RESPONSE_NOT_COMPLETE")
    message = item.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise NvidiaLightningError("RESPONSE_MESSAGE_ROLE_INVALID")
    body = message.get("content")
    if not isinstance(body, str) or not 2 <= len(body) <= 12000:
        raise NvidiaLightningError("RESPONSE_CONTENT_INVALID")
    try:
        proposal = json.loads(body)
    except ValueError:
        raise NvidiaLightningError("MODEL_OUTPUT_NOT_STRICT_JSON") from None
    if not isinstance(proposal, dict) or set(proposal) != {
        "latest_nhc_mph", "florida_emergency_counties", "source_ids",
        "historical_first_publication_authenticated", "rationale"
    }:
        raise NvidiaLightningError("MODEL_OUTPUT_KEYS_INVALID")
    ids = proposal["source_ids"]
    if (not isinstance(ids, list) or len(ids) > 7
            or any(not isinstance(x, str) for x in ids)):
        raise NvidiaLightningError("MODEL_CITATION_SHAPE_INVALID")
    if (not isinstance(proposal["rationale"], str)
            or not proposal["rationale"].strip()
            or len(proposal["rationale"]) > 1600):
        raise NvidiaLightningError("MODEL_RATIONALE_INVALID")
    usage = obj.get("usage")
    numbers = None
    if isinstance(usage, dict):
        names = ("prompt_tokens", "completion_tokens", "total_tokens")
        if all(type(usage.get(k)) is int and 0 <= usage[k] <= 100000 for k in names):
            numbers = {k: usage[k] for k in names}
    return {
        "response_id_sha12": hashlib.sha256(rid.encode()).hexdigest()[:12],
        "returned_model": obj["model"],
        "content_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "usage": numbers,
        "proposal": proposal,
    }


def _source_bound_input(truth: dict, selected_rows: list[dict]) -> list[dict]:
    """Recheck every SQL-returned field at the provider boundary.

    Do not rely only on the presence of a matching source ID: an attacker can
    swap a numeric value, issue time, URL, issuer or excerpt AFTER the SQL
    filter but BEFORE a model prompt is constructed.
    """
    from evidencetrail.external_milton import _load as nhc_catalog
    from evidencetrail.cross_issuer_milton import _fl_metadata
    from evidencetrail.zetaris_cross_issuer import _sql_int, _sql_issue_clock

    _, nhc = nhc_catalog()
    _, florida = _fl_metadata()
    expected = {}
    for record in nhc:
        expected[record.source_id] = {
            "issuer_family": "NOAA_NHC",
            "locator": record.locator,
            "claim_type": "maximum_sustained_wind_mph",
            "value": record.observation_fields["reported_maximum_sustained_wind_mph"],
            "issue_utc": record.issued_at_claimed_utc,
            "displayed_local_date": None,
            "excerpt_sha256": hashlib.sha256(record.excerpt.encode("utf8")).hexdigest(),
        }
    for record in florida:
        expected[record["id"]] = {
            "issuer_family": "FLORIDA_GOVERNOR",
            "locator": record["url"],
            "claim_type": record["claim_type"],
            "value": record["value"],
            "issue_utc": None,
            "displayed_local_date": record["displayed_date_local"],
            "excerpt_sha256": hashlib.sha256(record["description"].encode("utf8")).hexdigest(),
        }
    result = []
    for row in selected_rows:
        if not isinstance(row, dict):
            raise NvidiaLightningError("SELECTED_SQL_ROW_NOT_OBJECT")
        spec = expected.get(row.get("source_id"))
        if spec is None:
            raise NvidiaLightningError("SELECTED_SQL_ORIGIN_NOT_ALLOWLISTED")
        excerpt = row.get("excerpt")
        if not isinstance(excerpt, str) or len(excerpt) > 3000:
            raise NvidiaLightningError("SELECTED_SQL_EXCERPT_UNTRUSTED")
        if (row.get("excerpt_sha256") != spec["excerpt_sha256"]
                or hashlib.sha256(excerpt.encode("utf8")).hexdigest()
                   != spec["excerpt_sha256"]):
            raise NvidiaLightningError("SELECTED_SQL_EXCERPT_DIGEST_REFUSED")
        try:
            number = _sql_int(row.get("value_int"))
            instant = _sql_issue_clock(row.get("issue_utc"))
        except (ValueError, TypeError) as exc:
            raise NvidiaLightningError("SELECTED_SQL_TYPES_REFUSED") from None
        if (row.get("issuer_family") != spec["issuer_family"]
                or row.get("locator") != spec["locator"]
                or row.get("claim_type") != spec["claim_type"]
                or number != spec["value"]
                or instant != spec["issue_utc"]
                or row.get("displayed_date_local") != spec["displayed_local_date"]):
            raise NvidiaLightningError("SELECTED_SQL_SOURCE_BINDING_REFUSED")
        result.append({
            "source_id": row["source_id"],
            "issuer_family": spec["issuer_family"],
            "claim_type": spec["claim_type"],
            "value": number,
            "official_reference": spec["locator"],
            "claimed_issue_utc": (
                spec["issue_utc"].isoformat().replace("+00:00", "Z")
                if spec["issue_utc"] else None),
            "displayed_local_date": spec["displayed_local_date"],
            "first_public_availability_authenticated": False,
        })
    return result


def _narrative_risk_flags(rationale: str) -> list[str]:
    """Bounded adversarial hints, NOT a semantic entailment classifier."""
    flags = []
    if re.search(r"\b(authenticated|independently verified|certified|validated original)\b",
                 rationale, re.IGNORECASE):
        flags.append("AMBIGUOUS_AUTHENTICATION_ASSERTION")
    if re.search(r"\b(first published at|first posted at|proven public|verified publication)\b",
                 rationale, re.IGNORECASE):
        flags.append("UNSUPPORTED_FIRST_PUBLICATION_ASSERTION")
    if re.search(r"\b(must evacuate|safe to stay|no evacuation needed|will make landfall)\b",
                 rationale, re.IGNORECASE):
        flags.append("UNSUPPORTED_OPERATIONAL_RECOMMENDATION")
    return flags


def _verified_explanation(truth: dict) -> dict:
    """Trusted final narrative rendered exclusively from typed, checked data.

    This establishes a bounded *claim template*, not semantic validation of
    any arbitrary natural-language assertion returned by an LLM.
    """
    claim_nhc = {
        "claim_id": "NHC_LATEST_REPORTED_WIND",
        "source_id": "NHC-AL142024-PUBLIC-008",
        "issuer": "NOAA/National Hurricane Center",
        "value": truth["latest_noaa_wind_mph"],
        "unit": "mph",
        "issue_clock": "2024-10-07T09:00:00Z",
        "clock_kind": "CLAIMED_BULLETIN_ISSUE_UTC",
        "first_publication_authenticated": False,
    }
    claim_florida = {
        "claim_id": "FLORIDA_GOVERNOR_EMERGENCY_COUNTIES",
        "source_id": "FL-EO-24-215",
        "issuer": "Florida Executive Office of the Governor",
        "value": truth["latest_florida_emergency_counties"],
        "unit": "counties_under_emergency_order",
        "displayed_date_local": "2024-10-06",
        "clock_kind": "DISPLAYED_LOCAL_CALENDAR_DATE_ONLY",
        "first_publication_authenticated": False,
    }
    return {
        "as_of_utc": truth["as_of_utc"],
        "typed_claims": [claim_nhc, claim_florida],
        "explanation": (
            "At 2024-10-07 11:00 UTC, the admitted NOAA/NHC advisory #8 "
            "has a claimed issue clock of 09:00 UTC and reports "
            + str(claim_nhc["value"]) + " mph ("
            + claim_nhc["source_id"] + "). A conservatively admitted Florida "
            "Governor emergency order dated 2024-10-06 lists "
            + str(claim_florida["value"]) + " counties ("
            + claim_florida["source_id"] + "). Florida's date does not "
            "establish a publication hour. Neither original page's first "
            "public availability in 2024 is independently authenticated. "
            "These are historical curated-source claims, NOT an emergency "
            "warning or weather prediction."
        ),
        "derived_without_model_free_text": True,
        "arbitrary_llm_narrative_entailment_proven": False,
        "independent_analyst_validation": False,
    }


def check_grounding(parsed: dict, truth: dict) -> dict:
    p = parsed["proposal"]
    eligible = set(truth["selected_original_ids"])
    ids = p["source_ids"]
    grounded = (
        type(p["latest_nhc_mph"]) is int
        and p["latest_nhc_mph"] == truth["latest_noaa_wind_mph"]
        and type(p["florida_emergency_counties"]) is int
        and p["florida_emergency_counties"] == truth["latest_florida_emergency_counties"]
        and p["historical_first_publication_authenticated"] is False
        and len(ids) == len(set(ids))
        and set(ids).issubset(eligible)
        and {"NHC-AL142024-PUBLIC-008", "FL-EO-24-215"}.issubset(set(ids))
    )
    flags = _narrative_risk_flags(p["rationale"])
    return {
        "grounded_against_sql_selection": grounded,
        "numeric_and_citation_contract_passed": grounded,
        "model_rationale_is_authoritatively_verified": False,
        "model_rationale_exposed_as_trusted_explanation": False,
        "model_rationale_sha256": hashlib.sha256(
            p["rationale"].encode("utf8")).hexdigest(),
        "model_rationale_risk_flags": flags,
        "semantic_entailment_of_arbitrary_model_text_proven": False,
        "source_ids_reported": ids,
        "exact_issue_clock_and_value_check": (
            type(p["latest_nhc_mph"]) is int
            and type(p["florida_emergency_counties"]) is int
            and p["latest_nhc_mph"] == truth["latest_noaa_wind_mph"]
            and p["florida_emergency_counties"] == truth["latest_florida_emergency_counties"]
        ),
        "first_publication_overclaim": p[
            "historical_first_publication_authenticated"
        ] is not False,
        "source_bound_rendering": _verified_explanation(truth) if grounded else None,
    }


def chat_public_evidence(
    *, key: str, truth: dict, selected_rows: list[dict],
    transport: Callable[[urllib.request.Request], tuple[int, bytes]] | None = None,
) -> dict:
    if not isinstance(key, str) or not 12 <= len(key) <= 512 or re.search(r"\s", key):
        raise NvidiaLightningError("NVIDIA_KEY_ABSENT_OR_MALFORMED")
    if (truth.get("as_of_utc") != "2024-10-07T11:00:00Z"
            or truth.get("sql_decoded_issuer_row_counts") != {
                "NOAA_NHC": 4, "FLORIDA_GOVERNOR": 3
            } or not truth.get("source_data_was_supplied_by_sql_query_arguments")
            or truth.get("original_2024_first_publication_authenticated") is not False):
        raise NvidiaLightningError("REQUIRED_REAL_SQL_TRUTH_NOT_ESTABLISHED")
    ids = truth.get("selected_original_ids", [])
    if (not isinstance(ids, list) or len(ids) != 3
            or len(selected_rows) != 3
            or set(x["source_id"] for x in selected_rows) != set(ids)):
        raise NvidiaLightningError("SOURCE_SELECTION_MISMATCH")
    facts = _source_bound_input(truth, selected_rows)
    brief = {
        "as_of_utc": truth["as_of_utc"],
        "reported_date_replay_not_original_publisher_availability_proof": True,
        "source_rows_selected_by_real_authenticated_zetaris_sql": facts,
        "facts_to_separate": ["NOAA reported wind in mph",
                              "Florida Governor legal emergency order county count"],
        "not_a_weather_forecast_or_operational_warning": True,
    }
    prompt = (
        "Retrospective evidence audit, NOT an emergency forecast. Answer strictly "
        "from selected source metadata below. NOAA claims have exact issue UTC "
        "clocks; Florida Governor has a date only. The Florida Oct 6 document "
        "is admitted conservatively only after that local EDT date fully ends. "
        "Neither proves when an original 2024 web page first went public. "
        "Never invent later NHC notices or independent third-party agreement. "
        "Return exactly one valid JSON object with keys latest_nhc_mph "
        "(integer), florida_emergency_counties (integer), source_ids "
        "(an array of evidence IDs, include the pivotal NOAA and Florida IDs), "
        "historical_first_publication_authenticated (boolean false), rationale "
        "(one concise sentence). No markdown fences.\n"
        + json.dumps(brief, separators=(",", ":"), ensure_ascii=False)
    )
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content":
             "You are an evidence-bound assistant. Never assert a publisher's "
             "original historical first availability without proof. JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 750,
        "chat_template_kwargs": {"enable_thinking": False},
        "stream": False,
    }, separators=(",", ":"), ensure_ascii=False).encode("utf8")
    req = urllib.request.Request(
        ENDPOINT, data=payload, method="POST",
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "EvidenceTrail-Verified-Public-Research/1"}
    )
    mocked = transport is not None
    if transport is None:
        transport = official_transport
    try:
        status, raw = transport(req)
    except urllib.error.HTTPError as err:
        code = err.code
        err.close()
        raise NvidiaLightningError("NVIDIA_HTTP_" + str(code)) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise NvidiaLightningError("NVIDIA_TRANSPORT_UNAVAILABLE") from None
    if status != 200:
        raise NvidiaLightningError("NVIDIA_HTTP_" + str(status))
    result = _parse_output(raw)
    audit = check_grounding(result, truth)
    return {
        "status": "INJECTED_CONTRACT_ONLY" if mocked else (
            "REAL_NVIDIA_SQL_CLAIMS_BOUNDED" if audit["grounded_against_sql_selection"]
            else "REAL_NVIDIA_RESPONSE_NOT_GROUNDED"
        ),
        "real_nvidia_network_called": not mocked,
        "injected_transport": mocked,
        "endpoint": ENDPOINT,
        "requested_model": MODEL,
        "returned_model": result["returned_model"],
        "response_id_sha12": result["response_id_sha12"],
        "content_sha256": result["content_sha256"],
        "usage": result["usage"],
        "source_selection": ids,
        "grounding": audit,
        "trusted_explanation": audit["source_bound_rendering"],
        "model_rationale_quarantined": True,
        "semantic_entailment_verification": "NOT_PROVEN_FREE_TEXT_NOT_TRUSTED",
        "organizer_sponsor_eligibility_certified": False,
        "original_2024_first_publication_authenticated": False,
        "weather_prediction_accuracy_measured": False,
    }
