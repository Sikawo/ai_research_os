"""Behavioral regressions for Academic PI contracts, privacy, and CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from Career_Job_Agent_Framework.core.config import ConfigError
from Career_Job_Agent_Framework.core.connectors import DiscoveryBatch
from Career_Job_Agent_Framework.core.models import (
    JobRecord,
    VerificationResult,
    VerificationStatus,
)
from Career_Job_Agent_Framework.deployments.academic_pi.cli import (
    build_connector_bundle,
    main,
    validate_connector_config,
)
from Career_Job_Agent_Framework.deployments.academic_pi.handoff import (
    ContractValidationError,
    build_gatedsprint_handoff,
    validate_schema_payload,
)
from Career_Job_Agent_Framework.deployments.academic_pi.models import (
    AcademicJob,
    AcademicRoleClass,
    AcademicTier,
    IndependenceClass,
)
from Scripts.run_safety_check import (
    EXCLUDED_SEARCH_PREFIXES,
    IMPORTANT_PATHS,
    iter_all_search_files,
    is_relevant_search_path,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = REPO_ROOT / "Career_Job_Agent_Framework" / "deployments" / "academic_pi"


def _verified_job(**overrides: Any) -> JobRecord:
    values: dict[str, Any] = {
        "canonical_id": "requisition:synthetic-university:req-100",
        "title": "Assistant Professor of Biology",
        "institution": "Synthetic University",
        "organization": "Synthetic University",
        "department": "Biology",
        "official_job_id": "REQ-100",
        "official_url": "https://jobs.example.edu/REQ-100",
        "last_verified": "2026-10-04T00:00:00Z",
        "verification_status": VerificationStatus.VERIFIED_OPEN,
        "role_class": AcademicRoleClass.TENURE_TRACK_FACULTY.value,
        "evaluation": {
            "fit_score": 88,
            "tier": AcademicTier.TIER_1.value,
            "strongest_matches": ["direct scientific alignment"],
        },
    }
    values.update(overrides)
    return JobRecord(**values)


def _connector_config() -> dict[str, Any]:
    return {
        "source_catalog": {
            "sources": [
                {
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
            ]
        },
        "connectors": {
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
        },
    }


class _OfficialConnector:
    connector_id = "institution_direct"

    def discover(self, request: Any) -> DiscoveryBatch:
        return DiscoveryBatch.from_jobs(self.connector_id, [])

    def verify(self, job: JobRecord) -> VerificationResult:
        return VerificationResult(
            status=VerificationStatus.VERIFIED_OPEN,
            source_url=job.official_url,
            confidence=1.0,
        )


def test_repo_local_private_fallback_and_runtime_directories_are_ignored() -> None:
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    required = {
        "Career_Job_Agent_Framework/profiles/local/",
        "Career_Job_Agent_Framework/private/",
        "Career_Job_Agent_Framework/state/",
        "Career_Job_Agent_Framework/outputs/",
        "Career_Job_Agent_Framework/reports/private/",
        "Career_Job_Agent_Framework/application_materials/",
        "Career_Job_Agent_Framework/credentials/",
        "Career_Job_Agent_Framework/tokens/",
    }
    assert required.issubset(set(ignore))


def test_safety_scanner_inventories_the_career_job_agent_tree() -> None:
    assert "Career_Job_Agent_Framework" in IMPORTANT_PATHS
    assert is_relevant_search_path(
        "Career_Job_Agent_Framework/deployments/academic_pi/config/connectors.yaml"
    )
    assert "Career_Job_Agent_Framework/profiles/local" in EXCLUDED_SEARCH_PREFIXES
    assert not is_relevant_search_path(
        "Career_Job_Agent_Framework/profiles/local/candidate_profile.yaml"
    )


def test_full_safety_inventory_does_not_read_private_framework_subtrees(
    tmp_path: Path,
) -> None:
    public = tmp_path / "Career_Job_Agent_Framework" / "public.py"
    private = (
        tmp_path
        / "Career_Job_Agent_Framework"
        / "profiles"
        / "local"
        / "candidate_profile.yaml"
    )
    public.parent.mkdir(parents=True)
    private.parent.mkdir(parents=True)
    public.write_text("PUBLIC = True\n", encoding="utf-8")
    private.write_text("private: value\n", encoding="utf-8")

    inventoried = {path.relative_to(tmp_path).as_posix() for path in iter_all_search_files(tmp_path)}
    assert "Career_Job_Agent_Framework/public.py" in inventoried
    assert "Career_Job_Agent_Framework/profiles/local/candidate_profile.yaml" not in inventoried


def test_gatedsprint_handoff_is_schema_valid_and_has_no_submission_claim() -> None:
    payload = build_gatedsprint_handoff(
        _verified_job(),
        evidence=[
            {
                "id": "candidate-evidence:E-1",
                "strength": "strong_direct_evidence",
                "claim": "Authorized direct evidence",
                "authorized": True,
            }
        ],
    )

    validate_schema_payload(payload, "gatedsprint_handoff.schema.json")
    assert payload["schema_version"] == 1
    assert payload["job"]["canonical_job_id"] == "requisition:synthetic-university:req-100"
    assert payload["search"]["normalized_role_class"] == "tenure_track_faculty"
    assert payload["candidate_evidence"]["evidence_refs"] == [
        {
            "ref": "candidate-evidence:E-1",
            "strength": "strong_direct_evidence",
            "note": "Authorized direct evidence",
        }
    ]
    assert payload["application"]["submission_authorized"] is False
    assert "submission_performed" not in json.dumps(payload)


def test_gatedsprint_handoff_fails_closed_on_missing_or_invalid_contract_data() -> None:
    with pytest.raises(ContractValidationError, match="official_url"):
        build_gatedsprint_handoff(
            _verified_job(official_url=None),
            evidence=[{"ref": "E-1", "strength": "uncertain", "authorized": True}],
        )
    with pytest.raises(ContractValidationError, match="evidence_refs"):
        build_gatedsprint_handoff(
            _verified_job(),
            evidence=[{"strength": "strong_direct_evidence", "authorized": True}],
        )
    with pytest.raises(ContractValidationError, match="allowed enum"):
        build_gatedsprint_handoff(
            _verified_job(),
            evidence=[
                {
                    "ref": "E-1",
                    "strength": "unsupported_strength",
                    "authorized": True,
                }
            ],
        )


def test_academic_job_runtime_payload_and_enum_values_match_schema() -> None:
    record = AcademicJob(
        canonical_job_id="job-1",
        institution="Synthetic University",
        raw_title="Assistant Professor of Biology",
        normalized_role_class=AcademicRoleClass.TENURE_TRACK_FACULTY.value,
        official_url="https://jobs.example.edu/REQ-100",
        first_discovered_by="institution_direct",
        independence_class=IndependenceClass.INDEPENDENT.value,
        evaluation={
            "fit_score": 88,
            "fit_confidence": 0.9,
            "tier": AcademicTier.TIER_1,
            "strongest_matches": ["fit"],
        },
    )
    payload = record.to_dict()
    validate_schema_payload(payload, "academic_job.schema.json")
    assert payload["schema_version"] == 1
    assert AcademicJob.from_dict(payload).to_dict() == payload

    schema = json.loads(
        (DEPLOYMENT / "schemas" / "academic_job.schema.json").read_text(encoding="utf-8")
    )
    assert set(schema["$defs"]["roleClass"]["enum"]) == {
        item.value for item in AcademicRoleClass
    }
    assert set(schema["$defs"]["independenceClass"]["enum"]) == {
        item.value for item in IndependenceClass
    }
    assert set(schema["properties"]["evaluation"]["properties"]["tier"]["enum"]) == {
        item.value for item in AcademicTier
    } | {None}
    with pytest.raises(ValueError, match="schema_version"):
        AcademicJob(schema_version=2)
    with pytest.raises(ContractValidationError, match="canonical_job_id"):
        AcademicJob().to_dict()


def test_connector_config_rejects_dynamic_loading_and_cross_reference_errors() -> None:
    config = _connector_config()
    plugin = config["connectors"]["plugins"][0]
    plugin["module"] = "untrusted.module"
    plugin["capabilities"] = ["verification"]
    config["connectors"]["bindings"]["discovery"] = ["missing_source"]
    config["connectors"]["bindings"]["verification"] = None
    config["source_overrides"] = {"sources": {"unknown_board": {"enabled": True}}}

    errors = validate_connector_config(
        config, available_factory_names={"different_factory"}
    )
    joined = "\n".join(errors)
    assert "forbidden dynamic-loading keys" in joined
    assert "not registered in the host allowlist" in joined
    assert "references unknown connector 'missing_source'" in joined
    assert "source_overrides.sources references unknown source 'unknown_board'" in joined
    assert "declares verification but is not bound" in joined

    missing = validate_connector_config(
        {"connectors": {"version": 1, "plugins": [], "bindings": {}}},
        available_factory_names=(),
        require_operational_capabilities=True,
    )
    assert any("discovery or email" in error for error in missing)
    assert any("verification connector" in error for error in missing)


def test_connector_factory_registry_builds_and_checks_declared_capabilities() -> None:
    config = _connector_config()
    seen: list[Mapping[str, Any]] = []

    def factory(definition: Mapping[str, Any]) -> _OfficialConnector:
        seen.append(definition)
        return _OfficialConnector()

    bundle = build_connector_bundle(
        config, connector_factories={"official_v1": factory}
    )
    assert bundle.discovery == (bundle.verification,)
    assert seen[0]["id"] == "institution_direct"

    with pytest.raises(ConfigError, match="not registered in the host allowlist"):
        build_connector_bundle(config, connector_factories={})

    with pytest.raises(ConfigError, match="lacks methods"):
        build_connector_bundle(
            config,
            connector_factories={"official_v1": lambda definition: type(
                "Incomplete", (), {"connector_id": "institution_direct"}
            )()},
        )


def test_cli_constructs_allowlisted_connectors_and_rejects_silent_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    public = tmp_path / "public"
    private = tmp_path / "private"
    public.mkdir()
    private.mkdir()
    (public / "source_catalog.json").write_text(
        json.dumps(_connector_config()["source_catalog"]), encoding="utf-8"
    )
    (public / "connectors.json").write_text(
        json.dumps(_connector_config()["connectors"]), encoding="utf-8"
    )
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
    (private / "candidate_profile.yaml").write_text(
        (DEPLOYMENT / "templates" / "candidate_profile.example.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (private / "preferences.yaml").write_text(
        (DEPLOYMENT / "templates" / "preferences.example.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    argv = [
        "--config",
        str(public),
        "--private-config-dir",
        str(private),
        "--state",
        str(tmp_path / "private-state" / "academic-pi.json"),
        "daily",
    ]
    assert main(argv, connector_factories={"official_v1": lambda definition: _OfficialConnector()}) == 0
    assert "# Academic PI Job Agent" in capsys.readouterr().out

    scan_argv = [*argv[:-1], "scan-source", "unbound_source"]
    assert (
        main(
            scan_argv,
            connector_factories={"official_v1": lambda definition: _OfficialConnector()},
        )
        == 2
    )
    assert "has no bound discovery connector" in capsys.readouterr().err

    (public / "connectors.json").write_text(
        json.dumps({"version": 1, "plugins": [], "bindings": {}}), encoding="utf-8"
    )
    assert main(argv) == 2
    captured = capsys.readouterr()
    assert "requires at least one discovery or email connector" in captured.err


def test_cli_source_contains_no_configuration_driven_import_loader() -> None:
    source = (DEPLOYMENT / "cli.py").read_text(encoding="utf-8")
    assert "importlib" not in source
    assert "__import__" not in source
