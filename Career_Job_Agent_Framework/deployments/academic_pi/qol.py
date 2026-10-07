"""Pure salary and quality-of-life assessment helpers.

These helpers never fetch tax, housing, school, or routing data. Trusted host
connectors supply dated evidence and explicit assumptions; this module keeps
unknowns visible, separates employer retirement contributions from spendable
salary, and computes only transparent budget arithmetic.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping


ACTIONABLE_TIERS = {"tier 1", "tier 2", "tier_1", "tier_2", "tier1", "tier2"}
VERIFIED_OPEN = {"verified_open", "verified_reopened"}
MATERIAL_SALARY_PATHS = (
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_basis",
    "salary_source_url",
    "salary_is_estimate",
)
MATERIAL_LOCATION_PATHS = ("location", "country", "city", "region", "worksite")
SCENARIO_COST_FIELDS = (
    "rent",
    "childcare",
    "education",
    "food",
    "healthcare",
    "transport",
    "utilities_internet",
    "other_needs",
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


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


def _get(record: Any, *paths: str, default: Any = None) -> Any:
    for path in paths:
        current = record
        found = True
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                extra = getattr(current, "extra", None)
                if isinstance(extra, Mapping) and part in extra:
                    current = extra[part]
                else:
                    found = False
                    break
        if found:
            return current
    return default


def requires_full_qol(job: Any) -> bool:
    """Tier 1/2 triggers QOL only after authoritative open verification."""

    tier = _enum_text(_get(job, "tier", "evaluation.tier")).strip().casefold()
    status = _enum_text(
        _get(job, "verification_status", "status.verification_status")
    ).strip().casefold()
    return tier in ACTIONABLE_TIERS and status in VERIFIED_OPEN


def normalize_compensation(
    compensation: Mapping[str, Any],
    *,
    country: str | None = None,
) -> dict[str, Any]:
    """Normalize salary without annualizing or treating employer super as cash.

    If an Australian total package includes super, an explicit super amount or
    rate is required to separate base salary. Otherwise the spendable range is
    left unknown rather than guessed.
    """

    notes = [str(item) for item in compensation.get("notes", ()) if str(item)]
    unknowns: list[str] = []
    salary_min = _number(compensation.get("salary_min"))
    salary_max = _number(compensation.get("salary_max"))
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        salary_min, salary_max = salary_max, salary_min
        notes.append("Salary bounds were reordered during normalization.")
    retirement = compensation.get("employer_retirement_or_super")
    retirement = retirement if isinstance(retirement, Mapping) else {}
    included_super = bool(
        compensation.get("salary_includes_super")
        or compensation.get("includes_employer_super")
        or compensation.get("employer_super_included")
        or retirement.get("included_in_package")
        or retirement.get("includes_employer_super")
    )
    super_rate = _number(
        compensation.get("employer_super_rate", retirement.get("rate"))
    )
    if super_rate is not None and super_rate > 1:
        super_rate /= 100.0
    super_min = _number(
        compensation.get("employer_super_min", retirement.get("amount_min"))
    )
    super_max = _number(
        compensation.get("employer_super_max", retirement.get("amount_max"))
    )
    country_code = str(country or compensation.get("country") or "").upper()
    if country_code in {"AU", "AUS", "AUSTRALIA"} and included_super:
        if super_min is not None or super_max is not None:
            if salary_min is not None:
                salary_min -= super_min if super_min is not None else super_max or 0.0
            if salary_max is not None:
                salary_max -= super_max if super_max is not None else super_min or 0.0
        elif super_rate is not None and super_rate >= 0:
            divisor = 1.0 + super_rate
            salary_min = salary_min / divisor if salary_min is not None else None
            salary_max = salary_max / divisor if salary_max is not None else None
        else:
            salary_min = None
            salary_max = None
            unknowns.append(
                "Australian package includes employer super, but its amount or rate is unknown."
            )
        notes.append("Employer super is excluded from spendable gross salary.")
    salary_mid = (
        (salary_min + salary_max) / 2
        if salary_min is not None and salary_max is not None
        else salary_min if salary_min is not None else salary_max
    )
    if salary_min is None and salary_max is None and not unknowns:
        unknowns.append("Salary is not stated on the verified source.")
    return {
        "salary_min": salary_min,
        "salary_mid": salary_mid,
        "salary_max": salary_max,
        "currency": compensation.get("currency", compensation.get("salary_currency")),
        "period": compensation.get("period", compensation.get("salary_period")),
        "basis": compensation.get("basis", compensation.get("salary_basis")),
        "official": compensation.get("official"),
        "evidence_url": compensation.get(
            "source_url",
            compensation.get("salary_source_url", compensation.get("salary_evidence_url")),
        ),
        "source_date": compensation.get("source_date"),
        "employer_retirement_or_super": compensation.get(
            "employer_retirement_or_super",
            {
                "included_in_package": included_super,
                "rate": super_rate,
                "amount_min": super_min,
                "amount_max": super_max,
            },
        ),
        "notes": list(dict.fromkeys(notes)),
        "unknowns": list(dict.fromkeys(unknowns)),
    }


def normalize_take_home(take_home: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve declared assumptions and derive monthly values only from net annual values."""

    result = copy.deepcopy(dict(take_home))
    for suffix in ("min", "mid", "max"):
        annual_key = f"annual_net_{suffix}"
        monthly_key = f"monthly_net_{suffix}"
        annual = _number(result.get(annual_key))
        monthly = _number(result.get(monthly_key))
        result[annual_key] = annual
        result[monthly_key] = monthly if monthly is not None else (
            annual / 12.0 if annual is not None else None
        )
    result.setdefault("filing_assumption", None)
    result.setdefault("tax_year", None)
    result.setdefault("currency", None)
    result.setdefault("estimate_method", None)
    result.setdefault("confidence", None)
    result["sources"] = list(result.get("sources", ()) or ())
    return result


def build_budget_scenario(
    name: str,
    *,
    gross_salary: float | None,
    estimated_monthly_take_home: float | None,
    costs: Mapping[str, Any],
    confidence: float | None = None,
) -> dict[str, Any]:
    """Compute surplus only when every required monthly cost is known."""

    take_home = _number(estimated_monthly_take_home)
    normalized_costs = {field: _number(costs.get(field)) for field in SCENARIO_COST_FIELDS}
    unknowns = [field for field, value in normalized_costs.items() if value is None]
    if take_home is None:
        unknowns.insert(0, "estimated_monthly_take_home")
    surplus = None
    if not unknowns and take_home is not None:
        surplus = take_home - sum(value or 0.0 for value in normalized_costs.values())
    return {
        "name": name,
        "gross_salary": _number(gross_salary),
        "estimated_monthly_take_home": take_home,
        **normalized_costs,
        "estimated_monthly_surplus": surplus,
        "confidence": confidence,
        "unknowns": unknowns,
    }


def unknown_qol_assessment(*reasons: str) -> dict[str, Any]:
    """Return an explicit unknown assessment without fabricated precision."""

    unknowns = [reason for reason in reasons if reason]
    return {
        "status": "unknown",
        "score": None,
        "confidence": None,
        "assessed_at": None,
        "compensation": normalize_compensation({}),
        "take_home": normalize_take_home({}),
        "housing": {},
        "childcare": {},
        "education": {},
        "transport": {},
        "scenarios": [],
        "verdicts": {
            "economic_qol": None,
            "education_qol": None,
            "commute_qol": None,
            "overall_qol": None,
        },
        "notes": [],
        "unknowns": list(dict.fromkeys(unknowns or ["QOL evidence is insufficient."])),
        "sources": [],
    }


def build_qol_assessment(
    *,
    compensation: Mapping[str, Any],
    take_home: Mapping[str, Any],
    country: str | None = None,
    housing: Mapping[str, Any] | None = None,
    childcare: Mapping[str, Any] | None = None,
    education: Mapping[str, Any] | None = None,
    transport: Mapping[str, Any] | None = None,
    scenarios: Iterable[Mapping[str, Any]] = (),
    verdicts: Mapping[str, Any] | None = None,
    notes: Iterable[str] = (),
    sources: Iterable[Any] = (),
    assessed_at: datetime | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Assemble an assessment and mark incomplete evidence pending, not complete."""

    normalized_comp = normalize_compensation(compensation, country=country)
    normalized_take_home = normalize_take_home(take_home)
    scenario_rows = [copy.deepcopy(dict(item)) for item in scenarios]
    unknowns = list(normalized_comp.get("unknowns", ()))
    if normalized_take_home.get("monthly_net_mid") is None:
        unknowns.append("Estimated take-home is unknown.")
    evidence_layers = {
        "housing": housing,
        "childcare": childcare,
        "education": education,
        "transport": transport,
    }
    for layer_name, layer in evidence_layers.items():
        if not isinstance(layer, Mapping) or not layer:
            unknowns.append(f"{layer_name.capitalize()} evidence is unavailable.")
    if not scenario_rows:
        unknowns.append("No complete monthly budget scenario is available.")
    else:
        for row in scenario_rows:
            unknowns.extend(
                f"{row.get('name', 'scenario')}: {item} is unknown"
                for item in row.get("unknowns", ())
            )
    source_rows = copy.deepcopy(list(sources))
    if not source_rows:
        unknowns.append("QOL evidence sources are unavailable.")
    complete = not unknowns and all(
        row.get("estimated_monthly_surplus") is not None for row in scenario_rows
    )
    timestamp = (assessed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "status": "complete" if complete else "pending",
        "score": None,
        "confidence": confidence,
        "assessed_at": timestamp.isoformat().replace("+00:00", "Z"),
        "compensation": normalized_comp,
        "take_home": normalized_take_home,
        "housing": copy.deepcopy(dict(housing or {})),
        "childcare": copy.deepcopy(dict(childcare or {})),
        "education": copy.deepcopy(dict(education or {})),
        "transport": copy.deepcopy(dict(transport or {})),
        "scenarios": scenario_rows,
        "verdicts": {
            "economic_qol": None,
            "education_qol": None,
            "commute_qol": None,
            "overall_qol": None,
            **copy.deepcopy(dict(verdicts or {})),
        },
        "notes": list(dict.fromkeys(str(item) for item in notes if str(item))),
        "unknowns": list(dict.fromkeys(unknowns)),
        "sources": source_rows,
    }


def attach_qol_assessment(job: Mapping[str, Any], assessment: Mapping[str, Any]) -> dict[str, Any]:
    """Attach top-level QOL data without changing scientific evaluation or tier."""

    result = copy.deepcopy(dict(job))
    result["qol_assessment"] = copy.deepcopy(dict(assessment))
    return result


def invalidate_qol_assessment(
    assessment: Mapping[str, Any] | None,
    *reasons: str,
) -> dict[str, Any]:
    """Preserve evidence while marking affected QOL layers pending refresh."""

    result = copy.deepcopy(dict(assessment or unknown_qol_assessment()))
    result["status"] = "pending"
    result["score"] = None
    result["confidence"] = None
    result["unknowns"] = list(
        dict.fromkeys(
            [str(item) for item in result.get("unknowns", ()) if str(item)]
            + [reason for reason in reasons if reason]
        )
    )
    return result


def qol_refresh_reasons(
    job: Any,
    *,
    previous_job: Any = None,
    now: datetime | None = None,
    stale_after_days: int = 30,
) -> tuple[str, ...]:
    """Return deterministic refresh reasons for an actionable job."""

    if not requires_full_qol(job):
        return ()
    reasons: list[str] = []
    assessment = _get(job, "qol_assessment", default=None)
    if not isinstance(assessment, Mapping):
        reasons.append("qol_missing")
    else:
        assessed = _as_datetime(assessment.get("assessed_at"))
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if assessed is None:
            reasons.append("qol_unassessed")
        elif current >= assessed + timedelta(days=max(0, stale_after_days)):
            reasons.append("qol_stale")
    if previous_job is not None:
        if any(
            _get(job, f"position.{name}", name) != _get(previous_job, f"position.{name}", name)
            for name in MATERIAL_SALARY_PATHS
        ):
            reasons.append("salary_material_change")
        if any(
            _get(job, f"identity.{name}", name) != _get(previous_job, f"identity.{name}", name)
            for name in MATERIAL_LOCATION_PATHS
        ):
            reasons.append("location_material_change")
    return tuple(dict.fromkeys(reasons))
