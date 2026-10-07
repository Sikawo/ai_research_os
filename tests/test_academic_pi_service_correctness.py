"""Adversarial service/runtime correctness tests for the Academic PI deployment."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from Career_Job_Agent_Framework.core.connectors import DiscoveryBatch
from Career_Job_Agent_Framework.core.models import (
    ApplicationRecord,
    ChangeRecord,
    JobRecord,
    RunRecord,
    SourceAuthority,
    VerificationResult,
    VerificationStatus,
    utc_now,
)
from Career_Job_Agent_Framework.core.state import InMemoryStateStore
from Career_Job_Agent_Framework.deployments.academic_pi import (
    AcademicPiService,
    CallableVerificationAdapter,
    StaticEmailAdapter,
)


def _config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "academic_pi": {
            "automation": {"auto_apply": False},
            "query_budget": 1,
            "coverage": {
                "frequency_classes": {
                    "high": {"interval_days": 1},
                    "medium": {"interval_days": 3},
                },
                "target_institutions": {"default_interval_days": 3},
            },
        },
        "candidate_profile": {
            "profile_version": 7,
            "career_stage": {
                "target_independence": ["tenure_track_faculty"]
            },
            "scientific_identity": {
                "primary_fields": ["virology"],
                "research_questions": ["host defense"],
                "methods": ["single-cell sequencing"],
            },
            "departments": {"strong_fit": ["Biology"]},
        },
        "target_institutions": {"institutions": []},
        "scoring_overrides": {"rubric_version": 9},
    }
    config.update(overrides)
    return config


def _job(job_id: str, institution: str, **overrides: Any) -> JobRecord:
    values: dict[str, Any] = {
        "title": "Assistant Professor of Biology",
        "institution": institution,
        "organization": institution,
        "department": "Biology",
        "country": "US",
        "official_job_id": job_id,
        "official_url": f"https://jobs.example.edu/{job_id}",
        "description": (
            "Tenure-track faculty will establish an independent research program "
            "in virology and host defense using single-cell sequencing, startup "
            "support, and graduate supervision."
        ),
        "lifecycle_status": "open",
        "verification_status": VerificationStatus.VERIFIED_OPEN,
        "last_verified": "2026-10-03T00:00:00Z",
        "verification_confidence": 0.95,
        "tier": "Tier 2",
        "fit_score": 75.0,
    }
    values.update(overrides)
    return JobRecord(**values)


def _official_verifier(callback: Any | None = None) -> CallableVerificationAdapter:
    def verify(job: JobRecord) -> VerificationResult:
        if callback is not None:
            return callback(job)
        return VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            source_url=job.official_url or (job.discovery_urls[0] if job.discovery_urls else None),
            source_id="official",
            authority=SourceAuthority.OFFICIAL_DETAIL,
            confidence=0.99,
            evidence=["official detail page"],
            verified_fields={
                "title": job.title,
                "institution": job.institution,
                "department": job.department,
                "deadline": job.deadline,
                "deadline_type": job.deadline_type,
                "requirements": job.requirements,
            },
        )

    return CallableVerificationAdapter(verify, connector_id="official")


def _run_by_id(state: InMemoryStateStore, run_id: str):
    return next(run for run in state.list_runs() if run.run_id == run_id)


class _OneSiblingFailureStore(InMemoryStateStore):
    def __init__(self) -> None:
        super().__init__()
        self.failed_once = False

    def upsert_job(self, job: Any, *, record_changes: bool = True):
        title = job.title if isinstance(job, JobRecord) else str(job.get("title", ""))
        if "Group Leader" in title and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("synthetic sibling write failure")
        return super().upsert_job(job, record_changes=record_changes)


class _FlakyLabelEmail(StaticEmailAdapter):
    def __init__(self, messages: list[Any]) -> None:
        super().__init__(messages=messages)
        self.failed_once = False

    def apply_label_plan(self, plan):
        self.applied_plans.append(plan)
        if plan.processed and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("synthetic Gmail label failure")
        return True


def test_multi_job_email_retries_failed_sibling_before_message_completion() -> None:
    email = StaticEmailAdapter(
        messages=[
            {
                "message_id": "multi-1",
                "body": (
                    "Assistant Professor of Biology https://alerts.example/job/1\n"
                    "Independent Group Leader https://alerts.example/job/2"
                ),
            }
        ]
    )
    state = _OneSiblingFailureStore()
    service = AcademicPiService(
        config=_config(),
        state_store=state,
        email_connector=email,
        verification_connector=_official_verifier(),
    )

    first = service.daily()
    assert len(state.list_jobs()) == 1
    assert not first.label_plans[0].processed
    assert _run_by_id(state, first.run_id).extra["completed_email_message_ids"] == []

    second = service.daily()
    assert len(state.list_jobs()) == 2
    assert second.label_plans[0].processed
    assert _run_by_id(state, second.run_id).extra["completed_email_message_ids"] == ["multi-1"]


def test_gmail_label_failure_remains_retryable_and_reconcilable() -> None:
    email = _FlakyLabelEmail(
        [
            {
                "message_id": "label-1",
                "body": "Assistant Professor of Biology https://alerts.example/job/1",
            }
        ]
    )
    state = InMemoryStateStore()
    service = AcademicPiService(
        config=_config(),
        state_store=state,
        email_connector=email,
        verification_connector=_official_verifier(),
    )

    first = service.daily()
    assert not first.label_plans[0].processed
    assert "synthetic Gmail label failure" in first.errors
    assert _run_by_id(state, first.run_id).extra["completed_email_message_ids"] == []

    second = service.daily()
    assert second.metrics["new_jobs"] == 0
    assert second.label_plans[0].processed
    assert _run_by_id(state, second.run_id).extra["completed_email_message_ids"] == ["label-1"]


def test_daily_reverifies_retained_candidates_and_builds_strict_snapshot() -> None:
    state = InMemoryStateStore()
    for job in (
        _job("GOOD", "Good University"),
        _job("STALE", "Stale University"),
        _job("PENDING", "Pending University", verification_status=VerificationStatus.VERIFICATION_PENDING),
        _job("BLOCKED", "Blocked University", manual_review_state="blocked"),
        _job("REJECTED", "Rejected University", rejected=True),
    ):
        state.upsert_job(job)

    calls: list[str] = []

    def callback(job: JobRecord) -> VerificationResult:
        calls.append(str(job.official_job_id))
        status = (
            VerificationStatus.VERIFICATION_FAILED_TRANSIENT
            if job.official_job_id == "STALE"
            else VerificationStatus.VERIFIED_OPEN
        )
        return VerificationResult(
            status=status,
            source_url=job.official_url,
            source_id="official",
            authority=SourceAuthority.OFFICIAL_DETAIL,
            confidence=0.99 if status == VerificationStatus.VERIFIED_OPEN else 0.0,
            error="temporary outage" if status.is_transient else None,
        )

    result = AcademicPiService(
        config=_config(),
        state_store=state,
        verification_connector=_official_verifier(callback),
    ).daily()

    assert set(calls) == {"GOOD", "STALE", "PENDING", "BLOCKED"}
    assert result.metrics["tier2_active"] == 2
    assert "Good University" in result.report
    assert "Pending University" in result.report
    assert "Stale University — Assistant Professor of Biology: verification_failed_transient" in result.report
    active = AcademicPiService(
        config=_config(), state_store=state, verification_connector=_official_verifier()
    ).active()
    assert {job.official_job_id for job in active} == {"GOOD", "PENDING"}


def test_manual_evaluate_reverifies_and_rejects_discovery_only_authority() -> None:
    state = InMemoryStateStore()
    inserted = state.upsert_job(_job("MANUAL", "Manual University"))
    calls = 0

    class DiscoveryOnlyVerifier:
        connector_id = "discovery_only"

        def verify(self, job: JobRecord) -> VerificationResult:
            nonlocal calls
            calls += 1
            return VerificationResult(
                status=VerificationStatus.VERIFIED_OPEN,
                source_url=job.official_url,
                source_id="aggregator",
                authority=SourceAuthority.DISCOVERY_ONLY,
                confidence=0.9,
            )

    service = AcademicPiService(
        config=_config(),
        state_store=state,
        verification_connector=DiscoveryOnlyVerifier(),
    )
    with pytest.raises(RuntimeError, match="fresh open-status verification"):
        service.evaluate(inserted.job_id or "")
    assert calls == 1


def test_untrusted_closure_is_reported_pending_not_verified_closed() -> None:
    state = InMemoryStateStore()
    state.upsert_job(_job("UNTRUSTED-CLOSE", "Authority University"))

    class DiscoveryOnlyClosure:
        connector_id = "aggregator"

        def verify(self, job: JobRecord) -> VerificationResult:
            return VerificationResult(
                status=VerificationStatus.VERIFIED_CLOSED,
                source_url=job.official_url,
                source_id="aggregator",
                authority=SourceAuthority.TRUSTED_AGGREGATOR,
                confidence=1.0,
            )

    result = AcademicPiService(
        config=_config(),
        state_store=state,
        verification_connector=DiscoveryOnlyClosure(),
    ).daily()

    assert result.metrics["verified_closed"] == 0
    assert result.metrics["verification_pending"] == 1
    assert state.list_jobs()[0].lifecycle_status == "open"


class _BatchConnector:
    connector_id = "batch"

    def __init__(self, batch: DiscoveryBatch) -> None:
        self.batch = batch
        self.calls = 0

    def discover(self, request):
        self.calls += 1
        return self.batch


def test_coverage_never_claims_unvisited_pages_or_missing_connectors() -> None:
    institutions = {
        "institutions": [
            {
                "name": "Coverage University",
                "career_urls": ["https://coverage.example.edu/careers"],
                "enabled": True,
            }
        ]
    }
    no_connector_state = InMemoryStateStore()
    no_connector = AcademicPiService(
        config=_config(target_institutions=institutions),
        state_store=no_connector_state,
    ).daily()
    missing = no_connector_state.list_institution_coverage()[0]
    assert no_connector.metrics["institutions_checked"] == 0
    assert missing.status == "not_attempted"
    assert missing.official_pages_checked == []

    empty_state = InMemoryStateStore()
    empty_connector = _BatchConnector(DiscoveryBatch(source_id="batch", candidates=[]))
    empty = AcademicPiService(
        config=_config(target_institutions=institutions),
        state_store=empty_state,
        discovery_connectors=[empty_connector],
    ).daily()
    unvisited = empty_state.list_institution_coverage()[0]
    assert empty.metrics["institutions_checked"] == 0
    assert unvisited.status == "incomplete"
    assert unvisited.official_pages_checked == []


def test_connector_batch_errors_fail_source_and_institution_coverage() -> None:
    connector = _BatchConnector(
        DiscoveryBatch(
            source_id="batch",
            errors=[{"category": "rate_limit", "message": "synthetic throttle"}],
        )
    )
    state = InMemoryStateStore()
    result = AcademicPiService(
        config=_config(
            target_institutions={
                "institutions": [{"name": "Error University", "enabled": True}]
            }
        ),
        state_store=state,
        discovery_connectors=[connector],
    ).daily()
    assert state.list_source_coverage()[0].status == "failed"
    assert state.list_source_coverage()[0].error == "synthetic throttle"
    assert state.list_institution_coverage()[0].status == "failed"
    assert state.list_institution_coverage()[0].official_pages_checked == []
    assert result.metrics["institutions_checked"] == 0


def test_source_cadence_deadline_windows_and_evaluation_versions_are_wired() -> None:
    connector = _BatchConnector(
        DiscoveryBatch(
            source_id="cadenced",
            candidates=[],
            completed_at=utc_now(),
            metadata={"scan_completed": True},
        )
    )
    connector.connector_id = "cadenced"
    state = InMemoryStateStore()
    config = _config(
        source_catalog={
            "sources": [
                {"id": "cadenced", "enabled": True, "frequency_class": "medium"}
            ]
        },
        preferences={"reporting": {"deadline_warning_days": [14, 3]}},
    )
    service = AcademicPiService(
        config=config,
        state_store=state,
        discovery_connectors=[connector],
        verification_connector=_official_verifier(),
    )
    first = service.daily()
    calls_after_first = connector.calls
    second = service.daily()
    assert first.metrics["sources_due"] == 1
    assert second.metrics["sources_due"] == 0
    assert connector.calls == calls_after_first
    assert state.list_source_coverage()[0].next_due

    today = date(2026, 10, 4)
    warning = _job("WARN", "Warning University", deadline=str(today + timedelta(days=14)), deadline_type="fixed")
    quiet = _job("QUIET", "Quiet University", deadline=str(today + timedelta(days=10)), deadline_type="fixed")
    assert [job.official_job_id for job in service._deadline_alerts([warning, quiet], today=today)] == ["WARN"]
    evaluated = service._evaluate_job(service._coerce_job(warning))
    assert evaluated.evaluation["profile_version"] == 7
    assert evaluated.evaluation["rubric_version"] == 9


def test_configured_material_change_fields_drive_run_alerts() -> None:
    state = InMemoryStateStore()
    state.upsert_job(_job("CHANGE", "Change University", deadline="2026-11-01"))
    changed = _job("CHANGE", "Change University", deadline="2026-12-15")
    connector = _BatchConnector(
        DiscoveryBatch(
            source_id="material",
            candidates=[changed.to_dict()],
            completed_at=utc_now(),
            metadata={"scan_completed": True},
        )
    )
    connector.connector_id = "material"
    result = AcademicPiService(
        config=_config(
            material_change_fields={"material_fields": ["dates.deadline"]}
        ),
        state_store=state,
        discovery_connectors=[connector],
        verification_connector=_official_verifier(),
    ).daily()
    assert result.metrics["material_changes"] == 1
    assert "deadline" in result.report


def test_application_reporting_reads_state_without_claiming_agent_submission() -> None:
    state = InMemoryStateStore()
    state.upsert_application(ApplicationRecord(job_id="A", status="submitted"))
    state.upsert_application(ApplicationRecord(job_id="B", status="drafting"))
    result = AcademicPiService(config=_config(), state_store=state).daily()

    assert result.metrics["applications_recorded"] == 2
    assert result.metrics["applications_submitted_recorded"] == 1
    assert "drafting=1" in result.report
    assert "submitted=1" in result.report
    assert "submission was not performed by this agent" in result.report
    assert "Applications submitted by this agent: 0" in result.report
    assert result.submitted_applications == 0


def test_gatedsprint_handoff_reads_separate_application_state() -> None:
    state = InMemoryStateStore()
    job = _job(
        "HANDOFF",
        "Handoff University",
        canonical_id="job-handoff",
        last_verified=utc_now(),
        role_class="tenure_track_faculty",
        evaluation={
            "fit_score": 82.0,
            "tier": "Tier 1",
            "strongest_matches": ["virology"],
        },
    )
    state.upsert_job(job)
    state.upsert_application(
        ApplicationRecord(
            job_id="job-handoff",
            status="drafting",
            package_path="PRIVATE_APPLICATION_PACKAGE_REFERENCE",
        )
    )

    payload = AcademicPiService(config=_config(), state_store=state).handoff(
        "job-handoff",
        evidence=[{"ref": "E-1", "strength": "uncertain", "authorized": True}],
    )

    assert payload["application"]["current_status"] == "drafting"
    assert payload["application"]["existing_materials"] == [
        "PRIVATE_APPLICATION_PACKAGE_REFERENCE"
    ]
    assert payload["application"]["submission_authorized"] is False


def test_weekly_sections_use_a_seven_day_window() -> None:
    now = datetime.now(timezone.utc)
    state = InMemoryStateStore()
    recent = _job(
        "RECENT",
        "Recent University",
        first_seen=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
    )
    old = _job(
        "OLD",
        "Old University",
        first_seen=(now - timedelta(days=10)).isoformat().replace("+00:00", "Z"),
    )
    closed = _job(
        "CLOSED",
        "Closed University",
        lifecycle_status="closed",
        verification_status=VerificationStatus.VERIFIED_CLOSED,
        first_seen=(now - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
    )
    state.upsert_job(recent)
    state.upsert_job(old)
    closed_result = state.upsert_job(closed)
    state.record_change(
        ChangeRecord(
            job_id=closed_result.job_id or "",
            field="lifecycle_status",
            old_value="open",
            new_value="closed",
            changed_at=(now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        )
    )

    report = AcademicPiService(
        config=_config(),
        state_store=state,
        verification_connector=_official_verifier(),
    ).weekly().report
    new_this_week = report.split("## NEW THIS WEEK", 1)[1].split(
        "## MATERIAL CHANGES", 1
    )[0]
    closed_this_week = report.split(
        "## CLOSED / EXPIRED / REOPENED THIS WEEK", 1
    )[1].split("## Roles needing a user decision", 1)[0]

    assert "Recent University" in new_this_week
    assert "Old University" not in new_this_week
    assert "Closed University" in closed_this_week


def test_weekly_report_audits_cross_run_blind_spots() -> None:
    now = datetime.now(timezone.utc)
    state = InMemoryStateStore()
    state.upsert_job(
        _job(
            "BLIND",
            "Blind Spot University",
            deadline=None,
            deadline_type="unknown",
            last_verified=(now - timedelta(days=30)).isoformat().replace(
                "+00:00", "Z"
            ),
            source_provenance=[{"source_id": "single-source"}],
        )
    )
    state.record_run(
        RunRecord(
            run_id="prior-parser-failure",
            run_type="daily",
            started_at=(now - timedelta(days=1)).isoformat().replace(
                "+00:00", "Z"
            ),
            status="completed_with_errors",
            errors=[
                {
                    "category": "parser_error",
                    "message": "no_plausible_job_candidates",
                    "message_id": "repeated-message",
                }
            ],
        )
    )
    email = StaticEmailAdapter(
        messages=[{"message_id": "repeated-message", "body": "not a job alert"}]
    )

    report = AcademicPiService(
        config=_config(),
        state_store=state,
        email_connector=email,
    ).weekly().report

    blind_spots = report.split("## BLIND-SPOT AUDIT", 1)[1].split(
        "## EMAIL BACKLOG / PARSE ERRORS", 1
    )[0]
    assert "Repeated parser failures: 1 repeated signature(s)" in blind_spots
    assert "Single-source dependence: 1/1" in blind_spots
    assert "Unknown-deadline ratio: 1/1" in blind_spots
    assert "Stale official verification: 1/1" in blind_spots
