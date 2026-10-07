"""Focused tests for Scripts/check_shared_core.py.

All tests operate on tmp_path. They never touch the real shared_core/ or the
real REPO_PROFILE.md anywhere in the repository.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


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


@pytest.fixture(scope="module")
def check_shared_core() -> ModuleType:
    return load_script_module("check_shared_core.py")


def _valid_core_file_text(title: str, source: str, extra_body: str = "") -> str:
    body = "\n".join(
        [
            "<!-- SHARED CORE v2026-05-22 — canonical source: ai_research_os/shared_core.",
            "     Do NOT edit in a downstream repo. Edit only in ai_research_os, then re-sync. -->",
            "",
            f"# {title}",
            "",
            "> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Do NOT edit in a",
            "> downstream repo. Edit only in `ai_research_os`, then re-sync. Version: 2026-05-22.",
            "",
            f"Source: {source}",
            "",
            "Body text here.",
        ]
    )
    if extra_body:
        body = body + "\n\n" + extra_body
    return body + "\n"


def _valid_readme_text() -> str:
    return "\n".join(
        [
            "<!-- SHARED CORE v2026-05-22 — canonical source: ai_research_os/shared_core.",
            "     Do NOT edit in a downstream repo. -->",
            "",
            "# Shared Core",
            "",
            "> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Version: 2026-05-22.",
            "",
            "README body — README is exempt from the Source: line requirement.",
            "",
        ]
    )


def _make_valid_shared_core(repo_root: Path) -> Path:
    shared_core = repo_root / "shared_core"
    shared_core.mkdir()
    (shared_core / "README.md").write_text(_valid_readme_text(), encoding="utf-8")
    (shared_core / "CORE_PRINCIPLES.md").write_text(
        _valid_core_file_text("Core Principles", "consolidated from Docs/."),
        encoding="utf-8",
    )
    (shared_core / "CORE_WORKFLOW.md").write_text(
        _valid_core_file_text("Core Workflow", "consolidated from AGENTS.md."),
        encoding="utf-8",
    )
    return shared_core


def _write_repo_profile(
    repo_root: Path,
    *,
    include_section: bool = True,
    terms: list[str] | None = None,
) -> Path:
    lines = [
        "# Repo Profile",
        "",
        "This repository obeys shared_core/ as the safety FLOOR.",
        "",
    ]
    if include_section:
        lines.append("## Floor-leak watch terms")
        lines.append("")
        lines.append(
            "<!-- Each bullet below is a single repo-specific term. -->"
        )
        lines.append("")
        for term in terms or []:
            lines.append(f"- {term}")
        lines.append("")
    path = repo_root / "REPO_PROFILE.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Case 1: all shared_core/ files well-formed -> no FAIL, no WARN
# ---------------------------------------------------------------------------


def test_all_well_formed_no_findings(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    _make_valid_shared_core(tmp_path)

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.shared_core_present is True
    assert report.errors == []
    assert report.warnings == []
    assert report.marker_failures == []
    assert report.source_failures == []
    assert report.leak_matches == []
    assert any("not present" in line for line in report.info_lines)


# ---------------------------------------------------------------------------
# Case 2: one file missing the HTML-comment marker -> FAIL
# ---------------------------------------------------------------------------


def test_missing_html_marker_is_fail(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    shared_core = _make_valid_shared_core(tmp_path)
    target = shared_core / "CORE_PRINCIPLES.md"
    text = target.read_text(encoding="utf-8")
    new_text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("<!--")
    )
    target.write_text(new_text + "\n", encoding="utf-8")

    report = check_shared_core.check_shared_core(tmp_path)

    assert any(
        "CORE_PRINCIPLES.md" in fail and "HTML-comment" in fail
        for fail in report.marker_failures
    )
    assert any("shared_core/CORE_PRINCIPLES.md" in err for err in report.errors)


# ---------------------------------------------------------------------------
# Case 3: one file missing the blockquote marker -> FAIL
# ---------------------------------------------------------------------------


def test_missing_blockquote_marker_is_fail(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    shared_core = _make_valid_shared_core(tmp_path)
    target = shared_core / "CORE_WORKFLOW.md"
    text = target.read_text(encoding="utf-8")
    new_text = "\n".join(
        line
        for line in text.splitlines()
        if "**SHARED CORE**" not in line
    )
    target.write_text(new_text + "\n", encoding="utf-8")

    report = check_shared_core.check_shared_core(tmp_path)

    assert any(
        "CORE_WORKFLOW.md" in fail and "blockquote" in fail
        for fail in report.marker_failures
    )
    assert any("shared_core/CORE_WORKFLOW.md" in err for err in report.errors)


# ---------------------------------------------------------------------------
# Case 4: one CORE_*.md missing Source: line -> FAIL
# ---------------------------------------------------------------------------


def test_missing_source_line_is_fail(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    shared_core = _make_valid_shared_core(tmp_path)
    target = shared_core / "CORE_PRINCIPLES.md"
    text = target.read_text(encoding="utf-8")
    new_text = "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith("Source:")
    )
    target.write_text(new_text + "\n", encoding="utf-8")

    report = check_shared_core.check_shared_core(tmp_path)

    assert any(
        "CORE_PRINCIPLES.md" in fail for fail in report.source_failures
    )
    assert any(
        "Source line missing" in err and "CORE_PRINCIPLES.md" in err
        for err in report.errors
    )


# ---------------------------------------------------------------------------
# Case 5: README.md without Source: line -> exempt (no FAIL on Source)
# ---------------------------------------------------------------------------


def test_readme_without_source_is_exempt(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    # README in the valid fixture already has no Source: line.
    _make_valid_shared_core(tmp_path)

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.source_failures == []
    assert not any("README.md" in err for err in report.errors)


# ---------------------------------------------------------------------------
# Case 6: shared_core/ absent -> graceful skip, no FAIL, no WARN
# ---------------------------------------------------------------------------


def test_missing_shared_core_dir_graceful_skip(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    report = check_shared_core.check_shared_core(tmp_path)

    assert report.shared_core_present is False
    assert report.errors == []
    assert report.warnings == []
    assert any(
        "shared_core/: not present" in line for line in report.info_lines
    )


# ---------------------------------------------------------------------------
# Case 7: REPO_PROFILE.md absent -> leak scan skipped, "not present"
# ---------------------------------------------------------------------------


def test_repo_profile_absent_leak_skipped(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    _make_valid_shared_core(tmp_path)

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.repo_profile_present is False
    assert report.watch_terms == []
    assert any(
        "REPO_PROFILE.md: not present" in line for line in report.info_lines
    )


# ---------------------------------------------------------------------------
# Case 8: REPO_PROFILE.md present but watch-terms section absent
# ---------------------------------------------------------------------------


def test_watch_section_absent_leak_skipped(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    _make_valid_shared_core(tmp_path)
    _write_repo_profile(tmp_path, include_section=False)

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.repo_profile_present is True
    assert report.watch_section_present is False
    assert report.watch_terms == []
    assert any(
        "section not present" in line for line in report.info_lines
    )


# ---------------------------------------------------------------------------
# Case 9: watch-terms section present but empty -> "watch terms loaded: 0"
# ---------------------------------------------------------------------------


def test_watch_section_empty_zero_terms(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    _make_valid_shared_core(tmp_path)
    _write_repo_profile(tmp_path, include_section=True, terms=[])

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.repo_profile_present is True
    assert report.watch_section_present is True
    assert report.watch_terms == []
    assert report.leak_matches == []
    assert any(
        "watch terms loaded: 0" in line for line in report.info_lines
    )


# ---------------------------------------------------------------------------
# Case 10: whole-word match -> WARN, never FAIL
# ---------------------------------------------------------------------------


def test_whole_word_match_emits_warn(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    shared_core = _make_valid_shared_core(tmp_path)
    leaked = shared_core / "CORE_PRINCIPLES.md"
    leaked.write_text(
        _valid_core_file_text(
            "Core Principles",
            "consolidated from Docs/.",
            extra_body="Note: microscopy is a domain term.",
        ),
        encoding="utf-8",
    )
    _write_repo_profile(tmp_path, include_section=True, terms=["microscopy"])

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.errors == []
    assert len(report.leak_matches) >= 1
    first = report.leak_matches[0]
    assert first.term == "microscopy"
    assert "CORE_PRINCIPLES.md" in first.path
    assert any(
        "CORE_PRINCIPLES.md" in w and "microscopy" in w for w in report.warnings
    )


def test_whole_word_match_is_case_insensitive(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    shared_core = _make_valid_shared_core(tmp_path)
    leaked = shared_core / "CORE_PRINCIPLES.md"
    leaked.write_text(
        _valid_core_file_text(
            "Core Principles",
            "consolidated from Docs/.",
            extra_body="Note: Microscopy capitalized appears here.",
        ),
        encoding="utf-8",
    )
    _write_repo_profile(tmp_path, include_section=True, terms=["microscopy"])

    report = check_shared_core.check_shared_core(tmp_path)

    assert any(match.term == "microscopy" for match in report.leak_matches)


# ---------------------------------------------------------------------------
# Case 11: substring of compound word (microscopy_quant) -> no WARN
# ---------------------------------------------------------------------------


def test_compound_word_not_flagged(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    shared_core = _make_valid_shared_core(tmp_path)
    leaked = shared_core / "CORE_PRINCIPLES.md"
    leaked.write_text(
        _valid_core_file_text(
            "Core Principles",
            "consolidated from Docs/.",
            extra_body="Note: microscopy_quant is a downstream repository name.",
        ),
        encoding="utf-8",
    )
    _write_repo_profile(tmp_path, include_section=True, terms=["microscopy"])

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.errors == []
    assert report.leak_matches == []
    assert report.warnings == []


# ---------------------------------------------------------------------------
# Case 12: visibility output lists loaded watch terms in sorted order
# ---------------------------------------------------------------------------


def test_loaded_terms_listed_in_sorted_order(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    _make_valid_shared_core(tmp_path)
    _write_repo_profile(
        tmp_path, include_section=True, terms=["zeta", "alpha", "mu"]
    )

    report = check_shared_core.check_shared_core(tmp_path)

    assert report.watch_terms == ["alpha", "mu", "zeta"]
    assert any(
        "Watch terms" in line and "alpha, mu, zeta" in line
        for line in report.info_lines
    )


# ---------------------------------------------------------------------------
# Extra: render_report exposes informational lines and FAIL/WARN labels
# ---------------------------------------------------------------------------


def test_render_report_includes_info_and_findings(
    check_shared_core: ModuleType, tmp_path: Path
) -> None:
    _make_valid_shared_core(tmp_path)
    report = check_shared_core.check_shared_core(tmp_path)
    rendered = check_shared_core.render_report(report)

    joined = "\n".join(rendered)
    assert "REPO_PROFILE.md: not present" in joined
    assert "OK: shared_core marker" in joined
