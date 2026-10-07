"""Explainable Academic PI fit scoring and tier routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping

from .models import (
    AcademicRoleClass,
    AcademicTier,
    FitEvaluation,
    get_value,
    text_values,
)
from .titles import infer_independence, normalize_academic_title


DEFAULT_WEIGHTS = {
    "scientific_program_fit": 30.0,
    "department_search_fit": 20.0,
    "independence_and_career_stage_fit": 15.0,
    "method_or_model_system_relevance": 10.0,
    "strategic_research_environment_fit": 10.0,
    "evidence_of_candidate_distinctiveness": 10.0,
    "translational_or_collaborative_fit": 5.0,
}

DEFAULT_THRESHOLDS = {
    "tier_1_min_fit": 80.0,
    "tier_2_min_fit": 68.0,
    "watchlist_min_fit": 55.0,
}

_BROAD_SCOPE_PATTERNS = (
    re.compile(r"\ball areas? (?:of|in) (?:biology|biomedical science|life science|science)", re.I),
    re.compile(r"\bany (?:area|field) (?:of|in)\b", re.I),
    re.compile(r"\bbroad(?:ly)? defined\b", re.I),
    re.compile(r"\bopen (?:discipline|field|area)\b", re.I),
)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _haystack(job: Any) -> str:
    values = (
        get_value(job, "raw_title", "identity.raw_title", "title", default=""),
        get_value(job, "description", "extra.description", default=""),
        *text_values(get_value(job, "declared_fields", "search_scope.declared_fields", default=())),
        *text_values(get_value(job, "department_scope", "search_scope.department_scope", default=())),
        *text_values(get_value(job, "required_expertise", "requirements.required_expertise", default=())),
        *text_values(get_value(job, "preferred_expertise", "requirements.preferred_expertise", default=())),
    )
    return _norm(" ".join(str(value) for value in values if value))


def is_broad_search(job: Any) -> bool:
    explicit = get_value(job, "broad_search", "search_scope.broad_search", default=None)
    if explicit is not None:
        return bool(explicit)
    text = str(get_value(job, "description", "extra.description", default=""))
    return any(pattern.search(text) for pattern in _BROAD_SCOPE_PATTERNS)


def _profile_terms(profile: Mapping[str, Any], *names: str) -> tuple[str, ...]:
    identity = profile.get("scientific_identity", {})
    values: list[str] = []
    for name in names:
        values.extend(text_values(identity.get(name)))
    return tuple(dict.fromkeys(value for value in values if value.strip()))


def _matches(terms: tuple[str, ...], haystack: str) -> list[str]:
    matches: list[str] = []
    for term in terms:
        normalized = _norm(term)
        if normalized and normalized in haystack:
            matches.append(term)
    return matches


def _component_from_matches(matches: list[str], total_terms: int, *, floor: float = 0.0) -> float:
    if total_terms <= 0:
        return 0.0
    if not matches:
        return floor
    coverage = min(1.0, len(matches) / max(1.0, min(total_terms, 4)))
    return max(floor, 0.55 + 0.45 * coverage)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _hard_blockers(job: Any, profile: Mapping[str, Any], today: date) -> list[str]:
    # Prior scorer output is a snapshot, not fresh evidence.  Only carry an
    # explicit/manual blocker into a new evaluation; all derived blockers are
    # recomputed below from the current job and profile.
    blockers = list(
        text_values(
            get_value(
                job,
                "manual_hard_blockers",
                "confirmed_hard_blockers",
                "extra.manual_hard_blockers",
                default=(),
            )
        )
    )
    prior_evaluation = get_value(job, "evaluation", default={})
    prior_derived = (
        text_values(prior_evaluation.get("hard_blockers"))
        if isinstance(prior_evaluation, Mapping)
        else ()
    )
    top_level_blockers = text_values(get_value(job, "hard_blockers", default=()))
    if top_level_blockers and tuple(top_level_blockers) != tuple(prior_derived):
        blockers.extend(top_level_blockers)
    human_override = get_value(job, "human_override", "extra.human_override", default={})
    if isinstance(human_override, Mapping) and str(human_override.get("field", "")).casefold() in {
        "blocker",
        "blockers",
        "hard_blockers",
    }:
        blockers.extend(text_values(human_override.get("value")))
    role = str(
        get_value(job, "normalized_role_class", "identity.normalized_role_class", default="")
        or normalize_academic_title(
            str(get_value(job, "raw_title", "identity.raw_title", "title", default=""))
        ).normalized_role_class
    )
    targets = set(
        text_values(
            get_value(profile, "career_stage.target_independence", default=("independent_pi", "tenure_track_faculty", "independent_group_leader"))
        )
    )
    independent_only = bool(targets) and not any(
        value in targets for value in ("research_faculty", "non_independent_research")
    )
    if independent_only and role in {
        AcademicRoleClass.POSTDOC.value,
        AcademicRoleClass.STAFF_SCIENTIST.value,
        AcademicRoleClass.TECHNICIAN.value,
        AcademicRoleClass.NON_INDEPENDENT_RESEARCH.value,
        AcademicRoleClass.TEACHING_ONLY.value,
    }:
        blockers.append("role is explicitly non-independent for an independent-PI search")

    deadline = _parse_date(get_value(job, "deadline", "dates.deadline", default=None))
    deadline_type = str(get_value(job, "deadline_type", "dates.deadline_type", default="unknown"))
    if deadline and deadline_type.casefold() == "fixed" and deadline < today:
        blockers.append("fixed application deadline has passed")

    country = str(get_value(job, "country", "identity.country", default="")).upper()
    geography = profile.get("geography", {})
    hard_avoid = {str(value).upper() for value in text_values(geography.get("hard_exclude", geography.get("avoid_if_hard", ())))}
    if country and country in hard_avoid:
        blockers.append("country or region is configured as a hard geographic exclusion")

    eligibility = str(get_value(job, "citizenship_or_eligibility", "requirements.citizenship_or_eligibility", default=""))
    unmet = [
        value for value in text_values(get_value(profile, "eligibility.explicit_citizenship_constraints", default=()))
        if value and value.casefold() in eligibility.casefold()
    ]
    if unmet:
        blockers.append("explicit citizenship or eligibility requirement is not met")
    return list(dict.fromkeys(blockers))


def score_academic_fit(
    job: Any,
    profile: Mapping[str, Any],
    scoring_config: Mapping[str, Any] | None = None,
    *,
    today: date | None = None,
) -> FitEvaluation:
    """Score candidate fit while keeping blockers and confidence independent."""

    config = dict(scoring_config or {})
    weights = {
        **DEFAULT_WEIGHTS,
        **dict(config.get("weights", config.get("dimensions", {}))),
    }
    # ``tiering`` is the public default and ``thresholds`` is the documented
    # private overlay.  When both are present, the private values must win.
    public_thresholds = config.get("tiering", config)
    private_thresholds = config.get("thresholds", {})
    threshold_values = {
        **(dict(public_thresholds) if isinstance(public_thresholds, Mapping) else {}),
        **(dict(private_thresholds) if isinstance(private_thresholds, Mapping) else {}),
    }
    thresholds = {
        **DEFAULT_THRESHOLDS,
        **{
            key: value
            for key, value in dict(threshold_values).items()
            if key in DEFAULT_THRESHOLDS
        },
    }
    now = today or datetime.now(timezone.utc).date()
    text = _haystack(job)
    broad = is_broad_search(job)

    primary = _profile_terms(profile, "primary_fields", "research_questions")
    secondary = _profile_terms(profile, "secondary_fields", "pathogens_or_disease_areas")
    methods = _profile_terms(profile, "methods", "systems", "computational_or_quantitative_strengths")
    translational = _profile_terms(profile, "translational_strengths")
    direct_matches = _matches(primary, text)
    adjacent_matches = _matches(secondary, text)
    method_matches = _matches(methods, text)
    translational_matches = _matches(translational, text)

    departments = profile.get("departments", {})
    strong_departments = tuple(text_values(departments.get("strong_fit")))
    plausible_departments = tuple(text_values(departments.get("plausible_fit")))
    department_text = _norm(
        " ".join(
            text_values(get_value(job, "department", "identity.department", default=""))
            + text_values(get_value(job, "department_scope", "search_scope.department_scope", default=()))
        )
    )
    strong_department_matches = _matches(strong_departments, department_text)
    plausible_department_matches = _matches(plausible_departments, department_text)

    scientific_matches = direct_matches + adjacent_matches
    scientific_term_count = len(primary) + len(secondary)
    if broad and scientific_term_count and not scientific_matches:
        # Keyword absence in a broad call is unknown/neutral.  It is not a
        # penalty, but it also is not positive evidence of candidate fit.
        scientific_component = 0.5
    else:
        scientific_component = _component_from_matches(
            scientific_matches,
            scientific_term_count,
            floor=0.15 if text else 0.5,
        )

    if strong_department_matches:
        department_component = 1.0
    elif plausible_department_matches:
        department_component = 0.78
    elif broad and (strong_departments or plausible_departments):
        department_component = 0.5
    elif not (strong_departments or plausible_departments):
        department_component = 0.0
    else:
        department_component = 0.5 if not department_text else 0.3

    title = str(get_value(job, "raw_title", "identity.raw_title", "title", default=""))
    country = get_value(job, "country", "identity.country", default=None)
    description = str(get_value(job, "description", "extra.description", default=""))
    independence = infer_independence(title, description, country=country)
    explicit_independence = str(get_value(job, "independence_class", "independence.class", default=""))
    independence_class = explicit_independence or independence.independence_class
    configured_career_targets = text_values(
        get_value(profile, "career_stage.target_independence", default=())
    )
    independence_component = (
        {
            "independent": 1.0,
            "likely_independent": 0.8,
            "ambiguous": 0.5,
            "non_independent": 0.0,
        }.get(independence_class, 0.5)
        if configured_career_targets
        else 0.0
    )

    method_component = _component_from_matches(method_matches, len(methods), floor=0.5 if broad else 0.15)
    environment_signals = text_values(
        get_value(job, "opportunity_notes", "evaluation.opportunity_notes", default=())
    ) + text_values(get_value(job, "position.startup_information", "startup_information", default=()))
    environment_component = 0.75 if environment_signals else 0.0

    evidence = profile.get("evidence", {})
    if not isinstance(evidence, Mapping):
        evidence = {}
    distinctiveness_terms = tuple(
        dict.fromkeys(
            text_values(evidence.get("verified_distinctiveness"))
            + text_values(evidence.get("distinctiveness_strengths"))
        )
    )
    distinctiveness_matches = _matches(distinctiveness_terms, text)
    # Merely having an evidence path is not a positive claim.  Only explicitly
    # verified distinctiveness strengths that overlap the posting earn points.
    distinctiveness_component = _component_from_matches(
        distinctiveness_matches,
        len(distinctiveness_terms),
    )
    translational_component = _component_from_matches(
        translational_matches,
        len(translational),
        floor=0.5 if broad else 0.0,
    )

    components = {
        "scientific_program_fit": scientific_component,
        "department_search_fit": department_component,
        "independence_and_career_stage_fit": independence_component,
        "method_or_model_system_relevance": method_component,
        "strategic_research_environment_fit": environment_component,
        "evidence_of_candidate_distinctiveness": distinctiveness_component,
        "translational_or_collaborative_fit": translational_component,
    }
    weight_total = sum(max(0.0, float(weights.get(name, 0.0))) for name in components) or 1.0
    raw_score = 100.0 * sum(
        components[name] * max(0.0, float(weights.get(name, 0.0))) for name in components
    ) / weight_total
    fit_score = round(max(0.0, min(100.0, raw_score)), 1)

    blockers = _hard_blockers(job, profile, now)
    raw_verification_status = get_value(
        job, "verification_status", "status.verification_status", default="verification_pending"
    )
    verification_status = str(getattr(raw_verification_status, "value", raw_verification_status))
    verification_confidence = float(
        get_value(job, "verification_confidence", "status.verification_confidence", default=0.0) or 0.0
    )
    verified_usable = verification_status in {"verified_open", "verified_reopened"}
    evidence_backed_matches = (
        direct_matches
        + adjacent_matches
        + method_matches
        + translational_matches
        + strong_department_matches
        + plausible_department_matches
        + distinctiveness_matches
    )
    candidate_fit_basis = bool(evidence_backed_matches)
    if blockers:
        tier = AcademicTier.BLOCKED.value
    elif not verified_usable:
        tier = AcademicTier.WATCHLIST.value
    elif not candidate_fit_basis:
        tier = (
            AcademicTier.WATCHLIST.value
            if fit_score >= float(thresholds["watchlist_min_fit"])
            else AcademicTier.BELOW_THRESHOLD.value
        )
    elif fit_score >= float(thresholds["tier_1_min_fit"]) and verification_confidence >= float(config.get("tier_1_min_verification_confidence", 0.7)):
        tier = AcademicTier.TIER_1.value
    elif fit_score >= float(thresholds["tier_2_min_fit"]):
        tier = AcademicTier.TIER_2.value
    elif fit_score >= float(thresholds["watchlist_min_fit"]):
        tier = AcademicTier.WATCHLIST.value
    else:
        tier = AcademicTier.BELOW_THRESHOLD.value

    strongest: list[str] = []
    strongest.extend(f"direct profile match: {value}" for value in direct_matches[:3])
    strongest.extend(f"credible adjacent match: {value}" for value in adjacent_matches[:2])
    strongest.extend(f"department match: {value}" for value in strong_department_matches[:2])
    strongest.extend(
        f"verified distinctiveness match: {value}"
        for value in distinctiveness_matches[:2]
    )
    gaps: list[str] = []
    if not broad and primary and not direct_matches:
        gaps.append("no direct primary-field term found in the posting")
    if independence_class == "ambiguous":
        gaps.append("independence requires manual review")
    if not verified_usable:
        gaps.append("official open status is not sufficiently verified")
    if not candidate_fit_basis:
        gaps.append("insufficient candidate-fit evidence for Tier 1 or Tier 2")

    known_signals = sum(bool(value) for value in (text, title, country, department_text))
    confidence = min(1.0, 0.35 + 0.12 * known_signals + 0.15 * verification_confidence)
    return FitEvaluation(
        fit_score=fit_score,
        tier=tier,
        fit_confidence=round(confidence, 3),
        category_scores={name: round(value * 100.0, 1) for name, value in components.items()},
        strongest_matches=tuple(dict.fromkeys(strongest)),
        meaningful_gaps=tuple(dict.fromkeys(gaps)),
        hard_blockers=tuple(blockers),
        opportunity_notes=tuple(environment_signals),
        broad_search=broad,
    )


@dataclass
class AcademicScorer:
    config: Mapping[str, Any] = field(default_factory=dict)

    def score(
        self,
        job: Any,
        profile: Mapping[str, Any],
        *,
        today: date | None = None,
    ) -> FitEvaluation:
        return score_academic_fit(job, profile, self.config, today=today)


apply_broad_search_rule = is_broad_search
