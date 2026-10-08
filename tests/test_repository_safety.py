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
    PHASE12_EXPECTED_INTEGRATION_PATHS,
    PHASE12_EXPECTED_TARGET_COUNT,
    PHASE12_EXPECTED_TRANSFER_COUNT,
    PHASE12_MANIFEST_PATH,
    load_manifest,
    load_phase12_manifest,
    validate_manifest,
    validate_phase12_manifest,
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

    def phase12_manifest(self) -> dict[str, object]:
        transfers: list[dict[str, object]] = []
        for index in range(PHASE12_EXPECTED_TRANSFER_COUNT):
            if index < 85:
                relative = f"tests/fixtures/exact_{index:03d}.json"
                mode = "exact_copy"
            elif index == 85:
                relative = "README.md"
                mode = "adapted_public_copy"
            elif index == 86:
                relative = "tests/test_state_validation.py"
                mode = "adapted_public_copy"
            elif index == 87:
                relative = "tests/test_industry_resume_validation.py"
                mode = "adapted_public_copy"
            else:
                relative = "skill-package-manifest.json"
                mode = "regenerated_manifest"
            transfers.append(
                {
                    "source_id": "gated_sprint_v2_reviewed_package",
                    "source_commit": "d1fc6462fcc5dbdafb527d4ee318d12f84b65a1f",
                    "source_path": f"Application_Review_OS/gated_sprint/v2/{relative}",
                    "destination_path": (
                        f"plugins/gated-sprint/skills/gated-sprint/{relative}"
                    ),
                    "transfer_mode": mode,
                    "phase": "12A",
                    "status": "ported_offline",
                }
            )
        destinations = {item["destination_path"] for item in transfers}
        allowed = sorted(destinations | PHASE12_EXPECTED_INTEGRATION_PATHS)
        return {
            "schema_version": 1,
            "manifest_id": "phase12a-gated-sprint-public-plugin",
            "status": "ported_offline",
            "deny_by_default": True,
            "license": "Apache-2.0",
            "license_authority": "synthetic test authority",
            "target": {
                "repository": "Sikawo/ai_research_os",
                "base_commit": "e09dd53414d6c1bab9c70e8294808e51af3c70ba",
            },
            "sources": {
                "gated_sprint_v2_reviewed_package": {
                    "repository": "Sikawo/personal_research_brain",
                    "commit": "d1fc6462fcc5dbdafb527d4ee318d12f84b65a1f",
                    "package_root": "Application_Review_OS/gated_sprint/v2",
                    "access_class": "synthetic",
                    "source_package_hash": "synthetic-source-hash",
                    "destination_package_hash": "synthetic-destination-hash",
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
            "expected_transfer_count": PHASE12_EXPECTED_TRANSFER_COUNT,
            "expected_target_path_count": PHASE12_EXPECTED_TARGET_COUNT,
            "integration_paths": sorted(PHASE12_EXPECTED_INTEGRATION_PATHS),
            "allowed_target_paths": allowed,
            "transfers": transfers,
        }

    def make_tree(self, root: Path) -> None:
        phase12 = self.phase12_manifest()
        phase12_paths = set(phase12["allowed_target_paths"])
        for relative in BASELINE_PATHS | GOVERNANCE_PATHS | phase12_paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic public content\n", encoding="utf-8")
        (root / "manifests" / "phase6a_transfer_allowlist.yaml").write_text(
            json.dumps(self.manifest()), encoding="utf-8"
        )
        (root / PHASE12_MANIFEST_PATH).write_text(
            json.dumps(phase12), encoding="utf-8"
        )
        package_manifest = (
            root
            / "plugins"
            / "gated-sprint"
            / "skills"
            / "gated-sprint"
            / "skill-package-manifest.json"
        )
        package_manifest.write_text(
            json.dumps(
                {
                    "file_count": 88,
                    "package_hash": "synthetic-destination-hash",
                }
            ),
            encoding="utf-8",
        )

    def test_repository_manifest_has_exact_reviewed_inventory(self) -> None:
        self.assertEqual(EXPECTED_TRANSFER_COUNT, 171)
        root = Path(__file__).resolve().parents[1]
        manifest, errors = load_manifest(root)
        self.assertEqual(errors, [])
        self.assertIsNotNone(manifest)
        manifest_errors, destinations, ported = validate_manifest(manifest or {})
        self.assertEqual(manifest_errors, [])
        self.assertEqual(len(destinations), EXPECTED_TRANSFER_COUNT)
        self.assertEqual(len(ported), EXPECTED_PORTED_COUNT)

        phase12, phase12_errors = load_phase12_manifest(root)
        self.assertEqual(phase12_errors, [])
        self.assertIsNotNone(phase12)
        errors, allowed, destinations = validate_phase12_manifest(phase12 or {})
        self.assertEqual(errors, [])
        self.assertEqual(len(allowed), PHASE12_EXPECTED_TARGET_COUNT)
        self.assertEqual(len(destinations), PHASE12_EXPECTED_TRANSFER_COUNT)

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

    def test_phase12_scope_must_match_transfers_and_integration_paths(self) -> None:
        manifest = self.phase12_manifest()
        allowed = manifest["allowed_target_paths"]
        assert isinstance(allowed, list)
        allowed[-1] = "unexpected.txt"
        errors, _, _ = validate_phase12_manifest(manifest)
        self.assertTrue(
            any("allowed targets must equal" in error for error in errors)
        )

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
