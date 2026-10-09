"""Regression checks for the Academic PI production daily-run contracts."""

from pathlib import Path

from Career_Job_Agent_Framework.core.models import JobRecord
from Career_Job_Agent_Framework.core.state import InMemoryStateStore
from Career_Job_Agent_Framework.deployments.academic_pi import (
    AcademicPiService,
    StaticEmailAdapter,
)
from Career_Job_Agent_Framework.deployments.academic_pi.reports import (
    render_daily_report,
    render_weekly_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "Career_Job_Agent_Framework" / "deployments" / "academic_pi"


def _contract(name: str) -> str:
    return (DEPLOYMENT / "contracts" / name).read_text(encoding="utf-8")


def test_daily_contract_requires_value_free_provenance_and_no_fallback() -> None:
    text = _contract("daily_run.md")
    for token in (
        "CONFIGURATION PROVENANCE",
        "framework_resolution: PASS | FAIL | UNKNOWN",
        "deployment_config_resolution: PASS | FAIL | UNKNOWN",
        "fallback_used: no | yes | unknown",
        "BLOCKING CONFIGURATION DIAGNOSTIC",
        "A selector copied from a saved task prompt is not resolution evidence",
    ):
        assert token in text


def test_daily_contract_requires_rss_gmail_dedupe_and_full_report() -> None:
    text = _contract("daily_run.md")
    for token in (
        "AcademicJobsOnline Faculty and Open Rank RSS",
        "Gmail academic-alert scope",
        "CURRENT ACTIVE TIER 1",
        "CURRENT ACTIVE TIER 2",
        "salary",
        "QOL",
        "independence",
        "tenure/faculty-track",
        "startup/lab-space",
        "teaching",
        "verification confidence",
        "ChatGPT-visible report is mandatory",
    ):
        assert token in text


def test_shadow_mode_forbids_gmail_mutation() -> None:
    daily = _contract("daily_run.md")
    runtime = _contract("runtime.md")
    gmail = (DEPLOYMENT / "docs" / "GMAIL_ALERTS.md").read_text(encoding="utf-8")

    for text in (daily, runtime, gmail):
        normalized = " ".join(text.split()).lower()
        assert "shadow mode" in normalized
        assert "archive" in normalized
        assert "label" in normalized
    assert "separately approved" in daily
    assert "separately approved" in gmail


def test_runtime_contract_preserves_task_state_and_bounded_gate() -> None:
    text = _contract("runtime.md")
    for token in (
        "existing Academic scheduled task only",
        "existing dedicated Academic Sheet",
        "exactly three bounded validation runs",
        "daily 5:00 AM",
        "America/New_York",
        "no fourth accelerated run",
        "Preserve the existing Sheet, State, Reports, bindings",
    ):
        assert token in text


def test_gmail_delivery_is_non_blocking_but_never_unconfirmed_success() -> None:
    daily = _contract("daily_run.md")
    runtime = _contract("runtime.md")
    for text in (daily, runtime):
        assert "non-blocking" in text
        assert "connector confirmation" in text
        assert "uncertain" in text


def test_daily_report_always_emits_value_free_provenance() -> None:
    report = render_daily_report()
    assert "CONFIGURATION PROVENANCE" in report
    assert "framework_resolution: UNKNOWN" in report
    assert "deployment_config_resolution: UNKNOWN" in report
    assert "fallback_used: unknown" in report

    explicit = render_daily_report(
        configuration_provenance={
            "framework_source": "Sikawo/ai_research_os/framework",
            "framework_resolution": "PASS",
            "deployment_config_source": "Sikawo/personal_config/academic",
            "deployment_config_resolution": "PASS",
            "fallback_used": "no",
        }
    )
    assert "framework_resolution: PASS" in explicit
    assert "deployment_config_resolution: PASS" in explicit
    assert "fallback_used: no" in explicit


def test_current_active_report_deduplicates_canonical_roles() -> None:
    job = JobRecord(
        canonical_id="synthetic-role",
        title="Assistant Professor",
        institution="Synthetic University",
        official_url="https://example.edu/jobs/synthetic-role",
        lifecycle_status="open",
        verification_status="verified_open",
        tier="Tier 1",
    )
    report = render_daily_report(current_active_jobs=[job, job])
    assert report.count("**Synthetic University — Assistant Professor**") == 2
    assert report.split("## CURRENT ACTIVE TIER 1", 1)[1].split(
        "## CURRENT ACTIVE TIER 2", 1
    )[0].count("**Synthetic University — Assistant Professor**") == 1
    weekly = render_weekly_report(current_active_jobs=[job, job])
    assert "CONFIGURATION PROVENANCE" in weekly
    assert "label_mutation: disabled (shadow mode)" in weekly
    assert weekly.split("## CURRENT ACTIVE TIER 1", 1)[1].split(
        "## CURRENT ACTIVE TIER 2", 1
    )[0].count("**Synthetic University — Assistant Professor**") == 1


def test_shadow_mode_does_not_call_email_label_adapter() -> None:
    email = StaticEmailAdapter(
        messages=[
            {
                "message_id": "synthetic-shadow-message",
                "body": "Assistant Professor https://example.edu/jobs/shadow",
            }
        ]
    )
    service = AcademicPiService(
        config={
            "academic_pi": {"automation": {"auto_apply": False}, "query_budget": 1},
            "candidate_profile": {
                "scientific_identity": {"primary_fields": ["synthetic field"]}
            },
            "connectors": {
                "plugins": [
                    {
                        "id": "synthetic_email",
                        "enabled": True,
                        "options": {
                            "processing_mode": "shadow",
                            "label_mutation_enabled": False,
                            "archive_enabled": False,
                            "delete_enabled": False,
                        },
                    }
                ],
                "bindings": {"email": "synthetic_email"},
            },
            "configuration_provenance": {
                "framework_source": "synthetic/public-framework",
                "framework_resolution": "PASS",
                "deployment_config_source": "synthetic/private-overlay",
                "deployment_config_resolution": "PASS",
                "fallback_used": "no",
            },
        },
        state_store=InMemoryStateStore(),
        email_connector=email,
    )
    result = service.daily()
    assert result.label_plans
    assert email.applied_plans == []
    run = next(row for row in service.state.list_runs() if row.run_id == result.run_id)
    assert run.extra["email_labels_applied"] is False
    assert "label_mutation: disabled (shadow mode)" in result.report


def test_missing_provenance_stops_before_state_or_email_side_effects() -> None:
    email = StaticEmailAdapter(
        messages=[
            {
                "message_id": "synthetic-blocked-message",
                "body": "Assistant Professor https://example.edu/jobs/blocked",
            }
        ]
    )
    state = InMemoryStateStore()
    service = AcademicPiService(
        config={
            "academic_pi": {"automation": {"auto_apply": False}, "query_budget": 1},
            "connectors": {
                "plugins": [
                    {
                        "id": "synthetic_email",
                        "enabled": True,
                        "options": {"processing_mode": "shadow"},
                    }
                ],
                "bindings": {"email": "synthetic_email"},
            },
        },
        state_store=state,
        email_connector=email,
    )
    result = service.daily()
    assert "BLOCKING CONFIGURATION DIAGNOSTIC" in result.report
    assert "framework_resolution: UNKNOWN" in result.report
    assert email.applied_plans == []
    assert state.list_runs() == []
    assert state.list_jobs() == []


def test_injected_live_adapter_cannot_bypass_provenance_gate() -> None:
    email = StaticEmailAdapter(
        messages=[
            {
                "message_id": "synthetic-injected-message",
                "body": "Assistant Professor https://example.edu/jobs/injected",
            }
        ]
    )
    state = InMemoryStateStore()
    result = AcademicPiService(
        config={
            "academic_pi": {"automation": {"auto_apply": False}, "query_budget": 1}
        },
        state_store=state,
        email_connector=email,
    ).daily()
    assert "BLOCKING CONFIGURATION DIAGNOSTIC" in result.report
    assert state.list_jobs() == []
    assert state.list_runs() == []
    assert email.applied_plans == []
