"""Regression coverage for Academic PI handoff and reporting boundaries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from math import inf, nan

import pytest

from Career_Job_Agent_Framework.core.models import JobRecord, VerificationStatus
from Career_Job_Agent_Framework.deployments.academic_pi.handoff import (
    ContractValidationError,
    build_gatedsprint_handoff,
    render_gatedsprint_handoff,
    validate_schema_payload,
)
from Career_Job_Agent_Framework.deployments.academic_pi.reports import (
    render_daily_report,
    render_weekly_report,
)
from Career_Job_Agent_Framework.deployments.academic_pi.scoring import (
    score_academic_fit,
)


def _handoff_job(**overrides: object) -> JobRecord:
    values: dict[str, object] = {
        "canonical_id": "job:handoff-1",
        "title": "Assistant Professor of Biology",
        "institution": "Contract University",
        "department": "Biology",
        "official_url": "https://jobs.example.edu/handoff-1",
        "lifecycle_status": "open",
        "verification_status": VerificationStatus.VERIFIED_OPEN,
        "last_verified": "2026-10-04T00:00:00Z",
        "verification_confidence": 1.0,
        "role_class": "tenure_track_faculty",
        "evaluation": {
            "fit_score": 88.0,
            "tier": "Tier 1",
            "strongest_matches": ["direct scientific alignment"],
            "meaningful_gaps": [],
            "hard_blockers": [],
            "uncertainty": [],
        },
    }
    values.update(overrides)
    return JobRecord.from_dict(values)


def _authorized_evidence() -> list[dict[str, object]]:
    return [
        {
            "ref": "candidate-evidence:E-1",
            "strength": "strong_direct_evidence",
            "authorized": True,
        }
    ]


def test_handoff_uses_spec_field_names_and_strict_json() -> None:
    payload = build_gatedsprint_handoff(
        _handoff_job(),
        evidence=_authorized_evidence(),
    )

    assert payload["job"]["canonical_job_id"] == "job:handoff-1"
    assert "canonical_id" not in payload["job"]
    assert payload["search"]["normalized_role_class"] == "tenure_track_faculty"
    assert "role_class" not in payload["search"]
    validate_schema_payload(payload, "gatedsprint_handoff.schema.json")

    rendered = render_gatedsprint_handoff(
        _handoff_job(),
        evidence=_authorized_evidence(),
    )
    assert json.loads(rendered) == payload
    assert "NaN" not in rendered


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lifecycle_status": "closed"}, "lifecycle"),
        (
            {"verification_status": VerificationStatus.VERIFICATION_PENDING},
            "currently verified",
        ),
        ({"verification_stale": True}, "stale"),
        (
            {"last_verification_transition_accepted": False},
            "transition was not accepted",
        ),
        ({"official_url": None}, "official URL"),
        ({"last_verified": None}, "last_verified"),
    ],
)
def test_handoff_rejects_jobs_that_are_not_currently_verified(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ContractValidationError, match=message):
        build_gatedsprint_handoff(
            _handoff_job(**overrides),
            evidence=_authorized_evidence(),
        )


def test_handoff_requires_authorized_evidence_for_positive_fit_claims() -> None:
    with pytest.raises(ContractValidationError, match="at least one authorized"):
        build_gatedsprint_handoff(_handoff_job(), evidence=[])

    with pytest.raises(ContractValidationError, match="not authorized"):
        build_gatedsprint_handoff(
            _handoff_job(),
            evidence=[
                {
                    "ref": "candidate-evidence:E-1",
                    "strength": "uncertain",
                    "authorized": False,
                }
            ],
        )

    with pytest.raises(ContractValidationError, match="not authorized"):
        build_gatedsprint_handoff(
            _handoff_job(),
            evidence=[{"ref": "candidate-evidence:E-1", "strength": "uncertain"}],
        )
    with pytest.raises(ContractValidationError, match="not authorized"):
        build_gatedsprint_handoff(
            _handoff_job(),
            evidence=["candidate-evidence:E-1"],
        )


def test_handoff_enforces_timestamp_freshness_from_cadence() -> None:
    with pytest.raises(ContractValidationError, match="older than the allowed cadence"):
        build_gatedsprint_handoff(
            _handoff_job(last_verified="2026-09-01T00:00:00Z"),
            evidence=_authorized_evidence(),
            max_verification_age_days=7,
            now=datetime(2026, 10, 4, tzinfo=timezone.utc),
        )


def test_deadline_action_never_renders_complete_job_repr_or_private_package() -> None:
    job = _handoff_job(
        deadline="2026-10-11",
        application={"package_path": "PRIVATE_PACKAGE_REFERENCE"},
    )

    report = render_daily_report(deadline_alerts=[job])
    action = report.split("## Action Required", 1)[1].split("## ", 1)[0]

    assert "job:handoff-1" in action
    assert "Contract University" in action
    assert "PRIVATE_PACKAGE_REFERENCE" not in action
    assert "JobRecord(" not in action


@pytest.mark.parametrize("non_finite", [nan, inf, -inf])
def test_handoff_rejects_non_finite_schema_numbers(non_finite: float) -> None:
    job = _handoff_job(
        evaluation={
            "fit_score": non_finite,
            "tier": "Tier 1",
            "strongest_matches": ["claim"],
        }
    )

    with pytest.raises(ContractValidationError, match="expected number"):
        build_gatedsprint_handoff(job, evidence=_authorized_evidence())
    with pytest.raises(ContractValidationError, match="expected number"):
        render_gatedsprint_handoff(job, evidence=_authorized_evidence())


def test_private_thresholds_override_public_tiering() -> None:
    job = _handoff_job(
        description="Independent virology research program",
        search_scope={"broad_search": False},
    )
    profile = {
        "career_stage": {"target_independence": ["tenure_track_faculty"]},
        "scientific_identity": {"primary_fields": ["virology"]},
        "departments": {"strong_fit": ["Biology"]},
    }
    evaluation = score_academic_fit(
        job,
        profile,
        {
            "tiering": {
                "tier_1_min_fit": 101,
                "tier_2_min_fit": 101,
                "watchlist_min_fit": 101,
            },
            "thresholds": {
                "tier_1_min_fit": 0,
                "tier_2_min_fit": 0,
                "watchlist_min_fit": 0,
            },
        },
    )

    assert evaluation.tier == "Tier 1"


def test_rejected_jobs_are_not_reported_as_verification_pending() -> None:
    rejected = _handoff_job(
        institution="Rejected University",
        rejected=True,
        verification_status=VerificationStatus.VERIFICATION_PENDING,
        independence_class="ambiguous",
        tier="Watchlist",
    )

    assert "Rejected University" not in render_daily_report([rejected])
    assert "Rejected University" not in render_weekly_report([rejected])


def test_report_location_falls_back_to_job_record_location() -> None:
    job = _handoff_job(
        location="Remote within Europe",
        country="DE",
        tier="Tier 1",
        fit_score=88.0,
    )

    report = render_daily_report([job], current_active_jobs=[job])

    assert "Location: Remote within Europe" in report
