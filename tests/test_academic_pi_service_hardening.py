"""Security and durability regressions for Academic PI service boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from Career_Job_Agent_Framework.core.connectors import DiscoveryBatch
from Career_Job_Agent_Framework.core.models import (
    JobRecord,
    SourceAuthority,
    VerificationResult,
    VerificationStatus,
)
from Career_Job_Agent_Framework.core.state import InMemoryStateStore
from Career_Job_Agent_Framework.deployments.academic_pi import (
    AcademicPiService,
    CallableVerificationAdapter,
    StaticEmailAdapter,
)
from Career_Job_Agent_Framework.deployments.academic_pi.cli import main
from Career_Job_Agent_Framework.deployments.academic_pi.email_ingestion import (
    parse_academic_alert_result,
)
from Career_Job_Agent_Framework.deployments.academic_pi.models import AcademicJob


def _base_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "academic_pi": {"automation": {"auto_apply": False}, "query_budget": 1},
        "candidate_profile": {
            "scientific_identity": {"primary_fields": ["virology"]},
        },
        "target_institutions": {"institutions": []},
        "configuration_provenance": {
            "framework_source": "synthetic/public-framework",
            "framework_resolution": "PASS",
            "deployment_config_source": "synthetic/private-overlay",
            "deployment_config_resolution": "PASS",
            "fallback_used": "no",
        },
    }
    config.update(overrides)
    return config


def _official_verifier(authority: SourceAuthority = SourceAuthority.OFFICIAL_DETAIL):
    return CallableVerificationAdapter(
        lambda job: VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            source_url=job.official_url
            or (job.discovery_urls[0] if job.discovery_urls else None),
            source_id="official",
            authority=authority,
            confidence=0.99,
        ),
        connector_id="official",
    )


class _Connector:
    def __init__(self, connector_id: str, batch: DiscoveryBatch) -> None:
        self.connector_id = connector_id
        self.batch = batch
        self.calls = 0

    def discover(self, request: Any) -> DiscoveryBatch:
        self.calls += 1
        return self.batch


def test_discovery_payload_cannot_target_or_clear_a_human_rejection() -> None:
    state = InMemoryStateStore()
    inserted = state.upsert_job(
        JobRecord(
            canonical_id="victim",
            title="Assistant Professor of Biology",
            institution="Safe University",
            organization="Safe University",
            official_job_id="REQ-1",
            official_url="https://safe.example.edu/jobs/REQ-1",
            rejected=True,
            manual_review_state="not_interested",
            extra={"human_override": {"source": "human"}},
        )
    )
    connector = _Connector(
        "board",
        DiscoveryBatch(
            source_id="board",
            candidates=[
                {
                    "canonical_id": "victim",
                    "title": "Assistant Professor of Biology",
                    "institution": "Safe University",
                    "official_job_id": "REQ-1",
                    "official_url": "https://safe.example.edu/jobs/REQ-1",
                    "rejected": False,
                    "manual_review_state": "reviewed",
                    "verification_authority": 999,
                    "field_authority": {"title": 999},
                    "evaluation": {"fit_score": 100, "tier": "Tier 1"},
                    "application": {"status": "submitted"},
                    "extra": {
                        "clear_manual_override": True,
                        "current_active_verified_open": True,
                    },
                }
            ],
            completed_at="2026-10-04T00:00:00Z",
        ),
    )
    service = AcademicPiService(
        config=_base_config(
            source_catalog={
                "sources": [
                    {
                        "id": "board",
                        "enabled": True,
                        "supports_direct_search": True,
                    }
                ]
            }
        ),
        state_store=state,
        discovery_connectors=[connector],
        verification_connector=_official_verifier(),
    )

    service.daily()

    stored = state.get_job(inserted.job_id or "")
    assert stored is not None
    assert stored.rejected is True
    assert stored.manual_review_state == "not_interested"
    assert stored.application == {}
    assert stored.extra.get("clear_manual_override") is None
    assert stored.extra["human_override"]["source"] == "human"


class _AlternatingFailureStore(InMemoryStateStore):
    def __init__(self) -> None:
        super().__init__()
        self.first_title_was_written = False
        self.second_title_failed = False

    def upsert_job(self, job: Any, *, record_changes: bool = True):
        title = job.title if isinstance(job, JobRecord) else str(job.get("title", ""))
        if "Assistant Professor" in title:
            if self.first_title_was_written:
                raise RuntimeError("first sibling must not be retried")
            self.first_title_was_written = True
        if "Group Leader" in title and not self.second_title_failed:
            self.second_title_failed = True
            raise RuntimeError("second sibling failed once")
        return super().upsert_job(job, record_changes=record_changes)


class _RejectRunLedgerStore(InMemoryStateStore):
    def record_run(self, run: Any):
        raise RuntimeError("synthetic run-ledger failure")


def test_email_candidate_progress_survives_runs_and_skips_completed_siblings() -> None:
    email = StaticEmailAdapter(
        messages=[
            {
                "message_id": "durable-progress",
                "body": (
                    "Assistant Professor of Biology https://alerts.example/job/1\n"
                    "Independent Group Leader https://alerts.example/job/2"
                ),
            }
        ]
    )
    state = _AlternatingFailureStore()
    service = AcademicPiService(
        config=_base_config(
            academic_pi={
                "automation": {"auto_apply": False},
                "query_budget": 1,
                "coverage": {
                    "reverify_active": {
                        "tier_1_interval_days": 99,
                        "tier_2_interval_days": 99,
                        "watchlist_interval_days": 99,
                    }
                },
            }
        ),
        state_store=state,
        email_connector=email,
        verification_connector=_official_verifier(),
    )

    first = service.daily()
    first_run = next(item for item in state.list_runs() if item.run_id == first.run_id)
    assert len(first_run.extra["email_candidate_progress"]["durable-progress"]) == 1
    assert not first.label_plans[0].processed

    second = service.daily()
    assert len(state.list_jobs()) == 2
    assert second.label_plans[0].processed
    assert "first sibling must not be retried" not in second.errors


def test_email_labels_are_not_applied_before_failure_evidence_is_durable() -> None:
    email = StaticEmailAdapter(
        messages=[{"message_id": "parse-failure", "body": "not a job alert"}]
    )
    service = AcademicPiService(
        config=_base_config(),
        state_store=_RejectRunLedgerStore(),
        email_connector=email,
    )

    with pytest.raises(RuntimeError, match="synthetic run-ledger failure"):
        service.daily()

    assert email.applied_plans == []


def test_messages_without_provider_ids_use_stable_distinct_fingerprints() -> None:
    one = {"body": "Assistant Professor https://alerts.example/job/1"}
    two = {"body": "Assistant Professor https://alerts.example/job/2"}
    first = parse_academic_alert_result(one)
    repeated = parse_academic_alert_result(one)
    different = parse_academic_alert_result(two)
    assert first.message_id.startswith("synthetic:")
    assert first.message_id == repeated.message_id
    assert first.message_id != different.message_id


def test_disabled_sources_do_not_run_and_unbound_enabled_sources_are_visible() -> None:
    disabled = _Connector(
        "disabled_board",
        DiscoveryBatch(source_id="disabled_board", completed_at="2026-10-04T00:00:00Z"),
    )
    state = InMemoryStateStore()
    service = AcademicPiService(
        config=_base_config(
            source_catalog={
                "sources": [
                    {
                        "id": "disabled_board",
                        "enabled": False,
                        "supports_direct_search": True,
                    },
                    {
                        "id": "missing_board",
                        "enabled": True,
                        "supports_direct_search": True,
                    },
                ]
            }
        ),
        state_store=state,
        discovery_connectors=[disabled],
    )

    service.daily()

    assert disabled.calls == 0
    coverage = {item.source_id: item for item in state.list_source_coverage()}
    assert "disabled_board" not in coverage
    assert coverage["missing_board"].status == "not_configured"


def test_empty_source_batch_without_visit_evidence_is_incomplete() -> None:
    connector = _Connector("empty", DiscoveryBatch(source_id="empty"))
    state = InMemoryStateStore()
    result = AcademicPiService(
        config=_base_config(
            source_catalog={
                "sources": [
                    {"id": "empty", "enabled": True, "supports_direct_search": True}
                ]
            }
        ),
        state_store=state,
        discovery_connectors=[connector],
    ).daily()
    assert state.list_source_coverage()[0].status == "incomplete"
    assert result.metrics["sources_successful"] == 0


def test_complete_public_contracts_are_schema_validated_before_cli_execution(
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = {
        "profile_version": 999,
        "identity": {},
        "career_stage": {},
        "scientific_identity": {},
        "evidence": {},
        "departments": {},
        "eligibility": {},
        "career_constraints": {},
        "unexpected": True,
    }
    preferences = {
        "version": 1,
        "geography": {},
        "institution_types": {},
        "role_preferences": {},
        "teaching": {},
        "compensation": {},
        "quality_of_life": {},
        "reporting": {"deadline_warning_days": 14},
    }
    source = {
        "id": "board",
        "name": "Board",
        "class": "SCIENCE_JOB_BOARD",
        "base_url": None,
        "regions": ["GLOBAL"],
        "enabled_by_default": True,
        "priority": 50,
        "frequency_class": "high",
        "discovery_method": "configured_runtime_search",
        "supports_email_alerts": False,
        "supports_direct_search": True,
        "verification_authority": "discovery_only",
        "expected_update_cadence": "daily",
        "parser_version": 1,
        "unexpected": True,
    }
    service = AcademicPiService(
        config=_base_config(
            candidate_profile=profile,
            preferences=preferences,
            source_catalog={"sources": [source]},
        )
    )
    assert main(["validate-config"], service=service) == 2
    output = capsys.readouterr().out
    assert "profile_version" in output
    assert "additional property" in output
    assert "source_catalog.sources[0]" in output
    assert "deadline_warning_days must be an array" in output


def test_validate_config_reports_missing_public_contract_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = AcademicPiService(
        config=_base_config(
            candidate_profile={
                "profile_version": 1,
                "scientific_identity": {"primary_fields": ["virology"]},
            },
            preferences={"version": 1},
            source_catalog={
                "sources": [
                    {
                        "id": "board",
                        "enabled": True,
                        "supports_direct_search": True,
                    }
                ]
            },
        )
    )

    assert main(["validate-config"], service=service) == 2
    output = capsys.readouterr().out
    assert "required property is missing" in output
    assert "candidate_profile.identity" in output
    assert "preferences.geography" in output
    assert "source_catalog.sources[0].name" in output


def test_private_threshold_overrides_replace_public_tiering_values() -> None:
    service = AcademicPiService(
        config=_base_config(
            academic_pi={
                "automation": {"auto_apply": False},
                "tiering": {"tier_1_min_fit": 80, "tier_2_min_fit": 68},
            },
            scoring_overrides={
                "scoring": {
                    "thresholds": {"tier_1_min_fit": 93, "tier_2_min_fit": 81}
                }
            },
        )
    )
    assert service.scoring_config["tiering"]["tier_1_min_fit"] == 93
    assert service.scoring_config["tiering"]["tier_2_min_fit"] == 81


def test_nested_academic_job_payload_round_trips_all_operational_sections() -> None:
    payload = AcademicJob(
        canonical_job_id="job-1",
        institution="Roundtrip University",
        raw_title="Assistant Professor",
        normalized_role_class="tenure_track_faculty",
        first_discovered_by="board",
        all_discovery_sources=["board", "institution_direct"],
        source_message_ids=["message-1"],
        first_seen="2026-10-01T00:00:00Z",
        last_seen="2026-10-04T00:00:00Z",
        posted_date="2026-09-30",
        deadline="2026-11-01",
        deadline_type="fixed",
        expected_start_date="2027-01-01",
        declared_fields=["virology"],
        broad_search=True,
        department_scope=["Biology"],
        rank_scope=["Assistant Professor"],
        required_degree="PhD",
        required_expertise=["virology"],
        required_documents=["CV"],
        position={"tenure_status": "tenure-track"},
        evaluation={
            "fit_score": 82,
            "tier": "Tier 1",
            "strongest_matches": ["virology"],
        },
        application={"status": "preparing_application"},
    ).to_dict()

    job = AcademicPiService(config=_base_config())._coerce_job(payload, trusted=True)

    assert job.canonical_id == "job-1"
    assert job.source_message_ids == ["message-1"]
    assert {row["source_id"] for row in job.source_provenance} == {
        "board",
        "institution_direct",
    }
    assert job.first_seen == "2026-10-01T00:00:00Z"
    assert job.posted_date == "2026-09-30"
    assert job.expected_start_date == "2027-01-01"
    assert job.search_scope["broad_search"] is True
    assert job.requirements["required_degree"] == "PhD"
    assert job.position["tenure_status"] == "tenure-track"
    assert job.evaluation["fit_score"] == 82
    assert job.application["status"] == "preparing_application"


def test_lower_precedence_attempt_cannot_count_or_unlock_manual_evaluation() -> None:
    state = InMemoryStateStore()
    inserted = state.upsert_job(
        JobRecord(
            title="Assistant Professor",
            institution="Authority University",
            organization="Authority University",
            official_job_id="AUTH-1",
            official_url="https://authority.example.edu/AUTH-1",
            lifecycle_status="closed",
            verification_status=VerificationStatus.VERIFIED_CLOSED,
            verification_authority=SourceAuthority.OFFICIAL_DETAIL,
            last_verified="2026-10-04T00:00:00Z",
            field_authority={
                "lifecycle_status": int(SourceAuthority.OFFICIAL_DETAIL),
                "verification_status": int(SourceAuthority.OFFICIAL_DETAIL),
            },
        )
    )
    service = AcademicPiService(
        config=_base_config(),
        state_store=state,
        verification_connector=_official_verifier(SourceAuthority.OFFICIAL_DEPARTMENT),
    )

    with pytest.raises(RuntimeError, match="fresh open-status verification"):
        service.evaluate(inserted.job_id or "")
    stored = state.get_job(inserted.job_id or "")
    assert stored is not None
    assert stored.extra["last_verification_transition_accepted"] is False
    assert stored.lifecycle_status == "closed"


def test_scan_frequency_and_active_reverification_cadence_are_honored() -> None:
    calls = 0

    def verify(job: JobRecord) -> VerificationResult:
        nonlocal calls
        calls += 1
        return VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            source_url=job.official_url,
            source_id="official",
            authority=SourceAuthority.OFFICIAL_DETAIL,
        )

    now = datetime.now(timezone.utc)
    state = InMemoryStateStore()
    state.upsert_job(
        JobRecord(
            title="Assistant Professor",
            institution="Cadence University",
            organization="Cadence University",
            official_job_id="CADENCE-1",
            official_url="https://cadence.example.edu/CADENCE-1",
            lifecycle_status="open",
            verification_status=VerificationStatus.VERIFIED_OPEN,
            last_verified=now.isoformat().replace("+00:00", "Z"),
            tier="Tier 2",
            extra={
                "last_verification_attempted_at": now.isoformat().replace(
                    "+00:00", "Z"
                )
            },
        )
    )
    service = AcademicPiService(
        config=_base_config(
            academic_pi={
                "automation": {"auto_apply": False},
                "query_budget": 1,
                "coverage": {
                    "frequency_classes": {"medium": {"interval_days": 3}},
                    "reverify_active": {"tier_2_interval_days": 3},
                },
            }
        ),
        state_store=state,
        verification_connector=CallableVerificationAdapter(verify),
    )
    assert service._cadence_days({"scan_frequency": "medium"}) == 3
    result = service.daily()
    assert calls == 0
    assert result.metrics["tier2_active"] == 0

    stored = state.list_jobs()[0]
    stored.extra["last_verification_attempted_at"] = (
        now - timedelta(days=4)
    ).isoformat().replace("+00:00", "Z")
    state.upsert_job(stored)
    service.daily()
    assert calls == 1


def test_service_rejects_handoff_for_non_open_or_rejected_verification() -> None:
    state = InMemoryStateStore()
    inserted = state.upsert_job(
        JobRecord(
            canonical_id="closed-handoff",
            title="Assistant Professor",
            institution="Closed University",
            official_url="https://closed.example.edu/job",
            lifecycle_status="closed",
            verification_status=VerificationStatus.VERIFIED_CLOSED,
            last_verified="2026-10-04T00:00:00Z",
            extra={"last_verification_transition_accepted": False},
        )
    )
    with pytest.raises(ValueError, match="currently verified-open"):
        AcademicPiService(config=_base_config(), state_store=state).handoff(
            inserted.job_id or ""
        )
