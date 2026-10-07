from __future__ import annotations

import importlib.util
import os
import subprocess
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


def valid_request(
    *,
    experiment: str = "demo_assay",
    storage: bool = True,
    keep_git: str = "false",
    raw_path: str = "Box/Experiments/EXP_20300102_demo_assay/raw_data",
) -> str:
    storage_block = ""
    if storage:
        storage_block = (
            "\n"
            "storage:\n"
            "  provider: box\n"
            "  mode: synced_folder\n"
            "  create_cloud_folder: true\n"
            "  parent_ref: default_experiments_parent\n"
            "  folder_template: standard_experiment_v1\n"
            "\n"
            "git:\n"
            f"  auto_commit: {keep_git}\n"
            "  auto_push: false\n"
        )
    return (
        "project:\n"
        "  project_id: demo_project\n"
        "  display_name: Demo project\n"
        "  description: Synthetic experiments.\n"
        "  status: active\n"
        "  create_if_missing: false\n"
        "\n"
        "experiment:\n"
        '  date: "2030-01-02"\n'
        f"  short_description: {experiment}\n"
        "  status: planned\n"
        "  purpose: Test downloaded request registration.\n"
        "\n"
        "experimental_context:\n"
        "  biological_material: Demo cell line\n"
        "  stimulus: synthetic stimulus\n"
        "  assay: RNA-FISH\n"
        "  readout: viral RNA puncta\n"
        "  comparison: infected vs mock\n"
        "\n"
        "locations:\n"
        "  note_location:\n"
        "    system: GitHub\n"
        "    reference: Experiments/EXP_20300102_demo_assay/summary.md\n"
        "  raw_data_location:\n"
        "    system: Box\n"
        f"    path_or_url: {raw_path}\n"
        "    notes: Raw data stay external.\n"
        "  processed_data_location:\n"
        "    system: N/A\n"
        "    path_or_url: not generated yet\n"
        "  analysis_location:\n"
        "    system: GitHub\n"
        "    path: Analysis/EXP_20300102_demo_assay\n"
        "\n"
        "summary:\n"
        "  short_title: Synthetic demo assay\n"
        "  index_summary: Planned Synthetic demo assay experiment.\n"
        "  freeform_notes: none\n"
        f"{storage_block}"
    )


def write_config(path: Path, cloud_parent: Path) -> Path:
    config = path / "config.yaml"
    config.write_text(
        "storage:\n"
        "  default_provider: box\n"
        "  box:\n"
        "    mode: synced_folder\n"
        f"    experiments_parent: {cloud_parent}\n"
        "safety:\n"
        "  allowed_cloud_actions:\n"
        "    - create_folder\n"
        "    - create_readme\n",
        encoding="utf-8",
    )
    return config


def test_explicit_yaml_path_registers_creates_cloud_and_deletes_request(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    cloud_parent = tmp_path / "Box" / "Experiments"
    config = write_config(tmp_path, cloud_parent)
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(valid_request(), encoding="utf-8")

    exit_code = research_os.main(["new-exp", str(request), "--yes", "--config", str(config)])

    experiment_id = "EXP_20300102_demo_assay"
    assert exit_code == 0
    assert not request.exists()
    assert (repo_root / "Experiments" / experiment_id / "manifest.yaml").is_file()
    assert (repo_root / "Experiments" / experiment_id / "summary.md").is_file()
    assert (cloud_parent / experiment_id / "README.md").is_file()
    for name in ("raw_data", "analysis_runs", "processed_data", "final_outputs", "docs"):
        assert (cloud_parent / experiment_id / name).is_dir()


def test_keep_request_preserves_yaml(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    config = write_config(tmp_path, tmp_path / "Cloud")
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(valid_request(), encoding="utf-8")

    exit_code = research_os.main(
        ["new-exp", str(request), "--yes", "--keep-request", "--config", str(config)]
    )

    assert exit_code == 0
    assert request.exists()


def test_failure_preserves_yaml_before_writes(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(
        valid_request(raw_path="/" + "Users/example/raw_data"), encoding="utf-8"
    )

    exit_code = research_os.main(["new-exp", str(request), "--yes"])

    assert exit_code == 1
    assert request.exists()
    assert not (repo_root / "Experiments" / "EXP_20300102_demo_assay").exists()


def test_existing_experiment_folder_fails_before_cloud_creation(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    experiment_id = "EXP_20300102_demo_assay"
    (repo_root / "Experiments" / experiment_id).mkdir()
    cloud_parent = tmp_path / "Cloud"
    config = write_config(tmp_path, cloud_parent)
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(valid_request(), encoding="utf-8")

    exit_code = research_os.main(["new-exp", str(request), "--yes", "--config", str(config)])

    assert exit_code == 1
    assert request.exists()
    assert not cloud_parent.exists()


def test_existing_index_row_fails_before_cloud_creation(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    experiment_id = "EXP_20300102_demo_assay"
    index = repo_root / "EXPERIMENT_INDEX.md"
    index.write_text(
        index.read_text(encoding="utf-8")
        + f"| {experiment_id} | 2026-07-08 | demo_project | existing | planned | note | raw | analysis | summary |\n",
        encoding="utf-8",
    )
    cloud_parent = tmp_path / "Cloud"
    config = write_config(tmp_path, cloud_parent)
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(valid_request(), encoding="utf-8")

    exit_code = research_os.main(["new-exp", str(request), "--yes", "--config", str(config)])

    assert exit_code == 1
    assert request.exists()
    assert not cloud_parent.exists()


def test_latest_download_selects_newest_browser_renamed_file(
    research_os: ModuleType,
    tmp_path: Path,
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    older = downloads / "experiment_request_EXP_20300102_demo_assay.yaml"
    newer = downloads / "experiment_request_EXP_20300102_demo_assay (1).yaml"
    older.write_text("old\n", encoding="utf-8")
    newer.write_text("new\n", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    assert research_os.find_latest_download(downloads) == newer


def test_existing_cloud_folder_is_completed_without_overwriting_readme(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    experiment_id = "EXP_20300102_demo_assay"
    cloud_parent = tmp_path / "Cloud"
    cloud_exp = cloud_parent / experiment_id
    cloud_exp.mkdir(parents=True)
    readme = cloud_exp / "README.md"
    readme.write_text("existing readme\n", encoding="utf-8")
    config = write_config(tmp_path, cloud_parent)
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(valid_request(), encoding="utf-8")

    exit_code = research_os.main(["new-exp", str(request), "--yes", "--config", str(config)])

    assert exit_code == 0
    assert readme.read_text(encoding="utf-8") == "existing readme\n"
    for name in ("raw_data", "analysis_runs", "processed_data", "final_outputs", "docs"):
        assert (cloud_exp / name).is_dir()


def test_backward_compatible_request_without_storage_skips_cloud(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(valid_request(storage=False), encoding="utf-8")

    exit_code = research_os.main(["new-exp", str(request), "--yes"])

    assert exit_code == 0
    assert (repo_root / "Experiments" / "EXP_20300102_demo_assay").is_dir()


def test_no_local_absolute_paths_written_to_git_metadata(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    cloud_parent = tmp_path / "Cloud"
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(
        valid_request(storage=False)
        + "\n"
        "storage:\n"
        "  provider: box\n"
        "  mode: synced_folder\n"
        "  create_cloud_folder: true\n"
        f"  parent_path: {cloud_parent}\n",
        encoding="utf-8",
    )

    exit_code = research_os.main(["new-exp", str(request), "--yes"])

    assert exit_code == 0
    generated = [
        repo_root / "Experiments" / "EXP_20300102_demo_assay" / "manifest.yaml",
        repo_root / "Experiments" / "EXP_20300102_demo_assay" / "summary.md",
        repo_root / "EXPERIMENT_INDEX.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in generated)
    assert str(cloud_parent) not in combined
    assert "/" + "Users/" not in combined


class FakeGitRunner:
    def __init__(self, *, pre_staged: list[str] | None = None, branch: str = "main") -> None:
        self.pre_staged = pre_staged or []
        self.branch = branch
        self.calls: list[list[str]] = []
        self.staged: list[str] = list(self.pre_staged)

    def __call__(
        self,
        args: list[str],
        cwd: Path,
        *,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(args, 0, self.branch + "\n", "")
        if args == ["git", "diff", "--cached", "--name-only"]:
            return subprocess.CompletedProcess(args, 0, "\n".join(self.staged) + ("\n" if self.staged else ""), "")
        if args[:3] == ["git", "add", "--"]:
            self.staged = sorted(args[3:])
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "pull"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "commit"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "push"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "unexpected command")


def test_git_preparation_pulls_before_metadata_write(
    research_os: ModuleType,
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(repo_root)
    runner = FakeGitRunner()
    monkeypatch.setattr(research_os, "GitRunner", lambda: runner)
    original_register = research_os.register_from_request

    def recording_register(request_path: Path, root: Path) -> dict[str, object]:
        assert ["git", "pull", "--ff-only"] in runner.calls
        return original_register(request_path, root)

    monkeypatch.setattr(research_os, "register_from_request", recording_register)
    request = tmp_path / "experiment_request_EXP_20300102_demo_assay.yaml"
    request.write_text(valid_request(storage=True, keep_git="true"), encoding="utf-8")
    config = write_config(tmp_path, tmp_path / "Cloud")

    exit_code = research_os.main(["new-exp", str(request), "--yes", "--config", str(config)])

    assert exit_code == 0
    pull_index = runner.calls.index(["git", "pull", "--ff-only"])
    add_index = next(i for i, call in enumerate(runner.calls) if call[:3] == ["git", "add", "--"])
    assert pull_index < add_index


def test_git_preparation_allows_unrelated_unstaged_files(
    research_os: ModuleType,
    tmp_path: Path,
) -> None:
    runner = FakeGitRunner()
    (tmp_path / "unrelated.md").write_text("unstaged local note\n", encoding="utf-8")

    research_os.prepare_git_for_metadata_write(tmp_path, runner=runner)

    assert ["git", "pull", "--ff-only"] in runner.calls


def test_git_preparation_blocks_unrelated_staged_files(
    research_os: ModuleType,
    tmp_path: Path,
) -> None:
    runner = FakeGitRunner(pre_staged=["unrelated.md"])

    with pytest.raises(research_os.CommandError, match="Unrelated staged files"):
        research_os.prepare_git_for_metadata_write(tmp_path, runner=runner)


def test_git_commit_staging_allowlist_uses_only_generated_paths(
    research_os: ModuleType,
    tmp_path: Path,
) -> None:
    runner = FakeGitRunner()
    allowed = [
        "EXPERIMENT_INDEX.md",
        "Experiments/EXP_20300102_demo_assay/manifest.yaml",
        "Experiments/EXP_20300102_demo_assay/summary.md",
    ]

    research_os.commit_generated_paths(
        tmp_path,
        "EXP_20300102_demo_assay",
        allowed,
        auto_push=False,
        runner=runner,
    )

    assert ["git", "add", "--", *sorted(allowed)] in runner.calls
    assert ["git", "add", "."] not in runner.calls


def test_commit_generated_paths_runs_commit_after_allowlist_stage(
    research_os: ModuleType,
    tmp_path: Path,
) -> None:
    runner = FakeGitRunner()

    research_os.commit_generated_paths(
        tmp_path,
        "EXP_20300102_demo_assay",
        ["EXPERIMENT_INDEX.md"],
        auto_push=False,
        runner=runner,
    )

    assert any(call[:2] == ["git", "commit"] for call in runner.calls)


def test_docs_mention_downloadable_yaml_and_one_command() -> None:
    docs = (REPO_ROOT / "Docs" / "experiment_registration_workflow.md").read_text(encoding="utf-8")
    assert "downloadable" in docs
    assert "research-os new-exp" in docs
    assert "heredoc" in docs
