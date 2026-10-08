import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_deployments.py"
SPEC = importlib.util.spec_from_file_location("verified_search_deployment_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

DEPLOYMENTS = MODULE.DEPLOYMENTS
DeploymentSpec = MODULE.DeploymentSpec
ValidationError = MODULE.ValidationError
extract_paste_ready_block = MODULE.extract_paste_ready_block
validate_deployment = MODULE.validate_deployment


CUSTOM_GPT = DEPLOYMENTS[0]


def test_all_verified_search_deployments_fit_independent_budgets() -> None:
    counts = {spec.name: validate_deployment(spec) for spec in DEPLOYMENTS}

    assert counts["Custom GPT Instructions"] <= 7_500
    assert counts["Compact Custom Instructions"] <= 1_400
    assert counts["Full Custom Instructions"] <= 5_000
    assert [spec.platform_hard_limit for spec in DEPLOYMENTS] == [8_000, None, None]


def test_custom_gpt_validator_fails_above_platform_limit(tmp_path: Path) -> None:
    artifact = tmp_path / "custom_gpt.md"
    artifact.write_text(
        "# Test\n\n## Paste-Ready Instructions\n\n```text\n"
        + ("x" * 8_001)
        + "\n```\n",
        encoding="utf-8",
    )
    spec = DeploymentSpec(
        name="Custom GPT Instructions",
        path=artifact,
        heading="Paste-Ready Instructions",
        platform_hard_limit=8_000,
        release_budget=8_000,
        reported_count_required=False,
    )

    with pytest.raises(ValidationError, match="hard limit is 8,000"):
        validate_deployment(spec)


def test_custom_gpt_block_preserves_required_deployment_contract() -> None:
    text = CUSTOM_GPT.path.read_text(encoding="utf-8")
    block = extract_paste_ready_block(text, CUSTOM_GPT.heading)

    required_signals = (
        "These Instructions control",
        "verified_search_core.md",
        "test_cases.md",
        "user_experience.md",
        "Baseline",
        "Strict",
        "Final-Action Audit",
        "Decision Framing",
        "Failure-Mode First",
        "claim-specific authority",
        "Entity Lock",
        "Date Lock",
        "Freshness",
        "Applicability",
        "Temporal Relevance",
        "CONTINUING APPLICABILITY AND SUPERSESSION",
        "Newer does not automatically win",
        "older/specific information does not control forever",
        "does not prove continuation",
        "does not prove termination",
        "Search snippets are discovery only",
        "No-Fill Rule",
        "Negative-Claim Guard",
        "Conflicting/Unverified",
        "ACTION READINESS",
        "MANDATORY SOURCE URL POLICY",
        "Never invent, reconstruct, infer, autocomplete, or guess a URL",
        "mitigation",
        "Re-check",
    )
    for signal in required_signals:
        assert signal in block
