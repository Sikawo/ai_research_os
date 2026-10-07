"""Side-effect boundaries for discovery, verification, messaging, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from .models import JobRecord, JsonModel, VerificationResult, utc_now


class ConnectorError(RuntimeError):
    """A connector failure that callers should record without corrupting state."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "unknown",
        transient: bool = False,
    ) -> None:
        self.category = category
        self.transient = transient
        super().__init__(message)


@dataclass
class DiscoveryRequest(JsonModel):
    run_id: str = ""
    source_id: str | None = None
    query: str | None = None
    institution: str | None = None
    limit: int | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryBatch(JsonModel):
    source_id: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    attempted_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_jobs(
        cls,
        source_id: str,
        jobs: Iterable[JobRecord | Mapping[str, Any]],
        **kwargs: Any,
    ) -> "DiscoveryBatch":
        return cls(
            source_id=source_id,
            candidates=[
                job.to_dict() if isinstance(job, JobRecord) else dict(job) for job in jobs
            ],
            **kwargs,
        )

    def jobs(self) -> list[JobRecord]:
        return [JobRecord.from_dict(item) for item in self.candidates]


@dataclass
class DeliveryResult(JsonModel):
    channel: str = ""
    confirmed: bool = False
    delivered_at: str | None = None
    destination: str | None = None
    external_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        channel: str,
        *,
        destination: str | None = None,
        external_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "DeliveryResult":
        return cls(
            channel=channel,
            confirmed=True,
            delivered_at=utc_now(),
            destination=destination,
            external_id=external_id,
            metadata=dict(metadata or {}),
        )


@dataclass
class AlertMessage(JsonModel):
    message_id: str = ""
    subject: str | None = None
    body: str | None = None
    html: str | None = None
    sender: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    source_id: str | None = None
    received_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DiscoveryConnector(Protocol):
    connector_id: str

    def discover(self, request: DiscoveryRequest) -> DiscoveryBatch: ...


@runtime_checkable
class VerificationConnector(Protocol):
    connector_id: str

    def verify(self, job: JobRecord) -> VerificationResult: ...


@runtime_checkable
class ReportConnector(Protocol):
    connector_id: str

    def deliver(
        self,
        report: str | Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> DeliveryResult: ...


@runtime_checkable
class EmailAlertConnector(Protocol):
    """Approval-safe ingestion protocol; it intentionally has no send/delete API."""

    connector_id: str

    def fetch_unprocessed(self, *, limit: int | None = None) -> Iterable[AlertMessage]: ...

    def mark_processed(self, message_id: str) -> None: ...

    def mark_needs_review(self, message_id: str, reason: str) -> None: ...

    def mark_error(self, message_id: str, reason: str) -> None: ...
