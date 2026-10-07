"""Focused tests for post-final-review commit preparation."""

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


prepare_commit = load_script_module("prepare_commit_after_review.py")


def packet_text(paths_line: str) -> str:
    return "\n".join(
        [
            "# Final Review Packet",
            "",
            "## Expected Behavior / Review Checklist",
            "",
            paths_line,
            "- Generated `exports/final_review/` packets should not be committed.",
            "",
        ]
    )


def write_packet(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_active_spec(repo_root: Path) -> Path:
    active_path = repo_root / "exports" / "active_change" / "CHANGE_SPEC.md"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text("# Change Spec\n\n## Metadata\n\n- Spec ID: `SPEC_test`\n", encoding="utf-8")
    return active_path


class PrepareCommitAfterReviewTests(unittest.TestCase):
    def test_parse_intended_commit_candidate_paths(self) -> None:
        paths, source = prepare_commit.parse_intended_commit_paths(
            packet_text(
                "- Intended commit candidate paths: `Docs/final_review_workflow.md`, `Scripts/tool.py`."
            )
        )

        self.assertEqual(source, "Intended commit candidate paths")
        self.assertEqual(paths, ["Docs/final_review_workflow.md", "Scripts/tool.py"])

    def test_parse_no_repository_files_as_empty(self) -> None:
        paths, source = prepare_commit.parse_intended_commit_paths(
            packet_text("- Intended commit candidate paths: no repository files.")
        )

        self.assertEqual(source, "not found")
        self.assertEqual(paths, [])

    def test_parse_changed_files_fallback_reports_source(self) -> None:
        text = "\n".join(
            [
                "# Final Review Packet",
                "",
                "## Changed Files",
                "",
                "```",
                "M    Docs/final_review_workflow.md [git status]",
                "??   tests/test_prepare_commit_after_review.py [untracked]",
                "```",
                "",
                "## Human-Readable Summary",
            ]
        )

        paths, source = prepare_commit.parse_intended_commit_paths(text)

        self.assertEqual(source, "Changed Files fallback")
        self.assertEqual(
            paths,
            [
                "Docs/final_review_workflow.md",
                "tests/test_prepare_commit_after_review.py",
            ],
        )

    def test_cleanup_refuses_tracked_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            packet = prepare_commit.PacketExpectation(
                packet_path=repo_root / "exports" / "final_review" / "20260516" / "FINAL_REVIEW_PACKET.md",
                expected_paths=["Docs/final_review_workflow.md"],
                source="Intended commit candidate paths",
                content="",
            )
            tracked_file = repo_root / "exports" / "manual_specs" / "CHANGE_SPEC.md"
            tracked_file.parent.mkdir(parents=True)
            tracked_file.write_text("tracked temporary spec\n", encoding="utf-8")

            def fake_runner(_repo_root: Path, command: list[str]):
                self.assertEqual(command, ["git", "ls-files", "exports"])
                return prepare_commit.CommandResult(
                    command,
                    0,
                    "exports/manual_specs/CHANGE_SPEC.md\n",
                    "",
                )

            result = prepare_commit.cleanup_exports(
                repo_root,
                packet,
                " M exports/manual_specs/CHANGE_SPEC.md\n",
                no_clean=False,
                runner=fake_runner,
            )

            self.assertTrue(result.blocked)
            self.assertTrue(tracked_file.exists())
            self.assertTrue(
                any("tracked files exist under exports/" in message for message in result.messages)
            )

    def test_blocked_cleanup_exits_nonzero_even_when_status_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            packet_path = write_packet(
                repo_root / "exports" / "final_review" / "20260516" / "FINAL_REVIEW_PACKET.md",
                packet_text("- Intended commit candidate paths: `Docs/final_review_workflow.md`."),
            )
            executed: list[list[str]] = []

            def fake_runner(_repo_root: Path, command: list[str]):
                executed.append(command)
                if command == ["git", "status", "--short"]:
                    return prepare_commit.CommandResult(command, 0, "", "")
                if command == ["git", "ls-files", "exports"]:
                    return prepare_commit.CommandResult(command, 0, "exports/manual_specs/CHANGE_SPEC.md\n", "")
                return prepare_commit.CommandResult(command, 0, "", "")

            out = io.StringIO()
            exit_code = prepare_commit.prepare_commit_after_review(
                repo_root,
                packet_path=packet_path,
                runner=fake_runner,
                out=out,
            )

            self.assertEqual(exit_code, 1)
            self.assertIn("BLOCK: tracked files exist under exports/; cleanup refused.", out.getvalue())
            self.assertFalse(any(command[:2] == ["git", "add"] for command in executed))

    def test_cleanup_allows_untracked_generated_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            packet = prepare_commit.PacketExpectation(
                packet_path=repo_root / "exports" / "final_review" / "20260516" / "FINAL_REVIEW_PACKET.md",
                expected_paths=["Docs/final_review_workflow.md"],
                source="Intended commit candidate paths",
                content="",
            )
            generated_packet = packet.packet_path
            generated_packet.parent.mkdir(parents=True)
            generated_packet.write_text("packet already parsed\n", encoding="utf-8")

            def fake_runner(_repo_root: Path, command: list[str]):
                self.assertEqual(command, ["git", "ls-files", "exports"])
                return prepare_commit.CommandResult(command, 0, "", "")

            result = prepare_commit.cleanup_exports(
                repo_root,
                packet,
                "?? exports/\n",
                no_clean=False,
                runner=fake_runner,
            )

            self.assertTrue(result.removed)
            self.assertFalse((repo_root / "exports").exists())

    def test_unexpected_non_export_changes_block_commit_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            packet_path = write_packet(
                repo_root / "packet" / "FINAL_REVIEW_PACKET.md",
                packet_text("- Intended commit candidate paths: `Docs/final_review_workflow.md`."),
            )
            executed: list[list[str]] = []

            def fake_runner(_repo_root: Path, command: list[str]):
                executed.append(command)
                if command == ["git", "status", "--short"]:
                    return prepare_commit.CommandResult(
                        command,
                        0,
                        " M Docs/final_review_workflow.md\n M NEXT_ACTIONS.md\n",
                        "",
                    )
                return prepare_commit.CommandResult(command, 0, "", "")

            out = io.StringIO()
            exit_code = prepare_commit.prepare_commit_after_review(
                repo_root,
                packet_path=packet_path,
                no_clean=True,
                runner=fake_runner,
                out=out,
            )

            output = out.getvalue()
            self.assertEqual(exit_code, 1)
            self.assertIn("BLOCK: unexpected non-export changed files remain.", output)
            self.assertIn("NEXT_ACTIONS.md", output)
            self.assertNotIn("git add", output)
            self.assertFalse(
                any(command[:2] in (["git", "add"], ["git", "commit"], ["git", "push"]) for command in executed)
            )

    def test_prints_human_controlled_git_commands_without_executing_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_active_spec(repo_root)
            packet_path = write_packet(
                repo_root / "packet" / "FINAL_REVIEW_PACKET.md",
                packet_text("- Intended commit candidate paths: `Docs/final_review_workflow.md`."),
            )
            executed: list[list[str]] = []

            def fake_runner(_repo_root: Path, command: list[str]):
                executed.append(command)
                if command == ["git", "status", "--short"]:
                    return prepare_commit.CommandResult(command, 0, " M Docs/final_review_workflow.md\n", "")
                return prepare_commit.CommandResult(command, 0, "", "")

            out = io.StringIO()
            exit_code = prepare_commit.prepare_commit_after_review(
                repo_root,
                packet_path=packet_path,
                no_clean=True,
                commit_message="Docs: update final review workflow",
                runner=fake_runner,
                out=out,
            )

            output = out.getvalue()

            self.assertEqual(exit_code, 0)
            self.assertIn("git add -- Docs/final_review_workflow.md", output)
            self.assertIn("git commit -m 'Docs: update final review workflow'", output)
            self.assertIn("git push origin main", output)
            self.assertIn(
                "python3 Scripts/finalize_completed_change.py --archive-active-spec",
                output,
            )

            forbidden = {
                ("git", "add"),
                ("git", "commit"),
                ("git", "push"),
                ("git", "pull"),
                ("git", "fetch"),
            }
            self.assertFalse(any(tuple(command[:2]) in forbidden for command in executed))
            self.assertFalse(
                any("finalize_completed_change.py" in part for command in executed for part in command)
            )

    def test_cleaned_exports_do_not_print_misleading_finalize_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_active_spec(repo_root)
            packet_path = write_packet(
                repo_root / "exports" / "final_review" / "20260516" / "FINAL_REVIEW_PACKET.md",
                packet_text("- Intended commit candidate paths: `Docs/final_review_workflow.md`."),
            )
            status_calls = 0
            executed: list[list[str]] = []

            def fake_runner(_repo_root: Path, command: list[str]):
                nonlocal status_calls
                executed.append(command)
                if command == ["git", "status", "--short"]:
                    status_calls += 1
                    if status_calls == 1:
                        return prepare_commit.CommandResult(
                            command,
                            0,
                            " M Docs/final_review_workflow.md\n?? exports/\n",
                            "",
                        )
                    return prepare_commit.CommandResult(
                        command,
                        0,
                        " M Docs/final_review_workflow.md\n",
                        "",
                    )
                if command == ["git", "ls-files", "exports"]:
                    return prepare_commit.CommandResult(command, 0, "", "")
                return prepare_commit.CommandResult(command, 0, "", "")

            out = io.StringIO()
            exit_code = prepare_commit.prepare_commit_after_review(
                repo_root,
                packet_path=packet_path,
                no_clean=False,
                commit_message="Docs: update final review workflow",
                runner=fake_runner,
                out=out,
            )

            output = out.getvalue()

            self.assertEqual(exit_code, 0)
            self.assertFalse((repo_root / "exports").exists())
            self.assertIn("git add -- Docs/final_review_workflow.md", output)
            self.assertIn("git commit -m 'Docs: update final review workflow'", output)
            self.assertIn("git push origin main", output)
            self.assertNotIn(
                "python3 Scripts/finalize_completed_change.py --archive-active-spec",
                output,
            )
            self.assertIn("Generated exports were already cleaned during prepare", output)

            forbidden = {
                ("git", "add"),
                ("git", "commit"),
                ("git", "push"),
                ("git", "pull"),
                ("git", "fetch"),
            }
            self.assertFalse(any(tuple(command[:2]) in forbidden for command in executed))


if __name__ == "__main__":
    unittest.main()
