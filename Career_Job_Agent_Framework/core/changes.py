"""Material-change detection with noise-resistant comparisons."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from .identity import coerce_job
from .models import ChangeRecord, JobRecord, VerificationStatus, json_safe, utc_now
from .urls import normalize_url


DEFAULT_MATERIAL_FIELDS: tuple[str, ...] = (
    "lifecycle_status",
    "verification_status",
    "deadline",
    "deadline_type",
    "title",
    "normalized_title",
    "role_class",
    "department",
    "location",
    "position.tenure_status",
    "position.faculty_track",
    "position.appointment_type",
    "position.contract_term",
    "position.salary_min",
    "position.salary_max",
    "position.salary_currency",
    "requirements.required_documents",
    "requirements.reference_letter_policy",
    "requirements.number_of_references",
    "requirements.citizenship_or_eligibility",
    "search_scope.declared_fields",
    "search_scope.department_scope",
    "position.teaching_expectation",
    "expected_start_date",
    "official_url",
    "official_job_id",
)

DEFAULT_EVALUATION_FIELDS: tuple[str, ...] = (
    "fit_score",
    "tier",
    "evaluation.fit_confidence",
    "evaluation.opportunity_notes",
    "evaluation.qol_notes",
    "strongest_matches",
    "meaningful_gaps",
    "hard_blockers",
)

_TRANSIENT_STATUSES = {
    VerificationStatus.VERIFICATION_PENDING.value,
    VerificationStatus.VERIFICATION_FAILED_TRANSIENT.value,
}


def _as_mapping(value: JobRecord | Mapping[str, Any]) -> Mapping[str, Any]:
    return coerce_job(value).to_dict() if isinstance(value, JobRecord) else value


def get_field(value: Mapping[str, Any], path: str) -> Any:
    if path in value:
        return value[path]
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def normalize_comparable(value: Any, *, field_path: str = "") -> Any:
    """Normalize formatting noise without erasing meaningful values."""

    value = json_safe(value)
    if value is None:
        return None
    if field_path.endswith("url") and isinstance(value, str):
        return normalize_url(value)
    if isinstance(value, str):
        return _normalized_text(value)
    if isinstance(value, list):
        normalized = [normalize_comparable(item, field_path=field_path) for item in value]
        return sorted(normalized, key=repr)
    if isinstance(value, dict):
        return {
            key: normalize_comparable(item, field_path=f"{field_path}.{key}".strip("."))
            for key, item in sorted(value.items())
        }
    return value


def _detect(
    old: JobRecord | Mapping[str, Any],
    new: JobRecord | Mapping[str, Any],
    *,
    fields: Iterable[str],
    changed_at: str | None,
    source: str | None,
    confidence: float | None,
    change_type: str,
    ignore_missing: bool,
) -> list[ChangeRecord]:
    previous = _as_mapping(old)
    current = _as_mapping(new)
    job_id = str(
        current.get("canonical_id")
        or current.get("id")
        or previous.get("canonical_id")
        or previous.get("id")
        or ""
    )
    timestamp = changed_at or utc_now()
    changes: list[ChangeRecord] = []
    for path in fields:
        old_value = get_field(previous, path)
        new_value = get_field(current, path)
        if ignore_missing and new_value is None:
            continue
        if path == "verification_status":
            status = str(getattr(new_value, "value", new_value) or "")
            if status in _TRANSIENT_STATUSES:
                continue
        if normalize_comparable(old_value, field_path=path) == normalize_comparable(
            new_value, field_path=path
        ):
            continue
        changes.append(
            ChangeRecord(
                job_id=job_id,
                field=path,
                old_value=old_value,
                new_value=new_value,
                changed_at=timestamp,
                source=source,
                confidence=confidence,
                change_type=change_type,
            )
        )
    return changes


def detect_material_changes(
    old: JobRecord | Mapping[str, Any],
    new: JobRecord | Mapping[str, Any],
    *,
    fields: Iterable[str] | None = None,
    changed_at: str | None = None,
    source: str | None = None,
    confidence: float | None = None,
    ignore_missing: bool = True,
) -> list[ChangeRecord]:
    return _detect(
        old,
        new,
        fields=fields or DEFAULT_MATERIAL_FIELDS,
        changed_at=changed_at,
        source=source,
        confidence=confidence,
        change_type="job_content_change",
        ignore_missing=ignore_missing,
    )


def detect_evaluation_changes(
    old: JobRecord | Mapping[str, Any],
    new: JobRecord | Mapping[str, Any],
    *,
    fields: Iterable[str] | None = None,
    changed_at: str | None = None,
    source: str | None = None,
) -> list[ChangeRecord]:
    """Track rescoring separately so it never masquerades as discovery."""

    return _detect(
        old,
        new,
        fields=fields or DEFAULT_EVALUATION_FIELDS,
        changed_at=changed_at,
        source=source,
        confidence=None,
        change_type="evaluation_change",
        ignore_missing=True,
    )
