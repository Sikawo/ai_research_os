"""Integration checks for the public Phase 12B Review Tools port."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "review-tools"
SKILLS_ROOT = PLUGIN_ROOT / "skills"
TRANSFER_MANIFEST = REPO_ROOT / "manifests" / "phase12b_review_tools_allowlist.yaml"
CANONICAL_SPRINT_ENTRYPOINT = "plugins/gated-sprint/skills/gated-sprint/SKILL.md"


EXACT_COPY_HASHES = {
    "application-review/tests/fixtures/failure-cases/aims_clear_but_significance_missing.md": "97fa3a08628a471973125824534053d969fc00dfa811bd2a412a95a930c12f3f",
    "application-review/tests/fixtures/failure-cases/foundational_concept_treated_as_given.md": "f8eeb14a189a9178a710ea34fd646717d6d756d9183fc2cf968bff734ab498c2",
    "application-review/tests/fixtures/failure-cases/hypothesis_without_citation_should_not_flag.md": "be949f3659725cbe96ae8ac68e47895085d745141c04130175691f911f63cd80",
    "application-review/tests/fixtures/failure-cases/materials_science_prior_knowledge_without_citation.md": "c0e7d13500d61d18792c542e57f936b59b6a3862bab43a7ac1cdc1b837437fb7",
    "application-review/tests/fixtures/failure-cases/missing_background_significance_references.md": "fe0099ad8be947a199e940cb0049d29cb0667739ed6c093fe69d6e648eee794d",
    "application-review/tests/fixtures/failure-cases/paragraph_level_citation_support_should_pass.md": "bb855a3bb5deb3278d793ddbfa253c5bc1c7b2eaab833692934d5cc30414a8fe",
    "application-review/tests/fixtures/failure-cases/preliminary_data_without_external_citation_should_not_flag.md": "543687f15d59370541a00d1085e9e7817d7edd078e42ea6de6f9cca204141f89",
    "application-review/tests/fixtures/failure-cases/prior_knowledge_block_without_citation.md": "3229b233b93b3398ca374f6b367e4ca2a6abfa204e3c686d3e57b346f7acf7dd",
    "application-review/tests/fixtures/serendipity/README.md": "4f9557ea995a6c1a3bbbd8af319ba95226c09dbc9a89727e3cee2a6a17024bed",
    "application-review/tests/fixtures/serendipity/adapter_behavior_cases.md": "d6ab1bb19b844cb9d7cb1e514b65b5cd4779c6e4bc5978b9e117dae77d38092d",
    "application-review/tests/fixtures/serendipity/anomaly_and_convergence_cases.md": "c1a1f964d20e42ac245a8df37f6a0b754c4bd8023bbbb5f1b4685e849744d1b9",
    "application-review/tests/fixtures/serendipity/cross_domain_analogy_cases.md": "3bc7feb1a539d852108033ca4a57604aecd19ffd2433e4f8afb9249f8daf609a",
    "application-review/tests/fixtures/serendipity/human_position_and_change_budget_cases.md": "108b51092f35ea6fabd90856c79c080b4604e2864515f144a7f9dd138ee5bc36",
    "application-review/tests/fixtures/serendipity/memory_and_privacy_cases.md": "90d8498004a02c032e118db2a6440d7d53a33fc31cb51f72f718c84d4e4fade5",
    "application-review/tests/fixtures/serendipity/quadrant_and_coherence_cases.md": "82ceec2622a47ff44a606a9ebe68d8d68a58eea2cbe68f8dda90ab49187b48b6",
    "application-review/tests/fixtures/serendipity/user_burden_and_output_cases.md": "f4430874a4587dda782af9566ff0876aa954637125553cc16ad1b262481b2e25",
}


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def skill_files() -> set[str]:
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in SKILLS_ROOT.rglob("*")
        if path.is_file()
    }


def test_plugin_and_marketplace_are_wired_with_apache_license() -> None:
    plugin = load_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    marketplace = load_json(REPO_ROOT / ".agents" / "plugins" / "marketplace.json")
    assert plugin["name"] == "review-tools"
    assert plugin["version"] == "1.0.0"
    assert plugin["license"] == "Apache-2.0"
    entry = next(item for item in marketplace["plugins"] if item["name"] == "review-tools")
    assert entry["source"]["path"] == "./plugins/review-tools"
    assert entry["policy"]["installation"] == "AVAILABLE"


def test_manifest_exactly_covers_the_classified_transfer() -> None:
    manifest = load_json(TRANSFER_MANIFEST)
    transfers = manifest["transfers"]
    assert isinstance(transfers, list) and len(transfers) == 102
    assert manifest["expected_transfer_count"] == 102
    assert manifest["expected_target_path_count"] == 110
    assert len(manifest["excluded_source_paths"]) == 11
    modes: dict[str, int] = {}
    for item in transfers:
        mode = item["transfer_mode"]
        modes[mode] = modes.get(mode, 0) + 1
    assert modes == {"exact_copy": 16, "adapted_public_copy": 86}
    exact_destinations = {
        Path(item["destination_path"])
        .relative_to("plugins/review-tools/skills")
        .as_posix()
        for item in transfers
        if item["transfer_mode"] == "exact_copy"
    }
    assert exact_destinations == set(EXACT_COPY_HASHES)
    destinations = {item["destination_path"] for item in transfers}
    assert destinations == skill_files()
    assert set(manifest["allowed_target_paths"]) == destinations | set(
        manifest["integration_paths"]
    )


def test_exact_copy_fixture_hashes_are_locked() -> None:
    for relative, expected in EXACT_COPY_HASHES.items():
        digest = hashlib.sha256((SKILLS_ROOT / relative).read_bytes()).hexdigest()
        assert digest == expected, relative


def test_gated_sprint_remains_the_only_sprint_entrypoint() -> None:
    application = (SKILLS_ROOT / "application-review" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "belong exclusively to" in application
    assert "plugins/gated-sprint" not in application
    for path in (SKILLS_ROOT / "reviewer-lens", SKILLS_ROOT / "communication-lens"):
        skill = (path / "SKILL.md").read_text(encoding="utf-8")
        assert "exact bare `Sprint`" not in skill


def test_review_support_files_cannot_activate_or_execute_sprint() -> None:
    subordinate_files = (
        "application-review/references/core/engine.md",
        "application-review/references/core/sprint_engine.md",
        "application-review/references/core/mode_router.md",
        "application-review/references/career-documents/README.md",
        "application-review/references/career-documents/mode_config.md",
        "application-review/references/career-documents/sprint_adapter.md",
    )
    for relative in subordinate_files:
        text = (SKILLS_ROOT / relative).read_text(encoding="utf-8")
        assert CANONICAL_SPRINT_ENTRYPOINT in text, relative
        assert "subordinate" in text.lower(), relative
        assert "does not" in text.lower() or "cannot" in text.lower(), relative

    forbidden_execution_markers = (
        "## User-Facing Interface",
        "## Activation Rules",
        "## Sprint Cycle",
        "## Workflow Selection",
        "Use when the user says:",
        "The user invokes either:",
        "turns the one-word command `Sprint`",
        "`Sprint` runs the full five-step workflow",
    )
    for path in SKILLS_ROOT.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_execution_markers:
            assert marker not in text, f"{marker}: {path.relative_to(REPO_ROOT)}"


def test_public_skills_contain_no_excluded_instance_markers() -> None:
    blocked = (
        "Kojiro",
        "Mukai",
        "RIKEN",
        "KAKENHI",
        "Astellas",
        "AstraZeneca",
        "Genentech",
        "Gilead",
        "Stadtman",
        "reviewer_aliases.md",
        "gated_sprint_adapter.md",
        "gated_sprint_engine.md",
        "Presentation_Style",
    )
    for path in SKILLS_ROOT.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for marker in blocked:
                assert marker not in text, f"{marker}: {path.relative_to(REPO_ROOT)}"


def test_repo_relative_plugin_references_exist() -> None:
    pattern = re.compile(r"plugins/(?:gated-sprint|review-tools)/[A-Za-z0-9_./-]+")
    for path in SKILLS_ROOT.rglob("*"):
        if not path.is_file():
            continue
        for match in pattern.findall(path.read_text(encoding="utf-8")):
            relative = match.rstrip(".:)")
            assert (REPO_ROOT / relative).exists(), (
                f"missing reference {relative} in {path.relative_to(REPO_ROOT)}"
            )
