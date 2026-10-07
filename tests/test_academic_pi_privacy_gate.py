"""Release-gate regressions for public-file privacy and secret scanning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Career_Job_Agent_Framework.core.privacy import (
    PrivacyConfigError,
    PrivacyGuard,
)
from Scripts import run_safety_check as safety


def _run_gate(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    names: set[str],
    *,
    tracked_names: set[str] | None = None,
    privacy_config_path: Path | None = None,
) -> safety.CheckResult:
    monkeypatch.setattr(
        safety, "release_candidate_file_names", lambda _root: set(names)
    )
    monkeypatch.setattr(
        safety,
        "tracked_file_names",
        lambda _root: set() if tracked_names is None else set(tracked_names),
    )
    results = safety.CheckResult()
    safety.run_public_release_privacy_check(
        repo_root,
        results,
        privacy_config_path=(str(privacy_config_path) if privacy_config_path else None),
    )
    return results


def test_release_gate_scans_changed_public_file_with_default_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    public = tmp_path / "public.txt"
    synthetic_access_key = "AK" + "IA" + ("A" * 16)
    public.write_text(f"synthetic fixture {synthetic_access_key}\n", encoding="utf-8")

    results = _run_gate(monkeypatch, tmp_path, {"public.txt"})
    output = capsys.readouterr().out

    assert results.errors == ["Public release privacy/secret check failed."]
    assert "access-key shaped content" in output
    assert synthetic_access_key not in output


def test_explicit_config_adds_rules_without_disabling_defaults_or_printing_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    forbidden_literal = "PERSON" + "_TO_BLOCK"
    forbidden_regex = "PROJECT" + r"-\d{4}"
    matching_regex_text = "PROJECT-2042"
    synthetic_access_key = "AK" + "IA" + ("B" * 16)
    public = tmp_path / "public.txt"
    public.write_text(
        f"{forbidden_literal} {matching_regex_text} {synthetic_access_key}\n",
        encoding="utf-8",
    )
    config = tmp_path / "privacy.json"
    config.write_text(
        json.dumps(
            {
                "privacy_guard": {
                    "forbidden_literals": [forbidden_literal],
                    "forbidden_regexes": [forbidden_regex],
                    "include_default_secret_patterns": False,
                }
            }
        ),
        encoding="utf-8",
    )

    results = _run_gate(
        monkeypatch,
        tmp_path,
        {"public.txt"},
        privacy_config_path=config,
    )
    output = capsys.readouterr().out

    assert results.errors
    assert "configured forbidden literal" in output
    assert "configured forbidden pattern" in output
    assert "access-key shaped content" in output
    for private_value in (
        forbidden_literal,
        forbidden_regex,
        matching_regex_text,
        synthetic_access_key,
    ):
        assert private_value not in output


def test_invalid_configured_regex_is_generic_and_does_not_echo_expression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_expression = "(" + "PRIVATE_EXPRESSION"
    config = tmp_path / "privacy.json"
    config.write_text(
        json.dumps({"forbidden_regexes": [private_expression]}),
        encoding="utf-8",
    )

    results = _run_gate(
        monkeypatch,
        tmp_path,
        set(),
        privacy_config_path=config,
    )
    output = capsys.readouterr().out

    assert results.errors == [
        "Public release privacy/secret guard could not be initialized."
    ]
    assert private_expression not in output
    with pytest.raises(PrivacyConfigError) as exc_info:
        PrivacyGuard(forbidden_regexes=[private_expression])
    assert private_expression not in str(exc_info.value)


def test_private_runtime_paths_are_pruned_without_being_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = (
        tmp_path
        / "Career_Job_Agent_Framework"
        / "profiles"
        / "local"
        / "candidate_profile.yaml"
    )
    public = tmp_path / "README.md"
    private.parent.mkdir(parents=True)
    private.write_text("private fixture\n", encoding="utf-8")
    public.write_text("Public fixture\n", encoding="utf-8")
    scanned: list[Path] = []
    original = PrivacyGuard.scan_files

    def recording_scan(self, paths, *, max_bytes=2_000_000):
        materialized = [Path(path) for path in paths]
        scanned.extend(materialized)
        return original(self, materialized, max_bytes=max_bytes)

    monkeypatch.setattr(PrivacyGuard, "scan_files", recording_scan)
    private_relative = private.relative_to(tmp_path).as_posix()

    results = _run_gate(
        monkeypatch,
        tmp_path,
        {private_relative, "README.md"},
    )
    output = capsys.readouterr().out

    assert not results.errors
    assert scanned == [public]
    assert "Skipped 1 local private runtime path" in output


def test_python_syntax_inventory_also_prunes_private_and_protected_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public = tmp_path / "public.py"
    private = tmp_path / "Career_Job_Agent_Framework" / "private" / "local.py"
    protected = tmp_path / "Papers" / "notes.py"
    private.parent.mkdir(parents=True)
    protected.parent.mkdir()
    for path in (public, private, protected):
        path.write_text("VALUE = True\n", encoding="utf-8")
    monkeypatch.setattr(
        safety,
        "changed_file_names",
        lambda _root: {
            "public.py",
            "Career_Job_Agent_Framework/private/local.py",
            "Papers/notes.py",
        },
    )

    assert safety.changed_python_files(tmp_path) == [public]


def test_protected_release_path_blocks_without_opening_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    protected = tmp_path / "Papers" / "private.pdf"
    protected.parent.mkdir()
    protected.write_bytes(b"not opened")
    scanned: list[Path] = []

    def recording_scan(self, paths, *, max_bytes=2_000_000):
        scanned.extend(Path(path) for path in paths)
        return []

    monkeypatch.setattr(PrivacyGuard, "scan_files", recording_scan)
    results = _run_gate(monkeypatch, tmp_path, {"Papers/private.pdf"})
    output = capsys.readouterr().out

    assert results.errors
    assert scanned == []
    assert "contents were not opened" in output


def test_binary_oversize_non_utf8_and_symlink_candidates_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "binary.dat").write_bytes(b"public\x00binary")
    (tmp_path / "oversize.txt").write_bytes(b"A" * (safety.MAX_TEXT_FILE_BYTES + 1))
    (tmp_path / "non-utf8.txt").write_bytes(b"\xff\xfe")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside fixture\n", encoding="utf-8")
    (tmp_path / "linked.txt").symlink_to(outside)

    results = _run_gate(
        monkeypatch,
        tmp_path,
        {"binary.dat", "oversize.txt", "non-utf8.txt", "linked.txt"},
    )
    output = capsys.readouterr().out

    assert results.errors
    for label in (
        "binary or non-text file",
        "file exceeds the privacy scan limit",
        "unreadable or non-UTF-8 file",
        "symbolic link",
    ):
        assert label in output
    assert str(outside) not in output


def test_configured_identifiers_scan_all_tracked_public_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_identifier = "TRACKED_" + "PRIVATE_IDENTIFIER"
    tracked = tmp_path / "tracked.md"
    tracked.write_text(f"public text plus {private_identifier}\n", encoding="utf-8")
    config = tmp_path / "privacy.json"
    config.write_text(
        json.dumps({"forbidden_literals": [private_identifier]}), encoding="utf-8"
    )

    results = _run_gate(
        monkeypatch,
        tmp_path,
        set(),
        tracked_names={"tracked.md"},
        privacy_config_path=config,
    )
    output = capsys.readouterr().out

    assert results.errors == ["Public release privacy/secret check failed."]
    assert "tracked.md: configured forbidden literal" in output
    assert private_identifier not in output


def test_upstream_branch_diff_is_part_of_release_candidate_inventory() -> None:
    assert ["diff", "--name-only", "@{upstream}...HEAD"] in (
        list(args) for args in safety.CHANGED_FILE_GIT_SOURCES
    )


def test_release_gate_fails_closed_when_git_inventory_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_inventory(_root: Path) -> set[str]:
        raise RuntimeError("synthetic private detail")

    monkeypatch.setattr(safety, "release_candidate_file_names", fail_inventory)
    monkeypatch.setattr(safety, "tracked_file_names", lambda _root: set())
    results = safety.CheckResult()

    safety.run_public_release_privacy_check(tmp_path, results)
    output = capsys.readouterr().out

    assert results.errors == ["Public release privacy/secret file inventory failed."]
    assert "synthetic private detail" not in output
