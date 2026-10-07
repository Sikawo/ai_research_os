"""Daily, weekly, and manual Academic PI workflow orchestration."""

from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from uuid import uuid4

from ...core.changes import detect_material_changes
from ...core.connectors import (
    AlertMessage,
    DeliveryResult,
    DiscoveryBatch,
    DiscoveryRequest,
    EmailAlertConnector,
    ReportConnector,
    VerificationConnector,
)
from ...core.identity import canonical_job_identity
from ...core.models import (
    InstitutionCoverageRecord,
    JobRecord,
    RunRecord,
    SourceCoverageRecord,
    VerificationResult,
    VerificationStatus,
    utc_now,
)
from ...core.sources import apply_verification, verification_is_authoritative
from ...core.state import InMemoryStateStore, StateStore
from ...core.urls import normalize_url
from .adapters import NoOpVerificationAdapter
from .email_ingestion import (
    DEFAULT_GMAIL_LABELS,
    EmailParseResult,
    parse_academic_alert_result,
    plan_gmail_labels,
)
from .handoff import (
    ContractValidationError,
    build_gatedsprint_handoff,
    validate_schema_payload,
)
from .models import (
    AcademicJob,
    DiscoveryCandidate,
    GmailLabelPlan,
    WorkflowResult,
    get_value,
)
from .institution_monitor import is_authoritative_target_url, plan_target_scan
from .queries import generate_academic_queries
from .qol import build_qol_assessment, qol_refresh_reasons, requires_full_qol
from .reports import render_daily_report, render_weekly_report
from .scoring import score_academic_fit
from .titles import infer_independence, normalize_academic_title


ERROR_CATEGORIES = {
    "source_unavailable",
    "authentication_error",
    "parser_error",
    "rate_limit",
    "official_page_unreachable",
    "official_source_not_found",
    "schema_validation_error",
    "state_write_error",
    "email_label_error",
    "report_delivery_error",
    "unknown",
}


_UNTRUSTED_JOB_FIELDS = {
    "title",
    "raw_title",
    "company",
    "institution",
    "organization",
    "department",
    "location",
    "country",
    "official_job_id",
    "requisition_id",
    "official_requisition_id",
    "official_url",
    "canonical_url",
    "discovery_urls",
    "posted_date",
    "deadline",
    "deadline_type",
    "expected_start_date",
    "normalized_title",
    "role_class",
    "independence_class",
    "independence_confidence",
    "independence_evidence",
    "description",
    "search_scope",
    "requirements",
    "position",
}
_UNTRUSTED_EXTRA_BLOCKED = {
    "clear_manual_override",
    "human_override",
    "update_source",
    "ingestion_event_id",
    "evaluation_versions",
    "last_verification_transition_accepted",
    "last_verification_authoritative",
    "last_verification_result_status",
    "last_verification_run_id",
    "last_verification_attempted_at",
    "verified_open_in_run",
    "current_active_run_id",
    "current_active_verified_open",
}
@dataclass(frozen=True)
class _DiscoveryPayload:
    payload: Any
    source_id: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_data(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if hasattr(value, "to_dict"):
        return copy.deepcopy(value.to_dict())
    raise TypeError(f"Expected a job mapping or model, got {type(value).__name__}")


def _config_rows(value: Any, nested_key: str) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        nested = value.get(nested_key)
        if nested is not None:
            value = nested
        elif all(isinstance(item, Mapping) for item in value.values()):
            value = list(value.values())
        else:
            return []
    if value is None:
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _error(category: str, message: str, **context: Any) -> dict[str, Any]:
    safe_category = category if category in ERROR_CATEGORIES else "unknown"
    return {"category": safe_category, "message": message, **context}


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _string_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (Mapping, bytes)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _write_confirmed(value: Any) -> bool:
    if value is False:
        return False
    if isinstance(value, Mapping) and "confirmed" in value:
        return bool(value["confirmed"])
    if hasattr(value, "confirmed"):
        return bool(value.confirmed)
    return True


def _source_enabled(source: Mapping[str, Any]) -> bool:
    """Resolve the catalog default and any explicit private override."""

    if "enabled" in source:
        return source.get("enabled") is True
    return source.get("enabled_by_default", True) is True


def _safe_untrusted_extra(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key)
        folded = name.casefold()
        if name in _UNTRUSTED_EXTRA_BLOCKED:
            continue
        if folded.startswith(("last_verification", "current_active", "human_")):
            continue
        safe[name] = copy.deepcopy(item)
    return safe


@dataclass
class AcademicPiService:
    """Academic deployment using only injected side-effect boundaries.

    With no connectors it remains fully runnable: state is in-memory, discovery
    returns no jobs, verification stays pending, and a local report is returned.
    """

    config: Mapping[str, Any] = field(default_factory=dict)
    state_store: StateStore | None = None
    discovery_connectors: Sequence[Any] = field(default_factory=tuple)
    verification_connector: VerificationConnector | None = None
    report_connectors: Sequence[ReportConnector] = field(default_factory=tuple)
    email_connector: EmailAlertConnector | None = None

    def __post_init__(self) -> None:
        self.config = copy.deepcopy(dict(self.config))
        self.state: StateStore = self.state_store or InMemoryStateStore()
        self.verifier: VerificationConnector = self.verification_connector or NoOpVerificationAdapter()

    @property
    def academic_config(self) -> Mapping[str, Any]:
        value = self.config.get("academic_pi")
        if value is None:
            defaults = self.config.get("defaults")
            if isinstance(defaults, Mapping):
                value = defaults.get("academic_pi")
        if value is None:
            value = self.config
        return value if isinstance(value, Mapping) else {}

    @property
    def profile(self) -> Mapping[str, Any]:
        for key in ("candidate_profile", "candidate_profile.example", "profile"):
            value = self.config.get(key)
            if isinstance(value, Mapping):
                return value
        academic = self.academic_config
        value = academic.get("candidate_profile")
        return value if isinstance(value, Mapping) else {}

    @property
    def preferences(self) -> Mapping[str, Any]:
        value = self.config.get("preferences", self.config.get("preferences.example", {}))
        return value if isinstance(value, Mapping) else {}

    @property
    def evaluation_profile(self) -> Mapping[str, Any]:
        merged = copy.deepcopy(dict(self.preferences))
        for key, value in self.profile.items():
            if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
                merged[key] = {**dict(merged[key]), **copy.deepcopy(dict(value))}
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    @property
    def sources(self) -> list[Mapping[str, Any]]:
        value = self.config.get("source_catalog", self.config.get("sources"))
        if value is None:
            value = self.academic_config.get("source_catalog", self.academic_config.get("sources"))
        rows = [dict(row) for row in _config_rows(value, "sources")]
        override = self.config.get("source_overrides", self.config.get("source_overrides.example", {}))
        override_rows = override.get("sources", {}) if isinstance(override, Mapping) else {}
        if isinstance(override_rows, Mapping):
            for row in rows:
                item = override_rows.get(row.get("id"))
                if isinstance(item, Mapping):
                    row.update(item)
        society_rows = override.get("society_sources", ()) if isinstance(override, Mapping) else ()
        for item in society_rows or ():
            if isinstance(item, Mapping) and item.get("source_id"):
                rows.append({"id": item["source_id"], **dict(item)})
        return rows

    @property
    def institutions(self) -> list[Mapping[str, Any]]:
        value = self.config.get(
            "target_institutions",
            self.config.get("target_institutions.example", self.config.get("institutions")),
        )
        if value is None:
            value = self.academic_config.get("target_institutions", self.academic_config.get("institutions"))
        return [row for row in _config_rows(value, "institutions") if row.get("enabled", True)]

    @property
    def scoring_config(self) -> Mapping[str, Any]:
        public_value = self.academic_config.get("scoring", {})
        config = dict(public_value) if isinstance(public_value, Mapping) else {}
        if "dimensions" in config and "weights" not in config:
            config["weights"] = dict(config["dimensions"])
        tiering = self.academic_config.get("tiering")
        if isinstance(tiering, Mapping):
            config["tiering"] = dict(tiering)
        override = self.config.get("scoring_overrides", self.config.get("scoring_overrides.example"))
        if isinstance(override, Mapping):
            override_value = override.get("scoring", override)
            if isinstance(override_value, Mapping):
                for key, value in override_value.items():
                    if isinstance(value, Mapping) and isinstance(config.get(key), Mapping):
                        config[key] = {**dict(config[key]), **dict(value)}
                    else:
                        config[key] = copy.deepcopy(value)
        # Private templates use ``thresholds`` while the public defaults use
        # ``tiering``.  The private values are the later overlay and therefore
        # must be the effective tier thresholds.
        if isinstance(config.get("thresholds"), Mapping):
            config["tiering"] = {
                **dict(config.get("tiering", {})),
                **dict(config["thresholds"]),
            }
        return config

    @property
    def email_labels(self) -> Mapping[str, str]:
        email = self.academic_config.get("email", {})
        labels = email.get("labels", {}) if isinstance(email, Mapping) else {}
        return {
            str(key): str(value)
            for key, value in labels.items()
            if value not in (None, "")
        } if isinstance(labels, Mapping) else {}

    @property
    def email_source_registry(self) -> Mapping[str, Any]:
        value = self.config.get(
            "email_sources", self.config.get("email_sources.example", {})
        )
        return value if isinstance(value, Mapping) else {}

    @property
    def deadline_warning_days(self) -> tuple[int, ...]:
        reporting = self.preferences.get("reporting", {})
        configured = (
            reporting.get("deadline_warning_days")
            if isinstance(reporting, Mapping)
            else None
        )
        if configured is None:
            deadlines = self.academic_config.get("deadlines", {})
            configured = deadlines.get("warning_days") if isinstance(deadlines, Mapping) else None
        values: set[int] = set()
        for item in (30, 14, 7, 3, 1) if configured is None else configured:
            try:
                days = int(item)
            except (TypeError, ValueError):
                continue
            if days >= 0:
                values.add(days)
        return tuple(sorted(values, reverse=True))

    @property
    def material_change_fields(self) -> tuple[str, ...] | None:
        configured = self.config.get("material_change_fields", {})
        fields = configured.get("material_fields") if isinstance(configured, Mapping) else None
        if not fields:
            return None
        aliases = {
            "status.lifecycle_status": "lifecycle_status",
            "status.verification_status": "verification_status",
            "dates.deadline": "deadline",
            "dates.deadline_type": "deadline_type",
            "dates.expected_start_date": "expected_start_date",
            "identity.raw_title": "title",
            "identity.normalized_role_class": "role_class",
            "identity.department": "department",
            "identity.city": "location",
            "identity.region": "location",
            "urls.official_url": "official_url",
            "identity.job_id_or_requisition": "official_job_id",
        }
        normalized: list[str] = []
        for item in fields:
            value = aliases.get(str(item), str(item))
            if value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    @property
    def evaluation_versions(self) -> dict[str, Any]:
        scoring_override = self.config.get(
            "scoring_overrides", self.config.get("scoring_overrides.example", {})
        )
        profile_version = self.profile.get("profile_version")
        rubric_version = (
            scoring_override.get("rubric_version")
            if isinstance(scoring_override, Mapping)
            else None
        )
        if rubric_version is None:
            scoring = self.academic_config.get("scoring", {})
            rubric_version = scoring.get("rubric_version") if isinstance(scoring, Mapping) else None
        return {
            "profile_version": profile_version if profile_version is not None else "unversioned",
            "rubric_version": rubric_version if rubric_version is not None else "unversioned",
            "evaluation_engine_version": "academic_pi_v1",
        }

    def validate_config(self, *, strict_contracts: bool = True) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.config, Mapping):
            errors.append("configuration root must be a mapping")
            return errors
        automation = self.academic_config.get("automation", {})
        if isinstance(automation, Mapping) and automation.get("auto_apply") is True:
            errors.append("academic_pi.automation.auto_apply must remain false")
        identity = self.profile.get("scientific_identity", {}) if self.profile else {}
        if identity and not isinstance(identity, Mapping):
            errors.append("candidate_profile.scientific_identity must be a mapping")
        if strict_contracts and not self.profile:
            errors.append(
                "candidate_profile is required for operational CLI commands"
            )
        if strict_contracts and not self.preferences:
            errors.append("preferences is required for operational CLI commands")
        contracts = (
            (self.profile, "candidate_profile.schema.json", "candidate_profile"),
            (self.preferences, "preferences.schema.json", "preferences"),
        )
        for payload, schema_name, label in contracts:
            if not isinstance(payload, Mapping) or not payload:
                continue
            try:
                validate_schema_payload(dict(payload), schema_name)
            except ContractValidationError as exc:
                issues = list(exc.issues)
                if not strict_contracts:
                    # Library callers may intentionally supply a narrow scoring
                    # context.  Validate every value they did supply, while the
                    # CLI's explicit validation command enforces completeness.
                    issues = [
                        issue
                        for issue in issues
                        if "required property is missing" not in issue
                        and "expected constant" not in issue
                        and "additional property is not allowed" not in issue
                    ]
                errors.extend(f"{label}{issue[1:]}" for issue in issues)
        reporting = self.preferences.get("reporting", {})
        if isinstance(reporting, Mapping):
            warning_days = reporting.get("deadline_warning_days")
            if warning_days is not None and (
                isinstance(warning_days, (str, bytes, Mapping))
                or not isinstance(warning_days, Iterable)
            ):
                errors.append("preferences.reporting.deadline_warning_days must be an array")
            elif warning_days is not None:
                for index, value in enumerate(warning_days):
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or value < 0
                    ):
                        errors.append(
                            "preferences.reporting.deadline_warning_days"
                            f"[{index}] must be a non-negative integer"
                        )

        def require_non_negative_int(value: Any, path: str, *, positive: bool = False) -> None:
            minimum = 1 if positive else 0
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                qualifier = "positive" if positive else "non-negative"
                errors.append(f"{path} must be a {qualifier} integer")

        query_budget = self.academic_config.get("query_budget", 50)
        if isinstance(query_budget, Mapping):
            for key in ("total", "max_queries", "per_source"):
                if key in query_budget:
                    require_non_negative_int(
                        query_budget[key],
                        f"academic_pi.query_budget.{key}",
                        positive=key == "per_source",
                    )
        else:
            require_non_negative_int(query_budget, "academic_pi.query_budget")

        source_override = self.config.get(
            "source_overrides", self.config.get("source_overrides.example", {})
        )
        if source_override not in (None, {}) and not isinstance(source_override, Mapping):
            errors.append("source_overrides must be a mapping")
        if isinstance(source_override, Mapping):
            query_generation = source_override.get("query_generation", {})
            if query_generation not in (None, {}) and not isinstance(
                query_generation, Mapping
            ):
                errors.append("source_overrides.query_generation must be a mapping")
            elif isinstance(query_generation, Mapping):
                maximum = query_generation.get("maximum_queries_per_source_per_run")
                if maximum is not None:
                    require_non_negative_int(
                        maximum,
                        "source_overrides.query_generation."
                        "maximum_queries_per_source_per_run",
                        positive=True,
                    )

        for index, source in enumerate(self.sources):
            for key in (
                "query_cap",
                "max_queries",
                "interval_days",
                "scan_frequency_days",
                "cadence_days",
            ):
                if source.get(key) is not None:
                    require_non_negative_int(
                        source[key], f"sources[{index}].{key}"
                    )
        for index, institution in enumerate(self.institutions):
            if institution.get("priority") is not None:
                require_non_negative_int(
                    institution["priority"],
                    f"target_institutions.institutions[{index}].priority",
                )
            for key in ("interval_days", "scan_frequency_days", "cadence_days"):
                if institution.get(key) is not None:
                    require_non_negative_int(
                        institution[key],
                        f"target_institutions.institutions[{index}].{key}",
                    )

        coverage = self.academic_config.get("coverage", {})
        if isinstance(coverage, Mapping):
            interval_sections = (
                ("frequency_classes", coverage.get("frequency_classes", {})),
                ("target_institutions", coverage.get("target_institutions", {})),
                ("reverify_active", coverage.get("reverify_active", {})),
            )
            for section_name, section in interval_sections:
                if not isinstance(section, Mapping):
                    errors.append(f"academic_pi.coverage.{section_name} must be a mapping")
                    continue
                for key, value in section.items():
                    if isinstance(value, Mapping):
                        value = value.get("interval_days")
                    if value is not None and (
                        key.endswith("interval_days") or isinstance(section.get(key), Mapping)
                    ):
                        require_non_negative_int(
                            value,
                            f"academic_pi.coverage.{section_name}.{key}.interval_days"
                            if isinstance(section.get(key), Mapping)
                            else f"academic_pi.coverage.{section_name}.{key}",
                        )

        scoring = self.scoring_config
        for section_name in ("weights", "tiering"):
            section = scoring.get(section_name, {}) if isinstance(scoring, Mapping) else {}
            if not isinstance(section, Mapping):
                errors.append(f"scoring.{section_name} must be a mapping")
                continue
            for key, value in section.items():
                if section_name == "tiering" and key.startswith("require_"):
                    if not isinstance(value, bool):
                        errors.append(f"scoring.{section_name}.{key} must be boolean")
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append(f"scoring.{section_name}.{key} must be a finite number")
                elif not math.isfinite(float(value)):
                    errors.append(f"scoring.{section_name}.{key} must be a finite number")
        catalog_value = self.config.get("source_catalog", self.config.get("sources"))
        if catalog_value is None:
            catalog_value = self.academic_config.get(
                "source_catalog", self.academic_config.get("sources")
            )
        catalog_sources = [dict(row) for row in _config_rows(catalog_value, "sources")]
        if strict_contracts and not catalog_sources:
            errors.append(
                "source_catalog.sources requires at least one schema-valid source"
            )
        for index, source in enumerate(catalog_sources):
            if not source.get("id"):
                errors.append(f"source_catalog.sources[{index}] requires id")
            # ``enabled`` is a private runtime override, not part of the
            # immutable public catalog contract.
            payload = {key: value for key, value in source.items() if key != "enabled"}
            try:
                validate_schema_payload(payload, "source.schema.json")
            except ContractValidationError as exc:
                issues = list(exc.issues)
                if not strict_contracts:
                    issues = [
                        issue
                        for issue in issues
                        if "required property is missing" not in issue
                        and "expected constant" not in issue
                        and "additional property is not allowed" not in issue
                    ]
                errors.extend(
                    f"source_catalog.sources[{index}]{issue[1:]}"
                    for issue in issues
                )
        for index, institution in enumerate(self.institutions):
            if not institution.get("name"):
                errors.append(f"target_institutions.institutions[{index}] requires name")
            try:
                validate_schema_payload(
                    {"version": 1, "institutions": [dict(institution)]},
                    "target_institutions.schema.json",
                )
            except ContractValidationError as exc:
                issues = list(exc.issues)
                if not strict_contracts:
                    issues = [
                        issue
                        for issue in issues
                        if "required property is missing" not in issue
                        and "additional property is not allowed" not in issue
                    ]
                errors.extend(
                    f"target_institutions.institutions[{index}]{issue[1:]}"
                    for issue in issues
                )
        return errors

    def _processed_message_ids(self) -> set[str]:
        values: set[str] = set()
        for run in self.state.list_runs():
            # A job-level message ID proves only that one candidate was persisted.
            # It must never suppress failed siblings from the same Gmail message.
            # Ignore the legacy pre-label marker because it could be written even
            # when Gmail label application failed.
            values.update(
                str(item)
                for item in run.extra.get("completed_email_message_ids", [])
            )
        return values

    def _email_candidate_progress(self) -> dict[str, set[str]]:
        progress: dict[str, set[str]] = {}
        for run in self.state.list_runs():
            raw = run.extra.get("email_candidate_progress", {})
            if not isinstance(raw, Mapping):
                continue
            for message_id, event_ids in raw.items():
                progress.setdefault(str(message_id), set()).update(
                    _string_values(event_ids)
                )
        return progress

    def _job_from_candidate(self, candidate: DiscoveryCandidate) -> JobRecord:
        seen_at = utc_now()
        host = urlparse(candidate.official_url or candidate.url or "").hostname
        institution = candidate.institution
        organization = institution or (host.removeprefix("www.") if host else "unverified source")
        normalized_url = normalize_url(candidate.official_url or candidate.url)
        normalization = normalize_academic_title(
            candidate.raw_title,
            country=candidate.country,
            context=candidate.snippet,
            rules=self.config.get("title_ontology"),
            country_rules=self.config.get("country_title_rules"),
        )
        independence = infer_independence(
            candidate.raw_title,
            candidate.snippet or "",
            country=candidate.country,
        )
        job = JobRecord(
            title=candidate.raw_title,
            institution=institution,
            organization=organization,
            department=candidate.department,
            location=candidate.location,
            country=candidate.country,
            official_job_id=candidate.requisition_id,
            official_url=normalize_url(candidate.official_url),
            discovery_urls=[url for url in (candidate.url,) if url],
            source_provenance=[
                {
                    "source_id": candidate.source_id,
                    "url": candidate.url,
                    "message_id": candidate.message_id,
                    "source_listing_id": candidate.source_listing_id,
                }
            ],
            source_message_ids=[candidate.message_id] if candidate.message_id else [],
            first_seen=seen_at,
            last_seen=seen_at,
            deadline=candidate.deadline,
            lifecycle_status="unknown",
            verification_status=VerificationStatus.VERIFICATION_PENDING,
            normalized_title=candidate.raw_title.casefold().strip(),
            role_class=normalization.normalized_role_class,
            independence_class=independence.independence_class,
            independence_confidence=independence.confidence,
            independence_evidence=list(independence.evidence),
            description=candidate.snippet,
            manual_review_state="needs_review" if normalization.requires_review else None,
            extra={
                **_safe_untrusted_extra(candidate.extra),
                "ingestion_event_id": candidate.event_id,
                "provisional_official_candidate_url": normalized_url,
                "source_listing_ids": (
                    [candidate.source_listing_id]
                    if candidate.source_listing_id
                    else []
                ),
            },
        )
        job.canonical_id = canonical_job_identity(job)
        return job

    @staticmethod
    def _academic_job_record(value: Mapping[str, Any]) -> JobRecord:
        academic = AcademicJob.from_dict(value)
        source_ids = list(
            dict.fromkeys(
                item
                for item in (
                    academic.first_discovered_by,
                    *academic.all_discovery_sources,
                )
                if item
            )
        )
        location = ", ".join(
            str(item)
            for item in (academic.city, academic.region, academic.country)
            if item
        ) or None
        evaluation = copy.deepcopy(academic.evaluation)
        extra = copy.deepcopy(academic.extra)
        if academic.application_url:
            extra["application_url"] = academic.application_url
        if academic.institute_or_center:
            extra["institute_or_center"] = academic.institute_or_center
        if academic.source_listing_ids:
            extra["source_listing_ids"] = list(academic.source_listing_ids)
        if academic.qol_assessment:
            extra["qol_assessment"] = copy.deepcopy(academic.qol_assessment)
        return JobRecord(
            canonical_id=academic.canonical_job_id or None,
            title=academic.raw_title,
            institution=academic.institution or None,
            organization=academic.institution or None,
            department=academic.department,
            location=location,
            country=academic.country,
            official_job_id=academic.job_id_or_requisition,
            official_url=academic.official_url,
            discovery_urls=list(academic.discovery_urls),
            source_provenance=[{"source_id": item} for item in source_ids],
            source_message_ids=list(academic.source_message_ids),
            first_seen=academic.first_seen,
            last_seen=academic.last_seen,
            posted_date=academic.posted_date,
            deadline=academic.deadline,
            deadline_type=academic.deadline_type,
            expected_start_date=academic.expected_start_date,
            lifecycle_status=academic.lifecycle_status,
            verification_status=academic.verification_status,
            last_verified=academic.last_verified,
            verification_confidence=academic.verification_confidence,
            close_reason=academic.close_reason,
            normalized_title=academic.raw_title.casefold().strip(),
            role_class=academic.normalized_role_class,
            independence_class=academic.independence_class,
            independence_confidence=academic.independence_confidence,
            independence_evidence=list(academic.independence_evidence),
            search_scope={
                "declared_fields": list(academic.declared_fields),
                "broad_search": academic.broad_search,
                "department_scope": list(academic.department_scope),
                "rank_scope": list(academic.rank_scope),
            },
            requirements={
                "required_degree": academic.required_degree,
                "years_or_stage": academic.years_or_stage,
                "required_expertise": list(academic.required_expertise),
                "preferred_expertise": list(academic.preferred_expertise),
                "required_documents": list(academic.required_documents),
                "reference_letter_policy": academic.reference_letter_policy,
                "number_of_references": academic.number_of_references,
                "citizenship_or_eligibility": academic.citizenship_or_eligibility,
                "other_requirements": list(academic.other_requirements),
            },
            position=copy.deepcopy(academic.position),
            evaluation=evaluation,
            application=copy.deepcopy(academic.application),
            fit_score=evaluation.get("fit_score"),
            tier=evaluation.get("tier"),
            strongest_matches=list(evaluation.get("strongest_matches", []) or []),
            meaningful_gaps=list(evaluation.get("meaningful_gaps", []) or []),
            hard_blockers=list(evaluation.get("hard_blockers", []) or []),
            extra=extra,
        )

    @staticmethod
    def _sanitize_discovered_job(job: JobRecord, source_id: str) -> JobRecord:
        """Remove state-control fields from connector-owned discovery data."""

        safe = JobRecord(
            **{
                field_name: copy.deepcopy(getattr(job, field_name))
                for field_name in _UNTRUSTED_JOB_FIELDS
                if field_name not in {"raw_title", "requisition_id", "official_requisition_id", "canonical_url"}
                and hasattr(job, field_name)
            },
            extra=_safe_untrusted_extra(job.extra),
        )
        # Provenance is assigned from the actual connector boundary; a payload
        # cannot impersonate a different source or a prior Gmail message.
        safe.source_provenance = [{"source_id": source_id}]
        safe.source_message_ids = []
        safe.lifecycle_status = "unknown"
        safe.verification_status = VerificationStatus.VERIFICATION_PENDING
        safe.verification_authority = None
        safe.field_authority = {}
        safe.last_verified = None
        safe.verification_confidence = None
        safe.close_reason = None
        safe.evaluation = {}
        safe.evaluation_history = []
        safe.evaluation_version = 0
        safe.application = {}
        safe.fit_score = None
        safe.tier = None
        safe.strongest_matches = []
        safe.meaningful_gaps = []
        safe.hard_blockers = []
        safe.manual_review_state = None
        safe.rejected = False
        seen_at = utc_now()
        safe.first_seen = seen_at
        safe.last_seen = seen_at
        safe.canonical_id = canonical_job_identity(safe)
        return safe

    def _coerce_job(
        self,
        value: Any,
        *,
        source_id: str = "manual",
        trusted: bool = True,
    ) -> JobRecord:
        if isinstance(value, DiscoveryCandidate):
            return self._job_from_candidate(value)
        if isinstance(value, JobRecord):
            job = JobRecord.from_dict(value.to_dict())
        else:
            data = _record_data(value)
            if "identity" in data and isinstance(data["identity"], Mapping):
                job = self._academic_job_record(data)
            else:
                job = JobRecord.from_dict(data)
        if not trusted:
            job = self._sanitize_discovered_job(job, source_id)
        source_listing_id = job.extra.get("source_listing_id")
        if source_listing_id:
            listing_ids = list(job.extra.get("source_listing_ids", []) or [])
            if str(source_listing_id) not in listing_ids:
                listing_ids.append(str(source_listing_id))
            job.extra["source_listing_ids"] = listing_ids
            for provenance in job.source_provenance:
                if (
                    isinstance(provenance, dict)
                    and provenance.get("source_id") == source_id
                ):
                    provenance.setdefault("source_listing_id", str(source_listing_id))
        job.discovery_urls = [url for url in (normalize_url(item) for item in job.discovery_urls) if url]
        job.official_url = normalize_url(job.official_url)
        if not job.normalized_title or not job.role_class:
            result = normalize_academic_title(
                job.title,
                country=job.country,
                context=job.description,
                rules=self.config.get("title_ontology"),
                country_rules=self.config.get("country_title_rules"),
            )
            job.normalized_title = job.normalized_title or job.title.casefold().strip()
            job.role_class = job.role_class or result.normalized_role_class
            if result.requires_review and not job.manual_review_state:
                job.manual_review_state = "needs_review"
        if not job.independence_class:
            independence = infer_independence(job.title, job.description or "", country=job.country)
            job.independence_class = independence.independence_class
            job.independence_confidence = independence.confidence
            job.independence_evidence = list(independence.evidence)
        if not job.source_provenance:
            job.source_provenance = [{"source_id": source_id}]
        seen_at = utc_now()
        if not job.first_seen:
            job.first_seen = seen_at
        if not job.last_seen:
            job.last_seen = seen_at
        if not job.canonical_id:
            job.canonical_id = canonical_job_identity(job)
        return job

    def _verify_job(self, job: JobRecord, errors: list[dict[str, Any]]) -> JobRecord:
        return self._verify_job_for_run(job, errors)

    def _verify_job_for_run(
        self,
        job: JobRecord,
        errors: list[dict[str, Any]],
        *,
        run_id: str | None = None,
        current_snapshot: bool = False,
    ) -> JobRecord:
        try:
            result = self.verifier.verify(job)
            if not isinstance(result, VerificationResult):
                result = VerificationResult.from_dict(result)
        except Exception as exc:  # connector boundary: preserve state and continue
            errors.append(_error("official_page_unreachable", str(exc), job_id=job.canonical_id))
            result = VerificationResult(
                status=VerificationStatus.VERIFICATION_FAILED_TRANSIENT,
                source_url=job.official_url,
                confidence=0.0,
                error=str(exc),
            )
        authoritative = verification_is_authoritative(result)
        if result.status in {
            VerificationStatus.VERIFIED_OPEN,
            VerificationStatus.VERIFIED_REOPENED,
        } and not authoritative:
            errors.append(
                _error(
                    "official_source_not_found",
                    "Open-status verification lacked official or corroborated authority",
                    job_id=job.canonical_id,
                    source_id=result.source_id,
                )
            )
        verified = apply_verification(job, result)
        transition_accepted = (
            verified.extra.get("last_verification_transition_accepted") is True
        )
        if run_id:
            verified.extra["last_verification_run_id"] = run_id
        verified.extra["last_verification_attempted_at"] = result.checked_at
        verified.extra["last_verification_authoritative"] = authoritative
        verified.extra["last_verification_result_status"] = result.status.value
        verified.extra["verified_open_in_run"] = bool(
            authoritative
            and transition_accepted
            and result.status
            in {
                VerificationStatus.VERIFIED_OPEN,
                VerificationStatus.VERIFIED_REOPENED,
            }
        )
        if run_id and current_snapshot:
            verified.extra["current_active_run_id"] = run_id
            verified.extra["current_active_verified_open"] = verified.extra[
                "verified_open_in_run"
            ]
        return verified

    def _evaluate_job(self, job: JobRecord) -> JobRecord:
        evaluation = score_academic_fit(job, self.evaluation_profile, self.scoring_config)
        job.fit_score = evaluation.fit_score
        job.tier = evaluation.tier
        job.strongest_matches = list(evaluation.strongest_matches)
        job.meaningful_gaps = list(evaluation.meaningful_gaps)
        job.hard_blockers = list(evaluation.hard_blockers)
        job.evaluation = {
            **evaluation.to_dict(),
            **self.evaluation_versions,
            "evaluated_at": utc_now(),
        }
        job.extra["evaluation_versions"] = self.evaluation_versions
        if evaluation.hard_blockers:
            job.manual_review_state = "blocked"
        elif job.independence_class == "ambiguous" and not job.manual_review_state:
            job.manual_review_state = "needs_review"
        return job

    def _qol_inputs_for_job(self, job: JobRecord) -> Mapping[str, Any]:
        configured = self.config.get("qol_inputs", {})
        if not isinstance(configured, Mapping):
            return {}
        candidates = configured.get("jobs", configured)
        if not isinstance(candidates, Mapping):
            return {}
        for key in (job.canonical_id, job.official_url):
            if key and isinstance(candidates.get(key), Mapping):
                return candidates[key]
        default = configured.get("default")
        return default if isinstance(default, Mapping) else {}

    def _refresh_qol_for_job(
        self,
        job: JobRecord,
        *,
        previous_job: JobRecord | None = None,
        force: bool = False,
    ) -> JobRecord:
        if not requires_full_qol(job):
            return job
        refresh_days = 30
        refresh = self.academic_config.get("qol_refresh", {})
        if isinstance(refresh, Mapping):
            try:
                refresh_days = int(refresh.get("housing_days", 30))
            except (TypeError, ValueError):
                refresh_days = 30
        reasons = qol_refresh_reasons(
            job,
            previous_job=previous_job,
            stale_after_days=max(0, refresh_days),
        )
        if not force and not reasons:
            return job
        inputs = self._qol_inputs_for_job(job)
        compensation = inputs.get("compensation") if isinstance(inputs, Mapping) else None
        if not isinstance(compensation, Mapping):
            compensation = {
                "salary_min": job.position.get("salary_min"),
                "salary_max": job.position.get("salary_max"),
                "salary_currency": job.position.get("salary_currency"),
                "salary_period": job.position.get("salary_period"),
                "salary_basis": job.position.get("salary_basis"),
                "salary_evidence_url": job.position.get("salary_evidence_url"),
                "official": job.position.get("salary_is_estimate") is False,
                "employer_retirement_or_super": job.position.get(
                    "employer_retirement_or_super"
                ),
            }
        assessment = build_qol_assessment(
            compensation=compensation,
            take_home=(inputs.get("take_home", {}) if isinstance(inputs, Mapping) else {}),
            country=job.country,
            housing=(inputs.get("housing") if isinstance(inputs, Mapping) else None),
            childcare=(inputs.get("childcare") if isinstance(inputs, Mapping) else None),
            education=(inputs.get("education") if isinstance(inputs, Mapping) else None),
            transport=(inputs.get("transport") if isinstance(inputs, Mapping) else None),
            scenarios=(inputs.get("scenarios", ()) if isinstance(inputs, Mapping) else ()),
            verdicts=(inputs.get("verdicts") if isinstance(inputs, Mapping) else None),
            notes=[f"Refresh trigger: {reason}" for reason in reasons],
            sources=(inputs.get("sources", ()) if isinstance(inputs, Mapping) else ()),
            confidence=(inputs.get("confidence") if isinstance(inputs, Mapping) else None),
        )
        job.extra["qol_assessment"] = assessment
        job.extra["qol_refresh_reasons"] = list(reasons)
        return job

    def _source_settings(self, connector_id: str) -> Mapping[str, Any]:
        for source in self.sources:
            if str(source.get("id") or "") == connector_id:
                return source
        return {}

    def _cadence_days(
        self,
        settings: Mapping[str, Any],
        *,
        institution: bool = False,
    ) -> int | None:
        for key in ("interval_days", "scan_frequency_days", "cadence_days", "scan_frequency"):
            if settings.get(key) is not None:
                try:
                    return max(0, int(settings[key]))
                except (TypeError, ValueError):
                    if key != "scan_frequency":
                        return 0
        if institution:
            priority_tier = str(settings.get("priority_tier") or "").upper()
            if priority_tier == "S":
                return 1
            if priority_tier == "A":
                return 7
        coverage = self.academic_config.get("coverage", {})
        frequency = str(
            settings.get("frequency_class") or settings.get("scan_frequency") or ""
        ).casefold()
        if frequency and isinstance(coverage, Mapping):
            classes = coverage.get("frequency_classes", {})
            selected = classes.get(frequency, {}) if isinstance(classes, Mapping) else {}
            if isinstance(selected, Mapping) and selected.get("interval_days") is not None:
                try:
                    return max(0, int(selected["interval_days"]))
                except (TypeError, ValueError):
                    return 0
        cadence = str(
            settings.get("expected_update_cadence")
            or settings.get("cadence")
            or ""
        ).casefold().replace("-", "_").replace(" ", "_")
        named = {
            "daily": 1,
            "every_day": 1,
            "every_three_days": 3,
            "every_3_days": 3,
            "weekly": 7,
            "on_demand": None,
        }
        if cadence in named:
            return named[cadence]
        if institution and isinstance(coverage, Mapping):
            target = coverage.get("target_institutions", {})
            if isinstance(target, Mapping) and target.get("default_interval_days") is not None:
                try:
                    return max(0, int(target["default_interval_days"]))
                except (TypeError, ValueError):
                    return 0
        return 0

    @staticmethod
    def _coverage_is_due(
        previous: Any,
        interval_days: int | None,
        now: datetime,
        *,
        force: bool = False,
    ) -> bool:
        if force:
            return True
        if interval_days is None:
            return False
        if interval_days <= 0 or previous is None:
            return True
        last = _as_datetime(
            get_value(previous, "last_attempted", "last_successful", default=None)
        )
        return last is None or now >= last + timedelta(days=interval_days)

    @staticmethod
    def _next_due(now: datetime, interval_days: int | None) -> str | None:
        if interval_days is None:
            return None
        return (now + timedelta(days=max(0, interval_days))).isoformat().replace(
            "+00:00", "Z"
        )

    @staticmethod
    def _batch_visit_details(batch: DiscoveryBatch) -> tuple[bool, list[str], list[str]]:
        metadata = batch.metadata if isinstance(batch.metadata, Mapping) else {}
        pages: list[str] = []
        queries: list[str] = []
        for key in ("official_pages_checked", "visited_urls", "pages_checked"):
            pages.extend(_string_values(metadata.get(key)))
        for key in ("search_queries_checked", "queries_checked"):
            queries.extend(_string_values(metadata.get(key)))
        explicit = any(
            bool(metadata.get(key))
            for key in (
                "scan_completed",
                "institution_visited",
                "retrieval_completed",
                "visited",
            )
        )
        visited = bool(batch.candidates or batch.completed_at or explicit or pages or queries)
        return visited, list(dict.fromkeys(pages)), list(dict.fromkeys(queries))

    @staticmethod
    def _is_current_candidate(job: JobRecord) -> bool:
        lifecycle = str(job.lifecycle_status or "").casefold()
        return not job.rejected and lifecycle not in {
            "closed",
            "expired",
            "withdrawn",
            "closed_expired",
        }

    def _reverification_interval_days(self, job: JobRecord) -> int:
        coverage = self.academic_config.get("coverage", {})
        configured = (
            coverage.get("reverify_active", {})
            if isinstance(coverage, Mapping)
            else {}
        )
        if not isinstance(configured, Mapping):
            return 0
        tier = str(job.tier or "").casefold().replace(" ", "_")
        key = {
            "tier_1": "tier_1_interval_days",
            "tier1": "tier_1_interval_days",
            "tier_2": "tier_2_interval_days",
            "tier2": "tier_2_interval_days",
            "watchlist": "watchlist_interval_days",
        }.get(tier, "watchlist_interval_days")
        try:
            return max(0, int(configured.get(key, 0)))
        except (TypeError, ValueError):
            return 0

    def _reverification_is_due(self, job: JobRecord, now: datetime) -> bool:
        interval_days = self._reverification_interval_days(job)
        if interval_days <= 0:
            return True
        last_attempt = _as_datetime(
            job.extra.get("last_verification_attempted_at") or job.last_verified
        )
        return last_attempt is None or now >= last_attempt + timedelta(days=interval_days)

    def _weekly_blind_spots(
        self,
        jobs: Sequence[JobRecord],
        errors: Sequence[Mapping[str, Any]],
        *,
        run_id: str,
        now: datetime,
    ) -> list[str]:
        """Summarize cross-run blind spots without treating absence as success."""

        week_start = now - timedelta(days=7)
        parser_signatures: Counter[str] = Counter()
        for run in self.state.list_runs():
            if run.run_id == run_id:
                continue
            started_at = _as_datetime(run.started_at)
            if started_at is None or not week_start <= started_at <= now:
                continue
            for error in run.errors:
                if str(error.get("category", "")).casefold() != "parser_error":
                    continue
                signature = str(
                    error.get("message_id")
                    or error.get("message")
                    or "unknown-parser-error"
                )
                parser_signatures[signature] += 1
        for error in errors:
            if str(error.get("category", "")).casefold() != "parser_error":
                continue
            signature = str(
                error.get("message_id")
                or error.get("message")
                or "unknown-parser-error"
            )
            parser_signatures[signature] += 1

        repeated = sorted(
            signature
            for signature, count in parser_signatures.items()
            if count >= 2
        )
        repeated_line = (
            f"- Repeated parser failures: {len(repeated)} repeated signature(s) "
            "in the last 7 days."
            if repeated
            else "- Repeated parser failures: none in the last 7 days."
        )

        candidates = [job for job in jobs if self._is_current_candidate(job)]
        single_source = []
        for job in candidates:
            source_ids = {
                str(row.get("source_id"))
                for row in job.source_provenance
                if isinstance(row, Mapping) and row.get("source_id")
            }
            if len(source_ids) <= 1:
                single_source.append(job)
        candidate_count = len(candidates)
        single_source_ratio = (
            len(single_source) / candidate_count if candidate_count else 0.0
        )

        unknown_deadlines = [
            job
            for job in candidates
            if not job.deadline
            or str(job.deadline_type or "unknown").casefold()
            in {"unknown", "unconfirmed", "tbd"}
        ]
        unknown_deadline_ratio = (
            len(unknown_deadlines) / candidate_count if candidate_count else 0.0
        )

        stale_jobs: list[JobRecord] = []
        for job in candidates:
            last_verified = _as_datetime(job.last_verified)
            interval_days = self._reverification_interval_days(job)
            fresh_in_run = bool(
                job.extra.get("last_verification_run_id") == run_id
                and job.extra.get("last_verification_authoritative") is True
                and job.extra.get("last_verification_transition_accepted") is True
            )
            if fresh_in_run:
                continue
            if (
                last_verified is None
                or last_verified > now
                or interval_days <= 0
                or now >= last_verified + timedelta(days=interval_days)
            ):
                stale_jobs.append(job)

        return [
            repeated_line,
            "- Single-source dependence: "
            f"{len(single_source)}/{candidate_count} current candidate(s) "
            f"({single_source_ratio:.1%}).",
            "- Unknown-deadline ratio: "
            f"{len(unknown_deadlines)}/{candidate_count} current candidate(s) "
            f"({unknown_deadline_ratio:.1%}).",
            "- Stale official verification: "
            f"{len(stale_jobs)}/{candidate_count} current candidate(s) exceed "
            "their configured cadence.",
        ]

    @staticmethod
    def _is_current_active_for_run(job: JobRecord, run_id: str) -> bool:
        return bool(
            job.extra.get("current_active_run_id") == run_id
            and job.extra.get("current_active_verified_open") is True
            and job.extra.get("last_verification_authoritative") is True
            and job.extra.get("last_verification_transition_accepted") is True
            and job.verification_status
            in {
                VerificationStatus.VERIFIED_OPEN,
                VerificationStatus.VERIFIED_REOPENED,
            }
            and str(job.lifecycle_status or "").casefold() in {"open", "reopened", "active"}
            and str(job.tier or "") in {"Tier 1", "Tier 2"}
            and not job.rejected
            and not job.hard_blockers
            and str(job.manual_review_state or "").casefold()
            not in {"blocked", "not_interested", "rejected"}
        )

    def _deadline_alerts(
        self,
        jobs: Iterable[JobRecord],
        *,
        today: date | None = None,
    ) -> list[JobRecord]:
        current = today or _now().date()
        warning_days = set(self.deadline_warning_days)
        rows: list[tuple[date, JobRecord]] = []
        for job in jobs:
            if job.deadline_type == "rolling" or not job.deadline:
                continue
            try:
                deadline = date.fromisoformat(str(job.deadline)[:10])
            except ValueError:
                continue
            if (deadline - current).days in warning_days:
                rows.append((deadline, job))
        return [
            job
            for _, job in sorted(
                rows, key=lambda item: (item[0], item[1].organization_name)
            )
        ]

    def _apply_email_label_plan(self, plan: GmailLabelPlan) -> bool:
        if self.email_connector is None:
            return False
        apply_plan = getattr(self.email_connector, "apply_label_plan", None)
        if callable(apply_plan):
            return _write_confirmed(apply_plan(plan))

        # Use configured names only for routing to the protocol's semantic
        # methods; Processed is deliberately applied last.
        configured = {**DEFAULT_GMAIL_LABELS, **dict(self.email_labels)}
        labels = {
            "processed": configured["processed"],
            "needs_review": configured["needs_review"],
            "error": configured["error"],
        }
        for label in plan.add_labels:
            if label == labels["processed"]:
                continue
            if label == labels["error"]:
                if not _write_confirmed(
                    self.email_connector.mark_error(plan.message_id, plan.reason)
                ):
                    return False
            else:
                if not _write_confirmed(
                    self.email_connector.mark_needs_review(
                        plan.message_id, plan.reason
                    )
                ):
                    return False
        if plan.processed:
            if not _write_confirmed(
                self.email_connector.mark_processed(plan.message_id)
            ):
                return False
        elif not plan.add_labels:
            if not _write_confirmed(
                self.email_connector.mark_needs_review(plan.message_id, plan.reason)
            ):
                return False
        return True

    def _discover_from_connectors(
        self,
        run_id: str,
        run_type: str,
        metrics: dict[str, int],
        errors: list[dict[str, Any]],
        *,
        source_filter: str | None = None,
        institution_filter: str | None = None,
    ) -> tuple[list[Any], list[SourceCoverageRecord], list[InstitutionCoverageRecord]]:
        query_budget: int | Mapping[str, Any] = self.academic_config.get("query_budget", 50)
        source_override = self.config.get("source_overrides", self.config.get("source_overrides.example", {}))
        if isinstance(source_override, Mapping):
            query_settings = source_override.get("query_generation", {})
            if isinstance(query_settings, Mapping) and query_settings.get("maximum_queries_per_source_per_run"):
                per_source = int(query_settings["maximum_queries_per_source_per_run"])
                query_budget = {"total": max(1, per_source * max(1, len(self.sources))), "per_source": per_source}
        queries = generate_academic_queries(
            self.evaluation_profile,
            self.sources,
            self.institutions,
            query_budget,
            rotation_offset=len(self.state.list_runs()),
        )
        discovered: list[Any] = []
        source_coverage: list[SourceCoverageRecord] = []
        institution_coverage: list[InstitutionCoverageRecord] = []
        now_dt = _now()
        now = now_dt.isoformat().replace("+00:00", "Z")
        prior_sources = {
            row.source_id: row for row in self.state.list_source_coverage()
        }
        prior_institutions = {
            row.institution.casefold(): row
            for row in self.state.list_institution_coverage()
        }
        matched_source_connector = False
        covered_source_ids: set[str] = set()
        configured_connector_ids = {
            str(
                getattr(
                    connector,
                    "connector_id",
                    getattr(connector, "id", type(connector).__name__),
                )
            )
            for connector in self.discovery_connectors
        }

        for connector in self.discovery_connectors:
            connector_id = str(
                getattr(
                    connector,
                    "connector_id",
                    getattr(connector, "id", type(connector).__name__),
                )
            )
            if source_filter and connector_id != source_filter:
                continue
            settings = self._source_settings(connector_id)
            if settings and not _source_enabled(settings):
                if source_filter:
                    covered_source_ids.add(connector_id)
                    source_coverage.append(
                        SourceCoverageRecord(
                            source_id=connector_id,
                            status="disabled",
                            error="Source is disabled by configuration",
                        )
                    )
                continue
            matched_source_connector = True
            covered_source_ids.add(connector_id)
            interval_days = self._cadence_days(settings)
            if not self._coverage_is_due(
                prior_sources.get(connector_id),
                interval_days,
                now_dt,
                force=bool(source_filter),
            ):
                continue
            metrics["sources_due"] += 1
            connector_queries = [
                query for query in queries if query.source_id in {None, connector_id}
            ]
            if not connector_queries:
                connector_queries = [None]
            attempted = 0
            successful = 0
            incomplete = 0
            items_seen = 0
            new_items = 0
            feed_health: list[Any] = []
            failure_messages: list[str] = []
            metrics["sources_attempted"] += 1
            for query in connector_queries:
                request = DiscoveryRequest(
                    run_id=run_id,
                    source_id=connector_id,
                    query=query.text if query else None,
                    limit=None,
                    context={
                        "run_type": run_type,
                        "query_family": query.family if query else None,
                    },
                )
                attempted += 1
                try:
                    batch = connector.discover(request)
                    if not isinstance(batch, DiscoveryBatch):
                        if isinstance(batch, Mapping) and "candidates" in batch:
                            batch = DiscoveryBatch.from_dict(batch)
                        else:
                            batch = DiscoveryBatch.from_jobs(connector_id, batch)
                    discovered.extend(
                        _DiscoveryPayload(copy.deepcopy(item), connector_id)
                        for item in batch.candidates
                    )
                    items_seen += len(batch.candidates)
                    metadata = batch.metadata if isinstance(batch.metadata, Mapping) else {}
                    if isinstance(metadata.get("feed_health"), list):
                        feed_health.extend(copy.deepcopy(metadata["feed_health"]))
                    try:
                        new_items += int(metadata.get("new_items", 0) or 0)
                    except (TypeError, ValueError):
                        pass
                    metrics["raw_candidates"] += len(batch.candidates)
                    if batch.errors:
                        for item in batch.errors:
                            category = (
                                str(item.get("category", "source_unavailable"))
                                if isinstance(item, Mapping)
                                else "source_unavailable"
                            )
                            message = (
                                str(item.get("message", item))
                                if isinstance(item, Mapping)
                                else str(item)
                            )
                            failure_messages.append(message)
                            errors.append(
                                _error(category, message, source_id=connector_id)
                            )
                    else:
                        visited, _, _ = self._batch_visit_details(batch)
                        if visited:
                            successful += 1
                        else:
                            incomplete += 1
                            failure_messages.append(
                                "no confirmed retrieval or visit evidence"
                            )
                except Exception as exc:
                    failure_messages.append(str(exc))
                    errors.append(
                        _error("source_unavailable", str(exc), source_id=connector_id)
                    )
            if successful:
                metrics["sources_successful"] += 1
            else:
                metrics["sources_failed"] += 1
            status = (
                "success"
                if attempted and successful == attempted
                else "partial"
                if successful
                else "incomplete"
                if incomplete
                else "failed"
            )
            source_coverage.append(
                SourceCoverageRecord.from_dict(
                    {
                        "source_id": connector_id,
                        "last_attempted": now,
                        "last_successful": now if successful else None,
                        "status": status,
                        "items_seen": items_seen,
                        "error": "; ".join(dict.fromkeys(failure_messages)) or None,
                        "next_due": self._next_due(now_dt, interval_days),
                        "new_items": new_items,
                        "parser_errors": sum(
                            1
                            for item in feed_health
                            if isinstance(item, Mapping)
                            and item.get("status") == "failed"
                        ),
                        "feed_health": feed_health,
                    }
                )
            )

        catalog_ids: set[str] = set()
        for settings in self.sources:
            connector_id = str(settings.get("id") or "").strip()
            if not connector_id or connector_id in catalog_ids:
                continue
            catalog_ids.add(connector_id)
            if source_filter and connector_id != source_filter:
                continue
            if not _source_enabled(settings) or not settings.get(
                "supports_direct_search", True
            ):
                continue
            if connector_id in configured_connector_ids or connector_id in covered_source_ids:
                continue
            interval_days = self._cadence_days(settings)
            if not self._coverage_is_due(
                prior_sources.get(connector_id),
                interval_days,
                now_dt,
                force=bool(source_filter),
            ):
                continue
            matched_source_connector = matched_source_connector or bool(source_filter)
            covered_source_ids.add(connector_id)
            metrics["sources_due"] += 1
            metrics["sources_failed"] += 1
            message = f"No discovery connector configured for source {connector_id}"
            errors.append(
                _error("source_unavailable", message, source_id=connector_id)
            )
            source_coverage.append(
                SourceCoverageRecord(
                    source_id=connector_id,
                    status="not_configured",
                    error=message,
                    next_due=self._next_due(now_dt, interval_days),
                )
            )

        if source_filter and not matched_source_connector and source_filter not in covered_source_ids:
            metrics["sources_due"] += 1
            metrics["sources_failed"] += 1
            message = f"No discovery connector configured for source {source_filter}"
            errors.append(
                _error("source_unavailable", message, source_id=source_filter)
            )
            source_coverage.append(
                SourceCoverageRecord(
                    source_id=source_filter,
                    status="not_configured",
                    error=message,
                )
            )

        selected_institutions = self.institutions
        if institution_filter:
            selected_institutions = [
                row
                for row in selected_institutions
                if str(row.get("name", "")).casefold()
                == institution_filter.casefold()
            ]
            if not selected_institutions:
                selected_institutions = [
                    {"name": institution_filter, "enabled": True}
                ]
        for institution in selected_institutions:
            name = str(institution.get("name") or "").strip()
            interval_days = self._cadence_days(institution, institution=True)
            if not self._coverage_is_due(
                prior_institutions.get(name.casefold()),
                interval_days,
                now_dt,
                force=bool(institution_filter),
            ):
                continue
            metrics["institutions_due"] += 1
            pages: list[str] = []
            checked_queries: list[str] = []
            success_count = 0
            attempted_count = 0
            failed_count = 0
            incomplete_count = 0
            notes: list[str] = []
            broken_urls: list[str] = []
            fallback_queries_used: list[str] = []
            replacement_url_evidence: list[Any] = []
            matching_jobs_found = 0
            scan_plan = plan_target_scan(
                institution,
                prior_institutions.get(name.casefold()),
                now=now_dt,
            )
            for connector in self.discovery_connectors:
                connector_id = str(
                    getattr(
                        connector,
                        "connector_id",
                        getattr(connector, "id", type(connector).__name__),
                    )
                )
                if source_filter and connector_id != source_filter:
                    continue
                if getattr(connector, "supports_institution_scan", True) is not True:
                    continue
                settings = self._source_settings(connector_id)
                if settings and not _source_enabled(settings):
                    continue
                attempted_count += 1
                request = DiscoveryRequest(
                    run_id=run_id,
                    source_id=connector_id,
                    institution=name,
                    context={
                        "run_type": run_type,
                        "institution": dict(institution),
                        "target_scan_plan": scan_plan.to_dict(),
                    },
                )
                try:
                    batch = connector.discover(request)
                    if not isinstance(batch, DiscoveryBatch):
                        if isinstance(batch, Mapping) and "candidates" in batch:
                            batch = DiscoveryBatch.from_dict(batch)
                        else:
                            batch = DiscoveryBatch.from_jobs(connector_id, batch)
                    discovered.extend(
                        _DiscoveryPayload(copy.deepcopy(item), connector_id)
                        for item in batch.candidates
                    )
                    metrics["raw_candidates"] += len(batch.candidates)
                    matching_jobs_found += len(batch.candidates)
                    metadata = batch.metadata if isinstance(batch.metadata, Mapping) else {}
                    broken_urls.extend(_string_values(metadata.get("broken_urls")))
                    fallback_queries_used.extend(
                        _string_values(metadata.get("fallback_queries_used"))
                    )
                    replacement_url_evidence.extend(
                        metadata.get("replacement_url_evidence", [])
                        if isinstance(metadata.get("replacement_url_evidence"), list)
                        else []
                    )
                    if batch.errors:
                        failed_count += 1
                        for item in batch.errors:
                            category = (
                                str(item.get("category", "source_unavailable"))
                                if isinstance(item, Mapping)
                                else "source_unavailable"
                            )
                            message = (
                                str(item.get("message", item))
                                if isinstance(item, Mapping)
                                else str(item)
                            )
                            notes.append(f"{connector_id}: {message}")
                            errors.append(
                                _error(
                                    category,
                                    message,
                                    source_id=connector_id,
                                    institution=name,
                                )
                            )
                        continue
                    _, visited_pages, visited_queries = self._batch_visit_details(batch)
                    official_ats_domains = institution.get(
                        "official_ats_domains", ()
                    )
                    if isinstance(official_ats_domains, str):
                        official_ats_domains = (official_ats_domains,)
                    visited_pages = [
                        page
                        for page in visited_pages
                        if is_authoritative_target_url(
                            page,
                            institution,
                            official_ats_domains=official_ats_domains,
                        )
                    ]
                    visited = bool(visited_pages)
                    if not visited:
                        incomplete_count += 1
                        notes.append(
                            f"{connector_id}: no authoritative institution-page visit evidence"
                        )
                        continue
                    success_count += 1
                    pages.extend(visited_pages)
                    checked_queries.extend(
                        visited_queries or [f"{connector_id}:institution_scan"]
                    )
                except Exception as exc:
                    failed_count += 1
                    notes.append(f"{connector_id}: {exc}")
                    errors.append(
                        _error(
                            "source_unavailable",
                            str(exc),
                            source_id=connector_id,
                            institution=name,
                        )
                    )
            if attempted_count == 0:
                status = "not_attempted"
                notes.append("No compatible discovery connector was configured")
            elif success_count == attempted_count:
                status = "success"
            elif success_count:
                status = "partial"
            elif failed_count:
                status = "failed"
            else:
                status = "incomplete"
            if success_count:
                metrics["institutions_checked"] += 1
            institution_coverage.append(
                InstitutionCoverageRecord.from_dict(
                    {
                        "institution": name,
                        "last_attempted": now if attempted_count else None,
                        "last_successful": now if success_count else None,
                        "official_pages_checked": list(dict.fromkeys(pages)),
                        "search_queries_checked": list(
                            dict.fromkeys(checked_queries)
                        ),
                        "status": status,
                        "notes": notes,
                        "next_due": self._next_due(now_dt, interval_days),
                        "failed_connectors": failed_count,
                        "incomplete_connectors": incomplete_count,
                        "known_urls_checked": list(dict.fromkeys(pages)),
                        "broken_urls": list(dict.fromkeys(broken_urls)),
                        "domain_fallback_used": bool(fallback_queries_used),
                        "fallback_queries_used": list(
                            dict.fromkeys(fallback_queries_used)
                        ),
                        "replacement_url_evidence": replacement_url_evidence,
                        "matching_jobs_found": matching_jobs_found,
                        "target_retained": True,
                    }
                )
            )
        return discovered, source_coverage, institution_coverage

    def _ingest_email(
        self,
        metrics: dict[str, int],
        errors: list[dict[str, Any]],
    ) -> tuple[list[DiscoveryCandidate], list[EmailParseResult]]:
        if self.email_connector is None:
            return [], []
        processed_ids = self._processed_message_ids()
        durable_progress = self._email_candidate_progress()
        candidates: list[DiscoveryCandidate] = []
        results: list[EmailParseResult] = []
        email_settings = self.academic_config.get("email", {})
        limit = (
            email_settings.get("max_messages_per_run", 100)
            if isinstance(email_settings, Mapping)
            else 100
        )
        try:
            messages = list(self.email_connector.fetch_unprocessed(limit=int(limit)))
        except Exception as exc:
            errors.append(_error("authentication_error", str(exc), connector="email"))
            return [], []
        metrics["emails_scanned"] += len(messages)
        for message in messages:
            if isinstance(message, AlertMessage):
                payload: Any = {
                    "message_id": message.message_id,
                    "subject": message.subject,
                    "body": message.body,
                    "html": message.html,
                    "sender": message.sender,
                    "headers": dict(message.headers),
                    "links": list(message.links),
                    "source_id": message.source_id,
                }
                source_id = message.source_id or "email_alert"
            else:
                payload = message
                source_id = "email_alert"
            result = parse_academic_alert_result(
                payload,
                source_id=source_id,
                processed_message_ids=processed_ids,
                email_source_registry=self.email_source_registry,
            )
            if result.already_processed:
                continue
            result.handled_candidate_ids.update(
                durable_progress.get(result.message_id, set())
            )
            results.append(result)
            candidates.extend(
                candidate
                for candidate in result.candidates
                if candidate.event_id not in result.handled_candidate_ids
            )
            if result.parse_failures:
                metrics["email_parse_failures"] += len(result.parse_failures)
                for failure in result.parse_failures:
                    errors.append(_error("parser_error", failure, message_id=result.message_id))
                result.failures_recorded = True
        return candidates, results

    def _deliver(
        self,
        report: str,
        run_id: str,
        run_type: str,
        metrics: dict[str, int],
        errors: list[dict[str, Any]],
    ) -> None:
        for connector in self.report_connectors:
            channel = str(getattr(connector, "connector_id", type(connector).__name__))
            try:
                result = connector.deliver(report, metadata={"run_id": run_id, "run_type": run_type})
                if not isinstance(result, DeliveryResult):
                    result = DeliveryResult.from_dict(result)
                if result.confirmed:
                    metrics["report_delivery_successes"] += 1
                else:
                    metrics["report_delivery_failures"] += 1
                    errors.append(_error("report_delivery_error", result.error or "delivery not confirmed", channel=channel))
            except Exception as exc:
                metrics["report_delivery_failures"] += 1
                errors.append(_error("report_delivery_error", str(exc), channel=channel))

    def _run(
        self,
        run_type: str,
        *,
        source_filter: str | None = None,
        institution_filter: str | None = None,
        deliver: bool = True,
        mark_email: bool = True,
        ingest_email: bool = True,
        discover: bool = True,
    ) -> WorkflowResult:
        config_errors = self.validate_config(strict_contracts=False)
        if config_errors:
            raise ValueError("Invalid Academic PI configuration: " + "; ".join(config_errors))
        started = _now()
        run_id = f"academic-pi-{run_type}-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        metric_names = (
            "emails_scanned", "emails_processed", "email_parse_failures",
            "sources_due", "sources_attempted", "sources_successful", "sources_failed",
            "institutions_due", "institutions_checked", "raw_candidates", "deduped_candidates",
            "new_jobs", "existing_jobs_updated", "material_changes", "verified_open",
            "verified_closed", "verification_pending", "tier1_active", "tier2_active",
            "watchlist_active", "deadline_alerts", "report_delivery_successes", "report_delivery_failures",
        )
        metrics = {name: 0 for name in metric_names}
        errors: list[dict[str, Any]] = []
        email_candidates, email_results = (
            self._ingest_email(metrics, errors) if ingest_email else ([], [])
        )
        if discover:
            web_candidates, source_coverage, institution_coverage = self._discover_from_connectors(
                run_id,
                run_type,
                metrics,
                errors,
                source_filter=source_filter,
                institution_filter=institution_filter,
            )
        else:
            web_candidates, source_coverage, institution_coverage = [], [], []
        if ingest_email and self.email_connector is not None:
            auth_failed = any(
                error.get("category") == "authentication_error" for error in errors
            )
            real_alerts = sum(
                result.message_class.value == "JOB_ALERT" for result in email_results
            )
            prior_email = next(
                (
                    row
                    for row in self.state.list_source_coverage()
                    if row.source_id == "email_alert"
                ),
                None,
            )
            previously_active = bool(
                prior_email
                and (
                    prior_email.status == "active"
                    or prior_email.extra.get("first_real_alert_seen") is True
                )
            )
            source_coverage.append(
                SourceCoverageRecord.from_dict(
                    {
                        "source_id": "email_alert",
                        "last_attempted": started.isoformat().replace("+00:00", "Z"),
                        "last_successful": (
                            None
                            if auth_failed
                            else started.isoformat().replace("+00:00", "Z")
                        ),
                        "status": (
                            "auth_error"
                            if auth_failed
                            else "active"
                            if real_alerts or previously_active
                            else "configured_unconfirmed"
                        ),
                        "items_seen": len(email_results),
                        "error": "email authentication failed" if auth_failed else None,
                        "first_real_alert_seen": bool(real_alerts or previously_active),
                        "real_alerts_seen": real_alerts,
                    }
                )
            )
        raw_candidates: list[Any] = [*email_candidates, *web_candidates]
        metrics["raw_candidates"] = max(metrics["raw_candidates"], len(raw_candidates))
        seen_ids: set[str] = set()
        verification_attempted_ids: set[str] = set()
        run_jobs: list[JobRecord] = []
        new_jobs: list[JobRecord] = []
        changes: list[Any] = []

        for raw in raw_candidates:
            try:
                if isinstance(raw, _DiscoveryPayload):
                    payload = raw.payload
                    discovery_source_id = raw.source_id
                else:
                    payload = raw
                    discovery_source_id = str(
                        getattr(raw, "source_id", "email_alert") or "email_alert"
                    )
                job = self._coerce_job(
                    payload,
                    source_id=discovery_source_id,
                    trusted=False,
                )
                previous_job = (
                    self.state.get_job(job.canonical_id)
                    if job.canonical_id
                    else None
                )
                job = self._verify_job_for_run(
                    job, errors, run_id=run_id, current_snapshot=True
                )
                job = self._evaluate_job(job)
                job = self._refresh_qol_for_job(
                    job, previous_job=previous_job
                )
                result = self.state.upsert_job(job)
                if result.action == "inserted":
                    metrics["new_jobs"] += 1
                elif result.action == "updated":
                    metrics["existing_jobs_updated"] += 1
                if result.previous and result.record:
                    detected = detect_material_changes(
                        result.previous,
                        result.record,
                        fields=self.material_change_fields,
                        source="academic_pi",
                    )
                    changes.extend(detected)
                    metrics["material_changes"] += len(detected)
                stored = self.state.get_job(result.job_id or job.canonical_id or "") or job
                if stored.canonical_id:
                    verification_attempted_ids.add(stored.canonical_id)
                if stored.canonical_id and stored.canonical_id not in seen_ids:
                    seen_ids.add(stored.canonical_id)
                    run_jobs.append(stored)
                    if result.action == "inserted":
                        new_jobs.append(stored)
                event_id = job.extra.get("ingestion_event_id")
                if event_id:
                    for email_result in email_results:
                        if any(candidate.event_id == event_id for candidate in email_result.candidates):
                            email_result.handled_candidate_ids.add(str(event_id))
            except Exception as exc:
                errors.append(
                    _error(
                        "state_write_error",
                        str(exc),
                        message_id=getattr(
                            raw.payload if isinstance(raw, _DiscoveryPayload) else raw,
                            "message_id",
                            None,
                        ),
                        candidate_event_id=getattr(
                            raw.payload if isinstance(raw, _DiscoveryPayload) else raw,
                            "event_id",
                            None,
                        ),
                    )
                )

        metrics["deduped_candidates"] = len(run_jobs)

        # A current-active snapshot is run-scoped. Reverify every retained role
        # whose configured tier cadence is due, including roles unchanged by
        # discovery today. Non-due and failed roles cannot enter this run's
        # snapshot because active membership always requires this run's marker.
        for existing in self.state.list_jobs():
            if (
                not existing.canonical_id
                or existing.canonical_id in verification_attempted_ids
                or not self._is_current_candidate(existing)
                or not self._reverification_is_due(existing, started)
            ):
                continue
            verified = self._verify_job_for_run(
                existing, errors, run_id=run_id, current_snapshot=True
            )
            evaluated = self._evaluate_job(verified)
            evaluated = self._refresh_qol_for_job(
                evaluated, previous_job=existing
            )
            try:
                upserted = self.state.upsert_job(evaluated)
                verification_attempted_ids.add(
                    upserted.job_id or existing.canonical_id
                )
                if upserted.previous and upserted.record:
                    detected = detect_material_changes(
                        upserted.previous,
                        upserted.record,
                        fields=self.material_change_fields,
                        source="academic_pi_reverification",
                    )
                    changes.extend(detected)
                    metrics["material_changes"] += len(detected)
            except Exception as exc:
                errors.append(
                    _error(
                        "state_write_error",
                        str(exc),
                        job_id=existing.canonical_id,
                        operation="current_candidate_reverification",
                    )
                )

        for coverage in source_coverage:
            try:
                self.state.upsert_source_coverage(coverage)
            except Exception as exc:
                errors.append(
                    _error(
                        "state_write_error",
                        str(exc),
                        source_id=coverage.source_id,
                    )
                )
        for coverage in institution_coverage:
            try:
                self.state.upsert_institution_coverage(coverage)
            except Exception as exc:
                errors.append(
                    _error(
                        "state_write_error",
                        str(exc),
                        institution=coverage.institution,
                    )
                )

        # Persist candidate progress and parse-failure evidence before any
        # external Gmail mutation.  The same run ID is finalized below, so
        # normal stores still retain one run row.  If this write fails, no
        # Processed/Error label has been applied and the message remains
        # safely retryable.
        if email_results:
            self.state.record_run(
                RunRecord(
                    run_id=run_id,
                    run_type=run_type,
                    started_at=started.isoformat().replace("+00:00", "Z"),
                    status="email_progress_persisted",
                    metrics=copy.deepcopy(metrics),
                    errors=copy.deepcopy(errors),
                    extra={
                        "completed_email_message_ids": [],
                        "email_candidate_progress": {
                            result.message_id: sorted(result.handled_candidate_ids)
                            for result in email_results
                            if result.handled_candidate_ids
                        },
                        "email_parse_failure_ids": [
                            result.message_id
                            for result in email_results
                            if result.parse_failures and result.failures_recorded
                        ],
                        "email_labels_applied": False,
                        "agent_submitted_applications": 0,
                    },
                )
            )

        label_plans: list[GmailLabelPlan] = []
        completed_message_ids: list[str] = []
        label_failure_ids: list[str] = []
        for result in email_results:
            plan = plan_gmail_labels(result, self.email_labels)
            if mark_email and self.email_connector is not None:
                try:
                    label_succeeded = self._apply_email_label_plan(plan)
                    if not label_succeeded:
                        raise RuntimeError("email connector did not confirm label application")
                except Exception as exc:
                    label_failure_ids.append(result.message_id)
                    errors.append(
                        _error(
                            "email_label_error",
                            str(exc),
                            message_id=result.message_id,
                        )
                    )
                    plan = GmailLabelPlan(
                        message_id=plan.message_id,
                        add_labels=plan.add_labels,
                        remove_labels=plan.remove_labels,
                        processed=False,
                        reason=f"label application incomplete: {exc}",
                        archive=False,
                        delete=False,
                    )
                else:
                    if plan.processed:
                        completed_message_ids.append(result.message_id)
                        metrics["emails_processed"] += 1
            label_plans.append(plan)

        all_jobs = self.state.list_jobs()
        current_active = [
            job for job in all_jobs if self._is_current_active_for_run(job, run_id)
        ]
        attempted_this_run = [
            job
            for job in all_jobs
            if job.extra.get("last_verification_run_id") == run_id
        ]
        metrics["tier1_active"] = sum(
            job.tier == "Tier 1" for job in current_active
        )
        metrics["tier2_active"] = sum(
            job.tier == "Tier 2" for job in current_active
        )
        metrics["watchlist_active"] = sum(
            job.tier == "Watchlist"
            and job.extra.get("verified_open_in_run") is True
            and not job.rejected
            and not job.hard_blockers
            for job in attempted_this_run
        )
        metrics["verified_open"] = sum(
            job.extra.get("verified_open_in_run") is True
            for job in attempted_this_run
        )
        metrics["verified_closed"] = sum(
            job.extra.get("last_verification_authoritative") is True
            and job.extra.get("last_verification_transition_accepted") is True
            and job.extra.get("last_verification_result_status")
            in {
                VerificationStatus.VERIFIED_CLOSED.value,
                VerificationStatus.VERIFIED_EXPIRED.value,
            }
            for job in attempted_this_run
        )
        metrics["verification_pending"] = sum(
            job.extra.get("last_verification_result_status")
            in {
                VerificationStatus.VERIFICATION_PENDING.value,
                VerificationStatus.VERIFICATION_FAILED_TRANSIENT.value,
                VerificationStatus.VERIFICATION_FAILED_PERSISTENT.value,
                VerificationStatus.OFFICIAL_SOURCE_NOT_FOUND.value,
                VerificationStatus.MANUAL_REVIEW_REQUIRED.value,
                VerificationStatus.UNKNOWN.value,
            }
            or job.extra.get("last_verification_authoritative") is not True
            or job.extra.get("last_verification_transition_accepted") is not True
            for job in attempted_this_run
        )
        deadline_jobs = self._deadline_alerts(current_active)
        metrics["deadline_alerts"] = len(deadline_jobs)
        applications = list(self.state.list_applications())
        application_by_job = {application.job_id: application for application in applications}

        def with_application_state(job: JobRecord) -> JobRecord:
            rendered = JobRecord.from_dict(job.to_dict())
            application = application_by_job.get(rendered.canonical_id or "")
            if application is not None:
                rendered.application = application.to_dict()
                if application.package_path:
                    rendered.application["existing_materials"] = [
                        application.package_path
                    ]
            return rendered

        report_jobs = [with_application_state(job) for job in all_jobs]
        report_active = [with_application_state(job) for job in current_active]
        report_new = [with_application_state(job) for job in new_jobs]
        application_counts = Counter(
            str(application.status or "unknown")
            .strip()
            .casefold()
            .replace(" ", "_")
            for application in applications
        )
        metrics["applications_recorded"] = len(applications)
        metrics["applications_submitted_recorded"] = application_counts.get(
            "submitted", 0
        )
        email_backlog = [
            result
            for result in email_results
            if not result.processing_complete
            or result.message_id not in completed_message_ids
        ]

        weekly_new_jobs = report_new
        weekly_changes = list(changes)
        weekly_closed_or_reopened = [
            with_application_state(job)
            for job in all_jobs
            if job.lifecycle_status in {"closed", "expired", "reopened"}
        ]
        if run_type == "weekly":
            week_start = started - timedelta(days=7)

            def in_week(value: Any) -> bool:
                parsed = _as_datetime(value)
                return parsed is not None and week_start <= parsed <= started

            weekly_new_by_id = {
                job.canonical_id: with_application_state(job)
                for job in all_jobs
                if job.canonical_id and in_week(job.first_seen)
            }
            weekly_new_by_id.update(
                {
                    job.canonical_id: with_application_state(job)
                    for job in new_jobs
                    if job.canonical_id
                }
            )
            weekly_new_jobs = list(weekly_new_by_id.values())

            historical_changes = [
                change
                for change in self.state.list_changes()
                if change.change_type == "job_content_change"
                and change.material
                and in_week(change.changed_at)
            ]
            change_rows = [*historical_changes, *changes]
            weekly_changes = list(
                {
                    (
                        change.job_id,
                        change.field,
                        repr(change.old_value),
                        repr(change.new_value),
                    ): change
                    for change in change_rows
                }.values()
            )
            lifecycle_changes = [
                change
                for change in weekly_changes
                if change.field in {"lifecycle_status", "verification_status"}
                and str(change.new_value)
                in {
                    "closed",
                    "expired",
                    "reopened",
                    VerificationStatus.VERIFIED_CLOSED.value,
                    VerificationStatus.VERIFIED_EXPIRED.value,
                    VerificationStatus.VERIFIED_REOPENED.value,
                }
            ]
            changed_job_ids = {change.job_id for change in lifecycle_changes}
            weekly_closed_or_reopened = [
                with_application_state(job)
                for job in all_jobs
                if job.canonical_id in changed_job_ids
            ]

        if run_type == "weekly":
            blind_spots = self._weekly_blind_spots(
                all_jobs,
                errors,
                run_id=run_id,
                now=started,
            )
            report = render_weekly_report(
                report_jobs,
                current_active_jobs=report_active,
                new_jobs=weekly_new_jobs,
                material_changes=weekly_changes,
                source_coverage=self.state.list_source_coverage(),
                institution_coverage=self.state.list_institution_coverage(),
                email_backlog=email_backlog,
                errors=errors,
                closed_or_reopened=weekly_closed_or_reopened,
                applications=applications,
                blind_spots=blind_spots,
                metrics=metrics,
            )
        else:
            report = render_daily_report(
                report_jobs,
                current_active_jobs=report_active,
                new_jobs=report_new,
                material_changes=changes,
                verification_errors=errors,
                coverage=[*source_coverage, *institution_coverage],
                deadline_alerts=deadline_jobs,
                metrics=metrics,
                applications=applications,
            )
        if deliver:
            self._deliver(report, run_id, run_type, metrics, errors)
        completed = utc_now()
        self.state.record_run(
            RunRecord(
                run_id=run_id,
                run_type=run_type,
                started_at=started.isoformat().replace("+00:00", "Z"),
                completed_at=completed,
                status="completed_with_errors" if errors else "completed",
                metrics=metrics,
                errors=errors,
                extra={
                    "completed_email_message_ids": completed_message_ids,
                    "email_candidate_progress": {
                        result.message_id: sorted(result.handled_candidate_ids)
                        for result in email_results
                        if result.handled_candidate_ids
                    },
                    "email_label_failure_ids": label_failure_ids,
                    "email_parse_failure_ids": [
                        result.message_id
                        for result in email_results
                        if result.parse_failures and result.failures_recorded
                    ],
                    "email_labels_applied": bool(mark_email and email_results),
                    "application_status_counts": dict(application_counts),
                    "agent_submitted_applications": 0,
                },
            )
        )
        return WorkflowResult(
            run_id=run_id,
            run_type=run_type,
            metrics=metrics,
            report=report,
            jobs=run_jobs,
            label_plans=label_plans,
            errors=[item["message"] for item in errors],
            submitted_applications=0,
        )

    def daily(self) -> WorkflowResult:
        return self._run("daily")

    def weekly(self) -> WorkflowResult:
        return self._run("weekly")

    def scan_source(self, source_id: str) -> WorkflowResult:
        return self._run("manual_source", source_filter=source_id)

    def scan_rss(self, source_id: str) -> WorkflowResult:
        settings = self._source_settings(source_id)
        if not settings or not settings.get("supports_rss", False):
            raise ValueError(f"Source is not configured for RSS: {source_id}")
        return self._run(
            "manual_rss",
            source_filter=source_id,
            ingest_email=False,
        )

    def scan_email(self) -> WorkflowResult:
        return self._run("manual_email", discover=False)

    def scan_institution(self, institution: str) -> WorkflowResult:
        return self._run("manual_institution", institution_filter=institution)

    def _find_job(self, job_id_or_url: str) -> JobRecord:
        direct = self.state.get_job(job_id_or_url)
        if direct is not None:
            return direct
        normalized = normalize_url(job_id_or_url)
        for job in self.state.list_jobs():
            if normalized and normalized in {normalize_url(job.official_url), *(normalize_url(url) for url in job.discovery_urls)}:
                return job
        raise KeyError(f"Unknown job: {job_id_or_url}")

    def verify(self, job_id_or_url: str) -> JobRecord:
        try:
            job = self._find_job(job_id_or_url)
        except KeyError:
            url = normalize_url(job_id_or_url)
            host = urlparse(url or "").hostname
            if not url or not host:
                raise
            job = JobRecord(
                title="Academic opportunity pending verification",
                organization=host.removeprefix("www."),
                official_url=url,
                discovery_urls=[url],
                lifecycle_status="unknown",
                verification_status=VerificationStatus.VERIFICATION_PENDING,
                source_provenance=[{"source_id": "manual", "url": url}],
            )
        errors: list[dict[str, Any]] = []
        verification_id = (
            f"academic-pi-manual-verify-{_now().strftime('%Y%m%dT%H%M%SZ')}-"
            f"{uuid4().hex[:8]}"
        )
        job = self._verify_job_for_run(job, errors, run_id=verification_id)
        job = self._coerce_job(job, source_id="manual")
        if errors:
            job.extra["manual_verification_errors"] = errors
        result = self.state.upsert_job(job)
        return self.state.get_job(result.job_id or job.canonical_id or "") or job

    def evaluate(self, job_id_or_url: str) -> JobRecord:
        errors: list[dict[str, Any]] = []
        evaluation_id = (
            f"academic-pi-manual-evaluate-{_now().strftime('%Y%m%dT%H%M%SZ')}-"
            f"{uuid4().hex[:8]}"
        )
        job = self._verify_job_for_run(
            self._find_job(job_id_or_url), errors, run_id=evaluation_id
        )
        if errors:
            job.extra["manual_verification_errors"] = errors
        verified_write = self.state.upsert_job(job)
        stored = self.state.get_job(
            verified_write.job_id or job.canonical_id or ""
        ) or job
        if not (
            stored.extra.get("last_verification_run_id") == evaluation_id
            and stored.extra.get("verified_open_in_run") is True
            and stored.extra.get("last_verification_authoritative") is True
            and stored.extra.get("last_verification_transition_accepted") is True
        ):
            raise RuntimeError(
                "Manual evaluation requires a fresh open-status verification "
                "from an official or explicitly corroborated source"
            )
        evaluated = self._evaluate_job(stored)
        result = self.state.upsert_job(evaluated)
        return self.state.get_job(result.job_id or evaluated.canonical_id or "") or evaluated

    def refresh_qol(self, job_id_or_url: str) -> JobRecord:
        job = self._find_job(job_id_or_url)
        if not requires_full_qol(job):
            raise ValueError(
                "Full QOL refresh requires a verified-open Tier 1 or Tier 2 job"
            )
        refreshed = self._refresh_qol_for_job(
            JobRecord.from_dict(job.to_dict()),
            previous_job=job,
            force=True,
        )
        result = self.state.upsert_job(refreshed)
        return self.state.get_job(result.job_id or refreshed.canonical_id or "") or refreshed

    def show(self, canonical_job_id: str) -> JobRecord:
        return self._find_job(canonical_job_id)

    def active(self) -> list[JobRecord]:
        runs = self.state.list_runs()
        if not runs:
            return []
        latest = max(
            runs,
            key=lambda run: _as_datetime(run.completed_at or run.started_at)
            or datetime.min.replace(tzinfo=timezone.utc),
        )
        return sorted(
            [
                job
                for job in self.state.list_jobs()
                if self._is_current_active_for_run(job, latest.run_id)
            ],
            key=lambda job: ({"Tier 1": 0, "Tier 2": 1}.get(job.tier or "", 9), -(job.fit_score or 0.0), job.organization_name.casefold()),
        )

    def deadlines(self, *, days: int | None = None, today: date | None = None) -> list[JobRecord]:
        current = today or _now().date()
        rows: list[tuple[date, JobRecord]] = []
        for job in self.state.list_jobs():
            if job.rejected or job.deadline_type == "rolling" or not job.deadline:
                continue
            try:
                deadline = date.fromisoformat(str(job.deadline)[:10])
            except ValueError:
                continue
            delta = (deadline - current).days
            if delta < 0:
                continue
            if days is None or delta <= days:
                rows.append((deadline, job))
        return [job for _, job in sorted(rows, key=lambda item: (item[0], item[1].organization_name))]

    def coverage(self) -> dict[str, list[Any]]:
        return {
            "sources": self.state.list_source_coverage(),
            "institutions": self.state.list_institution_coverage(),
        }

    def source_health(self) -> dict[str, Any]:
        coverage = self.state.list_source_coverage()
        configured = {
            str(source.get("id")): {
                "configured": bool(_source_enabled(source)),
                "supports_rss": bool(source.get("supports_rss", False)),
                "alert_delivery_state": source.get("alert_delivery_state"),
            }
            for source in self.sources
            if source.get("id")
        }
        return {"configured": configured, "coverage": coverage}

    def target_health(self) -> dict[str, Any]:
        coverage_by_name = {
            row.institution.casefold(): row
            for row in self.state.list_institution_coverage()
        }
        return {
            "targets": [
                {
                    "id": target.get("id"),
                    "name": target.get("name"),
                    "priority_tier": target.get("priority_tier"),
                    "interval_days": self._cadence_days(target, institution=True),
                    "coverage": coverage_by_name.get(
                        str(target.get("name") or "").casefold()
                    ),
                }
                for target in self.institutions
            ]
        }

    def reject(self, canonical_job_id: str, *, reason: str | None = None) -> JobRecord:
        job = self._find_job(canonical_job_id)
        job.rejected = True
        job.manual_review_state = "not_interested"
        job.extra["human_override"] = {"field": "interest_status", "value": "not_interested", "reason": reason, "timestamp": utc_now(), "source": "human"}
        result = self.state.upsert_job(job)
        return self.state.get_job(result.job_id or canonical_job_id) or job

    def restore(self, canonical_job_id: str, *, reason: str | None = None) -> JobRecord:
        job = self._find_job(canonical_job_id)
        job.rejected = False
        job.manual_review_state = "reviewed"
        job.extra["clear_manual_override"] = True
        job.extra["human_override"] = {"field": "interest_status", "value": "reviewed", "reason": reason, "timestamp": utc_now(), "source": "human"}
        result = self.state.upsert_job(job)
        return self.state.get_job(result.job_id or canonical_job_id) or job

    def handoff(self, canonical_job_id: str, evidence: Iterable[Any] = ()) -> dict[str, Any]:
        job = JobRecord.from_dict(self._find_job(canonical_job_id).to_dict())
        if (
            job.verification_status
            not in {
                VerificationStatus.VERIFIED_OPEN,
                VerificationStatus.VERIFIED_REOPENED,
            }
            or str(job.lifecycle_status or "").casefold()
            not in {"open", "reopened", "active"}
            or not job.official_url
            or not job.last_verified
            or job.extra.get("last_verification_transition_accepted") is False
        ):
            raise ValueError(
                "GatedSprint handoff requires a currently verified-open role "
                "with an official URL and verification timestamp"
            )
        application = next(
            (
                record
                for record in self.state.list_applications()
                if record.job_id == (job.canonical_id or canonical_job_id)
            ),
            None,
        )
        if application is not None:
            job.application = application.to_dict()
            if application.package_path:
                job.application["existing_materials"] = [application.package_path]
        return build_gatedsprint_handoff(
            job,
            job.evaluation,
            evidence,
            max_verification_age_days=max(
                1, self._reverification_interval_days(job)
            ),
        )

    @staticmethod
    def _clone_connector_for_dry_run(connector: Any) -> Any:
        if connector is None:
            return None
        clone = getattr(connector, "clone_for_dry_run", None)
        if callable(clone):
            return clone()
        try:
            return copy.deepcopy(connector)
        except Exception as exc:
            raise RuntimeError(
                f"Dry-run connector {type(connector).__name__} cannot be isolated"
            ) from exc

    def dry_run(self, run_type: str = "daily") -> WorkflowResult:
        temporary = InMemoryStateStore(self.state.snapshot())
        isolated_connectors = [
            self._clone_connector_for_dry_run(connector)
            for connector in self.discovery_connectors
        ]
        service = AcademicPiService(
            config=copy.deepcopy(self.config),
            state_store=temporary,
            discovery_connectors=isolated_connectors,
            verification_connector=self._clone_connector_for_dry_run(self.verifier),
            report_connectors=(),
            email_connector=self._clone_connector_for_dry_run(self.email_connector),
        )
        return service._run(run_type, deliver=False, mark_email=False)


AcademicPIService = AcademicPiService
