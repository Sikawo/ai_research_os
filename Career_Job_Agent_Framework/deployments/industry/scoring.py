"""Deterministic fit scoring and duplicate detection for Career Job Agent v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ScoreResult:
    raw_score: float
    penalty_total: float
    final_score: float
    tier: str


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def score_job(dimensions: Mapping[str, float], weights: Mapping[str, float], active_penalties: Mapping[str, bool], penalty_values: Mapping[str, float], tier_1_minimum: float, tier_2_minimum: float) -> ScoreResult:
    weight_total = sum(float(value) for value in weights.values())
    if weight_total <= 0:
        raise ValueError("weights must sum to a positive value")
    weighted = sum(_bounded(dimensions.get(name, 0.0)) * float(weight) for name, weight in weights.items())
    raw_score = 100.0 * weighted / weight_total
    penalty_total = sum(float(penalty_values.get(name, 0.0)) for name, enabled in active_penalties.items() if enabled)
    final_score = max(0.0, min(100.0, raw_score - penalty_total))
    tier = "tier_1" if final_score >= tier_1_minimum else "tier_2" if final_score >= tier_2_minimum else "below_threshold"
    return ScoreResult(round(raw_score, 2), round(penalty_total, 2), round(final_score, 2), tier)


def normalized_job_key(company: str, job_id: str, title: str, location: str) -> str:
    def clean(value: str) -> str:
        return " ".join(value.lower().strip().split())
    return "|".join(clean(value) for value in (company, job_id, title, location))
