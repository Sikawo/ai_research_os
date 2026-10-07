"""Pure planning helpers for private target-institution monitoring.

Network access and private-overlay writes belong to trusted host connectors.
This module only decides cadence, prepares bounded official-domain fallback
queries, and records scan evidence without removing a configured target or URL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


DEFAULT_FALLBACK_ROLE_TERMS = (
    "faculty recruitment",
    "assistant professor",
    "principal investigator",
    "group leader",
    "investigator",
    "faculty position",
    "tenure track",
    "open rank",
)

_EXCLUDED_ROLE = re.compile(
    r"\b(postdoc(?:toral)?|research assistant|research associate|staff scientist|"
    r"technician|student|phd student|teaching[- ]only|adjunct[- ]only)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_RESEARCH_SCIENTIST = re.compile(
    r"\b(?:research|project) scientist\b", re.IGNORECASE
)
_INDEPENDENCE_EVIDENCE = re.compile(
    r"\b(independent (?:research|lab|laboratory|group|budget|funding)|"
    r"lead (?:a |an |your )?(?:research )?(?:group|lab|laboratory|team)|"
    r"principal investigator|startup (?:package|funds?|support)|"
    r"dedicated lab(?:oratory)? space|recruit (?:your |a )?(?:research )?team)\b",
    re.IGNORECASE,
)
_POSITIVE_ROLE = re.compile(
    r"\b(assistant professor|associate professor|full professor|professor|faculty|"
    r"open rank|tenure[- ]track|principal investigator|investigator|group leader|"
    r"laboratory head|lab head|team leader|programme leader|program leader|"
    r"unit leader|w[123][ -]?professor|senior lecturer|lecturer|reader)\b",
    re.IGNORECASE,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _value(record: Any, *names: str) -> Any:
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if hasattr(record, name):
            return getattr(record, name)
    return None


def target_cadence_days(target: Mapping[str, Any]) -> int:
    """Return explicit cadence, otherwise enforce S=daily and A=weekly."""

    for key in ("interval_days", "scan_frequency_days", "cadence_days"):
        explicit = target.get(key)
        if explicit is None:
            continue
        if isinstance(explicit, bool) or not isinstance(explicit, int) or explicit < 1:
            raise ValueError(f"target {key} must be a positive integer")
        return explicit
    tier = str(target.get("priority_tier") or "").strip().upper()
    if tier == "S":
        return 1
    if tier == "A":
        return 7
    scan_frequency = target.get("scan_frequency")
    if isinstance(scan_frequency, int) and not isinstance(scan_frequency, bool):
        if scan_frequency < 1:
            raise ValueError("target scan_frequency must be a positive integer")
        return scan_frequency
    named = str(scan_frequency or "").strip().casefold()
    if named in {"daily", "high"}:
        return 1
    if named in {"weekly", "low"}:
        return 7
    if named == "medium":
        return 3
    return 7


def target_is_due(
    target: Mapping[str, Any],
    previous_health: Any = None,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether an enabled target is due without mutating its state."""

    if target.get("enabled", True) is not True:
        return False
    last_attempt = _as_datetime(
        _value(previous_health, "last_attempt_at", "last_attempted", "last_success_at", "last_successful")
    )
    if last_attempt is None:
        return True
    current = (now or _utc_now()).astimezone(timezone.utc)
    return current >= last_attempt + timedelta(days=target_cadence_days(target))


def domain_fallback_queries(
    target: Mapping[str, Any],
    *,
    max_queries: int = 12,
) -> tuple[str, ...]:
    """Build a deterministic, bounded set of institution-domain queries."""

    if max_queries < 0:
        raise ValueError("max_queries must not be negative")
    domains = [str(item).strip().casefold() for item in target.get("domains", ()) if str(item).strip()]
    role_terms = [
        str(item).strip()
        for item in target.get("expected_role_terms", DEFAULT_FALLBACK_ROLE_TERMS)
        if str(item).strip()
    ]
    if not role_terms:
        role_terms = list(DEFAULT_FALLBACK_ROLE_TERMS)
    queries = (
        f'site:{domain} "{term}"'
        for domain in domains
        for term in role_terms
    )
    return tuple(dict.fromkeys(queries))[:max_queries]


@dataclass(frozen=True)
class TargetScanPlan:
    target_id: str
    institution: str
    due: bool
    interval_days: int
    official_urls: tuple[str, ...]
    fallback_queries: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_target_scan(
    target: Mapping[str, Any],
    previous_health: Any = None,
    *,
    now: datetime | None = None,
    max_fallback_queries: int = 12,
) -> TargetScanPlan:
    """Prepare official URLs and fallback searches for a trusted host connector."""

    institution = str(target.get("name") or "").strip()
    if not institution:
        raise ValueError("target institution requires name")
    target_id = str(target.get("id") or institution.casefold().replace(" ", "-")).strip()
    urls = tuple(
        dict.fromkeys(
            str(item).strip()
            for key in ("career_urls", "department_urls")
            for item in target.get(key, ())
            if str(item).strip()
        )
    )
    return TargetScanPlan(
        target_id=target_id,
        institution=institution,
        due=target_is_due(target, previous_health, now=now),
        interval_days=target_cadence_days(target),
        official_urls=urls,
        fallback_queries=domain_fallback_queries(
            target, max_queries=max_fallback_queries
        ),
    )


def is_authoritative_target_url(
    url: str,
    target: Mapping[str, Any],
    *,
    official_ats_domains: Iterable[str] = (),
) -> bool:
    """Recognize institution-owned URLs or explicitly allowlisted official ATS hosts."""

    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    configured_urls: list[str] = []
    for key in ("career_urls", "department_urls", "faculty_urls", "lab_urls"):
        values = target.get(key, ())
        if isinstance(values, str):
            values = (values,)
        configured_urls.extend(str(item) for item in values or () if str(item).strip())
    allowed = [
        str(item).casefold().removeprefix("www.")
        for item in (
            *target.get("domains", ()),
            *(urlparse(item).hostname or "" for item in configured_urls),
            *official_ats_domains,
        )
        if str(item).strip()
    ]
    return bool(host and any(host == domain or host.endswith(f".{domain}") for domain in allowed))


def role_disposition(title: str, official_text: str = "") -> str:
    """Return ``include``, ``review``, or ``exclude`` for a direct-monitor hit.

    Ambiguous Research Scientist roles survive for review when official text
    contains credible independence evidence.
    """

    title_text = title or ""
    combined = f"{title_text}\n{official_text or ''}"
    if _AMBIGUOUS_RESEARCH_SCIENTIST.search(title_text):
        return "review" if _INDEPENDENCE_EVIDENCE.search(combined) else "exclude"
    if _EXCLUDED_ROLE.search(title_text):
        return "exclude"
    if _POSITIVE_ROLE.search(title_text):
        return "include"
    return "review"


def build_scan_evidence(
    target: Mapping[str, Any],
    *,
    checked_urls: Iterable[str] = (),
    successful_urls: Iterable[str] = (),
    broken_urls: Iterable[str] = (),
    fallback_queries_used: Iterable[str] = (),
    replacement_urls: Mapping[str, str] | None = None,
    matching_jobs_found: int = 0,
    attempted_at: datetime | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Create durable health evidence while retaining original configured URLs."""

    current = (attempted_at or _utc_now()).astimezone(timezone.utc)
    checked = list(dict.fromkeys(str(item) for item in checked_urls if str(item)))
    successful = list(dict.fromkeys(str(item) for item in successful_urls if str(item)))
    broken = list(dict.fromkeys(str(item) for item in broken_urls if str(item)))
    fallbacks = list(
        dict.fromkeys(str(item) for item in fallback_queries_used if str(item))
    )
    replacements = [
        {"old_url": str(old), "replacement_url": str(new)}
        for old, new in (replacement_urls or {}).items()
        if str(old) and str(new)
    ]
    configured_urls = [
        str(item)
        for key in ("career_urls", "department_urls")
        for item in target.get(key, ())
        if str(item)
    ]
    if not checked:
        status = "not_attempted"
    elif successful and not broken and not error:
        status = "success"
    elif successful:
        status = "partial"
    else:
        status = "failed"
    timestamp = current.isoformat().replace("+00:00", "Z")
    return {
        "target_id": str(target.get("id") or ""),
        "institution": str(target.get("name") or ""),
        "priority_tier": target.get("priority_tier"),
        "last_attempt_at": timestamp,
        "last_success_at": timestamp if successful else None,
        "known_urls_checked": checked,
        "successful_urls": successful,
        "broken_urls": broken,
        "domain_fallback_used": bool(fallbacks),
        "fallback_queries_used": fallbacks,
        "replacement_url_evidence": replacements,
        "matching_jobs_found": max(0, int(matching_jobs_found)),
        "status": status,
        "next_due_at": (
            current + timedelta(days=target_cadence_days(target))
        ).isoformat().replace("+00:00", "Z"),
        "error": error,
        # Evidence of the safety invariant: a broken URL is retained until a
        # private-overlay owner explicitly accepts a replacement.
        "target_retained": True,
        "retained_configured_urls": list(dict.fromkeys(configured_urls)),
    }
