"""Regression tests for the GatedSprint v2 deterministic state validator."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

TEST_DIR = Path(__file__).resolve().parent
FIXTURES = TEST_DIR / "fixtures"
VALIDATOR = TEST_DIR.parent / "scripts" / "validate_gatedsprint_state.py"
SCHEMA = TEST_DIR.parent / "schemas" / "gatedsprint-state.schema.json"

VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "gated_sprint_state_validator",
    VALIDATOR,
)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR_MODULE = importlib.util.module_from_spec(VALIDATOR_SPEC)
sys.modules[VALIDATOR_SPEC.name] = VALIDATOR_MODULE
VALIDATOR_SPEC.loader.exec_module(VALIDATOR_MODULE)
BINARY_COMPARISON_CHUNK_SIZE = VALIDATOR_MODULE.BINARY_COMPARISON_CHUNK_SIZE
_range_sha256 = VALIDATOR_MODULE._range_sha256
_ranges_equal = VALIDATOR_MODULE._ranges_equal

SOURCE_BINDING_AUTHORIZATION_FIELDS = (
    "binding_type",
    "source_id",
    "source_fingerprint",
    "proposal_fingerprint",
    "old_source_id",
    "old_source_fingerprint",
    "old_anchor_hash",
    "new_anchor_hash",
    "protected_intent_hash",
    "dependency_set_hash",
    "comparison_result",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def source_binding_authorization_hash(binding: dict[str, Any]) -> str:
    return canonical_hash(
        {field: binding.get(field) for field in SOURCE_BINDING_AUTHORIZATION_FIELDS}
    )


def lock_creation_payload_hash(lock: dict[str, Any]) -> str:
    return canonical_hash(
        {
            field: lock.get(field)
            for field in (
                "lock_id",
                "type",
                "scope_anchor",
                "reason",
                "creating_authority",
                "source_fingerprint",
                "release_condition",
                "created_at",
            )
        }
    )


def lock_release_payload_hash(lock: dict[str, Any]) -> str:
    return canonical_hash(
        {
            field: lock.get(field)
            for field in (
                "lock_id",
                "released_at",
                "released_by",
                "source_fingerprint",
            )
        }
    )


def _pointer_tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer: {pointer!r}")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]


def _read_pointer(document: Any, pointer: str) -> Any:
    current = document
    for token in _pointer_tokens(pointer):
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def _parent_and_token(document: Any, pointer: str) -> tuple[Any, str]:
    tokens = _pointer_tokens(pointer)
    if not tokens:
        raise ValueError("fixture mutations may not replace the document root")
    current = document
    for token in tokens[:-1]:
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current, tokens[-1]


def apply_mutations(document: Any, mutations: list[dict[str, Any]]) -> Any:
    result = copy.deepcopy(document)
    for mutation in mutations:
        operation = mutation["op"]
        parent, token = _parent_and_token(result, mutation["path"])
        if operation == "copy":
            value = copy.deepcopy(_read_pointer(result, mutation["from"]))
        else:
            value = copy.deepcopy(mutation.get("value"))
        if operation in {"add", "copy"}:
            if isinstance(parent, list):
                if token == "-":
                    parent.append(value)
                else:
                    parent.insert(int(token), value)
            else:
                parent[token] = value
        elif operation == "replace":
            if isinstance(parent, list):
                parent[int(token)] = value
            else:
                if token not in parent:
                    raise KeyError(f"replace target does not exist: {mutation['path']}")
                parent[token] = value
        elif operation == "remove":
            if isinstance(parent, list):
                del parent[int(token)]
            else:
                del parent[token]
        else:
            raise ValueError(f"unsupported fixture mutation operation: {operation!r}")
    return result


def run_validator(
    *,
    state: Path,
    baseline: Path,
    check: str,
    candidate: Path | None = None,
    diff_map: Path | None = None,
    artifact_root: Path | None = None,
    source_root: Path | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "--state",
        str(state),
        "--baseline",
        str(baseline),
        "--check",
        check,
    ]
    if candidate is not None:
        command.extend(["--candidate", str(candidate)])
        command.extend(["--artifact-root", str(artifact_root or FIXTURES)])
        command.extend(["--source-root", str(source_root or FIXTURES)])
    if diff_map is not None:
        command.extend(["--diff-map", str(diff_map)])
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def run_materialized_documents(
    *,
    state: dict[str, Any],
    baseline: dict[str, Any],
    check: str,
    candidate: dict[str, Any] | None = None,
    diff_map: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        state_path = temporary_path / "state.json"
        baseline_path = temporary_path / "baseline.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        candidate_path = None
        if candidate is not None:
            candidate_path = temporary_path / "candidate.json"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        diff_path = None
        if diff_map is not None:
            diff_path = temporary_path / "diff-map.json"
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
        return run_validator(
            state=state_path,
            baseline=baseline_path,
            candidate=candidate_path,
            diff_map=diff_path,
            check=check,
        )


def add_valid_local_fix(
    state: dict[str, Any],
    diff_map: dict[str, Any],
    *,
    hunk_coverage: dict[str, Any] | None = None,
) -> None:
    candidate_hash = state["artifacts"][0]["candidate_hash"]
    local_fix = {
        "local_fix_id": "LF-GHOST",
        "category": "PUNCTUATION",
        "scope": "Research statement opening",
        "description": "Correct one enumerated punctuation error.",
        "source_id": "SRC-RELEASE",
        "source_fingerprint": "sha256:cf40fbd1b90427f1d79b335a2adcf4b3bf593afea52350b57d90789d043861f1",
        "authorized": True,
        "authorized_by": "user",
        "authorized_at": "2026-10-01T14:03:30Z",
        "implemented_hunk_ids": ["HUNK-GHOST"],
        "candidate_hash": candidate_hash,
    }
    state["local_fix_log"].append(local_fix)
    local_fix_payload = {
        key: local_fix[key]
        for key in (
            "local_fix_id",
            "category",
            "scope",
            "description",
            "source_id",
            "source_fingerprint",
        )
    }
    local_fix_payload_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            local_fix_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    state["events"].insert(
        3,
        {
            "event_id": "EVT-REL-LF-001",
            "event_type": "LOCAL_FIX_AUTHORIZED",
            "decision_id": None,
            "proposal_revision": None,
            "artifact_id": None,
            "actor": "user",
            "authority_kind": "USER",
            "timestamp": "2026-10-01T14:03:30Z",
            "prior_state": None,
            "new_state": None,
            "prior_support_status": None,
            "new_support_status": None,
            "prior_source_impact": None,
            "new_source_impact": None,
            "proposal_fingerprint": None,
            "source_id": local_fix["source_id"],
            "source_fingerprint": local_fix["source_fingerprint"],
            "artifact_hash": None,
            "authority_basis": "The user approved this exact enumerated local fix.",
            "details": {
                "local_fix_id": "LF-GHOST",
                "local_fix_payload_hash": local_fix_payload_hash,
            },
        },
    )
    state["attestations"].append(
        {
            "attestation_id": "ATT-REL-LF-001",
            "check_id": "local_fix_semantics:LF-GHOST",
            "source_id": None,
            "source_fingerprint": None,
            "artifact_id": "ART-FINAL",
            "artifact_hash": candidate_hash,
            "rubric": "local fix non-semantic review",
            "result": "PASS",
            "responsible_actor": "reviewer",
            "authority_kind": "REVIEWER",
            "timestamp": "2026-10-01T14:18:00Z",
            "evidence": "The enumerated punctuation correction is non-semantic on the exact artifact.",
        }
    )
    local_hunk = {
            "hunk_id": "HUNK-GHOST",
            "kind": "LOCAL_FIX",
            "decision_id": None,
            "proposal_revision": None,
            "local_fix_id": "LF-GHOST",
            "description": "Authorized punctuation correction.",
        }
    if hunk_coverage:
        local_hunk.update(hunk_coverage)
    diff_map["hunks"].append(local_hunk)


class GatedSprintStateValidationTests(unittest.TestCase):
    maxDiff = None

    def assert_pass(self, completed: subprocess.CompletedProcess[str], check: str) -> dict[str, Any]:
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["check"], check)
        self.assertEqual(payload["result"], "PASS")
        self.assertEqual(payload["error_count"], 0)
        self.assertIn(f"GatedSprint {check}: PASS", completed.stderr)
        return payload

    def test_schema_is_versioned_draft_2020_12_json(self) -> None:
        schema = load_json(SCHEMA)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "2.0.0")
        decision_states = schema["$defs"]["decision"]["properties"]["decision_state"]["enum"]
        self.assertIn("AUTHORIZED", decision_states)
        self.assertNotIn("BLOCKED", decision_states)
        document_types = schema["$defs"]["run"]["properties"]["document_type"]["enum"]
        artifact_formats = schema["$defs"]["artifact"]["properties"]["format"]["enum"]
        self.assertIn("RESUME", document_types)
        self.assertIn("JSON", artifact_formats)

    def test_binary_range_helpers_are_exact_across_multiple_chunks(self) -> None:
        payload = bytes(range(256)) * (
            (BINARY_COMPARISON_CHUNK_SIZE * 3 // 256) + 1
        )
        changed = bytearray(payload)
        changed[BINARY_COMPARISON_CHUNK_SIZE * 2 + 17] ^= 0xFF
        changed = bytes(changed)

        self.assertTrue(_ranges_equal(payload, 0, len(payload), payload, 0, len(payload)))
        self.assertFalse(_ranges_equal(payload, 0, len(payload), changed, 0, len(changed)))
        self.assertEqual(
            _range_sha256(payload, 0, len(payload)),
            "sha256:" + hashlib.sha256(payload).hexdigest(),
        )

    def test_valid_diagnostic_state(self) -> None:
        completed = run_validator(
            state=FIXTURES / "valid_diagnostic_state.json",
            baseline=FIXTURES / "diagnostic_baseline.json",
            check="diagnostic",
        )
        self.assert_pass(completed, "diagnostic")

    def test_valid_diagnostic_may_preserve_a_blocked_proposal(self) -> None:
        case = load_json(FIXTURES / "valid_blocked_diagnostic.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            completed = run_validator(
                state=state_path,
                baseline=FIXTURES / case["baseline"],
                check=case["check"],
            )
        self.assert_pass(completed, "diagnostic")

    def test_valid_revalidated_state_is_ready_to_implement(self) -> None:
        completed = run_validator(
            state=FIXTURES / "valid_ready_to_implement_revalidated.json",
            baseline=FIXTURES / "revalidated_baseline.json",
            check="ready-to-implement",
        )
        self.assert_pass(completed, "ready-to-implement")

    def test_valid_exact_artifact_is_ready_to_release(self) -> None:
        completed = run_validator(
            state=FIXTURES / "valid_ready_to_release.json",
            baseline=FIXTURES / "release_baseline.json",
            candidate=FIXTURES / "release_candidate.json",
            diff_map=FIXTURES / "release_diff_map.json",
            check="ready-to-release",
        )
        self.assert_pass(completed, "ready-to-release")

    def test_realistic_size_binary_pdf_release_uses_linear_exact_byte_coverage(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        baseline = load_json(FIXTURES / "release_baseline.json")
        candidate = load_json(FIXTURES / "release_candidate.json")
        diff_map = load_json(FIXTURES / "release_diff_map.json")

        # A multi-megabyte repetitive payload is realistic for compressed
        # document containers and pathological for SequenceMatcher with
        # autojunk disabled. The validator must finish within a bounded time
        # while retaining exact hunk and unchanged-gap checks.
        repeated_payload = bytes(range(256)) * 8192
        prefix = b"%PDF-1.7\n%\xff\xfe\n" + repeated_payload
        baseline_body = b"BASELINE-BINARY-BLOCK" * 2048 + b"B"
        candidate_body = b"CANDIDATE-BINARY-BLOCK" * 2304 + b"C"
        suffix = repeated_payload[::-1] + b"\n%%EOF\n"
        baseline_bytes = prefix + baseline_body + suffix
        candidate_bytes = prefix + candidate_body + suffix
        baseline_hash = "sha256:" + hashlib.sha256(baseline_bytes).hexdigest()
        candidate_hash = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()

        source = state["sources"][0]
        old_source_fingerprint = source["byte_hash"]
        source.update(
            {
                "path": "approved-source.pdf",
                "media_type": "application/pdf",
                "layout_authority": True,
                "byte_hash": baseline_hash,
            }
        )
        baseline_entry = baseline["sources"][0]
        for field in (
            "path",
            "byte_hash",
            "extracted_text_hash",
            "user_designated_role",
            "content_authority",
            "layout_authority",
            "editable_target",
            "equivalence_status",
            "version_designation",
        ):
            baseline_entry[field] = source[field]

        decision = state["decisions"][0]
        decision["source_fingerprint"] = baseline_hash
        decision["source_bindings"][0]["source_fingerprint"] = baseline_hash
        for event in state["events"]:
            if event.get("source_fingerprint") == old_source_fingerprint:
                event["source_fingerprint"] = baseline_hash
            if event.get("artifact_hash") is not None:
                event["artifact_hash"] = candidate_hash
            if event.get("new_state") in {"APPROVED", "AUTHORIZED"}:
                event["details"]["source_binding_hash"] = source_binding_authorization_hash(
                    decision["source_bindings"][0]
                )

        artifact = state["artifacts"][0]
        artifact.update(
            {
                "path": "submission-final.pdf",
                "format": "PDF",
                "source_hash": baseline_hash,
                "candidate_hash": candidate_hash,
            }
        )
        artifact["verification"]["candidate_hash"] = candidate_hash
        decision["implementation_result"]["candidate_hash"] = candidate_hash
        decision["verification_result"]["candidate_hash"] = candidate_hash
        for attestation in state["attestations"]:
            if attestation.get("artifact_hash") is not None:
                attestation["artifact_hash"] = candidate_hash

        candidate_entry = candidate["artifacts"][0]
        for field in (
            "path",
            "baseline_source_ids",
            "candidate_hash",
            "artifact_status",
            "relationship_to_baseline",
            "actual_submission_artifact",
            "format",
        ):
            candidate_entry[field] = artifact[field]

        diff_map.update(
            {
                "baseline_hash": baseline_hash,
                "candidate_hash": candidate_hash,
                "comparison_mode": "BINARY_BYTES",
            }
        )
        hunk = diff_map["hunks"][0]
        exact_hunk_coverage = {
            "operation": "replace",
            "baseline_start": len(prefix),
            "baseline_end": len(prefix) + len(baseline_body),
            "candidate_start": len(prefix),
            "candidate_end": len(prefix) + len(candidate_body),
            "baseline_lines_hash": "sha256:"
            + hashlib.sha256(baseline_body).hexdigest(),
            "candidate_lines_hash": "sha256:"
            + hashlib.sha256(candidate_body).hexdigest(),
        }
        hunk.update(exact_hunk_coverage)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            baseline_path = root / "baseline.json"
            candidate_path = root / "candidate.json"
            diff_path = root / "diff.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            (root / source["path"]).write_bytes(baseline_bytes)
            (root / artifact["path"]).write_bytes(candidate_bytes)
            completed = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=root,
                source_root=root,
                check="ready-to-release",
                timeout=10,
            )
            hunk["candidate_lines_hash"] = "sha256:" + "0" * 64
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            tampered = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=root,
                source_root=root,
                check="ready-to-release",
                timeout=10,
            )
            hunk.update(
                {
                    "operation": "replace",
                    "baseline_start": 0,
                    "baseline_end": len(baseline_bytes),
                    "candidate_start": 0,
                    "candidate_end": len(candidate_bytes),
                    "baseline_lines_hash": "sha256:"
                    + hashlib.sha256(baseline_bytes).hexdigest(),
                    "candidate_lines_hash": "sha256:"
                    + hashlib.sha256(candidate_bytes).hexdigest(),
                }
            )
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            stable_edge_overbroad = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=root,
                source_root=root,
                check="ready-to-release",
                timeout=10,
            )
            empty_hash = "sha256:" + hashlib.sha256(b"").hexdigest()
            delete_hunk = copy.deepcopy(hunk)
            delete_hunk.update(
                {
                    "operation": "delete",
                    "baseline_start": 0,
                    "baseline_end": len(baseline_bytes),
                    "candidate_start": 0,
                    "candidate_end": 0,
                    "baseline_lines_hash": baseline_hash,
                    "candidate_lines_hash": empty_hash,
                }
            )
            insert_hunk = copy.deepcopy(hunk)
            insert_hunk.update(
                {
                    "hunk_id": "HUNK-002",
                    "operation": "insert",
                    "baseline_start": len(baseline_bytes),
                    "baseline_end": len(baseline_bytes),
                    "candidate_start": 0,
                    "candidate_end": len(candidate_bytes),
                    "baseline_lines_hash": empty_hash,
                    "candidate_lines_hash": candidate_hash,
                }
            )
            decision["implementation_result"]["diff_hunk_ids"] = [
                "HUNK-001",
                "HUNK-002",
            ]
            diff_map["hunks"] = [delete_hunk, insert_hunk]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            delete_then_insert = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=root,
                source_root=root,
                check="ready-to-release",
                timeout=10,
            )
            insert_first_hunk = copy.deepcopy(insert_hunk)
            insert_first_hunk.update(
                {
                    "hunk_id": "HUNK-001",
                    "baseline_start": 0,
                    "baseline_end": 0,
                    "candidate_start": 0,
                    "candidate_end": len(candidate_bytes),
                }
            )
            delete_second_hunk = copy.deepcopy(delete_hunk)
            delete_second_hunk.update(
                {
                    "hunk_id": "HUNK-002",
                    "baseline_start": 0,
                    "baseline_end": len(baseline_bytes),
                    "candidate_start": len(candidate_bytes),
                    "candidate_end": len(candidate_bytes),
                }
            )
            diff_map["hunks"] = [insert_first_hunk, delete_second_hunk]
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            insert_then_delete = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=root,
                source_root=root,
                check="ready-to-release",
                timeout=10,
            )
            decision["implementation_result"]["diff_hunk_ids"] = ["HUNK-001"]
            diff_map["hunks"] = [hunk]
            hunk.update(exact_hunk_coverage)
            hidden_delta_bytes = bytearray(candidate_bytes)
            hidden_delta_offset = len(prefix) + len(candidate_body) + len(suffix) // 2
            hidden_delta_bytes[hidden_delta_offset] ^= 0xFF
            hidden_delta_bytes = bytes(hidden_delta_bytes)
            hidden_delta_hash = "sha256:" + hashlib.sha256(hidden_delta_bytes).hexdigest()
            artifact["candidate_hash"] = hidden_delta_hash
            artifact["verification"]["candidate_hash"] = hidden_delta_hash
            decision["implementation_result"]["candidate_hash"] = hidden_delta_hash
            decision["verification_result"]["candidate_hash"] = hidden_delta_hash
            candidate_entry["candidate_hash"] = hidden_delta_hash
            diff_map["candidate_hash"] = hidden_delta_hash
            for event in state["events"]:
                if event.get("artifact_hash") is not None:
                    event["artifact_hash"] = hidden_delta_hash
            for attestation in state["attestations"]:
                if attestation.get("artifact_hash") is not None:
                    attestation["artifact_hash"] = hidden_delta_hash
            state_path.write_text(json.dumps(state), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            (root / artifact["path"]).write_bytes(hidden_delta_bytes)
            hidden_delta = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=root,
                source_root=root,
                check="ready-to-release",
                timeout=10,
            )
        self.assert_pass(completed, "ready-to-release")
        self.assertEqual(tampered.returncode, 1, tampered.stderr + tampered.stdout)
        issues = json.loads(tampered.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.DIFF_COVERAGE"
                and "slice hashes" in item["explanation"]
                for item in issues
            )
        )
        self.assertEqual(
            stable_edge_overbroad.returncode,
            1,
            stable_edge_overbroad.stderr + stable_edge_overbroad.stdout,
        )
        overbroad_issues = json.loads(stable_edge_overbroad.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.DIFF_COVERAGE"
                and "complete baseline-to-candidate delta" in item["explanation"]
                for item in overbroad_issues
            )
        )
        for composite_result in (delete_then_insert, insert_then_delete):
            self.assertEqual(
                composite_result.returncode,
                1,
                composite_result.stderr + composite_result.stdout,
            )
            composite_issues = json.loads(composite_result.stdout)["issues"]
            self.assertTrue(
                any(
                    item["check_id"] == "STATE.DIFF_COVERAGE"
                    and "complete baseline-to-candidate delta" in item["explanation"]
                    for item in composite_issues
                )
            )
        self.assertEqual(hidden_delta.returncode, 1, hidden_delta.stderr + hidden_delta.stdout)
        hidden_delta_issues = json.loads(hidden_delta.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.DIFF_COVERAGE"
                and "complete baseline-to-candidate delta" in item["explanation"]
                for item in hidden_delta_issues
            )
        )

    def test_qualitative_attestation_rejects_assistant_self_authority(self) -> None:
        state = load_json(FIXTURES / "valid_diagnostic_state.json")
        state["attestations"][0]["authority_kind"] = "ASSISTANT"
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "diagnostic_baseline.json"),
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.SCHEMA", issue_ids)

    def test_narrative_gate_attestation_must_use_content_authority(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        baseline = load_json(FIXTURES / "revalidated_baseline.json")
        preview = copy.deepcopy(state["sources"][1])
        preview.update(
            {
                "source_id": "SRC-STALE-PREVIEW",
                "path": "fixtures/stale-preview.docx",
                "origin": "GENERATED_PREVIEW",
                "is_current": True,
                "content_authority": False,
                "layout_authority": False,
                "equivalence_status": "DIFFERENT_CONTENT",
                "byte_hash": "sha256:" + "9" * 64,
                "extracted_text_hash": "sha256:" + "8" * 64,
            }
        )
        state["sources"].append(preview)
        state["run"]["current_source_ids"].append(preview["source_id"])
        baseline_preview = copy.deepcopy(baseline["sources"][1])
        for field in (
            "source_id",
            "path",
            "byte_hash",
            "extracted_text_hash",
            "user_designated_role",
            "content_authority",
            "layout_authority",
            "editable_target",
            "equivalence_status",
            "version_designation",
        ):
            baseline_preview[field] = preview[field]
        baseline["sources"].append(baseline_preview)
        for attestation in state["attestations"]:
            if attestation["check_id"] in {"motivation_significance", "logical_simplicity"}:
                attestation["source_id"] = preview["source_id"]
                attestation["source_fingerprint"] = preview["extracted_text_hash"]

        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issues = json.loads(completed.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.ATTESTATION"
                and "motivation_significance" in item["explanation"]
                for item in issues
            )
        )

    def test_user_lock_cannot_be_released_by_assistant_authority(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        lock = {
            "lock_id": "LOCK-USER-AUTHORITY",
            "type": "USER_LOCK",
            "scope_anchor": "Appendix note",
            "reason": "Preserve until the user explicitly releases it.",
            "creating_authority": "user",
            "source_fingerprint": "sha256:" + "d" * 64,
            "status": "RELEASED",
            "release_condition": "The user explicitly releases the lock.",
            "created_at": "2026-10-01T13:03:10Z",
            "released_at": "2026-10-01T13:03:20Z",
            "released_by": "assistant",
        }
        state["locks"].append(lock)
        created_event = {
            "event_id": "EVT-LOCK-AUTH-001",
            "event_type": "LOCK_CREATED",
            "decision_id": None,
            "proposal_revision": None,
            "artifact_id": None,
            "actor": "user",
            "authority_kind": "USER",
            "timestamp": lock["created_at"],
            "prior_state": None,
            "new_state": None,
            "prior_support_status": None,
            "new_support_status": None,
            "prior_source_impact": None,
            "new_source_impact": None,
            "proposal_fingerprint": None,
            "source_id": "SRC-NEW",
            "source_fingerprint": lock["source_fingerprint"],
            "artifact_hash": None,
            "authority_basis": "The user created the lock.",
            "details": {
                "lock_id": lock["lock_id"],
                "lock_payload_hash": lock_creation_payload_hash(lock),
            },
        }
        released_event = copy.deepcopy(created_event)
        released_event.update(
            {
                "event_id": "EVT-LOCK-AUTH-002",
                "event_type": "LOCK_RELEASED",
                "actor": "assistant",
                "authority_kind": "ASSISTANT",
                "timestamp": lock["released_at"],
                "authority_basis": "The assistant asserted release.",
            }
        )
        released_event["details"] = {
            "lock_id": lock["lock_id"],
            "lock_release_payload_hash": lock_release_payload_hash(lock),
        }
        state["events"][3:3] = [created_event, released_event]

        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.LOCK_AUTHORITY", issue_ids)

    def test_local_fix_authorization_binds_exact_payload(self) -> None:
        state = load_json(FIXTURES / "valid_diagnostic_state.json")
        local_fix = {
            "local_fix_id": "LF-BOUND",
            "category": "PUNCTUATION",
            "scope": "Research statement opening",
            "description": "Remove one duplicated comma.",
            "source_id": "SRC-DRAFT",
            "source_fingerprint": "sha256:" + "a" * 64,
            "authorized": True,
            "authorized_by": "user",
            "authorized_at": "2026-10-01T12:02:00Z",
            "implemented_hunk_ids": [],
            "candidate_hash": None,
        }
        authorized_payload = {
            key: local_fix[key]
            for key in (
                "local_fix_id",
                "category",
                "scope",
                "description",
                "source_id",
                "source_fingerprint",
            )
        }
        state["local_fix_log"].append(local_fix)
        state["events"].append(
            {
                "event_id": "EVT-LF-BOUND",
                "event_type": "LOCAL_FIX_AUTHORIZED",
                "decision_id": None,
                "proposal_revision": None,
                "artifact_id": None,
                "actor": "user",
                "authority_kind": "USER",
                "timestamp": local_fix["authorized_at"],
                "prior_state": None,
                "new_state": None,
                "prior_support_status": None,
                "new_support_status": None,
                "prior_source_impact": None,
                "new_source_impact": None,
                "proposal_fingerprint": None,
                "source_id": local_fix["source_id"],
                "source_fingerprint": local_fix["source_fingerprint"],
                "artifact_hash": None,
                "authority_basis": "The user authorized the exact bounded fix.",
                "details": {
                    "local_fix_id": local_fix["local_fix_id"],
                    "local_fix_payload_hash": canonical_hash(authorized_payload),
                },
            }
        )
        local_fix["description"] = "Add an unapproved substantive argument."

        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "diagnostic_baseline.json"),
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issues = json.loads(completed.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.LOCAL_FIX"
                and "exact payload" in item["explanation"]
                for item in issues
            )
        )

    def test_local_fix_authorization_cannot_replay_across_current_sources(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        baseline = load_json(FIXTURES / "release_baseline.json")
        candidate = load_json(FIXTURES / "release_candidate.json")
        diff_map = load_json(FIXTURES / "release_diff_map.json")
        add_valid_local_fix(
            state,
            diff_map,
            hunk_coverage={
                "operation": "insert",
                "baseline_start": 1,
                "baseline_end": 1,
                "candidate_start": 1,
                "candidate_end": 2,
                "baseline_lines_hash": "sha256:"
                + hashlib.sha256(b"").hexdigest(),
                "candidate_lines_hash": "sha256:"
                + hashlib.sha256(b"Clear consequence.\n").hexdigest(),
            },
        )

        other_source = copy.deepcopy(state["sources"][0])
        other_source.update(
            {
                "source_id": "SRC-OTHER-CURRENT",
                "path": "submission-final.txt",
                "byte_hash": state["artifacts"][0]["candidate_hash"],
                "extracted_text_hash": state["artifacts"][0]["candidate_hash"],
            }
        )
        state["sources"].append(other_source)
        state["run"]["current_source_ids"].append(other_source["source_id"])
        baseline_other = copy.deepcopy(baseline["sources"][0])
        for field in (
            "source_id",
            "path",
            "byte_hash",
            "extracted_text_hash",
            "user_designated_role",
            "content_authority",
            "layout_authority",
            "editable_target",
            "equivalence_status",
            "version_designation",
        ):
            baseline_other[field] = other_source[field]
        baseline["sources"].append(baseline_other)

        local_fix = state["local_fix_log"][0]
        local_fix["source_id"] = other_source["source_id"]
        local_fix["source_fingerprint"] = other_source["byte_hash"]
        authorization_event = next(
            event
            for event in state["events"]
            if event.get("event_type") == "LOCAL_FIX_AUTHORIZED"
        )
        authorization_event["source_id"] = local_fix["source_id"]
        authorization_event["source_fingerprint"] = local_fix["source_fingerprint"]
        authorization_event["details"]["local_fix_payload_hash"] = canonical_hash(
            {
                key: local_fix[key]
                for key in (
                    "local_fix_id",
                    "category",
                    "scope",
                    "description",
                    "source_id",
                    "source_fingerprint",
                )
            }
        )

        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            candidate=candidate,
            diff_map=diff_map,
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issues = json.loads(completed.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.LOCAL_FIX"
                and "exact authorized source" in item["explanation"]
                for item in issues
            )
        )

    def test_tradeoff_acceptance_cannot_be_recorded_after_release(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        decision = state["decisions"][0]
        latest_binding = decision["source_bindings"][-1]
        accepted = {
            "user_choice": "Accept the disclosed loss of nuance.",
            "disclosed_consequence": "The final text may hide an important limitation.",
            "accepted_by": "user",
            "timestamp": "2026-10-01T14:21:00Z",
            "source_fingerprint": latest_binding["source_fingerprint"],
            "proposal_fingerprint": decision["proposal_fingerprint"],
        }
        decision["accepted_tradeoff"] = accepted
        state["events"].append(
            {
                "event_id": "EVT-TRADEOFF-LATE",
                "event_type": "TRADEOFF_ACCEPTED",
                "decision_id": decision["decision_id"],
                "proposal_revision": decision["proposal_revision"],
                "artifact_id": None,
                "actor": "user",
                "authority_kind": "USER",
                "timestamp": accepted["timestamp"],
                "prior_state": None,
                "new_state": None,
                "prior_support_status": None,
                "new_support_status": None,
                "prior_source_impact": None,
                "new_source_impact": None,
                "proposal_fingerprint": decision["proposal_fingerprint"],
                "source_id": latest_binding["source_id"],
                "source_fingerprint": latest_binding["source_fingerprint"],
                "artifact_hash": None,
                "authority_basis": "The user accepted only after final verification.",
                "details": {"accepted_tradeoff_hash": canonical_hash(accepted)},
            }
        )

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            completed = run_validator(
                state=state_path,
                baseline=FIXTURES / "release_baseline.json",
                candidate=FIXTURES / "release_candidate.json",
                diff_map=FIXTURES / "release_diff_map.json",
                check="ready-to-release",
            )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issues = json.loads(completed.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.ACCEPTED_TRADEOFF"
                and "before authorization" in item["explanation"]
                for item in issues
            )
        )

    def test_proposal_fingerprint_covers_proposed_intervention(self) -> None:
        state = load_json(FIXTURES / "valid_diagnostic_state.json")
        state["decisions"][0]["proposed_intervention"] = (
            "Silently changed intervention that was never fingerprinted or approved."
        )
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "diagnostic_baseline.json"),
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.PROPOSAL_FINGERPRINT", issue_ids)

    def test_post_approval_dependency_tampering_cannot_refresh_its_way_to_readiness(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        decision = state["decisions"][0]
        dependency_ref = {"decision_id": "GS-099", "proposal_revision": 1}
        decision["dependencies"] = [dependency_ref]
        dependency_hash = "sha256:" + hashlib.sha256(
            json.dumps(
                [dependency_ref], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        for binding in decision["source_bindings"]:
            binding["dependency_set_hash"] = dependency_hash
        state["events"][2]["details"]["dependency_set_hash"] = dependency_hash
        authorization_fields = (
            "binding_type",
            "source_id",
            "source_fingerprint",
            "proposal_fingerprint",
            "old_source_id",
            "old_source_fingerprint",
            "old_anchor_hash",
            "new_anchor_hash",
            "protected_intent_hash",
            "dependency_set_hash",
            "comparison_result",
        )
        for event_index, binding_index in ((1, 0), (3, 1)):
            binding_payload = {
                field: decision["source_bindings"][binding_index].get(field)
                for field in authorization_fields
            }
            state["events"][event_index]["details"]["source_binding_hash"] = (
                "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        binding_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
            )

        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.PROPOSAL_FINGERPRINT", issue_ids)
        self.assertNotIn("STATE.SOURCE_BINDING", issue_ids)
        self.assertNotIn("STATE.AUTHORIZATION_BINDING", issue_ids)

    def test_authorization_requires_active_source_binding_control_hash(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        state["events"][3]["details"]["source_binding_hash"] = state["events"][1][
            "details"
        ]["source_binding_hash"]
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.AUTHORIZATION_BINDING", issue_ids)
        self.assertIn("STATE.AUTHORIZATION", issue_ids)

    def test_narrative_release_cannot_opt_out_of_motivation_or_simplicity(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        mandatory = {"motivation_significance", "logical_simplicity"}
        for requirement in state["gate_applicability"]:
            if requirement["check_id"] in mandatory:
                requirement["applicability"] = "NOT_APPLICABLE"
                requirement["reason"] = "Attempted narrative hard-gate opt-out."
        state["attestations"] = [
            item for item in state["attestations"] if item["check_id"] not in mandatory
        ]
        state["artifacts"][0]["verification"]["check_ids"] = [
            check_id
            for check_id in state["artifacts"][0]["verification"]["check_ids"]
            if check_id not in mandatory
        ]
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "release_baseline.json"),
            candidate=load_json(FIXTURES / "release_candidate.json"),
            diff_map=load_json(FIXTURES / "release_diff_map.json"),
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.RELEASE_GATE_REGISTRY", issue_ids)

    def test_narrative_hard_gates_apply_before_diagnosis_and_implementation(self) -> None:
        routes = (
            (
                "valid_diagnostic_state.json",
                "diagnostic_baseline.json",
                "diagnostic",
            ),
            (
                "valid_ready_to_implement_revalidated.json",
                "revalidated_baseline.json",
                "ready-to-implement",
            ),
        )
        mandatory = {"motivation_significance", "logical_simplicity"}
        for state_name, baseline_name, check in routes:
            with self.subTest(check=check):
                state = load_json(FIXTURES / state_name)
                for requirement in state["gate_applicability"]:
                    if requirement["check_id"] in mandatory:
                        requirement["applicability"] = "NOT_APPLICABLE"
                        requirement["reason"] = "Attempted narrative hard-gate opt-out."
                state["attestations"] = [
                    item
                    for item in state["attestations"]
                    if item["check_id"] not in mandatory
                ]
                completed = run_materialized_documents(
                    state=state,
                    baseline=load_json(FIXTURES / baseline_name),
                    check=check,
                )
                self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
                issue_ids = {
                    item["check_id"] for item in json.loads(completed.stdout)["issues"]
                }
                self.assertIn("STATE.GATE_REGISTRY", issue_ids)

    def test_release_hash_is_recomputed_from_exact_artifact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            (artifact_root / "submission-final.txt").write_text(
                "Bytes changed after verification.\n", encoding="utf-8"
            )
            completed = run_validator(
                state=FIXTURES / "valid_ready_to_release.json",
                baseline=FIXTURES / "release_baseline.json",
                candidate=FIXTURES / "release_candidate.json",
                diff_map=FIXTURES / "release_diff_map.json",
                artifact_root=artifact_root,
                check="ready-to-release",
            )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.EXACT_ARTIFACT_HASH", issue_ids)

    def test_release_rehashes_authoritative_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            (source_root / "approved-source.txt").write_text(
                "Source bytes changed after the baseline was registered.\n",
                encoding="utf-8",
            )
            completed = run_validator(
                state=FIXTURES / "valid_ready_to_release.json",
                baseline=FIXTURES / "release_baseline.json",
                candidate=FIXTURES / "release_candidate.json",
                diff_map=FIXTURES / "release_diff_map.json",
                artifact_root=FIXTURES,
                source_root=source_root,
                check="ready-to-release",
            )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.EXACT_SOURCE_HASH", issue_ids)

    def test_release_rejects_unmapped_delta_even_when_all_candidate_hashes_are_refreshed(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        baseline = load_json(FIXTURES / "release_baseline.json")
        candidate = load_json(FIXTURES / "release_candidate.json")
        diff_map = load_json(FIXTURES / "release_diff_map.json")
        candidate_bytes = (FIXTURES / "submission-final.txt").read_bytes() + b"Unauthorized extra delta.\n"
        candidate_hash = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()
        artifact = state["artifacts"][0]
        artifact["candidate_hash"] = candidate_hash
        artifact["verification"]["candidate_hash"] = candidate_hash
        decision = state["decisions"][0]
        decision["implementation_result"]["candidate_hash"] = candidate_hash
        decision["verification_result"]["candidate_hash"] = candidate_hash
        for event in state["events"]:
            if event["artifact_hash"] is not None:
                event["artifact_hash"] = candidate_hash
        for attestation in state["attestations"]:
            if attestation["artifact_hash"] is not None:
                attestation["artifact_hash"] = candidate_hash
        candidate["artifacts"][0]["candidate_hash"] = candidate_hash
        diff_map["candidate_hash"] = candidate_hash
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            baseline_path = root / "baseline.json"
            candidate_path = root / "candidate.json"
            diff_path = root / "diff-map.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            (root / "submission-final.txt").write_bytes(candidate_bytes)
            completed = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=root,
                source_root=FIXTURES,
                check="ready-to-release",
            )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.DIFF_COVERAGE", issue_ids)

    def test_diagnostic_gate_failure_is_a_valid_assessment_not_a_validation_error(self) -> None:
        state = load_json(FIXTURES / "valid_diagnostic_state.json")
        motivation = next(
            item for item in state["attestations"] if item["check_id"] == "motivation_significance"
        )
        motivation["result"] = "FAIL"
        motivation["evidence"] = "The opening fails to expose the motivating problem before detail."
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "diagnostic_baseline.json"),
            check="diagnostic",
        )
        self.assert_pass(completed, "diagnostic")

        implementation_state = copy.deepcopy(state)
        implementation_state["run"]["operation"] = "RECEIPT"
        for requirement in implementation_state["gate_applicability"]:
            requirement["required_for"] = ["IMPLEMENTATION"]
        blocked = run_materialized_documents(
            state=implementation_state,
            baseline=load_json(FIXTURES / "diagnostic_baseline.json"),
            check="ready-to-implement",
        )
        self.assertEqual(blocked.returncode, 1, blocked.stderr + blocked.stdout)
        issue_ids = {item["check_id"] for item in json.loads(blocked.stdout)["issues"]}
        self.assertIn("STATE.ATTESTATION", issue_ids)

    def test_accepted_tradeoff_requires_exact_user_authority_event(self) -> None:
        state = load_json(FIXTURES / "valid_diagnostic_state.json")
        decision = state["decisions"][0]
        decision["accepted_tradeoff"] = {
            "user_choice": "Retain the bounded wording.",
            "disclosed_consequence": "The claim will sound narrower.",
            "accepted_by": "user",
            "timestamp": "2026-10-01T12:02:00Z",
            "source_fingerprint": decision["source_fingerprint"],
            "proposal_fingerprint": decision["proposal_fingerprint"],
        }
        baseline = load_json(FIXTURES / "diagnostic_baseline.json")
        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.ACCEPTED_TRADEOFF", issue_ids)

        state["events"].append(
            {
                "event_id": "EVT-DIAG-002",
                "event_type": "TRADEOFF_ACCEPTED",
                "decision_id": decision["decision_id"],
                "proposal_revision": decision["proposal_revision"],
                "artifact_id": None,
                "actor": "user",
                "authority_kind": "USER",
                "timestamp": decision["accepted_tradeoff"]["timestamp"],
                "prior_state": None,
                "new_state": None,
                "prior_support_status": None,
                "new_support_status": None,
                "prior_source_impact": None,
                "new_source_impact": None,
                "proposal_fingerprint": decision["proposal_fingerprint"],
                "source_id": decision["source_id"],
                "source_fingerprint": decision["source_fingerprint"],
                "artifact_hash": None,
                "authority_basis": "The user explicitly accepted the disclosed tradeoff.",
                "details": {
                    "accepted_tradeoff_hash": (
                        "sha256:"
                        + hashlib.sha256(
                            json.dumps(
                                decision["accepted_tradeoff"],
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest()
                    )
                },
            }
        )
        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            check="diagnostic",
        )
        self.assert_pass(completed, "diagnostic")

        decision["accepted_tradeoff"]["disclosed_consequence"] = (
            "A materially different consequence that the user did not accept."
        )
        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.ACCEPTED_TRADEOFF", issue_ids)

    def test_valid_authorized_local_fix_is_ready_to_release(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        baseline = load_json(FIXTURES / "release_baseline.json")
        candidate = load_json(FIXTURES / "release_candidate.json")
        diff_map = load_json(FIXTURES / "release_diff_map.json")
        candidate_bytes = (FIXTURES / "submission-final.txt").read_bytes() + b"Punctuation corrected.\n"
        candidate_hash = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()
        candidate_name = "submission-with-local-fix.txt"
        artifact = state["artifacts"][0]
        artifact["path"] = candidate_name
        artifact["candidate_hash"] = candidate_hash
        artifact["verification"]["candidate_hash"] = candidate_hash
        decision = state["decisions"][0]
        decision["implementation_result"]["candidate_hash"] = candidate_hash
        decision["verification_result"]["candidate_hash"] = candidate_hash
        for event in state["events"]:
            if event["artifact_hash"] is not None:
                event["artifact_hash"] = candidate_hash
        for attestation in state["attestations"]:
            if attestation["artifact_hash"] is not None:
                attestation["artifact_hash"] = candidate_hash
        candidate["artifacts"][0]["path"] = candidate_name
        candidate["artifacts"][0]["candidate_hash"] = candidate_hash
        diff_map["candidate_hash"] = candidate_hash
        line = b"Punctuation corrected.\n"
        add_valid_local_fix(
            state,
            diff_map,
            hunk_coverage={
                "operation": "insert",
                "baseline_start": 2,
                "baseline_end": 2,
                "candidate_start": 2,
                "candidate_end": 3,
                "baseline_lines_hash": "sha256:" + hashlib.sha256(b"").hexdigest(),
                "candidate_lines_hash": "sha256:" + hashlib.sha256(line).hexdigest(),
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            baseline_path = root / "baseline.json"
            candidate_path = root / "candidate.json"
            diff_path = root / "diff-map.json"
            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            state_path.write_text(json.dumps(state), encoding="utf-8")
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            diff_path.write_text(json.dumps(diff_map), encoding="utf-8")
            (artifact_root / candidate_name).write_bytes(candidate_bytes)
            completed = run_validator(
                state=state_path,
                baseline=baseline_path,
                candidate=candidate_path,
                diff_map=diff_path,
                artifact_root=artifact_root,
                source_root=FIXTURES,
                check="ready-to-release",
            )
        self.assert_pass(completed, "ready-to-release")

    def test_unverified_artifact_creation_must_precede_implementation(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        baseline = load_json(FIXTURES / "revalidated_baseline.json")
        original = state["decisions"][0]
        implemented = copy.deepcopy(original)
        implemented["decision_id"] = "GS-002"
        implemented["decision_state"] = "IMPLEMENTED"
        implemented["source_bindings"][0]["event_id"] = "EVT-PREM-001"
        implemented["source_bindings"][0]["timestamp"] = "2026-10-01T13:05:00Z"
        implemented["source_bindings"][1]["event_id"] = "EVT-PREM-003"
        implemented["source_bindings"][1]["timestamp"] = "2026-10-01T13:07:00Z"
        candidate_hash = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        implemented["implementation_result"] = {
            "artifact_id": "ART-PREMATURE",
            "candidate_hash": candidate_hash,
            "diff_hunk_ids": ["HUNK-PREMATURE"],
            "implemented_at": "2026-10-01T13:09:00Z",
            "actor": "assistant",
        }
        state["decisions"].append(implemented)
        state["artifacts"].append(
            {
                "artifact_id": "ART-PREMATURE",
                "path": "fixtures/premature.docx",
                "format": "DOCX",
                "baseline_source_ids": ["SRC-NEW"],
                "source_hash": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "candidate_hash": candidate_hash,
                "relationship_to_baseline": "DERIVED",
                "actual_submission_artifact": False,
                "layout_relevant": False,
                "artifact_status": "UNVERIFIED",
                "created_at": "2026-10-01T13:10:00Z",
                "verification": None,
            }
        )
        cloned_events = []
        cloned_times = (
            "2026-10-01T13:05:00Z",
            "2026-10-01T13:06:00Z",
            "2026-10-01T13:07:00Z",
            "2026-10-01T13:08:00Z",
        )
        for index, event in enumerate(copy.deepcopy(state["events"])):
            cloned = copy.deepcopy(event)
            cloned["event_id"] = f"EVT-PREM-{index + 1:03d}"
            cloned["decision_id"] = "GS-002"
            cloned["timestamp"] = cloned_times[index]
            cloned_events.append(cloned)
        implementation_event = copy.deepcopy(cloned_events[-1])
        implementation_event.update(
            {
                "event_id": "EVT-PREM-005",
                "event_type": "DECISION_IMPLEMENTED",
                "actor": "assistant",
                "authority_kind": "ASSISTANT",
                "timestamp": "2026-10-01T13:09:00Z",
                "prior_state": "AUTHORIZED",
                "new_state": "IMPLEMENTED",
                "artifact_id": "ART-PREMATURE",
                "artifact_hash": candidate_hash,
                "authority_basis": "Implemented the authorized intervention.",
            }
        )
        creation_event = copy.deepcopy(implementation_event)
        creation_event.update(
            {
                "event_id": "EVT-PREM-006",
                "event_type": "ARTIFACT_CREATED",
                "decision_id": None,
                "proposal_revision": None,
                "timestamp": "2026-10-01T13:10:00Z",
                "prior_state": None,
                "new_state": None,
                "proposal_fingerprint": None,
                "authority_basis": "Registered the exact generated candidate.",
            }
        )
        state["events"].extend(cloned_events + [implementation_event, creation_event])
        state["run"]["updated_at"] = "2026-10-01T13:10:00Z"
        state["attestations"][0]["timestamp"] = "2026-10-01T13:07:30Z"
        state["attestations"][1]["timestamp"] = "2026-10-01T13:07:40Z"
        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertNotIn("STATE.SCHEMA", {item["check_id"] for item in payload["issues"]})
        self.assertIn("STATE.ARTIFACT_BINDING", {item["check_id"] for item in payload["issues"]})

    def test_local_fix_authorization_must_precede_creation_by_event_order(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        baseline = load_json(FIXTURES / "release_baseline.json")
        candidate = load_json(FIXTURES / "release_candidate.json")
        diff_map = load_json(FIXTURES / "release_diff_map.json")
        add_valid_local_fix(state, diff_map)
        authorization = state["events"].pop(3)
        authorization["timestamp"] = "2026-10-01T14:04:00Z"
        state["local_fix_log"][0]["authorized_at"] = "2026-10-01T14:04:00Z"
        state["events"].insert(4, authorization)
        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            candidate=candidate,
            diff_map=diff_map,
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertIn("STATE.LOCAL_FIX", {item["check_id"] for item in payload["issues"]})

    def test_later_local_fix_failure_cannot_hide_after_verification(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        baseline = load_json(FIXTURES / "release_baseline.json")
        candidate = load_json(FIXTURES / "release_candidate.json")
        diff_map = load_json(FIXTURES / "release_diff_map.json")
        add_valid_local_fix(state, diff_map)
        failed = copy.deepcopy(state["attestations"][-1])
        failed.update(
            {
                "attestation_id": "ATT-REL-LF-002",
                "result": "FAIL",
                "timestamp": "2026-10-01T14:21:00Z",
                "evidence": "A later review found that the local edit changes meaning.",
            }
        )
        state["attestations"].append(failed)
        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            candidate=candidate,
            diff_map=diff_map,
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.ATTESTATION_SEQUENCE", issue_ids)
        self.assertIn("STATE.LOCAL_FIX", issue_ids)

    def test_release_attestation_must_be_strictly_after_creation(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        for attestation in state["attestations"]:
            attestation["timestamp"] = state["artifacts"][0]["created_at"]
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "release_baseline.json"),
            candidate=load_json(FIXTURES / "release_candidate.json"),
            diff_map=load_json(FIXTURES / "release_diff_map.json"),
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        self.assertIn(
            "STATE.ATTESTATION_SEQUENCE",
            {item["check_id"] for item in json.loads(completed.stdout)["issues"]},
        )

    def test_pdf_path_cannot_be_relabelled_to_bypass_layout_gates(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        candidate = load_json(FIXTURES / "release_candidate.json")
        artifact = state["artifacts"][0]
        artifact["path"] = "synthetic-submission.pdf"
        artifact["format"] = "OTHER"
        artifact["layout_relevant"] = False
        artifact["verification"]["layout_result"] = "NOT_APPLICABLE"
        artifact["verification"]["check_ids"].remove("layout_verification")
        candidate["artifacts"][0]["path"] = "synthetic-submission.pdf"
        candidate["artifacts"][0]["format"] = "OTHER"
        layout_requirement = next(
            item for item in state["gate_applicability"] if item["check_id"] == "layout_verification"
        )
        layout_requirement["applicability"] = "NOT_APPLICABLE"
        state["attestations"] = [
            item for item in state["attestations"] if item["check_id"] != "layout_verification"
        ]
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "release_baseline.json"),
            candidate=candidate,
            diff_map=load_json(FIXTURES / "release_diff_map.json"),
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.ARTIFACT_FORMAT", issue_ids)
        self.assertIn("STATE.LAYOUT_VERIFICATION", issue_ids)

    def test_each_reauthorization_replays_dependency_state(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        original_events = copy.deepcopy(state["events"])
        dependency = copy.deepcopy(state["decisions"][0])
        dependency["decision_id"] = "GS-002"
        dependency["source_bindings"][0]["event_id"] = "EVT-DEP-001"
        dependency["source_bindings"][1]["event_id"] = "EVT-DEP-003"
        state["decisions"].append(dependency)

        dependency_ref = {"decision_id": "GS-002", "proposal_revision": 1}
        state["decisions"][0]["dependencies"] = [dependency_ref]
        encoded_dependencies = json.dumps(
            [dependency_ref], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        dependency_hash = f"sha256:{hashlib.sha256(encoded_dependencies).hexdigest()}"
        for binding in state["decisions"][0]["source_bindings"]:
            binding["dependency_set_hash"] = dependency_hash
        original_events[2]["details"]["dependency_set_hash"] = dependency_hash

        dependency_events = []
        for index, event in enumerate(copy.deepcopy(original_events)):
            cloned = copy.deepcopy(event)
            cloned["event_id"] = f"EVT-DEP-{index + 1:03d}"
            cloned["decision_id"] = "GS-002"
            if index == 2:
                cloned["details"]["dependency_set_hash"] = dependency["source_bindings"][1][
                    "dependency_set_hash"
                ]
            dependency_events.append(cloned)
        state["events"] = [
            original_events[0],
            dependency_events[0],
            original_events[1],
            dependency_events[1],
            original_events[2],
            dependency_events[2],
            dependency_events[3],
            original_events[3],
        ]

        def transition(
            event_id: str,
            decision_id: str,
            timestamp: str,
            prior_state: str,
            new_state: str,
        ) -> dict[str, Any]:
            event = copy.deepcopy(original_events[3])
            event.update(
                {
                    "event_id": event_id,
                    "decision_id": decision_id,
                    "timestamp": timestamp,
                    "prior_state": prior_state,
                    "new_state": new_state,
                    "authority_basis": "Explicit user state transition for chronology testing.",
                }
            )
            return event

        state["events"].extend(
            [
                transition("EVT-DEP-005", "GS-002", "2026-10-01T13:05:00Z", "AUTHORIZED", "HELD"),
                transition("EVT-OWN-005", "GS-001", "2026-10-01T13:06:00Z", "AUTHORIZED", "HELD"),
                transition("EVT-OWN-006", "GS-001", "2026-10-01T13:07:00Z", "HELD", "APPROVED"),
                transition("EVT-OWN-007", "GS-001", "2026-10-01T13:08:00Z", "APPROVED", "AUTHORIZED"),
                transition("EVT-DEP-006", "GS-002", "2026-10-01T13:09:00Z", "HELD", "APPROVED"),
                transition("EVT-DEP-007", "GS-002", "2026-10-01T13:10:00Z", "APPROVED", "AUTHORIZED"),
            ]
        )
        state["run"]["updated_at"] = "2026-10-01T13:10:00Z"
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.DEPENDENCY", issue_ids)

    def test_historical_conflict_coactivity_requires_compatibility_resolution(self) -> None:
        case = load_json(FIXTURES / "invalid_unresolved_conflict.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        state["decisions"][1]["decision_state"] = "HELD"
        held_event = copy.deepcopy(state["events"][-1])
        held_event.update(
            {
                "event_id": "EVT-IMPL-105",
                "timestamp": "2026-10-01T13:09:00Z",
                "prior_state": "AUTHORIZED",
                "new_state": "HELD",
                "authority_basis": "The user held the competing decision after reviewing it.",
            }
        )
        state["events"].append(held_event)
        state["attestations"][0]["timestamp"] = "2026-10-01T13:07:30Z"
        state["attestations"][1]["timestamp"] = "2026-10-01T13:07:40Z"
        state["run"]["updated_at"] = "2026-10-01T13:09:00Z"
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / case["baseline"]),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.CONFLICT", issue_ids)

    def test_reverse_one_way_conflict_replays_historical_coactivity_fail_closed(self) -> None:
        case = load_json(FIXTURES / "invalid_unresolved_conflict.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        # Retain only the lexically later -> earlier declaration, which used to
        # bypass the `key < target` replay branch. Both decisions were already
        # AUTHORIZED before the earlier decision was subsequently held.
        state["decisions"][0]["conflicts"] = []
        state["decisions"][1]["conflicts"] = [
            {"decision_id": "GS-001", "proposal_revision": 1}
        ]
        state["decisions"][0]["decision_state"] = "HELD"
        held_event = copy.deepcopy(state["events"][3])
        held_event.update(
            {
                "event_id": "EVT-IMPL-005",
                "timestamp": "2026-10-01T13:09:00Z",
                "prior_state": "AUTHORIZED",
                "new_state": "HELD",
                "authority_basis": "The user held GS-001 after both conflicting decisions were active.",
            }
        )
        state["events"].append(held_event)
        state["attestations"][0]["timestamp"] = "2026-10-01T13:07:30Z"
        state["attestations"][1]["timestamp"] = "2026-10-01T13:07:40Z"
        state["run"]["updated_at"] = "2026-10-01T13:09:00Z"

        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / case["baseline"]),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        conflict_issues = [
            item
            for item in json.loads(completed.stdout)["issues"]
            if item["check_id"] == "STATE.CONFLICT"
        ]
        self.assertTrue(
            any(
                item["severity"] == "ERROR" and "not reciprocal" in item["explanation"]
                for item in conflict_issues
            )
        )
        self.assertTrue(
            any("simultaneously active" in item["explanation"] for item in conflict_issues)
        )

    def test_revalidation_anchor_chain_is_append_only_even_when_changed(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        state["run"]["operation"] = "DIAGNOSE"
        decision = state["decisions"][0]
        decision["decision_state"] = "PROPOSED"
        decision["source_impact"] = "REVALIDATION_REQUIRED"
        second_binding = decision["source_bindings"][1]
        second_binding["comparison_result"] = "REVALIDATION_REQUIRED"
        second_binding["old_anchor_hash"] = (
            "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        )
        second_binding["new_anchor_hash"] = (
            "sha256:d1f815ce46011807ae669a162d5e315d980bfcf60ef01f21d3b119c887445122"
        )
        revalidation_event = state["events"][2]
        revalidation_event["new_source_impact"] = "REVALIDATION_REQUIRED"
        revalidation_event["details"]["comparison_result"] = "REVALIDATION_REQUIRED"
        revalidation_event["details"]["old_anchor_hash"] = second_binding["old_anchor_hash"]
        revalidation_event["details"]["new_anchor_hash"] = second_binding["new_anchor_hash"]
        state["events"] = [state["events"][0], revalidation_event]
        for requirement in state["gate_applicability"]:
            requirement["required_for"] = ["DIAGNOSTIC"]
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.SOURCE_BINDING", issue_ids)

    def test_artifact_verification_event_cannot_bind_an_orphan_hash(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        orphaned = copy.deepcopy(state["events"][-1])
        orphaned.update(
            {
                "event_id": "EVT-REL-008",
                "timestamp": "2026-10-01T14:21:00Z",
                "artifact_hash": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            }
        )
        state["events"].append(orphaned)
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "release_baseline.json"),
            candidate=load_json(FIXTURES / "release_candidate.json"),
            diff_map=load_json(FIXTURES / "release_diff_map.json"),
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.ARTIFACT_BINDING", issue_ids)

    def test_unchanged_hop_cannot_launder_prior_material_source_change(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        baseline = load_json(FIXTURES / "revalidated_baseline.json")
        mid_fingerprint = "sha256:5555555555555555555555555555555555555555555555555555555555555555"
        mid_source = copy.deepcopy(state["sources"][0])
        mid_source.update(
            {
                "source_id": "SRC-MID",
                "path": "fixtures/draft-mid.docx",
                "name": "draft-mid.docx",
                "byte_hash": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
                "extracted_text_hash": mid_fingerprint,
                "modified_at": "2026-10-01T12:45:00Z",
                "authority_basis": "Intermediate draft retained for append-only provenance.",
            }
        )
        state["sources"].insert(1, mid_source)
        mid_baseline = copy.deepcopy(baseline["sources"][0])
        for field in (
            "source_id",
            "path",
            "byte_hash",
            "extracted_text_hash",
            "user_designated_role",
            "content_authority",
            "layout_authority",
            "editable_target",
            "equivalence_status",
            "version_designation",
        ):
            mid_baseline[field] = mid_source[field]
        baseline["sources"].insert(1, mid_baseline)

        decision = state["decisions"][0]
        later_binding = decision["source_bindings"][1]
        mid_binding = copy.deepcopy(later_binding)
        mid_binding.update(
            {
                "event_id": "EVT-IMPL-002A",
                "source_id": "SRC-MID",
                "source_fingerprint": mid_fingerprint,
                "timestamp": "2026-10-01T13:02:30Z",
                "old_source_id": "SRC-OLD",
                "old_source_fingerprint": decision["source_bindings"][0]["source_fingerprint"],
                "comparison_result": "REVALIDATION_REQUIRED",
            }
        )
        later_binding["old_source_id"] = "SRC-MID"
        later_binding["old_source_fingerprint"] = mid_fingerprint
        decision["source_bindings"].insert(1, mid_binding)

        later_event = state["events"][2]
        mid_event = copy.deepcopy(later_event)
        mid_event.update(
            {
                "event_id": "EVT-IMPL-002A",
                "source_id": "SRC-MID",
                "source_fingerprint": mid_fingerprint,
                "timestamp": "2026-10-01T13:02:30Z",
                "prior_source_impact": "CURRENT",
                "new_source_impact": "REVALIDATION_REQUIRED",
            }
        )
        mid_event["details"].update(
            {
                "old_source_id": "SRC-OLD",
                "old_source_fingerprint": decision["source_bindings"][0]["source_fingerprint"],
                "new_source_id": "SRC-MID",
                "new_source_fingerprint": mid_fingerprint,
                "comparison_result": "REVALIDATION_REQUIRED",
            }
        )
        later_event["prior_source_impact"] = "REVALIDATION_REQUIRED"
        later_event["details"]["old_source_id"] = "SRC-MID"
        later_event["details"]["old_source_fingerprint"] = mid_fingerprint
        state["events"].insert(2, mid_event)
        held_event = copy.deepcopy(state["events"][1])
        held_event.update(
            {
                "event_id": "EVT-IMPL-002B",
                "timestamp": "2026-10-01T13:02:40Z",
                "prior_state": "APPROVED",
                "new_state": "HELD",
                "source_id": "SRC-MID",
                "source_fingerprint": mid_fingerprint,
                "authority_basis": "The proposal was held after the material source finding.",
            }
        )
        reapplied_approval = copy.deepcopy(state["events"][1])
        reapplied_approval.update(
            {
                "event_id": "EVT-IMPL-003A",
                "timestamp": "2026-10-01T13:03:30Z",
                "prior_state": "HELD",
                "new_state": "APPROVED",
                "source_id": "SRC-NEW",
                "source_fingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "authority_basis": "Attempted in-place reapproval of the invalidated revision.",
            }
        )
        state["events"].insert(3, held_event)
        state["events"].insert(5, reapplied_approval)

        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.SOURCE_REVALIDATION", issue_ids)

    def test_duplicate_verification_cannot_hide_a_late_edit(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        modified = copy.deepcopy(state["events"][3])
        modified.update(
            {
                "event_id": "EVT-REL-008",
                "event_type": "ARTIFACT_MODIFIED",
                "timestamp": "2026-10-01T14:20:00Z",
                "authority_basis": "A post-verification edit was made to the artifact.",
            }
        )
        duplicate_verification = copy.deepcopy(state["events"][-1])
        duplicate_verification["event_id"] = "EVT-REL-009"
        state["events"].extend([modified, duplicate_verification])
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "release_baseline.json"),
            candidate=load_json(FIXTURES / "release_candidate.json"),
            diff_map=load_json(FIXTURES / "release_diff_map.json"),
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.LATE_EDIT", issue_ids)
        self.assertIn("STATE.ARTIFACT_BINDING", issue_ids)

    def test_equal_timestamp_source_events_cannot_reverse_binding_order(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        baseline = load_json(FIXTURES / "revalidated_baseline.json")
        mid_fingerprint = "sha256:5555555555555555555555555555555555555555555555555555555555555555"
        mid_source = copy.deepcopy(state["sources"][0])
        mid_source.update(
            {
                "source_id": "SRC-MID",
                "path": "fixtures/draft-mid.docx",
                "name": "draft-mid.docx",
                "byte_hash": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
                "extracted_text_hash": mid_fingerprint,
                "modified_at": "2026-10-01T12:45:00Z",
                "authority_basis": "Intermediate draft retained for append-only provenance.",
            }
        )
        state["sources"].insert(1, mid_source)
        mid_baseline = copy.deepcopy(baseline["sources"][0])
        for field in (
            "source_id",
            "path",
            "byte_hash",
            "extracted_text_hash",
            "user_designated_role",
            "content_authority",
            "layout_authority",
            "editable_target",
            "equivalence_status",
            "version_designation",
        ):
            mid_baseline[field] = mid_source[field]
        baseline["sources"].insert(1, mid_baseline)

        decision = state["decisions"][0]
        new_binding = decision["source_bindings"][1]
        mid_binding = copy.deepcopy(new_binding)
        mid_binding.update(
            {
                "event_id": "EVT-IMPL-005",
                "source_id": "SRC-MID",
                "source_fingerprint": mid_fingerprint,
                "timestamp": "2026-10-01T13:04:00Z",
                "old_source_id": "SRC-OLD",
                "old_source_fingerprint": decision["source_bindings"][0]["source_fingerprint"],
            }
        )
        new_binding.update(
            {
                "timestamp": "2026-10-01T13:04:00Z",
                "old_source_id": "SRC-MID",
                "old_source_fingerprint": mid_fingerprint,
            }
        )
        decision["source_bindings"].insert(1, mid_binding)

        new_event = state["events"][2]
        new_event["timestamp"] = "2026-10-01T13:04:00Z"
        new_event["details"]["old_source_id"] = "SRC-MID"
        new_event["details"]["old_source_fingerprint"] = mid_fingerprint
        mid_event = copy.deepcopy(new_event)
        mid_event.update(
            {
                "event_id": "EVT-IMPL-005",
                "source_id": "SRC-MID",
                "source_fingerprint": mid_fingerprint,
                "prior_source_impact": "UNCHANGED",
                "new_source_impact": "UNCHANGED",
            }
        )
        mid_event["details"].update(
            {
                "old_source_id": "SRC-OLD",
                "old_source_fingerprint": decision["source_bindings"][0]["source_fingerprint"],
                "new_source_id": "SRC-MID",
                "new_source_fingerprint": mid_fingerprint,
            }
        )
        state["events"] = [
            state["events"][0],
            state["events"][1],
            new_event,
            state["events"][3],
            mid_event,
        ]
        state["attestations"][0]["timestamp"] = "2026-10-01T13:04:30Z"
        state["attestations"][1]["timestamp"] = "2026-10-01T13:04:40Z"

        completed = run_materialized_documents(
            state=state,
            baseline=baseline,
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.SOURCE_BINDING", issue_ids)

    def test_same_timestamp_lock_release_cannot_retroactively_authorize(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        state["locks"].append(
            {
                "lock_id": "LOCK-1",
                "type": "USER_LOCK",
                "scope_anchor": "Future program opening",
                "reason": "Preserve this passage until the user explicitly releases it.",
                "creating_authority": "user",
                "source_fingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "status": "RELEASED",
                "release_condition": "The user explicitly releases LOCK-1.",
                "created_at": "2026-10-01T13:03:30Z",
                "released_at": "2026-10-01T13:04:00Z",
                "released_by": "user",
            }
        )
        lock = state["locks"][-1]
        state["decisions"][0]["affected_lock_ids"] = ["LOCK-1"]
        created_event = {
            "event_id": "EVT-LOCK-001",
            "event_type": "LOCK_CREATED",
            "decision_id": None,
            "proposal_revision": None,
            "artifact_id": None,
            "actor": "user",
            "authority_kind": "USER",
            "timestamp": "2026-10-01T13:03:30Z",
            "prior_state": None,
            "new_state": None,
            "prior_support_status": None,
            "new_support_status": None,
            "prior_source_impact": None,
            "new_source_impact": None,
            "proposal_fingerprint": None,
            "source_id": "SRC-NEW",
            "source_fingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
            "artifact_hash": None,
            "authority_basis": "The user locked the scoped passage.",
            "details": {
                "lock_id": lock["lock_id"],
                "lock_payload_hash": lock_creation_payload_hash(lock),
            },
        }
        released_event = copy.deepcopy(created_event)
        released_event.update(
            {
                "event_id": "EVT-LOCK-002",
                "event_type": "LOCK_RELEASED",
                "timestamp": "2026-10-01T13:04:00Z",
                "authority_basis": "The user released the scoped passage.",
            }
        )
        released_event["details"] = {
            "lock_id": lock["lock_id"],
            "lock_release_payload_hash": lock_release_payload_hash(lock),
        }
        state["events"].insert(3, created_event)
        state["events"].append(released_event)
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertNotIn("STATE.SCHEMA", issue_ids)
        self.assertIn("STATE.LOCK", issue_ids)

    def test_broad_scope_lock_cannot_be_omitted_from_narrower_decision_metadata(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_implement_revalidated.json")
        state["locks"].append(
            {
                "lock_id": "LOCK-OMITTED",
                "type": "USER_LOCK",
                "scope_anchor": "Future program",
                "reason": "Preserve this passage until explicit release.",
                "creating_authority": "user",
                "source_fingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "status": "ACTIVE",
                "release_condition": "The user explicitly releases LOCK-OMITTED.",
                "created_at": "2026-10-01T13:03:30Z",
                "released_at": None,
                "released_by": None,
            }
        )
        lock = state["locks"][-1]
        state["events"].insert(
            3,
            {
                "event_id": "EVT-LOCK-OMITTED",
                "event_type": "LOCK_CREATED",
                "decision_id": None,
                "proposal_revision": None,
                "artifact_id": None,
                "actor": "user",
                "authority_kind": "USER",
                "timestamp": "2026-10-01T13:03:30Z",
                "prior_state": None,
                "new_state": None,
                "prior_support_status": None,
                "new_support_status": None,
                "prior_source_impact": None,
                "new_source_impact": None,
                "proposal_fingerprint": None,
                "source_id": "SRC-NEW",
                "source_fingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "artifact_hash": None,
                "authority_basis": "The user locked the broader future-program scope.",
                "details": {
                    "lock_id": lock["lock_id"],
                    "lock_payload_hash": lock_creation_payload_hash(lock),
                },
            },
        )
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        lock_issues = [
            item for item in json.loads(completed.stdout)["issues"] if item["check_id"] == "STATE.LOCK"
        ]
        self.assertTrue(any("omitted from affected_lock_ids" in item["explanation"] for item in lock_issues))

        state["locks"][0]["scope_anchor"] = "Aim 1"
        state["events"][3]["details"]["lock_payload_hash"] = lock_creation_payload_hash(
            state["locks"][0]
        )
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "revalidated_baseline.json"),
            check="ready-to-implement",
        )
        self.assert_pass(completed, "ready-to-implement")

    def test_conflict_and_lock_controls_are_approval_fingerprinted(self) -> None:
        for field, value in (
            ("affected_lock_ids", ["LOCK-UNAPPROVED"]),
            ("conflicts", [{"decision_id": "GS-099", "proposal_revision": 1}]),
        ):
            with self.subTest(field=field):
                state = load_json(FIXTURES / "valid_diagnostic_state.json")
                state["decisions"][0][field] = value
                completed = run_materialized_documents(
                    state=state,
                    baseline=load_json(FIXTURES / "diagnostic_baseline.json"),
                    check="diagnostic",
                )
                self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
                issue_ids = {
                    item["check_id"] for item in json.loads(completed.stdout)["issues"]
                }
                self.assertIn("STATE.PROPOSAL_FINGERPRINT", issue_ids)

    def test_both_compatible_resolution_requires_user_authority_event(self) -> None:
        case = load_json(FIXTURES / "invalid_unresolved_conflict.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        state["decisions"][0]["conflict_resolutions"] = [
            {
                "with_decision": {"decision_id": "GS-002", "proposal_revision": 1},
                "resolution": "BOTH_COMPATIBLE",
                "rationale": "The two interventions affect distinct wording surfaces.",
                "authority_basis": "Assistant assertion without user acceptance.",
            }
        ]
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / case["baseline"]),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.CONFLICT_AUTHORITY", issue_ids)

    def test_both_compatible_acceptance_cannot_be_recorded_after_activation(self) -> None:
        case = load_json(FIXTURES / "invalid_unresolved_conflict.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        decision = state["decisions"][0]
        resolution = {
            "with_decision": {"decision_id": "GS-002", "proposal_revision": 1},
            "resolution": "BOTH_COMPATIBLE",
            "rationale": "The two interventions affect distinct wording surfaces.",
            "authority_basis": "The user accepted compatibility only after activation.",
        }
        decision["conflict_resolutions"] = [resolution]
        state["events"].append(
            {
                "event_id": "EVT-CONFLICT-LATE",
                "event_type": "CONFLICT_RESOLUTION_ACCEPTED",
                "decision_id": decision["decision_id"],
                "proposal_revision": decision["proposal_revision"],
                "artifact_id": None,
                "actor": "user",
                "authority_kind": "USER",
                "timestamp": "2026-10-01T13:09:00Z",
                "prior_state": None,
                "new_state": None,
                "prior_support_status": None,
                "new_support_status": None,
                "prior_source_impact": None,
                "new_source_impact": None,
                "proposal_fingerprint": decision["proposal_fingerprint"],
                "source_id": "SRC-NEW",
                "source_fingerprint": "sha256:" + "d" * 64,
                "artifact_hash": None,
                "authority_basis": "The user accepted compatibility only after both decisions were authorized.",
                "details": {
                    "conflict_resolution_hash": canonical_hash(resolution),
                },
            }
        )

        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / case["baseline"]),
            check="ready-to-implement",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issues = json.loads(completed.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.CONFLICT_AUTHORITY"
                and "precede" in item["explanation"]
                for item in issues
            )
        )

    def test_active_lock_created_after_verified_work_does_not_rewrite_history(self) -> None:
        state = load_json(FIXTURES / "valid_ready_to_release.json")
        state["locks"].append(
            {
                "lock_id": "LOCK-AFTER",
                "type": "USER_LOCK",
                "scope_anchor": "Future program opening",
                "reason": "Prevent any later edits to the already verified passage.",
                "creating_authority": "user",
                "source_fingerprint": "sha256:cf40fbd1b90427f1d79b335a2adcf4b3bf593afea52350b57d90789d043861f1",
                "status": "ACTIVE",
                "release_condition": "The user explicitly releases LOCK-AFTER.",
                "created_at": "2026-10-01T14:21:00Z",
                "released_at": None,
                "released_by": None,
            }
        )
        lock = state["locks"][-1]
        state["events"].append(
            {
                "event_id": "EVT-REL-LOCK-001",
                "event_type": "LOCK_CREATED",
                "decision_id": None,
                "proposal_revision": None,
                "artifact_id": None,
                "actor": "user",
                "authority_kind": "USER",
                "timestamp": "2026-10-01T14:21:00Z",
                "prior_state": None,
                "new_state": None,
                "prior_support_status": None,
                "new_support_status": None,
                "prior_source_impact": None,
                "new_source_impact": None,
                "proposal_fingerprint": None,
                "source_id": "SRC-RELEASE",
                "source_fingerprint": "sha256:cf40fbd1b90427f1d79b335a2adcf4b3bf593afea52350b57d90789d043861f1",
                "artifact_hash": None,
                "authority_basis": "The user locked the already verified passage against future edits.",
                "details": {
                    "lock_id": lock["lock_id"],
                    "lock_payload_hash": lock_creation_payload_hash(lock),
                },
            }
        )
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "release_baseline.json"),
            candidate=load_json(FIXTURES / "release_candidate.json"),
            diff_map=load_json(FIXTURES / "release_diff_map.json"),
            check="ready-to-release",
        )
        self.assert_pass(completed, "ready-to-release")
        state["locks"][0]["reason"] = "Mutated reason not present at lock creation."
        completed = run_materialized_documents(
            state=state,
            baseline=load_json(FIXTURES / "release_baseline.json"),
            candidate=load_json(FIXTURES / "release_candidate.json"),
            diff_map=load_json(FIXTURES / "release_diff_map.json"),
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issues = json.loads(completed.stdout)["issues"]
        self.assertTrue(
            any(
                item["check_id"] == "STATE.LOCK"
                and "canonical LOCK_CREATED" in item["explanation"]
                for item in issues
            )
        )

    def test_diagnostic_can_record_unresolved_content_authority(self) -> None:
        case = load_json(FIXTURES / "valid_unresolved_content_authority.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        baseline = apply_mutations(
            load_json(FIXTURES / case["baseline"]), case.get("baseline_mutations", [])
        )
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            state_path = temporary_path / "state.json"
            baseline_path = temporary_path / "baseline.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            completed = run_validator(
                state=state_path,
                baseline=baseline_path,
                check=case["check"],
            )
        payload = self.assert_pass(completed, "diagnostic")
        warning_ids = {
            issue["check_id"] for issue in payload["issues"] if issue["severity"] == "WARNING"
        }
        self.assertTrue(set(case["expected_warning_ids"]).issubset(warning_ids))

    def test_unresolved_authority_cannot_turn_narrative_hard_gates_off(self) -> None:
        case = load_json(FIXTURES / "valid_unresolved_content_authority.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        for requirement in state["gate_applicability"]:
            if requirement["check_id"] in {"motivation_significance", "logical_simplicity"}:
                requirement["applicability"] = "NOT_APPLICABLE"
                requirement["reason"] = "Attempted opt-out while authority is unresolved."
        completed = run_materialized_documents(
            state=state,
            baseline=apply_mutations(
                load_json(FIXTURES / case["baseline"]), case.get("baseline_mutations", [])
            ),
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        issue_ids = {item["check_id"] for item in json.loads(completed.stdout)["issues"]}
        self.assertIn("STATE.GATE_REGISTRY", issue_ids)

    def test_release_allows_append_only_superseded_implementation_history(self) -> None:
        case = load_json(FIXTURES / "valid_release_with_superseded_history.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            state_path = temporary_path / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            completed = run_validator(
                state=state_path,
                baseline=FIXTURES / case["baseline"],
                candidate=FIXTURES / case["candidate"],
                diff_map=FIXTURES / case["diff_map"],
                check=case["check"],
            )
        self.assert_pass(completed, "ready-to-release")

    def test_supersession_links_cannot_form_a_reverse_revision_cycle(self) -> None:
        case = load_json(FIXTURES / "valid_release_with_superseded_history.case.json")
        state = apply_mutations(
            load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
        )
        older = state["decisions"][1]
        newer = state["decisions"][2]
        older["supersession_links"].append(
            {"relation": "SUPERSEDES", "decision_id": "GS-099", "proposal_revision": 2}
        )
        newer["decision_state"] = "SUPERSEDED"
        newer["supersession_links"].append(
            {"relation": "SUPERSEDED_BY", "decision_id": "GS-099", "proposal_revision": 1}
        )
        state["events"][16]["new_state"] = "SUPERSEDED"

        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            completed = run_validator(
                state=state_path,
                baseline=FIXTURES / case["baseline"],
                candidate=FIXTURES / case["candidate"],
                diff_map=FIXTURES / case["diff_map"],
                check=case["check"],
            )
        self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertIn(
            "STATE.SUPERSESSION",
            {issue["check_id"] for issue in payload["issues"]},
        )

    def test_invalid_fixture_cases_fail_with_expected_issue_ids(self) -> None:
        case_paths = sorted(FIXTURES.glob("invalid_*.case.json"))
        case_names = {path.name for path in case_paths}
        audit_regressions = {
            "invalid_empty_candidate_manifest.case.json",
            "invalid_non_object_diff_map.case.json",
            "invalid_unauthorized_implementation_result.case.json",
            "invalid_cross_artifact_decision.case.json",
            "invalid_changed_anchor_carry_forward.case.json",
            "invalid_changed_protected_intent_carry_forward.case.json",
            "invalid_collapsed_confirmation_approval.case.json",
            "invalid_assistant_self_authorization.case.json",
            "invalid_historical_source_attestation.case.json",
            "invalid_post_verification_attestation.case.json",
            "invalid_later_fail_same_timestamp.case.json",
            "invalid_docx_layout_authority.case.json",
            "invalid_local_fix_category.case.json",
            "invalid_local_fix_reverse_mapping.case.json",
            "invalid_conflict_resolution_orientation.case.json",
            "invalid_source_fingerprint.case.json",
            "invalid_stale_source_event_after_revalidation.case.json",
            "invalid_generic_implementation_before_creation.case.json",
            "invalid_generic_verification_after_final_verification.case.json",
            "invalid_pdf_layout_opt_out.case.json",
            "invalid_diagnostic_authority_opt_out.case.json",
        }
        self.assertTrue(audit_regressions.issubset(case_names))
        for case_path in case_paths:
            with self.subTest(case=case_path.name):
                case = load_json(case_path)
                state = apply_mutations(
                    load_json(FIXTURES / case["state"]), case.get("state_mutations", [])
                )
                baseline = apply_mutations(
                    load_json(FIXTURES / case["baseline"]), case.get("baseline_mutations", [])
                )
                candidate = None
                if case.get("candidate"):
                    candidate = apply_mutations(
                        load_json(FIXTURES / case["candidate"]),
                        case.get("candidate_mutations", []),
                    )
                diff_map = None
                if case.get("diff_map"):
                    diff_map = apply_mutations(
                        load_json(FIXTURES / case["diff_map"]),
                        case.get("diff_map_mutations", []),
                    )

                with tempfile.TemporaryDirectory() as temporary:
                    temporary_path = Path(temporary)
                    state_path = temporary_path / "state.json"
                    baseline_path = temporary_path / "baseline.json"
                    state_path.write_text(json.dumps(state), encoding="utf-8")
                    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
                    candidate_path = None
                    if candidate is not None:
                        candidate_path = temporary_path / "candidate.json"
                        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
                    diff_path = None
                    if diff_map is not None:
                        diff_path = temporary_path / "diff-map.json"
                        diff_path.write_text(json.dumps(diff_map), encoding="utf-8")

                    completed = run_validator(
                        state=state_path,
                        baseline=baseline_path,
                        candidate=candidate_path,
                        diff_map=diff_path,
                        check=case["check"],
                    )

                self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["result"], "FAIL")
                self.assertGreater(payload["error_count"], 0)
                actual_ids = {issue["check_id"] for issue in payload["issues"]}
                self.assertTrue(
                    set(case["expected_check_ids"]).issubset(actual_ids),
                    f"expected {case['expected_check_ids']}; got {sorted(actual_ids)}",
                )
                if "STATE.SCHEMA" not in case["expected_check_ids"]:
                    self.assertNotIn(
                        "STATE.SCHEMA",
                        actual_ids,
                        "semantic regression fixture should remain structurally schema-valid",
                    )
                for issue in payload["issues"]:
                    self.assertEqual(
                        set(issue),
                        {
                            "check_id",
                            "severity",
                            "affected_decision",
                            "affected_artifact",
                            "explanation",
                        },
                    )
                    self.assertIn(issue["severity"], {"ERROR", "WARNING"})
                    self.assertTrue(issue["explanation"])

    def test_unreadable_input_is_machine_readable_and_uses_exit_two(self) -> None:
        completed = run_validator(
            state=FIXTURES / "does-not-exist.json",
            baseline=FIXTURES / "diagnostic_baseline.json",
            check="diagnostic",
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["result"], "FAIL")
        self.assertEqual(payload["issues"][0]["check_id"], "INPUT.FILE")

    def test_invalid_utf8_is_machine_readable_and_uses_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bad_state = Path(temporary) / "state.json"
            bad_state.write_bytes(b"\xff\xfe\x00")
            completed = run_validator(
                state=bad_state,
                baseline=FIXTURES / "diagnostic_baseline.json",
                check="diagnostic",
            )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["issues"][0]["check_id"], "INPUT.JSON")
        self.assertNotIn("Traceback", completed.stderr)

    def test_nonstandard_or_ambiguous_json_is_rejected_as_input(self) -> None:
        bad_documents = (
            '{"schema_version":"2.0.0","schema_version":"2.0.0"}',
            '{"schema_version":NaN}',
        )
        for document in bad_documents:
            with self.subTest(document=document):
                with tempfile.TemporaryDirectory() as temporary:
                    bad_state = Path(temporary) / "state.json"
                    bad_state.write_text(document, encoding="utf-8")
                    completed = run_validator(
                        state=bad_state,
                        baseline=FIXTURES / "diagnostic_baseline.json",
                        check="diagnostic",
                    )
                self.assertEqual(completed.returncode, 2)
                payload = json.loads(completed.stdout)
                self.assertEqual(payload["issues"][0]["check_id"], "INPUT.JSON")
                self.assertNotIn("Traceback", completed.stderr)

    def test_escaped_unpaired_surrogate_is_machine_readable_input_error(self) -> None:
        state = load_json(FIXTURES / "valid_diagnostic_state.json")
        state["decisions"][0]["protected_intent"] = "\ud800"
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            completed = run_validator(
                state=state_path,
                baseline=FIXTURES / "diagnostic_baseline.json",
                check="diagnostic",
            )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["issues"][0]["check_id"], "INPUT.JSON")
        self.assertNotIn("Traceback", completed.stderr)

    def test_huge_revision_number_fails_without_range_materialization(self) -> None:
        state = load_json(FIXTURES / "valid_diagnostic_state.json")
        huge_revision = 10**100
        state["decisions"][0]["proposal_revision"] = huge_revision
        state["events"][0]["proposal_revision"] = huge_revision
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            completed = run_validator(
                state=state_path,
                baseline=FIXTURES / "diagnostic_baseline.json",
                check="diagnostic",
            )
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertIn(
            "STATE.REVISION_ORDER",
            {issue["check_id"] for issue in payload["issues"]},
        )
        self.assertNotIn("Traceback", completed.stderr)

    def test_invalid_invocation_is_machine_readable_and_uses_exit_two(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["check"], "invocation")
        self.assertEqual(payload["issues"][0]["check_id"], "INPUT.ARGUMENT")
        self.assertNotIn("usage:", completed.stderr.lower())

    def test_release_requires_candidate_and_diff_sidecars(self) -> None:
        completed = run_validator(
            state=FIXTURES / "valid_ready_to_release.json",
            baseline=FIXTURES / "release_baseline.json",
            check="ready-to-release",
        )
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        ids = {issue["check_id"] for issue in payload["issues"]}
        self.assertIn("STATE.RELEASE_SIDECAR", ids)


if __name__ == "__main__":
    unittest.main()
