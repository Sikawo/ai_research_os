"""Regression checks for the reusable CURRENT ACTIVE TIER 1/2 contract."""

from pathlib import Path

from Career_Job_Agent_Framework.core.connectors import ConnectorError, DeliveryResult


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


def test_industry_contracts_require_value_free_configuration_provenance() -> None:
    contracts = (
        FRAMEWORK / "contracts" / "daily_run.md",
        FRAMEWORK / "deployments" / "industry" / "contracts" / "daily_run.md",
        FRAMEWORK / "deployments" / "industry" / "contracts" / "runtime.md",
    )

    required_tokens = (
        "CONFIGURATION PROVENANCE",
        "framework_source",
        "framework_resolution",
        "deployment_config_source",
        "deployment_config_resolution",
        "fallback_used",
        "PASS",
        "FAIL",
        "UNKNOWN",
        "BLOCKING CONFIGURATION DIAGNOSTIC",
    )
    for path in contracts:
        contract = path.read_text(encoding="utf-8")
        for token in required_tokens:
            assert token in contract, f"{path.relative_to(REPO_ROOT)} missing {token}"


def test_industry_provenance_gate_rejects_prompt_only_evidence_and_fallback() -> None:
    shared = (FRAMEWORK / "contracts" / "daily_run.md").read_text(encoding="utf-8")
    industry_daily = (
        FRAMEWORK / "deployments" / "industry" / "contracts" / "daily_run.md"
    ).read_text(encoding="utf-8")
    industry_runtime = (
        FRAMEWORK / "deployments" / "industry" / "contracts" / "runtime.md"
    ).read_text(encoding="utf-8")

    assert "saved task prompt is not resolution evidence" in " ".join(shared.split())
    assert "saved task prompt is not proof" in " ".join(industry_daily.split())
    assert "saved prompt is not sufficient evidence" in " ".join(
        industry_runtime.split()
    )

    for contract in (shared, industry_daily, industry_runtime):
        normalized = " ".join(contract.split())
        assert "fallback_used` is `no`" in normalized
        assert "stop before search" in normalized
        assert "private" in normalized
        assert "connector IDs" in normalized


def test_delivery_result_preserves_legacy_confirmed_success() -> None:
    result = DeliveryResult.from_dict(
        {
            "channel": "synthetic_report",
            "confirmed": True,
            "external_id": "synthetic-result-1",
        }
    )

    assert result.confirmed is True
    assert result.attempted is True
    assert result.connector_reached == "yes"
    assert result.outcome == "success"
    assert result.result_reference == "synthetic-result-1"
    assert result.retryable is False


def test_uncertain_delivery_requires_reconciliation_before_retry() -> None:
    result = DeliveryResult.uncertain(
        "synthetic_mail",
        run_id="run-1",
        logical_action="send_digest",
        failure_class="safety_checks",
        error_code="blocked",
        error="sanitized synthetic failure",
        destination_type="mailbox",
        account_selector_redacted="account-…01",
        account_selection_unique=True,
        idempotency_key="run-1:send_digest",
    )

    assert result.confirmed is False
    assert result.run_id == "run-1"
    assert result.attempted is True
    assert result.attempted_at is not None
    assert result.outcome == "uncertain"
    assert result.readback_status == "unknown"
    assert result.requires_reconciliation is True
    assert result.may_retry_without_reconciliation is False


def test_only_confirmed_predispatch_failure_allows_blind_retry() -> None:
    result = DeliveryResult.failure(
        "synthetic_chat",
        logical_action="post_digest",
        connector_reached="no",
        failure_class="temporary_connector_error",
        error_code="synthetic_unavailable",
        error="sanitized synthetic failure",
        retryable=True,
        destination_type="channel",
        account_selection_unique=True,
        idempotency_key="run-1:post_digest",
    )

    assert result.confirmed is False
    assert result.outcome == "failure"
    assert result.requires_reconciliation is False
    assert result.may_retry_without_reconciliation is True


def test_explicit_uncertain_outcome_overrides_legacy_confirmed_flag() -> None:
    result = DeliveryResult.from_dict(
        {
            "channel": "synthetic_mail",
            "confirmed": True,
            "attempted": True,
            "connector_reached": "unknown",
            "outcome": "uncertain",
            "retryable": True,
        }
    )

    assert result.confirmed is False
    assert result.outcome == "uncertain"
    assert result.retryable is None
    assert result.readback_status == "unknown"
    assert result.requires_reconciliation is True
    assert result.may_retry_without_reconciliation is False


def test_unknown_reachability_cannot_advertise_blind_retry() -> None:
    result = DeliveryResult.failure(
        "synthetic_chat",
        connector_reached="unknown",
        retryable=True,
        error="sanitized synthetic failure",
    )

    assert result.outcome == "uncertain"
    assert result.retryable is None
    assert result.requires_reconciliation is True
    assert result.may_retry_without_reconciliation is False


def test_success_cannot_coexist_with_confirmed_connector_nonreachability() -> None:
    result = DeliveryResult.from_dict(
        {
            "channel": "synthetic_mail",
            "confirmed": True,
            "connector_reached": "no",
            "outcome": "success",
        }
    )

    assert result.confirmed is False
    assert result.outcome == "uncertain"
    assert result.readback_status == "unknown"
    assert result.requires_reconciliation is True


def test_attempted_record_without_outcome_fails_closed() -> None:
    result = DeliveryResult.from_dict(
        {
            "channel": "synthetic_chat",
            "attempted": True,
            "connector_reached": "yes",
        }
    )

    assert result.confirmed is False
    assert result.outcome == "uncertain"
    assert result.retryable is None
    assert result.requires_reconciliation is True


def test_connector_error_retains_sanitized_failure_classification() -> None:
    error = ConnectorError(
        "sanitized synthetic failure",
        category="delivery",
        transient=True,
        failure_class="safety_checks",
        error_code="blocked",
        connector_reached="unknown",
        outcome="uncertain",
        retryable=False,
    )

    assert error.category == "delivery"
    assert error.transient is True
    assert error.failure_class == "safety_checks"
    assert error.error_code == "blocked"
    assert error.connector_reached == "unknown"
    assert error.outcome == "uncertain"
    assert error.retryable is False


def test_transient_connector_error_with_unknown_reachability_is_uncertain() -> None:
    error = ConnectorError(
        "sanitized synthetic failure",
        category="delivery",
        transient=True,
    )

    assert error.transient is True
    assert error.connector_reached == "unknown"
    assert error.outcome == "uncertain"
    assert error.retryable is None


def test_delivery_contract_forbids_unconfirmed_success_and_blind_retry() -> None:
    shared = (FRAMEWORK / "contracts" / "daily_run.md").read_text(encoding="utf-8")
    industry_runtime = (
        FRAMEWORK / "deployments" / "industry" / "contracts" / "runtime.md"
    ).read_text(encoding="utf-8")
    industry_daily = (
        FRAMEWORK / "deployments" / "industry" / "contracts" / "daily_run.md"
    ).read_text(encoding="utf-8")

    for contract in (shared, industry_runtime, industry_daily):
        assert "confirmed" in contract
        assert "uncertain" in contract
        assert "reconcil" in contract
        assert "pre-dispatch" in contract

    assert "connector link IDs" in shared
    assert "account_selection_unique" not in shared
    assert "exactly one account" in " ".join(industry_runtime.split())
    assert "safety_checks" in industry_daily
