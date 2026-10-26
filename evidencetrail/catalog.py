"""Cached 2024 government-news paraphrases + synthetic capacity.

No full article HTML. URLs are attribution pointers. Displayed datelines are
NOT authenticated first-availability proofs.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from evidencetrail.models import ProvenanceQuality, RecordKind, SourceRecord

def ict(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    from datetime import timedelta, timezone as tz

    return datetime(y, m, d, hh, mm, tzinfo=tz(timedelta(hours=7))).astimezone(timezone.utc)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def government_sources() -> list[SourceRecord]:
    """Structured paraphrases of displayed 2024 government-news datelines."""
    s1530_excerpt = (
        "Government news displayed 2024-09-08 15:30 ICT reports NCHMF issued a "
        "14:30 bulletin of flash-flood/landslide risk in the next 6 hours across "
        "18 localities including Yen Bai and Lao Cai (level-2 tier). URL slug "
        "contains 16-tinh while displayed body says 18 localities. "
        "Not a site-level forecast."
    )
    s1621_excerpt = (
        "Government news displayed 2024-09-08 16:21 ICT describes very high "
        "flash-flood/landslide concern for historical Yen Bai with reported "
        "antecedent rainfall/damage. Past observations relative to earlier clocks."
    )
    s1637_excerpt = (
        "Government news displayed 2024-09-08 16:37 ICT reports 15:00 ICT river-gauge "
        "observations (Song Thao at Yen Bai 31.40m, 0.40m over BD2; Ngoi Thia 45.98m, "
        "0.48m over BD2), 6-12 hour flood outlook, and named 2024 Yen Bai districts/"
        "towns at elevated flash-flood/landslide risk plus Level-2 provincial flood "
        "danger. Observation time is not publication time. URL id digits are not "
        "publication proof."
    )
    s1540_excerpt = (
        "Government news displayed 2024-09-09 15:40 ICT reports Lao Cai provincial "
        "emergency decision 2285/QD-UBND covering Van Ban, Bat Xat and Sa Pa. This is "
        "an observed administrative action, not a Sep8 forecast."
    )
    s0700_excerpt = (
        "Government news from 2024-09-07 07:19 ICT reports regional heavy rain with "
        "flash-flood and landslide risk. Public-context background only."
    )

    districts_1637 = [
        "yen bai city",
        "nghia lo",
        "luc yen",
        "van yen",
        "mu cang chai",
        "tran yen",
        "tram tau",
        "van chan",
        "yen binh",
    ]

    return [
        SourceRecord(
            source_id="GOV-2024-09-07-0719",
            record_kind=RecordKind.GOVERNMENT_NEWS,
            locator="https://baochinhphu.vn/ (see research doc 19; Sep7 regional rain bulletin)",
            publisher="baochinhphu.vn",
            paraphrase="Sep7 regional rain/flash-flood context.",
            excerpt=s0700_excerpt,
            excerpt_sha256=sha(s0700_excerpt),
            published_at_displayed_utc=ict(2024, 9, 7, 7, 19),
            observed_at_utc=None,
            issued_at_claimed_utc=None,
            first_availability_proven_utc=None,
            retrieved_at_utc=ict(2026, 10, 21, 15, 0),
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            historical_admin_vintage="2024",
            spatial_scope=["national", "yen bai", "lao cai"],
            named_districts_2024=[],
            granularity="region",
        ),
        SourceRecord(
            source_id="GOV-2024-09-08-1530",
            record_kind=RecordKind.GOVERNMENT_NEWS,
            locator="https://baochinhphu.vn/canh-bao-16-tinh-co-nguy-co-lu-quet-sat-lo-dat-da-trong-6-gio-toi-102240908152851068.htm",
            publisher="baochinhphu.vn",
            paraphrase="National 6-hour flash-flood/landslide bulletin report.",
            excerpt=s1530_excerpt,
            excerpt_sha256=sha(s1530_excerpt),
            published_at_displayed_utc=ict(2024, 9, 8, 15, 30),
            observed_at_utc=None,
            issued_at_claimed_utc=ict(2024, 9, 8, 14, 30),
            first_availability_proven_utc=None,
            retrieved_at_utc=ict(2026, 10, 22, 5, 50),
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            historical_admin_vintage="2024",
            spatial_scope=["national", "yen bai", "lao cai"],
            named_districts_2024=[],
            granularity="province",
            metadata_conflicts=["SOURCE_METADATA_CONFLICT:url_slug_16-tinh_vs_displayed_18_localities"],
        ),
        SourceRecord(
            source_id="GOV-2024-09-08-1621",
            record_kind=RecordKind.GOVERNMENT_NEWS,
            locator="https://baochinhphu.vn/canh-bao-lu-quet-va-sat-lo-dat-tai-yen-bai-102240908160432222.htm",
            publisher="baochinhphu.vn",
            paraphrase="Yen Bai provincial risk article.",
            excerpt=s1621_excerpt,
            excerpt_sha256=sha(s1621_excerpt),
            published_at_displayed_utc=ict(2024, 9, 8, 16, 21),
            observed_at_utc=None,
            issued_at_claimed_utc=None,
            first_availability_proven_utc=None,
            retrieved_at_utc=ict(2026, 10, 21, 16, 0),
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            historical_admin_vintage="2024",
            spatial_scope=["yen bai"],
            named_districts_2024=[],
            granularity="province",
        ),
        SourceRecord(
            source_id="GOV-2024-09-08-1637",
            record_kind=RecordKind.GOVERNMENT_NEWS,
            locator="https://baochinhphu.vn/tang-so-nguoi-bi-thuong-do-bao-yagi-102240908163127919.htm",
            publisher="baochinhphu.vn",
            paraphrase="District-named Yen Bai risk plus 15:00 gauge observations published at 16:37.",
            excerpt=s1637_excerpt,
            excerpt_sha256=sha(s1637_excerpt),
            published_at_displayed_utc=ict(2024, 9, 8, 16, 37),
            observed_at_utc=ict(2024, 9, 8, 15, 0),
            issued_at_claimed_utc=None,
            first_availability_proven_utc=None,
            retrieved_at_utc=ict(2026, 10, 22, 5, 50),
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            historical_admin_vintage="2024",
            spatial_scope=["yen bai"],
            named_districts_2024=districts_1637,
            granularity="district",
            metadata_conflicts=["SOURCE_METADATA_CONFLICT:url_id_looks_like_1631_displayed_1637"],
            observation_fields={
                "song_thao_yen_bai_m": 31.40,
                "ngoi_thia_m": 45.98,
                "observation_clock_ict": "2024-09-08T15:00:00+07:00",
                "publication_clock_ict": "2024-09-08T16:37:00+07:00",
            },
        ),
        SourceRecord(
            source_id="GOV-2024-09-09-1540",
            record_kind=RecordKind.GOVERNMENT_NEWS,
            locator="https://baochinhphu.vn/cong-bo-tinh-huong-khan-cap-ve-thien-tai-tren-dia-ban-tinh-lao-cai-102240909151615948.htm",
            publisher="baochinhphu.vn",
            paraphrase="Lao Cai 2024 emergency action, not a Yen Bai forecast.",
            excerpt=s1540_excerpt,
            excerpt_sha256=sha(s1540_excerpt),
            published_at_displayed_utc=ict(2024, 9, 9, 15, 40),
            observed_at_utc=ict(2024, 9, 9, 8, 0),
            issued_at_claimed_utc=None,
            first_availability_proven_utc=None,
            retrieved_at_utc=ict(2026, 10, 21, 16, 0),
            provenance_quality=ProvenanceQuality.ORIGINAL_ARTICLE_DISPLAYED_DATELINE_EDIT_HISTORY_UNKNOWN,
            historical_admin_vintage="2024",
            spatial_scope=["lao cai"],
            named_districts_2024=["van ban", "bat xat", "sa pa"],
            granularity="district",
        ),
        SourceRecord(
            source_id="HINDCAST-ECMWF-49R1-SEP2024",
            record_kind=RecordKind.RETROSPECTIVE_HINDCAST,
            locator="https://open-meteo.com/en/docs/historical-forecast-api",
            publisher="open-meteo/ecmwf-later-cycle",
            paraphrase="ECMWF IFS 49r1 became operational 2024-11-12; Sep 2024 archive values are hindcasts.",
            excerpt="RETROSPECTIVE_2026_HINDCAST must not score as operational 2024 forecast.",
            excerpt_sha256=sha("RETROSPECTIVE_2026_HINDCAST must not score as operational 2024 forecast."),
            published_at_displayed_utc=ict(2026, 10, 20, 12, 0),
            observed_at_utc=None,
            issued_at_claimed_utc=None,
            first_availability_proven_utc=None,
            retrieved_at_utc=ict(2026, 10, 20, 12, 0),
            provenance_quality=ProvenanceQuality.RETROSPECTIVE_2026_HINDCAST,
            historical_admin_vintage="n/a",
            spatial_scope=["national"],
            named_districts_2024=[],
            granularity="grid",
        ),
        SourceRecord(
            source_id="ARCHIVE-PCTT-LAOCAI-YENBAI-2024-MIGRATION",
            record_kind=RecordKind.IMPORTED_ARCHIVE,
            locator="https://pctt.laocai.gov.vn/",
            publisher="pctt.laocai.gov.vn",
            paraphrase="2026 Lao Cai portal hosts a Yen Bai 2024-dated bulletin; first 2024 page availability unproven.",
            excerpt="Do not treat 2026-hosted archive dateline as 2024 page availability or relabel 2024 Yen Bai as 2026 Lao Cai.",
            excerpt_sha256=sha(
                "Do not treat 2026-hosted archive dateline as 2024 page availability or relabel 2024 Yen Bai as 2026 Lao Cai."
            ),
            published_at_displayed_utc=ict(2024, 9, 8, 11, 55),
            observed_at_utc=None,
            issued_at_claimed_utc=None,
            first_availability_proven_utc=None,
            retrieved_at_utc=ict(2026, 10, 21, 16, 0),
            provenance_quality=ProvenanceQuality.IMPORTED_2024_DATELINE_ON_2026_PORTAL,
            historical_admin_vintage="2024-yen-bai-on-2026-lao-cai-portal",
            spatial_scope=["yen bai"],
            named_districts_2024=[],
            granularity="province",
        ),
    ]


def synthetic_capacity() -> list[SourceRecord]:
    excerpt = (
        "SYNTHETIC what-if capacity for scenario yagi-replay-alpha: fictional "
        "coordinator watch roster sized for Luc Yen 2024. Not a real 2024 shelter, "
        "hospital, or evacuation order."
    )
    return [
        SourceRecord(
            source_id="SYN-CAP-YAGI-ALPHA-LUCYEN",
            record_kind=RecordKind.SYNTHETIC_CAPACITY,
            locator="evidencetrail://synthetic/yagi-replay-alpha/luc-yen",
            publisher="EvidenceTrail synthetic fixture",
            paraphrase="Fictional coordinator watch capacity bound to scenario yagi-replay-alpha.",
            excerpt=excerpt,
            excerpt_sha256=sha(excerpt),
            published_at_displayed_utc=ict(2024, 9, 1, 0, 0),
            observed_at_utc=None,
            issued_at_claimed_utc=None,
            first_availability_proven_utc=ict(2024, 9, 1, 0, 0),
            retrieved_at_utc=ict(2026, 10, 22, 7, 0),
            provenance_quality=ProvenanceQuality.SYNTHETIC,
            historical_admin_vintage="2024",
            spatial_scope=["yen bai"],
            named_districts_2024=["luc yen"],
            granularity="district",
            scenario_id="yagi-replay-alpha",
            plan_predicates={
                "coordinator_watch_authorized": True,
                "named_district_matches": True,
                "site_population_verified": False,
                "route_safety_verified": False,
                "original_2024_bytes_authenticated": False,
            },
        )
    ]


def all_catalog() -> list[SourceRecord]:
    return government_sources() + synthetic_capacity()


def by_id(source_id: str, catalog: list[SourceRecord] | None = None) -> SourceRecord | None:
    catalog = catalog or all_catalog()
    for row in catalog:
        if row.source_id == source_id:
            return row
    return None
