from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "Scripts" / "register_project_from_request.py"


def load_script_module() -> ModuleType:
    scripts_dir = str(REPO_ROOT / "Scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(
        "test_loaded_register_project_from_request",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_loaded_register_project_from_request"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def project_registration() -> ModuleType:
    return load_script_module()


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "LAB_SCHEMA.md").write_text("# schema\n", encoding="utf-8")
    (tmp_path / "EXPERIMENT_INDEX.md").write_text("# Experiment index\n", encoding="utf-8")
    (tmp_path / "PROJECT_REGISTRY.md").write_text(
        "# Project Registry\n\n"
        "This file defines valid project IDs for experiment registration.\n\n"
        "| project_id | display_name | description | status |\n"
        "|---|---|---|---|\n"
        "| demo_project | Demo project | Synthetic experiments. | active |\n",
        encoding="utf-8",
    )
    return tmp_path


def write_request(repo_root: Path, text: str) -> Path:
    path = repo_root / "request.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def valid_request(
    *,
    project_id: str = "example_project",
    status: str = "planned",
    description: str = "One or two sentence project description.",
    notes: str = "Optional short note.",
) -> str:
    return (
        f'project_id: "{project_id}"\n'
        'name: "Example Project"\n'
        f'status: "{status}"\n'
        f'description: "{description}"\n'
        f'notes: "{notes}"\n'
    )


def test_valid_request_appends_one_project_entry(
    project_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(repo_root, valid_request())

    result = project_registration.register_project_from_request(request_path, repo_root)

    registry_text = (repo_root / "PROJECT_REGISTRY.md").read_text(encoding="utf-8")
    assert result["project_id"] == "example_project"
    assert "| example_project | Example Project | One or two sentence project description. | planned |" in registry_text
    assert registry_text.count("example_project") == 1
    assert "demo_project" in registry_text


def test_duplicate_project_id_is_blocked(
    project_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(repo_root, valid_request(project_id="demo_project"))

    with pytest.raises(project_registration.RequestValidationError, match="already exists"):
        project_registration.register_project_from_request(request_path, repo_root)


def test_invalid_non_snake_case_project_id_is_blocked(
    project_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(repo_root, valid_request(project_id="Bad Project"))

    with pytest.raises(project_registration.RequestValidationError, match="snake_case"):
        project_registration.register_project_from_request(request_path, repo_root)


@pytest.mark.parametrize("missing_field", ["project_id", "name", "description"])
def test_missing_required_fields_are_blocked(
    project_registration: ModuleType,
    repo_root: Path,
    missing_field: str,
) -> None:
    lines = [
        line
        for line in valid_request().splitlines()
        if not line.startswith(f"{missing_field}:")
    ]
    request_path = write_request(repo_root, "\n".join(lines) + "\n")

    with pytest.raises(project_registration.RequestValidationError, match=missing_field):
        project_registration.register_project_from_request(request_path, repo_root)


@pytest.mark.parametrize(
    ("description", "notes", "match"),
    [
        ("See /" + "Users/example/project", "", "Local absolute path"),
        ("One sentence.", "API_TOKEN=abc123", "Unsafe value"),
        ("One sentence.", "Use ../private", "Path traversal"),
    ],
)
def test_unsafe_content_is_blocked(
    project_registration: ModuleType,
    repo_root: Path,
    description: str,
    notes: str,
    match: str,
) -> None:
    request_path = write_request(
        repo_root,
        valid_request(description=description, notes=notes),
    )

    with pytest.raises(project_registration.RequestValidationError, match=match):
        project_registration.register_project_from_request(request_path, repo_root)


def test_dry_run_does_not_modify_registry(
    project_registration: ModuleType,
    repo_root: Path,
) -> None:
    request_path = write_request(repo_root, valid_request())
    before = (repo_root / "PROJECT_REGISTRY.md").read_text(encoding="utf-8")

    result = project_registration.register_project_from_request(
        request_path,
        repo_root,
        dry_run=True,
    )

    after = (repo_root / "PROJECT_REGISTRY.md").read_text(encoding="utf-8")
    assert result["dry_run"] is True
    assert before == after


def test_success_output_is_short_and_practical(
    project_registration: ModuleType,
    repo_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = write_request(repo_root, valid_request())
    result = project_registration.register_project_from_request(request_path, repo_root)

    project_registration.print_success(result, repo_root)

    output = capsys.readouterr().out
    assert "Registered project from request." in output
    assert "python3 Scripts/check_daily_metadata_lane.py" in output
    assert len(output.splitlines()) <= 10


def test_script_does_not_run_forbidden_operations() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "subprocess" not in source
    assert "os.system" not in source
    for forbidden in (
        "git add",
        "git commit",
        "git push",
        "git clean",
        "git reset",
        "gh pr",
        "unlink(",
        "rmdir(",
        "replace(",
        "rename(",
    ):
        assert forbidden not in source
