import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
ADAPTER_PATH = REPO_ROOT / "Docs" / "codex_autonomous_work_policy.md"
MANIFEST_PATH = REPO_ROOT / "config" / "autonomous_delivery.json"
SHARED_POLICY_PATH = REPO_ROOT / "shared_core" / "CORE_AUTONOMOUS_DELIVERY_POLICY.md"


def manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_enables_only_feature_branch_to_draft_pr_level_4():
    policy = manifest()

    assert policy["repository"] == "ai_research_os"
    assert policy["origin_url"] == "https://github.com/Sikawo/ai_research_os.git"
    assert policy["enabled"] is True
    assert policy["max_git_level"] == 4
    assert policy["base_branch"] == "main"
    assert policy["allowed_branch_prefixes"] == ["agent/", "codex/"]
    assert policy["protected_content_mode"] == "forbidden"
    assert policy["draft_pr_allowed"] is True
    assert policy["merge_allowed"] is False
    assert policy["forbid_force_push"] is True
    assert policy["forbid_branch_delete"] is True


def test_manifest_blocks_private_raw_large_generated_and_notebook_content():
    blocked = set(manifest()["blocked_path_patterns"])

    for expected in (
        ".env",
        "exports/**",
        "ai_artifacts/**",
        "Papers/**",
        "Applications/**",
        "People/**",
        "Protocols/**",
        "Private/**",
        "raw_data/**",
        "**/*.fcs",
        "**/*.fastq",
        "**/*.bam",
        "**/*.czi",
        "**/*.tif",
        "**/*.h5",
        "**/*.zip",
        "**/*.tar.gz",
        "**/*.ipynb",
        "**/*.pdf",
        "**/*.docx",
    ):
        assert expected in blocked


def test_adapter_requires_structured_scope_and_all_review_gates():
    adapter = ADAPTER_PATH.read_text(encoding="utf-8")

    assert "machine-readable task scope" in adapter
    assert "Independent Reviewer `APPROVE`" in adapter
    assert "finish_change.py --active-spec" in adapter
    assert "review gate before and after exact" in adapter
    assert "An uncertain or unclassified path is a stop" in adapter
    assert "Protected-content mode: forbidden" in adapter
    assert "another repository" in adapter
    assert "ready-for-review transition" in adapter
    assert "hard reset" in adapter
    assert "broad clean" in adapter


def test_agent_entrypoint_declares_narrow_level_4_exception():
    agents = AGENTS_PATH.read_text(encoding="utf-8")

    assert "narrow exception to the" in agents
    assert "A compliant Git Level 4 cycle" in agents
    assert "Direct push to `main`" in agents
    assert "merge" in agents
    assert "force" in agents


def test_shared_floor_permanently_excludes_merge_and_destructive_git():
    shared = SHARED_POLICY_PATH.read_text(encoding="utf-8")

    assert "No level inferred from this policy permits direct push to `main`" in shared
    assert "Merge approval is separate from push and draft PR approval." in shared
    assert "force-push" in shared
    assert "history rewriting" in shared
    assert "branch deletion" in shared
