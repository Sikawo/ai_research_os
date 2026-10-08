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
        failure_class: str | None = None,
        error_code: str | None = None,
        connector_reached: str = "unknown",
        outcome: str = "failure",
        retryable: bool | None = None,
    ) -> None:
        self.category = category
        self.transient = transient
        self.failure_class = failure_class or category
        self.error_code = error_code
        self.connector_reached = connector_reached
        self.outcome = "uncertain" if connector_reached == "unknown" else outcome
        self.retryable = (
            retryable
            if self.outcome == "failure" and connector_reached == "no"
            else False
            if retryable is False
            else None
        )
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
    run_id: str | None = None
    logical_action: str | None = None
    attempted: bool = False
    attempted_at: str | None = None
    connector_reached: str = "unknown"
    outcome: str = "not_attempted"
    delivered_at: str | None = None
    destination_type: str | None = None
    destination: str | None = None
    account_selector_redacted: str | None = None
    account_selection_unique: bool | None = None
    failure_class: str | None = None
    error_code: str | None = None
    retryable: bool | None = None
    result_reference: str | None = None
    readback_status: str = "not_requested"
    idempotency_key: str | None = None
    external_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize new lifecycle fields without breaking legacy payloads."""

        if self.outcome in {"failure", "uncertain"}:
            self.confirmed = False
            self.attempted = True
            if self.outcome == "uncertain" or self.connector_reached == "unknown":
                self.outcome = "uncertain"
                if self.retryable is True:
                    self.retryable = None
                if self.readback_status == "not_requested":
                    self.readback_status = "unknown"
            elif self.connector_reached != "no" and self.retryable is True:
                self.retryable = None
        elif self.outcome == "success" or self.confirmed:
            self.attempted = True
            if self.connector_reached == "no":
                self.confirmed = False
                self.outcome = "uncertain"
                self.retryable = None
                if self.readback_status == "not_requested":
                    self.readback_status = "unknown"
            else:
                self.confirmed = True
                self.outcome = "success"
                if self.connector_reached == "unknown":
                    self.connector_reached = "yes"
                if self.retryable is None:
                    self.retryable = False
        elif self.attempted:
            self.confirmed = False
            self.outcome = "uncertain"
            self.retryable = None
            if self.readback_status == "not_requested":
                self.readback_status = "unknown"

        if self.result_reference is None and self.external_id is not None:
            self.result_reference = self.external_id
        if self.attempted and self.attempted_at is None and self.delivered_at is not None:
            self.attempted_at = self.delivered_at

    @property
    def requires_reconciliation(self) -> bool:
        """Whether a readback or status lookup is required before retrying."""

        return self.outcome == "uncertain" or (
            self.attempted
            and not self.confirmed
            and self.connector_reached == "unknown"
        )

    @property
    def may_retry_without_reconciliation(self) -> bool:
        """Allow blind retry only for a confirmed pre-dispatch failure."""

        return (
            self.outcome == "failure"
            and self.connector_reached == "no"
            and self.retryable is True
        )

    @classmethod
    def success(
        cls,
        channel: str,
        *,
        run_id: str | None = None,
        logical_action: str | None = None,
        attempted_at: str | None = None,
        destination_type: str | None = None,
        destination: str | None = None,
        account_selector_redacted: str | None = None,
        account_selection_unique: bool | None = None,
        result_reference: str | None = None,
        readback_status: str = "not_requested",
        idempotency_key: str | None = None,
        external_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "DeliveryResult":
        recorded_at = attempted_at or utc_now()
        return cls(
            channel=channel,
            confirmed=True,
            run_id=run_id,
            logical_action=logical_action,
            attempted=True,
            attempted_at=recorded_at,
            connector_reached="yes",
            outcome="success",
            delivered_at=recorded_at,
            destination_type=destination_type,
            destination=destination,
            account_selector_redacted=account_selector_redacted,
            account_selection_unique=account_selection_unique,
            retryable=False,
            result_reference=result_reference or external_id,
            readback_status=readback_status,
            idempotency_key=idempotency_key,
            external_id=external_id,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failure(
        cls,
        channel: str,
        *,
        run_id: str | None = None,
        logical_action: str | None = None,
        attempted_at: str | None = None,
        connector_reached: str = "no",
        failure_class: str = "connector_error",
        error_code: str | None = None,
        error: str | None = None,
        retryable: bool = False,
        destination_type: str | None = None,
        destination: str | None = None,
        account_selector_redacted: str | None = None,
        account_selection_unique: bool | None = None,
        idempotency_key: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "DeliveryResult":
        """Record a definite failure with sanitized execution metadata."""

        return cls(
            channel=channel,
            confirmed=False,
            run_id=run_id,
            logical_action=logical_action,
            attempted=True,
            attempted_at=attempted_at or utc_now(),
            connector_reached=connector_reached,
            outcome="failure",
            destination_type=destination_type,
            destination=destination,
            account_selector_redacted=account_selector_redacted,
            account_selection_unique=account_selection_unique,
            failure_class=failure_class,
            error_code=error_code,
            retryable=retryable,
            readback_status="not_requested",
            idempotency_key=idempotency_key,
            error=error,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def uncertain(
        cls,
        channel: str,
        *,
        run_id: str | None = None,
        logical_action: str | None = None,
        attempted_at: str | None = None,
        connector_reached: str = "unknown",
        failure_class: str = "uncertain_result",
        error_code: str | None = None,
        error: str | None = None,
        destination_type: str | None = None,
        destination: str | None = None,
        account_selector_redacted: str | None = None,
        account_selection_unique: bool | None = None,
        result_reference: str | None = None,
        readback_status: str = "unknown",
        idempotency_key: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "DeliveryResult":
        """Record an outcome that must be reconciled before any retry."""

        return cls(
            channel=channel,
            confirmed=False,
            run_id=run_id,
            logical_action=logical_action,
            attempted=True,
            attempted_at=attempted_at or utc_now(),
            connector_reached=connector_reached,
            outcome="uncertain",
            destination_type=destination_type,
            destination=destination,
            account_selector_redacted=account_selector_redacted,
            account_selection_unique=account_selection_unique,
            failure_class=failure_class,
            error_code=error_code,
            retryable=None,
            result_reference=result_reference,
            readback_status=readback_status,
            idempotency_key=idempotency_key,
            error=error,
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
