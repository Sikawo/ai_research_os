"""Focused tests for change-start packet generation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script_module(script_name: str) -> ModuleType:
    script_path = REPO_ROOT / "Scripts" / script_name
    module_name = f"test_loaded_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


start_change = load_script_module("start_change.py")


def test_packet_requests_recommended_ai_execution_settings() -> None:
    packet = start_change.build_packet(REPO_ROOT, "Example workflow task")

    assert "top-level section titled exactly `## Recommended AI execution settings`" in packet
    assert "- Recommended AI execution settings" in packet
    assert "task classification" in packet
    assert "Codex/Cursor" in packet
    assert "Claude Code" in packet
    assert "recommended model" in packet
    assert "reasoning level" in packet
    assert "effort/thinking level" in packet
    assert "Sonnet vs Opus" in packet
    assert "docs-only or template wording" in packet
    assert "small bugfix" in packet
    assert "test-only change" in packet
    assert "CLI/script behavior change" in packet
    assert "workflow/safety/review policy change" in packet
    assert "shared-core or cross-repo sync change" in packet
    assert "broad refactor/migration" in packet
    assert "private-data-risk change" in packet
    assert "advisory only and never override" in packet
    assert "human-controlled Git" in packet


def test_packet_includes_stale_active_spec_guidance_without_archiving(
    tmp_path: Path,
    monkeypatch,
) -> None:
    active_path = tmp_path / "exports" / "active_change" / "CHANGE_SPEC.md"
    active_path.parent.mkdir(parents=True)
    active_path.write_text(
        "\n".join(
            [
                "# Change Spec",
                "",
                "## Metadata",
                "",
                "- Spec ID: `SPEC_previous_task`",
                "- Target repo: `ai_research_os`",
                "- Task: `Previous task`",
                "- Created for / change class: `Medium change`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    final_review = tmp_path / "exports" / "final_review" / "20260609_010000" / "FINAL_REVIEW_PACKET.md"
    final_review.parent.mkdir(parents=True)
    final_review.write_text("# Final Review Packet\n", encoding="utf-8")

    monkeypatch.setattr(start_change, "current_branch", lambda _repo_root: "main")

    def fake_run_git(_repo_root: Path, args: list[str]) -> str:
        if args == ["status", "--short"]:
            return ""
        if args == ["rev-parse", "--short", "HEAD"]:
            return "abc1234\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(start_change, "run_git", fake_run_git)

    packet = start_change.build_packet(tmp_path, "New task")

    assert "## Existing Active Spec Diagnostic" in packet
    assert "exports/active_change/CHANGE_SPEC.md" in packet
    assert "SPEC_previous_task" in packet
    assert "Current branch: `main`" in packet
    assert "Latest commit short SHA: `abc1234`" in packet
    assert "exports/final_review/20260609_010000/FINAL_REVIEW_PACKET.md" in packet
    assert "python3 Scripts/finalize_completed_change.py --archive-active-spec" in packet
    assert "must not be silently replaced" in packet
    assert "does not auto-archive or auto-delete active specs" in packet
    assert active_path.exists()
    assert not (tmp_path / "exports" / "archived_change_specs").exists()
