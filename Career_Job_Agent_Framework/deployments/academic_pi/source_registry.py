"""Offline planning primitives for multi-source Academic PI discovery.

The module deliberately performs no network, connector, scheduler, state, or
notification work. Trusted runtimes may consume its plans after a separate
activation review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


HEALTH_STATES = {"not_checked", "healthy", "degraded", "failed", "disabled"}
VERIFICATION_STATES = {"pending", "verified", "rejected"}
ADAPTER_KINDS = {
    "unassigned", "rss", "api", "workday", "interfolio", "taleo", "successfactors",
    "peopleadmin", "pageup", "oracle_hcm", "generic_html", "institution_custom",
}
ADAPTER_SOURCE_MODES = {
    "unassigned": {"discovery_pending"},
    "rss": {"official_rss"},
    "api": {"official_api"},
    "workday": {"common_ats"},
    "interfolio": {"common_ats"},
    "taleo": {"common_ats"},
    "successfactors": {"common_ats"},
    "peopleadmin": {"common_ats"},
    "pageup": {"common_ats"},
    "oracle_hcm": {"common_ats"},
    "generic_html": {"official_page"},
    "institution_custom": {"official_page", "official_api"},
}
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def normalize_source_url(value: str) -> str:
    """Return a stable URL identity while retaining functional query keys."""

    parsed = urlparse(str(value).strip())
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if not parsed.scheme or not host:
        return ""
    port = f":{parsed.port}" if parsed.port else ""
    query = urlencode(sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in _TRACKING_KEYS
    ))
    path = re.sub(r"/{2,}", "/", parsed.path or "/").rstrip("/") or "/"
    return urlunparse((parsed.scheme.casefold(), host + port, path, "", query, ""))


def is_allowlisted_official_url(
    url: str,
    institution_domains: Iterable[str],
    *,
    approved_platform_domains: Iterable[str] = (),
) -> bool:
    """Recognize institution-owned or explicitly approved ATS URLs."""

    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    domains = {
        str(item).casefold().removeprefix("www.")
        for item in (*institution_domains, *approved_platform_domains)
        if str(item).strip()
    }
    return bool(host and any(host == item or host.endswith(f".{item}") for item in domains))


def canonical_listing_key(record: Mapping[str, Any]) -> str:
    """Build a cross-lane dedup key for RSS, official-site, and email hits."""

    institution = _normalized_text(record.get("institution"))
    official_id = _normalized_text(
        record.get("official_job_id") or record.get("requisition_id")
    )
    if institution and official_id:
        material = f"official-id\t{institution}\t{official_id}"
    else:
        normalized_url = normalize_source_url(
            str(record.get("official_url") or record.get("url") or "")
        )
        if normalized_url:
            material = f"official-url\t{normalized_url}"
        else:
            fallback = (
                institution,
                _normalized_text(record.get("title")),
                _normalized_text(record.get("location")),
                _normalized_text(record.get("deadline")),
            )
            if not institution or not fallback[1]:
                raise ValueError("dedup fallback requires institution and title")
            material = "fallback\t" + "\t".join(fallback)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def listing_identity_aliases(record: Mapping[str, Any]) -> frozenset[str]:
    """Return every available strong/fallback identity for cross-lane matching."""

    aliases: set[str] = set()
    institution = _normalized_text(record.get("institution"))
    official_id = _normalized_text(
        record.get("official_job_id") or record.get("requisition_id")
    )
    if institution and official_id:
        aliases.add(f"official-id:{institution}:{official_id}")
    normalized_url = normalize_source_url(
        str(record.get("official_url") or record.get("url") or "")
    )
    if normalized_url:
        aliases.add(f"official-url:{normalized_url}")
    title = _normalized_text(record.get("title"))
    if institution and title:
        aliases.add("fallback:" + "|".join((
            institution,
            title,
            _normalized_text(record.get("location")),
            _normalized_text(record.get("deadline")),
        )))
    if not aliases:
        raise ValueError("listing identity requires official ID, URL, or institution/title")
    return frozenset(aliases)


def listings_match(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Match two records tier-by-tier without bypassing conflicting evidence."""

    left_institution = _normalized_text(left.get("institution"))
    right_institution = _normalized_text(right.get("institution"))
    left_id = _normalized_text(left.get("official_job_id") or left.get("requisition_id"))
    right_id = _normalized_text(right.get("official_job_id") or right.get("requisition_id"))
    if left_id and right_id:
        return left_institution == right_institution and left_id == right_id

    left_url = normalize_source_url(str(left.get("official_url") or left.get("url") or ""))
    right_url = normalize_source_url(str(right.get("official_url") or right.get("url") or ""))
    if left_url and right_url:
        return left_url == right_url

    # A conservative text fallback is allowed only when neither record carries
    # a stronger official ID or URL. One-sided strong evidence remains
    # unresolved instead of being silently collapsed.
    if left_id or right_id or left_url or right_url:
        return False
    return bool(listing_identity_aliases(left) & listing_identity_aliases(right))


@dataclass(frozen=True)
class SourceBatch:
    batch_id: str
    institution_ids: tuple[str, ...]
    cadence_hours: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_source_batches(
    registry: Mapping[str, Any],
    *,
    include_planned: bool = False,
    maximum_batch_size: int = 10,
) -> tuple[SourceBatch, ...]:
    """Group declarative sources into deterministic bounded batches."""

    if maximum_batch_size < 1:
        raise ValueError("maximum_batch_size must be positive")
    issues = registry_issues(registry)
    if issues:
        raise ValueError("invalid source registry: " + "; ".join(issues))
    grouped: dict[str, list[tuple[str, int]]] = {}
    for row in registry.get("institutions", ()):
        if not isinstance(row, Mapping):
            raise ValueError("institution registry rows must be mappings")
        if row.get("enabled") is not True and not include_planned:
            continue
        institution_id = str(row.get("id") or "").strip()
        batch_id = str(row.get("batch_id") or "").strip()
        cadence = row.get("cadence_hours")
        if not institution_id or not batch_id:
            raise ValueError("institution rows require id and batch_id")
        if isinstance(cadence, bool) or not isinstance(cadence, int) or cadence < 1:
            raise ValueError("institution cadence_hours must be a positive integer")
        grouped.setdefault(batch_id, []).append((institution_id, cadence))

    plans: list[SourceBatch] = []
    for batch_id, rows in sorted(grouped.items()):
        if len(rows) > maximum_batch_size:
            raise ValueError(f"batch {batch_id} exceeds maximum size {maximum_batch_size}")
        # A mixed-priority batch runs at its shortest declared cadence so a
        # 48-hour source can never delay a 24-hour source.
        plans.append(SourceBatch(
            batch_id,
            tuple(sorted(institution_id for institution_id, _ in rows)),
            min(cadence for _, cadence in rows),
        ))
    return tuple(plans)


def build_source_health(
    source_id: str,
    *,
    status: str,
    checked_at: datetime | None = None,
    items_seen: int | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Create truthful coverage evidence; retrieval failure is never zero."""

    if status not in HEALTH_STATES - {"not_checked", "disabled"}:
        raise ValueError(f"unsupported attempted source status: {status}")
    if status == "failed":
        if not failure_reason:
            raise ValueError("failed source health requires failure_reason")
        if items_seen is not None:
            raise ValueError("failed retrieval must not report an item count")
    elif items_seen is None or isinstance(items_seen, bool) or items_seen < 0:
        raise ValueError("successful or degraded retrieval requires non-negative items_seen")
    current = (checked_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "source_id": source_id,
        "last_checked": current.isoformat().replace("+00:00", "Z"),
        "source_health": status,
        "items_seen": items_seen,
        "failure_reason": failure_reason,
    }


def registry_issues(registry: Mapping[str, Any]) -> tuple[str, ...]:
    """Return cross-field registry errors that JSON Schema cannot express."""

    issues: list[str] = []
    rows = registry.get("institutions")
    if not isinstance(rows, list):
        return ("institutions must be a list",)
    ids: set[str] = set()
    source_ids: set[str] = set()
    registry_mode = registry.get("registry_mode")
    if registry_mode not in {"offline_only", "pilot", "active"}:
        issues.append("registry_mode must be offline_only, pilot, or active")
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            issues.append(f"institution {index} must be a mapping")
            continue
        institution_id = str(row.get("id") or "")
        if institution_id in ids:
            issues.append(f"duplicate institution id: {institution_id}")
        ids.add(institution_id)
        if row.get("verification_status") not in VERIFICATION_STATES:
            issues.append(f"{institution_id}: invalid verification_status")
        if registry_mode == "offline_only" and row.get("enabled") is True:
            issues.append(f"{institution_id}: offline_only entry cannot be enabled")
        cadence = row.get("cadence_hours")
        tier = row.get("priority_tier")
        if tier in {1, "P1"} and isinstance(cadence, int) and cadence > 24:
            issues.append(f"{institution_id}: priority-1 cadence exceeds 24 hours")
        sources = row.get("sources")
        if not isinstance(sources, list) or not sources:
            issues.append(f"{institution_id}: at least one source is required")
            continue
        for source in sources:
            if not isinstance(source, Mapping):
                issues.append(f"{institution_id}: source must be a mapping")
                continue
            source_id = str(source.get("source_id") or "")
            if source_id in source_ids:
                issues.append(f"duplicate source id: {source_id}")
            source_ids.add(source_id)
            adapter = source.get("adapter")
            mode = source.get("mode")
            if adapter not in ADAPTER_KINDS:
                issues.append(f"{institution_id}: unsupported adapter")
            elif mode not in ADAPTER_SOURCE_MODES.get(str(adapter), set()):
                issues.append(f"{institution_id}: adapter {adapter} is incompatible with {mode}")
            url = source.get("url")
            if mode == "discovery_pending" and url not in {None, ""}:
                issues.append(f"{institution_id}: discovery_pending source must not claim a URL")
            if mode != "discovery_pending" and not url:
                issues.append(f"{institution_id}: configured source requires URL")
            official = bool(url) and is_allowlisted_official_url(
                str(url),
                row.get("official_domains", ()),
                approved_platform_domains=row.get("approved_platform_domains", ()),
            )
            if source.get("verification_status") == "verified" and not official:
                issues.append(f"{institution_id}: verified URL is outside official domains")
            if row.get("enabled") is True and (
                row.get("verification_status") != "verified"
                or source.get("verification_status") != "verified"
                or not official
            ):
                issues.append(f"{institution_id}: enabled source is not fully verified")
    return tuple(issues)
