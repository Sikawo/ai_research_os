"""Regression checks for manual-evaluation canonical-state persistence."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = REPO_ROOT / "Career_Job_Agent_Framework"


def test_contract_requires_official_active_actionable_manual_upsert() -> None:
    contract = (FRAMEWORK / "contracts" / "state_persistence.md").read_text(
        encoding="utf-8"
    )

    required_tokens = (
        "one canonical Career Job Agent state",
        "official employer career page",
        "actionable Tier 1 or Tier 2",
        "LinkedIn and other aggregators are discovery aids only",
        "Upsert; never blindly append",
        "normalized company + official job ID",
        "canonical official URL",
        "normalized company + title + location",
        "must not:\n\n- increment the scheduled run's new-job",
        "generate or submit an application",
        "Retrying must remain idempotent",
    )
    for token in required_tokens:
        assert token in contract


def test_example_config_enables_manual_tier_1_2_persistence() -> None:
    config = (FRAMEWORK / "templates" / "search_preferences.example.yaml").read_text(
        encoding="utf-8"
    )

    required_tokens = (
        "state_persistence:",
        "manual_evaluations:",
        "enabled: true",
        "upsert_actionable_tier_1_2: true",
        "require_current_official_verification: true",
    )
    for token in required_tokens:
        assert token in config


def test_framework_readme_routes_manual_rows_to_same_canonical_state() -> None:
    readme = (FRAMEWORK / "README.md").read_text(encoding="utf-8")

    assert "Manual ChatGPT evaluations use that same canonical state" in readme
    assert "does not count as scheduled discovery" in readme
    assert "contracts/state_persistence.md" in readme
