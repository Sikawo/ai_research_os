"""Academic PI deployment value objects.

The shared core deliberately keeps job records generic.  These small value
objects describe academic-only parsing, scoring, reporting, and orchestration
results without introducing a second state store or connector system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from hashlib import sha256
from typing import Any, Iterable, Mapping


class AcademicRoleClass(str, Enum):
    INDEPENDENT_PI = "independent_pi"
    TENURE_TRACK_FACULTY = "tenure_track_faculty"
    FACULTY_OPEN_RANK = "faculty_open_rank"
    INDEPENDENT_GROUP_LEADER = "independent_group_leader"
    LIKELY_INDEPENDENT_PI = "likely_independent_pi"
    AMBIGUOUS_INDEPENDENCE = "ambiguous_independence"
    RESEARCH_FACULTY = "research_faculty"
    NON_INDEPENDENT_RESEARCH = "non_independent_research"
    POSTDOC = "postdoc"
    STAFF_SCIENTIST = "staff_scientist"
    TECHNICIAN = "technician"
    TEACHING_ONLY = "teaching_only"
    ADMINISTRATIVE = "administrative"
    OTHER = "other"


class IndependenceClass(str, Enum):
    INDEPENDENT = "independent"
    LIKELY_INDEPENDENT = "likely_independent"
    AMBIGUOUS = "ambiguous"
    NON_INDEPENDENT = "non_independent"


class AcademicTier(str, Enum):
    TIER_1 = "Tier 1"
    TIER_2 = "Tier 2"
    WATCHLIST = "Watchlist"
    BLOCKED = "BLOCKED"
    BELOW_THRESHOLD = "Below threshold"


ACADEMIC_JOB_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TitleNormalization:
    raw_title: str
    normalized_role_class: str
    country: str | None = None
    confidence: float = 0.0
    matched_terms: tuple[str, ...] = ()
    requires_review: bool = False


@dataclass(frozen=True)
class IndependenceAssessment:
    independence_class: str
    confidence: float
    evidence: tuple[str, ...] = ()


@dataclass
class DiscoveryCandidate:
    """One plausible job parsed from a discovery event.

    A message may produce many candidates.  ``event_id`` is an ingestion-event
    identifier, never a canonical job identifier.
    """

    raw_title: str
    institution: str | None = None
    url: str | None = None
    source_id: str = "email_alert"
    message_id: str | None = None
    department: str | None = None
    location: str | None = None
    country: str | None = None
    snippet: str | None = None
    official_url: str | None = None
    requisition_id: str | None = None
    source_listing_id: str | None = None
    deadline: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        payload = "\x1f".join(
            (
                self.message_id or "",
                self.source_id,
                self.url or "",
                self.raw_title,
                self.institution or "",
            )
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GmailLabelPlan:
    message_id: str
    add_labels: tuple[str, ...]
    remove_labels: tuple[str, ...] = ()
    processed: bool = False
    reason: str = ""
    archive: bool = False
    delete: bool = False


@dataclass(frozen=True)
class AcademicQuery:
    text: str
    family: str
    priority: int
    source_id: str | None = None
    institution: str | None = None
    broad_search: bool = False


@dataclass(frozen=True)
class FitEvaluation:
    fit_score: float
    tier: str
    fit_confidence: float
    category_scores: Mapping[str, float]
    strongest_matches: tuple[str, ...] = ()
    meaningful_gaps: tuple[str, ...] = ()
    hard_blockers: tuple[str, ...] = ()
    opportunity_notes: tuple[str, ...] = ()
    broad_search: bool = False

    @property
    def raw_fit_score(self) -> float:
        return self.fit_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "fit_score": self.fit_score,
            "raw_fit_score": self.fit_score,
            "tier": self.tier,
            "fit_confidence": self.fit_confidence,
            "category_scores": dict(self.category_scores),
            "strongest_matches": list(self.strongest_matches),
            "meaningful_gaps": list(self.meaningful_gaps),
            "hard_blockers": list(self.hard_blockers),
            "opportunity_notes": list(self.opportunity_notes),
            "broad_search": self.broad_search,
        }


@dataclass
class AcademicJob:
    """Portable academic extension payload for a shared ``JobRecord``.

    State adapters may store this payload inside ``JobRecord.extra``.  The
    deployment also accepts plain mappings, so adopters are not forced to
    migrate existing state merely to use academic-specific behavior.
    """

    schema_version: int = field(default=ACADEMIC_JOB_SCHEMA_VERSION, kw_only=True)
    canonical_job_id: str = ""
    institution: str = ""
    raw_title: str = ""
    department: str | None = None
    institute_or_center: str | None = None
    normalized_role_class: str = AcademicRoleClass.OTHER.value
    job_id_or_requisition: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    discovery_urls: list[str] = field(default_factory=list)
    official_url: str | None = None
    application_url: str | None = None
    first_discovered_by: str | None = None
    all_discovery_sources: list[str] = field(default_factory=list)
    source_message_ids: list[str] = field(default_factory=list)
    source_listing_ids: list[str] = field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None
    posted_date: str | None = None
    deadline: str | None = None
    deadline_type: str = "unknown"
    expected_start_date: str | None = None
    lifecycle_status: str = "active"
    verification_status: str = "verification_pending"
    last_verified: str | None = None
    verification_confidence: float = 0.0
    close_reason: str | None = None
    independence_class: str = IndependenceClass.AMBIGUOUS.value
    independence_confidence: float = 0.0
    independence_evidence: list[str] = field(default_factory=list)
    declared_fields: list[str] = field(default_factory=list)
    broad_search: bool = False
    department_scope: list[str] = field(default_factory=list)
    rank_scope: list[str] = field(default_factory=list)
    required_degree: str | None = None
    years_or_stage: str | None = None
    required_expertise: list[str] = field(default_factory=list)
    preferred_expertise: list[str] = field(default_factory=list)
    required_documents: list[str] = field(default_factory=list)
    reference_letter_policy: str | None = None
    number_of_references: int | None = None
    citizenship_or_eligibility: str | None = None
    other_requirements: list[str] = field(default_factory=list)
    position: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    qol_assessment: dict[str, Any] = field(default_factory=dict)
    application: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != ACADEMIC_JOB_SCHEMA_VERSION:
            raise ValueError(
                f"AcademicJob schema_version must be {ACADEMIC_JOB_SCHEMA_VERSION}"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AcademicJob":
        identity = data.get("identity", {}) if isinstance(data.get("identity"), Mapping) else {}
        urls = data.get("urls", {}) if isinstance(data.get("urls"), Mapping) else {}
        source = data.get("source", {}) if isinstance(data.get("source"), Mapping) else {}
        dates = data.get("dates", {}) if isinstance(data.get("dates"), Mapping) else {}
        status = data.get("status", {}) if isinstance(data.get("status"), Mapping) else {}
        independence = data.get("independence", {}) if isinstance(data.get("independence"), Mapping) else {}
        scope = data.get("search_scope", {}) if isinstance(data.get("search_scope"), Mapping) else {}
        requirements = data.get("requirements", {}) if isinstance(data.get("requirements"), Mapping) else {}
        known = {
            "schema_version", "identity", "urls", "source", "dates", "status", "independence",
            "search_scope", "requirements", "position", "evaluation", "qol_assessment",
            "application", "extra",
        }
        extras = dict(data.get("extra", {})) if isinstance(data.get("extra"), Mapping) else {}
        extras.update({key: value for key, value in data.items() if key not in known})
        return cls(
            schema_version=int(data.get("schema_version", ACADEMIC_JOB_SCHEMA_VERSION)),
            canonical_job_id=str(identity.get("canonical_job_id") or data.get("canonical_job_id") or ""),
            institution=str(identity.get("institution") or data.get("institution") or ""),
            raw_title=str(identity.get("raw_title") or data.get("raw_title") or data.get("title") or ""),
            department=identity.get("department", data.get("department")),
            institute_or_center=identity.get("institute_or_center"),
            normalized_role_class=str(identity.get("normalized_role_class") or AcademicRoleClass.OTHER.value),
            job_id_or_requisition=identity.get("job_id_or_requisition"),
            country=identity.get("country"),
            region=identity.get("region"),
            city=identity.get("city"),
            discovery_urls=list(urls.get("discovery_urls", data.get("discovery_urls", [])) or []),
            official_url=urls.get("official_url", data.get("official_url")),
            application_url=urls.get("application_url"),
            first_discovered_by=source.get("first_discovered_by"),
            all_discovery_sources=list(source.get("all_discovery_sources", []) or []),
            source_message_ids=list(source.get("source_message_ids", []) or []),
            source_listing_ids=list(source.get("source_listing_ids", []) or []),
            first_seen=dates.get("first_seen"),
            last_seen=dates.get("last_seen"),
            posted_date=dates.get("posted_date"),
            deadline=dates.get("deadline", data.get("deadline")),
            deadline_type=str(dates.get("deadline_type", "unknown")),
            expected_start_date=dates.get("expected_start_date"),
            lifecycle_status=str(status.get("lifecycle_status", "active")),
            verification_status=str(status.get("verification_status", "verification_pending")),
            last_verified=status.get("last_verified"),
            verification_confidence=float(status.get("verification_confidence", 0.0) or 0.0),
            close_reason=status.get("close_reason"),
            independence_class=str(independence.get("class", IndependenceClass.AMBIGUOUS.value)),
            independence_confidence=float(independence.get("confidence", 0.0) or 0.0),
            independence_evidence=list(independence.get("evidence", []) or []),
            declared_fields=list(scope.get("declared_fields", []) or []),
            broad_search=bool(scope.get("broad_search", False)),
            department_scope=list(scope.get("department_scope", []) or []),
            rank_scope=list(scope.get("rank_scope", []) or []),
            required_degree=requirements.get("required_degree"),
            years_or_stage=requirements.get("years_or_stage"),
            required_expertise=list(requirements.get("required_expertise", []) or []),
            preferred_expertise=list(requirements.get("preferred_expertise", []) or []),
            required_documents=list(requirements.get("required_documents", []) or []),
            reference_letter_policy=requirements.get("reference_letter_policy"),
            number_of_references=requirements.get("number_of_references"),
            citizenship_or_eligibility=requirements.get("citizenship_or_eligibility"),
            other_requirements=list(requirements.get("other_requirements", []) or []),
            position=dict(data.get("position", {}) or {}),
            evaluation=dict(data.get("evaluation", {}) or {}),
            qol_assessment=dict(data.get("qol_assessment", {}) or {}),
            application=dict(data.get("application", {}) or {}),
            extra=extras,
        )

    def to_dict(self) -> dict[str, Any]:
        position = {
            "tenure_status": None,
            "faculty_track": None,
            "appointment_type": None,
            "contract_term": None,
            "salary_min": None,
            "salary_max": None,
            "salary_currency": None,
            "salary_period": None,
            "salary_basis": None,
            "salary_evidence_url": None,
            "salary_is_estimate": None,
            "employer_retirement_or_super": None,
            "startup_information": None,
            "lab_space_information": None,
            "teaching_expectation": None,
            "clinical_expectation": None,
            "visa_or_sponsorship_information": None,
        }
        position.update(dict(to_plain_data(self.position)))
        evaluation = {
            "fit_score": None,
            "fit_confidence": None,
            "tier": None,
            "strongest_matches": [],
            "meaningful_gaps": [],
            "hard_blockers": [],
            "opportunity_notes": [],
            "qol_notes": [],
        }
        evaluation.update(dict(to_plain_data(self.evaluation)))
        application = {
            "status": "not_started",
            "gatedsprint_status": None,
            "package_path": None,
            "submitted_date": None,
            "notes": [],
        }
        application.update(dict(to_plain_data(self.application)))
        if "submitted_at" in application and application.get("submitted_date") is None:
            application["submitted_date"] = application.pop("submitted_at")

        payload = {
            "schema_version": self.schema_version,
            "identity": {
                "canonical_job_id": self.canonical_job_id,
                "institution": self.institution,
                "department": self.department,
                "institute_or_center": self.institute_or_center,
                "raw_title": self.raw_title,
                "normalized_role_class": self.normalized_role_class,
                "job_id_or_requisition": self.job_id_or_requisition,
                "country": self.country,
                "region": self.region,
                "city": self.city,
            },
            "urls": {
                "discovery_urls": list(self.discovery_urls),
                "official_url": self.official_url,
                "application_url": self.application_url,
            },
            "source": {
                "first_discovered_by": self.first_discovered_by,
                "all_discovery_sources": list(self.all_discovery_sources),
                "source_message_ids": list(self.source_message_ids),
                "source_listing_ids": list(self.source_listing_ids),
            },
            "dates": {
                "first_seen": self.first_seen,
                "last_seen": self.last_seen,
                "posted_date": self.posted_date,
                "deadline": self.deadline,
                "deadline_type": self.deadline_type,
                "expected_start_date": self.expected_start_date,
            },
            "status": {
                "lifecycle_status": self.lifecycle_status,
                "verification_status": self.verification_status,
                "last_verified": self.last_verified,
                "verification_confidence": self.verification_confidence,
                "close_reason": self.close_reason,
            },
            "independence": {
                "class": self.independence_class,
                "confidence": self.independence_confidence,
                "evidence": list(self.independence_evidence),
            },
            "search_scope": {
                "declared_fields": list(self.declared_fields),
                "broad_search": self.broad_search,
                "department_scope": list(self.department_scope),
                "rank_scope": list(self.rank_scope),
            },
            "requirements": {
                "required_degree": self.required_degree,
                "years_or_stage": self.years_or_stage,
                "required_expertise": list(self.required_expertise),
                "preferred_expertise": list(self.preferred_expertise),
                "required_documents": list(self.required_documents),
                "reference_letter_policy": self.reference_letter_policy,
                "number_of_references": self.number_of_references,
                "citizenship_or_eligibility": self.citizenship_or_eligibility,
                "other_requirements": list(self.other_requirements),
            },
            "position": position,
            "evaluation": evaluation,
            "qol_assessment": dict(to_plain_data(self.qol_assessment)),
            "application": application,
            "extra": dict(to_plain_data(self.extra)),
        }
        # Import lazily to avoid a module cycle: handoff helpers depend on
        # these value objects, while AcademicJob validates only at emission.
        from .handoff import validate_schema_payload

        validate_schema_payload(payload, "academic_job.schema.json")
        return payload


@dataclass
class WorkflowResult:
    run_id: str
    run_type: str
    metrics: dict[str, int]
    report: str
    jobs: list[Any] = field(default_factory=list)
    label_plans: list[GmailLabelPlan] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    submitted_applications: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "metrics": dict(self.metrics),
            "report": self.report,
            "jobs": [to_plain_data(job) for job in self.jobs],
            "label_plans": [asdict(plan) for plan in self.label_plans],
            "errors": list(self.errors),
            "submitted_applications": self.submitted_applications,
        }


def to_plain_data(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): to_plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain_data(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def get_value(record: Any, *paths: str, default: Any = None) -> Any:
    """Read the first populated dotted path from a mapping or object."""

    for path in paths:
        current = record
        found = True
        for part in path.split("."):
            if isinstance(current, Mapping):
                if part not in current:
                    found = False
                    break
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                extra = getattr(current, "extra", None)
                if isinstance(extra, Mapping) and part in extra:
                    current = extra[part]
                else:
                    found = False
                    break
        if found and current not in (None, ""):
            return current
    return default


def text_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Mapping):
        return tuple(str(item) for item in value.values() if item not in (None, ""))
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if item not in (None, ""))
    return (str(value),)
