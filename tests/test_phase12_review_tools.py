"""Integration checks for the public GatedSprint plugin port."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "gated-sprint"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "gated-sprint"
TRANSFER_MANIFEST = REPO_ROOT / "manifests" / "phase12_review_tools_allowlist.yaml"


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_plugin_and_marketplace_are_wired_with_apache_license() -> None:
    plugin = load_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    marketplace = load_json(REPO_ROOT / ".agents" / "plugins" / "marketplace.json")
    assert plugin["name"] == "gated-sprint"
    assert plugin["version"] == "2.1.0"
    assert plugin["license"] == "Apache-2.0"
    assert plugin["skills"] == "./skills/"
    entry = next(
        item for item in marketplace["plugins"] if item["name"] == "gated-sprint"
    )
    assert entry["source"]["path"] == "./plugins/gated-sprint"
    assert entry["policy"]["installation"] == "AVAILABLE"


def test_transfer_manifest_exactly_covers_package_and_integration_scope() -> None:
    transfer = load_json(TRANSFER_MANIFEST)
    package = load_json(SKILL_ROOT / "skill-package-manifest.json")
    assert transfer["license"] == "Apache-2.0"
    assert transfer["expected_transfer_count"] == 89
    assert transfer["expected_target_path_count"] == 97
    transfers = transfer["transfers"]
    assert isinstance(transfers, list) and len(transfers) == 89
    destinations = {item["destination_path"] for item in transfers}
    package_paths = {
        f"plugins/gated-sprint/skills/gated-sprint/{item['path']}"
        for item in package["files"]
    }
    package_paths.add(
        "plugins/gated-sprint/skills/gated-sprint/skill-package-manifest.json"
    )
    assert destinations == package_paths
    allowed = set(transfer["allowed_target_paths"])
    integrations = set(transfer["integration_paths"])
    assert allowed == destinations | integrations
    modes: dict[str, int] = {}
    for item in transfers:
        mode = item["transfer_mode"]
        modes[mode] = modes.get(mode, 0) + 1
    assert modes == {
        "exact_copy": 85,
        "adapted_public_copy": 3,
        "regenerated_manifest": 1,
    }


def test_skill_metadata_matches_plugin_version_and_invocation_policy() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    agent = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'version: "2.1.0"' in skill
    assert "exact bare `Sprint`" in skill
    assert "GatedSprint" in skill
    assert "allow_implicit_invocation: true" in agent


def test_package_manifest_verifier_passes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "build_skill_manifest.py"),
            "verify",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "files=88" in result.stdout


def test_behavioral_catalog_validator_passes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "run_gatedsprint_evals.py"),
            "validate",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "33 cases" in result.stdout
