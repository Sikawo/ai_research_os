"""Contract tests for the autonomous delivery dry-run helper."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script_module() -> ModuleType:
    script_path = REPO_ROOT / "Scripts" / "autonomous_delivery.py"
    spec = importlib.util.spec_from_file_location("test_loaded_autonomous_delivery", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


delivery = load_script_module()


class TempGitRepo:
    def __init__(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "codex@example.test")
        self.git("config", "user.name", "Codex Test")
        self.git("remote", "add", "origin", "https://example.test/repo.git")
        self.commit_file("AGENTS.md", "# Test policy\n", "base")
        self.commit_file(
            "PR_BODY.md",
            "## Summary\nTest change.\n\n## Files\n- Docs/note.md\n\n"
            "## Validation\nTests pass.\n\n"
            "## Review\nApproved.\n\n## Risk\nLow.\n\n## Rollback\nRevert the commit.\n",
            "add PR body template",
        )
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

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

    def write_file(self, path: str, content: str = "content\n") -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def commit_file(self, path: str, content: str, message: str) -> None:
        self.write_file(path, content)
        self.git("add", "--", path)
        self.git("commit", "-m", message)

    def switch_task_branch(self) -> None:
        self.git("switch", "-c", "agent/test-autonomous-delivery")

    def approval_packet(self) -> Path:
        packet = self.root.parent / f"{self.root.name}_FINAL_REVIEW_PACKET.md"
        packet.write_text(
            "# Final Review Packet\n\n"
            "## Packet Metadata\n\n- Repository: `<REPO_ROOT>`\n\n"
            "## Git Branch\n\n```\nagent/test-autonomous-delivery\n```\n\n"
            "## Changed Files\n\n```\n? Docs/note.md\n```\n\n"
            "## Human-Readable Summary\n\nSafety check: PASS. Pytest: PASS.\n\n"
            "## Expected Behavior / Review Checklist\n\n"
            "- Intended commit candidate paths: `Docs/note.md`.\n\n"
            "## Change Spec Identity\n\n"
            "- Spec ID: `SPEC_test_autonomous_delivery`\n"
            f"- Target repo: `{self.root.name}`\n"
            "- Expected branch: `agent/test-autonomous-delivery`\n"
            "- Current branch: `agent/test-autonomous-delivery`\n\n"
            "## Spec-Based Review Summary\n\n"
            "- Safety check status: PASS\n"
            "- Python syntax status: PASS\n"
            "- Pytest status: PASS\n"
            "- Unsafe marker status: PASS\n\n"
            "## Safety Check Output\n\n"
            "Command: python3 Scripts/run_safety_check.py\nExit code: 0\nPASS\n\n"
            "## Pytest Output\n\nCommand: python3 -m pytest\nExit code: 0\nPASS\n\n"
            "## Relevant Diff\n\n```diff\n+content\n```\n",
            encoding="utf-8",
        )
        return packet


class AutonomousDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.policy = {
            "schema_version": 1,
            "repository": self.repo.root.name,
            "origin_url": "https://example.test/repo.git",
            "github_repository": "example/test",
            "enabled": True,
            "max_git_level": 4,
            "base_branch": "main",
            "allowed_branch_prefixes": ["agent/", "codex/"],
            "allowed_task_classes": ["documentation", "tests", "workflow"],
            "protected_content_mode": "forbidden",
            "blocked_path_patterns": [".env", "exports/**", "**/*.pem", "**/raw/**"],
            "required_validation_commands": ["python3 Scripts/run_safety_check.py"],
            "policy_documents": ["AGENTS.md"],
            "final_review_command": "python3 Scripts/finish_change.py --active-spec",
            "draft_pr_allowed": True,
            "merge_allowed": False,
            "forbid_force_push": True,
            "forbid_branch_delete": True,
        }
        self.task = {
            "schema_version": 1,
            "task_id": "SPEC_test_autonomous_delivery",
            "repository": self.repo.root.name,
            "task_class": "documentation",
            "change_class": "medium",
            "requested_git_level": 4,
            "base_branch": "main",
            "branch": "agent/test-autonomous-delivery",
            "allowed_paths": ["Docs/note.md"],
            "allowed_new_files": ["Docs/note.md"],
            "review_required_paths": [],
            "forbidden_paths": [".env", "exports/**", "**/raw/**"],
            "protected_content_mode": "none",
            "validation_commands": ["python3 Scripts/run_safety_check.py"],
            "commit_message": "Document autonomous delivery test",
            "pr_title": "Document autonomous delivery test",
            "pr_body_file": "PR_BODY.md",
            "existing_draft_pr_number": None,
        }

    def tearDown(self) -> None:
        self.repo.cleanup()

    def make_dirty_task_branch(self) -> None:
        self.repo.switch_task_branch()
        self.repo.write_file("Docs/note.md")

    def review_record(
        self,
        packet: Path,
        paths: list[str] | None = None,
        verdict: str = "APPROVE",
    ) -> dict[str, object]:
        reviewed_paths = paths or ["Docs/note.md"]
        return {
            "schema_version": 1,
            "task_id": self.task["task_id"],
            "verdict": verdict,
            "reviewed_paths": reviewed_paths,
            "reviewed_snapshot_sha256": delivery.snapshot_sha256(self.repo.root, reviewed_paths),
            "final_review_packet_sha256": delivery.file_sha256(packet),
            "reviewed_base_commit": delivery.merge_base_sha(self.repo.root, self.task["base_branch"]),
            "reviewed_head_commit": delivery.head_sha(self.repo.root),
            "pr_body_path": self.task["pr_body_file"],
            "pr_body_sha256": delivery.file_sha256(self.repo.root / self.task["pr_body_file"]),
        }

    def test_json_schemas_and_examples_preserve_safety_constants(self) -> None:
        policy_schema = json.loads(
            (REPO_ROOT / "Schemas" / "autonomous_delivery.schema.json").read_text(encoding="utf-8")
        )
        task_schema = json.loads(
            (REPO_ROOT / "Schemas" / "autonomous_task_scope.schema.json").read_text(encoding="utf-8")
        )
        review_schema = json.loads(
            (REPO_ROOT / "Schemas" / "autonomous_review.schema.json").read_text(encoding="utf-8")
        )
        policy_example = json.loads(
            (REPO_ROOT / "Templates" / "autonomous_delivery.example.json").read_text(encoding="utf-8")
        )
        task_example = json.loads(
            (REPO_ROOT / "Templates" / "autonomous_task_scope.example.json").read_text(encoding="utf-8")
        )
        review_example = json.loads(
            (REPO_ROOT / "Templates" / "autonomous_review.example.json").read_text(encoding="utf-8")
        )

        self.assertEqual(policy_schema["properties"]["merge_allowed"], {"const": False})
        self.assertEqual(policy_schema["properties"]["forbid_force_push"], {"const": True})
        self.assertIn("forbidden_paths", task_schema["required"])
        self.assertIn("reviewed_snapshot_sha256", review_schema["required"])
        self.assertIn("reviewed_base_commit", review_schema["required"])
        path_pattern = task_schema["$defs"]["relativePattern"]["pattern"]
        self.assertIsNone(re.fullmatch(path_pattern, r"..\secret"))
        delivery.validate_policy(policy_example)
        delivery.validate_task(task_example)
        delivery.validate_review(review_example)

    def test_preflight_ready_for_allowed_feature_branch_change(self) -> None:
        self.make_dirty_task_branch()

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertEqual(assessment.decision, delivery.READY)
        self.assertEqual(assessment.changed_paths, ["Docs/note.md"])
        self.assertEqual(assessment.proposed_commands, [])

    def test_preflight_blocks_main_branch(self) -> None:
        self.repo.write_file("Docs/note.md")

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertEqual(assessment.decision, delivery.BLOCK)
        self.assertTrue(any("does not match task branch" in reason for reason in assessment.reasons))

    def test_preflight_blocks_disabled_repository(self) -> None:
        self.make_dirty_task_branch()
        self.policy["enabled"] = False

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertIn("repository autonomous delivery is disabled", assessment.reasons)

    def test_preflight_blocks_mismatched_origin(self) -> None:
        self.make_dirty_task_branch()
        self.policy["origin_url"] = "https://github.com/example/wrong.git"

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertIn("origin URL does not match repository policy", assessment.reasons)

    def test_preflight_blocks_unclassified_path(self) -> None:
        self.repo.switch_task_branch()
        self.repo.write_file("Docs/unrelated.md")

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertTrue(any("outside task scope" in reason for reason in assessment.reasons))

    def test_preflight_enforces_allowed_new_files_separately(self) -> None:
        self.make_dirty_task_branch()
        self.task["allowed_new_files"] = []

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertTrue(any("outside allowed_new_files" in reason for reason in assessment.reasons))

    def test_preflight_blocks_forbidden_path_even_if_allowed(self) -> None:
        self.repo.switch_task_branch()
        self.repo.write_file(".env", "SECRET=value\n")
        self.task["allowed_paths"].append(".env")
        self.task["allowed_new_files"].append(".env")

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertTrue(any("forbidden patterns" in reason for reason in assessment.reasons))

    def test_recursive_forbidden_patterns_also_match_repository_root(self) -> None:
        self.assertTrue(delivery.path_matches("raw/input.tif", ["**/raw/**"]))
        self.assertTrue(delivery.path_matches("private.pem", ["**/*.pem"]))

    def test_shared_core_blocks_env_even_when_manifests_try_to_allow_it(self) -> None:
        self.repo.switch_task_branch()
        self.repo.write_file(".env", "SECRET=value\n")
        self.policy["blocked_path_patterns"] = ["tmp/**"]
        self.task["forbidden_paths"] = ["tmp/**"]
        self.task["allowed_paths"].append(".env")
        self.task["allowed_new_files"].append(".env")

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertTrue(any("forbidden patterns" in reason for reason in assessment.reasons))

    def test_preflight_blocks_missing_required_validation(self) -> None:
        self.make_dirty_task_branch()
        self.task["validation_commands"] = ["python3 -m pytest"]

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertTrue(any("omits required validation" in reason for reason in assessment.reasons))

    def test_manifest_validation_rejects_unknown_fields(self) -> None:
        self.policy["unexpected_permission"] = True

        with self.assertRaisesRegex(RuntimeError, "unsupported fields"):
            delivery.validate_policy(self.policy)

    def test_preflight_blocks_protected_scope_when_repository_forbids_it(self) -> None:
        self.make_dirty_task_branch()
        self.task["protected_content_mode"] = "explicit_exact_scope"

        assessment = delivery.assess_delivery(self.repo.root, self.policy, self.task, "preflight")

        self.assertIn("task protected-content mode exceeds repository policy", assessment.reasons)

    def test_review_first_pass_prints_only_exact_stage_command(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertEqual(assessment.decision, delivery.READY)
        self.assertEqual(
            assessment.proposed_commands,
            ["git add -- Docs/note.md"],
        )

    def test_review_second_pass_prints_commit_only_for_fully_staged_snapshot(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.git("add", "--", "Docs/note.md")

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertEqual(assessment.decision, delivery.READY)
        self.assertEqual(
            assessment.proposed_commands,
            ["git commit -m 'Document autonomous delivery test'"],
        )

    def test_review_blocks_commit_gate_below_git_level_3(self) -> None:
        self.make_dirty_task_branch()
        self.task["requested_git_level"] = 2
        packet = self.repo.approval_packet()
        review = self.review_record(packet)

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertTrue(any("Git Level 3 or 4" in reason for reason in assessment.reasons))
        self.assertEqual(assessment.proposed_commands, [])

    def test_review_ignores_pass_like_text_inside_relevant_diff(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        packet.write_text(
            "# Final Review Packet\n\n## Relevant Diff\n"
            "+Safety check status: PASS\n+Pytest status: PASS\n",
            encoding="utf-8",
        )
        review = self.review_record(packet)

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertTrue(any("packet structure is incomplete" in reason for reason in assessment.reasons))

    def test_review_rejects_failed_required_command_despite_pass_summary(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        packet.write_text(
            packet.read_text(encoding="utf-8").replace("Exit code: 0", "Exit code: 1", 1),
            encoding="utf-8",
        )
        review = self.review_record(packet)

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertTrue(any("lacks successful output" in reason for reason in assessment.reasons))

    def test_review_rejects_required_command_paired_with_unrelated_success(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        packet.write_text(
            packet.read_text(encoding="utf-8").replace(
                "Command: python3 Scripts/run_safety_check.py\nExit code: 0\nPASS",
                "Command: python3 Scripts/run_safety_check.py\n"
                "Command: python3 -c pass\nExit code: 0\nPASS",
            ),
            encoding="utf-8",
        )
        review = self.review_record(packet)

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertTrue(any("lacks successful output" in reason for reason in assessment.reasons))

    def test_review_blocks_clean_already_committed_branch(self) -> None:
        self.repo.switch_task_branch()
        self.repo.commit_file("Docs/note.md", "content\n", "task")
        packet = self.repo.approval_packet()
        review = self.review_record(packet)

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertIn("review requires uncommitted working-tree changes", assessment.reasons)

    def test_publish_ready_only_after_clean_feature_branch_commit(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.git("add", "--", "Docs/note.md")
        self.repo.git("commit", "-m", "task")

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "publish",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertEqual(assessment.decision, delivery.READY)
        self.assertEqual(
            assessment.proposed_commands[0],
            "git push -u origin agent/test-autonomous-delivery",
        )
        self.assertIn("gh pr create --repo example/test --draft", assessment.proposed_commands[1])

    def test_publish_blocks_dirty_tree(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.git("add", "--", "Docs/note.md")
        self.repo.git("commit", "-m", "task")
        self.repo.write_file("Docs/note.md", "dirty\n")

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "publish",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertIn("working tree is not clean", assessment.reasons)

    def test_output_states_dry_run_and_does_not_execute_proposed_commands(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        before = self.repo.git("status", "--short")
        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )
        out = io.StringIO()

        delivery.print_assessment(assessment, out=out)

        self.assertIn("Dry-run only; no Git or GitHub write action was executed.", out.getvalue())
        self.assertEqual(self.repo.git("status", "--short"), before)

    def test_review_blocks_same_path_modified_after_approval(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.write_file("Docs/note.md", "changed after review\n")

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertIn("reviewed content snapshot does not match current content", assessment.reasons)

    def test_review_blocks_pr_body_modified_after_approval(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.write_file(
            "PR_BODY.md",
            "## Summary\nChanged.\n## Files\nX\n## Validation\nX\n"
            "## Review\nX\n## Risk\nX\n## Rollback\nX\n",
        )
        self.task["allowed_paths"].append("PR_BODY.md")

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertIn("reviewed PR body SHA256 does not match current content", assessment.reasons)

    def test_review_rejects_pr_body_symlink(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        body = self.repo.root / "PR_BODY.md"
        body.unlink()
        blocked_target = self.repo.root / ".env"
        blocked_target.write_text(
            "## Summary\nX\n## Files\nX\n## Validation\nX\n"
            "## Review\nX\n## Risk\nX\n## Rollback\nX\n",
            encoding="utf-8",
        )
        body.symlink_to(blocked_target)

        original_file_sha256 = delivery.file_sha256

        def guarded_file_sha256(path: Path) -> str:
            if path == body:
                raise AssertionError("rejected PR body symlink was read")
            return original_file_sha256(path)

        with mock.patch.object(delivery, "file_sha256", side_effect=guarded_file_sha256):
            assessment = delivery.assess_delivery(
                self.repo.root,
                self.policy,
                self.task,
                "review",
                final_review_packet=packet,
                review_record=review,
            )

        self.assertIn("task PR body file must not be a symlink", assessment.reasons)

    def test_review_blocks_mixed_staged_and_unstaged_state(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.git("add", "--", "Docs/note.md")
        self.repo.write_file("Docs/note.md", "changed after staging\n")

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "review",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertTrue(any("entirely unstaged or entirely staged" in reason for reason in assessment.reasons))

    def test_publish_blocks_more_than_one_commit_after_review(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.git("add", "--", "Docs/note.md")
        self.repo.git("commit", "-m", "temporary secret")
        self.repo.write_file("Docs/note.md", "final content\n")
        review["reviewed_snapshot_sha256"] = delivery.snapshot_sha256(
            self.repo.root, ["Docs/note.md"]
        )
        self.repo.git("add", "--", "Docs/note.md")
        self.repo.git("commit", "-m", "remove temporary secret")

        assessment = delivery.assess_delivery(
            self.repo.root,
            self.policy,
            self.task,
            "publish",
            final_review_packet=packet,
            review_record=review,
        )

        self.assertTrue(any("exactly one commit" in reason for reason in assessment.reasons))

    def test_publish_uses_exact_pr_body_and_existing_draft_path(self) -> None:
        self.make_dirty_task_branch()
        packet = self.repo.approval_packet()
        review = self.review_record(packet)
        self.repo.git("add", "--", "Docs/note.md")
        self.repo.git("commit", "-m", "task")
        self.task["existing_draft_pr_number"] = 42

        existing = {
            "number": 42,
            "isDraft": True,
            "headRefName": self.task["branch"],
            "baseRefName": self.task["base_branch"],
            "url": "https://github.com/example/test/pull/42",
        }
        with mock.patch.object(delivery, "inspect_existing_draft_pr", return_value=existing):
            assessment = delivery.assess_delivery(
                self.repo.root,
                self.policy,
                self.task,
                "publish",
                final_review_packet=packet,
                review_record=review,
            )

        self.assertEqual(assessment.decision, delivery.READY)
        self.assertEqual(
            assessment.proposed_commands[1],
            "gh pr edit 42 --repo example/test --title 'Document autonomous delivery test' "
            "--body-file PR_BODY.md",
        )

    def test_run_git_refuses_write_commands(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "refusing non-read-only git command"):
            delivery.run_git(self.repo.root, ["push", "origin", "main"])
        with self.assertRaisesRegex(RuntimeError, "refusing non-read-only git command"):
            delivery.run_git(self.repo.root, ["branch", "-D", "main"])
        with self.assertRaisesRegex(RuntimeError, "refusing non-read-only git command"):
            delivery.run_git(self.repo.root, ["remote", "set-url", "origin", "bad"])


if __name__ == "__main__":
    unittest.main()
