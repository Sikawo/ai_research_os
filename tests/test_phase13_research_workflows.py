from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "research-workflows"
MANIFEST_PATH = ROOT / "manifests" / "phase13_research_workflows_allowlist.yaml"

EXACT_COPY_HASHES = {
    "skills/paper-workflow/assets/Paper_Template.md": "f87d45d44032530880a801726b655d1f533cd045c599aa7d6d8802cf2e5a7231",
    "skills/evidence-mode/references/evidence_gated_research_discussion_prompt.md": "ef646c77325bfd75be07386848e1d0d2d5286adaad2d7997377c5f9a2f7458f8",
    "skills/verified-search/references/CHANGELOG.md": "141bc3019c935a51cc8995b81d7c6c18c69ea99b1b6aa98ec51c0ee8225a80d7",
    "skills/verified-search/references/custom_gpt_instructions.md": "d2d352243f8d936378b5915b4b2ed0329672d2ac2e9be25b757fc7e9252e1714",
    "skills/verified-search/references/custom_instructions_free.md": "90e1cceb2476152c2f1958c3aedbdb900e607c1ff1d763e354dbe834a7d69bf4",
    "skills/verified-search/references/custom_instructions_full.md": "7698a0432b1ffcac94efcc913cdb0b68f194459469db20b2737f339e3621976e",
    "skills/verified-search/references/test_cases.md": "7eda14f220ad10eb256e40092f79f817ebe77842c77c651749c9b1083112fe16",
    "skills/verified-search/references/user_experience.md": "be8e33d4b13fd6bd618b28167df3510c20d1f0f63c3048564b3e0633ab387728",
    "skills/verified-search/references/verified_search_core.md": "a9846e2e64d5c2e624dc0c9aa01c82598b0e45fc5b69f4eaba1efd61e7b93a13",
}

SKILLS = {
    "antibody-registry",
    "buycheck",
    "evidence-mode",
    "paper-workflow",
    "pubmed-workflow",
    "reagent-manual",
    "verified-search",
}


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_exact_manifest_and_public_boundaries() -> None:
    manifest = load_manifest()
    transfers = manifest["transfers"]
    assert isinstance(transfers, list)
    modes = [item["transfer_mode"] for item in transfers]
    assert len(transfers) == 65
    assert modes.count("exact_copy") == 9
    assert modes.count("adapted_public_copy") == 56
    assert len(manifest["excluded_source_paths"]) == 5
    assert len(manifest["allowed_target_paths"]) == 74
    assert manifest["rules"]["offline_first"] is True
    assert manifest["rules"]["dry_run_by_default"] is True
    assert manifest["rules"]["external_network_in_tests"] is False
    assert manifest["rules"]["automatic_pdf_access"] is False
    assert manifest["rules"]["automatic_purchase"] is False
    assert all((ROOT / path).is_file() for path in manifest["allowed_target_paths"])


def test_all_seven_skills_have_public_frontmatter() -> None:
    discovered = {path.parent.name for path in (PLUGIN / "skills").glob("*/SKILL.md")}
    assert discovered == SKILLS
    for name in sorted(SKILLS):
        text = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\nname: ")
        assert "\ndescription: " in text.split("---", 2)[1]


def test_exact_copies_match_reviewed_source_hashes() -> None:
    for relative, expected in EXACT_COPY_HASHES.items():
        digest = hashlib.sha256((PLUGIN / relative).read_bytes()).hexdigest()
        assert digest == expected, relative


def test_plugin_registration_and_metadata() -> None:
    metadata = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    assert metadata["name"] == "research-workflows"
    assert metadata["license"] == "Apache-2.0"
    marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    names = [entry["name"] for entry in marketplace["plugins"]]
    assert names.count("research-workflows") == 1


def test_no_local_path_or_file_url_marker_in_plugin() -> None:
    local_prefix = "/" + "Users/"
    file_url = "file:" + "//"
    manifest = load_manifest()
    for relative in manifest["allowed_target_paths"]:
        if not relative.startswith("plugins/research-workflows/"):
            continue
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        assert local_prefix not in text, path
        assert file_url not in text, path


def test_adapted_markdown_links_resolve() -> None:
    exact_paths = {PLUGIN / relative for relative in EXACT_COPY_HASHES}
    for path in PLUGIN.rglob("*.md"):
        if path in exact_paths:
            continue
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            assert (path.parent / relative).resolve().exists(), (path, target)


def test_verified_search_historical_paths_have_public_plugin_mappings() -> None:
    wrapper = (PLUGIN / "skills" / "verified-search" / "SKILL.md").read_text(encoding="utf-8")
    mappings = {
        "`references/README.md`": PLUGIN / "skills" / "verified-search" / "SKILL.md",
        "`Scripts/validate_verified_search_deployments.py`": (
            PLUGIN / "skills" / "verified-search" / "scripts" / "validate_deployments.py"
        ),
        "`AI_INSTRUCTIONS.md`": PLUGIN / "skills" / "verified-search" / "SKILL.md",
    }
    for historical, public_target in mappings.items():
        assert historical in wrapper
        assert public_target.is_file()
    assert "`scripts/validate_deployments.py`" in wrapper
    assert "`references/verified_search_core.md`" in wrapper
