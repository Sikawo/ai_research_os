"""Focused tests for pure target-institution monitor planning."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from Career_Job_Agent_Framework.deployments.academic_pi.handoff import (
    validate_schema_payload,
)
from Career_Job_Agent_Framework.deployments.academic_pi.institution_monitor import (
    build_scan_evidence,
    domain_fallback_queries,
    is_authoritative_target_url,
    plan_target_scan,
    role_disposition,
    target_cadence_days,
    target_is_due,
)


DEPLOYMENT = (
    Path(__file__).resolve().parents[1]
    / "Career_Job_Agent_Framework"
    / "deployments"
    / "academic_pi"
)


def _target(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "synthetic_institute",
        "name": "Synthetic Institute",
        "aliases": ["SI"],
        "country": "US",
        "region": "Example Metro",
        "priority_tier": "S",
        "priority": 100,
        "enabled": True,
        "domains": ["synthetic.example.edu"],
        "career_urls": ["https://synthetic.example.edu/careers"],
        "department_urls": [],
        "departments": [],
        "expected_role_terms": ["Assistant Professor", "Principal Investigator"],
        "interval_days": 1,
        "notes": None,
    }
    value.update(overrides)
    return value


def test_s_and_a_tiers_default_to_daily_and_weekly() -> None:
    s_target = _target()
    a_target = _target(id="weekly", priority_tier="A", interval_days=None)
    s_target.pop("interval_days")

    assert target_cadence_days(s_target) == 1
    assert target_cadence_days(a_target) == 7

    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    assert target_is_due(
        s_target, {"last_attempt_at": "2026-10-04T00:00:00Z"}, now=now
    )
    assert not target_is_due(
        a_target, {"last_attempt_at": "2026-10-01T00:00:00Z"}, now=now
    )
    assert target_is_due(
        a_target, {"last_attempt_at": "2026-09-28T00:00:00Z"}, now=now
    )


def test_plan_is_bounded_and_keeps_official_urls_first() -> None:
    target = _target(
        department_urls=["https://synthetic.example.edu/biology/recruitment"],
        expected_role_terms=[f"Role {index}" for index in range(20)],
    )
    plan = plan_target_scan(target, max_fallback_queries=5)

    assert plan.official_urls == (
        "https://synthetic.example.edu/careers",
        "https://synthetic.example.edu/biology/recruitment",
    )
    assert len(plan.fallback_queries) == 5
    assert all(query.startswith("site:synthetic.example.edu") for query in plan.fallback_queries)
    assert domain_fallback_queries(target, max_queries=0) == ()


def test_broken_url_is_retained_and_replacement_is_only_evidence() -> None:
    target = _target()
    result = build_scan_evidence(
        target,
        checked_urls=["https://synthetic.example.edu/careers"],
        broken_urls=["https://synthetic.example.edu/careers"],
        fallback_queries_used=[
            'site:synthetic.example.edu "faculty recruitment"'
        ],
        replacement_urls={
            "https://synthetic.example.edu/careers":
            "https://synthetic.example.edu/faculty-recruitment"
        },
        attempted_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        error="configured URL returned 404",
    )

    assert result["status"] == "failed"
    assert result["target_retained"] is True
    assert result["retained_configured_urls"] == [
        "https://synthetic.example.edu/careers"
    ]
    assert result["domain_fallback_used"] is True
    assert result["replacement_url_evidence"] == [
        {
            "old_url": "https://synthetic.example.edu/careers",
            "replacement_url": "https://synthetic.example.edu/faculty-recruitment",
        }
    ]


def test_successful_zero_result_is_successful_coverage() -> None:
    url = "https://synthetic.example.edu/careers"
    result = build_scan_evidence(
        _target(),
        checked_urls=[url],
        successful_urls=[url],
        matching_jobs_found=0,
    )

    assert result["status"] == "success"
    assert result["matching_jobs_found"] == 0
    assert result["last_success_at"] is not None


def test_authority_and_ambiguous_research_scientist_behavior() -> None:
    target = _target()
    assert is_authoritative_target_url(
        "https://jobs.synthetic.example.edu/REQ-1", target
    )
    assert is_authoritative_target_url(
        "https://official-ats.example/REQ-1",
        target,
        official_ats_domains=["official-ats.example"],
    )
    assert not is_authoritative_target_url("https://board.example/REQ-1", target)
    assert role_disposition("Postdoctoral Fellow") == "exclude"
    assert role_disposition("Assistant Professor of Biology") == "include"
    assert role_disposition("Research Scientist") == "exclude"
    assert role_disposition(
        "Research Scientist",
        "The appointee will lead an independent research group and recruit a team.",
    ) == "review"


def test_synthetic_private_overlay_template_validates() -> None:
    payload = yaml.safe_load(
        (DEPLOYMENT / "templates" / "target_institutions.example.yaml").read_text(
            encoding="utf-8"
        )
    )
    validate_schema_payload(payload, "target_institutions.schema.json")
    assert {row["priority_tier"] for row in payload["institutions"]} == {"S", "A"}
    assert {row["interval_days"] for row in payload["institutions"]} == {1, 7}
