"""Structured, schema-checked handoff to Academic GatedSprint."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from ...core.identity import canonical_job_identity
from ...core.models import JobRecord
from .models import FitEvaluation, get_value, text_values, to_plain_data


HANDOFF_SCHEMA_VERSION = 1
_EVIDENCE_STRENGTH_ALIASES = {
    "direct": "strong_direct_evidence",
    "strong direct evidence": "strong_direct_evidence",
    "adjacent": "credible_adjacent_evidence",
    "credible adjacent evidence": "credible_adjacent_evidence",
    "unknown": "uncertain",
    "none": "no_evidence",
    "no evidence": "no_evidence",
}


class ContractValidationError(ValueError):
    """Raised when a generated deployment payload violates its public schema."""

    def __init__(self, schema_name: str, issues: Sequence[str]) -> None:
        self.schema_name = schema_name
        self.issues = tuple(issues)
        detail = "; ".join(self.issues) or "unknown contract violation"
        super().__init__(f"{schema_name}: {detail}")


def _schema_path(schema_name: str) -> Path:
    if Path(schema_name).name != schema_name or not schema_name.endswith(".schema.json"):
        raise ValueError(f"Unsupported schema name: {schema_name!r}")
    path = Path(__file__).resolve().parent / "schemas" / schema_name
    if not path.is_file():
        raise ValueError(f"Unknown Academic PI schema: {schema_name}")
    return path


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
        ) or (
            isinstance(value, float)
            and math.isfinite(value)
        )
    return False


def _resolve_local_ref(root_schema: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"Only local schema references are supported: {reference!r}")
    current: Any = root_schema
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or token not in current:
            raise ValueError(f"Unresolvable local schema reference: {reference!r}")
        current = current[token]
    if not isinstance(current, Mapping):
        raise ValueError(f"Schema reference is not an object: {reference!r}")
    return current


def _format_is_valid(value: str, format_name: str) -> bool:
    if format_name == "uri":
        parsed = urlparse(value)
        return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))
    if format_name == "date-time":
        if "T" not in value:
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return True
    return True


def _collect_schema_issues(
    value: Any,
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    *,
    path: str = "$",
) -> list[str]:
    """Validate the conservative JSON Schema subset used by this deployment."""

    if "$ref" in schema:
        return _collect_schema_issues(
            value,
            _resolve_local_ref(root_schema, str(schema["$ref"])),
            root_schema,
            path=path,
        )

    if "anyOf" in schema:
        alternatives = schema["anyOf"]
        if any(
            not _collect_schema_issues(value, option, root_schema, path=path)
            for option in alternatives
            if isinstance(option, Mapping)
        ):
            return []
        return [f"{path}: value does not match any allowed schema"]

    issues: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_json_type_matches(value, str(item)) for item in expected_types):
            names = ", ".join(str(item) for item in expected_types)
            return [f"{path}: expected {names}; got {type(value).__name__}"]

    if "const" in schema and value != schema["const"]:
        issues.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        issues.append(f"{path}: value {value!r} is not in the allowed enum")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            issues.append(f"{path}: string is shorter than {minimum_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            issues.append(f"{path}: string does not match required pattern")
        format_name = schema.get("format")
        if isinstance(format_name, str) and not _format_is_valid(value, format_name):
            issues.append(f"{path}: invalid {format_name}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            issues.append(f"{path}: value is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            issues.append(f"{path}: value is above {schema['maximum']}")

    if isinstance(value, Mapping):
        required = schema.get("required", ())
        for key in required:
            if key not in value:
                issues.append(f"{path}.{key}: required property is missing")
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for key, item in value.items():
                child_path = f"{path}.{key}"
                child_schema = properties.get(key)
                if isinstance(child_schema, Mapping):
                    issues.extend(
                        _collect_schema_issues(item, child_schema, root_schema, path=child_path)
                    )
                elif schema.get("additionalProperties") is False:
                    issues.append(f"{child_path}: additional property is not allowed")
                elif isinstance(schema.get("additionalProperties"), Mapping):
                    issues.extend(
                        _collect_schema_issues(
                            item,
                            schema["additionalProperties"],
                            root_schema,
                            path=child_path,
                        )
                    )

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            issues.append(f"{path}: array has fewer than {minimum_items} items")
        if schema.get("uniqueItems"):
            markers = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(markers) != len(set(markers)):
                issues.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                issues.extend(
                    _collect_schema_issues(
                        item,
                        item_schema,
                        root_schema,
                        path=f"{path}[{index}]",
                    )
                )
    return issues


def validate_schema_payload(payload: Any, schema_name: str) -> None:
    """Validate a payload without importing or executing third-party schema code."""

    schema_path = _schema_path(schema_name)
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # fail closed on a broken contract
        raise ContractValidationError(schema_name, [f"schema could not be loaded: {exc}"]) from exc
    issues = _collect_schema_issues(payload, schema, schema)
    if issues:
        raise ContractValidationError(schema_name, issues)


def _canonical_id(job: Any) -> Any:
    value = get_value(
        job,
        "canonical_id",
        "canonical_job_id",
        "identity.canonical_job_id",
        "id",
        default=None,
    )
    if value not in (None, ""):
        return value
    if isinstance(job, (JobRecord, Mapping)):
        try:
            return canonical_job_identity(job)
        except (TypeError, ValueError):
            return None
    return None


def _evidence_reference(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        reference = item.get("ref", item.get("id"))
        strength = item.get("strength", "uncertain")
        note = item.get("note", item.get("claim"))
    else:
        reference = str(item)
        strength = "uncertain"
        note = None
    strength_text = str(strength).strip()
    strength_text = _EVIDENCE_STRENGTH_ALIASES.get(
        strength_text.casefold().replace("_", " "), strength_text
    )
    result: dict[str, Any] = {
        "ref": "" if reference is None else str(reference).strip(),
        "strength": strength_text,
    }
    if note not in (None, ""):
        result["note"] = str(to_plain_data(note)).strip()
    return result


def _evidence_is_authorized(item: Any) -> bool:
    """Require affirmative authorization for an evidence-ledger reference."""

    if not isinstance(item, Mapping):
        return False
    marker = item.get(
        "authorized",
        item.get("authorized_for_handoff", item.get("authorization")),
    )
    if marker is None:
        return False
    if isinstance(marker, bool):
        return marker
    return str(marker).strip().casefold() in {
        "approved",
        "authorized",
        "true",
        "yes",
    }


def _handoff_precondition_issues(
    job: Any,
    evaluation_data: Mapping[str, Any],
    evidence: Sequence[Any],
    *,
    max_verification_age_days: int,
    now: datetime | None,
) -> list[str]:
    issues: list[str] = []
    lifecycle = str(
        get_value(job, "lifecycle_status", "status.lifecycle_status", default="")
        or ""
    ).strip().casefold()
    if lifecycle in {
        "closed",
        "expired",
        "withdrawn",
        "rejected",
        "closed_expired",
    }:
        issues.append("$.job: lifecycle is closed or otherwise terminal")

    raw_verification = get_value(
        job,
        "verification_status",
        "status.verification_status",
        default="unknown",
    )
    verification = str(getattr(raw_verification, "value", raw_verification))
    if verification not in {"verified_open", "verified_reopened"}:
        issues.append(
            "$.job.verified_at: job is not currently verified open or reopened"
        )
    if bool(get_value(job, "verification_stale", "status.stale", default=False)):
        issues.append("$.job.verified_at: verification is marked stale")
    transition_accepted = get_value(
        job,
        "last_verification_transition_accepted",
        "extra.last_verification_transition_accepted",
        default=None,
    )
    if transition_accepted is False:
        issues.append(
            "$.job.verified_at: the latest verification transition was not accepted"
        )
    if not get_value(job, "official_url", "urls.official_url", default=None):
        issues.append("$.job.official_url: a currently verified official URL is required")
    last_verified = get_value(
        job, "last_verified", "status.last_verified", default=None
    )
    if not last_verified:
        issues.append("$.job.verified_at: last_verified is required")
    else:
        try:
            verified_at = datetime.fromisoformat(
                str(last_verified).replace("Z", "+00:00")
            )
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=timezone.utc)
            verified_at = verified_at.astimezone(timezone.utc)
        except ValueError:
            issues.append("$.job.verified_at: last_verified must be a valid date-time")
        else:
            reference_time = now or datetime.now(timezone.utc)
            if reference_time.tzinfo is None:
                reference_time = reference_time.replace(tzinfo=timezone.utc)
            reference_time = reference_time.astimezone(timezone.utc)
            if verified_at > reference_time + timedelta(minutes=5):
                issues.append("$.job.verified_at: verification timestamp is in the future")
            elif verified_at < reference_time - timedelta(
                days=max_verification_age_days
            ):
                issues.append(
                    "$.job.verified_at: verification is older than the allowed cadence"
                )

    unauthorized = [
        index
        for index, item in enumerate(evidence)
        if not _evidence_is_authorized(item)
    ]
    issues.extend(
        f"$.candidate_evidence.evidence_refs[{index}]: evidence is not authorized for handoff"
        for index in unauthorized
    )
    positive_claims = bool(text_values(evaluation_data.get("strongest_matches")))
    positive_tier = str(evaluation_data.get("tier") or "") in {"Tier 1", "Tier 2"}
    if (positive_claims or positive_tier) and not evidence:
        issues.append(
            "$.candidate_evidence.evidence_refs: at least one authorized evidence reference "
            "is required for a positive fit handoff"
        )
    return issues


def build_gatedsprint_handoff(
    job: Any,
    evaluation: FitEvaluation | Mapping[str, Any] | None = None,
    evidence: Iterable[Any] = (),
    *,
    max_verification_age_days: int = 7,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build and validate a versioned handoff that never authorizes submission."""

    evaluation_data: Mapping[str, Any]
    if isinstance(evaluation, FitEvaluation):
        evaluation_data = evaluation.to_dict()
    elif isinstance(evaluation, Mapping):
        evaluation_data = evaluation
    else:
        candidate = get_value(job, "evaluation", default={})
        evaluation_data = candidate if isinstance(candidate, Mapping) else {}

    evidence_items = tuple(evidence)
    if isinstance(max_verification_age_days, bool) or not isinstance(
        max_verification_age_days, int
    ) or max_verification_age_days < 0:
        raise ValueError("max_verification_age_days must be a non-negative integer")
    precondition_issues = _handoff_precondition_issues(
        job,
        evaluation_data,
        evidence_items,
        max_verification_age_days=max_verification_age_days,
        now=now,
    )
    if precondition_issues:
        raise ContractValidationError(
            "gatedsprint_handoff.schema.json",
            precondition_issues,
        )

    payload = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "job": {
            "canonical_job_id": _canonical_id(job),
            "official_url": get_value(job, "official_url", "urls.official_url", default=None),
            "verified_at": get_value(job, "last_verified", "status.last_verified", default=None),
            "institution": get_value(job, "institution", "identity.institution", default=None),
            "department": get_value(job, "department", "identity.department", default=None),
            "title": get_value(job, "title", "raw_title", "identity.raw_title", default=None),
            "deadline": get_value(job, "deadline", "dates.deadline", default=None),
        },
        "search": {
            "normalized_role_class": get_value(
                job,
                "role_class",
                "normalized_role_class",
                "identity.normalized_role_class",
                default="other",
            ),
            "independence_evidence": list(
                text_values(
                    get_value(
                        job,
                        "independence_evidence",
                        "independence.evidence",
                        default=(),
                    )
                )
            ),
            "declared_fields": list(
                text_values(
                    get_value(job, "declared_fields", "search_scope.declared_fields", default=())
                )
            ),
            "broad_search": bool(
                get_value(job, "broad_search", "search_scope.broad_search", default=False)
            ),
            "required_documents": list(
                text_values(
                    get_value(
                        job,
                        "required_documents",
                        "requirements.required_documents",
                        default=(),
                    )
                )
            ),
            "reference_letter_policy": get_value(
                job,
                "reference_letter_policy",
                "requirements.reference_letter_policy",
                default=None,
            ),
        },
        "evaluation": {
            "fit_score": evaluation_data.get("fit_score"),
            "tier": evaluation_data.get("tier"),
            "strongest_matches": list(text_values(evaluation_data.get("strongest_matches"))),
            "meaningful_gaps": list(text_values(evaluation_data.get("meaningful_gaps"))),
            "blockers": list(
                text_values(
                    evaluation_data.get("hard_blockers", evaluation_data.get("blockers"))
                )
            ),
            "uncertainty": list(text_values(evaluation_data.get("uncertainty"))),
        },
        "candidate_evidence": {
            "evidence_refs": [_evidence_reference(item) for item in evidence_items]
        },
        "application": {
            "current_status": get_value(
                job, "application.status", "application_status", default="not_started"
            ),
            "existing_materials": list(
                text_values(
                    get_value(
                        job,
                        "application.existing_materials",
                        "existing_materials",
                        default=(),
                    )
                )
            ),
            "submission_authorized": False,
        },
    }
    validate_schema_payload(payload, "gatedsprint_handoff.schema.json")
    return payload


def render_gatedsprint_handoff(
    job: Any,
    evaluation: FitEvaluation | Mapping[str, Any] | None = None,
    evidence: Iterable[Any] = (),
    *,
    max_verification_age_days: int = 7,
    now: datetime | None = None,
) -> str:
    """Return deterministic schema-validated JSON, which is also valid YAML 1.2."""

    return json.dumps(
        build_gatedsprint_handoff(
            job,
            evaluation,
            evidence,
            max_verification_age_days=max_verification_age_days,
            now=now,
        ),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


build_academic_gatedsprint_handoff = build_gatedsprint_handoff
