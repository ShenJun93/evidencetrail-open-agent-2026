"""Temporal semantics for short-lived hazard bulletins.

An authenticated archive capture can establish that a warning text *existed*
by a given time. It does NOT establish when the warning was issued or
whether its "next N hours" risk window remains active during a later replay.
Separate historical existence from active risk, fail closed on uncertainty.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def assess_time_limited_warning(
    *,
    archived_at_utc: datetime,
    as_of_utc: datetime,
    max_forecast_hours: int,
    issued_at_independently_verified_utc: datetime | None = None,
) -> dict[str, str | bool | None]:
    """Return source-existence and active-warning status without guessing.

    issued_at_independently_verified_utc MUST be independently authenticated,
    not the clock shown on the article or inferred from the URL/Wayback crawl.
    With no proven issuance, a 6h bulletin archived on day one cannot be
    treated as active at any later date; capture+6h is only a generous UPPER
    bound on possible expiry. If the as-of is inside that bound, active risk
    remains UNPROVEN rather than a false positive.
    """
    for label, dt in (
        ("archived_at_utc", archived_at_utc),
        ("as_of_utc", as_of_utc),
        ("issued_at_independently_verified_utc", issued_at_independently_verified_utc),
    ):
        if dt is not None and (not isinstance(dt, datetime) or dt.tzinfo is None
                            or dt.utcoffset() is None):
            raise ValueError(f"{label}_must_be_timezone_aware")
    if type(max_forecast_hours) is not int or not 1 <= max_forecast_hours <= 72:
        raise ValueError("bounded_positive_forecast_horizon_required")

    captured = archived_at_utc.astimezone(timezone.utc)
    as_of = as_of_utc.astimezone(timezone.utc)
    issued = (
        issued_at_independently_verified_utc.astimezone(timezone.utc)
        if issued_at_independently_verified_utc is not None else None
    )
    horizon = timedelta(hours=max_forecast_hours)
    if issued is not None and issued > captured:
        raise ValueError("verified_issue_after_archive_capture_is_contradictory")
    latest_possible_expiry = (issued if issued is not None else captured) + horizon

    if as_of < captured:
        state = "ARCHIVE_NOT_YET_AVAILABLE"
    elif as_of > latest_possible_expiry:
        state = "WARNING_EXPIRED_BY_PROVEN_UPPER_BOUND"
    elif issued is None:
        state = "WARNING_MAY_BE_ACTIVE_BUT_ISSUANCE_UNVERIFIED"
    elif as_of < issued:
        state = "ISSUANCE_AFTER_AS_OF"
    else:
        state = "WARNING_ACTIVE_WITH_INDEPENDENT_ISSUANCE_PROOF"
    return {
        "state": state,
        "archive_body_available_by_asof": as_of >= captured,
        "risk_warning_verified_active": state == "WARNING_ACTIVE_WITH_INDEPENDENT_ISSUANCE_PROOF",
        "archive_capture_utc": captured.isoformat().replace("+00:00", "Z"),
        "independently_verified_issue_utc": (
            issued.isoformat().replace("+00:00", "Z") if issued is not None else None
        ),
        "latest_possible_expiry_utc": (
            latest_possible_expiry.isoformat().replace("+00:00", "Z")
        ),
        "forecast_horizon_hours": str(max_forecast_hours),
        "notice": (
            "An archive proves a text was captured; a finite forecast horizon "
            "does not prove continued risk or exact original issuance."
        ),
    }
