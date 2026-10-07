#!/usr/bin/env python3
"""Assemble and verify UTF-8 text from a baseline and approved replacements."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


class ParagraphLockError(ValueError):
    """Raised when ParagraphLock inputs violate the verification contract."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require_utf8(data: bytes, label: str) -> None:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParagraphLockError(f"{label} is not valid UTF-8: {exc}") from exc


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ParagraphLockError(f"cannot read change manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise ParagraphLockError("change manifest must contain a JSON object")
    if payload.get("schema_version") != 1:
        raise ParagraphLockError("change manifest schema_version must be 1")
    digest = payload.get("baseline_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ParagraphLockError("baseline_sha256 must be a 64-character SHA-256 digest")
    replacements = payload.get("replacements")
    if not isinstance(replacements, list):
        raise ParagraphLockError("replacements must be a JSON array")
    return payload


def _approved_replacements(
    baseline: bytes, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    require_utf8(baseline, "baseline")
    expected_digest = payload["baseline_sha256"].lower()
    actual_digest = sha256_bytes(baseline)
    if actual_digest != expected_digest:
        raise ParagraphLockError(
            f"baseline SHA-256 mismatch: expected {expected_digest}, got {actual_digest}"
        )

    approved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(payload["replacements"]):
        if not isinstance(item, dict):
            raise ParagraphLockError(f"replacement {index} must be a JSON object")
        change_id = item.get("id")
        if not isinstance(change_id, str) or not change_id.strip():
            raise ParagraphLockError(f"replacement {index} has no non-empty id")
        if change_id in seen_ids:
            raise ParagraphLockError(f"duplicate replacement id: {change_id}")
        seen_ids.add(change_id)
        if not isinstance(item.get("approved"), bool):
            raise ParagraphLockError(f"replacement {change_id} approved must be boolean")
        if not item["approved"]:
            continue

        start = item.get("start_byte")
        end = item.get("end_byte")
        before = item.get("before")
        after = item.get("after")
        if not isinstance(start, int) or isinstance(start, bool):
            raise ParagraphLockError(f"replacement {change_id} start_byte must be an integer")
        if not isinstance(end, int) or isinstance(end, bool):
            raise ParagraphLockError(f"replacement {change_id} end_byte must be an integer")
        if start < 0 or end < start or end > len(baseline):
            raise ParagraphLockError(f"replacement {change_id} has an invalid byte range")
        if not isinstance(before, str) or not isinstance(after, str):
            raise ParagraphLockError(
                f"replacement {change_id} before and after must be strings"
            )
        before_bytes = before.encode("utf-8")
        if baseline[start:end] != before_bytes:
            raise ParagraphLockError(
                f"replacement {change_id} before-text does not match the baseline range"
            )
        approved.append(
            {
                "id": change_id,
                "start_byte": start,
                "end_byte": end,
                "after_bytes": after.encode("utf-8"),
            }
        )

    approved.sort(key=lambda item: (item["start_byte"], item["end_byte"]))
    previous: dict[str, Any] | None = None
    for item in approved:
        if previous is not None and (
            item["start_byte"] < previous["end_byte"]
            or item["start_byte"] == previous["start_byte"]
        ):
            raise ParagraphLockError(
                f"approved replacements overlap: {previous['id']} and {item['id']}"
            )
        previous = item
    return approved


def assemble_bytes(baseline: bytes, payload: dict[str, Any]) -> tuple[bytes, list[str]]:
    approved = _approved_replacements(baseline, payload)
    output = bytearray()
    cursor = 0
    applied_ids: list[str] = []
    for item in approved:
        output.extend(baseline[cursor : item["start_byte"]])
        output.extend(item["after_bytes"])
        cursor = item["end_byte"]
        applied_ids.append(item["id"])
    output.extend(baseline[cursor:])
    return bytes(output), applied_ids


def first_difference(expected: bytes, actual: bytes) -> int | None:
    for index, (expected_byte, actual_byte) in enumerate(zip(expected, actual)):
        if expected_byte != actual_byte:
            return index
    if len(expected) != len(actual):
        return min(len(expected), len(actual))
    return None


def print_pass(applied_ids: list[str], result: bytes) -> None:
    print("ParagraphLock check: PASS")
    print(f"Approved changes: {len(applied_ids)}")
    print("Unapproved text changes: 0")
    print(f"Result SHA256: {sha256_bytes(result)}")


def run_self_test() -> None:
    baseline = "Alpha paragraph.\n\nA caf\u00e9 paragraph.\n\nOmega paragraph.\n".encode(
        "utf-8"
    )
    before = "A caf\u00e9 paragraph."
    start = baseline.index(before.encode("utf-8"))
    payload = {
        "schema_version": 1,
        "baseline_sha256": sha256_bytes(baseline),
        "replacements": [
            {
                "id": "P2-r1",
                "start_byte": start,
                "end_byte": start + len(before.encode("utf-8")),
                "before": before,
                "after": "An approved caf\u00e9 paragraph.",
                "approved": True,
            }
        ],
    }
    assembled, applied = assemble_bytes(baseline, payload)
    if applied != ["P2-r1"]:
        raise ParagraphLockError("self-test applied-ID mismatch")
    if not assembled.startswith(b"Alpha paragraph.\n\n"):
        raise ParagraphLockError("self-test changed locked prefix")
    if not assembled.endswith(b"\n\nOmega paragraph.\n"):
        raise ParagraphLockError("self-test changed locked suffix")
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / "candidate.txt"
        candidate.write_bytes(assembled)
        if candidate.read_bytes() != assembled:
            raise ParagraphLockError("self-test candidate mismatch")
    print_pass(applied, assembled)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assemble or verify ParagraphLock UTF-8 text."
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run a synthetic internal check."
    )
    subparsers = parser.add_subparsers(dest="command")

    fingerprint = subparsers.add_parser("fingerprint", help="Print baseline SHA-256.")
    fingerprint.add_argument("--baseline", type=Path, required=True)

    assemble = subparsers.add_parser(
        "assemble", help="Write baseline plus approved replacements."
    )
    assemble.add_argument("--baseline", type=Path, required=True)
    assemble.add_argument("--changes", type=Path, required=True)
    assemble.add_argument("--output", type=Path, required=True)
    assemble.add_argument("--force", action="store_true")

    verify = subparsers.add_parser(
        "verify", help="Verify a candidate against the approved assembly."
    )
    verify.add_argument("--baseline", type=Path, required=True)
    verify.add_argument("--changes", type=Path, required=True)
    verify.add_argument("--candidate", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            if args.command is not None:
                raise ParagraphLockError("--self-test cannot be combined with a command")
            run_self_test()
            return 0
        if args.command is None:
            parser.error("choose a command or use --self-test")

        baseline = args.baseline.read_bytes()
        require_utf8(baseline, "baseline")
        if args.command == "fingerprint":
            print(sha256_bytes(baseline))
            return 0

        payload = load_manifest(args.changes)
        expected, applied_ids = assemble_bytes(baseline, payload)
        if args.command == "assemble":
            if args.output.exists() and not args.force:
                raise ParagraphLockError(
                    f"output already exists: {args.output}; pass --force to replace it"
                )
            args.output.write_bytes(expected)
            print_pass(applied_ids, expected)
            return 0

        candidate = args.candidate.read_bytes()
        require_utf8(candidate, "candidate")
        difference = first_difference(expected, candidate)
        if difference is not None:
            raise ParagraphLockError(
                f"candidate contains an unapproved difference at byte {difference}"
            )
        print_pass(applied_ids, candidate)
        return 0
    except (OSError, UnicodeError, ParagraphLockError) as exc:
        print(f"ParagraphLock check: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
