"""Conservative canonical identity and deduplication utilities."""

from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping

from .models import JobRecord, SourceAuthority, VerificationStatus
from .urls import normalize_url


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _slug(value: Any) -> str:
    return normalize_text(value).replace(" ", "-")


def _digest(parts: Iterable[str]) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def coerce_job(value: JobRecord | Mapping[str, Any]) -> JobRecord:
    if isinstance(value, JobRecord):
        return value
    if isinstance(value, Mapping):
        return JobRecord.from_dict(value)
    raise TypeError("Expected JobRecord or mapping")


def job_identity_keys(value: JobRecord | Mapping[str, Any]) -> tuple[str, ...]:
    """Return strongest-to-weakest exact identity keys for a job.

    A title-only key is deliberately never generated.  Department is included
    whenever known so parallel faculty searches are not collapsed.
    """

    job = coerce_job(value)
    organization = normalize_text(job.organization_name)
    official_id = normalize_text(job.official_job_id)
    title = normalize_text(job.normalized_title or job.title)
    department = normalize_text(job.department)
    location = normalize_text(job.location)
    deadline = normalize_text(job.deadline)
    keys: list[str] = []

    if organization and official_id:
        keys.append(f"requisition:{_slug(organization)}:{_slug(official_id)}")
    official_url = normalize_url(job.official_url)
    if official_url:
        keys.append(f"url:{_digest([official_url])}")
    for discovery_url in job.discovery_urls:
        canonical_discovery_url = normalize_url(discovery_url)
        # Discovery/listing pages are often shared by several searches.  They
        # are useful only with posting context and must never become a global
        # exact key on their own.
        if canonical_discovery_url and organization and title:
            keys.append(
                "discovery_context:"
                + _digest(
                    [
                        canonical_discovery_url,
                        organization,
                        title,
                        department,
                        location,
                    ]
                )
            )
    if organization and title:
        if department:
            if location or deadline:
                keys.append(
                    "search:"
                    + _digest([organization, title, department, location, deadline])
                )
        elif location:
            # Backward-compatible industry fallback: company + title + location.
            keys.append("legacy:" + _digest([organization, title, location]))
    return tuple(dict.fromkeys(keys))


def canonical_job_identity(
    value: JobRecord | Mapping[str, Any], *, preserve_existing: bool = True
) -> str:
    job = coerce_job(value)
    if preserve_existing and job.canonical_id:
        return str(job.canonical_id)
    keys = job_identity_keys(job)
    if keys:
        return keys[0]
    organization = normalize_text(job.organization_name)
    title = normalize_text(job.title)
    if not organization or not title:
        raise ValueError(
            "A canonical job identity requires an organization and title, or a stronger identifier"
        )
    disambiguators = [
        normalize_text(job.department),
        normalize_text(job.location),
        normalize_text(job.deadline),
        normalize_text(job.description),
        *(normalize_text(item) for item in job.discovery_urls),
        *(normalize_text(item) for item in job.source_message_ids),
    ]
    if not any(disambiguators):
        raise ValueError(
            "A title plus organization is not sufficient for canonical identity; "
            "retain the candidate for manual review until a disambiguator is available"
        )
    return "provisional:" + _digest([organization, title, *disambiguators])


def _has_conflicting_strong_identity(first: JobRecord, second: JobRecord) -> bool:
    if (
        first.official_job_id
        and second.official_job_id
        and normalize_text(first.official_job_id) != normalize_text(second.official_job_id)
    ):
        return True
    if (
        first.department
        and second.department
        and normalize_text(first.department) != normalize_text(second.department)
    ):
        return True
    if (
        first.location
        and second.location
        and normalize_text(first.location) != normalize_text(second.location)
    ):
        return True
    return False


def are_duplicate_jobs(
    first: JobRecord | Mapping[str, Any],
    second: JobRecord | Mapping[str, Any],
    *,
    semantic_threshold: float = 0.94,
) -> bool:
    left = coerce_job(first)
    right = coerce_job(second)
    if (
        left.official_job_id
        and right.official_job_id
        and normalize_text(left.official_job_id) != normalize_text(right.official_job_id)
    ):
        return False
    if _has_conflicting_strong_identity(left, right):
        return False
    if set(job_identity_keys(left)).intersection(job_identity_keys(right)):
        return True
    if normalize_text(left.organization_name) != normalize_text(right.organization_name):
        return False
    if not left.organization_name or not right.organization_name:
        return False
    has_context_match = False
    if left.department and right.department:
        has_context_match = normalize_text(left.department) == normalize_text(right.department)
    if left.location and right.location:
        if normalize_text(left.location) != normalize_text(right.location):
            return False
        has_context_match = True
    if left.deadline and right.deadline:
        if normalize_text(left.deadline) != normalize_text(right.deadline):
            return False
    title_score = SequenceMatcher(
        None,
        normalize_text(left.normalized_title or left.title),
        normalize_text(right.normalized_title or right.title),
    ).ratio()
    if title_score < semantic_threshold:
        return False
    if left.description and right.description:
        description_score = SequenceMatcher(
            None, normalize_text(left.description), normalize_text(right.description)
        ).ratio()
        return description_score >= semantic_threshold
    # Without descriptions, require matching location or department context.
    return has_context_match and normalize_text(
        left.normalized_title or left.title
    ) == normalize_text(right.normalized_title or right.title)


def _unique_values(*collections: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for collection in collections:
        for item in collection:
            marker = repr(item)
            if marker not in seen:
                seen.add(marker)
                result.append(copy.deepcopy(item))
    return result


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
_AUTHORITY_REQUIRED_REPLACEMENT_FIELDS = {
    "title",
    "normalized_title",
    "institution",
    "organization",
    "deadline",
    "deadline_type",
    "requirements",
}


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
    """Return a compatibility authority for pre-field-authority records only.

    Modern verification records carry authority per explicitly verified field.
    Inferring authority from provenance or from a partially verified record's
    lifecycle authority would let unrelated discovery values masquerade as
    official facts.  The fallback is therefore limited to old definitive
    records which have no field-level metadata at all.
    """

    if job.field_authority or not job.verification_status.is_definitive:
        return -1
    authority = _coerce_authority_value(job.verification_authority)
    return authority if authority is not None else -1


def _effective_field_authorities(
    job: JobRecord, *, include_legacy_fallback: bool = False
) -> dict[str, int]:
    authorities = dict(job.field_authority)
    record_authority = (
        _legacy_record_authority(job) if include_legacy_fallback else -1
    )
    if record_authority >= 0:
        for field_name in _AUTHORITY_PROTECTED_FIELDS:
            authorities.setdefault(field_name, record_authority)
    return authorities


def merge_job_records(
    existing: JobRecord | Mapping[str, Any],
    incoming: JobRecord | Mapping[str, Any],
) -> JobRecord:
    """Merge a duplicate while preserving manual and previously verified state."""

    old = coerce_job(existing)
    new = coerce_job(incoming)
    merged = old.to_dict()
    incoming_data = new.to_dict()
    # Only the stored side receives the narrow compatibility fallback for
    # legacy definitive records.  Incoming records must carry explicit
    # per-field authority, otherwise a high lifecycle authority could launder
    # arbitrary discovery payload fields during merge.
    old_field_authority = _effective_field_authorities(
        old, include_legacy_fallback=True
    )
    new_field_authority = _effective_field_authorities(new)
    incoming_evaluation = bool(new.evaluation)
    evaluation_snapshot_fields = {
        "evaluation",
        "fit_score",
        "tier",
        "strongest_matches",
        "meaningful_gaps",
        "hard_blockers",
    }
    protected_when_empty = {
        "application",
        "evaluation",
        "manual_review_state",
        "rejected",
        "close_reason",
    }
    nondefinitive = new.verification_status in {
        VerificationStatus.VERIFICATION_PENDING,
        VerificationStatus.VERIFICATION_FAILED_TRANSIENT,
        VerificationStatus.VERIFICATION_FAILED_PERSISTENT,
        VerificationStatus.OFFICIAL_SOURCE_NOT_FOUND,
        VerificationStatus.MANUAL_REVIEW_REQUIRED,
        VerificationStatus.UNKNOWN,
    }
    lifecycle_fields = (
        "lifecycle_status",
        "verification_status",
        "last_verified",
        "verification_confidence",
    )
    old_lifecycle_authority = max(
        (int(old_field_authority.get(field_name, -1)) for field_name in lifecycle_fields),
        default=-1,
    )
    new_lifecycle_authority = max(
        (int(new_field_authority.get(field_name, -1)) for field_name in lifecycle_fields),
        default=-1,
    )
    incoming_transition_accepted = bool(
        new.extra.get("last_verification_transition_accepted") is True
        and new.verification_status.is_definitive
        and new_lifecycle_authority >= 0
        and new_lifecycle_authority >= old_lifecycle_authority
    )
    for key, value in incoming_data.items():
        if key == "field_authority":
            continue
        if key == "verification_authority":
            old_authority = int(old.verification_authority or -1)
            new_authority = int(new.verification_authority or -1)
            if new_authority >= old_authority and new.verification_authority is not None:
                merged[key] = new_authority
            continue
        if key == "last_verification_transition_accepted":
            # Acceptance describes the authoritative merged transition, not
            # merely the isolated incoming verification attempt.
            merged[key] = incoming_transition_accepted
            continue
        if key == "evaluation_history":
            merged[key] = _unique_values(merged.get(key, []), value or [])
            continue
        if key == "extra":
            old_extra = dict(merged.get(key, {}) or {})
            new_extra = dict(value or {})
            listing_ids = _unique_values(
                old_extra.get("source_listing_ids", []),
                new_extra.get("source_listing_ids", []),
            )
            old_extra.update(copy.deepcopy(new_extra))
            if listing_ids:
                old_extra["source_listing_ids"] = listing_ids
            merged[key] = old_extra
            continue
        if incoming_evaluation and key in evaluation_snapshot_fields:
            merged[key] = copy.deepcopy(value)
            continue
        if key in {
            "discovery_urls",
            "source_provenance",
            "source_message_ids",
            "independence_evidence",
            "strongest_matches",
            "meaningful_gaps",
            "hard_blockers",
        }:
            merged[key] = _unique_values(merged.get(key, []), value or [])
            continue
        if key == "canonical_id" and merged.get(key):
            continue
        if key == "first_seen" and merged.get(key):
            # Discovery history is immutable: a later sighting may refresh
            # ``last_seen`` but must never make an old role look newly found.
            continue
        if key in new.field_authority:
            if int(new_field_authority[key]) >= int(old_field_authority.get(key, -1)):
                # Presence in field_authority means the value was explicitly
                # established by verification.  Preserve explicit clears too.
                merged[key] = copy.deepcopy(value)
            continue
        if (
            key in _AUTHORITY_REQUIRED_REPLACEMENT_FIELDS
            and merged.get(key) not in (None, "", [], {})
        ):
            # Once present, these authoritative posting facts may be replaced
            # only by a verification result that assigned field-level authority.
            continue
        if (
            key in old_field_authority
            and int(old_field_authority[key]) > int(new_field_authority.get(key, -1))
        ):
            # A discovery-only or lower-authority refresh may add provenance,
            # but it cannot replace a fact established by a stronger source.
            continue
        if (
            key in {"lifecycle_status", "verification_status", "deadline_type"}
            and str(value).casefold() == "unknown"
            and str(merged.get(key) or "").casefold() not in {"", "unknown"}
        ):
            continue
        if key in protected_when_empty and value in (None, "", [], {}, False):
            continue
        if nondefinitive and key in {
            "lifecycle_status",
            "close_reason",
            "last_verified",
        }:
            continue
        if value not in (None, "", [], {}):
            merged[key] = copy.deepcopy(value)
    merged["field_authority"] = {
        field_name: max(
            int(old.field_authority.get(field_name, -1)),
            int(new.field_authority.get(field_name, -1)),
        )
        for field_name in set(old.field_authority).union(new.field_authority)
    }
    if "last_verification_transition_accepted" in incoming_data and not incoming_transition_accepted:
        merged["last_verification_transition_accepted"] = False
        merged["verified_open_in_run"] = False
        merged["current_active_verified_open"] = False
    if nondefinitive:
        # Preserve durable verified fields/lifecycle, while exposing that this
        # run did not establish a new definitive state.
        merged["verification_status"] = new.verification_status.value
        if new.verification_confidence is not None:
            merged["verification_confidence"] = new.verification_confidence
        if old.verification_status.is_definitive:
            merged.setdefault(
                "last_definitive_verification_status", old.verification_status.value
            )
    merged["canonical_id"] = old.canonical_id or canonical_job_identity(new)
    return JobRecord.from_dict(merged)


def deduplicate_jobs(
    jobs: Iterable[JobRecord | Mapping[str, Any]],
    *,
    semantic_threshold: float = 0.94,
) -> list[JobRecord]:
    """Coalesce duplicates in input order using conservative identity rules."""

    canonical: list[JobRecord] = []
    for raw_job in jobs:
        job = copy.deepcopy(coerce_job(raw_job))
        if not job.canonical_id:
            job.canonical_id = canonical_job_identity(job)
        for index, current in enumerate(canonical):
            if are_duplicate_jobs(current, job, semantic_threshold=semantic_threshold):
                canonical[index] = merge_job_records(current, job)
                break
        else:
            canonical.append(job)
    return canonical


dedupe_jobs = deduplicate_jobs
