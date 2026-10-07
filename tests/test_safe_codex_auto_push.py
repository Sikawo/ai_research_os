"""Tests for the codex-auto push dry-run helper."""

from __future__ import annotations

import importlib.util
import io
import subprocess
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


safe_push = load_script_module("safe_codex_auto_push.py")


class TempGitRepo:
    def __init__(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "codex@example.test")
        self.git("config", "user.name", "Codex Test")
        self.git("remote", "add", "origin", "https://example.test/repo.git")

    def cleanup(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def commit_file(self, path: str, content: str, message: str = "test commit") -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git("add", path)
        self.git("commit", "-m", message)

    def checkout_codex_auto(self) -> None:
        self.git("switch", "-c", "codex-auto/test-branch")

    def mark_origin_main(self) -> None:
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def write_approval_packet(self) -> Path:
        packet = self.root.parent / f"{self.root.name}_FINAL_REVIEW_PACKET.md"
        packet.write_text(
            "\n".join(
                [
                    "Safety check: PASS. Python syntax check: PASS. Pytest: PASS.",
                    "Suggested decision: `AUTO-APPROVE CANDIDATE`",
                ]
            ),
            encoding="utf-8",
        )
        return packet


class SafeCodexAutoPushTests(unittest.TestCase):
    def tearDown(self) -> None:
        repo = getattr(self, "repo", None)
        if repo is not None:
            repo.cleanup()

    def make_ready_repo(self) -> tuple[TempGitRepo, Path]:
        self.repo = TempGitRepo()
        self.repo.checkout_codex_auto()
        self.repo.commit_file("Docs/note.md", "hello\n")
        packet = self.repo.write_approval_packet()
        return self.repo, packet

    def test_ready_when_codex_auto_clean_and_packet_approves(self) -> None:
        repo, packet = self.make_ready_repo()

        readiness = safe_push.inspect_push_readiness(repo.root, final_review_packet=packet)

        self.assertEqual(readiness.decision, safe_push.READY)
        self.assertEqual(readiness.reasons, [])
        self.assertEqual(readiness.push_command, "git push -u origin codex-auto/test-branch")

    def test_output_is_dry_run_and_prints_push_command_only_when_ready(self) -> None:
        repo, packet = self.make_ready_repo()
        readiness = safe_push.inspect_push_readiness(repo.root, final_review_packet=packet)
        out = io.StringIO()

        safe_push.print_readiness(readiness, out=out)

        text = out.getvalue()
        self.assertIn("Decision: READY", text)
        self.assertIn("git push -u origin codex-auto/test-branch", text)
        self.assertIn("dry-run only; it did not run git push", text)

    def test_blocks_main_branch(self) -> None:
        self.repo = TempGitRepo()
        self.repo.commit_file("Docs/note.md", "hello\n")
        packet = self.repo.write_approval_packet()

        readiness = safe_push.inspect_push_readiness(self.repo.root, final_review_packet=packet)

        self.assertEqual(readiness.decision, safe_push.BLOCK)
        self.assertIn("current branch is not codex-auto/*", readiness.reasons)

    def test_blocks_dirty_working_tree(self) -> None:
        repo, packet = self.make_ready_repo()
        (repo.root / "Docs" / "dirty.md").write_text("dirty\n", encoding="utf-8")

        readiness = safe_push.inspect_push_readiness(repo.root, final_review_packet=packet)

        self.assertEqual(readiness.decision, safe_push.BLOCK)
        self.assertIn("working tree is not clean", readiness.reasons)

    def test_blocks_missing_final_review_packet(self) -> None:
        repo, _packet = self.make_ready_repo()

        readiness = safe_push.inspect_push_readiness(repo.root)

        self.assertEqual(readiness.decision, safe_push.BLOCK)
        self.assertIn("final review packet was not provided", readiness.reasons)

    def test_ignores_approval_like_text_inside_relevant_diff(self) -> None:
        repo, packet = self.make_ready_repo()
        packet.write_text(
            "\n".join(
                [
                    "Safety check: PASS. Python syntax check: PASS. Pytest: PASS.",
                    "## Relevant Diff",
                    '+    "Suggested decision: `AUTO-APPROVE CANDIDATE`",',
                ]
            ),
            encoding="utf-8",
        )

        readiness = safe_push.inspect_push_readiness(repo.root, final_review_packet=packet)

        self.assertEqual(readiness.decision, safe_push.BLOCK)
        self.assertIn("final review packet does not show safety pass and reviewer approval", readiness.reasons)

    def test_blocks_protected_or_generated_paths_in_head(self) -> None:
        self.repo = TempGitRepo()
        self.repo.checkout_codex_auto()
        self.repo.commit_file("exports/final_review/packet.md", "generated\n")
        packet = self.repo.write_approval_packet()

        readiness = safe_push.inspect_push_readiness(self.repo.root, final_review_packet=packet)

        self.assertEqual(readiness.decision, safe_push.BLOCK)
        self.assertTrue(any("blocked protected/generated paths" in reason for reason in readiness.reasons))

    def test_checks_all_branch_changes_since_origin_main(self) -> None:
        self.repo = TempGitRepo()
        self.repo.commit_file("README.md", "base\n")
        self.repo.mark_origin_main()
        self.repo.checkout_codex_auto()
        self.repo.commit_file("exports/final_review/packet.md", "generated\n")
        self.repo.commit_file("Docs/note.md", "safe\n")
        packet = self.repo.write_approval_packet()

        readiness = safe_push.inspect_push_readiness(self.repo.root, final_review_packet=packet)

        self.assertEqual(readiness.decision, safe_push.BLOCK)
        self.assertIn("exports/final_review/packet.md", readiness.changed_files)
        self.assertIn("Docs/note.md", readiness.changed_files)
        self.assertTrue(any("blocked protected/generated paths" in reason for reason in readiness.reasons))


if __name__ == "__main__":
    unittest.main()
