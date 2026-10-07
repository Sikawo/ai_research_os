"""Focused regressions for canonical-state and authority hardening."""

from __future__ import annotations

from Career_Job_Agent_Framework.core.identity import (
    are_duplicate_jobs,
    merge_job_records,
)
from Career_Job_Agent_Framework.core.models import (
    JobRecord,
    SourceAuthority,
    VerificationResult,
    VerificationStatus,
)
from Career_Job_Agent_Framework.core.sources import apply_verification
from Career_Job_Agent_Framework.core.state import InMemoryStateStore


def _job(**overrides: object) -> JobRecord:
    values: dict[str, object] = {
        "canonical_id": "job-1",
        "title": "Assistant Professor of Biology",
        "institution": "Synthetic University",
        "department": "Biology",
        "location": "Example City",
        "description": "Official posting text",
        "deadline": "2027-01-15",
        "requirements": {"required_degree": "PhD"},
        "discovery_urls": ["https://board.example/jobs/req-1?utm_source=mail"],
        "verification_status": VerificationStatus.VERIFICATION_PENDING,
    }
    values.update(overrides)
    return JobRecord(**values)


def test_partial_verification_does_not_launder_unverified_posting_fields() -> None:
    established = apply_verification(
        _job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            verified_fields={
                "title": "Official Assistant Professor",
                "department": "Official Biology Department",
                "location": "Official City",
                "description": "Official detail-page description",
                "requirements": {"required_degree": "PhD", "required_documents": ["CV"]},
            },
        ),
    )
    partially_verified = apply_verification(
        _job(
            title="Untrusted title",
            department="Untrusted department",
            location="Untrusted location",
            description="Untrusted description",
            requirements={"required_degree": "None"},
        ),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            verified_fields={"institution": "Synthetic University"},
        ),
    )

    assert "institution" in partially_verified.field_authority
    assert "title" not in partially_verified.field_authority
    assert "department" not in partially_verified.field_authority
    assert "description" not in partially_verified.field_authority

    merged = merge_job_records(established, partially_verified)
    assert merged.title == "Official Assistant Professor"
    assert merged.department == "Official Biology Department"
    assert merged.location == "Official City"
    assert merged.description == "Official detail-page description"
    assert merged.requirements == {
        "required_degree": "PhD",
        "required_documents": ["CV"],
    }


def test_corroboration_promotes_lifecycle_but_not_posting_field_authority() -> None:
    verified = apply_verification(
        _job(official_url=None),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            checked_at="2026-10-04T12:00:00Z",
            source_url="https://aggregator.example/jobs/req-1",
            authority=SourceAuthority.TRUSTED_AGGREGATOR,
            corroborating_sources=["department-index", "institution-search"],
            verified_fields={"title": "Corroborated aggregator title"},
        ),
    )

    assert verified.lifecycle_status == "open"
    assert int(verified.verification_authority or 0) == int(
        SourceAuthority.OFFICIAL_DEPARTMENT
    )
    assert verified.field_authority["title"] == int(
        SourceAuthority.TRUSTED_AGGREGATOR
    )
    assert verified.official_url is None
    assert "https://aggregator.example/jobs/req-1" in verified.discovery_urls
    assert verified.extra["last_verification_transition_accepted"] is True


def test_rejected_lower_authority_transition_sets_and_persists_false_marker() -> None:
    closed = apply_verification(
        _job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_CLOSED,
            checked_at="2026-10-03T12:00:00Z",
            authority=SourceAuthority.OFFICIAL_DETAIL,
        ),
    )
    rejected_reopen = apply_verification(
        closed,
        VerificationResult(
            status=VerificationStatus.VERIFIED_REOPENED,
            checked_at="2026-10-04T12:00:00Z",
            authority=SourceAuthority.OFFICIAL_DEPARTMENT,
        ),
    )

    assert rejected_reopen.lifecycle_status == "closed"
    assert rejected_reopen.verification_status == VerificationStatus.VERIFIED_CLOSED
    assert rejected_reopen.extra["last_verification_transition_accepted"] is False

    state = InMemoryStateStore()
    state.upsert_job(closed)
    state.upsert_job(rejected_reopen)
    stored = state.get_job("job-1")
    assert stored is not None
    assert stored.extra["last_verification_transition_accepted"] is False


def test_same_normalized_discovery_url_is_duplicate_when_deadline_changes() -> None:
    original = _job(deadline="2027-01-15")
    changed = _job(
        canonical_id=None,
        deadline="2027-02-01",
        discovery_urls=["https://board.example/jobs/req-1#details"],
    )

    assert are_duplicate_jobs(original, changed)
    state = InMemoryStateStore()
    state.upsert_job(original)
    result = state.upsert_job(changed)
    assert result.action == "updated"
    assert len(state.list_jobs()) == 1


def test_shared_discovery_landing_page_does_not_merge_different_departments() -> None:
    biology = _job(
        canonical_id=None,
        official_job_id=None,
        official_url=None,
        department="Biology",
        discovery_urls=["https://synthetic.example.edu/faculty-opportunities"],
    )
    chemistry = _job(
        canonical_id=None,
        official_job_id=None,
        official_url=None,
        department="Chemistry",
        discovery_urls=["https://synthetic.example.edu/faculty-opportunities"],
    )

    assert not are_duplicate_jobs(biology, chemistry)
    state = InMemoryStateStore()
    state.upsert_job(biology)
    state.upsert_job(chemistry)
    assert {job.department for job in state.list_jobs()} == {"Biology", "Chemistry"}


def test_lower_authority_transition_cannot_survive_authoritative_merge() -> None:
    authoritative_open = apply_verification(
        _job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            checked_at="2026-10-04T10:00:00Z",
        ),
    )
    lower_closed = apply_verification(
        _job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_CLOSED,
            authority=SourceAuthority.OFFICIAL_DEPARTMENT,
            checked_at="2026-10-04T11:00:00Z",
        ),
    )

    merged = merge_job_records(authoritative_open, lower_closed)
    assert merged.verification_status == VerificationStatus.VERIFIED_OPEN
    assert merged.lifecycle_status == "open"
    assert merged.extra["last_verification_transition_accepted"] is False
    assert merged.extra.get("verified_open_in_run") is not True


def test_unverified_identity_fields_cannot_replace_official_identity() -> None:
    official = apply_verification(
        _job(institution="Discovery University", organization="Discovery University"),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            verified_fields={
                "institution": "Official University",
                "organization": "Official University",
            },
        ),
    )
    rediscovered = _job(
        institution="Spoof University",
        organization="Spoof University",
    )

    merged = merge_job_records(official, rediscovered)
    assert merged.institution == "Official University"
    assert merged.organization == "Official University"


def test_unknown_verification_is_nondefinitive_even_at_official_authority() -> None:
    established = apply_verification(
        _job(),
        VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            checked_at="2026-10-04T10:00:00Z",
        ),
    )
    unknown = apply_verification(
        established,
        VerificationResult(
            status=VerificationStatus.UNKNOWN,
            authority=SourceAuthority.OFFICIAL_DETAIL,
            checked_at="2026-10-04T11:00:00Z",
        ),
    )

    assert unknown.lifecycle_status == "open"
    assert unknown.verification_status == VerificationStatus.UNKNOWN
    assert unknown.extra["last_verification_transition_accepted"] is False
    assert unknown.field_authority == established.field_authority


def test_state_accepts_canonical_nested_academic_job_payload() -> None:
    nested = {
        "schema_version": 1,
        "identity": {
            "canonical_job_id": "nested-job-1",
            "institution": "Nested University",
            "department": "Cell Biology",
            "raw_title": "Assistant Professor",
            "normalized_role_class": "tenure_track_faculty",
            "job_id_or_requisition": "NEST-1",
            "country": "US",
            "region": "Northeast",
            "city": "Example City",
        },
        "urls": {
            "discovery_urls": ["https://board.example/jobs/nest-1"],
            "official_url": "https://jobs.example.edu/NEST-1",
            "application_url": "https://apply.example.edu/NEST-1",
        },
        "source": {
            "first_discovered_by": "board",
            "all_discovery_sources": ["board", "institution_direct"],
            "source_message_ids": ["message-1"],
        },
        "dates": {
            "first_seen": "2026-10-01T00:00:00Z",
            "last_seen": "2026-10-04T00:00:00Z",
            "posted_date": "2026-09-15",
            "deadline": "2027-01-15",
            "deadline_type": "fixed",
            "expected_start_date": "2027-08-15",
        },
        "status": {
            "lifecycle_status": "open",
            "verification_status": "verified_open",
            "last_verified": "2026-10-04T00:00:00Z",
            "verification_confidence": 0.99,
            "close_reason": None,
        },
        "independence": {
            "class": "independent",
            "confidence": 0.95,
            "evidence": ["PI appointment"],
        },
        "search_scope": {
            "declared_fields": ["cell biology"],
            "broad_search": False,
            "department_scope": ["biology"],
            "rank_scope": ["assistant professor"],
        },
        "requirements": {
            "required_degree": "PhD",
            "required_documents": ["CV", "research statement"],
        },
        "position": {"tenure_status": "tenure-track"},
        "evaluation": {
            "fit_score": 91,
            "tier": "Tier 1",
            "strongest_matches": ["cell biology"],
            "meaningful_gaps": [],
            "hard_blockers": [],
        },
        "application": {"status": "not_started"},
        "extra": {"parser_version": "academic-v1"},
    }

    direct = JobRecord.from_dict(nested)
    state = InMemoryStateStore({"tables": {"Jobs": [nested]}})
    stored = state.get_job("nested-job-1")

    assert direct.title == "Assistant Professor"
    assert stored is not None
    assert stored.official_job_id == "NEST-1"
    assert stored.location == "Example City"
    assert stored.first_seen == "2026-10-01T00:00:00Z"
    assert stored.deadline == "2027-01-15"
    assert stored.search_scope["department_scope"] == ["biology"]
    assert stored.requirements["required_degree"] == "PhD"
    assert stored.position["tenure_status"] == "tenure-track"
    assert stored.fit_score == 91
    assert stored.tier == "Tier 1"
    assert stored.application["status"] == "not_started"
    assert stored.source_message_ids == ["message-1"]
    assert {item["source_id"] for item in stored.source_provenance} == {
        "board",
        "institution_direct",
    }
