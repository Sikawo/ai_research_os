"""Canonical-state upsert rules for manually evaluated Career Job Agent roles."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .reporting import VerificationOutcome, canonical_role_identity


OFFICIAL_EMPLOYER_SOURCES = {
    "official employer career page",
    "official employer page",
    "official_employer_career_page",
    "official_employer_page",
}

CANONICAL_UPSERT_FIELDS = (
    "company",
    "official_job_id",
    "job_id",
    "title",
    "location",
    "worksite",
    "official_url",
    "job_url",
    "posting_date",
    "closing_date",
    "salary",
    "salary_range",
    "salary_verified",
    "salary_source",
    "requirements",
    "sponsorship_wording",
    "fit_score",
    "score",
    "tier",
    "strongest_match",
    "strength",
    "key_gap",
    "gap",
    "workflow_status",
    "application_status",
    "official_status",
    "official_verified_once",
    "official_verified_at",
    "in_scope",
    "within_scope",
    "employer_in_scope",
    "source_in_scope",
    "rejected",
    "hard_blocked",
    "hard_blockers",
    "closed",
    "expired",
    "awaiting_first_time_verification",
    "rubric_version",
)


class PersistenceAction(str, Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ManualEvaluationPersistenceConfig:
    enabled: bool = True
    upsert_actionable_tier_1_2: bool = True
    require_current_official_verification: bool = True

    @classmethod
    def from_root(
        cls, config: Mapping[str, Any]
    ) -> "ManualEvaluationPersistenceConfig":
        state_persistence = config.get("state_persistence", {})
        if not isinstance(state_persistence, Mapping):
            raise ValueError("state_persistence must be a mapping")
        raw = state_persistence.get("manual_evaluations", {})
        if not isinstance(raw, Mapping):
            raise ValueError("state_persistence.manual_evaluations must be a mapping")
        return cls(
            enabled=bool(raw.get("enabled", True)),
            upsert_actionable_tier_1_2=bool(
                raw.get("upsert_actionable_tier_1_2", True)
            ),
            require_current_official_verification=bool(
                raw.get("require_current_official_verification", True)
            ),
        )


@dataclass(frozen=True)
class ManualOfficialVerification:
    """Verification evidence produced during the current manual evaluation."""

    source: str
    outcome: VerificationOutcome
    verified_current_run: bool


@dataclass(frozen=True)
class PersistenceResult:
    action: PersistenceAction
    reason: str
    canonical_index: int | None = None
    scheduled_new_job_count_delta: int = 0
    duplicate_daily_alert_required: bool = False
    application_submission_triggered: bool = False


class CanonicalStateAdapter(Protocol):
    """Existing deployment adapter for the authoritative canonical state."""

    def load_canonical_rows(self) -> Sequence[Mapping[str, Any]]: ...

    def write_canonical_rows(self, rows: Sequence[Mapping[str, Any]]) -> None: ...


def _text(role: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = role.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalized(value: object) -> str:
    return " ".join(str(value).casefold().strip().split())


def _normalized_source(value: object) -> str:
    return _normalized(value).replace("-", "_").replace(" ", "_")


def _normalized_tier(value: object) -> str | None:
    tier = _normalized(value).replace("-", "_").replace(" ", "_")
    if tier in {"1", "tier1", "tier_1"}:
        return "tier_1"
    if tier in {"2", "tier2", "tier_2"}:
        return "tier_2"
    return None


def _company_job_id_key(role: Mapping[str, Any]) -> tuple[str, ...] | None:
    company = _text(role, "company")
    job_id = _text(role, "official_job_id", "job_id")
    if not company or not job_id:
        return None
    return canonical_role_identity({"company": company, "official_job_id": job_id})


def _official_url_key(role: Mapping[str, Any]) -> tuple[str, ...] | None:
    official_url = _text(role, "official_url", "job_url")
    if not official_url:
        return None
    return canonical_role_identity({"official_url": official_url})


def _fallback_key(role: Mapping[str, Any]) -> tuple[str, ...] | None:
    company = _text(role, "company")
    title = _text(role, "title")
    location = _text(role, "location")
    if not company or not title or not location:
        return None
    return canonical_role_identity(
        {"company": company, "title": title, "location": location}
    )


def _find_existing_index(
    canonical_rows: MutableSequence[MutableMapping[str, Any]],
    evaluated_role: Mapping[str, Any],
) -> int | None:
    for key_builder in (_company_job_id_key, _official_url_key, _fallback_key):
        incoming_key = key_builder(evaluated_role)
        if incoming_key is None:
            continue
        for index, existing in enumerate(canonical_rows):
            if key_builder(existing) == incoming_key:
                return index
    return None


def _has_hard_blocker(role: Mapping[str, Any]) -> bool:
    return bool(role.get("hard_blocked")) or bool(role.get("hard_blockers"))


def _is_actionable_tier_1_2(role: Mapping[str, Any]) -> bool:
    if _normalized_tier(role.get("tier")) is None:
        return False
    workflow_status = _normalized(
        _text(role, "workflow_status", "application_status")
    )
    official_status = _normalized(_text(role, "official_status", "posting_status"))
    if bool(role.get("rejected")) or workflow_status in {"rejected", "skip", "skipped"}:
        return False
    if _has_hard_blocker(role):
        return False
    if bool(role.get("closed")) or bool(role.get("expired")):
        return False
    if official_status in {"closed", "expired"}:
        return False
    if role.get("in_scope") is False or role.get("within_scope") is False:
        return False
    if role.get("employer_in_scope") is False or role.get("source_in_scope") is False:
        return False
    return True


def _verification_is_eligible(
    verification: ManualOfficialVerification,
    config: ManualEvaluationPersistenceConfig,
) -> bool:
    source = _normalized_source(verification.source)
    normalized_sources = {_normalized_source(value) for value in OFFICIAL_EMPLOYER_SOURCES}
    if source not in normalized_sources:
        return False
    if verification.outcome is not VerificationOutcome.ACTIVE:
        return False
    if (
        config.require_current_official_verification
        and not verification.verified_current_run
    ):
        return False
    return True


def _has_usable_identity(role: Mapping[str, Any]) -> bool:
    return any(
        key_builder(role) is not None
        for key_builder in (_company_job_id_key, _official_url_key, _fallback_key)
    )


def _copyable_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _canonical_updates(evaluated_role: Mapping[str, Any]) -> dict[str, Any]:
    updates = {
        field: evaluated_role[field]
        for field in CANONICAL_UPSERT_FIELDS
        if field in evaluated_role and _copyable_value(evaluated_role[field])
    }
    updates["official_status"] = "active"
    updates["official_verified_once"] = True
    normalized_tier = _normalized_tier(evaluated_role.get("tier"))
    if normalized_tier is not None:
        updates["tier"] = normalized_tier
    return updates


def upsert_manual_evaluation(
    canonical_rows: MutableSequence[MutableMapping[str, Any]],
    evaluated_role: Mapping[str, Any],
    verification: ManualOfficialVerification,
    config: ManualEvaluationPersistenceConfig,
) -> PersistenceResult:
    """Upsert a qualifying evaluation into caller-owned canonical rows.

    The row collection is the deployment's existing canonical state view, such
    as rows loaded from the configured state adapter. The caller remains
    responsible for committing the mutated rows through that existing state
    adapter; this function does not create a second state store.
    """

    if not config.enabled:
        return PersistenceResult(PersistenceAction.SKIPPED, "manual_persistence_disabled")
    if not config.upsert_actionable_tier_1_2:
        return PersistenceResult(PersistenceAction.SKIPPED, "manual_upsert_disabled")
    if not _is_actionable_tier_1_2(evaluated_role):
        return PersistenceResult(PersistenceAction.SKIPPED, "role_not_actionable_tier_1_2")
    if not _verification_is_eligible(verification, config):
        return PersistenceResult(
            PersistenceAction.SKIPPED, "current_official_verification_required"
        )
    if not _has_usable_identity(evaluated_role):
        return PersistenceResult(PersistenceAction.SKIPPED, "canonical_identity_missing")

    updates = _canonical_updates(evaluated_role)
    existing_index = _find_existing_index(canonical_rows, evaluated_role)
    if existing_index is None:
        canonical_rows.append(dict(updates))
        return PersistenceResult(
            PersistenceAction.INSERTED,
            "qualifying_manual_role_inserted",
            len(canonical_rows) - 1,
        )

    canonical_rows[existing_index].update(updates)
    return PersistenceResult(
        PersistenceAction.UPDATED,
        "qualifying_manual_role_updated",
        existing_index,
    )


def persist_manual_evaluation(
    state_adapter: CanonicalStateAdapter,
    evaluated_role: Mapping[str, Any],
    verification: ManualOfficialVerification,
    config: ManualEvaluationPersistenceConfig,
) -> PersistenceResult:
    """Apply the upsert and commit it through the existing state adapter.

    Work happens on a copy so a failed adapter write cannot be mistaken for a
    successful durable mutation. Adapter exceptions intentionally propagate.
    """

    canonical_rows = [dict(row) for row in state_adapter.load_canonical_rows()]
    result = upsert_manual_evaluation(
        canonical_rows, evaluated_role, verification, config
    )
    if result.action is not PersistenceAction.SKIPPED:
        state_adapter.write_canonical_rows(canonical_rows)
    return result
