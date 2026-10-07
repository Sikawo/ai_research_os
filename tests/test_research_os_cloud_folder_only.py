from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "Scripts" / "research_os.py"


def load_script_module() -> ModuleType:
    scripts_dir = str(REPO_ROOT / "Scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "test_loaded_research_os",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_loaded_research_os"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def research_os() -> ModuleType:
    return load_script_module()


def test_parser_accepts_cloud_folder_only(research_os: ModuleType) -> None:
    parser = research_os.build_parser()

    args = parser.parse_args(["new-exp", "request.yaml", "--cloud-folder-only", "--yes"])

    assert args.command == "new-exp"
    assert args.request_yaml == "request.yaml"
    assert args.cloud_folder_only is True
    assert args.yes is True


def test_require_cloud_folder_request_rejects_noop_request(research_os: ModuleType) -> None:
    info = research_os.ExperimentRequestInfo(
        request_path=Path("experiment_request_test.yaml"),
        experiment_id="EXP_20260709_test",
        project_id="general_project",
        purpose="Test cloud-folder-only validation.",
        storage={},
        git={},
        cloud_target="none",
    )

    with pytest.raises(research_os.CommandError, match="storage.create_cloud_folder: true"):
        research_os.require_cloud_folder_request(info)


def test_cloud_folder_adapter_creates_standard_layout(research_os: ModuleType, tmp_path: Path) -> None:
    parent = tmp_path / "Box Experiments"
    info = research_os.ExperimentRequestInfo(
        request_path=tmp_path / "experiment_request_test.yaml",
        experiment_id="EXP_20260709_test_cloud_folder",
        project_id="general_project",
        purpose="Test cloud folder creation only.",
        storage={
            "provider": "box",
            "mode": "synced_folder",
            "create_cloud_folder": True,
            "parent_path": str(parent),
        },
        git={"auto_commit": True, "auto_push": True},
        cloud_target="box:configured parent/EXP_20260709_test_cloud_folder",
    )

    research_os.require_cloud_folder_request(info)
    result = research_os.create_cloud_folder_if_requested(info, {})

    exp_dir = parent / "EXP_20260709_test_cloud_folder"
    assert result.experiment_dir == exp_dir
    assert exp_dir.is_dir()
    for child in ("raw_data", "analysis_runs", "processed_data", "final_outputs", "docs"):
        assert (exp_dir / child).is_dir()
    assert (exp_dir / "README.md").is_file()
    assert "Raw data immutability rule" in (exp_dir / "README.md").read_text(encoding="utf-8")

    # Running the storage adapter again should be idempotent and leave existing paths unchanged.
    second_result = research_os.create_cloud_folder_if_requested(info, {})
    assert second_result.created == []
    assert exp_dir in second_result.skipped
