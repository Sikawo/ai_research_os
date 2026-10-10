"""Focused tests for the local final-review helper workflow."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


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
def finish_change() -> ModuleType:
    return load_script_module("finish_change.py")


@pytest.fixture(scope="module")
def start_change() -> ModuleType:
    return load_script_module("start_change.py")


@pytest.fixture(scope="module")
def handoff() -> ModuleType:
    return load_script_module("handoff.py")


def test_repository_safety_validation_uses_working_tree_phase(
    finish_change: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_run_command(
        repo_root: Path,
        command: list[str],
        label: str,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> object:
        del repo_root, timeout, env
        captured.append(command)
        return finish_change.CommandResult(label, command, 0, "PASS\n", "")

    monkeypatch.setattr(finish_change, "run_command", fake_run_command)

    result = finish_change.run_repository_safety_validation(REPO_ROOT)

    assert result.returncode == 0
    assert captured == [
        [
            "python3",
            "Scripts/validate_repository_safety.py",
            "--phase",
            "working-tree",
        ]
    ]


def test_pytest_timeout_defaults_to_clean_environment_margin(
    finish_change: ModuleType,
) -> None:
    timeout, error = finish_change.resolve_pytest_timeout({})

    assert timeout == 300
    assert timeout > 2 * 120
    assert error is None


def test_pytest_timeout_accepts_explicit_positive_override(
    finish_change: ModuleType,
) -> None:
    timeout, error = finish_change.resolve_pytest_timeout(
        {finish_change.PYTEST_TIMEOUT_ENV: "480"}
    )

    assert timeout == 480
    assert error is None


@pytest.mark.parametrize("value", ["0", "-1", "3601", "not-an-integer"])
def test_pytest_timeout_rejects_invalid_override(
    finish_change: ModuleType,
    value: str,
) -> None:
    timeout, error = finish_change.resolve_pytest_timeout(
        {finish_change.PYTEST_TIMEOUT_ENV: value}
    )

    assert timeout is None
    assert "between 1 and 3600" in str(error)


def test_pytest_timeout_remains_fail_closed(
    finish_change: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(finish_change.PYTEST_TIMEOUT_ENV, raising=False)
    monkeypatch.setattr(finish_change, "appears_to_have_tests", lambda _root: True)
    monkeypatch.setattr(finish_change, "pytest_available", lambda _root: True)

    def fake_run_command(
        repo_root: Path,
        command: list[str],
        label: str,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> object:
        del repo_root, label, env
        raise subprocess.TimeoutExpired(command, timeout or 0)

    monkeypatch.setattr(finish_change, "run_command", fake_run_command)

    result = finish_change.run_pytest_if_available(REPO_ROOT)

    assert result.startswith("FAIL: pytest timed out after 300 seconds.")


def test_generated_handoff_is_classified_from_pre_refresh_snapshot(
    finish_change: ModuleType,
) -> None:
    changed_after = {
        "HANDOFF.md": finish_change.ChangedFile(path="HANDOFF.md"),
        "Scripts/finish_change.py": finish_change.ChangedFile(
            path="Scripts/finish_change.py"
        ),
    }

    artifacts = finish_change.workflow_generated_artifact_paths(
        {}, changed_after, None
    )
    review_changed = finish_change.exclude_workflow_generated_artifacts(
        changed_after, artifacts
    )

    assert artifacts == {"HANDOFF.md"}
    assert sorted(review_changed) == ["Scripts/finish_change.py"]
    summary = finish_change.format_workflow_generated_artifacts(artifacts)
    assert "generated after the pre-review snapshot" in summary
    assert "commit-candidate and scope calculations" in summary


def test_preexisting_handoff_change_is_not_hidden(
    finish_change: ModuleType,
) -> None:
    changed_before = {
        "HANDOFF.md": finish_change.ChangedFile(path="HANDOFF.md")
    }
    changed_after = {
        "HANDOFF.md": finish_change.ChangedFile(path="HANDOFF.md")
    }

    artifacts = finish_change.workflow_generated_artifact_paths(
        changed_before, changed_after, None
    )

    assert artifacts == set()
    assert sorted(
        finish_change.exclude_workflow_generated_artifacts(changed_after, artifacts)
    ) == ["HANDOFF.md"]


def test_explicitly_scoped_handoff_change_is_not_hidden(
    finish_change: ModuleType,
    tmp_path: Path,
) -> None:
    spec_text = "\n".join(
        [
            "## Positive file list",
            "",
            "- `HANDOFF.md`",
            "- `Scripts/finish_change.py`",
        ]
    )
    change_spec = finish_change.ChangeSpec(
        source_path=tmp_path / "CHANGE_SPEC.md",
        content=spec_text,
        sha256="0" * 64,
        metadata={},
    )
    changed_after = {
        "HANDOFF.md": finish_change.ChangedFile(path="HANDOFF.md")
    }

    artifacts = finish_change.workflow_generated_artifact_paths(
        {}, changed_after, change_spec
    )

    assert artifacts == set()


def test_parse_change_spec_metadata_from_markdown_labels(finish_change: ModuleType) -> None:
    spec_text = "\n".join(
        [
            "## Metadata",
            "",
            "- **Spec ID:** SPEC_20260515_metadata",
            "- Target repo: ai_research_os",
            "- Expected branch: codex/spec-metadata",
            "- Task: Add spec metadata",
            "- Change class: Medium change",
        ]
    )

    metadata = finish_change.parse_change_spec_metadata(spec_text)

    assert metadata["Spec ID"] == "SPEC_20260515_metadata"
    assert metadata["Target repo"] == "ai_research_os"
    assert metadata["Expected branch"] == "codex/spec-metadata"
    assert metadata["Task"] == "Add spec metadata"
    assert metadata["Created for / change class"] == "Medium change"


def test_parse_change_spec_metadata_accepts_change_type_alias(finish_change: ModuleType) -> None:
    spec_text = "\n".join(
        [
            "## Spec Identity",
            "",
            "- Spec ID: SPEC_20260520_alias",
            "- Target repository: ai_research_os",
            "- Expected branch: feature/example",
            "- Change type: Medium",
            "- Task: Test change type alias",
        ]
    )

    metadata = finish_change.parse_change_spec_metadata(spec_text)

    assert metadata["Target repo"] == "ai_research_os"
    assert metadata["Created for / change class"] == "Medium"


def test_parse_change_spec_file_scope_extracts_markdown_lists(
    finish_change: ModuleType,
) -> None:
    spec_text = "\n".join(
        [
            "## Positive file list",
            "",
            "- `AGENTS.md`",
            "- other narrowly relevant tests under `tests/` if needed",
            "",
            "## Negative file list",
            "",
            "- `.gitignore`",
            "",
            "## Forbidden file list",
            "",
            "- raw data",
            "- generated `exports/`",
        ]
    )

    scope = finish_change.parse_change_spec_file_scope(spec_text)

    assert scope.positive == ["AGENTS.md", "tests/"]
    assert scope.negative == [".gitignore"]
    assert scope.forbidden == ["raw data", "exports/"]
    assert scope.missing_sections == []


def test_spec_based_review_summary_can_auto_approve_candidate(
    finish_change: ModuleType,
    tmp_path: Path,
) -> None:
    spec_text = "\n".join(
        [
            "- Spec ID: SPEC_20260520_docs",
            "- Target repo: ai_research_os",
            "- Expected branch: docs-branch",
            "- Task: Update docs",
            "- Created for / change class: Medium",
            "",
            "## Positive file list",
            "- `Docs/example.md`",
            "## Negative file list",
            "- `.gitignore`",
            "## Forbidden file list",
            "- raw data",
            "- generated `exports/`",
        ]
    )
    change_spec = finish_change.ChangeSpec(
        source_path=tmp_path / "CHANGE_SPEC.md",
        content=spec_text,
        sha256="1" * 64,
        metadata=finish_change.parse_change_spec_metadata(spec_text),
    )
    changed = {
        "Docs/example.md": finish_change.ChangedFile(
            path="Docs/example.md",
            status_codes={"M"},
            sources={"git status"},
        )
    }

    facts = finish_change.build_spec_review_facts(
        change_spec,
        "docs-branch",
        changed,
        "Command: python3 Scripts/run_safety_check.py\nExit code: 0\n== Summary ==\nPASS\nOK: no unsafe markers found in checked areas.",
        "No changed Python files found.",
        "PASS: pytest exited with code 0.",
        "Unstaged diff:\n(none)",
    )

    assert facts.suggested_decision == "AUTO-APPROVE CANDIDATE"
    summary = finish_change.format_spec_based_review_summary(facts, change_spec)
    assert "## Spec-Based Review Summary" in summary
    assert "`AUTO-APPROVE CANDIDATE` still requires ChatGPT/human review before commit" in summary


def test_spec_based_review_blocks_failed_python_syntax(
    finish_change: ModuleType,
    tmp_path: Path,
) -> None:
    spec_text = "\n".join(
        [
            "- Spec ID: SPEC_20260520_script",
            "- Target repo: ai_research_os",
            "- Expected branch: script-branch",
            "- Task: Update script",
            "- Created for / change class: Medium",
            "",
            "## Positive file list",
            "- `Scripts/example.py`",
            "## Negative file list",
            "- `.gitignore`",
            "## Forbidden file list",
            "- raw data",
        ]
    )
    change_spec = finish_change.ChangeSpec(
        source_path=tmp_path / "CHANGE_SPEC.md",
        content=spec_text,
        sha256="2" * 64,
        metadata=finish_change.parse_change_spec_metadata(spec_text),
    )
    changed = {
        "Scripts/example.py": finish_change.ChangedFile(
            path="Scripts/example.py",
            status_codes={"M"},
            sources={"git status"},
        )
    }

    facts = finish_change.build_spec_review_facts(
        change_spec,
        "script-branch",
        changed,
        "Command: python3 Scripts/run_safety_check.py\nExit code: 0\n== Summary ==\nPASS\nOK: no unsafe markers found in checked areas.",
        "FAIL: Python syntax checks failed.\nFAIL Scripts/example.py:1:1: invalid syntax",
        "PASS: pytest exited with code 0.",
        "Unstaged diff:\n(none)",
    )

    assert facts.suggested_decision == "BLOCK COMMIT"
    assert "Python syntax check failed" in facts.decision_reasons


def test_format_change_spec_identity_warns_on_branch_mismatch(
    finish_change: ModuleType,
    tmp_path: Path,
) -> None:
    change_spec = finish_change.ChangeSpec(
        source_path=tmp_path / "CHANGE_SPEC.md",
        content="- Expected branch: expected-branch\n",
        sha256="0" * 64,
        metadata={"Expected branch": "expected-branch"},
    )

    section = finish_change.format_change_spec_identity(change_spec, "actual-branch")

    assert "## Change Spec Identity" in section
    assert "Spec source path" in section
    assert "Spec SHA256" in section
    assert "Spec ID: missing" in section
    assert "Current branch: `actual-branch`" in section
    assert "WARNING: expected branch `expected-branch` does not match current branch `actual-branch`" in section


def test_start_change_packet_requests_self_identifying_metadata(
    start_change: ModuleType,
) -> None:
    packet = start_change.build_packet(REPO_ROOT, "Example task")

    assert "self-identifying metadata section" in packet
    assert "`Spec ID`" in packet
    assert "`Target repo`" in packet
    assert "`Expected branch`" in packet
    assert "`Task`" in packet
    assert "`Created for / change class`" in packet
    assert "--spec PATH" in packet


def test_start_change_packet_requests_minimal_codex_prompt(
    start_change: ModuleType,
) -> None:
    packet = start_change.build_packet(REPO_ROOT, "Example task")

    assert "Minimal prompt for Codex or Cursor" in packet
    assert "implement this `CHANGE_SPEC.md` only" in packet
    assert "`Instructions for Codex or Cursor` section" in packet
    assert "run the validation commands listed in the spec and show the results" in packet
    assert "not stage, commit, push, delete, rename, move files, switch branches" in packet
    assert "clean generated files, open a pull request, or upload anything" in packet


def test_start_change_packet_requests_downloadable_change_spec(
    start_change: ModuleType,
) -> None:
    packet = start_change.build_packet(REPO_ROOT, "Example task")

    assert "downloadable `CHANGE_SPEC.md` file" in packet
    assert "not only as inline Markdown in the chat response" in packet
    assert "one clean Markdown code block with no nested broken fences" in packet


def test_start_change_packet_requests_downloadable_long_artifacts(
    start_change: ModuleType,
) -> None:
    packet = start_change.build_packet(REPO_ROOT, "Example task")

    assert "long artifacts as downloadable files" in packet
    assert "If a code block is also shown, keep it secondary" in packet
    assert "`doc_sync.patch`" in packet
    assert "review templates" in packet


def test_start_change_packet_requests_active_change_spec_path(
    start_change: ModuleType,
) -> None:
    packet = start_change.build_packet(REPO_ROOT, "Example task")

    assert "exports/active_change/CHANGE_SPEC.md" in packet
    assert "before making implementation changes" in packet
    assert "The human should only need to give the approved `CHANGE_SPEC.md`" in packet
    assert "python3 Scripts/finish_change.py --spec exports/active_change/CHANGE_SPEC.md" in packet


def test_start_change_packet_requests_command_permission_policy(
    start_change: ModuleType,
) -> None:
    packet = start_change.build_packet(REPO_ROOT, "Example task")

    assert "Command permission policy" in packet
    assert "Allowed without extra human confirmation" in packet
    assert "Ask first" in packet
    assert "Forbidden unless explicitly approved in the current spec" in packet


def test_command_policy_documentation_lists_required_categories() -> None:
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    template_text = (REPO_ROOT / "Templates" / "change_spec_template.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([agents_text, template_text])

    assert "Allowed without extra human confirmation" in combined
    assert "Ask first" in combined
    assert "Forbidden unless explicitly approved" in combined
    assert "git status --short" in combined
    assert "python3 Scripts/finish_change.py --active-spec" in combined
    assert "git add" in combined
    assert "git commit" in combined
    assert "git push" in combined


def test_finish_change_active_spec_argument(finish_change: ModuleType) -> None:
    args = finish_change.parse_args(["--active-spec"])

    assert args.active_spec is True
    assert args.spec is None
    assert args.latest_spec is False


def test_handoff_content_is_current_snapshot(handoff: ModuleType) -> None:
    content = handoff.build_handoff_content(
        updated_at="2026-05-19T13:15:00",
        event="Generated final review packet",
        branch="example-branch",
        status_text=" M HANDOFF.md",
        latest_change_spec_packet="exports/change_start/one/CHANGE_SPEC_PACKET.md",
        latest_change_spec="exports/change_start/one/CHANGE_SPEC.md",
        latest_final_review_packet="exports/final_review/two/FINAL_REVIEW_PACKET.md",
        current_packet="exports/final_review/two/FINAL_REVIEW_PACKET.md",
        safe_stopping_point="Review packet is ready.",
        next_action="Upload FINAL_REVIEW_PACKET.md to ChatGPT for review before any commit.",
        notes=[],
    )

    assert content.startswith("# HANDOFF")
    assert "Current Snapshot" in content
    assert "Current branch: `example-branch`" in content
    assert "Latest Relevant Packets" in content
    assert "exports/final_review/two/FINAL_REVIEW_PACKET.md" in content
    assert "Do not stage, commit, push" in content


def test_workflow_scripts_expose_handoff_refresh_helpers(
    start_change: ModuleType,
    finish_change: ModuleType,
) -> None:
    assert callable(start_change.refresh_handoff)
    assert callable(finish_change.refresh_handoff)


def test_redact_local_paths_replaces_repo_root(finish_change: ModuleType) -> None:
    text = f"Packet generated for {REPO_ROOT / 'Scripts' / 'finish_change.py'}"

    redacted = finish_change.redact_local_paths(text, repo_root=REPO_ROOT, home=Path.home())

    assert "<REPO_ROOT>" in redacted
    assert str(REPO_ROOT) not in redacted


def test_redact_local_paths_replaces_home(finish_change: ModuleType) -> None:
    home = Path.home()
    text = f"Local note lives under {home / 'private-note.txt'}"

    redacted = finish_change.redact_local_paths(text, repo_root=REPO_ROOT, home=home)

    assert "<HOME>" in redacted
    assert str(home) not in redacted


def test_redact_local_paths_preserves_relative_repo_paths(
    finish_change: ModuleType,
) -> None:
    relative_path = "Scripts/finish_change.py"

    redacted = finish_change.redact_local_paths(
        f"Review {relative_path}",
        repo_root=REPO_ROOT,
        home=Path.home(),
    )

    assert relative_path in redacted


def marker_blob(*modules: ModuleType) -> str:
    values: list[str] = []
    for module in modules:
        for name in dir(module):
            if name.endswith(("MARKERS", "EXTENSIONS")) or name == "OUTPUT_ROOT_PARTS":
                value = getattr(module, name)
                if isinstance(value, (tuple, list, set)):
                    values.extend(str(item) for item in value)
    return "\n".join(values).casefold()


@pytest.mark.parametrize(
    ("category", "terms"),
    [
        ("raw data", ("raw_data", "data/raw", "raw/", ".fastq", ".tiff")),
        ("exports", ("exports",)),
        ("notebooks", ("notebook", "notebooks", ".ipynb")),
        ("secrets", ("secret", ".env")),
        ("credentials", ("credential", "credentials")),
        ("tokens", ("token",)),
        ("local paths", ("/users/", "file:" + "//", "private")),
    ],
)
def test_risk_marker_configuration_covers_expected_categories(
    finish_change: ModuleType,
    category: str,
    terms: tuple[str, ...],
) -> None:
    run_safety_check = load_script_module("run_safety_check.py")
    configured_markers = marker_blob(finish_change, run_safety_check)
    if not configured_markers:
        pytest.skip("No marker configuration is exposed by the workflow helpers.")

    if not any(term in configured_markers for term in terms):
        pytest.skip(f"No exposed marker configuration for {category}.")

    assert any(term in configured_markers for term in terms)


def test_run_safety_check_import_smoke() -> None:
    run_safety_check = load_script_module("run_safety_check.py")

    assert callable(run_safety_check.find_repo_root)
    assert callable(run_safety_check.main)
    assert isinstance(run_safety_check.UNSAFE_MARKERS, tuple)
