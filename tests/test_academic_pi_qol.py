"""Focused tests for pure Academic PI compensation and QOL helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Career_Job_Agent_Framework.core.models import JobRecord, VerificationStatus
from Career_Job_Agent_Framework.deployments.academic_pi.qol import (
    attach_qol_assessment,
    build_budget_scenario,
    build_qol_assessment,
    invalidate_qol_assessment,
    normalize_compensation,
    qol_refresh_reasons,
    requires_full_qol,
    unknown_qol_assessment,
)
from Career_Job_Agent_Framework.deployments.academic_pi.service import AcademicPiService


def _actionable_job(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "identity": {
            "country": "US",
            "city": "Example City",
            "region": "Example State",
        },
        "position": {
            "salary_min": 90000,
            "salary_max": 110000,
            "salary_currency": "USD",
            "salary_period": "annual",
            "salary_basis": "12-month",
        },
        "status": {"verification_status": "verified_open"},
        "evaluation": {"tier": "Tier 2", "fit_score": 75.0},
    }
    value.update(overrides)
    return value


def _complete_costs() -> dict[str, float]:
    return {
        "rent": 2400,
        "childcare": 1600,
        "education": 0,
        "food": 900,
        "healthcare": 500,
        "transport": 450,
        "utilities_internet": 300,
        "other_needs": 350,
    }


def test_only_verified_tier_1_or_2_triggers_full_qol() -> None:
    assert requires_full_qol(_actionable_job())
    assert not requires_full_qol(
        _actionable_job(evaluation={"tier": "Watchlist", "fit_score": 75.0})
    )
    assert not requires_full_qol(
        _actionable_job(status={"verification_status": "verification_pending"})
    )


def test_nine_month_basis_is_preserved_without_annualization() -> None:
    result = normalize_compensation(
        {
            "salary_min": 80000,
            "salary_max": 100000,
            "salary_currency": "USD",
            "salary_period": "academic_year",
            "salary_basis": "9-month",
        },
        country="US",
    )

    assert result["salary_min"] == 80000
    assert result["salary_max"] == 100000
    assert result["period"] == "academic_year"
    assert result["basis"] == "9-month"


def test_australian_super_is_excluded_from_spendable_salary() -> None:
    result = normalize_compensation(
        {
            "salary_min": 112000,
            "salary_max": 134400,
            "salary_currency": "AUD",
            "salary_period": "annual",
            "salary_basis": "total package including super",
            "salary_includes_super": True,
            "employer_super_rate": 12,
        },
        country="AU",
    )

    assert result["salary_min"] == pytest.approx(100000)
    assert result["salary_max"] == pytest.approx(120000)
    assert "excluded from spendable gross salary" in " ".join(result["notes"])


def test_included_super_without_separation_data_remains_unknown() -> None:
    result = normalize_compensation(
        {
            "salary_min": 112000,
            "salary_max": 134400,
            "salary_includes_super": True,
        },
        country="AU",
    )

    assert result["salary_min"] is None
    assert result["salary_max"] is None
    assert result["unknowns"]


def test_service_qol_refresh_normalizes_nested_australian_super() -> None:
    job = JobRecord(
        canonical_id="synthetic-au-role",
        title="Lecturer",
        institution="Synthetic Australian University",
        country="AU",
        tier="Tier 1",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        lifecycle_status="open",
        position={
            "salary_min": 112000,
            "salary_max": 134400,
            "salary_currency": "AUD",
            "salary_period": "annual",
            "salary_basis": "total package including super",
            "salary_is_estimate": False,
            "employer_retirement_or_super": {
                "included_in_package": True,
                "rate": 0.12,
            },
        },
    )
    service = AcademicPiService(
        config={"academic_pi": {"automation": {"auto_apply": False}}}
    )

    refreshed = service._refresh_qol_for_job(job, force=True)
    compensation = refreshed.extra["qol_assessment"]["compensation"]

    assert compensation["salary_min"] == pytest.approx(100000)
    assert compensation["salary_max"] == pytest.approx(120000)
    assert "excluded from spendable gross salary" in " ".join(
        compensation["notes"]
    )


def test_budget_surplus_requires_all_costs() -> None:
    complete = build_budget_scenario(
        "two bedroom public school",
        gross_salary=100000,
        estimated_monthly_take_home=8000,
        costs=_complete_costs(),
        confidence=0.7,
    )
    assert complete["estimated_monthly_surplus"] == 1500
    assert complete["unknowns"] == []

    incomplete_costs = _complete_costs()
    incomplete_costs["childcare"] = None  # type: ignore[assignment]
    incomplete = build_budget_scenario(
        "unknown childcare",
        gross_salary=100000,
        estimated_monthly_take_home=8000,
        costs=incomplete_costs,
    )
    assert incomplete["estimated_monthly_surplus"] is None
    assert "childcare" in incomplete["unknowns"]


def test_complete_and_unknown_assessments_avoid_false_precision() -> None:
    scenario = build_budget_scenario(
        "representative",
        gross_salary=100000,
        estimated_monthly_take_home=8000,
        costs=_complete_costs(),
    )
    assessment = build_qol_assessment(
        compensation={
            "salary_min": 90000,
            "salary_max": 110000,
            "salary_currency": "USD",
            "salary_period": "annual",
            "salary_basis": "12-month",
            "official": True,
        },
        take_home={
            "annual_net_mid": 96000,
            "filing_assumption": "synthetic single-income assumption",
            "tax_year": 2026,
            "currency": "USD",
            "estimate_method": "synthetic test fixture",
        },
        country="US",
        housing={"two_bedroom_range": [2200, 2800], "sample_size": 5},
        childcare={"monthly_cost_range": [1400, 1800]},
        education={"public_school_summary": "Synthetic official fixture."},
        transport={"commute_summary": "Synthetic peak-hour route fixture."},
        scenarios=[scenario],
        sources=[{"url": "https://official.example/qol-fixture", "kind": "synthetic"}],
        assessed_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )
    assert assessment["status"] == "complete"
    assert assessment["score"] is None
    assert assessment["take_home"]["monthly_net_mid"] == 8000

    unknown = unknown_qol_assessment("Salary source is unavailable.")
    assert unknown["status"] == "unknown"
    assert unknown["score"] is None
    assert "Salary source is unavailable." in unknown["unknowns"]


def test_top_level_attachment_does_not_change_scientific_tier() -> None:
    job = _actionable_job()
    original_evaluation = dict(job["evaluation"])  # type: ignore[arg-type]
    result = attach_qol_assessment(
        job, unknown_qol_assessment("Housing evidence is pending.")
    )

    assert result["qol_assessment"]["status"] == "unknown"
    assert result["evaluation"] == original_evaluation
    assert result["evaluation"]["tier"] == "Tier 2"
    assert "qol_assessment" not in job


def test_staleness_and_material_changes_trigger_refresh() -> None:
    previous = _actionable_job()
    current = _actionable_job(
        identity={
            "country": "US",
            "city": "New Example City",
            "region": "Example State",
        },
        position={
            "salary_min": 95000,
            "salary_max": 115000,
            "salary_currency": "USD",
            "salary_period": "annual",
            "salary_basis": "12-month",
        },
        qol_assessment={
            "status": "complete",
            "assessed_at": "2026-08-01T00:00:00Z",
        },
    )
    reasons = qol_refresh_reasons(
        current,
        previous_job=previous,
        now=datetime(2026, 10, 5, tzinfo=timezone.utc),
        stale_after_days=30,
    )

    assert reasons == (
        "qol_stale",
        "salary_material_change",
        "location_material_change",
    )
    invalidated = invalidate_qol_assessment(
        current["qol_assessment"], "Salary materially changed."
    )
    assert invalidated["status"] == "pending"
    assert invalidated["score"] is None
    assert "Salary materially changed." in invalidated["unknowns"]
