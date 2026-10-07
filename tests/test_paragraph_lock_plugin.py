"""Behavioral checks for the ParagraphLock plugin and verifier."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "paragraph-lock"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "paragraph-lock"
SCRIPT = SKILL_ROOT / "scripts" / "verify_paragraph_lock.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("paragraph_lock_verifier", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFIER = load_verifier()


def manifest_for(
    baseline: bytes,
    before: str,
    after: str,
    *,
    approved: bool = True,
    change_id: str = "P2-r1",
) -> dict[str, object]:
    before_bytes = before.encode("utf-8")
    start = baseline.index(before_bytes)
    return {
        "schema_version": 1,
        "baseline_sha256": VERIFIER.sha256_bytes(baseline),
        "replacements": [
            {
                "id": change_id,
                "start_byte": start,
                "end_byte": start + len(before_bytes),
                "before": before,
                "after": after,
                "approved": approved,
            }
        ],
    }


def test_plugin_and_marketplace_manifests_are_wired() -> None:
    plugin = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text())
    marketplace = json.loads(
        (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text()
    )
    assert plugin["name"] == "paragraph-lock"
    assert plugin["skills"] == "./skills/"
    assert plugin["interface"]["displayName"] == "ParagraphLock"
    entry = next(item for item in marketplace["plugins"] if item["name"] == plugin["name"])
    assert entry["source"]["path"] == "./plugins/paragraph-lock"
    assert entry["policy"]["installation"] == "AVAILABLE"


def test_skill_encodes_explicit_approval_and_fail_closed_behavior() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    protocol = (SKILL_ROOT / "references" / "protocol.md").read_text(
        encoding="utf-8"
    )
    combined = skill + protocol
    assert "Discussion is not implementation" in combined
    assert "Praise, agreement, silence" in combined
    assert "baseline plus the approved replacement ledger" in combined
    assert "Fail closed" in combined
    assert "Conversation-only" in combined


def test_assembly_changes_only_the_approved_span() -> None:
    baseline = b"First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n"
    payload = manifest_for(
        baseline, "Second paragraph.", "Approved second paragraph."
    )
    assembled, applied = VERIFIER.assemble_bytes(baseline, payload)
    assert applied == ["P2-r1"]
    assert assembled == (
        b"First paragraph.\n\nApproved second paragraph.\n\nThird paragraph.\n"
    )


def test_unapproved_candidate_is_not_applied() -> None:
    baseline = b"Locked first.\n\nEditable second.\n"
    payload = manifest_for(
        baseline,
        "Editable second.",
        "Unapproved second.",
        approved=False,
    )
    assembled, applied = VERIFIER.assemble_bytes(baseline, payload)
    assert applied == []
    assert assembled == baseline


def test_candidate_with_unapproved_drift_fails_cli_verification(tmp_path: Path) -> None:
    baseline = b"Locked first.\n\nEditable second.\n\nLocked third.\n"
    payload = manifest_for(
        baseline, "Editable second.", "Approved second."
    )
    baseline_path = tmp_path / "baseline.txt"
    changes_path = tmp_path / "changes.json"
    candidate_path = tmp_path / "candidate.txt"
    baseline_path.write_bytes(baseline)
    changes_path.write_text(json.dumps(payload), encoding="utf-8")
    candidate_path.write_bytes(
        b"Changed first.\n\nApproved second.\n\nLocked third.\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "verify",
            "--baseline",
            str(baseline_path),
            "--changes",
            str(changes_path),
            "--candidate",
            str(candidate_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "unapproved difference" in result.stderr


def test_overlapping_approved_replacements_are_rejected() -> None:
    baseline = b"One paragraph."
    payload = {
        "schema_version": 1,
        "baseline_sha256": VERIFIER.sha256_bytes(baseline),
        "replacements": [
            {
                "id": "P1-r1",
                "start_byte": 0,
                "end_byte": 3,
                "before": "One",
                "after": "First",
                "approved": True,
            },
            {
                "id": "P1-r2",
                "start_byte": 0,
                "end_byte": 13,
                "before": "One paragraph",
                "after": "A paragraph",
                "approved": True,
            },
        ],
    }
    with pytest.raises(VERIFIER.ParagraphLockError, match="overlap"):
        VERIFIER.assemble_bytes(baseline, payload)


def test_utf8_byte_offsets_preserve_locked_text() -> None:
    baseline = "A plain paragraph.\n\nA caf\u00e9 paragraph.\n\nA locked ending.\n".encode(
        "utf-8"
    )
    payload = manifest_for(
        baseline,
        "A caf\u00e9 paragraph.",
        "An approved caf\u00e9 paragraph.",
    )
    assembled, _ = VERIFIER.assemble_bytes(baseline, payload)
    assert assembled.startswith(b"A plain paragraph.\n\n")
    assert assembled.endswith(b"\n\nA locked ending.\n")
    assert "An approved caf\u00e9 paragraph.".encode("utf-8") in assembled


def test_non_utf8_baseline_is_rejected() -> None:
    baseline = b"Valid prefix\n\xff"
    payload = {
        "schema_version": 1,
        "baseline_sha256": VERIFIER.sha256_bytes(baseline),
        "replacements": [],
    }
    with pytest.raises(VERIFIER.ParagraphLockError, match="not valid UTF-8"):
        VERIFIER.assemble_bytes(baseline, payload)


def test_self_test_command_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--self-test"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ParagraphLock check: PASS" in result.stdout
    assert "Unapproved text changes: 0" in result.stdout
