from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Scripts.validate_repository_safety import (
    APPROVED_BOOTSTRAP_PATHS,
    validate_tree,
)


class RepositorySafetyTests(unittest.TestCase):
    def make_scaffold(self, root: Path) -> None:
        for relative in APPROVED_BOOTSTRAP_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic public scaffold\n", encoding="utf-8")

        (root / "config" / "autonomous_delivery.json").write_text(
            json.dumps(
                {
                    "enabled": False,
                    "max_git_level": 0,
                    "origin_url": "https://github.com/Sikawo/ai_research_os.git",
                }
            ),
            encoding="utf-8",
        )
        (root / "manifests" / "phase6a_transfer_allowlist.yaml").write_text(
            "status: empty\ndeny_by_default: true\ntransfers: []\n",
            encoding="utf-8",
        )

    def test_exact_synthetic_scaffold_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scaffold(root)
            self.assertEqual(validate_tree(root), [])

    def test_extra_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scaffold(root)
            (root / "unexpected.txt").write_text("synthetic\n", encoding="utf-8")
            self.assertTrue(
                any("outside bootstrap allowlist" in error for error in validate_tree(root))
            )

    def test_local_absolute_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scaffold(root)
            (root / "README.md").write_text(
                "example local path: /" + "Users/example/private\n",
                encoding="utf-8",
            )
            self.assertTrue(
                any("local absolute path" in error for error in validate_tree(root))
            )

    def test_secret_marker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scaffold(root)
            (root / "README.md").write_text(
                "example secret: github_" + "pat_notallowedvalue\n",
                encoding="utf-8",
            )
            self.assertTrue(
                any("GitHub token" in error for error in validate_tree(root))
            )

    def test_autonomous_delivery_must_remain_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scaffold(root)
            manifest = root / "config" / "autonomous_delivery.json"
            manifest.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "max_git_level": 4,
                        "origin_url": "https://github.com/Sikawo/ai_research_os.git",
                    }
                ),
                encoding="utf-8",
            )
            errors = validate_tree(root)
            self.assertIn("autonomous delivery must remain disabled", errors)
            self.assertIn("bootstrap autonomous-delivery ceiling must be 0", errors)


if __name__ == "__main__":
    unittest.main()
