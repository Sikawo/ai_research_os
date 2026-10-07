"""Operational CLI regressions for strict, durable, privacy-safe execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from Career_Job_Agent_Framework.core.config import ConfigError, load_config_file
from Career_Job_Agent_Framework.deployments.academic_pi.cli import (
    load_academic_config,
    main,
    validate_connector_config,
)
from Career_Job_Agent_Framework.deployments.academic_pi.reports import (
    render_weekly_report,
)
from Career_Job_Agent_Framework.deployments.academic_pi.service import (
    AcademicPiService,
)


DEPLOYMENT = (
    Path(__file__).resolve().parents[1]
    / "Career_Job_Agent_Framework"
    / "deployments"
    / "academic_pi"
)


def _complete_source() -> dict[str, Any]:
    return {
        "id": "institution_direct",
        "name": "Institution Direct",
        "class": "INSTITUTION_DIRECT",
        "base_url": None,
        "regions": ["GLOBAL"],
        "enabled_by_default": True,
        "priority": 100,
        "frequency_class": "medium",
        "discovery_method": "private_target_institution_registry",
        "supports_email_alerts": False,
        "supports_direct_search": True,
        "verification_authority": "official_when_institution_owned",
        "expected_update_cadence": "configured_per_institution",
        "parser_version": 1,
    }


def _write_cli_config(root: Path) -> tuple[Path, Path]:
    public = root / "public"
    private = root / "private"
    public.mkdir()
    private.mkdir()
    (public / "defaults.json").write_text(
        json.dumps(
            {
                "academic_pi": {
                    "automation": {"auto_apply": False},
                    "query_budget": 1,
                }
            }
        ),
        encoding="utf-8",
    )
    (public / "source_catalog.json").write_text(
        json.dumps({"catalog_version": 1, "sources": [_complete_source()]}),
        encoding="utf-8",
    )
    (public / "connectors.json").write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": [
                    {
                        "id": "institution_direct",
                        "factory": "official_v1",
                        "enabled": True,
                        "capabilities": ["discovery", "verification"],
                        "options": {},
                    }
                ],
                "bindings": {
                    "discovery": ["institution_direct"],
                    "verification": "institution_direct",
                    "email": None,
                    "report": [],
                },
            }
        ),
        encoding="utf-8",
    )
    for name in ("candidate_profile", "preferences"):
        (private / f"{name}.yaml").write_text(
            (DEPLOYMENT / "templates" / f"{name}.example.yaml").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
    return public, private


def test_strict_validation_reports_wholly_missing_profile_and_preferences(
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = AcademicPiService(
        config={
            "academic_pi": {"automation": {"auto_apply": False}},
            "source_catalog": {"sources": [_complete_source()]},
        }
    )

    assert main(["validate-config"], service=service) == 2
    output = capsys.readouterr().out
    assert "candidate_profile is required" in output
    assert "preferences is required" in output


def test_standalone_mutation_requires_state_before_connector_construction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    public, private = _write_cli_config(tmp_path)
    factory_calls: list[str] = []

    def factory(declaration: dict[str, Any]) -> object:
        factory_calls.append(str(declaration["id"]))
        return object()

    result = main(
        [
            "--config",
            str(public),
            "--private-config-dir",
            str(private),
            "daily",
        ],
        connector_factories={"official_v1": factory},
    )

    assert result == 2
    assert "requires an explicit durable --state path" in capsys.readouterr().err
    assert factory_calls == []


def test_operational_cli_rejects_incomplete_contract_before_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    public, private = _write_cli_config(tmp_path)
    (private / "candidate_profile.yaml").write_text(
        "profile_version: 999\n", encoding="utf-8"
    )
    factory_calls: list[str] = []

    result = main(
        [
            "--config",
            str(public),
            "--private-config-dir",
            str(private),
            "--state",
            str(tmp_path / "runtime" / "state.json"),
            "daily",
        ],
        connector_factories={
            "official_v1": lambda declaration: factory_calls.append("called")
        },
    )

    assert result == 2
    assert "candidate_profile.identity" in capsys.readouterr().err
    assert factory_calls == []
    assert not (tmp_path / "runtime" / "state.json").exists()


def test_operational_cli_rejects_invalid_query_override_before_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    public, private = _write_cli_config(tmp_path)
    (private / "source_overrides.yaml").write_text(
        "query_generation:\n"
        "  maximum_queries_per_source_per_run: not-an-integer\n",
        encoding="utf-8",
    )
    factory_calls: list[str] = []
    state_path = tmp_path / "runtime" / "state.json"

    result = main(
        [
            "--config",
            str(public),
            "--private-config-dir",
            str(private),
            "--state",
            str(state_path),
            "daily",
        ],
        connector_factories={
            "official_v1": lambda declaration: factory_calls.append("called")
        },
    )

    assert result == 2
    assert "maximum_queries_per_source_per_run" in capsys.readouterr().err
    assert factory_calls == []
    assert not state_path.exists()


def test_partial_programmatic_embedding_requires_explicit_cli_bypass() -> None:
    service = AcademicPiService(
        config={
            "academic_pi": {"automation": {"auto_apply": False}},
            "candidate_profile": {
                "scientific_identity": {"primary_fields": ["SYNTHETIC_FIELD"]}
            },
        }
    )

    assert service.validate_config(strict_contracts=False) == []
    assert service.validate_config(strict_contracts=True)


def test_allow_example_forces_synthetic_overlay_and_reports_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "private"
    private.mkdir()
    (private / "candidate_profile.yaml").write_text(
        "profile_version: 1\nidentity:\n  display_name: PRIVATE_SENTINEL\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACADEMIC_PI_PRIVATE_CONFIG_DIR", str(private))
    monkeypatch.setenv("CAREER_JOB_AGENT_PRIVATE_CONFIG_DIR", str(private))

    config = load_academic_config(allow_example=True)
    assert config["_config"]["overlay_kind"] == "example"
    assert config["candidate_profile"]["identity"]["display_name"] is None
    assert config["connectors"]["bindings"]["discovery"] == []
    assert "PRIVATE_SENTINEL" not in json.dumps(config)

    custom_public = load_academic_config(
        {
            "candidate_profile": {
                "identity": {"display_name": "PUBLIC_SENTINEL"}
            }
        },
        allow_example=True,
    )
    assert custom_public["candidate_profile"]["identity"]["display_name"] is None
    assert "PUBLIC_SENTINEL" not in json.dumps(custom_public)

    assert main(["--allow-example", "validate-config"]) == 0
    output = capsys.readouterr().out
    assert '"overlay_kind": "example"' in output
    assert "PRIVATE_SENTINEL" not in output

    with pytest.raises(ConfigError, match="cannot be combined"):
        load_academic_config(
            private_config_dir=private,
            allow_example=True,
        )


def test_connector_example_is_safe_until_explicitly_enabled() -> None:
    template = load_config_file(DEPLOYMENT / "templates" / "connectors.example.yaml")

    assert validate_connector_config(
        {"connectors": template}, available_factory_names=()
    ) == []
    assert all(plugin["enabled"] is False for plugin in template["plugins"])


def test_weekly_report_keeps_non_email_errors_out_of_email_backlog() -> None:
    report = render_weekly_report(
        errors=[
            {
                "category": "parser_error",
                "message": "synthetic email parse failure",
                "message_id": "synthetic-message",
            },
            {
                "category": "source_unavailable",
                "message": "synthetic source outage",
                "source_id": "synthetic-source",
            },
        ]
    )

    email_section = report.split("## EMAIL BACKLOG / PARSE ERRORS", 1)[1].split(
        "## RUN ERRORS", 1
    )[0]
    run_error_section = report.split("## RUN ERRORS", 1)[1].split("## ", 1)[0]
    assert "synthetic email parse failure" in email_section
    assert "synthetic source outage" not in email_section
    assert "synthetic source outage" in run_error_section


@pytest.mark.parametrize(
    "command",
    [
        ["show", "job-1"],
        ["active"],
        ["deadlines"],
        ["coverage"],
        ["handoff", "job-1", "--evidence-ref", "candidate-evidence:E-1"],
    ],
)
def test_standalone_state_readers_require_durable_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    public, private = _write_cli_config(tmp_path)
    result = main(
        [
            "--config",
            str(public),
            "--private-config-dir",
            str(private),
            *command,
        ],
        connector_factories={"official_v1": lambda definition: object()},
    )

    assert result == 2
    assert "requires an explicit durable --state path" in capsys.readouterr().err


def test_dry_run_does_not_create_a_supplied_missing_state_file(tmp_path: Path) -> None:
    state_path = tmp_path / "private" / "state.json"

    assert (
        main(
            [
                "--allow-example",
                "--state",
                str(state_path),
                "dry-run",
            ]
        )
        == 0
    )
    assert not state_path.exists()


def test_evaluate_requires_verification_connector_before_state_creation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    public, private = _write_cli_config(tmp_path)
    (public / "connectors.json").write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": [
                    {
                        "id": "institution_direct",
                        "factory": "discovery_v1",
                        "enabled": True,
                        "capabilities": ["discovery"],
                        "options": {},
                    }
                ],
                "bindings": {
                    "discovery": ["institution_direct"],
                    "verification": None,
                    "email": None,
                    "report": [],
                },
            }
        ),
        encoding="utf-8",
    )

    class DiscoveryOnly:
        connector_id = "institution_direct"

        def discover(self, request: object) -> list[object]:
            return []

    state_path = tmp_path / "state" / "academic.json"
    result = main(
        [
            "--config",
            str(public),
            "--private-config-dir",
            str(private),
            "--state",
            str(state_path),
            "evaluate",
            "job-1",
        ],
        connector_factories={"discovery_v1": lambda definition: DiscoveryOnly()},
    )

    assert result == 2
    assert "evaluate requires a verification connector" in capsys.readouterr().err
    assert not state_path.exists()


def test_expected_runtime_failure_is_rendered_as_cli_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = AcademicPiService(config=load_academic_config(allow_example=True))

    def fail_evaluation(job: str) -> object:
        raise RuntimeError("fresh official verification required")

    monkeypatch.setattr(service, "evaluate", fail_evaluation)
    assert main(["evaluate", "job-1"], service=service) == 2
    assert "fresh official verification required" in capsys.readouterr().err
