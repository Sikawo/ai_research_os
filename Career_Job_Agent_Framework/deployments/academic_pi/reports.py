"""Deterministic Markdown reports for daily scans and weekly audits."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from .models import get_value, text_values


_ACTIVE_VERIFICATION = {"verified_open", "verified_reopened"}
_PENDING_VERIFICATION = {
    "verification_pending",
    "verification_failed_transient",
    "verification_failed_persistent",
    "official_source_not_found",
    "manual_review_required",
    "unknown",
}
_TERMINAL_LIFECYCLE = {
    "closed",
    "expired",
    "rejected",
    "withdrawn",
    "closed_expired",
}


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    return None


def _tier(job: Any) -> str:
    return str(get_value(job, "tier", "evaluation.tier", default=""))


def _score(job: Any) -> float:
    try:
        return float(get_value(job, "fit_score", "evaluation.fit_score", default=0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _active(job: Any) -> bool:
    lifecycle = str(get_value(job, "lifecycle_status", "status.lifecycle_status", default="active"))
    verification = str(_enum_value(get_value(job, "verification_status", "status.verification_status", default="")))
    rejected = bool(get_value(job, "rejected", default=False))
    blockers = text_values(
        get_value(job, "hard_blockers", "evaluation.hard_blockers", default=())
    )
    review = str(get_value(job, "manual_review_state", default="")).casefold()
    stale = bool(get_value(job, "verification_stale", "status.stale", default=False))
    return (
        lifecycle.casefold() not in _TERMINAL_LIFECYCLE
        and verification in _ACTIVE_VERIFICATION
        and not rejected
        and not blockers
        and review not in {"blocked", "not_interested", "rejected"}
        and not stale
    )


def _job_key(job: Any) -> str:
    value = get_value(
        job,
        "canonical_id",
        "canonical_job_id",
        "identity.canonical_job_id",
        default=None,
    )
    if value:
        return str(value)
    return "\x1f".join(
        str(get_value(job, path, default=""))
        for path in ("official_url", "institution", "title")
    )


def _pending_verification(job: Any) -> bool:
    if bool(get_value(job, "rejected", default=False)):
        return False
    status = str(
        _enum_value(
            get_value(
                job,
                "verification_status",
                "status.verification_status",
                default="unknown",
            )
        )
    )
    return status in _PENDING_VERIFICATION


def _snapshot_candidate(job: Any) -> bool:
    lifecycle = str(
        get_value(job, "lifecycle_status", "status.lifecycle_status", default="")
    ).casefold()
    review = str(get_value(job, "manual_review_state", default="")).casefold()
    return (
        lifecycle not in _TERMINAL_LIFECYCLE
        and not bool(get_value(job, "rejected", default=False))
        and not text_values(
            get_value(
                job,
                "hard_blockers",
                "evaluation.hard_blockers",
                default=(),
            )
        )
        and review not in {"blocked", "not_interested", "rejected"}
    )


def _pending_line(job: Any, *, stale: bool = False) -> str:
    institution = get_value(
        job, "institution", "identity.institution", default="Unknown institution"
    )
    title = get_value(
        job, "raw_title", "identity.raw_title", "title", default="Unknown title"
    )
    status = str(
        _enum_value(
            get_value(
                job,
                "verification_status",
                "status.verification_status",
                default="unknown",
            )
        )
    )
    if stale and status in _ACTIVE_VERIFICATION:
        status = "not verified active in this run"
    return f"- {institution} — {title}: {status}"


def _application_lines(
    applications: Iterable[Any], *, legacy_submitted: int = 0
) -> list[str]:
    rows = list(applications)
    counts = Counter(
        str(get_value(row, "status", "application.status", default="unknown"))
        .strip()
        .casefold()
        .replace(" ", "_")
        for row in rows
    )
    if legacy_submitted and not counts.get("submitted"):
        counts["submitted"] = int(legacy_submitted)
    lines: list[str] = []
    if counts:
        lines.append(
            "- Canonical application state: "
            + ", ".join(
                f"{status}={count}" for status, count in sorted(counts.items())
            )
            + "."
        )
        submitted = counts.get("submitted", 0)
        if submitted:
            lines.append(
                f"- {submitted} application(s) are recorded as submitted in state; "
                "submission was not performed by this agent."
            )
    else:
        lines.append("- No application activity is recorded in canonical state.")
    lines.append("- Applications submitted by this agent: 0.")
    return lines


def _job_sort(job: Any) -> tuple[int, float, str, str]:
    tier_rank = {"Tier 1": 0, "Tier 2": 1, "Watchlist": 2}.get(_tier(job), 9)
    institution = str(get_value(job, "institution", "identity.institution", default=""))
    title = str(get_value(job, "raw_title", "identity.raw_title", "title", default=""))
    return (tier_rank, -_score(job), institution.casefold(), title.casefold())


def _role_lines(job: Any, *, weekly: bool = False) -> list[str]:
    institution = get_value(job, "institution", "identity.institution", default="Unknown institution")
    department = get_value(job, "department", "identity.department", default=None)
    title = get_value(job, "raw_title", "identity.raw_title", "title", default="Unknown title")
    city = get_value(job, "city", "identity.city", default=None)
    country = get_value(job, "country", "identity.country", default=None)
    explicit_location = get_value(job, "location", "identity.location", default=None)
    if city:
        location = ", ".join(str(value) for value in (city, country) if value)
    elif explicit_location:
        location = str(explicit_location)
    elif country:
        location = str(country)
    else:
        location = "Unknown"
    deadline = get_value(job, "deadline", "dates.deadline", default="Unknown")
    tier = _tier(job) or "Unclassified"
    score = _score(job)
    official_url = get_value(job, "official_url", "urls.official_url", default=None)
    verified = get_value(job, "last_verified", "status.last_verified", default="Unknown")
    matches = text_values(get_value(job, "strongest_matches", "evaluation.strongest_matches", default=()))
    gaps = text_values(get_value(job, "meaningful_gaps", "evaluation.meaningful_gaps", default=()))
    blockers = text_values(
        get_value(job, "hard_blockers", "evaluation.hard_blockers", default=())
    )
    independence = get_value(job, "independence_class", "independence.class", default="unknown")
    fit_confidence = get_value(
        job, "fit_confidence", "evaluation.fit_confidence", default=None
    )
    verification_confidence = get_value(
        job,
        "verification_confidence",
        "status.verification_confidence",
        default=None,
    )
    opportunity = get_value(
        job,
        "opportunity_quality",
        "evaluation.opportunity_quality",
        default=None,
    )
    opportunity_notes = text_values(
        get_value(job, "opportunity_notes", "evaluation.opportunity_notes", default=())
    )
    qol = get_value(job, "qol_fit", "evaluation.qol_fit", default=None)
    qol_notes = text_values(
        get_value(job, "qol_notes", "evaluation.qol_notes", default=())
    )
    eligibility = get_value(
        job, "eligibility_status", "evaluation.eligibility_status", default=None
    )

    def display(value: Any, notes: tuple[str, ...], *, unknown: str) -> str:
        if value not in (None, "", [], {}):
            return str(value)
        if notes:
            return notes[0]
        return unknown

    eligibility_text = (
        str(eligibility)
        if eligibility not in (None, "", [], {})
        else f"blocked: {blockers[0]}"
        if blockers
        else "not established; no confirmed blocker"
    )
    fit_confidence_text = (
        str(fit_confidence) if fit_confidence is not None else "unknown"
    )
    verification_confidence_text = (
        str(verification_confidence)
        if verification_confidence is not None
        else "unknown"
    )

    heading = f"- **{institution} — {title}**"
    if department:
        heading += f" ({department})"
    lines = [heading, f"  - Location: {location}; deadline: {deadline}; {tier}; fit: {score:.1f}"]
    if matches:
        lines.append(f"  - Strongest fit: {matches[0]}")
    if gaps:
        lines.append(f"  - Main gap: {gaps[0]}")
    lines.append(f"  - Independence: {independence}; verified: {verified}")
    lines.extend(
        [
            f"  - Scientific fit: {score:.1f} ({tier}); fit confidence: {fit_confidence_text}",
            "  - Opportunity quality: "
            + display(opportunity, opportunity_notes, unknown="not evaluated"),
            "  - QOL fit: " + display(qol, qol_notes, unknown="not evaluated"),
            f"  - Eligibility: {eligibility_text}",
            f"  - Verification confidence: {verification_confidence_text}",
        ]
    )
    if weekly:
        required = text_values(get_value(job, "required_documents", "requirements.required_documents", default=()))
        letters = get_value(job, "reference_letter_policy", "requirements.reference_letter_policy", default="Unknown")
        application = get_value(job, "application.status", "application_status", default="not_started")
        why_now = get_value(job, "why_now", "evaluation.why_now", default=None)
        lines.extend(
            [
                f"  - Fit: {score:.1f} ({tier})",
                f"  - Why now: {why_now or 'Review fit, deadline, and readiness.'}",
                f"  - Strongest scientific alignment: {matches[0] if matches else 'Not established'}",
                f"  - Most important gap: {gaps[0] if gaps else 'None identified'}",
                f"  - Independence status: {independence}",
                f"  - Deadline: {deadline}",
                f"  - Required documents: {', '.join(required) if required else 'Unknown'}",
                f"  - Letters: {letters}",
                f"  - Verification status: {get_value(job, 'verification_status', 'status.verification_status', default='unknown')}",
                f"  - Application status: {application}",
            ]
        )
    if official_url:
        lines.append(f"  - Official URL: {official_url}")
    return lines


def _section(title: str, items: Sequence[str], empty: str = "None.") -> list[str]:
    return [f"## {title}", *(items or [empty]), ""]


def _deadline_action_line(item: Any) -> str:
    identifier = get_value(
        item,
        "canonical_id",
        "canonical_job_id",
        "identity.canonical_job_id",
        "job_id",
        default="unknown-job",
    )
    institution = get_value(
        item, "institution", "identity.institution", default="Unknown institution"
    )
    title = get_value(
        item, "title", "raw_title", "identity.raw_title", default="Unknown title"
    )
    deadline = get_value(item, "deadline", "dates.deadline", default="Unknown")
    return f"- Deadline action: {identifier} — {institution} — {title} — {deadline}"


def _is_email_error(error: Any) -> bool:
    """Return whether an operational error belongs in the email backlog."""

    category = str(get_value(error, "category", default="")).casefold()
    connector = str(get_value(error, "connector", default="")).casefold()
    return bool(
        get_value(error, "message_id", default=None)
        or connector == "email"
        or category == "email_label_error"
    )


def _is_rss_error(error: Any) -> bool:
    """Return whether an error came from a feed, regardless of category order."""

    values = (
        get_value(error, "category", default=""),
        get_value(error, "source_id", default=""),
        get_value(error, "connector", default=""),
    )
    folded = " ".join(str(value).casefold() for value in values)
    return bool(
        "rss" in folded
        or "academic_jobs_online" in folded
        or get_value(error, "feed_url", default=None)
    )


def _render_jobs(jobs: Iterable[Any], *, weekly: bool = False) -> list[str]:
    lines: list[str] = []
    for job in sorted(jobs, key=_job_sort):
        lines.extend(_role_lines(job, weekly=weekly))
    return lines


def _qol_lines(jobs: Iterable[Any]) -> list[str]:
    lines: list[str] = []
    for job in sorted(jobs, key=_job_sort):
        if _tier(job) not in {"Tier 1", "Tier 2"}:
            continue
        institution = get_value(job, "institution", "identity.institution", default="Unknown")
        title = get_value(job, "title", "raw_title", "identity.raw_title", default="Unknown")
        qol = get_value(job, "qol_assessment", default={})
        qol = qol if isinstance(qol, Mapping) else {}
        compensation = qol.get("compensation", {}) if isinstance(qol.get("compensation"), Mapping) else {}
        take_home = qol.get("take_home", {}) if isinstance(qol.get("take_home"), Mapping) else {}
        housing = qol.get("housing", {}) if isinstance(qol.get("housing"), Mapping) else {}
        childcare = qol.get("childcare", {}) if isinstance(qol.get("childcare"), Mapping) else {}
        verdicts = qol.get("verdicts", {}) if isinstance(qol.get("verdicts"), Mapping) else {}
        scenarios = qol.get("scenarios", []) if isinstance(qol.get("scenarios"), list) else []
        position = get_value(job, "position", default={})
        position = position if isinstance(position, Mapping) else {}
        salary_min = compensation.get("salary_min", position.get("salary_min"))
        salary_max = compensation.get("salary_max", position.get("salary_max"))
        currency = compensation.get("currency", position.get("salary_currency"))
        basis = compensation.get("basis", position.get("salary_basis"))
        if salary_min is None and salary_max is None:
            salary_text = "not stated on verified official source"
        else:
            salary_text = f"{salary_min if salary_min is not None else '?'}–{salary_max if salary_max is not None else '?'} {currency or 'currency unknown'}"
        monthly_net = take_home.get("monthly_net_mid")
        housing_range = housing.get("two_bedroom_range") or housing.get("one_bedroom_range")
        childcare_range = childcare.get("monthly_cost_range")
        surplus = next(
            (
                scenario.get("estimated_monthly_surplus")
                for scenario in scenarios
                if isinstance(scenario, Mapping)
                and scenario.get("estimated_monthly_surplus") is not None
            ),
            None,
        )
        unknowns = qol.get("unknowns", []) if isinstance(qol.get("unknowns"), list) else []
        lines.extend(
            [
                f"- **{institution} — {title}**",
                f"  - Salary: {salary_text}; basis: {basis or 'unknown'}",
                f"  - Estimated monthly take-home: {monthly_net if monthly_net is not None else 'unknown'} {currency or ''}".rstrip(),
                f"  - Housing range: {housing_range if housing_range is not None else 'unknown'}; childcare: {childcare_range if childcare_range is not None else 'unknown'}",
                f"  - Monthly surplus/deficit: {surplus if surplus is not None else 'unknown'}",
                f"  - Economic QOL: {verdicts.get('economic_qol') or 'pending/unknown'}; confidence: {qol.get('confidence') if qol.get('confidence') is not None else 'unknown'}",
                f"  - Major unknowns: {', '.join(str(item) for item in unknowns) if unknowns else 'none recorded'}",
            ]
        )
    return lines


def render_daily_report(
    jobs: Iterable[Any] = (),
    *,
    current_active_jobs: Iterable[Any] | None = None,
    new_jobs: Iterable[Any] = (),
    material_changes: Iterable[Any] = (),
    verification_errors: Iterable[Any] = (),
    coverage: Iterable[Any] = (),
    deadline_alerts: Iterable[Any] = (),
    metrics: Mapping[str, Any] | None = None,
    applications: Iterable[Any] = (),
    application_submissions: int = 0,
    report_date: date | None = None,
) -> str:
    """Render the required daily report without claiming unconfirmed delivery."""

    all_jobs = list(jobs)
    snapshot_supplied = current_active_jobs is not None
    snapshot_jobs = (
        list(current_active_jobs) if current_active_jobs is not None else all_jobs
    )
    new = list(new_jobs)
    tier1_new = [job for job in new if _tier(job) == "Tier 1" and _active(job)]
    tier2_new = [job for job in new if _tier(job) == "Tier 2" and _active(job)]
    active1 = [job for job in snapshot_jobs if _tier(job) == "Tier 1" and _active(job)]
    active2 = [job for job in snapshot_jobs if _tier(job) == "Tier 2" and _active(job)]
    changes = list(material_changes)
    deadlines = list(deadline_alerts)
    errors = list(verification_errors)
    coverage_rows = list(coverage)
    today = report_date or datetime.now(timezone.utc).date()

    action_lines: list[str] = []
    action_lines.extend(_deadline_action_line(item) for item in deadlines)
    action_lines.extend(f"- New Tier 1: {get_value(job, 'institution', 'identity.institution', default='Unknown')} — {get_value(job, 'raw_title', 'identity.raw_title', default='Unknown')}" for job in tier1_new)
    action_lines.extend(f"- Material change: {get_value(change, 'field', default='job update')}" for change in changes)

    lines = [
        f"# Academic PI Job Agent — Daily ({today.isoformat()})",
        "",
        "Scientific Fit, QOL Fit, Eligibility, opportunity quality, and confidence are reported separately.",
        "",
    ]
    lines.extend(_section("Action Required", action_lines))
    if not tier1_new and not tier2_new:
        lines.extend(["[NO MATCH] No new verified Tier 1 or Tier 2 roles today.", ""])
    lines.extend(_section("New Tier 1", _render_jobs(tier1_new)))
    lines.extend(_section("New Tier 2", _render_jobs(tier2_new)))
    change_lines = [
        f"- {get_value(change, 'field', default='field')}: "
        f"{get_value(change, 'old_value', default='unknown')} → "
        f"{get_value(change, 'new_value', default='unknown')}"
        for change in changes
    ]
    lines.extend(_section("Material Changes", change_lines))
    lines.extend(_section("CURRENT ACTIVE TIER 1", _render_jobs(active1)))
    lines.extend(_section("CURRENT ACTIVE TIER 2", _render_jobs(active2)))
    lines.extend(_section("COMPENSATION & QOL", _qol_lines((*active1, *active2))))
    active_keys = {_job_key(job) for job in (*active1, *active2)}
    pending_jobs = [job for job in all_jobs if _pending_verification(job)]
    if snapshot_supplied:
        pending_jobs.extend(
            job
            for job in all_jobs
            if _tier(job) in {"Tier 1", "Tier 2"}
            and _snapshot_candidate(job)
            and _job_key(job) not in active_keys
        )
    unique_pending = {
        _job_key(job): job for job in pending_jobs
    }
    error_lines = [
        f"- {get_value(error, 'message', 'error', default=str(error))}"
        for error in errors
    ]
    error_lines.extend(
        _pending_line(
            job,
            stale=snapshot_supplied and _job_key(job) not in active_keys,
        )
        for job in unique_pending.values()
    )
    lines.extend(_section("Verification Pending / Errors", error_lines))
    email_coverage = []
    rss_coverage = []
    target_coverage = []
    for row in coverage_rows:
        source_id = str(get_value(row, "source_id", default=""))
        line = (
            f"- {source_id or get_value(row, 'institution', default='source')}: "
            f"{get_value(row, 'status', default='unknown')}"
        )
        if get_value(row, "institution", default=None) is not None:
            target_coverage.append(line)
        elif source_id == "email_alert" or source_id.startswith("email"):
            email_coverage.append(line)
        elif "rss" in source_id or source_id == "academic_jobs_online":
            rss_coverage.append(line)
    coverage_lines = [
        f"- {get_value(row, 'source_id', 'institution', default='source')}: "
        f"{get_value(row, 'status', default='unknown')}"
        for row in coverage_rows
    ]
    if metrics:
        coverage_lines.append(
            "- Run metrics: " + ", ".join(f"{key}={value}" for key, value in sorted(metrics.items()))
        )
    lines.extend(_section("DISCOVERY COVERAGE", coverage_lines))
    lines.extend(_section("Email alerts", email_coverage))
    lines.extend(_section("RSS feeds", rss_coverage))
    lines.extend(_section("Target institutions", target_coverage))
    email_errors = [error for error in errors if _is_email_error(error)]
    rss_errors = [error for error in errors if _is_rss_error(error)]
    target_errors = [
        error for error in errors if get_value(error, "institution", default=None)
    ]
    lines.extend(_section("EMAIL BACKLOG / PARSE ERRORS", [f"- {get_value(error, 'message', default=str(error))}" for error in email_errors]))
    lines.extend(_section("RSS ERRORS", [f"- {get_value(error, 'message', default=str(error))}" for error in rss_errors]))
    lines.extend(_section("TARGET URL ERRORS", [f"- {get_value(error, 'message', default=str(error))}" for error in target_errors]))
    lines.extend(_section("BLIND SPOTS", ["- Live connector coverage not claimed unless confirmed above."]))
    lines.extend(
        _section(
            "Applications",
            _application_lines(
                applications, legacy_submitted=application_submissions
            ),
        )
    )
    return "\n".join(lines).rstrip() + "\n"


def _deadline_buckets(jobs: Iterable[Any], today: date) -> dict[str, list[Any]]:
    buckets = {"<= 7 days": [], "8–14 days": [], "15–30 days": [], "> 30 days / rolling / unknown": []}
    for job in jobs:
        deadline = _as_date(get_value(job, "deadline", "dates.deadline", default=None))
        kind = str(get_value(job, "deadline_type", "dates.deadline_type", default="unknown"))
        if not deadline or kind in {"rolling", "unknown"}:
            buckets["> 30 days / rolling / unknown"].append(job)
            continue
        days = (deadline - today).days
        if days <= 7:
            buckets["<= 7 days"].append(job)
        elif days <= 14:
            buckets["8–14 days"].append(job)
        elif days <= 30:
            buckets["15–30 days"].append(job)
        else:
            buckets["> 30 days / rolling / unknown"].append(job)
    return buckets


def render_weekly_report(
    jobs: Iterable[Any] = (),
    *,
    current_active_jobs: Iterable[Any] | None = None,
    new_jobs: Iterable[Any] = (),
    material_changes: Iterable[Any] = (),
    source_coverage: Iterable[Any] = (),
    institution_coverage: Iterable[Any] = (),
    email_backlog: Iterable[Any] = (),
    errors: Iterable[Any] = (),
    closed_or_reopened: Iterable[Any] = (),
    applications: Iterable[Any] = (),
    blind_spots: Iterable[str] = (),
    metrics: Mapping[str, Any] | None = None,
    report_date: date | None = None,
) -> str:
    """Render a decision-oriented weekly audit with explicit blind spots."""

    today = report_date or datetime.now(timezone.utc).date()
    all_jobs = list(jobs)
    snapshot_supplied = current_active_jobs is not None
    snapshot_jobs = (
        list(current_active_jobs) if current_active_jobs is not None else all_jobs
    )
    source_rows = list(source_coverage)
    institution_rows = list(institution_coverage)
    error_rows = list(errors)
    active1 = [job for job in snapshot_jobs if _tier(job) == "Tier 1" and _active(job)]
    active2 = [job for job in snapshot_jobs if _tier(job) == "Tier 2" and _active(job)]
    active = active1 + active2
    active_keys = {_job_key(job) for job in active}
    pending = [
        job for job in all_jobs
        if not bool(get_value(job, "rejected", default=False))
        and (
            _pending_verification(job)
            or str(get_value(job, "independence_class", "independence.class", default="")) == "ambiguous"
        )
    ]
    if snapshot_supplied:
        pending.extend(
            job
            for job in all_jobs
            if _tier(job) in {"Tier 1", "Tier 2"}
            and _snapshot_candidate(job)
            and _job_key(job) not in active_keys
        )
    pending = list({_job_key(job): job for job in pending}.values())
    deadlines = _deadline_buckets(active, today)

    lines = [
        f"# Academic PI Job Agent — Weekly ({today.isoformat()})",
        "",
        "Scientific Fit, QOL Fit, Eligibility, opportunity quality, and confidence are reported separately.",
        "",
    ]
    lines.extend(_section("Top roles to act on this week", _render_jobs(sorted(active, key=_job_sort)[:5], weekly=True)))
    lines.extend(_section("CURRENT ACTIVE TIER 1", _render_jobs(active1, weekly=True)))
    lines.extend(_section("CURRENT ACTIVE TIER 2", _render_jobs(active2, weekly=True)))
    lines.extend(_section("COMPENSATION & QOL COMPARISON", _qol_lines(active)))
    lines.extend(_section("NEW THIS WEEK", _render_jobs(list(new_jobs), weekly=True)))
    change_lines = [
        f"- {get_value(change, 'field', default='field')}: "
        f"{get_value(change, 'old_value', default='unknown')} → {get_value(change, 'new_value', default='unknown')}"
        for change in material_changes
    ]
    lines.extend(_section("MATERIAL CHANGES", change_lines))
    lines.extend(["## DEADLINES", ""])
    for name, rows in deadlines.items():
        lines.extend([f"### {name}", *(_render_jobs(rows) or ["None."]), ""])
    lines.extend(_section("VERIFY / REVIEW", _render_jobs(pending, weekly=True)))

    source_lines = [
        f"- {get_value(row, 'source_id', default='source')}: {get_value(row, 'status', default='unknown')}"
        for row in source_rows
    ]
    institution_lines = [
        f"- {get_value(row, 'institution', default='institution')}: {get_value(row, 'status', default='unknown')}"
        for row in institution_rows
    ]
    lines.extend(_section("SOURCE COVERAGE AUDIT", source_lines))
    lines.extend(_section("TARGET-INSTITUTION COVERAGE AUDIT", institution_lines))
    lines.extend(_section("BLIND-SPOT AUDIT", list(blind_spots)))
    email_errors = [error for error in error_rows if _is_email_error(error)]
    operational_errors = [error for error in error_rows if not _is_email_error(error)]
    backlog_lines = [f"- {get_value(item, 'message_id', default=str(item))}" for item in email_backlog]
    backlog_lines.extend(
        f"- Error: {get_value(error, 'message', default=str(error))}"
        for error in email_errors
    )
    lines.extend(_section("EMAIL BACKLOG / PARSE ERRORS", backlog_lines))
    rss_errors = [error for error in error_rows if _is_rss_error(error)]
    lines.extend(
        _section(
            "RSS ERRORS",
            [f"- {get_value(error, 'message', default=str(error))}" for error in rss_errors],
        )
    )
    stale_qol = [
        job for job in active
        if str(get_value(job, "qol_assessment.status", default="pending"))
        not in {"complete"}
    ]
    lines.extend(
        _section(
            "STALE QOL / COMPENSATION ASSUMPTIONS",
            [
                f"- {get_value(job, 'institution', default='Unknown')} — "
                f"{get_value(job, 'title', 'raw_title', default='Unknown')}: "
                f"{get_value(job, 'qol_assessment.status', default='pending/unknown')}"
                for job in stale_qol
            ],
        )
    )
    lines.extend(
        _section(
            "RUN ERRORS",
            [
                f"- {get_value(error, 'category', default='unknown')}: "
                f"{get_value(error, 'message', default=str(error))}"
                for error in operational_errors
            ],
        )
    )
    lines.extend(_section("CLOSED / EXPIRED / REOPENED THIS WEEK", _render_jobs(list(closed_or_reopened), weekly=True)))
    decision_jobs = [
        job
        for job in all_jobs
        if str(get_value(job, "manual_review_state", default=""))
        in {"needs_answers", "needs_review", "verification_pending"}
    ]
    close_soon = deadlines["<= 7 days"] + deadlines["8–14 days"]
    gap_lines = [
        f"- Source {get_value(row, 'source_id', default='unknown')}: {get_value(row, 'status', default='unknown')}"
        for row in source_rows
        if str(get_value(row, "status", default="unknown")) != "success"
    ]
    gap_lines.extend(
        f"- Institution {get_value(row, 'institution', default='unknown')}: {get_value(row, 'status', default='unknown')}"
        for row in institution_rows
        if str(get_value(row, "status", default="unknown")) != "success"
    )
    lines.extend(_section("Roles needing a user decision", _render_jobs(decision_jobs, weekly=True)))
    lines.extend(_section("Roles likely to close soon", _render_jobs(close_soon, weekly=True)))
    lines.extend(_section("Coverage gaps", gap_lines))
    lines.extend(_section("APPLICATION STATUS", _application_lines(applications)))
    if metrics:
        lines.extend(_section("RUN METRICS", [f"- {key}: {value}" for key, value in sorted(metrics.items())]))
    return "\n".join(lines).rstrip() + "\n"
