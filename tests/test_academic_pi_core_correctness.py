"""Regression tests for authority, state, and academic scoring correctness."""

from __future__ import annotations

from datetime import date

from Career_Job_Agent_Framework.core.identity import merge_job_records
from Career_Job_Agent_Framework.core.models import (
    JobRecord,
    SourceAuthority,
    VerificationResult,
    VerificationStatus,
)
from Career_Job_Agent_Framework.core.sources import (
    apply_verification,
    verification_can_close,
    verification_is_authoritative,
)
from Career_Job_Agent_Framework.core.state import InMemoryStateStore
from Career_Job_Agent_Framework.deployments.academic_pi.scoring import (
    score_academic_fit,
)


def _job(**overrides: object) -> JobRecord:
    values: dict[str, object] = {
        "canonical_id": "job-1",
        "title": "Assistant Professor of Biology",
        "institution": "Synthetic University",
        "organization": "Synthetic University",
        "department": "Biology",
        "location": "Example City",
        "official_job_id": "REQ-1",
        "official_url": "https://jobs.example.edu/REQ-1",
        "deadline": "2026-12-01",
        "deadline_type": "fixed",
        "requirements": {"required_degree": "PhD"},
        "lifecycle_status": "unknown",
        "verification_status": VerificationStatus.VERIFICATION_PENDING,
    }
    values.update(overrides)
    return JobRecord(**values)


def _official_open(job: JobRecord) -> JobRecord:
    return apply_verification(
        job,
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            source_url="https://jobs.example.edu/REQ-1",
            confidence=0.98,
            verified_fields={
                "title": "Official Assistant Professor Title",
                "deadline": "2027-01-15",
                "requirements": {"required_degree": "PhD", "required_documents": ["CV"]},
            },
        ),
    )


def test_definitive_lifecycle_requires_official_or_corroborated_authority() -> None:
    current = _official_open(_job())
    untrusted = VerificationResult(
        status=VerificationStatus.VERIFIED_CLOSED,
        authority=SourceAuthority.TRUSTED_AGGREGATOR,
        confidence=1.0,
        evidence=["aggregator says closed"],
        verified_fields={"title": "Incorrect aggregator title"},
    )

    unchanged = apply_verification(current, untrusted)

    assert not verification_is_authoritative(untrusted)
    assert not verification_can_close(untrusted)
    assert unchanged.lifecycle_status == "open"
    assert unchanged.verification_status == VerificationStatus.VERIFIED_OPEN
    assert unchanged.title == "Official Assistant Professor Title"
    assert unchanged.extra["last_unaccepted_definitive_status"] == "verified_closed"

    corroborated = VerificationResult(
        status=VerificationStatus.VERIFIED_CLOSED,
        authority=SourceAuthority.TRUSTED_AGGREGATOR,
        corroborating_sources=["institution-removal", "department-notice"],
        confidence=0.9,
    )
    assert verification_is_authoritative(corroborated)
    assert verification_can_close(corroborated)
    corroborated_closed = apply_verification(_job(), corroborated)
    assert corroborated_closed.lifecycle_status == "closed"

    single_source = VerificationResult(
        status=VerificationStatus.VERIFIED_CLOSED,
        authority=SourceAuthority.TRUSTED_AGGREGATOR,
        corroborating_sources="one-source",
    )
    assert not verification_is_authoritative(single_source)


def test_lower_authority_cannot_replace_official_title_deadline_or_requirements() -> None:
    official = _official_open(_job())
    lower_authority_refresh = _job(
        title="Aggregator Rewrite",
        deadline="2025-01-01",
        requirements={"required_degree": "None"},
        lifecycle_status="unknown",
        verification_status=VerificationStatus.VERIFICATION_PENDING,
        verification_authority=None,
        field_authority={},
    )

    merged = merge_job_records(official, lower_authority_refresh)

    assert merged.title == "Official Assistant Professor Title"
    assert merged.deadline == "2027-01-15"
    assert merged.requirements == {
        "required_degree": "PhD",
        "required_documents": ["CV"],
    }
    # The current attempt remains visible without erasing durable lifecycle.
    assert merged.verification_status == VerificationStatus.VERIFICATION_PENDING
    assert merged.lifecycle_status == "open"
    assert merged.extra["last_definitive_verification_status"] == "verified_open"

    lower_official = apply_verification(
        official,
        VerificationResult(
            status=VerificationStatus.VERIFIED_CLOSED,
            authority=SourceAuthority.OFFICIAL_DEPARTMENT,
            verified_fields={
                "title": "Lower-authority department title",
                "deadline": "2026-01-01",
                "requirements": {"required_degree": "Unknown"},
            },
        ),
    )
    assert lower_official.lifecycle_status == "open"
    assert lower_official.title == "Official Assistant Professor Title"
    assert lower_official.deadline == "2027-01-15"
    assert lower_official.requirements["required_degree"] == "PhD"
    legacy_official = _job(
        title="Legacy Official Title",
        deadline="2027-04-01",
        requirements={"required_degree": "PhD"},
        lifecycle_status="open",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        verification_authority=SourceAuthority.OFFICIAL_DETAIL,
        field_authority={},
    )
    aggregator = _job(
        title="Aggregator Title",
        deadline="2025-01-01",
        requirements={"required_degree": "None"},
        verification_authority=SourceAuthority.TRUSTED_AGGREGATOR,
        field_authority={},
    )
    legacy_merged = merge_job_records(legacy_official, aggregator)
    assert legacy_merged.title == "Legacy Official Title"
    assert legacy_merged.deadline == "2027-04-01"
    assert legacy_merged.requirements == {"required_degree": "PhD"}

    partially_verified_candidate = apply_verification(
        _job(
            title="Unverified Candidate Title",
            deadline="2025-02-01",
            requirements={"required_degree": "None"},
        ),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            verified_fields={"institution": "Synthetic University"},
        ),
    )
    partially_merged = merge_job_records(official, partially_verified_candidate)
    assert partially_merged.title == "Official Assistant Professor Title"
    assert partially_merged.deadline == "2027-01-15"
    assert partially_merged.requirements["required_degree"] == "PhD"


def test_rediscovery_preserves_original_first_seen_timestamp() -> None:
    original = _job(
        first_seen="2026-09-01T00:00:00Z",
        last_seen="2026-09-01T00:00:00Z",
    )
    rediscovered = _job(
        first_seen="2026-10-04T00:00:00Z",
        last_seen="2026-10-04T00:00:00Z",
    )

    merged = merge_job_records(original, rediscovered)

    assert merged.first_seen == "2026-09-01T00:00:00Z"
    assert merged.last_seen == "2026-10-04T00:00:00Z"


def test_transient_verification_preserves_durable_official_state() -> None:
    official = _official_open(_job())
    prior_verified_at = official.last_verified

    transient = apply_verification(
        official,
        VerificationResult(
            status=VerificationStatus.VERIFICATION_FAILED_TRANSIENT,
            authority=SourceAuthority.DISCOVERY_ONLY,
            error="timeout",
        ),
    )

    assert transient.verification_status == VerificationStatus.VERIFICATION_FAILED_TRANSIENT
    assert transient.lifecycle_status == "open"
    assert transient.last_verified == prior_verified_at
    assert transient.deadline == "2027-01-15"
    assert transient.extra["last_definitive_verification_status"] == "verified_open"


def test_equal_authority_reopen_clears_prior_close_reason() -> None:
    closed = apply_verification(
        _job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_CLOSED,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            verified_fields={"close_reason": "official posting closed"},
        ),
    )
    reopened = apply_verification(
        closed,
        VerificationResult(
            status=VerificationStatus.VERIFIED_REOPENED,
            authority=SourceAuthority.OFFICIAL_DETAIL,
        ),
    )
    state = InMemoryStateStore()
    state.upsert_job(closed)
    state.upsert_job(reopened)

    stored = state.get_job("job-1")
    assert stored is not None
    assert stored.lifecycle_status == "reopened"
    assert stored.close_reason is None


def test_restore_can_clear_rejected_and_consumes_command_marker() -> None:
    state = InMemoryStateStore()
    state.upsert_job(_job(rejected=True, manual_review_state="not_interested"))
    restored = state.get_job("job-1")
    assert restored is not None
    restored.rejected = False
    restored.manual_review_state = "reviewed"
    restored.extra["clear_manual_override"] = True

    state.upsert_job(restored)
    stored = state.get_job("job-1")

    assert stored is not None
    assert stored.rejected is False
    assert stored.manual_review_state == "reviewed"
    assert "clear_manual_override" not in stored.extra


def test_reevaluation_replaces_derived_lists_and_preserves_versioned_history() -> None:
    state = InMemoryStateStore()
    original = _job(
        fit_score=40.0,
        tier="BLOCKED",
        strongest_matches=["old match"],
        meaningful_gaps=["old gap"],
        hard_blockers=["old blocker"],
        evaluation={
            "fit_score": 40.0,
            "tier": "BLOCKED",
            "strongest_matches": ["old match"],
            "meaningful_gaps": ["old gap"],
            "hard_blockers": ["old blocker"],
        },
    )
    state.upsert_job(original)
    current = state.get_job("job-1")
    assert current is not None
    assert current.evaluation_version == 1

    current.fit_score = 82.0
    current.tier = "Tier 1"
    current.strongest_matches = ["new match"]
    current.meaningful_gaps = []
    current.hard_blockers = []
    current.evaluation = {
        "fit_score": 82.0,
        "tier": "Tier 1",
        "strongest_matches": ["new match"],
        "meaningful_gaps": [],
        "hard_blockers": [],
    }
    state.upsert_job(current)
    rescored = state.get_job("job-1")

    assert rescored is not None
    assert rescored.strongest_matches == ["new match"]
    assert rescored.meaningful_gaps == []
    assert rescored.hard_blockers == []
    assert rescored.evaluation_version == 2
    assert len(rescored.evaluation_history) == 1
    assert rescored.evaluation_history[0]["hard_blockers"] == ["old blocker"]
    evaluation_changes = [
        change
        for change in state.list_changes(job_id="job-1")
        if change.change_type == "evaluation_change"
    ]
    assert {change.field for change in evaluation_changes} >= {
        "fit_score",
        "tier",
        "strongest_matches",
        "meaningful_gaps",
        "hard_blockers",
    }

    category_only = state.get_job("job-1")
    assert category_only is not None
    category_only.evaluation["category_scores"] = {"scientific_program_fit": 90.0}
    state.upsert_job(category_only)
    category_refreshed = state.get_job("job-1")
    assert category_refreshed is not None
    assert category_refreshed.evaluation_version == 3
    assert len(category_refreshed.evaluation_history) == 2
    assert any(
        change.change_type == "evaluation_change" and change.field == "evaluation"
        for change in state.list_changes(job_id="job-1")
    )

    timestamp_only = state.get_job("job-1")
    assert timestamp_only is not None
    timestamp_only.evaluation["evaluated_at"] = "2026-10-04T12:00:00Z"
    state.upsert_job(timestamp_only)
    timestamp_refreshed = state.get_job("job-1")
    assert timestamp_refreshed is not None
    assert timestamp_refreshed.evaluation_version == 3
    assert len(timestamp_refreshed.evaluation_history) == 2


def test_rescoring_recomputes_instead_of_reusing_stale_derived_blockers() -> None:
    stale = _job(
        title="Assistant Professor of Virology",
        description="Independent virology research program.",
        deadline="2027-12-01",
        lifecycle_status="open",
        verification_status=VerificationStatus.VERIFIED_OPEN,
        verification_confidence=0.95,
        hard_blockers=["fixed application deadline has passed"],
        evaluation={"hard_blockers": ["fixed application deadline has passed"]},
    )
    profile = {
        "scientific_identity": {"primary_fields": ["virology"]},
        "departments": {"strong_fit": ["Biology"]},
        "career_stage": {"target_independence": ["tenure_track_faculty"]},
    }

    evaluation = score_academic_fit(stale, profile, today=date(2026, 10, 4))

    assert "fixed application deadline has passed" not in evaluation.hard_blockers


def test_broad_search_is_neutral_without_fabricating_positive_evidence() -> None:
    broad_job = {
        "raw_title": "Open Rank Faculty",
        "department": "Biology",
        "description": "Applications are invited from all areas of biology.",
        "search_scope": {"broad_search": True, "department_scope": ["Biology"]},
        "independence": {"class": "independent"},
        "status": {
            "verification_status": "verified_open",
            "verification_confidence": 0.95,
        },
    }
    empty_profile_result = score_academic_fit(broad_job, {})

    assert empty_profile_result.tier not in {"Tier 1", "Tier 2"}
    assert empty_profile_result.category_scores["scientific_program_fit"] == 0.0
    assert empty_profile_result.category_scores["department_search_fit"] == 0.0
    assert empty_profile_result.category_scores["independence_and_career_stage_fit"] == 0.0
    assert empty_profile_result.category_scores["method_or_model_system_relevance"] == 0.0
    assert empty_profile_result.category_scores["strategic_research_environment_fit"] == 0.0
    assert empty_profile_result.category_scores["evidence_of_candidate_distinctiveness"] == 0.0
    assert empty_profile_result.category_scores["translational_or_collaborative_fit"] == 0.0
    assert empty_profile_result.strongest_matches == ()
    assert "insufficient candidate-fit evidence for Tier 1 or Tier 2" in (
        empty_profile_result.meaningful_gaps
    )

    profile = {
        "scientific_identity": {"primary_fields": ["virology"]},
        "departments": {"strong_fit": ["Biology"]},
        "career_stage": {"target_independence": ["tenure_track_faculty"]},
    }
    broad_result = score_academic_fit(broad_job, profile)
    narrow_result = score_academic_fit(
        {**broad_job, "search_scope": {"broad_search": False}},
        profile,
    )

    assert broad_result.fit_score > narrow_result.fit_score
    assert not any(
        "no direct primary-field" in gap for gap in broad_result.meaningful_gaps
    )
    assert not any("broad search" in match for match in broad_result.strongest_matches)

    evidence_paths_only = {
        **profile,
        "evidence": {
            "cv_path": "PRIVATE_CV_REFERENCE",
            "publication_sources": ["PRIVATE_PUBLICATION_LEDGER"],
        },
    }
    direct_job = {
        **broad_job,
        "description": "Independent virology research program.",
        "search_scope": {"broad_search": False},
    }
    direct_result = score_academic_fit(direct_job, evidence_paths_only)
    assert any("direct profile match: virology" == match for match in direct_result.strongest_matches)
    assert direct_result.category_scores["evidence_of_candidate_distinctiveness"] == 0.0
