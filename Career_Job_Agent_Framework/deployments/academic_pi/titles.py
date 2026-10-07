"""Country-aware academic title and independence normalization."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from .models import (
    AcademicRoleClass,
    IndependenceAssessment,
    IndependenceClass,
    TitleNormalization,
)


_COUNTRY_ALIASES = {
    "UNITED STATES": "US",
    "USA": "US",
    "U.S.": "US",
    "UNITED KINGDOM": "GB",
    "UK": "GB",
    "GREAT BRITAIN": "GB",
    "GERMANY": "DE",
    "DEUTSCHLAND": "DE",
}


def _country_code(country: str | None) -> str | None:
    if not country:
        return None
    value = country.strip().upper()
    return _COUNTRY_ALIASES.get(value, value)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w+/-]+", " ", text.casefold())).strip()


_EXCLUSION_RULES: tuple[tuple[re.Pattern[str], AcademicRoleClass], ...] = (
    (re.compile(r"\b(postdoc(?:toral)?|research fellow)\b", re.I), AcademicRoleClass.POSTDOC),
    (re.compile(r"\bstaff scientist\b", re.I), AcademicRoleClass.STAFF_SCIENTIST),
    (re.compile(r"\bresearch assistant professor\b", re.I), AcademicRoleClass.RESEARCH_FACULTY),
    (re.compile(r"\b(technician|research assistant)\b", re.I), AcademicRoleClass.TECHNICIAN),
    (re.compile(r"\b(teaching[- ]only|teaching professor|instructor)\b", re.I), AcademicRoleClass.TEACHING_ONLY),
    (re.compile(r"\b(administrator|administrative|program manager)\b", re.I), AcademicRoleClass.ADMINISTRATIVE),
    (re.compile(r"\b(research scientist|project scientist)\b", re.I), AcademicRoleClass.NON_INDEPENDENT_RESEARCH),
)

_GENERAL_RULES: tuple[tuple[re.Pattern[str], AcademicRoleClass, float], ...] = (
    (re.compile(r"\bprincipal investigator\b", re.I), AcademicRoleClass.INDEPENDENT_PI, 0.98),
    (re.compile(r"\bindependent (?:junior )?group leader\b", re.I), AcademicRoleClass.INDEPENDENT_GROUP_LEADER, 0.98),
    (re.compile(r"\bjunior group leader\b", re.I), AcademicRoleClass.INDEPENDENT_GROUP_LEADER, 0.94),
    (re.compile(r"\bgroup leader\b", re.I), AcademicRoleClass.INDEPENDENT_GROUP_LEADER, 0.82),
    (re.compile(r"\btenure[- ]track\b", re.I), AcademicRoleClass.TENURE_TRACK_FACULTY, 0.98),
    (re.compile(r"\bopen[- ]rank\b", re.I), AcademicRoleClass.FACULTY_OPEN_RANK, 0.94),
    (re.compile(r"\bassistant professor\b", re.I), AcademicRoleClass.TENURE_TRACK_FACULTY, 0.88),
    (re.compile(r"\bfaculty (?:position|opening|search)\b", re.I), AcademicRoleClass.LIKELY_INDEPENDENT_PI, 0.76),
    (re.compile(r"\binvestigator\b", re.I), AcademicRoleClass.AMBIGUOUS_INDEPENDENCE, 0.58),
)

_COUNTRY_RULES: dict[str, tuple[tuple[re.Pattern[str], AcademicRoleClass, float], ...]] = {
    "GB": (
        (re.compile(r"\b(?:senior )?lecturer\b", re.I), AcademicRoleClass.LIKELY_INDEPENDENT_PI, 0.78),
        (re.compile(r"\breader\b", re.I), AcademicRoleClass.LIKELY_INDEPENDENT_PI, 0.84),
    ),
    "DE": (
        (re.compile(r"\bw[123][ -]?professor(?:ship)?\b", re.I), AcademicRoleClass.LIKELY_INDEPENDENT_PI, 0.88),
        (re.compile(r"\bjuniorprofessor(?:in)?\b", re.I), AcademicRoleClass.LIKELY_INDEPENDENT_PI, 0.84),
    ),
    "US": (
        (re.compile(r"\b(?:associate|full) professor\b", re.I), AcademicRoleClass.LIKELY_INDEPENDENT_PI, 0.9),
    ),
}


def normalize_academic_title(
    raw_title: str,
    country: str | None = None,
    context: str | None = None,
    *,
    rules: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    country_rules: Mapping[str, Any] | None = None,
) -> TitleNormalization:
    """Normalize a heterogeneous title without assuming title alone proves independence."""

    title = _compact(raw_title or "")
    context_text = _compact(context or "")
    combined = f"{title} {context_text}".strip()
    code = _country_code(country)
    if not title:
        return TitleNormalization(raw_title or "", AcademicRoleClass.OTHER.value, code, 0.0, (), True)

    for pattern, role_class in _EXCLUSION_RULES:
        match = pattern.search(title)
        if match:
            return TitleNormalization(
                raw_title,
                role_class.value,
                code,
                0.98,
                (match.group(0),),
                role_class in {AcademicRoleClass.RESEARCH_FACULTY, AcademicRoleClass.NON_INDEPENDENT_RESEARCH},
            )

    configured_regions = country_rules.get("regions", country_rules) if isinstance(country_rules, Mapping) else {}
    region = configured_regions.get(code, {}) if isinstance(configured_regions, Mapping) else {}
    overrides = region.get("title_overrides", {}) if isinstance(region, Mapping) else {}
    if isinstance(overrides, Mapping):
        for phrase, override in overrides.items():
            if _compact(str(phrase)) not in title or not isinstance(override, Mapping):
                continue
            role = str(override.get("normalized_class", AcademicRoleClass.OTHER.value))
            requires_review = any(
                bool(override.get(key))
                for key in (
                    "require_tenure_or_independence_evidence",
                    "require_independence_evidence",
                    "require_institution_context",
                    "require_country_and_institution_context",
                )
            )
            return TitleNormalization(raw_title, role, code, 0.9, (str(phrase),), requires_review)

    configured_rules: Iterable[Mapping[str, Any]] = ()
    if isinstance(rules, Mapping):
        configured_rules = rules.get("rules", ())
    elif rules is not None:
        configured_rules = rules
    for rule in sorted(configured_rules, key=lambda item: int(item.get("priority", 0)), reverse=True):
        for phrase in rule.get("patterns", ()):
            if _compact(str(phrase)) not in title:
                continue
            role = str(rule.get("normalized_class", AcademicRoleClass.OTHER.value))
            requires_review = bool(
                rule.get("require_context_for_final_independence")
                or rule.get("require_country_context")
                or role in {
                    AcademicRoleClass.LIKELY_INDEPENDENT_PI.value,
                    AcademicRoleClass.AMBIGUOUS_INDEPENDENCE.value,
                    AcademicRoleClass.RESEARCH_FACULTY.value,
                }
            )
            return TitleNormalization(raw_title, role, code, 0.88, (str(phrase),), requires_review)

    rules = (*_COUNTRY_RULES.get(code or "", ()), *_GENERAL_RULES)
    for pattern, role_class, confidence in rules:
        match = pattern.search(title)
        if not match:
            continue
        if role_class == AcademicRoleClass.INDEPENDENT_GROUP_LEADER and "group leader" in title:
            negative_context = any(
                pattern.search(context or "")
                for pattern, _label, _weight in _NEGATIVE_INDEPENDENCE_PATTERNS
            )
            if negative_context:
                role_class = AcademicRoleClass.AMBIGUOUS_INDEPENDENCE
                confidence = min(confidence, 0.55)
        requires_review = role_class in {
            AcademicRoleClass.LIKELY_INDEPENDENT_PI,
            AcademicRoleClass.AMBIGUOUS_INDEPENDENCE,
            AcademicRoleClass.RESEARCH_FACULTY,
        }
        return TitleNormalization(raw_title, role_class.value, code, confidence, (match.group(0),), requires_review)

    if re.search(r"\bprofessor(?:ship)?\b", combined, re.I):
        return TitleNormalization(
            raw_title,
            AcademicRoleClass.LIKELY_INDEPENDENT_PI.value,
            code,
            0.66,
            ("professor",),
            True,
        )
    return TitleNormalization(raw_title, AcademicRoleClass.OTHER.value, code, 0.25, (), True)


_POSITIVE_INDEPENDENCE_PATTERNS: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (re.compile(r"establish (?:an? |your )?independent research (?:program|programme)", re.I), "establish an independent research program", 0.36),
    (re.compile(r"develop (?:an? |your )?independent research (?:program|programme)", re.I), "develop an independent research program", 0.25),
    (re.compile(r"lead (?:an? |your )?(?:independent )?research (?:group|team|lab(?:oratory)?)", re.I), "lead a research group", 0.2),
    (re.compile(r"recruit (?:and |&)?.{0,20}(?:research )?(?:group|team|staff|students)", re.I), "recruit a research group", 0.16),
    (re.compile(r"startup (?:package|funds?|support)", re.I), "startup support", 0.14),
    (re.compile(r"(?:dedicated |independent )?lab(?:oratory)? space", re.I), "laboratory space", 0.14),
    (re.compile(r"independent (?:budget|funding)", re.I), "independent budget", 0.15),
    (re.compile(r"tenure[- ]track", re.I), "tenure-track appointment", 0.24),
    (re.compile(r"faculty appointment", re.I), "faculty appointment", 0.16),
    (re.compile(r"supervis(?:e|ion of) (?:graduate|doctoral|phd) students", re.I), "graduate student supervision", 0.12),
    (re.compile(r"eligible (?:to serve|for appointment) as (?:a )?(?:principal investigator|pi)", re.I), "principal investigator eligibility", 0.24),
    (re.compile(r"secure (?:independent |external )?(?:grant |research )?funding", re.I), "independent funding expectation", 0.12),
)

_NEGATIVE_INDEPENDENCE_PATTERNS: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (re.compile(r"under the (?:direct )?supervision of", re.I), "works under direct supervision", 0.32),
    (re.compile(r"support (?:the |an )?existing (?:lab|laboratory|research group)", re.I), "supports an existing laboratory", 0.28),
    (re.compile(r"(?:postdoctoral|postdoc) (?:fellow|position|researcher)", re.I), "postdoctoral appointment", 0.45),
    (re.compile(r"no independent (?:research )?(?:program|programme|budget|space)", re.I), "no independent program", 0.5),
)


def infer_independence(
    title: str,
    text: str,
    country: str | None = None,
) -> IndependenceAssessment:
    """Infer independence from contextual evidence, retaining ambiguity explicitly."""

    haystack = f"{title or ''}\n{text or ''}"
    evidence: list[str] = []
    positive = 0.0
    negative = 0.0
    for pattern, label, weight in _POSITIVE_INDEPENDENCE_PATTERNS:
        if pattern.search(haystack):
            evidence.append(label)
            positive += weight
    for pattern, label, weight in _NEGATIVE_INDEPENDENCE_PATTERNS:
        if pattern.search(haystack):
            evidence.append(label)
            negative += weight

    normalized = normalize_academic_title(title, country=country) if title else None
    if normalized:
        role = normalized.normalized_role_class
        if role in {
            AcademicRoleClass.INDEPENDENT_PI.value,
            AcademicRoleClass.TENURE_TRACK_FACULTY.value,
            AcademicRoleClass.FACULTY_OPEN_RANK.value,
        }:
            positive += 0.3
            evidence.append(f"title class: {role}")
        elif role == AcademicRoleClass.INDEPENDENT_GROUP_LEADER.value:
            # A bare European "Group Leader" title is not enough to prove
            # independence.  Stronger variants (independent/junior) remain
            # useful evidence, while the generic title is routed to review.
            title_text = title.casefold()
            positive += 0.3 if any(
                marker in title_text for marker in ("independent", "junior")
            ) else 0.2
            evidence.append(f"title class: {role}")
        elif role in {
            AcademicRoleClass.POSTDOC.value,
            AcademicRoleClass.STAFF_SCIENTIST.value,
            AcademicRoleClass.TECHNICIAN.value,
            AcademicRoleClass.NON_INDEPENDENT_RESEARCH.value,
        }:
            negative += 0.4
            evidence.append(f"title class: {role}")

    net = positive - negative
    if negative >= 0.4 and negative >= positive:
        classification = IndependenceClass.NON_INDEPENDENT.value
        confidence = min(0.99, 0.55 + negative - min(positive, 0.25))
    elif positive >= 0.55 and net >= 0.3:
        classification = IndependenceClass.INDEPENDENT.value
        confidence = min(0.99, 0.55 + positive / 2)
    elif positive >= 0.25 and net > 0:
        classification = IndependenceClass.LIKELY_INDEPENDENT.value
        confidence = min(0.9, 0.5 + positive / 2)
    else:
        classification = IndependenceClass.AMBIGUOUS.value
        confidence = max(0.25, min(0.65, 0.4 + abs(net) / 3))

    return IndependenceAssessment(classification, round(confidence, 3), tuple(dict.fromkeys(evidence)))


def normalize_titles(
    titles: Iterable[str], country: str | None = None
) -> tuple[TitleNormalization, ...]:
    return tuple(normalize_academic_title(title, country=country) for title in titles)
