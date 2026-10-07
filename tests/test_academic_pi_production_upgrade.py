"""Integration contracts for the production email/RSS/target/QOL upgrade."""

from __future__ import annotations

from pathlib import Path

from Career_Job_Agent_Framework.core.config import load_config_file
from Career_Job_Agent_Framework.deployments.academic_pi.cli import build_parser
from Career_Job_Agent_Framework.deployments.academic_pi.handoff import (
    validate_schema_payload,
)
from Career_Job_Agent_Framework.deployments.academic_pi.models import AcademicJob
from Career_Job_Agent_Framework.deployments.academic_pi.qol import (
    unknown_qol_assessment,
)
from Career_Job_Agent_Framework.deployments.academic_pi.reports import (
    render_daily_report,
    render_weekly_report,
)
from Career_Job_Agent_Framework.deployments.academic_pi.service import AcademicPiService


DEPLOYMENT = Path("Career_Job_Agent_Framework/deployments/academic_pi")


def test_source_catalog_exposes_two_ajo_feeds_and_first_class_sources() -> None:
    catalog = load_config_file(DEPLOYMENT / "config" / "source_catalog.yaml")
    sources = {row["id"]: row for row in catalog["sources"]}
    ajo = sources["academic_jobs_online"]

    assert ajo["supports_rss"] is True
    assert len(ajo["feed_urls"]) == 2
    assert ajo["bootstrap_url"].endswith("/ajo/jobs/job")
    assert {"jrec_in", "asm_career_connections", "institution_direct"} <= sources.keys()
    assert "ascb" not in sources
    for row in sources.values():
        validate_schema_payload(row, "source.schema.json")


def test_qol_is_a_true_top_level_academic_job_round_trip() -> None:
    assessment = unknown_qol_assessment("Synthetic evidence is pending.")
    job = AcademicJob(
        canonical_job_id="synthetic-qol-job",
        institution="Synthetic University",
        raw_title="Assistant Professor",
        qol_assessment=assessment,
    )

    payload = job.to_dict()
    assert payload["qol_assessment"]["status"] == "unknown"
    restored = AcademicJob.from_dict(payload).to_dict()
    assert restored["qol_assessment"] == payload["qol_assessment"]
    assert "qol_assessment" not in restored["extra"]


def test_target_priority_tiers_drive_service_cadence() -> None:
    service = AcademicPiService(config={"academic_pi": {}})
    assert service._cadence_days({"priority_tier": "S"}, institution=True) == 1
    assert service._cadence_days({"priority_tier": "A"}, institution=True) == 7
    assert service._cadence_days(
        {"priority_tier": "A", "interval_days": 2}, institution=True
    ) == 2


def test_reports_expose_qol_and_three_discovery_lanes() -> None:
    job = {
        "identity": {
            "canonical_job_id": "synthetic-report-job",
            "institution": "Synthetic University",
            "raw_title": "Assistant Professor",
        },
        "status": {"verification_status": "verified_open"},
        "evaluation": {"tier": "Tier 1", "fit_score": 90},
        "qol_assessment": unknown_qol_assessment("Housing is pending."),
    }
    daily = render_daily_report(
        [job],
        current_active_jobs=[job],
        coverage=[
            {"source_id": "email_alert", "status": "active"},
            {"source_id": "academic_jobs_online", "status": "success"},
            {"institution": "Synthetic University", "status": "success"},
        ],
    )
    weekly = render_weekly_report([job], current_active_jobs=[job])

    for heading in (
        "## COMPENSATION & QOL",
        "## Email alerts",
        "## RSS feeds",
        "## Target institutions",
        "## BLIND SPOTS",
    ):
        assert heading in daily
    assert "Salary: not stated on verified official source" in daily
    assert "## COMPENSATION & QOL COMPARISON" in weekly
    assert "## STALE QOL / COMPENSATION ASSUMPTIONS" in weekly


def test_reports_include_ajo_parser_errors_in_rss_section() -> None:
    error = {
        "category": "parser_error",
        "source_id": "academic_jobs_online",
        "message": "synthetic malformed feed",
    }

    daily = render_daily_report(verification_errors=[error])
    weekly = render_weekly_report(errors=[error])

    expected = "## RSS ERRORS\n- synthetic malformed feed"
    assert expected in daily
    assert expected in weekly


def test_production_cli_commands_are_registered() -> None:
    parser = build_parser()
    parser.parse_args(["--state", "synthetic.json", "scan-rss", "academic_jobs_online"])
    parser.parse_args(["--state", "synthetic.json", "scan-email"])
    parser.parse_args(["--state", "synthetic.json", "refresh-qol", "job-1"])
    parser.parse_args(["--state", "synthetic.json", "source-health"])
    parser.parse_args(["--state", "synthetic.json", "target-health"])
