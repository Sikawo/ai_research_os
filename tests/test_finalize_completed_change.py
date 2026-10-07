"""Focused tests for completed active-spec finalization."""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


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


finalize_change = load_script_module("finalize_completed_change.py")


def write_active_spec(repo_root: Path, spec_id: str = "SPEC_test_finalize") -> Path:
    active_path = repo_root / "exports" / "active_change" / "CHANGE_SPEC.md"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        "\n".join(
            [
                "# Change Spec",
                "",
                "## Metadata",
                "",
                f"- Spec ID: `{spec_id}`",
                "- Target repo: `ai_research_os`",
                "- Task: `Finalize active spec`",
                "- Created for / change class: `Medium workflow change`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return active_path


def write_final_review_packet(repo_root: Path, stamp: str = "20260609_010000") -> Path:
    packet_path = repo_root / "exports" / "final_review" / stamp / "FINAL_REVIEW_PACKET.md"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text("# Final Review Packet\n\nAPPROVE\n", encoding="utf-8")
    return packet_path


class FakeGitRunner:
    def __init__(self, *, status: str = "", tracked_active: bool = False) -> None:
        self.status = status
        self.tracked_active = tracked_active
        self.commands: list[list[str]] = []

    def __call__(self, _repo_root: Path, command: list[str]):
        self.commands.append(command)
        if command == ["git", "status", "--short"]:
            return finalize_change.CommandResult(command, 0, self.status, "")
        if command == [
            "git",
            "ls-files",
            "--error-unmatch",
            "--",
            "exports/active_change/CHANGE_SPEC.md",
        ]:
            stdout = "exports/active_change/CHANGE_SPEC.md\n" if self.tracked_active else ""
            return finalize_change.CommandResult(command, 0 if self.tracked_active else 1, stdout, "")
        if command == ["git", "branch", "--show-current"]:
            return finalize_change.CommandResult(command, 0, "main\n", "")
        if command == ["git", "rev-parse", "--short", "HEAD"]:
            return finalize_change.CommandResult(command, 0, "abc1234\n", "")
        return finalize_change.CommandResult(command, 99, "", "unexpected command")


class FinalizeCompletedChangeTests(unittest.TestCase):
    def test_archives_active_spec_and_latest_final_review_then_clears_active_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            active_path = write_active_spec(repo_root, "SPEC finalize/archive")
            final_review_packet = write_final_review_packet(repo_root)
            runner = FakeGitRunner()
            out = io.StringIO()

            exit_code = finalize_change.finalize_completed_change(
                repo_root,
                archive_active_spec=True,
                runner=runner,
                timestamp="20260609_010203",
                out=out,
            )

            archive_dir = (
                repo_root
                / "exports"
                / "archived_change_specs"
                / "20260609_010203_SPEC_finalize_archive_abc1234"
            )

            self.assertEqual(exit_code, 0)
            self.assertFalse(active_path.exists())
            self.assertFalse((repo_root / "exports" / "active_change").exists())
            self.assertTrue((archive_dir / "CHANGE_SPEC.md").is_file())
            self.assertEqual(
                (archive_dir / "FINAL_REVIEW_PACKET.md").read_text(encoding="utf-8"),
                final_review_packet.read_text(encoding="utf-8"),
            )
            manifest = (archive_dir / "MANIFEST.md").read_text(encoding="utf-8")
            self.assertIn("Archive timestamp: `20260609_010203`", manifest)
            self.assertIn("Branch: `main`", manifest)
            self.assertIn("Latest commit short SHA: `abc1234`", manifest)
            self.assertIn("Spec ID: `SPEC finalize/archive`", manifest)
            self.assertIn("must not be committed", manifest)
            self.assertIn("Archived completed active CHANGE_SPEC.md.", out.getvalue())

            forbidden = {
                ("git", "add"),
                ("git", "commit"),
                ("git", "push"),
                ("git", "pull"),
                ("git", "fetch"),
                ("git", "switch"),
            }
            self.assertFalse(any(tuple(command[:2]) in forbidden for command in runner.commands))

    def test_refuses_dirty_working_tree_without_removing_active_spec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            active_path = write_active_spec(repo_root)
            runner = FakeGitRunner(status=" M Scripts/start_change.py\n")
            out = io.StringIO()

            exit_code = finalize_change.finalize_completed_change(
                repo_root,
                archive_active_spec=True,
                runner=runner,
                timestamp="20260609_010203",
                out=out,
            )

            self.assertEqual(exit_code, 1)
            self.assertTrue(active_path.exists())
            self.assertFalse((repo_root / "exports" / "archived_change_specs").exists())
            self.assertIn("git status --short is not clean", out.getvalue())

    def test_refuses_tracked_active_spec_without_removing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            active_path = write_active_spec(repo_root)
            runner = FakeGitRunner(tracked_active=True)
            out = io.StringIO()

            exit_code = finalize_change.finalize_completed_change(
                repo_root,
                archive_active_spec=True,
                runner=runner,
                timestamp="20260609_010203",
                out=out,
            )

            self.assertEqual(exit_code, 1)
            self.assertTrue(active_path.exists())
            self.assertFalse((repo_root / "exports" / "archived_change_specs").exists())
            self.assertIn("tracked by Git", out.getvalue())

    def test_requires_explicit_archive_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_active_spec(repo_root)
            runner = FakeGitRunner()
            out = io.StringIO()

            exit_code = finalize_change.finalize_completed_change(
                repo_root,
                archive_active_spec=False,
                runner=runner,
                timestamp="20260609_010203",
                out=out,
            )

            self.assertEqual(exit_code, 1)
            self.assertIn("--archive-active-spec", out.getvalue())
            self.assertEqual(runner.commands, [])

    def test_refuses_symlink_active_spec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            active_dir = repo_root / "exports" / "active_change"
            active_dir.mkdir(parents=True)
            target = repo_root / "outside.md"
            target.write_text("# Change Spec\n", encoding="utf-8")
            (active_dir / "CHANGE_SPEC.md").symlink_to(target)
            runner = FakeGitRunner()
            out = io.StringIO()

            exit_code = finalize_change.finalize_completed_change(
                repo_root,
                archive_active_spec=True,
                runner=runner,
                timestamp="20260609_010203",
                out=out,
            )

            self.assertEqual(exit_code, 1)
            self.assertTrue((active_dir / "CHANGE_SPEC.md").is_symlink())
            self.assertIn("not a normal file", out.getvalue())


if __name__ == "__main__":
    unittest.main()
