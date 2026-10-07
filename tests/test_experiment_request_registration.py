from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "Scripts" / "register_experiment_from_request.py"


def load_script_module() -> ModuleType:
    scripts_dir = str(REPO_ROOT / "Scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "test_loaded_register_experiment_from_request",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_loaded_register_experiment_from_request"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def request_registration() -> ModuleType:
    return load_script_module()


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "LAB_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (tmp_path / "PROJECT_REGISTRY.md").write_text(
        "# Project Registry\n\n"
        "| project_id | display_name | description | status |\n"
        "|---|---|---|---|\n"
        "| demo_project | Demo project | Synthetic experiments. | active |\n",
        encoding="utf-8",
    )
    (tmp_path / "EXPERIMENT_INDEX.md").write_text(
        "# Experiment index\n\n"
        "## Master index\n\n"
        "| experiment_id | date | project | short_title | status | note_location | "
        "raw_data_location | analysis_location | summary |\n"
        "|---|---|---|---|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    templates = tmp_path / "Templates"
    templates.mkdir()
    templates.joinpath("experiment_summary_template.md").write_text(
        "# Experiment summary: $experiment_id\n\n"
        "$purpose\n\n"
        "$short_title\n\n"
        "$freeform_notes\n\n"
        "$note_location_summary\n"
        "$raw_data_location_summary\n"
        "$processed_data_location_summary\n"
        "$analysis_location_summary\n",
        encoding="utf-8",
    )
    (tmp_path / "Experiments").mkdir()
    return tmp_path


def write_request(repo_root: Path, text: str) -> Path:
    path = repo_root / "request.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def valid_request(
    *,
    project_id: str = "demo_project",
    create_if_missing: str | None = None,
    status: str = "planned",
    short_description: str = "demo_flow",
    raw_path: str = "cloud_storage/synthetic_demo",
) -> str:
    create_line = "" if create_if_missing is None else f"  create_if_missing: {create_if_missing}\n"
    return (
        "project:\n"
        f"  project_id: {project_id}\n"
        "  display_name: Test project\n"
        "  description: Test experiments.\n"
        "  status: active\n"
        f"{create_line}"
        "\n"
        "experiment:\n"
        '  date: "2030-01-03"\n'
        f"  short_description: {short_description}\n"
        f"  status: {status}\n"
        "  purpose: Test request registration.\n"
        "\n"
        "experimental_context:\n"
        "  biological_material: Demo cell line\n"
        "  stimulus: synthetic_compound\n"
        "  assay: flow cytometry\n"
        "  readout: GFP\n"
        "  comparison: treated vs untreated\n"
        "\n"
        "locations:\n"
        "  note_location:\n"
        "    system: GitHub\n"
        "    reference: Experiments/EXP_20300103_demo_flow/summary.md\n"
        "  raw_data_location:\n"
        "    system: Box\n"
        f"    path_or_url: {raw_path}\n"
        "    notes: Raw data stay external.\n"
        "  processed_data_location:\n"
        "    system: N/A\n"
        "    path_or_url: not generated yet\n"
        "  analysis_location:\n"
        "    system: GitHub\n"
        "    path: Analysis/EXP_20300103_demo_flow\n"
        "\n"
        "summary:\n"
        "  short_title: Test request registration\n"
        "  index_summary: Test request registration summary.\n"
        "  freeform_notes: none\n"
    )


def test_valid_request_creates_manifest_summary_and_index_row(
    request_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(repo_root, valid_request())

    result = request_registration.register_from_request(request_path, repo_root)

    experiment_id = "EXP_20300103_demo_flow"
    assert result["experiment_id"] == experiment_id
    assert (repo_root / "Experiments" / experiment_id / "manifest.yaml").is_file()
    assert (repo_root / "Experiments" / experiment_id / "summary.md").is_file()
    index_text = (repo_root / "EXPERIMENT_INDEX.md").read_text(encoding="utf-8")
    assert experiment_id in index_text
    assert "Test request registration summary." in index_text


def test_build_experiment_id_uses_canonical_exp_prefix_and_normalized_slug(
    request_registration: ModuleType,
) -> None:
    experiment_id = request_registration.build_experiment_id(
        "20300104",
        "synthetic delivery feasibility",
    )

    assert experiment_id == "EXP_20300104_synthetic_delivery_feasibility"
    assert experiment_id.startswith("EXP_")
    assert "DEMO-PROJECT" not in experiment_id


def test_create_if_missing_true_adds_missing_project(
    request_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(
        repo_root,
        valid_request(
            project_id="new_demo_project",
            create_if_missing="true",
            short_description="demo_payload_readout",
        ),
    )

    result = request_registration.register_from_request(request_path, repo_root)

    assert result["project_registry_updated"] is True
    registry_text = (repo_root / "PROJECT_REGISTRY.md").read_text(encoding="utf-8")
    assert "| new_demo_project | Test project | Test experiments. | active |" in registry_text


@pytest.mark.parametrize("create_if_missing", [None, "false"])
def test_missing_project_without_create_if_missing_fails(
    request_registration: ModuleType,
    repo_root: Path,
    create_if_missing: str | None,
) -> None:
    request_path = write_request(
        repo_root,
        valid_request(project_id="missing_project", create_if_missing=create_if_missing),
    )

    with pytest.raises(request_registration.RequestValidationError, match="create_if_missing: true"):
        request_registration.register_from_request(request_path, repo_root)


def test_local_absolute_path_is_rejected(
    request_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(
        repo_root,
        valid_request(raw_path="/" + "Users/example/raw_data"),
    )

    with pytest.raises(request_registration.RequestValidationError, match="cloud-relative path"):
        request_registration.register_from_request(request_path, repo_root)


def test_duplicate_experiment_id_is_rejected(
    request_registration: ModuleType,
    repo_root: Path,
) -> None:
    experiment_id = "EXP_20300103_demo_flow"
    (repo_root / "Experiments" / experiment_id).mkdir()
    request_path = write_request(repo_root, valid_request())

    with pytest.raises(request_registration.RequestValidationError, match="overwrite existing folder"):
        request_registration.register_from_request(request_path, repo_root)


def test_invalid_project_id_is_rejected(
    request_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(repo_root, valid_request(project_id="Bad Project"))

    with pytest.raises(ValueError, match="snake_case"):
        request_registration.register_from_request(request_path, repo_root)


def test_invalid_experiment_status_is_rejected(
    request_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(repo_root, valid_request(status="draft"))

    with pytest.raises(request_registration.RequestValidationError, match="Invalid experiment.status"):
        request_registration.register_from_request(request_path, repo_root)
