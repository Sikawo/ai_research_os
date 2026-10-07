"""
Non-destructive smoke tests for Scripts/*.py.

Runs subprocesses from the repository root. Does not modify experiments,
EXPERIMENT_INDEX.md, or raw data.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "Scripts"

CANONICAL_CONTEXT_EXPERIMENT = "EXP_20300101_demo"


def run_script(
    script_name: str,
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cwd = cwd or REPO_ROOT
    cmd = [sys.executable, str(SCRIPTS_DIR / script_name)] + args
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


class TestHelpDoesNotCrash(unittest.TestCase):
    """Each CLI script should accept --help and exit 0."""

    SCRIPTS = [
        "register_experiment.py",
        "list_experiments.py",
        "validate_experiments.py",
        "export_experiments_json.py",
        "export_experiment_context.py",
    ]

    def test_help_for_each_script(self) -> None:
        for name in self.SCRIPTS:
            with self.subTest(script=name):
                proc = run_script(name, ["--help"])
                self.assertEqual(
                    proc.returncode,
                    0,
                    msg=f"{name} --help failed: stderr={proc.stderr!r}",
                )
                combined = (proc.stdout or "") + (proc.stderr or "")
                self.assertIn(
                    "usage",
                    combined.casefold(),
                    msg=f"{name} --help output should mention usage; got stdout={proc.stdout!r}",
                )


class TestReadOnlyScriptsOnSyntheticWorkspace(unittest.TestCase):
    """Run read-only tools against a separate synthetic workspace."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        (self.workspace / "LAB_SCHEMA.md").write_text("# Schema\n", encoding="utf-8")
        (self.workspace / "EXPERIMENT_INDEX.md").write_text(
            "# Experiment index\n\n"
            "## Master index\n\n"
            "| experiment_id | date | project | short_title | status | note_location | "
            "raw_data_location | analysis_location | summary |\n"
            "|---|---|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
        (self.workspace / "PROJECT_REGISTRY.md").write_text(
            "# Project Registry\n\n"
            "| project_id | display_name | description | status |\n"
            "|---|---|---|---|\n"
            "| demo_project | Demo project | Synthetic fixture. | active |\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env["RESEARCH_OS_WORKSPACE_ROOT"] = str(self.workspace)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_validate_experiments(self) -> None:
        proc = run_script("validate_experiments.py", [], env=self.env)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)

    def test_list_experiments(self) -> None:
        proc = run_script("list_experiments.py", [], env=self.env)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)

    def test_export_experiments_json_stdout(self) -> None:
        proc = run_script("export_experiments_json.py", [], env=self.env)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIn("generated_at", data)
        self.assertIn("record_count", data)
        self.assertIn("filters", data)
        self.assertIn("experiments", data)
        self.assertIsInstance(data["experiments"], list)


@unittest.skipUnless(
    (REPO_ROOT / "Experiments" / CANONICAL_CONTEXT_EXPERIMENT).is_dir()
    and CANONICAL_CONTEXT_EXPERIMENT in (REPO_ROOT / "EXPERIMENT_INDEX.md").read_text(encoding="utf-8"),
    f"requires {CANONICAL_CONTEXT_EXPERIMENT} folder and index row",
)
class TestExportExperimentContextWhenFixturePresent(unittest.TestCase):
    def test_export_context_stdout(self) -> None:
        proc = run_script("export_experiment_context.py", [CANONICAL_CONTEXT_EXPERIMENT])
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("# Experiment context", proc.stdout)
        self.assertIn(CANONICAL_CONTEXT_EXPERIMENT, proc.stdout)


if __name__ == "__main__":
    unittest.main()
