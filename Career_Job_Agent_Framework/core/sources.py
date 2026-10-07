"""Discovery-source authority and official-verification behavior."""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any, Mapping

from .identity import coerce_job
from .models import (
    JobRecord,
    SourceAuthority,
    SourceRecord,
    VerificationResult,
    VerificationStatus,
)
from .urls import normalize_url


OFFICIAL_AUTHORITY_MINIMUM = int(SourceAuthority.OFFICIAL_DEPARTMENT)
_NON_VERIFIABLE_INTERNAL_FIELDS = {
    "canonical_id",
    "verification_status",
    "verification_authority",
    "field_authority",
    "lifecycle_status",
    "last_verified",
    "verification_confidence",
    "evaluation",
    "evaluation_version",
    "evaluation_history",
    "application",
    "fit_score",
    "tier",
    "strongest_matches",
    "meaningful_gaps",
    "hard_blockers",
    "manual_review_state",
    "rejected",
}
_AUTHORITY_PROTECTED_FIELDS = {
    "title",
    "normalized_title",
    "institution",
    "organization",
    "department",
    "location",
    "country",
    "official_job_id",
    "official_url",
    "posted_date",
    "deadline",
    "deadline_type",
    "expected_start_date",
    "description",
    "search_scope",
    "requirements",
    "position",
    "lifecycle_status",
    "verification_status",
    "last_verified",
    "verification_confidence",
    "close_reason",
}


def _coerce_verification(
    result: VerificationResult | Mapping[str, Any],
) -> VerificationResult:
    return (
        result
        if isinstance(result, VerificationResult)
        else VerificationResult.from_dict(result)
    )


def verification_is_authoritative(
    result: VerificationResult | Mapping[str, Any],
) -> bool:
    """Return whether a result can establish durable official facts.

    Official department, ATS, and detail sources qualify directly.  A lower
    authority source qualifies only when the verification adapter explicitly
    marks the result corroborated, or supplies at least two distinct
    corroborating source identifiers.  Free-form evidence text and confidence
    alone are never treated as authority.
    """

    verification = _coerce_verification(result)
    return (
        int(verification.authority) >= OFFICIAL_AUTHORITY_MINIMUM
        or _is_corroborated(verification)
    )


def _is_corroborated(verification: VerificationResult) -> bool:
    corroborating_sources = {
        source.casefold()
        for source in verification.corroborating_sources
        if source.strip()
    }
    return verification.corroborated or len(corroborating_sources) >= 2


def _effective_lifecycle_authority(verification: VerificationResult) -> int:
    """Return authority for a definitive lifecycle transition.

    Corroboration can make a lower-authority result sufficient to establish
    open/closed state.  It does not promote the authority of posting fields;
    those retain the source's actual authority and must be explicitly listed
    in ``verified_fields``.
    """

    authority = int(verification.authority)
    if verification_is_authoritative(verification):
        return max(authority, OFFICIAL_AUTHORITY_MINIMUM)
    return authority


def _coerce_authority_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return int(SourceAuthority[value.strip().upper()])
        except KeyError:
            pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _legacy_record_authority(job: JobRecord) -> int:
    """Support old definitive records without laundering partial authority."""

    if job.field_authority or not job.verification_status.is_definitive:
        return -1
    authority = _coerce_authority_value(job.verification_authority)
    return authority if authority is not None else -1


def _established_field_authority(job: JobRecord, field_name: str) -> int:
    if field_name in job.field_authority:
        return int(job.field_authority[field_name])
    if field_name in _AUTHORITY_PROTECTED_FIELDS:
        return _legacy_record_authority(job)
    return -1


def _field_can_replace(job: JobRecord, field_name: str, authority: int) -> bool:
    return authority >= _established_field_authority(job, field_name)


def _record_ignored_fields(job: JobRecord, fields: Iterable[str]) -> None:
    ignored = list(dict.fromkeys(str(field) for field in fields))
    if ignored:
        job.extra["last_ignored_lower_authority_fields"] = ignored


def source_authority(source: SourceRecord | Mapping[str, Any]) -> int:
    record = source if isinstance(source, SourceRecord) else SourceRecord.from_dict(source)
    return int(record.authority)


def choose_authoritative_source(
    sources: Iterable[SourceRecord | Mapping[str, Any]],
) -> SourceRecord | None:
    candidates = [
        item if isinstance(item, SourceRecord) else SourceRecord.from_dict(item)
        for item in sources
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (int(item.authority), item.priority))


def apply_verification(
    value: JobRecord | Mapping[str, Any],
    result: VerificationResult | Mapping[str, Any],
) -> JobRecord:
    """Apply one verification result without converting retrieval failure to closure."""

    job = copy.deepcopy(coerce_job(value))
    verification = _coerce_verification(result)
    prior_status = job.verification_status
    job.extra.pop("last_ignored_lower_authority_fields", None)
    job.extra["last_verification_attempt"] = verification.checked_at
    job.extra["last_verification_attempt_status"] = verification.status.value
    job.extra["last_verification_attempt_authority"] = int(verification.authority)
    job.extra["last_verification_attempt_corroborated"] = _is_corroborated(
        verification
    )
    job.extra["last_verification_transition_accepted"] = False
    if verification.error:
        job.extra["last_verification_error"] = verification.error
    else:
        job.extra.pop("last_verification_error", None)

    if verification.status.is_transient or verification.status in {
        VerificationStatus.VERIFICATION_FAILED_PERSISTENT,
        VerificationStatus.OFFICIAL_SOURCE_NOT_FOUND,
        VerificationStatus.MANUAL_REVIEW_REQUIRED,
        VerificationStatus.UNKNOWN,
    }:
        job.verification_status = verification.status
        if prior_status.is_definitive:
            job.extra["last_definitive_verification_status"] = prior_status.value
        # Critically, retain durable fields and lifecycle state.
        return job

    if not verification_is_authoritative(verification):
        job.extra["last_unaccepted_definitive_status"] = verification.status.value
        job.extra["last_verification_authority_error"] = (
            "Definitive verification requires an official source or explicit corroboration"
        )
        if prior_status.is_definitive:
            job.extra["last_definitive_verification_status"] = prior_status.value
        return job

    field_authority_value = int(verification.authority)
    lifecycle_authority_value = _effective_lifecycle_authority(verification)
    job.extra.pop("last_verification_authority_error", None)
    job.extra.pop("last_unaccepted_definitive_status", None)
    field_authority = dict(job.field_authority)
    ignored_fields: list[str] = []
    for field_name, field_value in verification.verified_fields.items():
        if field_value in (None, "", [], {}):
            continue
        if field_name in _NON_VERIFIABLE_INTERNAL_FIELDS:
            ignored_fields.append(field_name)
            continue
        if not _field_can_replace(job, field_name, field_authority_value):
            ignored_fields.append(field_name)
            continue
        if hasattr(job, field_name):
            setattr(job, field_name, copy.deepcopy(field_value))
        else:
            job.extra[field_name] = copy.deepcopy(field_value)
        field_authority[field_name] = field_authority_value
    if verification.source_url:
        canonical = normalize_url(verification.source_url)
        if (
            canonical
            and field_authority_value >= OFFICIAL_AUTHORITY_MINIMUM
            and _field_can_replace(job, "official_url", field_authority_value)
        ):
            job.official_url = canonical
            field_authority["official_url"] = field_authority_value
        elif canonical and field_authority_value >= OFFICIAL_AUTHORITY_MINIMUM:
            ignored_fields.append("official_url")
        if verification.source_url not in job.discovery_urls:
            job.discovery_urls.append(verification.source_url)

    lifecycle_fields = (
        "lifecycle_status",
        "verification_status",
        "last_verified",
        "verification_confidence",
    )
    lifecycle_authority = max(
        (_established_field_authority(job, field) for field in lifecycle_fields),
        default=-1,
    )
    if lifecycle_authority_value < lifecycle_authority:
        ignored_fields.extend(lifecycle_fields)
    else:
        job.verification_status = verification.status
        job.verification_authority = lifecycle_authority_value
        job.last_verified = verification.checked_at
        job.verification_confidence = verification.confidence
        job.extra["last_verification_transition_accepted"] = True
        job.extra["last_accepted_verification_attempt"] = verification.checked_at
        job.extra["last_definitive_verification_status"] = verification.status.value
        job.extra["last_definitive_verification_authority"] = lifecycle_authority_value
        if verification.status == VerificationStatus.VERIFIED_OPEN:
            job.lifecycle_status = "open"
        elif verification.status == VerificationStatus.VERIFIED_REOPENED:
            job.lifecycle_status = "reopened"
        elif verification.status == VerificationStatus.VERIFIED_CLOSED:
            job.lifecycle_status = "closed"
        elif verification.status == VerificationStatus.VERIFIED_EXPIRED:
            job.lifecycle_status = "expired"
        for field_name in lifecycle_fields:
            field_authority[field_name] = lifecycle_authority_value
        if verification.status in {
            VerificationStatus.VERIFIED_OPEN,
            VerificationStatus.VERIFIED_REOPENED,
        } and _field_can_replace(
            job, "close_reason", lifecycle_authority_value
        ):
            job.close_reason = None
            field_authority["close_reason"] = lifecycle_authority_value

    job.field_authority = field_authority
    _record_ignored_fields(job, ignored_fields)
    return job


def verification_can_close(result: VerificationResult | Mapping[str, Any]) -> bool:
    verification = _coerce_verification(result)
    return verification_is_authoritative(verification) and verification.status in {
        VerificationStatus.VERIFIED_CLOSED,
        VerificationStatus.VERIFIED_EXPIRED,
    }
