"""Canonical daily-report payloads for the Career Job Agent.

The current-active snapshot is deliberately separate from today's alert data.
It re-verifies eligible canonical roles once, stores the result in one immutable
payload, and lets every user-facing channel render that same role set.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit, urlunsplit


USER_FACING_CHANNELS = (
    "daily_report",
    "chatgpt_digest",
    "gmail_digest",
    "slack_digest",
)


class VerificationOutcome(str, Enum):
    """Current-run result from checking an official employer job page."""

    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    SOURCE_FAILURE = "source_failure"
    AMBIGUOUS = "ambiguous"
    PENDING = "pending"


@dataclass(frozen=True)
class OfficialVerification:
    outcome: VerificationOutcome
    detail: str = ""


OfficialVerifier = Callable[[Mapping[str, Any]], OfficialVerification]


@dataclass(frozen=True)
class CurrentActiveConfig:
    enabled: bool = True
    heading: str = "CURRENT ACTIVE TIER 1/2"
    include_unchanged: bool = True
    reverify_official_status_each_daily_run: bool = True
    include_in: tuple[str, ...] = USER_FACING_CHANNELS
    sort: tuple[str, ...] = ("tier", "fit_score_desc", "company", "title")
    fields: tuple[str, ...] = (
        "tier",
        "fit_score",
        "company",
        "title",
        "job_id",
        "location",
        "salary",
        "workflow_status",
        "strongest_match",
        "key_gap",
        "official_url",
    )

    @classmethod
    def from_reporting(cls, reporting: Mapping[str, Any]) -> "CurrentActiveConfig":
        raw = reporting.get("current_active_tier_1_2", {})
        if not isinstance(raw, Mapping):
            raise ValueError("reporting.current_active_tier_1_2 must be a mapping")
        return cls(
            enabled=bool(raw.get("enabled", True)),
            heading=str(raw.get("heading", cls.heading)),
            include_unchanged=bool(raw.get("include_unchanged", True)),
            reverify_official_status_each_daily_run=bool(
                raw.get("reverify_official_status_each_daily_run", True)
            ),
            include_in=tuple(raw.get("include_in", USER_FACING_CHANNELS)),
            sort=tuple(raw.get("sort", cls.sort)),
            fields=tuple(raw.get("fields", cls.fields)),
        )


@dataclass(frozen=True)
class ActiveRole:
    tier: str
    fit_score: float
    company: str
    title: str
    job_id: str
    location: str
    salary: str | None
    workflow_status: str
    strongest_match: str
    key_gap: str
    official_url: str


@dataclass(frozen=True)
class CurrentActiveSnapshot:
    enabled: bool
    heading: str
    include_in: tuple[str, ...]
    roles: tuple[ActiveRole, ...]
    incomplete_checks: tuple[str, ...]


@dataclass(frozen=True)
class DailyReportPayload:
    """One run payload shared by all user-facing report renderers."""

    today_changes: str
    alert_counts: Mapping[str, int]
    incomplete_checks: tuple[str, ...]
    current_active: CurrentActiveSnapshot


def _text(role: Mapping[str, Any], *names: str, default: str = "") -> str:
    for name in names:
        value = role.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _normalized(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _normalized_tier(value: object) -> str | None:
    normalized = _normalized(str(value)).replace("-", "_").replace(" ", "_")
    if normalized in {"1", "tier1", "tier_1"}:
        return "Tier 1"
    if normalized in {"2", "tier2", "tier_2"}:
        return "Tier 2"
    return None


def _canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, "", ""))


def canonical_role_identity(role: Mapping[str, Any]) -> tuple[str, ...]:
    """Apply the existing canonical deduplication precedence."""

    company = _normalized(_text(role, "company"))
    job_id = _normalized(_text(role, "official_job_id", "job_id"))
    if company and job_id:
        return ("company_job_id", company, job_id)
    official_url = _canonical_url(_text(role, "official_url", "job_url"))
    if official_url:
        return ("official_url", official_url)
    return (
        "company_title_location",
        company,
        _normalized(_text(role, "title")),
        _normalized(_text(role, "location")),
    )


def _has_hard_blocker(role: Mapping[str, Any]) -> bool:
    blockers = role.get("hard_blockers")
    return bool(role.get("hard_blocked")) or bool(blockers)


def _is_preverification_candidate(role: Mapping[str, Any]) -> bool:
    if _normalized_tier(role.get("tier")) is None:
        return False
    workflow_status = _normalized(_text(role, "workflow_status", "application_status"))
    official_status = _normalized(_text(role, "official_status", "posting_status"))
    if bool(role.get("rejected")) or workflow_status in {"rejected", "skip", "skipped"}:
        return False
    if _has_hard_blocker(role):
        return False
    if bool(role.get("closed")) or bool(role.get("expired")):
        return False
    if official_status in {"closed", "expired"}:
        return False
    if bool(role.get("awaiting_first_time_verification")):
        return False
    if official_status in {"verification_pending", "unverified"} and not bool(
        role.get("official_verified_once")
    ):
        return False
    if role.get("in_scope") is False or role.get("within_scope") is False:
        return False
    if role.get("employer_in_scope") is False or role.get("source_in_scope") is False:
        return False
    return True


def _salary(role: Mapping[str, Any]) -> str | None:
    salary = _text(role, "salary", "salary_range")
    salary_source = _normalized(_text(role, "salary_source"))
    verified = bool(role.get("salary_verified")) or salary_source in {
        "official",
        "official employer page",
        "official_employer_page",
    }
    return salary if salary and verified else None


def _active_role(role: Mapping[str, Any]) -> ActiveRole:
    tier = _normalized_tier(role.get("tier"))
    if tier is None:  # guarded by _is_preverification_candidate
        raise ValueError("active role must have Tier 1 or Tier 2 classification")
    return ActiveRole(
        tier=tier,
        fit_score=float(role.get("fit_score", role.get("score", 0.0))),
        company=_text(role, "company", default="Not recorded"),
        title=_text(role, "title", default="Not recorded"),
        job_id=_text(role, "official_job_id", "job_id", default="Not recorded"),
        location=_text(role, "location", default="Not recorded"),
        salary=_salary(role),
        workflow_status=_text(
            role, "workflow_status", "application_status", default="Not recorded"
        ),
        strongest_match=_text(
            role, "strongest_match", "strength", default="Not recorded"
        ),
        key_gap=_text(role, "key_gap", "gap", default="Not recorded"),
        official_url=_text(role, "official_url", "job_url", default="Not recorded"),
    )


def _sort_key(role: ActiveRole) -> tuple[object, ...]:
    return (
        0 if role.tier == "Tier 1" else 1,
        -role.fit_score,
        role.company.casefold(),
        role.title.casefold(),
    )


def build_current_active_snapshot(
    canonical_roles: Iterable[Mapping[str, Any]],
    verifier: OfficialVerifier | None,
    config: CurrentActiveConfig,
) -> CurrentActiveSnapshot:
    """Reverify and select the run's canonical CURRENT ACTIVE role set.

    The input records are never mutated. Definitive closed/expired results may
    be persisted by the caller's normal state writer; source failures are
    returned as incomplete checks and do not imply a state transition.
    """

    if not config.enabled:
        return CurrentActiveSnapshot(False, config.heading, config.include_in, (), ())
    if not config.include_unchanged:
        raise ValueError("CURRENT ACTIVE requires include_unchanged: true")
    if not config.reverify_official_status_each_daily_run:
        raise ValueError(
            "CURRENT ACTIVE requires reverify_official_status_each_daily_run: true"
        )
    if verifier is None:
        raise ValueError("CURRENT ACTIVE requires an official-page verifier")

    roles: list[ActiveRole] = []
    incomplete: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for record in canonical_roles:
        if not _is_preverification_candidate(record):
            continue
        identity = canonical_role_identity(record)
        if identity in seen:
            continue
        seen.add(identity)
        label = " | ".join(
            (
                _text(record, "company", default="Unknown company"),
                _text(record, "title", default="Unknown role"),
            )
        )
        try:
            verification = verifier(record)
        except Exception as error:  # source adapters may fail independently
            incomplete.append(
                f"{label} | official verification failed: {type(error).__name__}"
            )
            continue
        if verification.outcome is VerificationOutcome.ACTIVE:
            roles.append(_active_role(record))
        elif verification.outcome in {
            VerificationOutcome.SOURCE_FAILURE,
            VerificationOutcome.AMBIGUOUS,
            VerificationOutcome.PENDING,
        }:
            detail = verification.detail or verification.outcome.value
            incomplete.append(f"{label} | official verification incomplete: {detail}")

    return CurrentActiveSnapshot(
        True,
        config.heading,
        config.include_in,
        tuple(sorted(roles, key=_sort_key)),
        tuple(incomplete),
    )


def build_daily_report_payload(
    *,
    today_changes: str,
    alert_counts: Mapping[str, int],
    canonical_roles: Iterable[Mapping[str, Any]],
    verifier: OfficialVerifier | None,
    config: CurrentActiveConfig,
    incomplete_checks: Iterable[str] = (),
) -> DailyReportPayload:
    snapshot = build_current_active_snapshot(canonical_roles, verifier, config)
    counts = MappingProxyType(dict(alert_counts))
    combined_incomplete = tuple(incomplete_checks) + snapshot.incomplete_checks
    return DailyReportPayload(today_changes, counts, combined_incomplete, snapshot)


def _score(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def render_current_active(snapshot: CurrentActiveSnapshot) -> str:
    lines = [snapshot.heading]
    if not snapshot.roles:
        return "\n".join((snapshot.heading, "None."))
    for tier in ("Tier 1", "Tier 2"):
        tier_roles = [role for role in snapshot.roles if role.tier == tier]
        if not tier_roles:
            continue
        lines.extend(("", tier))
        for role in tier_roles:
            lines.append(
                f"- {_score(role.fit_score)} | {role.company} | {role.title} | "
                f"{role.job_id} | {role.location}"
            )
            lines.append(f"  Salary: {role.salary or 'Not verified.'}")
            lines.append(f"  Status: {role.workflow_status}")
            lines.append(f"  Strength: {role.strongest_match}")
            lines.append(f"  Gap: {role.key_gap}")
            lines.append(f"  Official: {role.official_url}")
    return "\n".join(lines)


def render_user_facing_output(payload: DailyReportPayload, channel: str) -> str:
    if channel not in USER_FACING_CHANNELS:
        raise ValueError(f"unsupported user-facing channel: {channel}")
    sections = [payload.today_changes.rstrip()]
    if payload.incomplete_checks:
        sections.append(
            "INCOMPLETE CHECKS / SOURCE FAILURES\n"
            + "\n".join(f"- {item}" for item in payload.incomplete_checks)
        )
    if payload.current_active.enabled and channel in payload.current_active.include_in:
        sections.append(render_current_active(payload.current_active))
    return "\n\n".join(section for section in sections if section).rstrip()


def render_daily_report(payload: DailyReportPayload) -> str:
    return render_user_facing_output(payload, "daily_report")


def render_chatgpt_digest(payload: DailyReportPayload) -> str:
    return render_user_facing_output(payload, "chatgpt_digest")


def render_gmail_digest(payload: DailyReportPayload) -> str:
    return render_user_facing_output(payload, "gmail_digest")


def render_slack_digest(payload: DailyReportPayload) -> str:
    return render_user_facing_output(payload, "slack_digest")
