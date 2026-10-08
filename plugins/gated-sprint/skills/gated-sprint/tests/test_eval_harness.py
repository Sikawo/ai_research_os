"""Regression tests for the GatedSprint v2 behavioral-eval harness."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
V2_ROOT = TEST_DIR.parent
HARNESS = V2_ROOT / "scripts" / "run_gatedsprint_evals.py"
CATALOG = V2_ROOT / "evals" / "cases.json"
SCHEMA = V2_ROOT / "schemas" / "eval-case.schema.json"
SKILL_VERSION = "2.0.0-test"
SKILL_SHA256 = "7" * 64
RUNNER_ID = "trusted-test-runner"
RUNNER_PROVENANCE = "isolated-subprocess-fixture"
ISSUED_AT = "2026-10-01T14:00:00Z"
CAPTURED_AT = "2026-10-01T14:01:00Z"
EXPIRES_AT = "2026-10-01T14:05:00Z"
POSIX_LOCAL_PATH = "/" + "Users" + "/example/private/output.docx"
WORKSPACE_LOCAL_PATH = "/" + "workspace" + "/private/output.docx"
WINDOWS_LOCAL_PATH = "C:" + "\\Users\\example\\output.docx"
UNC_LOCAL_PATH = "\\\\" + "server\\share\\output.docx"
FILE_LOCAL_URL = "file:" + "//" + POSIX_LOCAL_PATH
HOME_LOCAL_PATH = "~" + "/private/output.docx"
VALID_PATCH_POINTER = "/" + "Users" + "/example/value"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_harness(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HARNESS), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def trust_arguments(key_path: Path) -> list[str]:
    return [
        "--receipt-key-file",
        str(key_path),
        "--current-skill-version",
        SKILL_VERSION,
        "--current-skill-sha256",
        SKILL_SHA256,
        "--trusted-runner-id",
        RUNNER_ID,
        "--trusted-runner-provenance",
        RUNNER_PROVENANCE,
    ]


def contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(contains_key(item, key) for item in value)
    return False


class GatedSprintEvalHarnessTests(unittest.TestCase):
    maxDiff = None

    def create_packet_and_capture(
        self, root: Path, *, case_id: str = "E-08"
    ) -> tuple[Path, Path, Path]:
        key_path = root / "receipt.key"
        key_path.write_bytes(b"deterministic-test-receipt-key!!")
        packet_path = root / "packet.json"
        capture_path = root / "capture.json"
        prepared = run_harness(
            "prepare",
            "--case",
            case_id,
            "--run-id",
            f"RUN-{case_id}-TEST",
            "--issued-at",
            ISSUED_AT,
            "--expires-at",
            EXPIRES_AT,
            *trust_arguments(key_path),
            "--output",
            str(packet_path),
        )
        self.assertEqual(prepared.returncode, 0, prepared.stderr + prepared.stdout)
        created = run_harness(
            "new-capture",
            "--packet",
            str(packet_path),
            *trust_arguments(key_path),
            "--output",
            str(capture_path),
        )
        self.assertEqual(created.returncode, 0, created.stderr + created.stdout)
        return key_path, packet_path, capture_path

    def create_record(self, root: Path) -> tuple[Path, Path, dict[str, Any]]:
        key_path, packet_path, capture_path = self.create_packet_and_capture(root)
        sealed_path = root / "sealed-capture.json"
        records_dir = root / "records"
        records_dir.mkdir()
        record_path = records_dir / "E-08.json"
        sealed = run_harness(
            "seal-capture",
            "--packet",
            str(packet_path),
            "--capture",
            str(capture_path),
            "--captured-at",
            CAPTURED_AT,
            *trust_arguments(key_path),
            "--output",
            str(sealed_path),
        )
        self.assertEqual(sealed.returncode, 0, sealed.stderr + sealed.stdout)
        recorded = run_harness(
            "record",
            "--capture",
            str(sealed_path),
            *trust_arguments(key_path),
            "--output",
            str(record_path),
        )
        # The blank capture is deliberately incomplete, so grading fails while
        # still producing a fully bound immutable record envelope.
        self.assertEqual(recorded.returncode, 2, recorded.stderr + recorded.stdout)
        self.assertTrue(record_path.is_file())
        return sealed_path, record_path, load_json(record_path)

    def test_prepare_packet_strips_prelude_grading_expectations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, packet_path, _ = self.create_packet_and_capture(root)
            packet = load_json(packet_path)
        self.assertFalse(contains_key(packet, "expected_resulting_state"))
        for event in packet["prelude"]:
            self.assertEqual(
                set(event),
                {"order", "actor", "message", "artifact_changes", "state_changes"},
            )

    def test_record_uses_portable_current_content_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, record_path, record = self.create_record(Path(temporary))
            catalog = load_json(CATALOG)
            case = next(item for item in catalog["cases"] if item["case_id"] == "E-08")
            self.assertEqual(record["record_version"], "1.0.0")
            self.assertEqual(record["catalog_file"], CATALOG.name)
            self.assertNotIn("catalog_path", record)
            self.assertEqual(record["catalog_sha256"], sha256_file(CATALOG))
            self.assertEqual(record["schema_sha256"], sha256_file(SCHEMA))
            self.assertEqual(
                record["fixture_hashes"],
                {artifact["artifact_id"]: artifact["sha256"] for artifact in case["artifacts"]},
            )
            serialized = record_path.read_text(encoding="utf-8")
            self.assertNotIn(str(CATALOG.resolve()), serialized)
            self.assertNotIn(str(CATALOG.parent.resolve()), serialized)

            suite = run_harness(
                "suite",
                "--records-dir",
                str(record_path.parent),
                *trust_arguments(Path(temporary) / "receipt.key"),
            )
            self.assertEqual(suite.returncode, 2, suite.stderr + suite.stdout)
            suite_report = json.loads(suite.stdout)
            self.assertEqual(suite_report["load_errors"], [])
            self.assertEqual(suite_report["record_count"], 1)

    def test_suite_rejects_raw_capture_instead_of_grading_it_as_a_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records_dir = Path(temporary) / "records"
            records_dir.mkdir()
            capture_path = records_dir / "raw-capture.json"
            key_path, _, created_capture = self.create_packet_and_capture(Path(temporary))
            capture_path.write_bytes(created_capture.read_bytes())
            suite = run_harness(
                "suite",
                "--records-dir",
                str(records_dir),
                *trust_arguments(key_path),
            )
            self.assertEqual(suite.returncode, 2, suite.stderr + suite.stdout)
            report = json.loads(suite.stdout)
            self.assertEqual(report["record_count"], 0)
            self.assertTrue(report["load_errors"])
            self.assertIn("versioned record envelopes", report["load_errors"][0])

    def test_grade_verifies_record_envelope_before_unwrapping_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, record_path, record = self.create_record(Path(temporary))
            key_path = Path(temporary) / "receipt.key"
            valid_grade = run_harness(
                "grade", "--capture", str(record_path), *trust_arguments(key_path)
            )
            self.assertEqual(valid_grade.returncode, 2, valid_grade.stderr + valid_grade.stdout)

            record["catalog_sha256"] = "0" * 64
            record_path.write_text(json.dumps(record), encoding="utf-8")
            tampered_grade = run_harness(
                "grade", "--capture", str(record_path), *trust_arguments(key_path)
            )
            self.assertEqual(
                tampered_grade.returncode,
                1,
                tampered_grade.stderr + tampered_grade.stdout,
            )
            self.assertIn("catalog_sha256", tampered_grade.stderr)

    def test_record_and_suite_reject_machine_local_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture_path, record_path, record = self.create_record(root)
            absolute_output = str(Path("/") / "var" / "example" / "private" / "output.docx")

            capture = load_json(capture_path)
            capture["tool_actions"].append(
                {
                    "action": "READ_FILE",
                    "op": "read",
                    "path": absolute_output,
                }
            )
            capture_path.write_text(json.dumps(capture), encoding="utf-8")
            rejected_record = root / "rejected-record.json"
            recorded = run_harness(
                "record",
                "--capture",
                str(capture_path),
                *trust_arguments(root / "receipt.key"),
                "--output",
                str(rejected_record),
            )
            self.assertEqual(recorded.returncode, 1, recorded.stderr + recorded.stdout)
            self.assertIn("absolute paths", recorded.stderr)
            self.assertFalse(rejected_record.exists())

            capture["tool_actions"] = [
                {"action": "READ_FILE", "cwd": "~synthetic/private/input.docx"}
            ]
            capture_path.write_text(json.dumps(capture), encoding="utf-8")
            rejected_tilde_record = root / "rejected-tilde-record.json"
            recorded = run_harness(
                "record",
                "--capture",
                str(capture_path),
                *trust_arguments(root / "receipt.key"),
                "--output",
                str(rejected_tilde_record),
            )
            self.assertEqual(recorded.returncode, 1, recorded.stderr + recorded.stdout)
            self.assertIn("absolute paths", recorded.stderr)
            self.assertFalse(rejected_tilde_record.exists())

            record["capture"]["tool_actions"].append(
                {"action": "READ_FILE", "source_uri": f"file:{absolute_output}"}
            )
            record_path.write_text(json.dumps(record), encoding="utf-8")
            suite = run_harness(
                "suite",
                "--records-dir",
                str(record_path.parent),
                *trust_arguments(root / "receipt.key"),
            )
            self.assertEqual(suite.returncode, 2, suite.stderr + suite.stdout)
            report = json.loads(suite.stdout)
            self.assertEqual(report["record_count"], 0)
            self.assertTrue(report["load_errors"])
            self.assertIn("absolute paths or file URLs", report["load_errors"][0])

    def test_suite_requires_closed_record_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, record_path, record = self.create_record(Path(temporary))
            record["catalog_path"] = str(
                Path("/") / "var" / "example" / "private" / "cases.json"
            )
            del record["recorded_at"]
            record_path.write_text(json.dumps(record), encoding="utf-8")
            suite = run_harness(
                "suite",
                "--records-dir",
                str(record_path.parent),
                *trust_arguments(Path(temporary) / "receipt.key"),
            )
            self.assertEqual(suite.returncode, 2, suite.stderr + suite.stdout)
            report = json.loads(suite.stdout)
            self.assertEqual(report["record_count"], 0)
            self.assertTrue(report["load_errors"])
            self.assertIn("missing fields ['recorded_at']", report["load_errors"][0])
            self.assertIn("unexpected fields ['catalog_path']", report["load_errors"][0])

    def test_suite_rejects_stale_catalog_schema_and_fixture_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, record = self.create_record(root)
            corruptions = {
                "catalog_sha256": "0" * 64,
                "schema_sha256": "1" * 64,
                "fixture_hashes": {},
            }
            for index, (field, invalid_value) in enumerate(corruptions.items(), start=1):
                with self.subTest(field=field):
                    records_dir = root / f"tampered-{index}"
                    records_dir.mkdir()
                    tampered = json.loads(json.dumps(record))
                    tampered[field] = invalid_value
                    (records_dir / "E-08.json").write_text(
                        json.dumps(tampered), encoding="utf-8"
                    )
                    suite = run_harness(
                        "suite",
                        "--records-dir",
                        str(records_dir),
                        *trust_arguments(root / "receipt.key"),
                    )
                    self.assertEqual(suite.returncode, 2, suite.stderr + suite.stdout)
                    report = json.loads(suite.stdout)
                    self.assertEqual(report["record_count"], 0)
                    self.assertTrue(report["load_errors"])
                    self.assertIn(field, report["load_errors"][0])

    def test_unsealed_tampered_or_stale_capture_cannot_be_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key_path, packet_path, raw_path = self.create_packet_and_capture(root)
            rejected = root / "unsealed-record.json"
            unsealed = run_harness(
                "record",
                "--capture",
                str(raw_path),
                *trust_arguments(key_path),
                "--output",
                str(rejected),
            )
            self.assertEqual(unsealed.returncode, 1, unsealed.stderr + unsealed.stdout)
            self.assertIn("trusted execution receipt", unsealed.stderr)
            self.assertFalse(rejected.exists())

            sealed_path = root / "sealed.json"
            sealed = run_harness(
                "seal-capture",
                "--packet",
                str(packet_path),
                "--capture",
                str(raw_path),
                "--captured-at",
                CAPTURED_AT,
                *trust_arguments(key_path),
                "--output",
                str(sealed_path),
            )
            self.assertEqual(sealed.returncode, 0, sealed.stderr + sealed.stdout)
            tampered = load_json(sealed_path)
            tampered["final_response"] = "post-seal mutation"
            sealed_path.write_text(json.dumps(tampered), encoding="utf-8")
            tampered_result = run_harness(
                "record",
                "--capture",
                str(sealed_path),
                *trust_arguments(key_path),
                "--output",
                str(root / "tampered-record.json"),
            )
            self.assertEqual(
                tampered_result.returncode,
                1,
                tampered_result.stderr + tampered_result.stdout,
            )
            self.assertIn("captured payload bytes", tampered_result.stderr)

            stale_args = trust_arguments(key_path)
            stale_args[stale_args.index(SKILL_VERSION)] = "2.0.1-test"
            stale_result = run_harness(
                "grade", "--capture", str(sealed_path), *stale_args
            )
            self.assertEqual(stale_result.returncode, 2, stale_result.stderr + stale_result.stdout)
            report = json.loads(stale_result.stdout)
            self.assertFalse(report["execution_receipt_verified"])
            self.assertIn(
                "EXECUTION_SKILL_BINDING",
                {item["check_id"] for item in report["structural_issues"]},
            )

    def test_capture_time_must_fall_in_signed_execution_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key_path, packet_path, raw_path = self.create_packet_and_capture(root)
            completed = run_harness(
                "seal-capture",
                "--packet",
                str(packet_path),
                "--capture",
                str(raw_path),
                "--captured-at",
                "2026-10-01T15:00:00Z",
                *trust_arguments(key_path),
                "--output",
                str(root / "stale.json"),
            )
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            self.assertIn("signed issuance window", completed.stderr)

    def test_embedded_local_path_tokens_are_rejected_but_valid_pointers_are_allowed(self) -> None:
        local_tokens = (
            f"Saved to {POSIX_LOCAL_PATH}",
            f"Saved to {WORKSPACE_LOCAL_PATH}",
            f"Saved to {WINDOWS_LOCAL_PATH}",
            f"Saved to {UNC_LOCAL_PATH}",
            f"Saved to {FILE_LOCAL_URL}",
            f"Saved to {HOME_LOCAL_PATH}",
        )
        for index, token in enumerate(local_tokens):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                key_path, packet_path, raw_path = self.create_packet_and_capture(root)
                capture = load_json(raw_path)
                capture["final_response"] = token
                raw_path.write_text(json.dumps(capture), encoding="utf-8")
                sealed_path = root / "sealed.json"
                sealed = run_harness(
                    "seal-capture",
                    "--packet",
                    str(packet_path),
                    "--capture",
                    str(raw_path),
                    "--captured-at",
                    CAPTURED_AT,
                    *trust_arguments(key_path),
                    "--output",
                    str(sealed_path),
                )
                self.assertEqual(sealed.returncode, 0, sealed.stderr + sealed.stdout)
                recorded = run_harness(
                    "record",
                    "--capture",
                    str(sealed_path),
                    *trust_arguments(key_path),
                    "--output",
                    str(root / f"record-{index}.json"),
                )
                self.assertEqual(recorded.returncode, 1, recorded.stderr + recorded.stdout)
                self.assertIn("absolute paths or file URLs", recorded.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key_path, packet_path, raw_path = self.create_packet_and_capture(root)
            capture = load_json(raw_path)
            capture["state_sidecar"] = {
                "state_mutations": [
                    {"op": "replace", "path": VALID_PATCH_POINTER, "value": "safe"}
                ],
            }
            raw_path.write_text(json.dumps(capture), encoding="utf-8")
            sealed_path = root / "pointer-capture.json"
            sealed = run_harness(
                "seal-capture",
                "--packet",
                str(packet_path),
                "--capture",
                str(raw_path),
                "--captured-at",
                CAPTURED_AT,
                *trust_arguments(key_path),
                "--output",
                str(sealed_path),
            )
            self.assertEqual(sealed.returncode, 0, sealed.stderr + sealed.stdout)
            recorded = run_harness(
                "record",
                "--capture",
                str(sealed_path),
                *trust_arguments(key_path),
                "--output",
                str(root / "pointer-record.json"),
            )
            self.assertEqual(recorded.returncode, 2, recorded.stderr + recorded.stdout)
            self.assertNotIn("absolute paths", recorded.stderr)

            capture = load_json(raw_path)
            capture["state_sidecar"] = {
                "selector": POSIX_LOCAL_PATH
            }
            raw_path.write_text(json.dumps(capture), encoding="utf-8")
            bad_sealed = root / "bad-pointer-capture.json"
            resealed = run_harness(
                "seal-capture",
                "--packet",
                str(packet_path),
                "--capture",
                str(raw_path),
                "--captured-at",
                CAPTURED_AT,
                *trust_arguments(key_path),
                "--output",
                str(bad_sealed),
            )
            self.assertEqual(resealed.returncode, 0, resealed.stderr + resealed.stdout)
            rejected = run_harness(
                "record",
                "--capture",
                str(bad_sealed),
                *trust_arguments(key_path),
                "--output",
                str(root / "bad-pointer-record.json"),
            )
            self.assertEqual(rejected.returncode, 1, rejected.stderr + rejected.stdout)
            self.assertIn("absolute paths", rejected.stderr)

            capture = load_json(raw_path)
            capture["state_sidecar"] = {
                "state_mutations": [
                    {"op": "read", "path": POSIX_LOCAL_PATH}
                ]
            }
            raw_path.write_text(json.dumps(capture), encoding="utf-8")
            invalid_patch_sealed = root / "invalid-patch-capture.json"
            resealed = run_harness(
                "seal-capture",
                "--packet",
                str(packet_path),
                "--capture",
                str(raw_path),
                "--captured-at",
                CAPTURED_AT,
                *trust_arguments(key_path),
                "--output",
                str(invalid_patch_sealed),
            )
            self.assertEqual(resealed.returncode, 0, resealed.stderr + resealed.stdout)
            invalid_patch = run_harness(
                "record",
                "--capture",
                str(invalid_patch_sealed),
                *trust_arguments(key_path),
                "--output",
                str(root / "invalid-patch-record.json"),
            )
            self.assertEqual(invalid_patch.returncode, 1, invalid_patch.stderr + invalid_patch.stdout)
            self.assertIn("absolute paths", invalid_patch.stderr)

    def test_duplicate_keys_and_nonfinite_numbers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key_path = root / "receipt.key"
            key_path.write_bytes(b"deterministic-test-receipt-key!!")
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"case_id":"E-08","case_id":"E-08"}', encoding="utf-8")
            duplicate_result = run_harness(
                "grade", "--capture", str(duplicate), *trust_arguments(key_path)
            )
            self.assertEqual(duplicate_result.returncode, 1)
            self.assertIn("duplicate JSON object key", duplicate_result.stderr)

            nonfinite = root / "nonfinite.json"
            nonfinite.write_text('{"case_id":"E-08","score":NaN}', encoding="utf-8")
            nonfinite_result = run_harness(
                "grade", "--capture", str(nonfinite), *trust_arguments(key_path)
            )
            self.assertEqual(nonfinite_result.returncode, 1)
            self.assertIn("non-finite JSON number", nonfinite_result.stderr)

    def test_required_behavior_evidence_target_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, record_path, record = self.create_record(root)
            issue_ids = {item["check_id"] for item in record["report"]["structural_issues"]}
            self.assertIn("CAPTURE_REQUIRED_EVIDENCE_TARGET", issue_ids)
            self.assertEqual(record["report"]["overall_result"], "FAIL")
            self.assertTrue(record_path.exists())

    def test_e30_uses_promotion_validation_not_release_verified_terminology(self) -> None:
        catalog = load_json(CATALOG)
        case = next(item for item in catalog["cases"] if item["case_id"] == "E-30")
        serialized = json.dumps(case, sort_keys=True)
        self.assertIn("VALIDATE_CANDIDATE_FOR_PROMOTION", serialized)
        self.assertIn("PROMOTE_VALIDATED_CANDIDATE", serialized)
        self.assertNotIn("VERIFY_CANDIDATE", serialized)
        self.assertNotIn("PROMOTE_VERIFIED_CANDIDATE", serialized)


if __name__ == "__main__":
    unittest.main()
