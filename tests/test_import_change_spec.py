"""Focused tests for importing downloaded change specs."""

from __future__ import annotations

import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


VALID_SPEC = """# Change Spec

## Metadata

- Spec ID: `SPEC_TEST_import_change_spec`
- Target repo: `ai_research_os`
- Expected branch: `main`
- Task: `Test import change spec workflow`
- Created for / change class: `Medium change`

## Goal

Test importing a downloaded spec.
"""


def load_script_module(script_name: str) -> ModuleType:
    script_path = REPO_ROOT / "Scripts" / script_name
    module_name = f"test_loaded_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def import_change_spec() -> ModuleType:
    return load_script_module("import_change_spec.py")


def create_change_start_dir(repo_root: Path, name: str) -> Path:
    path = repo_root / "exports" / "change_start" / name
    path.mkdir(parents=True)
    return path


def test_imports_valid_spec_into_latest_change_start_folder(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    create_change_start_dir(repo_root, "20260515_010000")
    latest = create_change_start_dir(repo_root, "20260515_020000")
    source = tmp_path / "downloaded_CHANGE_SPEC.md"
    source.write_text(VALID_SPEC, encoding="utf-8")

    imported = import_change_spec.import_change_spec(source, repo_root)

    assert imported == latest / "CHANGE_SPEC.md"
    assert imported.read_text(encoding="utf-8") == VALID_SPEC
    assert source.read_text(encoding="utf-8") == VALID_SPEC


def test_validation_rejects_missing_required_metadata(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    latest = create_change_start_dir(repo_root, "20260515_030000")
    source = tmp_path / "not_a_change_spec.md"
    source.write_text("# Change Spec\n\n## Metadata\n\n- Spec ID: SPEC_TEST\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing:"):
        import_change_spec.import_change_spec(source, repo_root)

    assert not (latest / "CHANGE_SPEC.md").exists()


def test_import_does_not_overwrite_without_force(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    latest = create_change_start_dir(repo_root, "20260515_040000")
    target = latest / "CHANGE_SPEC.md"
    target.write_text("existing spec\n", encoding="utf-8")
    source = tmp_path / "downloaded_CHANGE_SPEC.md"
    source.write_text(VALID_SPEC, encoding="utf-8")

    with pytest.raises(RuntimeError, match="--force"):
        import_change_spec.import_change_spec(source, repo_root)

    assert target.read_text(encoding="utf-8") == "existing spec\n"


def test_force_overwrites_existing_target(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    latest = create_change_start_dir(repo_root, "20260515_050000")
    target = latest / "CHANGE_SPEC.md"
    target.write_text("existing spec\n", encoding="utf-8")
    source = tmp_path / "downloaded_CHANGE_SPEC.md"
    source.write_text(VALID_SPEC, encoding="utf-8")

    imported = import_change_spec.import_change_spec(source, repo_root, force=True)

    assert imported == target
    assert target.read_text(encoding="utf-8") == VALID_SPEC


def test_activate_change_spec_copies_active_spec_and_archives_previous(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    active_dir = repo_root / "exports" / "active_change"
    active_dir.mkdir(parents=True)
    previous = active_dir / "CHANGE_SPEC.md"
    previous.write_text("# Change Spec\n\nprevious\n", encoding="utf-8")
    source = tmp_path / "downloaded_CHANGE_SPEC.md"
    source.write_text(VALID_SPEC, encoding="utf-8")

    active, archived, metadata, unsafe_markers = import_change_spec.activate_change_spec(source, repo_root)

    assert active == active_dir / "CHANGE_SPEC.md"
    assert active.read_text(encoding="utf-8") == VALID_SPEC
    assert source.read_text(encoding="utf-8") == VALID_SPEC
    assert archived is not None
    assert archived.parent == repo_root / "exports" / "archived_change_specs"
    assert archived.name.startswith("CHANGE_SPEC_")
    assert archived.read_text(encoding="utf-8") == "# Change Spec\n\nprevious\n"
    assert metadata["Spec ID"] == "SPEC_TEST_import_change_spec"
    assert metadata["Target repo"] == "ai_research_os"
    assert unsafe_markers == []


def test_activate_change_spec_creates_exports_dirs_when_missing(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    source = tmp_path / "downloaded_CHANGE_SPEC.md"
    source.write_text(VALID_SPEC, encoding="utf-8")

    active, archived, _metadata, _unsafe_markers = import_change_spec.activate_change_spec(source, repo_root)

    assert active == repo_root / "exports" / "active_change" / "CHANGE_SPEC.md"
    assert active.read_text(encoding="utf-8") == VALID_SPEC
    assert archived is None
    assert (repo_root / "exports" / "archived_change_specs").is_dir()


def test_next_archive_path_avoids_timestamp_collision(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "exports" / "archived_change_specs"
    archive_dir.mkdir(parents=True)
    first = archive_dir / "CHANGE_SPEC_20260528_010203.md"
    first.write_text("existing\n", encoding="utf-8")

    assert (
        import_change_spec.next_archive_path(archive_dir, timestamp="20260528_010203")
        == archive_dir / "CHANGE_SPEC_20260528_010203_2.md"
    )


def test_active_summary_is_concise_and_includes_next_instruction(
    import_change_spec: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    active = repo_root / "exports" / "active_change" / "CHANGE_SPEC.md"
    archived = repo_root / "exports" / "archived_change_specs" / "CHANGE_SPEC_20260528_010203.md"
    metadata = import_change_spec.parse_metadata(VALID_SPEC)

    import_change_spec.print_active_summary(active, archived, metadata, [], repo_root)

    output = capsys.readouterr().out
    assert "Active spec: exports/active_change/CHANGE_SPEC.md" in output
    assert "Archived previous spec: exports/archived_change_specs/CHANGE_SPEC_20260528_010203.md" in output
    assert "- Spec ID: SPEC_TEST_import_change_spec" in output
    assert "Next instruction: Implement exports/active_change/CHANGE_SPEC.md only." in output
    assert str(tmp_path) not in output


def test_read_source_spec_rejects_non_markdown_file(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    source = tmp_path / "CHANGE_SPEC.txt"
    source.write_text(VALID_SPEC, encoding="utf-8")

    with pytest.raises(RuntimeError, match="Markdown"):
        import_change_spec.read_source_spec(source)


def test_read_source_spec_rejects_huge_file(
    import_change_spec: ModuleType,
    tmp_path: Path,
) -> None:
    source = tmp_path / "CHANGE_SPEC.md"
    source.write_text("x" * (import_change_spec.MAX_CHANGE_SPEC_BYTES + 1), encoding="utf-8")

    with pytest.raises(RuntimeError, match="too large"):
        import_change_spec.read_source_spec(source)


def test_reveal_imported_spec_honors_no_open(
    import_change_spec: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(import_change_spec.sys, "platform", "darwin")
    monkeypatch.setattr(import_change_spec.subprocess, "run", fake_run)

    import_change_spec.reveal_imported_spec(tmp_path / "CHANGE_SPEC.md", no_open=True)

    assert calls == []


def test_reveal_imported_spec_uses_finder_on_macos(
    import_change_spec: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    target = tmp_path / "CHANGE_SPEC.md"
    monkeypatch.setattr(import_change_spec.sys, "platform", "darwin")
    monkeypatch.setattr(import_change_spec.subprocess, "run", fake_run)

    import_change_spec.reveal_imported_spec(target)

    assert calls == [["open", "-R", str(target)]]


def test_import_function_has_no_git_action_side_effects(import_change_spec: ModuleType) -> None:
    source = inspect.getsource(import_change_spec.import_change_spec)

    assert "subprocess" not in source
    assert "git" not in source


def test_active_import_function_has_no_git_action_side_effects(import_change_spec: ModuleType) -> None:
    source = inspect.getsource(import_change_spec.activate_change_spec)

    assert "subprocess" not in source
    assert "git" not in source
