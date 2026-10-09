from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
REMOTE_ACTION = re.compile(r"^\s*-?\s*uses:\s*([^./\s][^@\s]*)@([^\s#]+)", re.MULTILINE)
FULL_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class WorkflowSecurityTests(unittest.TestCase):
    def workflow_files(self) -> list[Path]:
        return sorted((*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")))

    def test_all_workflows_declare_read_only_default_permissions(self) -> None:
        for path in self.workflow_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertRegex(text, r"(?m)^permissions:\n  contents: read$")
                self.assertNotIn("permissions: write-all", text)
                self.assertNotRegex(text, r"(?m)^\s{0,2}contents:\s*write\s*$")

    def test_workflows_are_valid_yaml_mappings(self) -> None:
        for path in self.workflow_files():
            with self.subTest(workflow=path.name):
                self.assertIsInstance(
                    yaml.safe_load(path.read_text(encoding="utf-8")),
                    dict,
                )

    def test_workflows_avoid_privileged_pull_request_target(self) -> None:
        for path in self.workflow_files():
            with self.subTest(workflow=path.name):
                self.assertNotIn("pull_request_target", path.read_text(encoding="utf-8"))

    def test_remote_actions_are_pinned_to_full_commit_shas(self) -> None:
        for path in self.workflow_files():
            text = path.read_text(encoding="utf-8")
            references = REMOTE_ACTION.findall(text)
            with self.subTest(workflow=path.name):
                self.assertTrue(references, "workflow must contain at least one remote Action")
                for action, reference in references:
                    self.assertRegex(
                        reference,
                        FULL_COMMIT_SHA,
                        f"{action} must use an immutable commit SHA",
                    )

    def test_only_codeql_job_receives_security_event_write(self) -> None:
        for path in self.workflow_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                expected = 1 if path.name == "codeql.yml" else 0
                self.assertEqual(text.count("security-events: write"), expected)

    def test_dependabot_monitors_actions_and_python_monthly(self) -> None:
        config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
        updates = config["updates"]
        self.assertEqual(
            {item["package-ecosystem"] for item in updates},
            {"github-actions", "pip"},
        )
        self.assertTrue(all(item["directory"] == "/" for item in updates))
        self.assertTrue(all(item["schedule"]["interval"] == "monthly" for item in updates))


if __name__ == "__main__":
    unittest.main()
