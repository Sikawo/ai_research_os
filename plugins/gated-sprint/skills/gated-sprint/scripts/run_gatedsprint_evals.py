#!/usr/bin/env python3
"""Validate, package, record, and grade GatedSprint v2 behavioral evals.

This harness deliberately does not call a model.  ``prepare`` emits a clean,
expectation-free execution packet.  A separate runner captures the model turn,
tool actions, state sidecars, and artifacts.  ``grade`` then applies mechanical
checks and verifies that an independent qualitative grader supplied cited
evidence.  It never treats a missing model run or grader judgment as a pass.

Only the Python standard library is used so the catalog remains portable.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = SKILL_ROOT / "evals" / "cases.json"
DEFAULT_SCHEMA = SKILL_ROOT / "schemas" / "eval-case.schema.json"
EXPECTED_CASE_IDS = [f"E-{number:02d}" for number in range(1, 34)]
REQUIRED_ONE_SHOT = {
    "E-01",
    "E-02",
    "E-04",
    "E-06",
    "E-08",
    "E-13",
    "E-15",
    "E-18",
    "E-24",
    "E-26",
    "E-27",
    "E-28",
    "E-29",
    "E-30",
    "E-31",
    "E-32",
    "E-33",
}
RESULT_RANK = {"FAIL": 0, "PARTIAL": 1, "PASS": 2}
FILE_URI_RE = re.compile(r"(?<![A-Za-z0-9+.-])file:(?:/{1,3}|[A-Za-z]:[\\/]|\\\\)", re.IGNORECASE)
EMBEDDED_POSIX_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._/-])/(?:[A-Za-z0-9._~+@%:,=-]+(?:/[A-Za-z0-9._~+@%:,=-]+)*)"
    r"(?=$|[\s\"'`)<>,;])"
)
EMBEDDED_WINDOWS_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/](?:[^\s\"'`<>|:*?]+[\\/])*[^\s\"'`<>|:*?]*|\\\\[^\s\\/]+[\\/][^\s\"'`<>|:*?]+)"
)
EMBEDDED_TILDE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._-])~(?:[A-Za-z0-9._+-]+)?[\\/](?:[^\s\"'`<>|]+)"
)
JSON_PATCH_OPERATIONS = {"add", "remove", "replace", "move", "copy", "test"}
JSON_PATCH_FIELDS = {"op", "path", "from", "value"}
JSON_PATCH_COLLECTION_KEYS = {
    "patch",
    "patches",
    "mutations",
    "state_mutations",
    "baseline_mutations",
    "candidate_mutations",
    "diff_map_mutations",
}
RECORD_ENVELOPE_FIELDS = frozenset(
    {
        "record_version",
        "recorded_at",
        "catalog_file",
        "catalog_sha256",
        "schema_sha256",
        "fixture_hashes",
        "capture",
        "capture_sha256",
        "report",
        "report_sha256",
    }
)
RECORD_MARKER_FIELDS = frozenset(
    {"record_version", "catalog_sha256", "schema_sha256", "capture_sha256", "report_sha256"}
)
RECEIPT_VERSION = "1.0.0"
EXECUTION_RECEIPT_FIELD = "execution_receipt"
ISSUANCE_FIELDS = frozenset(
    {
        "receipt_version",
        "case_id",
        "run_id",
        "packet_payload_sha256",
        "issued_at",
        "expires_at",
        "trusted_runner",
        "skill",
        "signature",
    }
)
EXECUTION_RECEIPT_FIELDS = frozenset(
    {
        "receipt_version",
        "case_id",
        "run_id",
        "prepared_packet_sha256",
        "capture_payload_sha256",
        "captured_at",
        "execution_issuance",
        "signature",
    }
)


@dataclass(frozen=True)
class Issue:
    check_id: str
    severity: str
    path: str
    explanation: str


@dataclass(frozen=True)
class TrustPolicy:
    key: bytes
    skill_version: str
    skill_sha256: str
    runner_id: str
    runner_provenance: str


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def is_aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def parsed_timestamp(value: Any) -> Optional[dt.datetime]:
    if not is_aware_timestamp(value):
        return None
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def read_receipt_key(path: Path) -> bytes:
    try:
        key = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"receipt key file does not exist: {path}") from exc
    if len(key) < 32:
        raise ValueError("receipt HMAC key must contain at least 32 bytes")
    return key


def trust_policy_from_args(args: argparse.Namespace) -> TrustPolicy:
    skill_sha256 = args.current_skill_sha256
    if re.fullmatch(r"[0-9a-f]{64}", skill_sha256 or "") is None:
        raise ValueError("--current-skill-sha256 must be a lowercase SHA-256")
    for field_name, value in (
        ("--current-skill-version", args.current_skill_version),
        ("--trusted-runner-id", args.trusted_runner_id),
        ("--trusted-runner-provenance", args.trusted_runner_provenance),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be non-empty")
    return TrustPolicy(
        key=read_receipt_key(Path(args.receipt_key_file).resolve()),
        skill_version=args.current_skill_version,
        skill_sha256=skill_sha256,
        runner_id=args.trusted_runner_id,
        runner_provenance=args.trusted_runner_provenance,
    )


def hmac_signature(payload: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(key, canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def signed_payload(payload: Mapping[str, Any], key: bytes) -> Dict[str, Any]:
    result = copy.deepcopy(dict(payload))
    result["signature"] = hmac_signature(payload, key)
    return result


def signature_valid(value: Mapping[str, Any], key: bytes) -> bool:
    signature = value.get("signature")
    if not isinstance(signature, str) or re.fullmatch(r"[0-9a-f]{64}", signature) is None:
        return False
    unsigned = {field: copy.deepcopy(item) for field, item in value.items() if field != "signature"}
    return hmac.compare_digest(signature, hmac_signature(unsigned, key))


def contains_local_path_token(value: str) -> bool:
    """Return whether arbitrary text exposes a machine-local path token."""

    return any(
        expression.search(value) is not None
        for expression in (
            FILE_URI_RE,
            EMBEDDED_POSIX_LOCAL_PATH_RE,
            EMBEDDED_WINDOWS_PATH_RE,
            EMBEDDED_TILDE_PATH_RE,
        )
    )


def is_valid_json_pointer(value: Any) -> bool:
    """Accept only RFC 6901 JSON pointers (not filesystem-looking pseudo-pointers)."""

    if not isinstance(value, str):
        return False
    if value == "":
        return True
    if not value.startswith("/"):
        return False
    index = 0
    while index < len(value):
        if value[index] == "~":
            if index + 1 >= len(value) or value[index + 1] not in {"0", "1"}:
                return False
            index += 2
            continue
        index += 1
    return True


def is_valid_json_patch_object(value: Mapping[str, Any]) -> bool:
    """Recognize a closed RFC-6902 operation before granting pointer exemptions."""

    operation = value.get("op")
    keys = set(value)
    if operation not in JSON_PATCH_OPERATIONS or not keys.issubset(JSON_PATCH_FIELDS):
        return False
    if not is_valid_json_pointer(value.get("path")):
        return False
    if operation in {"move", "copy"}:
        return keys == {"op", "path", "from"} and is_valid_json_pointer(value.get("from"))
    if operation in {"add", "replace", "test"}:
        return keys == {"op", "path", "value"}
    return operation == "remove" and keys == {"op", "path"}


def local_absolute_path_locations(
    value: Any,
    *,
    location: str = "$",
    json_pointer_context: bool = False,
    json_patch_collection_context: bool = False,
) -> List[str]:
    """Find machine-local paths, exempting only validated RFC-6902 pointers."""

    locations: List[str] = []
    if isinstance(value, dict):
        json_patch_object = json_patch_collection_context and is_valid_json_patch_object(value)
        for key, item in value.items():
            normalized_key = str(key).lower()
            child_json_pointer_context = (
                json_patch_object and normalized_key in {"path", "from"}
            )
            child_json_patch_collection_context = (
                normalized_key in JSON_PATCH_COLLECTION_KEYS
            )
            locations.extend(
                local_absolute_path_locations(
                    item,
                    location=f"{location}.{key}",
                    json_pointer_context=child_json_pointer_context,
                    json_patch_collection_context=child_json_patch_collection_context,
                )
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            locations.extend(
                local_absolute_path_locations(
                    item,
                    location=f"{location}[{index}]",
                    json_pointer_context=json_pointer_context,
                    json_patch_collection_context=json_patch_collection_context,
                )
            )
    elif isinstance(value, str) and (
        (json_pointer_context and not is_valid_json_pointer(value))
        or (not json_pointer_context and contains_local_path_token(value))
    ):
        locations.append(location)
    return locations


def reject_duplicate_object_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def reject_nonfinite_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number {value!r} is not permitted")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(
                handle,
                object_pairs_hook=reject_duplicate_object_pairs,
                parse_constant=reject_nonfinite_json_constant,
            )
    except FileNotFoundError as exc:
        raise ValueError(f"file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except ValueError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def write_json_atomic(path: Path, value: Any, *, overwrite: bool = False) -> None:
    path = path.resolve()
    if path.exists() and not overwrite:
        raise ValueError(f"refusing to overwrite existing file without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                value,
                handle,
                indent=2,
                ensure_ascii=False,
                sort_keys=False,
                allow_nan=False,
            )
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def resolve_schema_ref(root_schema: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"only local JSON Schema references are supported: {reference}")
    current: Any = root_schema
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"unresolvable JSON Schema reference: {reference}")
        current = current[token]
    if not isinstance(current, dict):
        raise ValueError(f"JSON Schema reference is not an object: {reference}")
    return current


def validate_against_schema(
    instance: Any,
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    path: str = "$",
) -> List[Issue]:
    """Validate the deliberately small JSON Schema subset used by this catalog."""

    issues: List[Issue] = []
    if "$ref" in schema:
        try:
            target = resolve_schema_ref(root_schema, schema["$ref"])
        except ValueError as exc:
            return [Issue("SCHEMA_REF", "ERROR", path, str(exc))]
        return validate_against_schema(instance, target, root_schema, path)

    if "const" in schema and instance != schema["const"]:
        issues.append(
            Issue("SCHEMA_CONST", "ERROR", path, f"expected constant {schema['const']!r}")
        )
    if "enum" in schema and instance not in schema["enum"]:
        issues.append(
            Issue("SCHEMA_ENUM", "ERROR", path, f"value {instance!r} is not in {schema['enum']!r}")
        )

    declared_type = schema.get("type")
    if declared_type is not None:
        allowed_types = [declared_type] if isinstance(declared_type, str) else declared_type
        if not any(json_type_matches(instance, type_name) for type_name in allowed_types):
            issues.append(
                Issue(
                    "SCHEMA_TYPE",
                    "ERROR",
                    path,
                    f"expected type {declared_type!r}; got {type(instance).__name__}",
                )
            )
            return issues

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                issues.append(
                    Issue("SCHEMA_REQUIRED", "ERROR", path, f"missing required property {key!r}")
                )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    issues.append(
                        Issue(
                            "SCHEMA_ADDITIONAL_PROPERTY",
                            "ERROR",
                            f"{path}.{key}",
                            "property is not allowed",
                        )
                    )
        for key, subschema in properties.items():
            if key in instance:
                issues.extend(
                    validate_against_schema(instance[key], subschema, root_schema, f"{path}.{key}")
                )
        if len(instance) < schema.get("minProperties", 0):
            issues.append(
                Issue(
                    "SCHEMA_MIN_PROPERTIES",
                    "ERROR",
                    path,
                    f"requires at least {schema['minProperties']} properties",
                )
            )

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            issues.append(
                Issue(
                    "SCHEMA_MIN_ITEMS",
                    "ERROR",
                    path,
                    f"requires at least {schema['minItems']} items",
                )
            )
        if schema.get("uniqueItems"):
            normalized = [canonical_json(item) for item in instance]
            if len(normalized) != len(set(normalized)):
                issues.append(Issue("SCHEMA_UNIQUE_ITEMS", "ERROR", path, "items are not unique"))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                issues.extend(
                    validate_against_schema(value, item_schema, root_schema, f"{path}[{index}]")
                )

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            issues.append(
                Issue(
                    "SCHEMA_MIN_LENGTH",
                    "ERROR",
                    path,
                    f"requires at least {schema['minLength']} characters",
                )
            )
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, instance) is None:
            issues.append(
                Issue("SCHEMA_PATTERN", "ERROR", path, f"does not match pattern {pattern!r}")
            )

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            issues.append(
                Issue(
                    "SCHEMA_MINIMUM",
                    "ERROR",
                    path,
                    f"must be at least {schema['minimum']}",
                )
            )
    return issues


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise KeyError(f"JSON pointer must start with '/': {pointer}")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if token == "-" or not token.isdigit():
                raise KeyError(f"invalid array token {token!r} in {pointer}")
            index = int(token)
            if index >= len(current):
                raise KeyError(f"array index {index} is out of range in {pointer}")
            current = current[index]
        elif isinstance(current, dict):
            if token not in current:
                raise KeyError(f"missing key {token!r} in {pointer}")
            current = current[token]
        else:
            raise KeyError(f"cannot traverse scalar at {token!r} in {pointer}")
    return current


def nonempty_fixture(value: Any) -> bool:
    if isinstance(value, (dict, list, str)):
        return bool(value)
    return value is not None


def semantic_catalog_issues(catalog: Mapping[str, Any], catalog_path: Path) -> List[Issue]:
    issues: List[Issue] = []
    cases = catalog.get("cases", [])
    if not isinstance(cases, list):
        return [Issue("CATALOG_CASES", "ERROR", "$.cases", "cases must be an array")]

    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if case_ids != EXPECTED_CASE_IDS:
        issues.append(
            Issue(
                "CASE_SET",
                "ERROR",
                "$.cases",
                f"case IDs must be ordered exactly E-01 through E-33; got {case_ids!r}",
            )
        )
    if len(case_ids) != len(set(case_ids)):
        issues.append(Issue("CASE_ID_UNIQUE", "ERROR", "$.cases", "case IDs are not unique"))

    one_shot = {case.get("case_id") for case in cases if case.get("required_one_shot") is True}
    if one_shot != REQUIRED_ONE_SHOT:
        issues.append(
            Issue(
                "ONE_SHOT_SET",
                "ERROR",
                "$.cases",
                f"required-one-shot set mismatch; expected {sorted(REQUIRED_ONE_SHOT)}, got {sorted(one_shot)}",
            )
        )

    known_ids = set(case_ids)
    coverage_map = catalog.get("coverage_map", {})
    if isinstance(coverage_map, dict):
        for coverage_name, covered in coverage_map.items():
            for case_id in covered if isinstance(covered, list) else []:
                if case_id not in known_ids:
                    issues.append(
                        Issue(
                            "COVERAGE_CASE_REF",
                            "ERROR",
                            f"$.coverage_map.{coverage_name}",
                            f"unknown case ID {case_id}",
                        )
                    )

    fixture_cache: Dict[Path, Any] = {}
    hash_cache: Dict[Path, str] = {}
    global_check_ids: set[str] = set()
    ur_core_coverage = {f"UR-0{index}": False for index in range(1, 7)}

    evals_root = catalog_path.parent.resolve()
    fixtures_root = (evals_root / "fixtures").resolve()
    for case_index, case in enumerate(cases):
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id", f"index-{case_index}")
        case_path = f"$.cases[{case_index}]"
        if case.get("criticality") == "CORE_REGRESSION":
            for requirement_id in case.get("requirement_ids", []):
                if requirement_id in ur_core_coverage:
                    ur_core_coverage[requirement_id] = True

        prelude = case.get("prelude", [])
        if isinstance(prelude, list):
            observed_orders = [event.get("order") for event in prelude if isinstance(event, dict)]
            expected_orders = list(range(1, len(prelude) + 1))
            if observed_orders != expected_orders:
                issues.append(
                    Issue(
                        "PRELUDE_ORDER",
                        "ERROR",
                        f"{case_path}.prelude",
                        f"orders must be contiguous and ordered; got {observed_orders}",
                    )
                )
        if case_id == "E-08" and len(prelude) < 2:
            issues.append(
                Issue("E08_PRELUDE", "ERROR", f"{case_path}.prelude", "E-08 requires an ordered multi-turn prelude")
            )
        if case_id == "E-11":
            prompt = str(case.get("prompt", "")).lower()
            if "authorize" not in prompt or "gs-01" not in prompt or "gs-02" not in prompt or "only" not in prompt:
                issues.append(
                    Issue(
                        "E11_AUTHORIZATION",
                        "ERROR",
                        f"{case_path}.prompt",
                        "E-11 must contain explicit, bounded implementation authorization",
                    )
                )

        artifacts = case.get("artifacts", [])
        artifact_ids = [item.get("artifact_id") for item in artifacts if isinstance(item, dict)]
        if len(artifact_ids) != len(set(artifact_ids)):
            issues.append(
                Issue("ARTIFACT_ID_UNIQUE", "ERROR", f"{case_path}.artifacts", "artifact IDs are not unique within the case")
            )
        artifact_by_id = {
            artifact.get("artifact_id"): artifact for artifact in artifacts if isinstance(artifact, dict)
        }
        authority = case.get("authority", {})
        if isinstance(authority, dict):
            for field in (
                "current_source_artifact_ids",
                "content_authority_artifact_ids",
                "layout_authority_artifact_ids",
                "editable_target_artifact_ids",
            ):
                for artifact_id in authority.get(field, []):
                    if artifact_id not in artifact_by_id:
                        issues.append(
                            Issue(
                                "AUTHORITY_ARTIFACT_REF",
                                "ERROR",
                                f"{case_path}.authority.{field}",
                                f"unknown artifact ID {artifact_id}",
                            )
                        )
            declared_content = {
                artifact_id
                for artifact_id, artifact in artifact_by_id.items()
                if artifact.get("content_authority") == "AUTHORITATIVE"
            }
            listed_content = set(authority.get("content_authority_artifact_ids", []))
            if declared_content != listed_content:
                issues.append(
                    Issue(
                        "CONTENT_AUTHORITY_CONSISTENCY",
                        "ERROR",
                        f"{case_path}.authority.content_authority_artifact_ids",
                        f"expected {sorted(declared_content)}, got {sorted(listed_content)}",
                    )
                )
            declared_layout = {
                artifact_id
                for artifact_id, artifact in artifact_by_id.items()
                if artifact.get("layout_authority") == "AUTHORITATIVE"
            }
            listed_layout = set(authority.get("layout_authority_artifact_ids", []))
            if declared_layout != listed_layout:
                issues.append(
                    Issue(
                        "LAYOUT_AUTHORITY_CONSISTENCY",
                        "ERROR",
                        f"{case_path}.authority.layout_authority_artifact_ids",
                        f"expected {sorted(declared_layout)}, got {sorted(listed_layout)}",
                    )
                )
            declared_editable = {
                artifact_id
                for artifact_id, artifact in artifact_by_id.items()
                if artifact.get("editable_target") is True
            }
            listed_editable = set(authority.get("editable_target_artifact_ids", []))
            if declared_editable != listed_editable:
                issues.append(
                    Issue(
                        "EDITABLE_TARGET_CONSISTENCY",
                        "ERROR",
                        f"{case_path}.authority.editable_target_artifact_ids",
                        f"expected {sorted(declared_editable)}, got {sorted(listed_editable)}",
                    )
                )

        for artifact_index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                continue
            artifact_path = f"{case_path}.artifacts[{artifact_index}]"
            relative_path = artifact.get("path")
            if not isinstance(relative_path, str):
                continue
            resolved_path = (evals_root / relative_path).resolve()
            if resolved_path != fixtures_root and fixtures_root not in resolved_path.parents:
                issues.append(
                    Issue(
                        "FIXTURE_PATH_CONFINEMENT",
                        "ERROR",
                        f"{artifact_path}.path",
                        f"fixture escapes evals/fixtures: {relative_path}",
                    )
                )
                continue
            if not resolved_path.is_file():
                issues.append(
                    Issue("FIXTURE_EXISTS", "ERROR", f"{artifact_path}.path", f"fixture not found: {resolved_path}")
                )
                continue
            if resolved_path not in hash_cache:
                hash_cache[resolved_path] = sha256_file(resolved_path)
            if artifact.get("sha256") != hash_cache[resolved_path]:
                issues.append(
                    Issue(
                        "FIXTURE_HASH",
                        "ERROR",
                        f"{artifact_path}.sha256",
                        f"expected actual hash {hash_cache[resolved_path]}, got {artifact.get('sha256')}",
                    )
                )
            try:
                if resolved_path not in fixture_cache:
                    fixture_cache[resolved_path] = load_json(resolved_path)
                selected = resolve_json_pointer(fixture_cache[resolved_path], artifact.get("selector", ""))
                if not nonempty_fixture(selected):
                    issues.append(
                        Issue(
                            "FIXTURE_CONTENT",
                            "ERROR",
                            f"{artifact_path}.selector",
                            "selector resolves to empty/non-runnable content",
                        )
                    )
            except (KeyError, ValueError) as exc:
                issues.append(Issue("FIXTURE_SELECTOR", "ERROR", f"{artifact_path}.selector", str(exc)))
            counterpart = artifact.get("version_equivalence", {}).get("counterpart_artifact_id")
            if counterpart is not None and counterpart not in artifact_by_id:
                issues.append(
                    Issue(
                        "COUNTERPART_ARTIFACT_REF",
                        "ERROR",
                        f"{artifact_path}.version_equivalence.counterpart_artifact_id",
                        f"unknown artifact ID {counterpart}",
                    )
                )

        checks = case.get("deterministic_checks", [])
        check_ids = [check.get("check_id") for check in checks if isinstance(check, dict)]
        if len(check_ids) != len(set(check_ids)):
            issues.append(
                Issue("CHECK_ID_UNIQUE_CASE", "ERROR", f"{case_path}.deterministic_checks", "check IDs are not unique")
            )
        for check_index, check in enumerate(checks):
            if not isinstance(check, dict):
                continue
            check_id = check.get("check_id")
            if check_id in global_check_ids:
                issues.append(
                    Issue("CHECK_ID_UNIQUE_GLOBAL", "ERROR", f"{case_path}.deterministic_checks[{check_index}]", f"duplicate check ID {check_id}")
                )
            global_check_ids.add(check_id)
            check_type = check.get("type")
            if check_type in {"STRUCTURED_EQUALS", "STRUCTURED_CONTAINS"} and not check.get("path"):
                issues.append(
                    Issue("CHECK_PATH", "ERROR", f"{case_path}.deterministic_checks[{check_index}]", f"{check_type} requires path")
                )
            if check_type == "SOURCE_HASH_UNCHANGED" and check.get("artifact_id") not in artifact_by_id:
                issues.append(
                    Issue("CHECK_ARTIFACT", "ERROR", f"{case_path}.deterministic_checks[{check_index}]", "SOURCE_HASH_UNCHANGED requires a known artifact_id")
                )
        grader_check_ids = case.get("graders", {}).get("deterministic", {}).get("check_ids", [])
        if set(grader_check_ids) != set(check_ids) or len(grader_check_ids) != len(check_ids):
            issues.append(
                Issue(
                    "GRADER_CHECK_BINDING",
                    "ERROR",
                    f"{case_path}.graders.deterministic.check_ids",
                    "deterministic grader must bind every case check exactly once",
                )
            )

        expected_prefix = str(case_id).replace("-", "")
        for collection_name in ("required_behavior", "forbidden_behavior"):
            for behavior in case.get(collection_name, []):
                behavior_id = behavior.get("behavior_id", "") if isinstance(behavior, dict) else ""
                if not str(behavior_id).startswith(expected_prefix):
                    issues.append(
                        Issue(
                            "BEHAVIOR_ID_CASE_BINDING",
                            "ERROR",
                            f"{case_path}.{collection_name}",
                            f"behavior ID {behavior_id!r} is not bound to {case_id}",
                        )
                    )

        if case.get("held_out_forward_evaluation") and case.get("required_one_shot"):
            issues.append(
                Issue(
                    "HELD_OUT_ONE_SHOT_CONFLICT",
                    "ERROR",
                    case_path,
                    "a known required-one-shot case cannot also be a held-out forward evaluation",
                )
            )

    missing_ur = [requirement for requirement, covered in ur_core_coverage.items() if not covered]
    if missing_ur:
        issues.append(
            Issue(
                "UR_CORE_COVERAGE",
                "ERROR",
                "$.cases",
                f"no CORE_REGRESSION case covers {missing_ur}",
            )
        )
    return issues


def validate_catalog(catalog_path: Path, schema_path: Path) -> Tuple[Mapping[str, Any], List[Issue]]:
    try:
        catalog = load_json(catalog_path)
    except ValueError as exc:
        return {}, [Issue("CATALOG_JSON", "ERROR", str(catalog_path), str(exc))]
    try:
        schema = load_json(schema_path)
    except ValueError as exc:
        return catalog if isinstance(catalog, dict) else {}, [
            Issue("SCHEMA_JSON", "ERROR", str(schema_path), str(exc))
        ]
    if not isinstance(catalog, dict):
        return {}, [Issue("CATALOG_ROOT", "ERROR", "$", "catalog root must be an object")]
    if not isinstance(schema, dict):
        return catalog, [Issue("SCHEMA_ROOT", "ERROR", "$", "schema root must be an object")]
    issues: List[Issue] = []
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        issues.append(
            Issue(
                "SCHEMA_DIALECT",
                "ERROR",
                "$.$schema",
                "eval schema must declare JSON Schema draft 2020-12",
            )
        )
    try:
        issues.extend(validate_against_schema(catalog, schema, schema))
    except ValueError as exc:
        issues.append(Issue("SCHEMA_IMPLEMENTATION", "ERROR", "$", str(exc)))
    issues.extend(semantic_catalog_issues(catalog, catalog_path))
    return catalog, issues


def case_index(catalog: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {case["case_id"]: case for case in catalog.get("cases", [])}


def select_case(catalog: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    selected = case_index(catalog).get(case_id)
    if selected is None:
        raise ValueError(f"unknown case ID {case_id}; expected E-01 through E-33")
    return selected


def execution_packet(case: Mapping[str, Any], catalog_path: Path) -> Mapping[str, Any]:
    """Return only inputs available to the system under evaluation."""

    evals_root = catalog_path.parent.resolve()
    artifact_inputs: List[Mapping[str, Any]] = []
    fixture_cache: Dict[Path, Any] = {}
    for artifact in case["artifacts"]:
        fixture_path = (evals_root / artifact["path"]).resolve()
        if fixture_path not in fixture_cache:
            fixture_cache[fixture_path] = load_json(fixture_path)
        artifact_inputs.append(
            {
                "artifact_id": artifact["artifact_id"],
                "path": artifact["path"],
                "selector": artifact["selector"],
                "sha256": artifact["sha256"],
                "media_type": artifact["media_type"],
                "source_role": artifact["source_role"],
                "content_authority": artifact["content_authority"],
                "layout_authority": artifact["layout_authority"],
                "editable_target": artifact["editable_target"],
                "version_equivalence": copy.deepcopy(artifact["version_equivalence"]),
                "content": copy.deepcopy(
                    resolve_json_pointer(fixture_cache[fixture_path], artifact["selector"])
                ),
            }
        )
    prelude_inputs = [
        {
            key: copy.deepcopy(event[key])
            for key in ("order", "actor", "message", "artifact_changes", "state_changes")
        }
        for event in case["prelude"]
    ]
    return {
        "packet_version": "1.0.0",
        "case_id": case["case_id"],
        "case_version": case["version"],
        "protocol": {
            "clean_context_required": True,
            "active_skill": "gated-sprint",
            "do_not_disclose_expected_or_forbidden_behavior": True,
            "capture_final_response_artifacts_state_tools_and_skill_hash": True,
        },
        "route": copy.deepcopy(case["route"]),
        "prelude": prelude_inputs,
        "prompt": case["prompt"],
        "artifacts": artifact_inputs,
        "authority": copy.deepcopy(case["authority"]),
        "starting_state": copy.deepcopy(case["starting_state"]),
    }


def issue_execution_packet(
    case: Mapping[str, Any],
    catalog_path: Path,
    *,
    run_id: str,
    issued_at: str,
    expires_at: str,
    policy: TrustPolicy,
) -> Mapping[str, Any]:
    """Issue a signed, expectation-free packet for exactly one trusted run."""

    if not run_id.strip():
        raise ValueError("--run-id must be non-empty")
    issued = parsed_timestamp(issued_at)
    expires = parsed_timestamp(expires_at)
    if issued is None or expires is None:
        raise ValueError("--issued-at and --expires-at must be timezone-aware timestamps")
    if expires <= issued:
        raise ValueError("--expires-at must be later than --issued-at")
    body = execution_packet(case, catalog_path)
    issuance = signed_payload(
        {
            "receipt_version": RECEIPT_VERSION,
            "case_id": case["case_id"],
            "run_id": run_id,
            "packet_payload_sha256": sha256_value(body),
            "issued_at": issued_at,
            "expires_at": expires_at,
            "trusted_runner": {
                "id": policy.runner_id,
                "provenance": policy.runner_provenance,
            },
            "skill": {
                "name": "gated-sprint",
                "version": policy.skill_version,
                "sha256": policy.skill_sha256,
            },
        },
        policy.key,
    )
    return {**body, "execution_issuance": issuance}


def issuance_issues(
    packet: Mapping[str, Any],
    case: Mapping[str, Any],
    catalog_path: Path,
    policy: TrustPolicy,
) -> List[Issue]:
    issues: List[Issue] = []
    issuance = packet.get("execution_issuance")
    if not isinstance(issuance, dict):
        return [
            Issue(
                "EXECUTION_ISSUANCE",
                "ERROR",
                "$.execution_issuance",
                "a trusted signed execution issuance is required",
            )
        ]
    missing = sorted(ISSUANCE_FIELDS - set(issuance))
    unexpected = sorted(set(issuance) - ISSUANCE_FIELDS)
    if missing or unexpected:
        issues.append(
            Issue(
                "EXECUTION_ISSUANCE_FIELDS",
                "ERROR",
                "$.execution_issuance",
                f"issuance fields are not closed (missing={missing}, unexpected={unexpected})",
            )
        )
    if issuance.get("receipt_version") != RECEIPT_VERSION:
        issues.append(
            Issue(
                "EXECUTION_ISSUANCE_VERSION",
                "ERROR",
                "$.execution_issuance.receipt_version",
                f"receipt_version must be {RECEIPT_VERSION!r}",
            )
        )
    if issuance.get("case_id") != case["case_id"]:
        issues.append(
            Issue(
                "EXECUTION_ISSUANCE_CASE",
                "ERROR",
                "$.execution_issuance.case_id",
                "issuance is not bound to the selected case",
            )
        )
    expected_runner = {"id": policy.runner_id, "provenance": policy.runner_provenance}
    expected_skill = {
        "name": "gated-sprint",
        "version": policy.skill_version,
        "sha256": policy.skill_sha256,
    }
    if issuance.get("trusted_runner") != expected_runner:
        issues.append(
            Issue(
                "EXECUTION_RUNNER_BINDING",
                "ERROR",
                "$.execution_issuance.trusted_runner",
                "issuance does not match the externally trusted runner identity and provenance",
            )
        )
    if issuance.get("skill") != expected_skill:
        issues.append(
            Issue(
                "EXECUTION_SKILL_BINDING",
                "ERROR",
                "$.execution_issuance.skill",
                "issuance does not match the externally supplied current skill version/hash",
            )
        )
    issued = parsed_timestamp(issuance.get("issued_at"))
    expires = parsed_timestamp(issuance.get("expires_at"))
    if issued is None or expires is None or expires <= issued:
        issues.append(
            Issue(
                "EXECUTION_ISSUANCE_TIME",
                "ERROR",
                "$.execution_issuance",
                "issuance requires an ordered timezone-aware issued_at/expires_at window",
            )
        )
    body = {key: copy.deepcopy(value) for key, value in packet.items() if key != "execution_issuance"}
    if body != execution_packet(case, catalog_path):
        issues.append(
            Issue(
                "EXECUTION_PACKET_CONTENT",
                "ERROR",
                "$",
                "prepared packet does not match current catalog inputs",
            )
        )
    if issuance.get("packet_payload_sha256") != sha256_value(body):
        issues.append(
            Issue(
                "EXECUTION_PACKET_HASH",
                "ERROR",
                "$.execution_issuance.packet_payload_sha256",
                "issuance packet hash does not match the prepared packet payload",
            )
        )
    if not signature_valid(issuance, policy.key):
        issues.append(
            Issue(
                "EXECUTION_ISSUANCE_SIGNATURE",
                "ERROR",
                "$.execution_issuance.signature",
                "issuance signature is absent or invalid for the trusted receipt key",
            )
        )
    return issues


def capture_template(case: Mapping[str, Any], packet: Mapping[str, Any]) -> Mapping[str, Any]:
    qualitative = case["graders"]["qualitative"]
    issuance = packet["execution_issuance"]
    return {
        "capture_version": "1.1.0",
        "case_id": case["case_id"],
        "run_id": issuance["run_id"],
        "captured_at": "",
        "skill": copy.deepcopy(issuance["skill"]),
        "final_response": "",
        "structured_output": {"findings": {}, "states": {}, "actions": []},
        "state_sidecar": {},
        "tool_actions": [],
        "produced_artifacts": [],
        "source_hashes_after": {},
        "qualitative_grade": {
            "grader_id": qualitative["grader_id"],
            "evaluator_id": "",
            "independent": False,
            "result": "FAIL",
            "criteria": [
                {"criterion_id": item["criterion_id"], "result": "FAIL", "evidence": []}
                for item in qualitative["rubric"]
            ],
            "evidence_requirements": [
                {"requirement": requirement, "citations": []}
                for requirement in qualitative["evidence_must_cite"]
            ],
            "notes": "",
        },
        EXECUTION_RECEIPT_FIELD: None,
    }


def capture_payload(capture: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in capture.items()
        if key != EXECUTION_RECEIPT_FIELD
    }


def seal_capture(
    capture: Mapping[str, Any],
    packet: Mapping[str, Any],
    case: Mapping[str, Any],
    catalog_path: Path,
    captured_at: str,
    policy: TrustPolicy,
) -> Mapping[str, Any]:
    packet_issues = issuance_issues(packet, case, catalog_path, policy)
    if packet_issues:
        raise ValueError("prepared packet is not trusted: " + "; ".join(item.explanation for item in packet_issues))
    issuance = packet["execution_issuance"]
    captured = parsed_timestamp(captured_at)
    issued = parsed_timestamp(issuance["issued_at"])
    expires = parsed_timestamp(issuance["expires_at"])
    if captured is None:
        raise ValueError("--captured-at must be a timezone-aware timestamp")
    if issued is None or expires is None or not (issued <= captured <= expires):
        raise ValueError("--captured-at must fall within the signed issuance window")
    if capture.get("case_id") != case["case_id"] or capture.get("run_id") != issuance["run_id"]:
        raise ValueError("capture case_id/run_id does not match the issued packet")
    if capture.get("skill") != issuance["skill"]:
        raise ValueError("capture skill metadata does not match the issued packet")
    sealed = copy.deepcopy(dict(capture))
    sealed["captured_at"] = captured_at
    sealed[EXECUTION_RECEIPT_FIELD] = None
    payload = capture_payload(sealed)
    receipt = signed_payload(
        {
            "receipt_version": RECEIPT_VERSION,
            "case_id": case["case_id"],
            "run_id": issuance["run_id"],
            "prepared_packet_sha256": sha256_value(packet),
            "capture_payload_sha256": sha256_value(payload),
            "captured_at": captured_at,
            "execution_issuance": copy.deepcopy(issuance),
        },
        policy.key,
    )
    sealed[EXECUTION_RECEIPT_FIELD] = receipt
    return sealed


def execution_receipt_issues(
    capture: Mapping[str, Any],
    case: Mapping[str, Any],
    catalog_path: Path,
    policy: TrustPolicy,
) -> List[Issue]:
    receipt = capture.get(EXECUTION_RECEIPT_FIELD)
    if not isinstance(receipt, dict):
        return [
            Issue(
                "EXECUTION_RECEIPT",
                "ERROR",
                f"$.{EXECUTION_RECEIPT_FIELD}",
                "an externally sealed execution receipt is required",
            )
        ]
    issues: List[Issue] = []
    missing = sorted(EXECUTION_RECEIPT_FIELDS - set(receipt))
    unexpected = sorted(set(receipt) - EXECUTION_RECEIPT_FIELDS)
    if missing or unexpected:
        issues.append(
            Issue(
                "EXECUTION_RECEIPT_FIELDS",
                "ERROR",
                f"$.{EXECUTION_RECEIPT_FIELD}",
                f"execution receipt fields are not closed (missing={missing}, unexpected={unexpected})",
            )
        )
    if receipt.get("receipt_version") != RECEIPT_VERSION:
        issues.append(
            Issue(
                "EXECUTION_RECEIPT_VERSION",
                "ERROR",
                f"$.{EXECUTION_RECEIPT_FIELD}.receipt_version",
                f"receipt_version must be {RECEIPT_VERSION!r}",
            )
        )
    issuance = receipt.get("execution_issuance")
    if isinstance(issuance, dict):
        reconstructed_packet = {
            **execution_packet(case, catalog_path),
            "execution_issuance": copy.deepcopy(issuance),
        }
        issues.extend(issuance_issues(reconstructed_packet, case, catalog_path, policy))
        if receipt.get("prepared_packet_sha256") != sha256_value(reconstructed_packet):
            issues.append(
                Issue(
                    "EXECUTION_PREPARED_PACKET_HASH",
                    "ERROR",
                    f"$.{EXECUTION_RECEIPT_FIELD}.prepared_packet_sha256",
                    "receipt is not bound to the reconstructed current prepared packet",
                )
            )
        issued = parsed_timestamp(issuance.get("issued_at"))
        expires = parsed_timestamp(issuance.get("expires_at"))
    else:
        issues.append(
            Issue(
                "EXECUTION_ISSUANCE",
                "ERROR",
                f"$.{EXECUTION_RECEIPT_FIELD}.execution_issuance",
                "receipt must embed the signed execution issuance",
            )
        )
        issued = None
        expires = None
    captured = parsed_timestamp(receipt.get("captured_at"))
    if captured is None or issued is None or expires is None or not (issued <= captured <= expires):
        issues.append(
            Issue(
                "EXECUTION_CAPTURE_TIME",
                "ERROR",
                f"$.{EXECUTION_RECEIPT_FIELD}.captured_at",
                "captured_at must be timezone-aware and within the signed issuance window",
            )
        )
    for field, expected in (
        ("case_id", case["case_id"]),
        ("run_id", issuance.get("run_id") if isinstance(issuance, dict) else None),
        ("captured_at", capture.get("captured_at")),
    ):
        if receipt.get(field) != expected:
            issues.append(
                Issue(
                    "EXECUTION_RECEIPT_BINDING",
                    "ERROR",
                    f"$.{EXECUTION_RECEIPT_FIELD}.{field}",
                    f"receipt {field} does not match the bound capture/issuance",
                )
            )
    if isinstance(issuance, dict):
        if capture.get("run_id") != issuance.get("run_id"):
            issues.append(
                Issue(
                    "EXECUTION_RUN_BINDING",
                    "ERROR",
                    "$.run_id",
                    "capture run_id does not match the signed issuance",
                )
            )
        if capture.get("skill") != issuance.get("skill"):
            issues.append(
                Issue(
                    "EXECUTION_SKILL_BINDING",
                    "ERROR",
                    "$.skill",
                    "capture skill metadata does not match the signed issuance/current skill",
                )
            )
    payload_hash = sha256_value(capture_payload(capture))
    if receipt.get("capture_payload_sha256") != payload_hash:
        issues.append(
            Issue(
                "EXECUTION_CAPTURE_HASH",
                "ERROR",
                f"$.{EXECUTION_RECEIPT_FIELD}.capture_payload_sha256",
                "receipt does not match the captured payload bytes",
            )
        )
    if not signature_valid(receipt, policy.key):
        issues.append(
            Issue(
                "EXECUTION_RECEIPT_SIGNATURE",
                "ERROR",
                f"$.{EXECUTION_RECEIPT_FIELD}.signature",
                "execution receipt signature is absent or invalid for the trusted receipt key",
            )
        )
    return issues


def capture_issues(capture: Mapping[str, Any], case: Mapping[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    required_fields = {
        "capture_version": str,
        "case_id": str,
        "run_id": str,
        "captured_at": str,
        "skill": dict,
        "final_response": str,
        "structured_output": dict,
        "state_sidecar": dict,
        "tool_actions": list,
        "produced_artifacts": list,
        "source_hashes_after": dict,
        EXECUTION_RECEIPT_FIELD: dict,
    }
    for field, expected_type in required_fields.items():
        if field not in capture:
            issues.append(Issue("CAPTURE_REQUIRED", "ERROR", f"$.{field}", "required capture field is missing"))
        elif not isinstance(capture[field], expected_type):
            issues.append(
                Issue(
                    "CAPTURE_TYPE",
                    "ERROR",
                    f"$.{field}",
                    f"expected {expected_type.__name__}",
                )
            )
    if capture.get("case_id") != case["case_id"]:
        issues.append(
            Issue(
                "CAPTURE_CASE_BINDING",
                "ERROR",
                "$.case_id",
                f"capture is for {capture.get('case_id')!r}, expected {case['case_id']!r}",
            )
        )
    if capture.get("capture_version") != "1.1.0":
        issues.append(
            Issue(
                "CAPTURE_VERSION",
                "ERROR",
                "$.capture_version",
                "trusted captures must use capture_version '1.1.0'",
            )
        )
    if not isinstance(capture.get("run_id"), str) or not capture.get("run_id", "").strip():
        issues.append(
            Issue("CAPTURE_RUN_ID", "ERROR", "$.run_id", "a non-empty issued run_id is required")
        )
    if not is_aware_timestamp(capture.get("captured_at")):
        issues.append(
            Issue(
                "CAPTURE_TIME",
                "ERROR",
                "$.captured_at",
                "captured_at must be a timezone-aware timestamp",
            )
        )
    skill = capture.get("skill", {})
    if isinstance(skill, dict):
        if skill.get("name") != "gated-sprint":
            issues.append(
                Issue("CAPTURE_SKILL", "ERROR", "$.skill.name", "skill name must be 'gated-sprint'")
            )
        hash_value = skill.get("sha256")
        if not isinstance(hash_value, str) or re.fullmatch(r"[0-9a-f]{64}", hash_value) is None:
            issues.append(
                Issue("CAPTURE_SKILL_HASH", "ERROR", "$.skill.sha256", "a 64-character lowercase SHA-256 is required")
            )
        if not isinstance(skill.get("version"), str) or not skill.get("version"):
            issues.append(
                Issue("CAPTURE_SKILL_VERSION", "ERROR", "$.skill.version", "skill version is required")
            )
    structured = capture.get("structured_output", {})
    if isinstance(structured, dict):
        for field, expected_type in (("findings", dict), ("states", dict), ("actions", list)):
            if not isinstance(structured.get(field), expected_type):
                issues.append(
                    Issue(
                        "CAPTURE_STRUCTURED_OUTPUT",
                        "ERROR",
                        f"$.structured_output.{field}",
                        f"expected {expected_type.__name__}",
                    )
                )
    evidence_surfaces = {
        "FINAL_RESPONSE": capture.get("final_response"),
        "STRUCTURED_OUTPUT": capture.get("structured_output"),
        "STATE_SIDECAR": capture.get("state_sidecar"),
        "PRODUCED_ARTIFACTS": capture.get("produced_artifacts"),
    }
    for behavior in case.get("required_behavior", []):
        target = behavior.get("evidence_target")
        surface = evidence_surfaces.get(target)
        has_evidence = bool(surface)
        if target == "STRUCTURED_OUTPUT" and isinstance(surface, dict):
            has_evidence = any(bool(surface.get(field)) for field in ("findings", "states", "actions"))
        if not has_evidence:
            issues.append(
                Issue(
                    "CAPTURE_REQUIRED_EVIDENCE_TARGET",
                    "ERROR",
                    f"$.required_behavior[{behavior.get('behavior_id', '?')}]",
                    f"required behavior {behavior.get('behavior_id')} lacks evidence in {target}",
                )
            )
    for index, action in enumerate(capture.get("tool_actions", [])):
        if not isinstance(action, dict) or not isinstance(action.get("action"), str):
            issues.append(
                Issue(
                    "CAPTURE_TOOL_ACTION",
                    "ERROR",
                    f"$.tool_actions[{index}]",
                    "each tool action needs a string action code",
                )
            )
    for index, artifact in enumerate(capture.get("produced_artifacts", [])):
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
            issues.append(
                Issue(
                    "CAPTURE_PRODUCED_ARTIFACT",
                    "ERROR",
                    f"$.produced_artifacts[{index}]",
                    "each produced artifact needs a path",
                )
            )
        elif re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))) is None:
            issues.append(
                Issue(
                    "CAPTURE_PRODUCED_HASH",
                    "ERROR",
                    f"$.produced_artifacts[{index}].sha256",
                    "each produced artifact needs a lowercase SHA-256",
                )
            )
    for location in local_absolute_path_locations(capture):
        issues.append(
            Issue(
                "CAPTURE_ABSOLUTE_PATH",
                "ERROR",
                location,
                "captures and records may not persist machine-local absolute paths or file URLs",
            )
        )
    return issues


def dotted_lookup(document: Any, path: str) -> Tuple[bool, Any]:
    current = document
    for token in path.split(".") if path else []:
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False, None
    return True, current


def observed_action_codes(capture: Mapping[str, Any]) -> set[str]:
    codes: set[str] = set()
    structured = capture.get("structured_output", {})
    if isinstance(structured, dict):
        for action in structured.get("actions", []):
            if isinstance(action, str):
                codes.add(action)
    for action in capture.get("tool_actions", []):
        if isinstance(action, dict) and isinstance(action.get("action"), str):
            codes.add(action["action"])
    for action in capture.get("observed_actions", []):
        if isinstance(action, str):
            codes.add(action)
    return codes


def evaluate_deterministic_checks(
    capture: Mapping[str, Any], case: Mapping[str, Any]
) -> Tuple[List[Mapping[str, Any]], bool, bool]:
    results: List[Mapping[str, Any]] = []
    any_failure = False
    any_incomplete = False
    actions = observed_action_codes(capture)
    artifact_by_id = {artifact["artifact_id"]: artifact for artifact in case["artifacts"]}
    for check in case["deterministic_checks"]:
        status = "PASS"
        observed: Any = None
        explanation = "check passed"
        check_type = check["type"]
        if check_type in {"STRUCTURED_EQUALS", "STRUCTURED_CONTAINS"}:
            found, observed = dotted_lookup(capture, check["path"])
            if not found:
                status = "INCOMPLETE"
                explanation = f"captured run does not provide {check['path']}"
            elif check_type == "STRUCTURED_EQUALS" and observed != check["expected"]:
                status = "FAIL"
                explanation = f"expected {check['expected']!r}, observed {observed!r}"
            elif check_type == "STRUCTURED_CONTAINS":
                expected = check["expected"]
                contains = False
                if isinstance(observed, (list, tuple, set, str)):
                    contains = expected in observed
                elif isinstance(observed, dict):
                    contains = expected in observed or expected in observed.values()
                if not contains:
                    status = "FAIL"
                    explanation = f"expected container to include {expected!r}; observed {observed!r}"
        elif check_type == "ACTION_ABSENT":
            observed = sorted(actions)
            if check["expected"] in actions:
                status = "FAIL"
                explanation = f"forbidden action {check['expected']!r} was observed"
        elif check_type == "SOURCE_HASH_UNCHANGED":
            artifact_id = check["artifact_id"]
            observed = capture.get("source_hashes_after", {}).get(artifact_id)
            if observed is None:
                status = "INCOMPLETE"
                explanation = f"source_hashes_after lacks {artifact_id}"
            else:
                expected_hash = artifact_by_id[artifact_id]["sha256"]
                if observed != expected_hash:
                    status = "FAIL"
                    explanation = f"source hash changed: expected {expected_hash}, observed {observed}"
        else:
            status = "INCOMPLETE"
            explanation = f"unsupported check type {check_type}"
        if status == "FAIL":
            any_failure = True
        elif status == "INCOMPLETE":
            any_incomplete = True
        results.append(
            {
                "check_id": check["check_id"],
                "type": check_type,
                "status": status,
                "expected": check.get("expected"),
                "observed": observed,
                "explanation": explanation,
            }
        )
    return results, any_failure, any_incomplete


def evaluate_expected_contract(
    capture: Mapping[str, Any], case: Mapping[str, Any]
) -> Tuple[List[Mapping[str, Any]], bool, bool]:
    """Compare every declared structured expectation with the captured output."""

    results: List[Mapping[str, Any]] = []
    any_failure = False
    any_incomplete = False
    structured = capture.get("structured_output", {})
    if not isinstance(structured, dict):
        structured = {}
    for section in ("findings", "states"):
        observed_section = structured.get(section, {})
        if not isinstance(observed_section, dict):
            observed_section = {}
        for key, expected_value in case["expected"][section].items():
            if key not in observed_section:
                status = "INCOMPLETE"
                observed_value = None
                explanation = f"structured_output.{section} lacks {key}"
                any_incomplete = True
            else:
                observed_value = observed_section[key]
                if observed_value == expected_value:
                    status = "PASS"
                    explanation = "declared expectation matched"
                else:
                    status = "FAIL"
                    explanation = f"expected {expected_value!r}, observed {observed_value!r}"
                    any_failure = True
            results.append(
                {
                    "expectation_id": f"{case['case_id']}-{section.upper()}-{key}",
                    "path": f"structured_output.{section}.{key}",
                    "status": status,
                    "expected": expected_value,
                    "observed": observed_value,
                    "explanation": explanation,
                }
            )
    observed_actions = structured.get("actions", [])
    if not isinstance(observed_actions, list):
        observed_actions = []
    for expected_action in case["expected"]["actions"]:
        if expected_action in observed_actions:
            status = "PASS"
            explanation = "declared action was captured"
        elif "actions" not in structured:
            status = "INCOMPLETE"
            explanation = "structured_output.actions is missing"
            any_incomplete = True
        else:
            status = "FAIL"
            explanation = f"declared action {expected_action!r} was not captured"
            any_failure = True
        results.append(
            {
                "expectation_id": f"{case['case_id']}-ACTION-{expected_action}",
                "path": "structured_output.actions",
                "status": status,
                "expected": expected_action,
                "observed": observed_actions,
                "explanation": explanation,
            }
        )
    return results, any_failure, any_incomplete


def evidence_source_text(
    citation: Mapping[str, Any],
    capture: Mapping[str, Any],
    case: Mapping[str, Any],
    catalog_path: Path,
) -> Optional[str]:
    source = citation.get("source")
    if source == "FINAL_RESPONSE":
        return capture.get("final_response", "")
    if source == "STRUCTURED_OUTPUT":
        return canonical_json(capture.get("structured_output", {}))
    if source == "STATE_SIDECAR":
        return canonical_json(capture.get("state_sidecar", {}))
    if source == "TOOL_ACTIONS":
        return canonical_json(capture.get("tool_actions", []))
    if source == "PRODUCED_ARTIFACTS":
        return canonical_json(capture.get("produced_artifacts", []))
    if source == "FIXTURE":
        locator = citation.get("locator", "")
        artifact_id = locator.split("#", 1)[0]
        artifacts = {
            artifact["artifact_id"]: artifact for artifact in case.get("artifacts", [])
        }
        artifact = artifacts.get(artifact_id)
        if artifact is None:
            return None
        fixture = load_json((catalog_path.parent / artifact["path"]).resolve())
        selected = resolve_json_pointer(fixture, artifact["selector"])
        return canonical_json(selected)
    return None


def citation_valid(
    citation: Any,
    capture: Mapping[str, Any],
    case: Mapping[str, Any],
    catalog_path: Path,
) -> Tuple[bool, str]:
    if not isinstance(citation, dict):
        return False, "citation must be an object"
    for field in ("source", "locator", "quote"):
        if not isinstance(citation.get(field), str) or not citation[field].strip():
            return False, f"citation requires non-empty {field}"
    try:
        source_text = evidence_source_text(citation, capture, case, catalog_path)
    except (KeyError, ValueError) as exc:
        return False, f"could not resolve citation: {exc}"
    if source_text is None:
        return False, f"unsupported or unresolved citation source {citation.get('source')!r}"
    if citation["quote"] not in source_text:
        return False, "quoted evidence is not present in the cited source"
    return True, "citation resolved"


def evaluate_qualitative_grade(
    capture: Mapping[str, Any], case: Mapping[str, Any], catalog_path: Path
) -> Mapping[str, Any]:
    expected_grader = case["graders"]["qualitative"]
    grade = capture.get("qualitative_grade")
    if not isinstance(grade, dict):
        return {
            "status": "INCOMPLETE",
            "grader_id": expected_grader["grader_id"],
            "issues": ["independent qualitative grade is missing"],
        }
    issues: List[str] = []
    if grade.get("grader_id") != expected_grader["grader_id"]:
        issues.append(
            f"grader_id must be {expected_grader['grader_id']!r}; got {grade.get('grader_id')!r}"
        )
    if grade.get("independent") is not True:
        issues.append("grader must attest independent=true")
    if not isinstance(grade.get("evaluator_id"), str) or not grade["evaluator_id"].strip():
        issues.append("evaluator_id is required")
    result = grade.get("result")
    if result not in RESULT_RANK:
        issues.append("result must be FAIL, PARTIAL, or PASS")
    elif RESULT_RANK[result] < RESULT_RANK[expected_grader["minimum_result"]]:
        issues.append(
            f"result {result} is below minimum {expected_grader['minimum_result']}"
        )

    observed_criteria = {
        item.get("criterion_id"): item
        for item in grade.get("criteria", [])
        if isinstance(item, dict) and isinstance(item.get("criterion_id"), str)
    }
    for criterion in expected_grader["rubric"]:
        observed = observed_criteria.get(criterion["criterion_id"])
        if observed is None:
            issues.append(f"missing criterion grade {criterion['criterion_id']}")
            continue
        if criterion["required"] and observed.get("result") != "PASS":
            issues.append(f"required criterion {criterion['criterion_id']} did not pass")
        citations = observed.get("evidence", [])
        if not isinstance(citations, list) or not citations:
            issues.append(f"criterion {criterion['criterion_id']} lacks cited evidence")
        else:
            for citation_index, citation in enumerate(citations):
                valid, explanation = citation_valid(citation, capture, case, catalog_path)
                if not valid:
                    issues.append(
                        f"criterion {criterion['criterion_id']} citation {citation_index}: {explanation}"
                    )

    observed_requirements = {
        item.get("requirement"): item
        for item in grade.get("evidence_requirements", [])
        if isinstance(item, dict) and isinstance(item.get("requirement"), str)
    }
    for requirement in expected_grader["evidence_must_cite"]:
        observed = observed_requirements.get(requirement)
        if observed is None:
            issues.append(f"missing evidence requirement: {requirement}")
            continue
        citations = observed.get("citations", [])
        if not isinstance(citations, list) or not citations:
            issues.append(f"evidence requirement has no citation: {requirement}")
        else:
            for citation_index, citation in enumerate(citations):
                valid, explanation = citation_valid(citation, capture, case, catalog_path)
                if not valid:
                    issues.append(
                        f"evidence requirement {requirement!r} citation {citation_index}: {explanation}"
                    )
    if issues:
        substantive_failure = result in RESULT_RANK and RESULT_RANK[result] < RESULT_RANK[expected_grader["minimum_result"]]
        status = "FAIL" if substantive_failure else "INCOMPLETE"
    else:
        status = "PASS"
    return {
        "status": status,
        "grader_id": expected_grader["grader_id"],
        "minimum_result": expected_grader["minimum_result"],
        "observed_result": result,
        "issues": issues,
    }


def grade_capture(
    capture: Mapping[str, Any],
    case: Mapping[str, Any],
    catalog_path: Path,
    *,
    execution_issues: Sequence[Issue] = (),
) -> Mapping[str, Any]:
    structural_issues = [*capture_issues(capture, case), *execution_issues]
    expected_contract, expected_failure, expected_incomplete = evaluate_expected_contract(
        capture, case
    )
    deterministic, deterministic_failure, deterministic_incomplete = evaluate_deterministic_checks(
        capture, case
    )
    actions = observed_action_codes(capture)
    forbidden_observations: List[Mapping[str, Any]] = []
    for behavior in case["forbidden_behavior"]:
        observed_codes = sorted(set(behavior["action_codes"]) & actions)
        if observed_codes:
            forbidden_observations.append(
                {
                    "behavior_id": behavior["behavior_id"],
                    "description": behavior["description"],
                    "observed_action_codes": observed_codes,
                    "zero_tolerance": behavior["zero_tolerance"],
                }
            )
    qualitative = evaluate_qualitative_grade(capture, case, catalog_path)

    if (
        structural_issues
        or expected_failure
        or deterministic_failure
        or forbidden_observations
        or qualitative["status"] == "FAIL"
    ):
        overall = "FAIL"
    elif expected_incomplete or deterministic_incomplete or qualitative["status"] == "INCOMPLETE":
        overall = "INCOMPLETE"
    else:
        overall = "PASS"
    hard_invariant_zero_forbidden = not forbidden_observations
    if case["criticality"] == "HARD_INVARIANT" and not hard_invariant_zero_forbidden:
        overall = "FAIL"

    return {
        "report_version": "1.0.0",
        "case_id": case["case_id"],
        "case_version": case["version"],
        "run_id": capture.get("run_id"),
        "graded_at": utc_now(),
        "execution_receipt_verified": not execution_issues,
        "criticality": case["criticality"],
        "required_one_shot": case["required_one_shot"],
        "structural_issues": [asdict(issue) for issue in structural_issues],
        "expected_contract_results": expected_contract,
        "deterministic_results": deterministic,
        "forbidden_observations": forbidden_observations,
        "hard_invariant_zero_forbidden": hard_invariant_zero_forbidden,
        "qualitative_result": qualitative,
        "overall_result": overall,
        "limitations": [
            "Deterministic checks validate captured structure and action logs, not scientific correctness.",
            "The qualitative result is an attestation by the named independent grader; this script validates its completeness and citations but does not replace that judgment.",
            "This harness does not invoke or simulate a model.",
        ],
    }


def normalized_report_for_binding(report: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = copy.deepcopy(dict(report))
    normalized.pop("graded_at", None)
    return normalized


def verified_record_capture(
    path: Path,
    catalog: Mapping[str, Any],
    catalog_path: Path,
    schema_path: Path,
    policy: TrustPolicy,
) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load one immutable record and verify all current content bindings."""

    record = load_json(path)
    if not isinstance(record, dict):
        raise ValueError("suite inputs must be versioned record envelopes, not raw captures")
    if "record_version" not in record:
        raise ValueError("suite inputs must be versioned record envelopes, not raw captures")
    if record.get("record_version") != "1.0.0":
        raise ValueError("record_version must be '1.0.0'")
    missing_fields = sorted(RECORD_ENVELOPE_FIELDS - set(record))
    unexpected_fields = sorted(set(record) - RECORD_ENVELOPE_FIELDS)
    if missing_fields or unexpected_fields:
        details = []
        if missing_fields:
            details.append(f"missing fields {missing_fields}")
        if unexpected_fields:
            details.append(f"unexpected fields {unexpected_fields}")
        raise ValueError(f"record envelope fields are not closed: {'; '.join(details)}")
    if not is_aware_timestamp(record.get("recorded_at")):
        raise ValueError("record envelope requires a timezone-aware recorded_at timestamp")
    path_locations = local_absolute_path_locations(record)
    if path_locations:
        raise ValueError(
            "record contains machine-local absolute paths or file URLs at "
            + ", ".join(path_locations)
        )
    capture = record.get("capture")
    stored_report = record.get("report")
    if not isinstance(capture, dict) or not isinstance(stored_report, dict):
        raise ValueError("record envelope requires capture and report objects")
    case_id = capture.get("case_id")
    if not isinstance(case_id, str):
        raise ValueError("record capture is missing case_id")
    case = select_case(catalog, case_id)
    receipt_problems = execution_receipt_issues(capture, case, catalog_path, policy)
    if receipt_problems:
        raise ValueError(
            "record capture has no valid trusted execution receipt: "
            + "; ".join(item.explanation for item in receipt_problems)
        )
    expected_fixture_hashes = {
        artifact["artifact_id"]: artifact["sha256"] for artifact in case["artifacts"]
    }
    bindings = (
        ("catalog_file", catalog_path.name),
        ("catalog_sha256", sha256_file(catalog_path)),
        ("schema_sha256", sha256_file(schema_path)),
        ("fixture_hashes", expected_fixture_hashes),
        ("capture_sha256", sha256_value(capture)),
        ("report_sha256", sha256_value(stored_report)),
    )
    for field, expected in bindings:
        if record.get(field) != expected:
            raise ValueError(f"record {field} does not match current bound content")

    current_report = grade_capture(capture, case, catalog_path)
    if normalized_report_for_binding(stored_report) != normalized_report_for_binding(current_report):
        raise ValueError("stored report does not match a fresh grade of the bound capture")
    return capture, current_report


def load_bound_capture_input(
    path: Path,
    catalog: Mapping[str, Any],
    catalog_path: Path,
    schema_path: Path,
    policy: TrustPolicy,
) -> Tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    """Load a raw capture, or fully verify a record before unwrapping it."""

    loaded = load_json(path)
    if not isinstance(loaded, dict):
        raise ValueError(f"capture/record root must be an object: {path}")
    if RECORD_MARKER_FIELDS.intersection(loaded):
        return verified_record_capture(path, catalog, catalog_path, schema_path, policy)
    return loaded, None


def output_value(value: Any, output: Optional[str], *, force: bool = False) -> None:
    if output is None or output == "-":
        json.dump(value, sys.stdout, indent=2, ensure_ascii=False, allow_nan=False)
        sys.stdout.write("\n")
        return
    write_json_atomic(Path(output), value, overwrite=force)


def print_validation(issues: Sequence[Issue], *, json_output: bool) -> None:
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    warnings = [issue for issue in issues if issue.severity == "WARNING"]
    if json_output:
        print(
            json.dumps(
                {
                    "valid": not errors,
                    "error_count": len(errors),
                    "warning_count": len(warnings),
                    "issues": [asdict(issue) for issue in issues],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if errors:
        print(f"GatedSprint eval catalog: FAIL ({len(errors)} errors, {len(warnings)} warnings)")
    else:
        print(f"GatedSprint eval catalog: PASS (33 cases; {len(warnings)} warnings)")
    for issue in issues:
        print(f"[{issue.severity}] {issue.check_id} {issue.path}: {issue.explanation}")


def command_validate(args: argparse.Namespace) -> int:
    _, issues = validate_catalog(Path(args.catalog).resolve(), Path(args.schema).resolve())
    print_validation(issues, json_output=args.json)
    return 1 if any(issue.severity == "ERROR" for issue in issues) else 0


def validated_catalog_or_raise(args: argparse.Namespace) -> Tuple[Mapping[str, Any], Path]:
    catalog_path = Path(args.catalog).resolve()
    catalog, issues = validate_catalog(catalog_path, Path(args.schema).resolve())
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    if errors:
        summary = "; ".join(f"{issue.check_id}: {issue.explanation}" for issue in errors[:5])
        raise ValueError(f"catalog validation failed: {summary}")
    return catalog, catalog_path


def command_list(args: argparse.Namespace) -> int:
    catalog, _ = validated_catalog_or_raise(args)
    cases = catalog["cases"]
    if args.required_one_shot:
        cases = [case for case in cases if case["required_one_shot"]]
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "case_id": case["case_id"],
                        "title": case["title"],
                        "criticality": case["criticality"],
                        "required_one_shot": case["required_one_shot"],
                        "held_out_forward_evaluation": case["held_out_forward_evaluation"],
                    }
                    for case in cases
                ],
                indent=2,
            )
        )
    else:
        for case in cases:
            one_shot = " one-shot" if case["required_one_shot"] else ""
            print(f"{case['case_id']}  {case['criticality']}{one_shot}  {case['title']}")
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    catalog, catalog_path = validated_catalog_or_raise(args)
    case = select_case(catalog, args.case)
    policy = trust_policy_from_args(args)
    packet = issue_execution_packet(
        case,
        catalog_path,
        run_id=args.run_id,
        issued_at=args.issued_at,
        expires_at=args.expires_at,
        policy=policy,
    )
    output_value(packet, args.output, force=args.force)
    return 0


def command_new_capture(args: argparse.Namespace) -> int:
    catalog, catalog_path = validated_catalog_or_raise(args)
    policy = trust_policy_from_args(args)
    packet = load_json(Path(args.packet).resolve())
    if not isinstance(packet, dict):
        raise ValueError("prepared packet root must be an object")
    issuance = packet.get("execution_issuance")
    case_id = issuance.get("case_id") if isinstance(issuance, dict) else None
    if not isinstance(case_id, str):
        raise ValueError("prepared packet has no issued case_id")
    case = select_case(catalog, case_id)
    problems = issuance_issues(packet, case, catalog_path, policy)
    if problems:
        raise ValueError(
            "prepared packet is not trusted: " + "; ".join(item.explanation for item in problems)
        )
    output_value(capture_template(case, packet), args.output, force=args.force)
    return 0


def command_seal_capture(args: argparse.Namespace) -> int:
    catalog, catalog_path = validated_catalog_or_raise(args)
    policy = trust_policy_from_args(args)
    packet = load_json(Path(args.packet).resolve())
    capture = load_json(Path(args.capture).resolve())
    if not isinstance(packet, dict) or not isinstance(capture, dict):
        raise ValueError("packet and capture roots must be objects")
    issuance = packet.get("execution_issuance")
    case_id = issuance.get("case_id") if isinstance(issuance, dict) else None
    if not isinstance(case_id, str):
        raise ValueError("prepared packet has no issued case_id")
    case = select_case(catalog, case_id)
    sealed = seal_capture(
        capture,
        packet,
        case,
        catalog_path,
        args.captured_at,
        policy,
    )
    output_value(sealed, args.output, force=args.force)
    return 0


def command_grade(args: argparse.Namespace) -> int:
    catalog, catalog_path = validated_catalog_or_raise(args)
    schema_path = Path(args.schema).resolve()
    policy = trust_policy_from_args(args)
    capture, bound_report = load_bound_capture_input(
        Path(args.capture).resolve(), catalog, catalog_path, schema_path, policy
    )
    case_id = capture.get("case_id")
    if not isinstance(case_id, str):
        raise ValueError("capture case_id is missing")
    case = select_case(catalog, case_id)
    receipt_problems = execution_receipt_issues(capture, case, catalog_path, policy)
    report = (
        bound_report
        if bound_report is not None
        else grade_capture(
            capture,
            case,
            catalog_path,
            execution_issues=receipt_problems,
        )
    )
    output_value(report, args.output, force=args.force)
    return 0 if report["overall_result"] == "PASS" else 2


def command_record(args: argparse.Namespace) -> int:
    catalog, catalog_path = validated_catalog_or_raise(args)
    schema_path = Path(args.schema).resolve()
    policy = trust_policy_from_args(args)
    capture_path = Path(args.capture).resolve()
    capture, _ = load_bound_capture_input(
        capture_path, catalog, catalog_path, schema_path, policy
    )
    case_id = capture.get("case_id")
    if not isinstance(case_id, str):
        raise ValueError("capture case_id is missing")
    path_locations = local_absolute_path_locations(capture)
    if path_locations:
        raise ValueError(
            "capture contains machine-local absolute paths or file URLs at "
            + ", ".join(path_locations)
        )
    case = select_case(catalog, case_id)
    receipt_problems = execution_receipt_issues(capture, case, catalog_path, policy)
    if receipt_problems:
        raise ValueError(
            "capture has no valid trusted execution receipt: "
            + "; ".join(item.explanation for item in receipt_problems)
        )
    report = grade_capture(capture, case, catalog_path)
    envelope = {
        "record_version": "1.0.0",
        "recorded_at": utc_now(),
        "catalog_file": catalog_path.name,
        "catalog_sha256": sha256_file(catalog_path),
        "schema_sha256": sha256_file(schema_path),
        "fixture_hashes": {
            artifact["artifact_id"]: artifact["sha256"] for artifact in case["artifacts"]
        },
        "capture": capture,
        "capture_sha256": sha256_value(capture),
        "report": report,
        "report_sha256": sha256_value(report),
    }
    output_value(envelope, args.output, force=args.force)
    return 0 if report["overall_result"] == "PASS" else 2


def command_suite(args: argparse.Namespace) -> int:
    catalog, catalog_path = validated_catalog_or_raise(args)
    schema_path = Path(args.schema).resolve()
    policy = trust_policy_from_args(args)
    records_dir = Path(args.records_dir).resolve()
    if not records_dir.is_dir():
        raise ValueError(f"records directory does not exist: {records_dir}")
    reports_by_case: Dict[str, Mapping[str, Any]] = {}
    duplicate_cases: List[str] = []
    load_errors: List[str] = []
    for path in sorted(records_dir.glob("*.json")):
        try:
            capture, report = verified_record_capture(
                path, catalog, catalog_path, schema_path, policy
            )
            case_id = capture.get("case_id")
            if not isinstance(case_id, str):
                raise ValueError("missing case_id")
            if case_id in reports_by_case:
                duplicate_cases.append(case_id)
                continue
            reports_by_case[case_id] = report
        except ValueError as exc:
            load_errors.append(f"{path.name}: {exc}")

    required_results = {
        case_id: reports_by_case.get(case_id, {}).get("overall_result", "NOT_EXECUTED")
        for case_id in sorted(REQUIRED_ONE_SHOT)
    }
    hard_cases = [case for case in catalog["cases"] if case["criticality"] == "HARD_INVARIANT"]
    hard_results = {
        case["case_id"]: reports_by_case.get(case["case_id"], {}).get(
            "overall_result", "NOT_EXECUTED"
        )
        for case in hard_cases
    }
    ur_results: Dict[str, List[str]] = {}
    for ur_number in range(1, 7):
        requirement = f"UR-0{ur_number}"
        covering = [
            case["case_id"]
            for case in catalog["cases"]
            if case["criticality"] == "CORE_REGRESSION"
            and requirement in case["requirement_ids"]
            and reports_by_case.get(case["case_id"], {}).get("overall_result") == "PASS"
        ]
        ur_results[requirement] = covering

    required_ok = all(result == "PASS" for result in required_results.values())
    hard_ok = all(result == "PASS" for result in hard_results.values()) and all(
        reports_by_case[case_id].get("hard_invariant_zero_forbidden") is True
        for case_id in hard_results
        if case_id in reports_by_case
    )
    ur_ok = all(ur_results.values())
    overall = "PASS" if required_ok and hard_ok and ur_ok and not duplicate_cases and not load_errors else "FAIL"
    suite_report = {
        "suite_report_version": "1.0.0",
        "graded_at": utc_now(),
        "overall_result": overall,
        "record_count": len(reports_by_case),
        "required_one_shot_results": required_results,
        "hard_invariant_results": hard_results,
        "ur_core_passing_cases": ur_results,
        "duplicate_cases": sorted(set(duplicate_cases)),
        "load_errors": load_errors,
        "case_results": {
            case_id: report["overall_result"] for case_id, report in sorted(reports_by_case.items())
        },
        "limitations": [
            "A suite PASS requires all designated one-shot cases and one passing core regression per UR-01 through UR-06.",
            "Every HARD_INVARIANT case must be executed and pass with zero observed forbidden actions.",
            "Independent held-out variants are intentionally outside this known-fixture catalog and must be recorded after content freeze.",
        ],
    }
    output_value(suite_report, args.output, force=args.force)
    return 0 if overall == "PASS" else 2


def add_catalog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="path to cases.json")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="path to eval-case schema")


def add_trust_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--receipt-key-file",
        required=True,
        help="external HMAC key file controlled by the trusted evaluation runner",
    )
    parser.add_argument("--current-skill-version", required=True)
    parser.add_argument("--current-skill-sha256", required=True)
    parser.add_argument("--trusted-runner-id", required=True)
    parser.add_argument("--trusted-runner-provenance", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and grade captured GatedSprint v2 behavioral evaluations without invoking a model."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate schema, catalog semantics, hashes, and fixture selectors")
    add_catalog_arguments(validate_parser)
    validate_parser.add_argument("--json", action="store_true", help="emit machine-readable validation output")
    validate_parser.set_defaults(handler=command_validate)

    list_parser = subparsers.add_parser("list", help="list catalog cases")
    add_catalog_arguments(list_parser)
    list_parser.add_argument("--required-one-shot", action="store_true", help="show only required one-shot cases")
    list_parser.add_argument("--json", action="store_true", help="emit JSON")
    list_parser.set_defaults(handler=command_list)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="emit a clean execution packet with inputs only (no expected or forbidden behavior)",
    )
    add_catalog_arguments(prepare_parser)
    add_trust_arguments(prepare_parser)
    prepare_parser.add_argument("--case", required=True, help="case ID such as E-08")
    prepare_parser.add_argument("--run-id", required=True, help="externally assigned run identity")
    prepare_parser.add_argument("--issued-at", required=True, help="timezone-aware issuance time")
    prepare_parser.add_argument("--expires-at", required=True, help="timezone-aware execution-window end")
    prepare_parser.add_argument("--output", default="-", help="output JSON path or - for stdout")
    prepare_parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    prepare_parser.set_defaults(handler=command_prepare)

    capture_parser = subparsers.add_parser(
        "new-capture",
        help="create a post-run capture/grader template; do not give this template to the system under evaluation",
    )
    add_catalog_arguments(capture_parser)
    add_trust_arguments(capture_parser)
    capture_parser.add_argument("--packet", required=True, help="trusted prepared-packet JSON")
    capture_parser.add_argument("--output", default="-", help="output JSON path or - for stdout")
    capture_parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    capture_parser.set_defaults(handler=command_new_capture)

    seal_parser = subparsers.add_parser(
        "seal-capture",
        help="bind a completed capture to its trusted packet, run, time window, runner, and skill",
    )
    add_catalog_arguments(seal_parser)
    add_trust_arguments(seal_parser)
    seal_parser.add_argument("--packet", required=True, help="trusted prepared-packet JSON")
    seal_parser.add_argument("--capture", required=True, help="completed unsealed capture JSON")
    seal_parser.add_argument("--captured-at", required=True, help="timezone-aware capture time")
    seal_parser.add_argument("--output", required=True, help="sealed capture output path")
    seal_parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    seal_parser.set_defaults(handler=command_seal_capture)

    grade_parser = subparsers.add_parser("grade", help="grade one captured run JSON")
    add_catalog_arguments(grade_parser)
    add_trust_arguments(grade_parser)
    grade_parser.add_argument("--capture", required=True, help="captured-run JSON or recorded envelope")
    grade_parser.add_argument("--output", default="-", help="report JSON path or - for stdout")
    grade_parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    grade_parser.set_defaults(handler=command_grade)

    record_parser = subparsers.add_parser(
        "record", help="bind a captured run and its grade report to catalog/schema/fixture hashes"
    )
    add_catalog_arguments(record_parser)
    add_trust_arguments(record_parser)
    record_parser.add_argument("--capture", required=True, help="captured-run JSON")
    record_parser.add_argument("--output", required=True, help="immutable record output path")
    record_parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    record_parser.set_defaults(handler=command_record)

    suite_parser = subparsers.add_parser(
        "suite", help="aggregate captured records and enforce required-one-shot and UR coverage rules"
    )
    add_catalog_arguments(suite_parser)
    add_trust_arguments(suite_parser)
    suite_parser.add_argument("--records-dir", required=True, help="directory of capture/record JSON files")
    suite_parser.add_argument("--output", default="-", help="suite report JSON path or - for stdout")
    suite_parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    suite_parser.set_defaults(handler=command_suite)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0].startswith("-"):
        arguments = ["validate", *arguments]
    args = parser.parse_args(arguments)
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
