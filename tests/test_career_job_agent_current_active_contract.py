"""Regression checks for the reusable CURRENT ACTIVE TIER 1/2 contract."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = REPO_ROOT / "Career_Job_Agent_Framework"


def test_daily_contract_separates_alerts_from_current_active_snapshot() -> None:
    contract = (FRAMEWORK / "contracts" / "daily_run.md").read_text(encoding="utf-8")

    assert "Today's changes / alerts" in contract
    assert "CURRENT ACTIVE TIER 1/2" in contract
    assert "including unchanged prior-day roles" in contract
    assert "Snapshot membership does not change the headline" in contract
    assert "same object or list" in contract
    assert "transient reverification failure" in contract
    assert "enabled` is `false`" in contract


def test_example_config_enables_all_required_snapshot_channels_and_fields() -> None:
    config = (FRAMEWORK / "templates" / "search_preferences.example.yaml").read_text(
        encoding="utf-8"
    )

    required_tokens = (
        "current_active_tier_1_2:",
        'heading: "CURRENT ACTIVE TIER 1/2"',
        "include_unchanged: true",
        "reverify_official_status_each_daily_run: true",
        "daily_report",
        "chatgpt_digest",
        "gmail_digest",
        "slack_digest",
        "fit_score_desc",
        "workflow_status",
        "strongest_match",
        "official_url",
    )
    for token in required_tokens:
        assert token in config


def test_framework_readme_prevents_new_jobs_only_regression() -> None:
    readme = (FRAMEWORK / "README.md").read_text(encoding="utf-8")

    assert "including unchanged roles" in readme
    assert "portfolio view, not a new-job alert" in readme
    assert "never changes today's headline" in readme
