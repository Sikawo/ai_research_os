from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Scripts.validate_repository_safety import (
    BASELINE_PATHS,
    EXPECTED_PORTED_COUNT,
    EXPECTED_TRANSFER_COUNT,
    GOVERNANCE_PATHS,
    load_manifest,
    validate_manifest,
    validate_tree,
)


class RepositorySafetyTests(unittest.TestCase):
    def manifest(self) -> dict[str, object]:
        governance = sorted(GOVERNANCE_PATHS)
        transfers: list[dict[str, object]] = []
        for index in range(EXPECTED_TRANSFER_COUNT):
            if index < len(governance):
                destination = governance[index]
                status = "ported_offline"
                phase = "6A.0"
            else:
                destination = f"planned/synthetic_{index:03d}.txt"
                status = "planned"
                phase = "6A.1"
            transfers.append(
                {
                    "source_id": "synthetic_source",
                    "source_commit": "a" * 40,
                    "source_path": f"source/synthetic_{index:03d}.txt",
                    "destination_path": destination,
                    "transfer_mode": "exact_copy",
                    "phase": phase,
                    "status": status,
                }
            )
        return {
            "schema_version": 1,
            "manifest_id": "phase6a-transfer-allowlist",
            "status": "approved_for_offline_transfer",
            "deny_by_default": True,
            "sources": {
                "synthetic_source": {
                    "repository": "example/public-source",
                    "commit": "a" * 40,
                    "access_class": "synthetic",
                }
            },
            "rules": {
                "exact_paths_only": True,
                "synthetic_fixtures_only": True,
                "copy_git_history": False,
                "copy_private_values": False,
                "copy_runtime_state": False,
                "copy_connector_bindings": False,
                "copy_scheduled_tasks": False,
                "live_cutover": False,
            },
            "expected_transfer_count": EXPECTED_TRANSFER_COUNT,
            "transfers": transfers,
        }

    def make_tree(self, root: Path) -> None:
        for relative in BASELINE_PATHS | GOVERNANCE_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic public content\n", encoding="utf-8")
        (root / "manifests" / "phase6a_transfer_allowlist.yaml").write_text(
            json.dumps(self.manifest()), encoding="utf-8"
        )

    def test_repository_manifest_has_exact_reviewed_inventory(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest, errors = load_manifest(root)
        self.assertEqual(errors, [])
        self.assertIsNotNone(manifest)
        manifest_errors, destinations, ported = validate_manifest(manifest or {})
        self.assertEqual(manifest_errors, [])
        self.assertEqual(len(destinations), EXPECTED_TRANSFER_COUNT)
        self.assertEqual(len(ported), EXPECTED_PORTED_COUNT)

    def test_exact_synthetic_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            self.assertEqual(validate_tree(root), [])

    def test_extra_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            (root / "unexpected.txt").write_text("synthetic\n", encoding="utf-8")
            self.assertTrue(
                any("outside public allowlist" in error for error in validate_tree(root))
            )

    def test_missing_ported_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            (root / sorted(GOVERNANCE_PATHS)[0]).unlink()
            errors = validate_tree(root)
            self.assertTrue(any("missing required paths" in error for error in errors))
            self.assertTrue(any("marks missing paths as ported" in error for error in errors))

    def test_duplicate_destination_is_rejected(self) -> None:
        manifest = self.manifest()
        transfers = manifest["transfers"]
        assert isinstance(transfers, list)
        transfers[1]["destination_path"] = transfers[0]["destination_path"]
        errors, _, _ = validate_manifest(manifest)
        self.assertTrue(any("duplicate destination path" in error for error in errors))

    def test_unsafe_relative_path_is_rejected(self) -> None:
        manifest = self.manifest()
        transfers = manifest["transfers"]
        assert isinstance(transfers, list)
        transfers[0]["source_path"] = "../private.txt"
        errors, _, _ = validate_manifest(manifest)
        self.assertTrue(any("unsafe source_path" in error for error in errors))

    def test_local_absolute_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
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
            self.make_tree(root)
            (root / "README.md").write_text(
                "example secret: github_" + "pat_notallowedvalue\n",
                encoding="utf-8",
            )
            self.assertTrue(any("GitHub token" in error for error in validate_tree(root)))


if __name__ == "__main__":
    unittest.main()
