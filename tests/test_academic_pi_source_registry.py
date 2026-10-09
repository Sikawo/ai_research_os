"""Synthetic tests for the offline Academic multi-source registry contract."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from Career_Job_Agent_Framework.deployments.academic_pi.handoff import (
    ContractValidationError,
    validate_schema_payload,
)
from Career_Job_Agent_Framework.deployments.academic_pi.source_registry import (
    build_source_health, canonical_listing_key, is_allowlisted_official_url,
    listings_match, normalize_source_url, plan_source_batches, registry_issues,
)


DEPLOYMENT = Path(__file__).resolve().parents[1] / "Career_Job_Agent_Framework" / "deployments" / "academic_pi"


def _registry() -> dict[str, object]:
    return yaml.safe_load((DEPLOYMENT / "templates" / "institution_source_registry.example.yaml").read_text(encoding="utf-8"))


def test_synthetic_registry_validates_and_is_offline() -> None:
    payload = _registry()
    validate_schema_payload(payload, "institution_source_registry.schema.json")
    assert registry_issues(payload) == ()
    assert payload["registry_mode"] == "offline_only"
    assert not any(row["enabled"] for row in payload["institutions"])


def test_batch_plan_is_bounded_and_deterministic() -> None:
    plans = plan_source_batches(_registry(), include_planned=True, maximum_batch_size=10)
    assert [plan.batch_id for plan in plans] == ["batch_01", "batch_02"]
    assert len(plans[0].institution_ids) == 2
    assert plans[0].cadence_hours == 24
    with pytest.raises(ValueError, match="exceeds maximum size"):
        plan_source_batches(_registry(), include_planned=True, maximum_batch_size=1)


def test_failed_retrieval_is_not_zero_results() -> None:
    failure = build_source_health(
        "synthetic", status="failed", checked_at=datetime(2026, 10, 9, tzinfo=timezone.utc),
        items_seen=None, failure_reason="synthetic timeout",
    )
    assert failure["items_seen"] is None
    validate_schema_payload(failure, "source_health.schema.json")
    with pytest.raises(ValueError, match="must not report an item count"):
        build_source_health("synthetic", status="failed", items_seen=0, failure_reason="timeout")


def test_cross_lane_dedup_prefers_official_identity() -> None:
    rss = {"institution": "Synthetic University", "official_job_id": "FAC-2026-1", "title": "Assistant Professor", "url": "https://jobs.example.edu/FAC-2026-1?utm_source=rss"}
    email = {"institution": " synthetic university ", "requisition_id": "fac-2026-1", "title": "Assistant Professor of Biology"}
    assert canonical_listing_key(rss) == canonical_listing_key(email)
    assert normalize_source_url(rss["url"]) == "https://jobs.example.edu/FAC-2026-1"
    url_only = {
        "institution": "Synthetic University",
        "title": "Assistant Professor",
        "official_url": "https://jobs.example.edu/FAC-2026-1?utm_medium=email",
    }
    assert listings_match(rss, url_only)


def test_cross_lane_dedup_does_not_bypass_conflicting_strong_evidence() -> None:
    first = {
        "institution": "Synthetic University",
        "official_job_id": "FAC-1",
        "official_url": "https://jobs.example.edu/FAC-1",
        "title": "Assistant Professor",
        "location": "Example City",
        "deadline": "2026-12-01",
    }
    conflicting_id = {**first, "official_job_id": "FAC-2"}
    conflicting_url = {
        key: value for key, value in first.items() if key != "official_job_id"
    }
    conflicting_url["official_url"] = "https://jobs.example.edu/FAC-2"
    assert not listings_match(first, conflicting_id)
    assert not listings_match(
        {key: value for key, value in first.items() if key != "official_job_id"},
        conflicting_url,
    )


def test_official_url_requires_allowlisted_domain() -> None:
    assert is_allowlisted_official_url("https://jobs.example.edu/role/1", ["example.edu"])
    assert not is_allowlisted_official_url("https://aggregator.example/role/1", ["example.edu"])


def test_registry_rejects_unsafe_activation_and_adapter_mismatch() -> None:
    payload = _registry()
    payload["institutions"][0]["enabled"] = True
    issues = registry_issues(payload)
    assert any("offline_only entry cannot be enabled" in item for item in issues)
    assert any("not fully verified" in item for item in issues)

    payload = _registry()
    payload["institutions"][0]["sources"][0]["adapter"] = "rss"
    issues = registry_issues(payload)
    assert any("incompatible" in item for item in issues)


def test_registry_rejects_duplicate_source_ids_and_slow_p1() -> None:
    payload = _registry()
    payload["institutions"][1]["sources"][0]["source_id"] = (
        payload["institutions"][0]["sources"][0]["source_id"]
    )
    payload["institutions"][0]["cadence_hours"] = 48
    issues = registry_issues(payload)
    assert any("duplicate source id" in item for item in issues)
    assert any("priority-1 cadence exceeds 24 hours" in item for item in issues)


def test_registry_rejects_unknown_mode_before_planning() -> None:
    payload = _registry()
    payload["registry_mode"] = "unknown"
    assert any("registry_mode" in item for item in registry_issues(payload))
    with pytest.raises(ValueError, match="registry_mode"):
        plan_source_batches(payload, include_planned=True)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "source_id": "synthetic",
            "last_checked": "2026-10-09T00:00:00Z",
            "source_health": "failed",
            "items_seen": 0,
            "failure_reason": None,
        },
        {
            "source_id": "synthetic",
            "last_checked": "2026-10-09T00:00:00Z",
            "source_health": "healthy",
            "items_seen": None,
            "failure_reason": None,
        },
    ],
)
def test_source_health_schema_rejects_false_coverage(payload: dict[str, object]) -> None:
    with pytest.raises(ContractValidationError):
        validate_schema_payload(payload, "source_health.schema.json")
