"""Injectable, credential-free adapters for the academic deployment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from ...core.connectors import (
    AlertMessage,
    DeliveryResult,
    DiscoveryBatch,
    DiscoveryConnector,
    DiscoveryRequest,
    EmailAlertConnector,
    ReportConnector,
    VerificationConnector,
)
from ...core.models import (
    JobRecord,
    SourceAuthority,
    VerificationResult,
    VerificationStatus,
    utc_now,
)
from .models import GmailLabelPlan


@dataclass
class CallableDiscoveryAdapter:
    """Wrap a host-provided web/search callable without embedding networking."""

    id: str
    callback: Callable[..., Iterable[JobRecord | Mapping[str, Any]] | Mapping[str, Any]]
    source_class: str = "SEARCH_ENGINE_DISCOVERY"
    supports_institution_scan: bool = field(default=True, init=False)

    @property
    def connector_id(self) -> str:
        return self.id

    def discover(self, request: DiscoveryRequest) -> DiscoveryBatch:
        value = self.callback(request=request)
        if isinstance(value, DiscoveryBatch):
            return value
        if isinstance(value, Mapping) and "candidates" in value:
            return DiscoveryBatch.from_dict(value)
        institution = request.context.get("institution", {})
        official_pages = []
        if request.institution and isinstance(institution, Mapping):
            for key in ("career_urls", "department_urls", "faculty_urls", "lab_urls"):
                values = institution.get(key, ())
                if isinstance(values, str):
                    values = (values,)
                official_pages.extend(str(item) for item in values or () if str(item))
        return DiscoveryBatch.from_jobs(
            self.id,
            value,
            completed_at=utc_now(),
            metadata={
                "scan_completed": True,
                "institution_visited": bool(request.institution),
                "official_pages_checked": list(dict.fromkeys(official_pages)),
            },
        )

    def scan_institution(
        self, institution: Mapping[str, Any], **context: Any
    ) -> DiscoveryBatch:
        return self.callback(institution=institution, **context)


@dataclass
class StaticDiscoveryAdapter:
    id: str = "static"
    candidates: list[JobRecord | Mapping[str, Any]] = field(default_factory=list)
    supports_institution_scan: bool = field(default=True, init=False)

    @property
    def connector_id(self) -> str:
        return self.id

    def discover(self, request: DiscoveryRequest) -> DiscoveryBatch:
        values = list(self.candidates)
        if request.institution:
            name = request.institution.casefold()
            values = [
                candidate
                for candidate in values
                if str(
                    (candidate.to_dict() if hasattr(candidate, "to_dict") else candidate).get(
                        "institution"
                    )
                    or ""
                ).casefold()
                == name
            ]
        institution = request.context.get("institution", {})
        official_pages = []
        if request.institution and isinstance(institution, Mapping):
            for key in ("career_urls", "department_urls", "faculty_urls", "lab_urls"):
                urls = institution.get(key, ())
                if isinstance(urls, str):
                    urls = (urls,)
                official_pages.extend(str(item) for item in urls or () if str(item))
        return DiscoveryBatch.from_jobs(
            self.id,
            values,
            completed_at=utc_now(),
            metadata={
                "scan_completed": True,
                "institution_visited": bool(request.institution),
                "official_pages_checked": list(dict.fromkeys(official_pages)),
            },
        )

    def scan_institution(
        self, institution: Mapping[str, Any], **context: Any
    ) -> list[JobRecord | Mapping[str, Any]]:
        name = str(institution.get("name") or "").casefold()
        if not name:
            return []
        output: list[JobRecord | Mapping[str, Any]] = []
        for candidate in self.candidates:
            value = candidate.to_dict() if hasattr(candidate, "to_dict") else candidate
            institution_name = str(value.get("institution") or value.get("organization") or "")
            if institution_name.casefold() == name:
                output.append(candidate)
        return output


@dataclass
class CallableVerificationAdapter:
    """Wrap a host official-page verifier.

    Callers using a lower-authority source must override ``authority`` or return
    an explicitly corroborated ``VerificationResult``.
    """

    callback: Callable[..., VerificationResult | Mapping[str, Any]]
    connector_id: str = "callable_verification"
    authority: SourceAuthority | int = SourceAuthority.OFFICIAL_DETAIL

    def verify(self, job: JobRecord) -> VerificationResult:
        value = self.callback(job=job)
        result = value if isinstance(value, VerificationResult) else VerificationResult.from_dict(value)
        if int(result.authority) == int(SourceAuthority.DISCOVERY_ONLY):
            result.authority = self.authority
        if not result.source_id:
            result.source_id = self.connector_id
        return result


class NoOpVerificationAdapter:
    """Safe default: retain the role as pending and never invent open status."""

    connector_id = "none"

    def verify(self, job: JobRecord) -> VerificationResult:
        return VerificationResult(
            status=VerificationStatus.VERIFICATION_PENDING,
            source_url=job.official_url,
            confidence=0.0,
            evidence=[],
            error="No verification adapter configured",
        )


@dataclass
class StaticEmailAdapter:
    messages: list[Any] = field(default_factory=list)
    applied_plans: list[GmailLabelPlan] = field(default_factory=list)
    connector_id: str = "static_email"

    def fetch_unprocessed(self, *, limit: int | None = None) -> list[AlertMessage]:
        values = self.messages if limit is None else self.messages[:limit]
        return [
            message
            if isinstance(message, AlertMessage)
            else AlertMessage.from_dict(message)
            if isinstance(message, Mapping)
            else AlertMessage(message_id=f"static-{index}", body=str(message))
            for index, message in enumerate(values)
        ]

    def apply_label_plan(self, plan: GmailLabelPlan) -> bool:
        self.applied_plans.append(plan)
        return True

    def mark_processed(self, message_id: str) -> None:
        self.applied_plans.append(GmailLabelPlan(message_id, ("Processed",), processed=True))

    def mark_needs_review(self, message_id: str, reason: str) -> None:
        self.applied_plans.append(GmailLabelPlan(message_id, ("Needs Review",), reason=reason))

    def mark_error(self, message_id: str, reason: str) -> None:
        self.applied_plans.append(GmailLabelPlan(message_id, ("Error",), reason=reason))


@dataclass
class MemoryReportAdapter:
    id: str = "memory"
    reports: list[str] = field(default_factory=list)

    @property
    def connector_id(self) -> str:
        return self.id

    def deliver(
        self, report: str | Mapping[str, Any], *, metadata: Mapping[str, Any] | None = None
    ) -> DeliveryResult:
        self.reports.append(report)
        return DeliveryResult.success(self.id, external_id=f"memory:{len(self.reports)}")


class NoOpReportAdapter:
    id = "none"
    connector_id = "none"

    def deliver(
        self, report: str | Mapping[str, Any], *, metadata: Mapping[str, Any] | None = None
    ) -> DeliveryResult:
        return DeliveryResult(channel=self.id, confirmed=False, error="No report channel configured")


# Concise aliases for host integrations.
AcademicDiscoveryAdapter = DiscoveryConnector
AcademicEmailAdapter = EmailAlertConnector
AcademicReportAdapter = ReportConnector
AcademicVerificationAdapter = VerificationConnector
CallableWebAdapter = CallableDiscoveryAdapter
StaticWebAdapter = StaticDiscoveryAdapter
