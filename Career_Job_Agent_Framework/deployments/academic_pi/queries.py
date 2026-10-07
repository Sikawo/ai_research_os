"""Budgeted, rotating academic search query generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .models import AcademicQuery, get_value, text_values


DEFAULT_ROLE_TERMS = {
    "US": (
        "assistant professor",
        "tenure-track faculty",
        "faculty position",
        "open rank professor",
        "investigator",
    ),
    "EUROPE": (
        "group leader",
        "junior group leader",
        "independent group leader",
        "assistant professor",
        "tenure track",
        "lecturer",
        "W1 professor",
        "investigator",
    ),
}


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return list(value.values())
    if isinstance(value, (str, bytes)):
        return [value]
    return list(value)


def _norm_query(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().replace('"', "")).strip()


def _ranked_terms(profile: Mapping[str, Any]) -> list[tuple[str, int]]:
    identity = profile.get("scientific_identity", {})
    departments = profile.get("departments", {})
    buckets = (
        (identity.get("primary_fields", ()), 100),
        (identity.get("secondary_fields", ()), 85),
        (identity.get("research_questions", ()), 80),
        (identity.get("systems", ()), 70),
        (identity.get("pathogens_or_disease_areas", ()), 68),
        (identity.get("methods", ()), 55),
        (departments.get("strong_fit", ()), 75),
        (departments.get("plausible_fit", ()), 60),
    )
    ranked: list[tuple[str, int]] = []
    seen: set[str] = set()
    for values, priority in buckets:
        for value in text_values(values):
            normalized = value.strip().casefold()
            if normalized and normalized not in seen:
                seen.add(normalized)
                ranked.append((value.strip(), priority))
    return ranked


def _role_terms(profile: Mapping[str, Any]) -> list[tuple[str, int]]:
    explicit = get_value(profile, "search.role_terms", "role_terms", default=None)
    if explicit:
        return [(term, 100 - index) for index, term in enumerate(text_values(explicit))]
    regions = [value.upper() for value in text_values(get_value(profile, "regions", "eligibility.countries_or_regions", default=("US", "EUROPE")))]
    terms: list[tuple[str, int]] = []
    seen: set[str] = set()
    for region in regions or ["US", "EUROPE"]:
        group = DEFAULT_ROLE_TERMS.get(region, DEFAULT_ROLE_TERMS.get("EUROPE", ()))
        for index, term in enumerate(group):
            if term.casefold() not in seen:
                seen.add(term.casefold())
                terms.append((term, 100 - index))
    return terms


def _institution_domain(institution: Mapping[str, Any]) -> str | None:
    domains = text_values(institution.get("domains"))
    if domains:
        return domains[0].removeprefix("www.")
    for url in (*text_values(institution.get("career_urls")), *text_values(institution.get("department_urls"))):
        host = urlparse(url).hostname
        if host:
            return host.removeprefix("www.")
    return None


def generate_academic_queries(
    profile: Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]] | Mapping[str, Any] = (),
    institutions: Sequence[Mapping[str, Any]] | Mapping[str, Any] = (),
    budget: int | Mapping[str, Any] = 50,
    *,
    rotation_offset: int = 0,
) -> list[AcademicQuery]:
    """Generate diverse queries without a role/field Cartesian explosion."""

    if isinstance(budget, Mapping):
        total_budget = max(0, int(budget.get("total", budget.get("max_queries", 50))))
        per_source_default = max(1, int(budget.get("per_source", total_budget or 1)))
    else:
        total_budget = max(0, int(budget))
        per_source_default = total_budget or 1
    if total_budget == 0:
        return []

    roles = _role_terms(profile)
    scientific = _ranked_terms(profile)
    if isinstance(institutions, Mapping) and "institutions" in institutions:
        institutions = institutions["institutions"]
    if isinstance(sources, Mapping) and "sources" in sources:
        sources = sources["sources"]
    institution_rows = [row for row in _items(institutions) if isinstance(row, Mapping) and row.get("enabled", True)]
    source_rows = [row for row in _items(sources) if isinstance(row, Mapping) and row.get("enabled", row.get("enabled_by_default", True))]
    if not source_rows:
        source_rows = [{"id": None, "query_cap": total_budget}]

    candidates: list[AcademicQuery] = []
    # Role-first queries provide reliable baseline coverage.
    for role, priority in roles:
        candidates.append(AcademicQuery(f'"{role}"', "role_first", priority))

    # Rotate paired terms rather than materializing every possible combination.
    pair_count = max(len(roles), len(scientific)) if scientific else 0
    for index in range(pair_count):
        role, role_priority = roles[(index + rotation_offset) % len(roles)]
        field, field_priority = scientific[(index + rotation_offset) % len(scientific)]
        candidates.append(
            AcademicQuery(
                f'"{role}" "{field}"',
                "field_first",
                min(role_priority, field_priority),
            )
        )

    # Broad institution searches intentionally omit candidate keywords.
    broad_roles = [term for term, _ in roles if term in {"assistant professor", "faculty position", "group leader", "open rank professor", "lecturer"}]
    for institution in institution_rows:
        name = str(institution.get("name") or "").strip()
        domain = _institution_domain(institution)
        for role in broad_roles[:3]:
            prefix = f"site:{domain} " if domain else f'"{name}" '
            candidates.append(
                AcademicQuery(
                    f'{prefix}"{role}"'.strip(),
                    "target_institution_broad",
                    110 - int(institution.get("priority", 1)),
                    institution=name or None,
                    broad_search=True,
                )
            )

    candidates.sort(key=lambda query: (-query.priority, query.family, _norm_query(query.text)))
    if candidates:
        shift = rotation_offset % len(candidates)
        candidates = candidates[shift:] + candidates[:shift]

    output: list[AcademicQuery] = []
    seen: set[str] = set()
    for source in source_rows:
        source_id = source.get("id")
        cap = min(total_budget, max(1, int(source.get("query_cap", source.get("max_queries", per_source_default)))))
        used = 0
        for query in candidates:
            if used >= cap or len(output) >= total_budget:
                break
            key = f"{source_id or ''}\x1f{_norm_query(query.text)}"
            if key in seen:
                continue
            seen.add(key)
            output.append(
                AcademicQuery(
                    query.text,
                    query.family,
                    query.priority,
                    str(source_id) if source_id else None,
                    query.institution,
                    query.broad_search,
                )
            )
            used += 1
        if len(output) >= total_budget:
            break
    return output


@dataclass
class AcademicQueryGenerator:
    total_budget: int = 50
    per_source_budget: int = 20

    def generate(
        self,
        profile: Mapping[str, Any],
        sources: Sequence[Mapping[str, Any]] | Mapping[str, Any] = (),
        institutions: Sequence[Mapping[str, Any]] | Mapping[str, Any] = (),
        *,
        rotation_offset: int = 0,
    ) -> list[AcademicQuery]:
        return generate_academic_queries(
            profile,
            sources,
            institutions,
            {"total": self.total_budget, "per_source": self.per_source_budget},
            rotation_offset=rotation_offset,
        )


QueryGenerator = AcademicQueryGenerator
