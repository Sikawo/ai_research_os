"""JSON-safe data models shared by Career Job Agent deployments.

The framework intentionally keeps these models schema-light.  Deployments may
add fields without forcing a migration by placing them in ``extra`` (unknown
keys passed to :meth:`from_dict` are preserved there automatically).
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field, fields, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, ClassVar, Mapping, TypeVar


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp suitable for durable state."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> JsonValue:
    """Recursively convert supported values into JSON-serializable values."""

    if isinstance(value, Enum):
        return json_safe(value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return json_safe(value.to_dict())
    if is_dataclass(value):
        return {
            item.name: json_safe(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable")


T = TypeVar("T", bound="JsonModel")


@dataclass
class JsonModel:
    """Mixin providing tolerant dictionary round-tripping.

    Unknown input keys are retained in ``extra``.  They are flattened back to
    their original top-level positions by :meth:`to_dict`, which lets older
    deployments consume newer records without discarding data.
    """

    extra: dict[str, Any] = dataclass_field(default_factory=dict, kw_only=True, repr=False)

    _ALIASES: ClassVar[Mapping[str, str]] = {}

    @classmethod
    def from_dict(cls: type[T], data: Mapping[str, Any]) -> T:
        if not isinstance(data, Mapping):
            raise TypeError(f"{cls.__name__}.from_dict expects a mapping")
        field_names = {item.name for item in fields(cls)}
        kwargs: dict[str, Any] = {}
        extras: dict[str, Any] = {}
        supplied_extra = data.get("extra")
        if isinstance(supplied_extra, Mapping):
            extras.update(supplied_extra)
        for raw_key, value in data.items():
            if raw_key == "extra":
                continue
            key = cls._ALIASES.get(raw_key, raw_key)
            if key in field_names:
                kwargs[key] = value
            else:
                extras[raw_key] = value
        if "extra" in field_names:
            kwargs["extra"] = extras
        return cls(**kwargs)

    def to_dict(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for item in fields(self):
            if item.name == "extra":
                continue
            result[item.name] = json_safe(getattr(self, item.name))
        for key, value in self.extra.items():
            if key not in result:
                result[key] = json_safe(value)
        return result


class SourceClass(str, Enum):
    GENERAL_ACADEMIC_AGGREGATOR = "GENERAL_ACADEMIC_AGGREGATOR"
    SCIENCE_JOB_BOARD = "SCIENCE_JOB_BOARD"
    REGIONAL_ACADEMIC_PORTAL = "REGIONAL_ACADEMIC_PORTAL"
    SCIENTIFIC_SOCIETY = "SCIENTIFIC_SOCIETY"
    INSTITUTION_DIRECT = "INSTITUTION_DIRECT"
    EMAIL_ALERT = "EMAIL_ALERT"
    SEARCH_ENGINE_DISCOVERY = "SEARCH_ENGINE_DISCOVERY"
    MANUAL = "MANUAL"
    EMPLOYER_DIRECT = "EMPLOYER_DIRECT"
    OTHER = "OTHER"


class SourceAuthority(IntEnum):
    """Default authority ordering; larger values are more authoritative."""

    DISCOVERY_ONLY = 10
    TRUSTED_AGGREGATOR = 30
    OFFICIAL_DEPARTMENT = 70
    OFFICIAL_ATS = 90
    OFFICIAL_DETAIL = 100


class VerificationStatus(str, Enum):
    VERIFIED_OPEN = "verified_open"
    VERIFIED_CLOSED = "verified_closed"
    VERIFIED_EXPIRED = "verified_expired"
    VERIFIED_REOPENED = "verified_reopened"
    VERIFICATION_PENDING = "verification_pending"
    VERIFICATION_FAILED_TRANSIENT = "verification_failed_transient"
    VERIFICATION_FAILED_PERSISTENT = "verification_failed_persistent"
    OFFICIAL_SOURCE_NOT_FOUND = "official_source_not_found"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    UNKNOWN = "unknown"

    @property
    def is_open(self) -> bool:
        return self in {self.VERIFIED_OPEN, self.VERIFIED_REOPENED}

    @property
    def is_definitive(self) -> bool:
        return self in {
            self.VERIFIED_OPEN,
            self.VERIFIED_CLOSED,
            self.VERIFIED_EXPIRED,
            self.VERIFIED_REOPENED,
        }

    @property
    def is_transient(self) -> bool:
        return self in {
            self.VERIFICATION_PENDING,
            self.VERIFICATION_FAILED_TRANSIENT,
        }


@dataclass
class SourceRecord(JsonModel):
    id: str = ""
    source_class: SourceClass | str = SourceClass.OTHER
    name: str | None = None
    regions: list[str] = dataclass_field(default_factory=list)
    url: str | None = None
    supports_email_alerts: bool = False
    supports_direct_search: bool = False
    supports_rss: bool = False
    feed_urls: list[str] = dataclass_field(default_factory=list)
    bootstrap_url: str | None = None
    alert_delivery_state: str | None = None
    official_source: bool = False
    enabled: bool = True
    priority: int = 0
    authority: SourceAuthority | int = SourceAuthority.DISCOVERY_ONLY
    cadence: str | None = None
    parser_version: str | None = None

    _ALIASES: ClassVar[Mapping[str, str]] = {"class": "source_class"}

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("SourceRecord.id must be non-empty")
        try:
            self.source_class = SourceClass(self.source_class)
        except ValueError:
            self.source_class = SourceClass.OTHER
        try:
            self.authority = SourceAuthority(self.authority)
        except ValueError:
            self.authority = int(self.authority)
        self.regions = [str(region) for region in self.regions]
        self.feed_urls = [str(url) for url in self.feed_urls]


@dataclass
class VerificationResult(JsonModel):
    status: VerificationStatus | str = VerificationStatus.UNKNOWN
    checked_at: str = dataclass_field(default_factory=utc_now)
    source_url: str | None = None
    source_id: str | None = None
    authority: SourceAuthority | int = SourceAuthority.DISCOVERY_ONLY
    corroborated: bool = False
    corroborating_sources: list[str] = dataclass_field(default_factory=list)
    confidence: float | None = None
    evidence: list[str] = dataclass_field(default_factory=list)
    verified_fields: dict[str, Any] = dataclass_field(default_factory=dict)
    error: str | None = None

    def __post_init__(self) -> None:
        try:
            self.status = VerificationStatus(self.status)
        except ValueError as exc:
            raise ValueError(f"Unknown verification status: {self.status!r}") from exc
        try:
            self.authority = SourceAuthority(self.authority)
        except ValueError:
            self.authority = int(self.authority)
        if not isinstance(self.corroborated, bool):
            raise ValueError("corroborated must be a boolean")
        raw_corroborating_sources = (
            []
            if self.corroborating_sources is None
            else [self.corroborating_sources]
            if isinstance(self.corroborating_sources, str)
            else self.corroborating_sources
        )
        self.corroborating_sources = [
            str(source).strip()
            for source in raw_corroborating_sources
            if str(source).strip()
        ]
        if self.confidence is not None and not 0 <= float(self.confidence) <= 1:
            raise ValueError("Verification confidence must be between 0 and 1")

    @property
    def is_definitive(self) -> bool:
        return self.status.is_definitive

    @property
    def is_transient(self) -> bool:
        return self.status.is_transient


@dataclass
class JobRecord(JsonModel):
    """Canonical generic job record used by industry and academic deployments."""

    canonical_id: str | None = None
    title: str = ""
    company: str | None = None
    institution: str | None = None
    organization: str | None = None
    department: str | None = None
    location: str | None = None
    country: str | None = None
    official_job_id: str | None = None
    official_url: str | None = None
    discovery_urls: list[str] = dataclass_field(default_factory=list)
    source_provenance: list[dict[str, Any]] = dataclass_field(default_factory=list)
    source_message_ids: list[str] = dataclass_field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None
    posted_date: str | None = None
    deadline: str | None = None
    deadline_type: str = "unknown"
    expected_start_date: str | None = None
    lifecycle_status: str = "unknown"
    verification_status: VerificationStatus | str = VerificationStatus.UNKNOWN
    verification_authority: SourceAuthority | int | None = None
    field_authority: dict[str, int] = dataclass_field(default_factory=dict)
    last_verified: str | None = None
    verification_confidence: float | None = None
    close_reason: str | None = None
    normalized_title: str | None = None
    role_class: str | None = None
    independence_class: str | None = None
    independence_confidence: float | None = None
    independence_evidence: list[str] = dataclass_field(default_factory=list)
    description: str | None = None
    search_scope: dict[str, Any] = dataclass_field(default_factory=dict)
    requirements: dict[str, Any] = dataclass_field(default_factory=dict)
    position: dict[str, Any] = dataclass_field(default_factory=dict)
    evaluation: dict[str, Any] = dataclass_field(default_factory=dict)
    evaluation_version: int = 0
    evaluation_history: list[dict[str, Any]] = dataclass_field(default_factory=list)
    application: dict[str, Any] = dataclass_field(default_factory=dict)
    fit_score: float | None = None
    tier: str | None = None
    strongest_matches: list[str] = dataclass_field(default_factory=list)
    meaningful_gaps: list[str] = dataclass_field(default_factory=list)
    hard_blockers: list[str] = dataclass_field(default_factory=list)
    manual_review_state: str | None = None
    rejected: bool = False

    _ALIASES: ClassVar[Mapping[str, str]] = {
        "id": "canonical_id",
        "job_id": "canonical_id",
        "canonical_job_id": "canonical_id",
        "requisition_id": "official_job_id",
        "official_requisition_id": "official_job_id",
        "canonical_url": "official_url",
        "sources": "source_provenance",
        "all_discovery_sources": "source_provenance",
    }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JobRecord":
        """Load either the flat core record or the canonical academic payload.

        The academic deployment's public contract groups fields under
        ``identity``, ``urls``, ``source``, ``dates``, ``status``, and
        ``independence``.  State stores are intentionally deployment-agnostic,
        so normalize that shape here rather than teaching every state adapter
        about ``AcademicJob``.  Flat values win when both representations are
        present, which keeps this migration path conservative.
        """

        if not isinstance(data, Mapping):
            raise TypeError(f"{cls.__name__}.from_dict expects a mapping")
        nested_names = {
            "identity",
            "urls",
            "source",
            "dates",
            "status",
            "independence",
        }
        if not any(isinstance(data.get(name), Mapping) for name in nested_names):
            return super().from_dict(data)

        identity = data.get("identity", {})
        identity = identity if isinstance(identity, Mapping) else {}
        urls = data.get("urls", {})
        urls = urls if isinstance(urls, Mapping) else {}
        source = data.get("source", {})
        source = source if isinstance(source, Mapping) else {}
        dates = data.get("dates", {})
        dates = dates if isinstance(dates, Mapping) else {}
        status = data.get("status", {})
        status = status if isinstance(status, Mapping) else {}
        independence = data.get("independence", {})
        independence = independence if isinstance(independence, Mapping) else {}
        flattened = {
            key: copy_value
            for key, copy_value in data.items()
            if key not in nested_names
        }

        def set_if_absent(name: str, value: Any) -> None:
            if name not in flattened and value is not None:
                flattened[name] = value

        set_if_absent("canonical_id", identity.get("canonical_job_id"))
        set_if_absent("institution", identity.get("institution"))
        set_if_absent("department", identity.get("department"))
        set_if_absent("title", identity.get("raw_title"))
        set_if_absent("role_class", identity.get("normalized_role_class"))
        set_if_absent("official_job_id", identity.get("job_id_or_requisition"))
        set_if_absent("country", identity.get("country"))
        set_if_absent(
            "location",
            identity.get("city") or identity.get("region"),
        )
        for name in ("institute_or_center", "region", "city"):
            set_if_absent(name, identity.get(name))

        set_if_absent("discovery_urls", urls.get("discovery_urls"))
        set_if_absent("official_url", urls.get("official_url"))
        set_if_absent("application_url", urls.get("application_url"))

        source_ids: list[str] = []
        first_source = source.get("first_discovered_by")
        if first_source:
            source_ids.append(str(first_source))
        raw_sources = source.get("all_discovery_sources", []) or []
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]
        source_ids.extend(str(item) for item in raw_sources if str(item).strip())
        if "source_provenance" not in flattened and source_ids:
            flattened["source_provenance"] = [
                {"source_id": source_id}
                for source_id in dict.fromkeys(source_ids)
            ]
        set_if_absent("source_message_ids", source.get("source_message_ids"))

        for name in (
            "first_seen",
            "last_seen",
            "posted_date",
            "deadline",
            "deadline_type",
            "expected_start_date",
        ):
            set_if_absent(name, dates.get(name))
        for name in (
            "lifecycle_status",
            "verification_status",
            "last_verified",
            "verification_confidence",
            "close_reason",
        ):
            set_if_absent(name, status.get(name))

        set_if_absent("independence_class", independence.get("class"))
        set_if_absent("independence_confidence", independence.get("confidence"))
        set_if_absent("independence_evidence", independence.get("evidence"))

        evaluation = flattened.get("evaluation")
        if isinstance(evaluation, Mapping):
            set_if_absent("fit_score", evaluation.get("fit_score"))
            set_if_absent("tier", evaluation.get("tier"))
            set_if_absent("strongest_matches", evaluation.get("strongest_matches"))
            set_if_absent("meaningful_gaps", evaluation.get("meaningful_gaps"))
            set_if_absent("hard_blockers", evaluation.get("hard_blockers"))
        return super().from_dict(flattened)

    def __post_init__(self) -> None:
        try:
            self.verification_status = VerificationStatus(self.verification_status)
        except ValueError:
            self.verification_status = VerificationStatus.UNKNOWN
        if self.verification_authority is not None:
            try:
                self.verification_authority = SourceAuthority(self.verification_authority)
            except ValueError:
                self.verification_authority = int(self.verification_authority)
        self.field_authority = {
            str(name): int(authority)
            for name, authority in dict(self.field_authority or {}).items()
        }
        self.evaluation_version = int(self.evaluation_version or 0)
        if self.evaluation_version < 0:
            raise ValueError("evaluation_version must not be negative")
        if self.verification_confidence is not None and not 0 <= float(
            self.verification_confidence
        ) <= 1:
            raise ValueError("verification_confidence must be between 0 and 1")
        if self.independence_confidence is not None and not 0 <= float(
            self.independence_confidence
        ) <= 1:
            raise ValueError("independence_confidence must be between 0 and 1")
        for name in (
            "discovery_urls",
            "source_message_ids",
            "independence_evidence",
            "strongest_matches",
            "meaningful_gaps",
            "hard_blockers",
            "evaluation_history",
        ):
            value = getattr(self, name)
            if value is None:
                setattr(self, name, [])
            elif not isinstance(value, list):
                setattr(self, name, list(value))

    @property
    def organization_name(self) -> str:
        return (self.institution or self.company or self.organization or "").strip()

    @property
    def is_actionable(self) -> bool:
        return (
            not self.rejected
            and not self.hard_blockers
            and str(self.tier or "").casefold().replace(" ", "_")
            in {"tier_1", "tier1", "tier_2", "tier2"}
            and self.verification_status
            in {VerificationStatus.VERIFIED_OPEN, VerificationStatus.VERIFIED_REOPENED}
        )


@dataclass
class ChangeRecord(JsonModel):
    job_id: str = ""
    field: str = ""
    old_value: Any = None
    new_value: Any = None
    changed_at: str = dataclass_field(default_factory=utc_now)
    source: str | None = None
    confidence: float | None = None
    change_type: str = "job_content_change"
    material: bool = True


@dataclass
class RunRecord(JsonModel):
    run_id: str = ""
    run_type: str = "daily"
    started_at: str = dataclass_field(default_factory=utc_now)
    completed_at: str | None = None
    status: str = "running"
    metrics: dict[str, Any] = dataclass_field(default_factory=dict)
    errors: list[dict[str, Any]] = dataclass_field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("RunRecord.run_id must be non-empty")


@dataclass
class CoverageRecord(JsonModel):
    """Generic coverage event for deployment-specific coverage dimensions."""

    coverage_id: str = ""
    coverage_type: str = "source"
    last_attempted: str | None = None
    last_successful: str | None = None
    status: str = "unknown"
    items_seen: int = 0
    error: str | None = None
    next_due: str | None = None

    def __post_init__(self) -> None:
        if not self.coverage_id:
            raise ValueError("CoverageRecord.coverage_id must be non-empty")


@dataclass
class SourceCoverageRecord(JsonModel):
    source_id: str = ""
    last_attempted: str | None = None
    last_successful: str | None = None
    status: str = "unknown"
    items_seen: int = 0
    error: str | None = None
    next_due: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("SourceCoverageRecord.source_id must be non-empty")


@dataclass
class InstitutionCoverageRecord(JsonModel):
    institution: str = ""
    last_attempted: str | None = None
    last_successful: str | None = None
    official_pages_checked: list[str] = dataclass_field(default_factory=list)
    search_queries_checked: list[str] = dataclass_field(default_factory=list)
    status: str = "unknown"
    notes: list[str] = dataclass_field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.institution:
            raise ValueError("InstitutionCoverageRecord.institution must be non-empty")

@dataclass
class ApplicationRecord(JsonModel):
    job_id: str = ""
    status: str = "not_started"
    gatedsprint_status: str | None = None
    package_path: str | None = None
    submitted_at: str | None = None
    notes: list[str] = dataclass_field(default_factory=list)
    updated_at: str = dataclass_field(default_factory=utc_now)

    _ALIASES: ClassVar[Mapping[str, str]] = {"submitted_date": "submitted_at"}

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("ApplicationRecord.job_id must be non-empty")


@dataclass
class UpsertResult(JsonModel):
    action: str = "skipped"
    job_id: str | None = None
    record: dict[str, Any] | None = None
    previous: dict[str, Any] | None = None
    reason: str | None = None
