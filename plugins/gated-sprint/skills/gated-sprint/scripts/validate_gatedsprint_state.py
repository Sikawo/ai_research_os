#!/usr/bin/env python3
"""Validate GatedSprint v2 state and release sidecars.

The implementation intentionally uses only the Python standard library.  It
validates the repository's JSON Schema subset and then enforces cross-record
invariants that JSON Schema cannot express.

Machine-readable output is written to stdout as one JSON object.  A one-line
human summary is written to stderr.  Exit status is 0 on success, 1 when a
required invariant fails, and 2 for invocation/input errors.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "2.0.0"
BINARY_COMPARISON_CHUNK_SIZE = 1024 * 1024
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _ranges_equal(
    left: Any,
    left_start: int,
    left_end: int,
    right: Any,
    right_start: int,
    right_end: int,
) -> bool:
    """Compare two same-kind unit ranges without materializing either slice."""

    range_length = left_end - left_start
    if range_length != right_end - right_start:
        return False
    if isinstance(left, bytes) and isinstance(right, bytes):
        left_view = memoryview(left)
        right_view = memoryview(right)
        for offset in range(0, range_length, BINARY_COMPARISON_CHUNK_SIZE):
            chunk_end = min(offset + BINARY_COMPARISON_CHUNK_SIZE, range_length)
            if (
                left_view[left_start + offset : left_start + chunk_end]
                != right_view[right_start + offset : right_start + chunk_end]
            ):
                return False
        return True
    return all(
        left[left_start + offset] == right[right_start + offset]
        for offset in range(range_length)
    )


def _range_sha256(units: Any, start: int, end: int) -> str:
    """Hash a text-line or binary-byte range without copying a large binary slice."""

    digest = hashlib.sha256()
    if isinstance(units, bytes):
        view = memoryview(units)
        for offset in range(start, end, BINARY_COMPARISON_CHUNK_SIZE):
            digest.update(view[offset : min(offset + BINARY_COMPARISON_CHUNK_SIZE, end)])
    else:
        for offset in range(start, end):
            digest.update(units[offset].encode("utf-8"))
    return "sha256:" + digest.hexdigest()


ALLOWED_TRANSITIONS = {
    "PROPOSED": {"DISCUSSED", "APPROVED", "HELD", "REJECTED", "SUPERSEDED"},
    "DISCUSSED": {"APPROVED", "HELD", "REJECTED", "SUPERSEDED"},
    "APPROVED": {"AUTHORIZED", "HELD", "REJECTED", "SUPERSEDED"},
    "AUTHORIZED": {"IMPLEMENTED", "HELD", "SUPERSEDED"},
    "IMPLEMENTED": {"VERIFIED", "SUPERSEDED"},
    "VERIFIED": {"SUPERSEDED"},
    "HELD": {"DISCUSSED", "APPROVED", "REJECTED", "SUPERSEDED"},
    "REJECTED": {"SUPERSEDED"},
    "SUPERSEDED": set(),
}

APPROVAL_STATES = {"APPROVED", "AUTHORIZED", "IMPLEMENTED", "VERIFIED"}
AUTHORIZATION_STATES = {"AUTHORIZED", "IMPLEMENTED", "VERIFIED"}
IMPLEMENTED_STATES = {"IMPLEMENTED", "VERIFIED"}
ACTIVE_FOR_CONFLICT = {"AUTHORIZED", "IMPLEMENTED", "VERIFIED"}

RELEASE_GATE_IDS = {
    "scientific_integrity",
    "current_source_authority",
    "motivation_significance",
    "logical_simplicity",
    "voice_tone",
    "salience",
    "visual_coverage",
    "citation_integrity",
    "format_constraints",
    "layout_verification",
    "final_actual_artifact",
    "post_implementation_blind",
    "tired_reader",
}
BASE_GATE_IDS = {"scientific_integrity", "current_source_authority"}

# These fields define the proposal content whose exact wording and rationale the
# user approves. Source bindings, lifecycle state, and implementation results
# are validated separately. Conflict/lock metadata that controls whether the
# proposal may be implemented is folded into the fingerprint when present.
PROPOSAL_PAYLOAD_FIELDS = (
    "decision_id",
    "proposal_revision",
    "run_id",
    "project_id",
    "scope",
    "location",
    "anchor_text",
    "anchor_hash",
    "trigger_provenance",
    "why_now",
    "root_cause",
    "downstream_symptoms",
    "proposed_intervention",
    "protected_intent",
    "reviewer_benefit",
    "lost_nuance_tradeoff",
    "evidence_assumptions",
    "change_risk",
    "domain_risk",
    "specialist_concern",
    "safer_alternative",
    "strategic_necessity",
    "assistant_recommendation",
    "page_figure_format_effect",
)

# This semantic projection contains every source-binding value that can change
# implementation readiness. Provenance-only metadata (event ID, timestamp,
# actor, and explanatory authority text) remains append-only validated but does
# not force a fresh user authorization when the binding semantics are identical.
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

NARRATIVE_HARD_GATE_DOCUMENT_TYPES = {
    "PACKAGE",
    "RESEARCH_STATEMENT",
    "RESEARCH_PLAN",
    "COVER_LETTER",
    "RECOMMENDATION_LETTER",
    "GRANT_NARRATIVE",
    "FELLOWSHIP_NARRATIVE",
}
NARRATIVE_HARD_GATE_IDS = {"motivation_significance", "logical_simplicity"}


@dataclass(frozen=True)
class Issue:
    check_id: str
    severity: str
    affected_decision: str | None
    affected_artifact: str | None
    explanation: str


def _display_decision(decision: dict[str, Any] | tuple[str, int] | None) -> str | None:
    if decision is None:
        return None
    if isinstance(decision, tuple):
        return f"{decision[0]}-r{decision[1]}"
    decision_id = decision.get("decision_id")
    revision = decision.get("proposal_revision")
    if isinstance(decision_id, str) and isinstance(revision, int):
        return f"{decision_id}-r{revision}"
    return str(decision_id) if decision_id is not None else None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or RFC3339_RE.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _timestamp_key(value: Any) -> float:
    parsed = _parse_timestamp(value)
    return parsed.timestamp() if parsed is not None else float("-inf")


def _content_hash(value: Any) -> str:
    """Return the state model's canonical SHA-256 fingerprint for JSON data."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _proposal_payload(decision: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical, approval-bounded proposal payload."""

    payload = {field: decision.get(field) for field in PROPOSAL_PAYLOAD_FIELDS}
    dependencies = sorted(
        (
            {
                "decision_id": reference.get("decision_id"),
                "proposal_revision": reference.get("proposal_revision"),
            }
            for reference in decision.get("dependencies", [])
            if isinstance(reference, dict)
        ),
        key=lambda item: (str(item["decision_id"]), item["proposal_revision"]),
    )
    if dependencies:
        payload["dependencies"] = dependencies
    for field in ("conflicts", "conflict_resolutions", "affected_lock_ids"):
        if decision.get(field):
            payload[field] = decision[field]
    return payload


def _source_binding_authorization_hash(binding: Any) -> str | None:
    """Bind all implementation-controlling source semantics to a USER transition."""

    if not isinstance(binding, dict):
        return None
    return _content_hash(
        {field: binding.get(field) for field in SOURCE_BINDING_AUTHORIZATION_FIELDS}
    )


def _local_fix_authorization_payload(local_fix: Any) -> dict[str, Any] | None:
    """Return the immutable local-fix fields that a user authorizes.

    Candidate hashes and implemented hunk IDs are implementation results and
    therefore do not exist yet when the user authorizes the bounded fix. The
    category, scope, and exact description do exist and must not be mutable
    behind a stable local-fix ID.
    """

    if not isinstance(local_fix, dict):
        return None
    return {
        "local_fix_id": local_fix.get("local_fix_id"),
        "category": local_fix.get("category"),
        "scope": local_fix.get("scope"),
        "description": local_fix.get("description"),
        "source_id": local_fix.get("source_id"),
        "source_fingerprint": local_fix.get("source_fingerprint"),
    }


def _lock_creation_payload(lock: Any) -> dict[str, Any] | None:
    """Return immutable lock fields that the creation event must bind."""

    if not isinstance(lock, dict):
        return None
    return {
        "lock_id": lock.get("lock_id"),
        "type": lock.get("type"),
        "scope_anchor": lock.get("scope_anchor"),
        "reason": lock.get("reason"),
        "creating_authority": lock.get("creating_authority"),
        "source_fingerprint": lock.get("source_fingerprint"),
        "release_condition": lock.get("release_condition"),
        "created_at": lock.get("created_at"),
    }


def _lock_release_payload(lock: Any) -> dict[str, Any] | None:
    """Return release fields that the release event must bind."""

    if not isinstance(lock, dict):
        return None
    return {
        "lock_id": lock.get("lock_id"),
        "released_at": lock.get("released_at"),
        "released_by": lock.get("released_by"),
        "source_fingerprint": lock.get("source_fingerprint"),
    }


def _scope_tokens(value: Any) -> tuple[str, ...]:
    """Return stable Unicode word tokens for conservative scope comparison."""

    if not isinstance(value, str):
        return ()
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(re.findall(r"[^\W_]+", normalized))


def _scope_anchors_overlap(left: Any, right: Any) -> bool:
    """Treat either contiguous token sequence as a conservative parent scope."""

    left_tokens = _scope_tokens(left)
    right_tokens = _scope_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    width = len(shorter)
    return any(longer[index : index + width] == shorter for index in range(len(longer) - width + 1))


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if not ref.startswith("#/"):
        return None
    current: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current if isinstance(current, dict) else None


def _schema_errors(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Validate the JSON Schema features used by the bundled schema."""

    if "$ref" in schema:
        target = _resolve_ref(root, schema["$ref"])
        if target is None:
            return [f"{path}: schema has unresolved reference {schema['$ref']!r}"]
        return _schema_errors(value, target, root, path)

    errors: list[str] = []

    if "allOf" in schema:
        for branch in schema["allOf"]:
            errors.extend(_schema_errors(value, branch, root, path))

    if "anyOf" in schema:
        branches = schema["anyOf"]
        if not any(not _schema_errors(value, branch, root, path) for branch in branches):
            errors.append(f"{path}: does not match any permitted schema")
            return errors

    if "oneOf" in schema:
        matches = sum(not _schema_errors(value, branch, root, path) for branch in schema["oneOf"])
        if matches != 1:
            errors.append(f"{path}: must match exactly one permitted schema (matched {matches})")
            return errors

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not an allowed value")

    expected_type = schema.get("type")
    if expected_type is not None:
        choices = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_json_type_matches(value, choice) for choice in choices):
            errors.append(f"{path}: expected type {' or '.join(choices)}, got {type(value).__name__}")
            return errors

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in properties:
                errors.extend(_schema_errors(item, properties[key], root, child_path))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{child_path}: additional property is not allowed")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(_schema_errors(item, schema["additionalProperties"], root, child_path))
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            errors.append(f"{path}: must contain at least {schema['minProperties']} properties")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: must contain at most {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            canonical = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(canonical) != len(set(canonical)):
                errors.append(f"{path}: items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_schema_errors(item, item_schema, root, f"{path}[{index}]"))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: must contain at least {schema['minLength']} characters")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            errors.append(f"{path}: does not match required pattern {pattern!r}")
        if schema.get("format") == "date-time" and _parse_timestamp(value) is None:
            errors.append(f"{path}: is not an RFC 3339 date-time with a timezone")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: must be at least {schema['minimum']}")

    condition = schema.get("if")
    if isinstance(condition, dict):
        branch_name = "then" if not _schema_errors(value, condition, root, path) else "else"
        branch = schema.get(branch_name)
        if isinstance(branch, dict):
            errors.extend(_schema_errors(value, branch, root, path))

    return errors


def _load_json(path: Path) -> Any:
    def reject_nonstandard_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant {value!r}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key {key!r}")
            result[key] = value
        return result

    def reject_unpaired_surrogates(value: Any, location: str = "$") -> None:
        if isinstance(value, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
                raise ValueError(f"unpaired Unicode surrogate at {location}")
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                reject_unpaired_surrogates(item, f"{location}[{index}]")
            return
        if isinstance(value, dict):
            for key, item in value.items():
                reject_unpaired_surrogates(key, f"{location}.<key>")
                reject_unpaired_surrogates(item, f"{location}.{key}")

    with path.open("r", encoding="utf-8") as handle:
        value = json.load(
            handle,
            parse_constant=reject_nonstandard_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    reject_unpaired_surrogates(value)
    return value


class StateValidator:
    def __init__(
        self,
        state: dict[str, Any],
        baseline: dict[str, Any],
        candidate: dict[str, Any] | None,
        diff_map: dict[str, Any] | None,
        check: str,
        schema: dict[str, Any],
        artifact_root: Path | None,
        source_root: Path | None,
    ) -> None:
        self.state = state
        self.baseline = baseline
        self.candidate = candidate
        self.diff_map = diff_map
        self.check = check
        self.schema = schema
        self.artifact_root = artifact_root
        self.source_root = source_root
        self.issues: list[Issue] = []

        self.sources: dict[str, dict[str, Any]] = {}
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.decisions: dict[tuple[str, int], dict[str, Any]] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self.locks: dict[str, dict[str, Any]] = {}
        self.local_fixes: dict[str, dict[str, Any]] = {}
        self.release_source_bytes: dict[str, bytes] = {}
        self.release_candidate_bytes: bytes | None = None

    def issue(
        self,
        check_id: str,
        explanation: str,
        *,
        severity: str = "ERROR",
        decision: dict[str, Any] | tuple[str, int] | None = None,
        artifact: str | None = None,
    ) -> None:
        self.issues.append(
            Issue(
                check_id=check_id,
                severity=severity,
                affected_decision=_display_decision(decision),
                affected_artifact=artifact,
                explanation=explanation,
            )
        )

    def run(self) -> list[Issue]:
        schema_errors = _schema_errors(self.state, self.schema, self.schema)
        for message in schema_errors[:100]:
            self.issue("STATE.SCHEMA", message)
        if len(schema_errors) > 100:
            self.issue("STATE.SCHEMA", f"{len(schema_errors) - 100} additional schema errors omitted")

        if not isinstance(self.state, dict):
            return self.issues
        # Cross-record checks assume the normative container types.  Stop after
        # structural errors so malformed input produces JSON issues, not a
        # traceback or a cascade of misleading semantic findings.
        if schema_errors:
            return self.issues

        self._build_indexes()
        self._validate_run_and_sources()
        self._validate_baseline_manifest()
        self._validate_decision_revisions()
        self._validate_source_bindings()
        self._validate_event_history()
        self._validate_decision_conditions()
        self._validate_dependencies_and_conflicts()
        self._validate_supersession()
        self._validate_locks()
        self._validate_local_fixes()
        self._validate_artifacts()
        self._validate_attestations()

        if self.check == "ready-to-implement":
            self._validate_ready_to_implement()
        elif self.check == "ready-to-release":
            self._validate_ready_to_release()
        elif self.check == "diagnostic":
            self._validate_diagnostic()
        return self.issues

    def _index_records(self, field: str, key_field: str, target: dict[str, dict[str, Any]]) -> None:
        records = self.state.get(field, [])
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict):
                continue
            key = record.get(key_field)
            if not isinstance(key, str):
                continue
            if key in target:
                self.issue("STATE.ID_UNIQUE", f"duplicate {field} identifier {key!r}")
            else:
                target[key] = record

    def _build_indexes(self) -> None:
        self._index_records("sources", "source_id", self.sources)
        self._index_records("artifacts", "artifact_id", self.artifacts)
        self._index_records("events", "event_id", self.events)
        self._index_records("locks", "lock_id", self.locks)
        self._index_records("local_fix_log", "local_fix_id", self.local_fixes)

        raw_decisions = self.state.get("decisions", [])
        if not isinstance(raw_decisions, list):
            return
        for decision in raw_decisions:
            if not isinstance(decision, dict):
                continue
            decision_id = decision.get("decision_id")
            revision = decision.get("proposal_revision")
            if not isinstance(decision_id, str) or not isinstance(revision, int):
                continue
            key = (decision_id, revision)
            if key in self.decisions:
                self.issue(
                    "STATE.DECISION_UNIQUE",
                    f"duplicate decision key ({decision_id}, {revision})",
                    decision=key,
                )
            else:
                self.decisions[key] = decision

    def _validate_run_and_sources(self) -> None:
        run = self.state.get("run")
        if not isinstance(run, dict):
            return
        if self.state.get("schema_version") != SCHEMA_VERSION:
            self.issue(
                "STATE.VERSION",
                f"schema_version must be {SCHEMA_VERSION}; got {self.state.get('schema_version')!r}",
            )
        if run.get("run_id") is not None:
            for decision in self.decisions.values():
                if decision.get("run_id") != run.get("run_id"):
                    self.issue(
                        "STATE.RUN_BINDING",
                        "decision run_id does not match the enclosing run",
                        decision=decision,
                    )
                if decision.get("project_id") != run.get("project_id"):
                    self.issue(
                        "STATE.RUN_BINDING",
                        "decision project_id does not match the enclosing run",
                        decision=decision,
                    )

        current_ids = run.get("current_source_ids", [])
        if isinstance(current_ids, list):
            for source_id in current_ids:
                source = self.sources.get(source_id)
                if source is None:
                    self.issue("STATE.CURRENT_SOURCE", f"current source {source_id!r} is not registered")
                elif not source.get("is_current"):
                    self.issue("STATE.CURRENT_SOURCE", f"source {source_id!r} is selected current but is_current is false")
        registered_current = {sid for sid, source in self.sources.items() if source.get("is_current")}
        if isinstance(current_ids, list) and registered_current != set(current_ids):
            self.issue(
                "STATE.CURRENT_SOURCE",
                "run.current_source_ids must exactly match sources marked is_current",
            )
        current_artifact_id = run.get("current_artifact_id")
        if current_artifact_id is not None and current_artifact_id not in self.artifacts:
            self.issue(
                "STATE.CURRENT_ARTIFACT",
                f"current artifact {current_artifact_id!r} is not registered",
                artifact=current_artifact_id,
            )
        has_content_authority = any(
            source.get("is_current") and source.get("content_authority")
            for source in self.sources.values()
        )
        authority_not_assessable = any(
            isinstance(requirement, dict)
            and requirement.get("check_id") == "current_source_authority"
            and requirement.get("applicability") == "NOT_ASSESSABLE"
            for requirement in self.state.get("gate_applicability", [])
        )
        if not has_content_authority and not (
            self.check == "diagnostic" and authority_not_assessable
        ):
            self.issue(
                "STATE.CONTENT_AUTHORITY",
                "a current content authority is required, except for a diagnostic scope explicitly marked NOT_ASSESSABLE",
            )

        for source_id, source in self.sources.items():
            if (
                source.get("is_current")
                and source.get("content_authority")
                and source.get("version_designation")
                not in {"EXPLICIT_CURRENT", "SAME_VERSION_CONFIRMED"}
            ):
                self.issue(
                    "STATE.CONTENT_AUTHORITY",
                    f"current content authority {source_id!r} lacks an explicit current/same-version designation",
                )
            if source.get("origin") == "GENERATED_PREVIEW" and source.get("layout_authority"):
                self.issue(
                    "STATE.LAYOUT_AUTHORITY",
                    "a generated preview cannot be authoritative for layout",
                )
            if source.get("layout_authority"):
                if not source.get("is_current"):
                    self.issue(
                        "STATE.LAYOUT_AUTHORITY",
                        f"layout authority {source_id!r} is not registered as current",
                    )
                if source.get("origin") != "USER_SUPPLIED":
                    self.issue(
                        "STATE.LAYOUT_AUTHORITY",
                        f"layout authority {source_id!r} must be user supplied",
                    )
                if (
                    run.get("document_type") != "FIGURE"
                    and source.get("media_type", "").lower() != "application/pdf"
                ):
                    self.issue(
                        "STATE.LAYOUT_AUTHORITY",
                        f"document layout authority {source_id!r} must be a user-supplied PDF, not {source.get('media_type')!r}",
                    )
                if source.get("version_designation") not in {"EXPLICIT_CURRENT", "SAME_VERSION_CONFIRMED"}:
                    self.issue(
                        "STATE.LAYOUT_AUTHORITY",
                        f"layout authority {source_id!r} lacks an explicit current/same-version designation",
                    )
                if not source.get("content_authority") and source.get("equivalence_status") != "SAME_VERSION":
                    self.issue(
                        "STATE.LAYOUT_AUTHORITY",
                        f"layout authority {source_id!r} is not the content authority and is not confirmed content-equivalent",
                    )

    def _validate_baseline_manifest(self) -> None:
        manifest = self.baseline
        if not isinstance(manifest, dict):
            self.issue("STATE.BASELINE", "baseline manifest must be a JSON object")
            return
        if manifest.get("schema_version") != "1.0.0":
            self.issue("STATE.BASELINE", "baseline manifest schema_version must be '1.0.0'")
        if manifest.get("run_id") != self.state.get("run", {}).get("run_id"):
            self.issue("STATE.BASELINE", "baseline manifest run_id does not match state.run.run_id")
        entries = manifest.get("sources")
        if not isinstance(entries, list):
            self.issue("STATE.BASELINE", "baseline manifest must contain a sources array")
            return
        indexed: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("source_id"), str):
                self.issue("STATE.BASELINE", "every baseline source needs a source_id")
                continue
            source_id = entry["source_id"]
            if source_id in indexed:
                self.issue("STATE.BASELINE", f"duplicate baseline source {source_id!r}")
                continue
            indexed[source_id] = entry
            state_source = self.sources.get(source_id)
            if state_source is None:
                self.issue("STATE.BASELINE", f"baseline source {source_id!r} is absent from state.sources")
                continue
            comparable = (
                "path",
                "byte_hash",
                "extracted_text_hash",
                "user_designated_role",
                "content_authority",
                "layout_authority",
                "editable_target",
                "equivalence_status",
                "version_designation",
            )
            for field in comparable:
                if field not in entry:
                    self.issue("STATE.BASELINE", f"baseline source {source_id!r} is missing {field!r}")
                elif entry.get(field) != state_source.get(field):
                    self.issue(
                        "STATE.BASELINE",
                        f"baseline {field} for {source_id!r} does not match the immutable state source register",
                    )
            before_byte = entry.get("byte_hash")
            after_byte = entry.get("observed_after_byte_hash")
            before_text = entry.get("extracted_text_hash")
            after_text = entry.get("observed_after_text_hash")
            if after_byte is not None and after_byte != before_byte:
                self.issue("STATE.BASELINE_IMMUTABLE", f"baseline byte hash changed for {source_id!r}")
            if after_text is not None and after_text != before_text:
                self.issue("STATE.BASELINE_IMMUTABLE", f"baseline extracted-text hash changed for {source_id!r}")
        for source_id in self.sources:
            if source_id not in indexed:
                self.issue("STATE.BASELINE", f"state source {source_id!r} is absent from baseline manifest")

    def _validate_decision_revisions(self) -> None:
        by_id: dict[str, list[int]] = {}
        appearance: dict[str, list[int]] = {}
        raw = self.state.get("decisions", [])
        if not isinstance(raw, list):
            return
        for decision in raw:
            if not isinstance(decision, dict):
                continue
            decision_id = decision.get("decision_id")
            revision = decision.get("proposal_revision")
            if isinstance(decision_id, str) and isinstance(revision, int):
                by_id.setdefault(decision_id, []).append(revision)
                appearance.setdefault(decision_id, []).append(revision)
        for decision_id, revisions in by_id.items():
            sorted_unique = sorted(set(revisions))
            revisions_are_contiguous = bool(sorted_unique) and all(
                revision == expected_revision
                for expected_revision, revision in enumerate(sorted_unique, start=1)
            )
            if not revisions_are_contiguous:
                self.issue(
                    "STATE.REVISION_ORDER",
                    f"{decision_id} revisions must start at 1 and be contiguous; got {sorted_unique}",
                )
            if appearance[decision_id] != sorted(appearance[decision_id]):
                self.issue(
                    "STATE.REVISION_ORDER",
                    f"{decision_id} revisions are not stored in append order",
                )
            fingerprints: set[str] = set()
            for revision in sorted_unique:
                decision = self.decisions.get((decision_id, revision))
                if decision is None:
                    continue
                fingerprint = decision.get("proposal_fingerprint")
                if fingerprint in fingerprints:
                    self.issue(
                        "STATE.REVISION_ORDER",
                        "material proposal revisions must have distinct proposal fingerprints",
                        decision=decision,
                    )
                if isinstance(fingerprint, str):
                    fingerprints.add(fingerprint)
                expected_fingerprint = _content_hash(_proposal_payload(decision))
                if fingerprint != expected_fingerprint:
                    self.issue(
                        "STATE.PROPOSAL_FINGERPRINT",
                        "proposal_fingerprint does not match the canonical approval-bounded proposal payload",
                        decision=decision,
                    )
            for revision in sorted_unique[:-1]:
                decision = self.decisions.get((decision_id, revision))
                if decision and decision.get("decision_state") != "SUPERSEDED":
                    self.issue(
                        "STATE.REVISION_ORDER",
                        "a non-latest proposal revision must be SUPERSEDED",
                        decision=decision,
                    )
            for revision in sorted_unique:
                decision = self.decisions.get((decision_id, revision))
                if decision is None:
                    continue
                links = decision.get("supersession_links", [])
                if revision > 1 and not any(
                    isinstance(link, dict)
                    and link.get("relation") == "SUPERSEDES"
                    and self._resolve_ref(link) == (decision_id, revision - 1)
                    for link in links
                ):
                    self.issue(
                        "STATE.SUPERSESSION",
                        f"revision {revision} must explicitly SUPERSEDE revision {revision - 1}",
                        decision=decision,
                    )
                if revision < max(sorted_unique) and not any(
                    isinstance(link, dict)
                    and link.get("relation") == "SUPERSEDED_BY"
                    and self._resolve_ref(link) == (decision_id, revision + 1)
                    for link in links
                ):
                    self.issue(
                        "STATE.SUPERSESSION",
                        f"revision {revision} must explicitly identify revision {revision + 1} as SUPERSEDED_BY",
                        decision=decision,
                    )

    def _source_matches_fingerprint(self, source_id: Any, fingerprint: Any) -> bool:
        source = self.sources.get(source_id) if isinstance(source_id, str) else None
        if source is None or not isinstance(fingerprint, str):
            return False
        return fingerprint in {source.get("byte_hash"), source.get("extracted_text_hash")}

    def _validate_source_bindings(self) -> None:
        current_ids = set(self.state.get("run", {}).get("current_source_ids", []))
        event_positions = {
            event.get("event_id"): position
            for position, event in enumerate(self.state.get("events", []))
            if isinstance(event, dict) and isinstance(event.get("event_id"), str)
        }
        for decision in self.decisions.values():
            bindings = decision.get("source_bindings")
            if not isinstance(bindings, list) or not bindings:
                continue
            first = bindings[0]
            if not isinstance(first, dict) or first.get("binding_type") != "INITIAL":
                self.issue("STATE.SOURCE_BINDING", "first source binding must be INITIAL", decision=decision)
                continue
            if first.get("source_id") != decision.get("source_id") or first.get("source_fingerprint") != decision.get("source_fingerprint"):
                self.issue(
                    "STATE.SOURCE_BINDING",
                    "initial source binding must preserve the decision's original source ID and fingerprint",
                    decision=decision,
                )
            if first.get("new_anchor_hash") != decision.get("anchor_hash"):
                self.issue(
                    "STATE.SOURCE_BINDING",
                    "INITIAL binding anchor hash must match the decision anchor hash",
                    decision=decision,
                )
            initial_event = self.events.get(first.get("event_id"))
            if (
                initial_event is None
                or initial_event.get("event_type") != "DECISION_PROPOSED"
                or initial_event.get("decision_id") != decision.get("decision_id")
                or initial_event.get("proposal_revision") != decision.get("proposal_revision")
                or initial_event.get("proposal_fingerprint") != decision.get("proposal_fingerprint")
                or initial_event.get("source_id") != first.get("source_id")
                or initial_event.get("source_fingerprint") != first.get("source_fingerprint")
                or initial_event.get("timestamp") != first.get("timestamp")
                or initial_event.get("actor") != first.get("actor")
            ):
                self.issue(
                    "STATE.SOURCE_BINDING",
                    "INITIAL binding lacks a matching DECISION_PROPOSED event",
                    decision=decision,
                )
            prior_time: datetime | None = None
            prior_binding_event_position: int | None = None
            prior = None
            expected_protected_intent_hash = _content_hash(decision.get("protected_intent"))
            dependency_payload = sorted(
                (
                    {
                        "decision_id": reference.get("decision_id"),
                        "proposal_revision": reference.get("proposal_revision"),
                    }
                    for reference in decision.get("dependencies", [])
                    if isinstance(reference, dict)
                ),
                key=lambda item: (str(item["decision_id"]), item["proposal_revision"]),
            )
            expected_dependency_set_hash = _content_hash(dependency_payload)
            for index, binding in enumerate(bindings):
                if not isinstance(binding, dict):
                    continue
                timestamp = _parse_timestamp(binding.get("timestamp"))
                if timestamp is not None and prior_time is not None and timestamp < prior_time:
                    self.issue(
                        "STATE.SOURCE_BINDING",
                        "source bindings are not in append-only timestamp order",
                        decision=decision,
                    )
                if timestamp is not None:
                    prior_time = timestamp
                binding_event_position = event_positions.get(binding.get("event_id"))
                if (
                    binding_event_position is not None
                    and prior_binding_event_position is not None
                    and binding_event_position <= prior_binding_event_position
                ):
                    self.issue(
                        "STATE.SOURCE_BINDING",
                        "source-binding events must appear in the same strict order as the append-only binding array",
                        decision=decision,
                    )
                if binding_event_position is not None:
                    prior_binding_event_position = binding_event_position
                if binding.get("proposal_fingerprint") != decision.get("proposal_fingerprint"):
                    self.issue(
                        "STATE.SOURCE_BINDING",
                        "source binding proposal fingerprint does not match this proposal revision",
                        decision=decision,
                    )
                if binding.get("protected_intent_hash") != expected_protected_intent_hash:
                    self.issue(
                        "STATE.SOURCE_BINDING",
                        "source binding protected-intent hash does not match the canonical decision value",
                        decision=decision,
                    )
                if binding.get("dependency_set_hash") != expected_dependency_set_hash:
                    self.issue(
                        "STATE.SOURCE_BINDING",
                        "source binding dependency-set hash does not match the canonical dependency references",
                        decision=decision,
                    )
                if not self._source_matches_fingerprint(binding.get("source_id"), binding.get("source_fingerprint")):
                    self.issue(
                        "STATE.SOURCE_FINGERPRINT",
                        f"binding {index} does not match the registered source fingerprint",
                        decision=decision,
                    )
                if index == 0:
                    if binding.get("comparison_result") != "INITIAL":
                        self.issue(
                            "STATE.SOURCE_BINDING",
                            "INITIAL binding must have comparison_result INITIAL",
                            decision=decision,
                        )
                    if binding.get("old_source_id") is not None or binding.get("old_source_fingerprint") is not None:
                        self.issue(
                            "STATE.SOURCE_BINDING",
                            "INITIAL binding cannot identify an old source",
                            decision=decision,
                        )
                else:
                    if binding.get("binding_type") != "SOURCE_REVALIDATED":
                        self.issue(
                            "STATE.SOURCE_BINDING",
                            "all bindings after the initial binding must be SOURCE_REVALIDATED",
                            decision=decision,
                        )
                    if binding.get("comparison_result") == "INITIAL":
                        self.issue(
                            "STATE.SOURCE_REVALIDATION",
                            "only the first source binding may use comparison_result INITIAL",
                            decision=decision,
                        )
                    if prior is not None and (
                        binding.get("old_source_id") != prior.get("source_id")
                        or binding.get("old_source_fingerprint") != prior.get("source_fingerprint")
                    ):
                        self.issue(
                            "STATE.SOURCE_BINDING",
                            "SOURCE_REVALIDATED binding does not link to the immediately preceding binding",
                            decision=decision,
                        )
                    if prior is not None and binding.get("old_anchor_hash") != prior.get(
                        "new_anchor_hash"
                    ):
                        self.issue(
                            "STATE.SOURCE_BINDING",
                            "SOURCE_REVALIDATED old anchor does not match the immediately preceding binding's scoped anchor",
                            decision=decision,
                        )
                    event = self.events.get(binding.get("event_id"))
                    details = event.get("details", {}) if isinstance(event, dict) else {}
                    expected_details = {
                        "old_source_id": binding.get("old_source_id"),
                        "old_source_fingerprint": binding.get("old_source_fingerprint"),
                        "new_source_id": binding.get("source_id"),
                        "new_source_fingerprint": binding.get("source_fingerprint"),
                        "old_anchor_hash": binding.get("old_anchor_hash"),
                        "new_anchor_hash": binding.get("new_anchor_hash"),
                        "protected_intent_hash": binding.get("protected_intent_hash"),
                        "dependency_set_hash": binding.get("dependency_set_hash"),
                        "comparison_result": binding.get("comparison_result"),
                    }
                    if (
                        event is None
                        or event.get("event_type") != "SOURCE_REVALIDATED"
                        or event.get("decision_id") != decision.get("decision_id")
                        or event.get("proposal_revision") != decision.get("proposal_revision")
                        or event.get("proposal_fingerprint") != decision.get("proposal_fingerprint")
                        or event.get("source_id") != binding.get("source_id")
                        or event.get("source_fingerprint") != binding.get("source_fingerprint")
                        or event.get("timestamp") != binding.get("timestamp")
                        or event.get("actor") != binding.get("actor")
                        or any(details.get(key) != value for key, value in expected_details.items())
                    ):
                        self.issue(
                            "STATE.SOURCE_REVALIDATION",
                            "SOURCE_REVALIDATED binding lacks a matching append-only event",
                            decision=decision,
                        )
                    if binding.get("comparison_result") == "UNCHANGED" and prior is not None:
                        old_anchor = binding.get("old_anchor_hash")
                        new_anchor = binding.get("new_anchor_hash")
                        if old_anchor != new_anchor:
                            self.issue(
                                "STATE.SOURCE_REVALIDATION",
                                "UNCHANGED carry-forward cannot use different scoped anchor hashes",
                                decision=decision,
                            )
                        if binding.get("protected_intent_hash") != prior.get("protected_intent_hash"):
                            self.issue(
                                "STATE.SOURCE_REVALIDATION",
                                "UNCHANGED carry-forward changed the protected-intent fingerprint",
                                decision=decision,
                            )
                        if binding.get("dependency_set_hash") != prior.get("dependency_set_hash"):
                            self.issue(
                                "STATE.SOURCE_REVALIDATION",
                                "UNCHANGED carry-forward changed the dependency-set fingerprint",
                                decision=decision,
                            )
                prior = binding

            latest = bindings[-1]
            if isinstance(latest, dict):
                impact = decision.get("source_impact")
                invalidating_bindings = [
                    binding
                    for binding in bindings
                    if isinstance(binding, dict)
                    and binding.get("comparison_result")
                    in {"REVALIDATION_REQUIRED", "OBSOLETE"}
                ]
                if invalidating_bindings:
                    required_invalidated_impact = (
                        "OBSOLETE"
                        if any(
                            binding.get("comparison_result") == "OBSOLETE"
                            for binding in invalidating_bindings
                        )
                        else "REVALIDATION_REQUIRED"
                    )
                    if impact != required_invalidated_impact:
                        self.issue(
                            "STATE.SOURCE_REVALIDATION",
                            f"a material source finding permanently requires source_impact {required_invalidated_impact} for this proposal revision",
                            decision=decision,
                        )
                    invalidating_positions = [
                        event_positions.get(binding.get("event_id"), -1)
                        for binding in invalidating_bindings
                    ]
                    for event in self._events_for_decision(decision):
                        event_position = event_positions.get(event.get("event_id"), -1)
                        if event.get("new_state") in APPROVAL_STATES and any(
                            invalidating_position < event_position
                            for invalidating_position in invalidating_positions
                        ):
                            self.issue(
                                "STATE.SOURCE_REVALIDATION",
                                "a proposal revision cannot be approved or advanced after a material source finding; create and approve a new revision",
                                decision=decision,
                            )
                if impact in {"CURRENT", "UNCHANGED"} and latest.get("source_id") not in current_ids:
                    self.issue(
                        "STATE.SOURCE_IMPACT",
                        "CURRENT/UNCHANGED decision is not bound to a current authoritative source",
                        decision=decision,
                    )
                latest_source = self.sources.get(latest.get("source_id"))
                if (
                    impact in {"CURRENT", "UNCHANGED"}
                    and decision.get("decision_state") in APPROVAL_STATES
                    and (latest_source is None or not latest_source.get("content_authority"))
                ):
                    self.issue(
                        "STATE.SOURCE_IMPACT",
                        "CURRENT/UNCHANGED decision must bind to a content-authority source",
                        decision=decision,
                    )
                if impact == "CURRENT" and latest.get("source_id") != decision.get("source_id"):
                    self.issue(
                        "STATE.SOURCE_IMPACT",
                        "a decision carried to a different source must use source_impact UNCHANGED after revalidation",
                        decision=decision,
                    )
                if impact == "UNCHANGED" and (
                    len(bindings) < 2 or latest.get("comparison_result") != "UNCHANGED"
                ):
                    self.issue(
                        "STATE.SOURCE_REVALIDATION",
                        "source_impact UNCHANGED requires a later SOURCE_REVALIDATED binding with comparison_result UNCHANGED",
                        decision=decision,
                    )
                if impact in {"CURRENT", "UNCHANGED"} and latest.get(
                    "new_anchor_hash"
                ) != decision.get("anchor_hash"):
                    self.issue(
                        "STATE.SOURCE_REVALIDATION",
                        "current decision anchor hash does not match its latest valid source binding",
                        decision=decision,
                    )
                expected_impact = {
                    "REVALIDATION_REQUIRED": "REVALIDATION_REQUIRED",
                    "OBSOLETE": "OBSOLETE",
                }.get(latest.get("comparison_result"))
                if expected_impact is not None and impact != expected_impact:
                    self.issue(
                        "STATE.SOURCE_REVALIDATION",
                        f"comparison_result {latest.get('comparison_result')} requires source_impact {expected_impact}",
                        decision=decision,
                    )

                approval_events = [
                    event
                    for event in self.events.values()
                    if event.get("decision_id") == decision.get("decision_id")
                    and event.get("proposal_revision") == decision.get("proposal_revision")
                    and event.get("new_state") == "APPROVED"
                ]
                if decision.get("decision_state") in APPROVAL_STATES and approval_events:
                    latest_approval_position = max(
                        event_positions.get(event.get("event_id"), -1)
                        for event in approval_events
                    )
                    invalidating_positions = [
                        event_positions.get(binding.get("event_id"), -1)
                        for binding in bindings
                        if isinstance(binding, dict)
                        and binding.get("comparison_result")
                        in {"REVALIDATION_REQUIRED", "OBSOLETE"}
                    ]
                    if any(
                        invalidating_position > latest_approval_position
                        for invalidating_position in invalidating_positions
                    ):
                        self.issue(
                            "STATE.SOURCE_REVALIDATION",
                            "approval predates a material source-change finding; a later UNCHANGED hop cannot restore that approval",
                            decision=decision,
                        )
                if (
                    latest.get("source_id") != decision.get("source_id")
                    and decision.get("decision_state") in APPROVAL_STATES
                    and not any(event.get("source_fingerprint") == latest.get("source_fingerprint") for event in approval_events)
                    and latest.get("comparison_result") != "UNCHANGED"
                ):
                    self.issue(
                        "STATE.SOURCE_REVALIDATION",
                        "approval cannot carry to a new source without an UNCHANGED SOURCE_REVALIDATED binding",
                        decision=decision,
                    )

    def _events_for_decision(self, decision: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            event
            for event in self.state.get("events", [])
            if isinstance(event, dict)
            and event.get("decision_id") == decision.get("decision_id")
            and event.get("proposal_revision") == decision.get("proposal_revision")
        ]

    def _validate_event_history(self) -> None:
        raw_events = self.state.get("events", [])
        if not isinstance(raw_events, list):
            return
        event_positions = {
            event.get("event_id"): index
            for index, event in enumerate(raw_events)
            if isinstance(event, dict) and isinstance(event.get("event_id"), str)
        }
        prior_timestamp: datetime | None = None
        for event_index, event in enumerate(raw_events):
            if not isinstance(event, dict):
                continue
            timestamp = _parse_timestamp(event.get("timestamp"))
            if timestamp is not None and prior_timestamp is not None and timestamp < prior_timestamp:
                self.issue("STATE.EVENT_ORDER", "events are not stored in append-only timestamp order")
            if timestamp is not None:
                prior_timestamp = timestamp
            decision_id = event.get("decision_id")
            revision = event.get("proposal_revision")
            if decision_id is not None or revision is not None:
                if not isinstance(decision_id, str) or not isinstance(revision, int) or (decision_id, revision) not in self.decisions:
                    self.issue(
                        "STATE.EVENT_REFERENCE",
                        f"event {event.get('event_id')!r} refers to an unknown decision revision",
                    )
            event_type = event.get("event_type")
            decision_event_types = {
                "DECISION_PROPOSED",
                "DECISION_STATE_CHANGED",
                "SUPPORT_STATUS_CHANGED",
                "SOURCE_REVALIDATED",
                "SOURCE_IMPACT_CHANGED",
                "DECISION_IMPLEMENTED",
                "DECISION_VERIFIED",
                "TRADEOFF_ACCEPTED",
                "CONFLICT_RESOLUTION_ACCEPTED",
            }
            if event_type in decision_event_types and (
                not isinstance(decision_id, str)
                or not isinstance(revision, int)
                or isinstance(revision, bool)
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    f"{event_type} requires a decision ID and integer proposal revision",
                )
            if event_type not in decision_event_types and (
                decision_id is not None or revision is not None
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    f"{event_type} cannot also be recorded as a decision event",
                )
            state_fields_present = event.get("prior_state") is not None or event.get("new_state") is not None
            support_fields_present = (
                event.get("prior_support_status") is not None
                or event.get("new_support_status") is not None
            )
            impact_fields_present = (
                event.get("prior_source_impact") is not None
                or event.get("new_source_impact") is not None
            )
            if event_type == "DECISION_PROPOSED" and (
                event.get("prior_state") is not None
                or event.get("new_state") != "PROPOSED"
                or event.get("prior_support_status") is not None
                or event.get("new_support_status") is None
                or event.get("prior_source_impact") is not None
                or event.get("new_source_impact") is None
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "DECISION_PROPOSED must initialize state, support status, and source impact",
                )
            artifact_id = event.get("artifact_id")
            if artifact_id is not None and artifact_id not in self.artifacts:
                self.issue(
                    "STATE.EVENT_REFERENCE",
                    f"event {event.get('event_id')!r} refers to unknown artifact {artifact_id!r}",
                    artifact=artifact_id,
                )
            if event_type in {
                "ARTIFACT_CREATED",
                "ARTIFACT_MODIFIED",
                "ARTIFACT_VERIFIED",
                "ARTIFACT_INVALIDATED",
            } and (artifact_id is None or event.get("artifact_hash") is None):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    f"{event_type} requires an artifact ID and hash",
                    artifact=artifact_id,
                )
            if event_type in {
                "ARTIFACT_CREATED",
                "ARTIFACT_MODIFIED",
                "ARTIFACT_VERIFIED",
                "ARTIFACT_INVALIDATED",
            } and artifact_id in self.artifacts:
                artifact = self.artifacts[artifact_id]
                if event.get("artifact_hash") != artifact.get("candidate_hash"):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        f"{event_type} hash does not match the registered exact candidate",
                        artifact=artifact_id,
                    )
                if event_type == "ARTIFACT_CREATED" and event.get("timestamp") != artifact.get(
                    "created_at"
                ):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "ARTIFACT_CREATED timestamp does not match the registered candidate creation time",
                        artifact=artifact_id,
                    )
                if event_type == "ARTIFACT_VERIFIED":
                    verification = artifact.get("verification")
                    if (
                        artifact.get("artifact_status") != "VERIFIED"
                        or not isinstance(verification, dict)
                        or event.get("timestamp") != verification.get("completed_at")
                        or event.get("actor") != verification.get("actor")
                    ):
                        self.issue(
                            "STATE.ARTIFACT_BINDING",
                            "ARTIFACT_VERIFIED event does not match the registered final verification record",
                            artifact=artifact_id,
                        )
            if event_type != "DECISION_PROPOSED":
                if event_type != "SUPPORT_STATUS_CHANGED" and support_fields_present:
                    self.issue(
                        "STATE.EVENT_CONTRACT",
                        f"{event_type} cannot also change support status",
                    )
                if event_type not in {"SOURCE_REVALIDATED", "SOURCE_IMPACT_CHANGED"} and impact_fields_present:
                    self.issue(
                        "STATE.EVENT_CONTRACT",
                        f"{event_type} cannot also change source impact",
                    )
                if event_type not in {
                    "DECISION_STATE_CHANGED",
                    "DECISION_IMPLEMENTED",
                    "DECISION_VERIFIED",
                } and state_fields_present:
                    self.issue(
                        "STATE.EVENT_CONTRACT",
                        f"{event_type} cannot also change decision state",
                    )
            if event_type == "DECISION_STATE_CHANGED" and (
                event.get("prior_state") is None or event.get("new_state") is None
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "DECISION_STATE_CHANGED requires prior_state and new_state",
                )
            if event.get("new_state") == "IMPLEMENTED" and event_type != "DECISION_IMPLEMENTED":
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "the IMPLEMENTED transition must use event_type DECISION_IMPLEMENTED",
                )
            if event.get("new_state") == "VERIFIED" and event_type != "DECISION_VERIFIED":
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "the VERIFIED transition must use event_type DECISION_VERIFIED",
                )
            if event_type == "SUPPORT_STATUS_CHANGED" and (
                event.get("prior_support_status") is None or event.get("new_support_status") is None
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "SUPPORT_STATUS_CHANGED requires prior and new support statuses",
                )
            if event_type == "SUPPORT_STATUS_CHANGED" and event.get("authority_kind") not in {
                "USER",
                "REVIEWER",
                "EXTERNAL_EVIDENCE",
            }:
                self.issue(
                    "STATE.EVENT_AUTHORITY",
                    "support confirmation/correction requires user, reviewer, or external-evidence authority",
                )
            if (
                event_type == "SUPPORT_STATUS_CHANGED"
                and event.get("prior_support_status") in {"NEEDS_CONFIRMATION", "BLOCKED"}
                and event.get("new_support_status") == "SUPPORTED"
                and not event.get("details", {}).get("evidence")
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "a support transition to SUPPORTED requires the confirming/corrective evidence in event details",
                )
            if event_type == "TRADEOFF_ACCEPTED":
                decision = self.decisions.get((decision_id, revision))
                accepted = decision.get("accepted_tradeoff") if isinstance(decision, dict) else None
                if (
                    event.get("authority_kind") != "USER"
                    or not isinstance(accepted, dict)
                    or event.get("actor") != accepted.get("accepted_by")
                    or event.get("timestamp") != accepted.get("timestamp")
                    or event.get("proposal_fingerprint") != accepted.get("proposal_fingerprint")
                    or event.get("source_fingerprint") != accepted.get("source_fingerprint")
                    or event.get("details", {}).get("accepted_tradeoff_hash")
                    != _content_hash(accepted)
                ):
                    self.issue(
                        "STATE.ACCEPTED_TRADEOFF",
                        "TRADEOFF_ACCEPTED must be an exact USER-authority event bound to the accepted tradeoff",
                        decision=decision,
                    )
            if event_type == "CONFLICT_RESOLUTION_ACCEPTED":
                decision = self.decisions.get((decision_id, revision))
                matching_resolutions = [
                    resolution
                    for resolution in decision.get("conflict_resolutions", [])
                    if isinstance(resolution, dict)
                    and resolution.get("resolution") == "BOTH_COMPATIBLE"
                    and event.get("details", {}).get("conflict_resolution_hash")
                    == _content_hash(resolution)
                ] if isinstance(decision, dict) else []
                if (
                    event.get("authority_kind") != "USER"
                    or len(matching_resolutions) != 1
                ):
                    self.issue(
                        "STATE.CONFLICT_AUTHORITY",
                        "CONFLICT_RESOLUTION_ACCEPTED must be a USER-authority event bound to one BOTH_COMPATIBLE resolution hash",
                        decision=decision,
                    )
            if event_type in {"SOURCE_REVALIDATED", "SOURCE_IMPACT_CHANGED"} and (
                event.get("prior_source_impact") is None or event.get("new_source_impact") is None
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    f"{event_type} requires prior and new source-impact values",
                )
            if event_type == "DECISION_IMPLEMENTED" and event.get("new_state") != "IMPLEMENTED":
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "DECISION_IMPLEMENTED must transition to IMPLEMENTED",
                )
            if event_type in {"DECISION_IMPLEMENTED", "DECISION_VERIFIED"} and (
                event.get("artifact_id") is None or event.get("artifact_hash") is None
            ):
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    f"{event_type} requires an exact artifact ID and hash",
                    artifact=event.get("artifact_id"),
                )
            if event_type == "DECISION_VERIFIED" and event.get("new_state") != "VERIFIED":
                self.issue(
                    "STATE.EVENT_CONTRACT",
                    "DECISION_VERIFIED must transition to VERIFIED",
                )

        for decision in self.decisions.values():
            history = self._events_for_decision(decision)
            state_events = [event for event in history if event.get("new_state") is not None]
            current_state: str | None = None
            support_status: str | None = None
            source_impact: str | None = None
            for event in history:
                event_index = event_positions.get(event.get("event_id"), -1)
                if event.get("new_support_status") is not None:
                    if support_status is not None and event.get("prior_support_status") != support_status:
                        self.issue(
                            "STATE.EVENT_CHAIN",
                            "support-status event prior value does not match event history",
                            decision=decision,
                        )
                    support_status = event.get("new_support_status")
                if event.get("new_source_impact") is not None:
                    if source_impact is not None and event.get("prior_source_impact") != source_impact:
                        self.issue(
                            "STATE.EVENT_CHAIN",
                            "source-impact event prior value does not match event history",
                            decision=decision,
                        )
                    source_impact = event.get("new_source_impact")
                if event.get("proposal_fingerprint") != decision.get("proposal_fingerprint"):
                    self.issue(
                        "STATE.EVENT_BINDING",
                        "decision event is not bound to the current proposal fingerprint",
                        decision=decision,
                    )
                active_bindings = [
                    (event_positions.get(binding.get("event_id"), -1), binding_index, binding)
                    for binding_index, binding in enumerate(decision.get("source_bindings", []))
                    if isinstance(binding, dict)
                    and event_positions.get(binding.get("event_id"), -1) <= event_index
                ]
                active_binding = (
                    max(active_bindings, key=lambda item: (item[0], item[1]))[2]
                    if active_bindings
                    else None
                )
                if active_binding is None or (
                    active_binding.get("source_id") != event.get("source_id")
                    or active_binding.get("source_fingerprint")
                    != event.get("source_fingerprint")
                ):
                    self.issue(
                        "STATE.EVENT_BINDING",
                        "decision event is not bound to the latest source binding active at that event",
                        decision=decision,
                    )
                next_state = event.get("new_state")
                if next_state is None:
                    continue
                prior_state = event.get("prior_state")
                if current_state is None:
                    if prior_state is not None or next_state != "PROPOSED":
                        self.issue(
                            "STATE.TRANSITION",
                            "the first state event must record null -> PROPOSED",
                            decision=decision,
                        )
                    current_state = next_state
                else:
                    if prior_state != current_state:
                        self.issue(
                            "STATE.EVENT_CHAIN",
                            f"event prior_state {prior_state!r} does not match accumulated state {current_state!r}",
                            decision=decision,
                        )
                    if next_state not in ALLOWED_TRANSITIONS.get(current_state, set()):
                        self.issue(
                            "STATE.TRANSITION",
                            f"illegal decision transition {current_state} -> {next_state}",
                            decision=decision,
                        )
                    current_state = next_state
                if next_state in APPROVAL_STATES and (support_status or decision.get("support_status")) != "SUPPORTED":
                    self.issue(
                        "STATE.SUPPORT",
                        f"transition to {next_state} occurred without support_status SUPPORTED",
                        decision=decision,
                    )
                if next_state in {"APPROVED", "AUTHORIZED"} and event.get("authority_kind") != "USER":
                    self.issue(
                        "STATE.EVENT_AUTHORITY",
                        f"transition to {next_state} requires explicit USER authority",
                        decision=decision,
                    )
                if next_state in {"APPROVED", "AUTHORIZED"} and event.get("details", {}).get(
                    "source_binding_hash"
                ) != _source_binding_authorization_hash(active_binding):
                    self.issue(
                        "STATE.AUTHORIZATION_BINDING",
                        f"transition to {next_state} is not bound to the complete source binding active at that event",
                        decision=decision,
                    )
                if next_state in AUTHORIZATION_STATES and (source_impact or decision.get("source_impact")) in {
                    "REVALIDATION_REQUIRED",
                    "OBSOLETE",
                }:
                    self.issue(
                        "STATE.SOURCE_IMPACT",
                        f"transition to {next_state} occurred while source revalidation/obsolescence blocked action",
                        decision=decision,
                    )
                if next_state == "IMPLEMENTED":
                    implementation = decision.get("implementation_result")
                    if not isinstance(implementation, dict) or (
                        event.get("artifact_id") != implementation.get("artifact_id")
                        or event.get("artifact_hash") != implementation.get("candidate_hash")
                        or event.get("timestamp") != implementation.get("implemented_at")
                        or event.get("actor") != implementation.get("actor")
                    ):
                        self.issue(
                            "STATE.EVENT_BINDING",
                            "IMPLEMENTED event is not bound to the implementation result's exact artifact",
                            decision=decision,
                            artifact=event.get("artifact_id"),
                        )
                if next_state == "VERIFIED":
                    verification = decision.get("verification_result")
                    if not isinstance(verification, dict) or (
                        event.get("artifact_id") != verification.get("artifact_id")
                        or event.get("artifact_hash") != verification.get("candidate_hash")
                        or event.get("timestamp") != verification.get("verified_at")
                        or event.get("actor") != verification.get("actor")
                    ):
                        self.issue(
                            "STATE.EVENT_BINDING",
                            "VERIFIED event is not bound to the verification result's exact artifact",
                            decision=decision,
                            artifact=event.get("artifact_id"),
                        )
            if not state_events:
                self.issue("STATE.EVENT_CHAIN", "decision has no state history", decision=decision)
            elif current_state != decision.get("decision_state"):
                self.issue(
                    "STATE.EVENT_CHAIN",
                    f"last event state {current_state!r} does not match decision_state {decision.get('decision_state')!r}",
                    decision=decision,
                )
            if support_status is not None and support_status != decision.get("support_status"):
                self.issue(
                    "STATE.EVENT_CHAIN",
                    "last support-status event does not match the decision record",
                    decision=decision,
                )
            if source_impact is not None and source_impact != decision.get("source_impact"):
                self.issue(
                    "STATE.EVENT_CHAIN",
                    "last source-impact event does not match the decision record",
                    decision=decision,
                )

    def _has_transition(
        self,
        decision: dict[str, Any],
        state: str,
        *,
        current_source: bool = False,
    ) -> bool:
        latest_binding = decision.get("source_bindings", [{}])[-1]
        for event in self._events_for_decision(decision):
            if event.get("new_state") != state:
                continue
            if event.get("proposal_fingerprint") != decision.get("proposal_fingerprint"):
                continue
            if current_source and (
                event.get("source_id") != latest_binding.get("source_id")
                or event.get("source_fingerprint") != latest_binding.get("source_fingerprint")
                or event.get("details", {}).get("source_binding_hash")
                != _source_binding_authorization_hash(latest_binding)
            ):
                continue
            return True
        return False

    def _validate_decision_conditions(self) -> None:
        for decision in self.decisions.values():
            support = decision.get("support_status")
            state = decision.get("decision_state")
            impact = decision.get("source_impact")
            if support == "BLOCKED":
                if not decision.get("blocking_reason") or not decision.get("unblock_condition"):
                    self.issue(
                        "STATE.SUPPORT",
                        "BLOCKED requires a blocking reason and unblock condition",
                        decision=decision,
                    )
            elif support == "NEEDS_CONFIRMATION":
                if not decision.get("confirmation_requirement"):
                    self.issue(
                        "STATE.SUPPORT",
                        "NEEDS_CONFIRMATION requires a confirmation requirement",
                        decision=decision,
                    )
            if support in {"BLOCKED", "NEEDS_CONFIRMATION"} and state in APPROVAL_STATES:
                self.issue(
                    "STATE.SUPPORT",
                    f"{support} decision cannot be {state}; confirmation/evidence must make it SUPPORTED first",
                    decision=decision,
                )
            if impact in {"REVALIDATION_REQUIRED", "OBSOLETE"} and state in AUTHORIZATION_STATES:
                self.issue(
                    "STATE.SOURCE_IMPACT",
                    f"source_impact {impact} prevents state {state}",
                    decision=decision,
                )
            if state in APPROVAL_STATES and not self._has_transition(decision, "APPROVED"):
                self.issue(
                    "STATE.AUTHORIZATION",
                    "approved-or-later decision lacks a recorded APPROVED event",
                    decision=decision,
                )
            if state in AUTHORIZATION_STATES and not self._has_transition(
                decision, "AUTHORIZED", current_source=True
            ):
                self.issue(
                    "STATE.AUTHORIZATION",
                    "authorized-or-later decision lacks an AUTHORIZED event bound to the current proposal and source fingerprints",
                    decision=decision,
                )
            if state in IMPLEMENTED_STATES and not self._has_transition(decision, "IMPLEMENTED"):
                self.issue(
                    "STATE.IMPLEMENTATION",
                    "implemented-or-later decision lacks an IMPLEMENTED event",
                    decision=decision,
                )
            if state == "VERIFIED" and not self._has_transition(decision, "VERIFIED"):
                self.issue(
                    "STATE.VERIFICATION",
                    "VERIFIED decision lacks a verification event",
                    decision=decision,
                )

            if decision.get("domain_risk") == "SPECIALIST_REVIEW_REQUIRED":
                if not decision.get("specialist_concern") or not decision.get("safer_alternative"):
                    self.issue(
                        "STATE.DOMAIN_RISK",
                        "SPECIALIST_REVIEW_REQUIRED needs both a specialist concern and a safer alternative",
                        decision=decision,
                    )

            accepted = decision.get("accepted_tradeoff")
            if isinstance(accepted, dict):
                latest_binding = decision.get("source_bindings", [{}])[-1]
                if accepted.get("proposal_fingerprint") != decision.get("proposal_fingerprint") or accepted.get(
                    "source_fingerprint"
                ) != latest_binding.get("source_fingerprint"):
                    self.issue(
                        "STATE.ACCEPTED_TRADEOFF",
                        "accepted tradeoff is stale because its proposal/source fingerprint does not match",
                        decision=decision,
                    )
                matching_acceptance_events = [
                    event
                    for event in self._events_for_decision(decision)
                    if event.get("event_type") == "TRADEOFF_ACCEPTED"
                    and event.get("authority_kind") == "USER"
                    and event.get("actor") == accepted.get("accepted_by")
                    and event.get("timestamp") == accepted.get("timestamp")
                    and event.get("proposal_fingerprint") == accepted.get("proposal_fingerprint")
                    and event.get("source_fingerprint") == accepted.get("source_fingerprint")
                    and event.get("details", {}).get("accepted_tradeoff_hash")
                    == _content_hash(accepted)
                ]
                if len(matching_acceptance_events) != 1:
                    self.issue(
                        "STATE.ACCEPTED_TRADEOFF",
                        "accepted tradeoff requires exactly one matching USER-authority TRADEOFF_ACCEPTED event",
                        decision=decision,
                    )
                else:
                    event_positions = {
                        event.get("event_id"): position
                        for position, event in enumerate(self.state.get("events", []))
                        if isinstance(event, dict) and isinstance(event.get("event_id"), str)
                    }
                    acceptance_position = event_positions.get(
                        matching_acceptance_events[0].get("event_id"), -1
                    )
                    controlled_transition_positions = [
                        event_positions.get(event.get("event_id"), -1)
                        for event in self._events_for_decision(decision)
                        if event.get("new_state")
                        in {"AUTHORIZED", "IMPLEMENTED", "VERIFIED"}
                    ]
                    if any(
                        acceptance_position >= transition_position
                        for transition_position in controlled_transition_positions
                    ):
                        self.issue(
                            "STATE.ACCEPTED_TRADEOFF",
                            "accepted tradeoff must be recorded before authorization, implementation, and verification",
                            decision=decision,
                        )
            elif any(
                event.get("event_type") == "TRADEOFF_ACCEPTED"
                for event in self._events_for_decision(decision)
            ):
                self.issue(
                    "STATE.ACCEPTED_TRADEOFF",
                    "TRADEOFF_ACCEPTED event has no corresponding accepted_tradeoff record",
                    decision=decision,
                )

            implementation = decision.get("implementation_result")
            if state in IMPLEMENTED_STATES and not isinstance(implementation, dict):
                self.issue(
                    "STATE.IMPLEMENTATION",
                    "IMPLEMENTED/VERIFIED requires an implementation result",
                    decision=decision,
                )
            if isinstance(implementation, dict):
                if state not in {"IMPLEMENTED", "VERIFIED", "SUPERSEDED"}:
                    self.issue(
                        "STATE.IMPLEMENTATION",
                        f"decision in state {state} cannot carry an implementation result",
                        decision=decision,
                    )
                if not self._has_transition(decision, "AUTHORIZED") or not self._has_transition(
                    decision, "IMPLEMENTED"
                ):
                    self.issue(
                        "STATE.AUTHORIZATION",
                        "implementation result lacks prior AUTHORIZED and IMPLEMENTED events",
                        decision=decision,
                    )
                artifact = self.artifacts.get(implementation.get("artifact_id"))
                if artifact is None or implementation.get("candidate_hash") != artifact.get("candidate_hash"):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "implementation result is not bound to a registered artifact's exact candidate hash",
                        decision=decision,
                        artifact=implementation.get("artifact_id"),
                    )
                elif artifact is not None:
                    all_events = self.state.get("events", [])
                    creation_positions = [
                        position
                        for position, event in enumerate(all_events)
                        if isinstance(event, dict)
                        and event.get("event_type") == "ARTIFACT_CREATED"
                        and event.get("artifact_id") == artifact.get("artifact_id")
                        and event.get("artifact_hash") == artifact.get("candidate_hash")
                        and event.get("timestamp") == artifact.get("created_at")
                    ]
                    implementation_positions = [
                        position
                        for position, event in enumerate(all_events)
                        if isinstance(event, dict)
                        and event.get("event_type") == "DECISION_IMPLEMENTED"
                        and event.get("decision_id") == decision.get("decision_id")
                        and event.get("proposal_revision") == decision.get("proposal_revision")
                        and event.get("artifact_id") == implementation.get("artifact_id")
                        and event.get("artifact_hash") == implementation.get("candidate_hash")
                        and event.get("timestamp") == implementation.get("implemented_at")
                        and event.get("actor") == implementation.get("actor")
                    ]
                    if not creation_positions:
                        self.issue(
                            "STATE.ARTIFACT_BINDING",
                            "implementation result's exact candidate lacks a matching ARTIFACT_CREATED event",
                            decision=decision,
                            artifact=implementation.get("artifact_id"),
                        )
                    elif not implementation_positions or min(implementation_positions) <= min(
                        creation_positions
                    ):
                        self.issue(
                            "STATE.ARTIFACT_BINDING",
                            "implementation was recorded before creation of its exact candidate artifact",
                            decision=decision,
                            artifact=implementation.get("artifact_id"),
                        )

            verification = decision.get("verification_result")
            if state == "VERIFIED" and not isinstance(verification, dict):
                self.issue(
                    "STATE.VERIFICATION",
                    "VERIFIED decision requires a verification result",
                    decision=decision,
                )
            if isinstance(verification, dict):
                if state not in {"VERIFIED", "SUPERSEDED"}:
                    self.issue(
                        "STATE.VERIFICATION",
                        f"decision in state {state} cannot carry a verification result",
                        decision=decision,
                    )
                artifact = self.artifacts.get(verification.get("artifact_id"))
                if (
                    artifact is None
                    or verification.get("candidate_hash") != artifact.get("candidate_hash")
                    or verification.get("result") != "PASS"
                ):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "decision verification must PASS on the exact registered candidate hash",
                        decision=decision,
                        artifact=verification.get("artifact_id"),
                    )
                if not isinstance(implementation, dict) or (
                    implementation.get("artifact_id") != verification.get("artifact_id")
                    or implementation.get("candidate_hash") != verification.get("candidate_hash")
                ):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "decision implementation and verification must bind to the same exact candidate artifact",
                        decision=decision,
                        artifact=verification.get("artifact_id"),
                    )
                if not self._has_transition(decision, "VERIFIED"):
                    self.issue(
                        "STATE.VERIFICATION",
                        "verification result lacks a matching VERIFIED transition",
                        decision=decision,
                        artifact=verification.get("artifact_id"),
                    )

    def _resolve_ref(self, reference: Any) -> tuple[str, int] | None:
        if not isinstance(reference, dict):
            return None
        decision_id = reference.get("decision_id")
        revision = reference.get("proposal_revision")
        if isinstance(decision_id, str) and isinstance(revision, int):
            return decision_id, revision
        return None

    def _validate_dependencies_and_conflicts(self) -> None:
        raw_events = self.state.get("events", [])
        event_positions = {
            event.get("event_id"): position
            for position, event in enumerate(raw_events)
            if isinstance(event, dict) and isinstance(event.get("event_id"), str)
        }
        dependency_graph: dict[tuple[str, int], list[tuple[str, int]]] = {}
        transition_positions: dict[tuple[str, int], dict[str, int]] = {}
        transition_history: dict[tuple[str, int], list[tuple[int, str]]] = {}
        replayed_conflict_pairs: set[
            tuple[tuple[str, int], tuple[str, int]]
        ] = set()
        for position, event in enumerate(raw_events):
            if not isinstance(event, dict):
                continue
            key = (event.get("decision_id"), event.get("proposal_revision"))
            state = event.get("new_state")
            if key in self.decisions and isinstance(state, str):
                transition_positions.setdefault(key, {}).setdefault(state, position)
                transition_history.setdefault(key, []).append((position, state))
        for key, decision in self.decisions.items():
            dependency_graph[key] = []
            for reference in decision.get("dependencies", []):
                target = self._resolve_ref(reference)
                if target is None or target not in self.decisions:
                    self.issue(
                        "STATE.DEPENDENCY",
                        f"dependency {reference!r} does not resolve to a decision revision",
                        decision=decision,
                    )
                    continue
                if target == key:
                    self.issue("STATE.DEPENDENCY", "decision cannot depend on itself", decision=decision)
                    continue
                dependency_graph[key].append(target)
                target_state = self.decisions[target].get("decision_state")
                if decision.get("decision_state") == "AUTHORIZED" and target_state not in AUTHORIZATION_STATES:
                    self.issue(
                        "STATE.DEPENDENCY",
                        f"authorized decision depends on unresolved {_display_decision(target)} in state {target_state}",
                        decision=decision,
                    )
                authorization_position = transition_positions.get(key, {}).get("AUTHORIZED")
                target_authorization_position = transition_positions.get(target, {}).get("AUTHORIZED")
                if authorization_position is not None and (
                    target_authorization_position is None
                    or target_authorization_position > authorization_position
                ):
                    self.issue(
                        "STATE.DEPENDENCY",
                        f"decision was authorized before dependency {_display_decision(target)} was authorized",
                        decision=decision,
                    )
                for repeated_authorization_position, repeated_state in transition_history.get(key, []):
                    if repeated_state != "AUTHORIZED":
                        continue
                    target_prior_states = [
                        target_state_at_event
                        for target_position, target_state_at_event in transition_history.get(target, [])
                        if target_position < repeated_authorization_position
                    ]
                    target_state_at_authorization = (
                        target_prior_states[-1] if target_prior_states else None
                    )
                    if target_state_at_authorization not in AUTHORIZATION_STATES:
                        self.issue(
                            "STATE.DEPENDENCY",
                            f"decision authorization occurred while dependency {_display_decision(target)} was in state {target_state_at_authorization}",
                            decision=decision,
                        )
                implementation_position = transition_positions.get(key, {}).get("IMPLEMENTED")
                target_implementation_position = transition_positions.get(target, {}).get("IMPLEMENTED")
                if implementation_position is not None and (
                    target_implementation_position is None
                    or target_implementation_position > implementation_position
                ):
                    self.issue(
                        "STATE.DEPENDENCY",
                        f"decision was implemented before dependency {_display_decision(target)} was implemented",
                        decision=decision,
                    )
                if decision.get("decision_state") in IMPLEMENTED_STATES and target_state not in IMPLEMENTED_STATES:
                    self.issue(
                        "STATE.DEPENDENCY",
                        f"implemented decision depends on unimplemented {_display_decision(target)}",
                        decision=decision,
                    )

            for reference in decision.get("conflicts", []):
                target = self._resolve_ref(reference)
                if target is None or target not in self.decisions:
                    self.issue(
                        "STATE.CONFLICT",
                        f"conflict {reference!r} does not resolve to a decision revision",
                        decision=decision,
                    )
                    continue
                if target == key:
                    self.issue("STATE.CONFLICT", "decision cannot conflict with itself", decision=decision)
                    continue
                other = self.decisions[target]
                reciprocal = any(self._resolve_ref(item) == key for item in other.get("conflicts", []))
                if not reciprocal:
                    self.issue(
                        "STATE.CONFLICT",
                        f"conflict with {_display_decision(target)} is not reciprocal",
                        decision=decision,
                    )
                own_resolutions = [
                    item.get("resolution")
                    for item in decision.get("conflict_resolutions", [])
                    if isinstance(item, dict) and self._resolve_ref(item.get("with_decision")) == target
                ]
                other_resolutions = [
                    item.get("resolution")
                    for item in other.get("conflict_resolutions", [])
                    if isinstance(item, dict) and self._resolve_ref(item.get("with_decision")) == key
                ]
                normalized_pair = tuple(sorted((key, target)))
                if (
                    normalized_pair not in replayed_conflict_pairs
                    and "BOTH_COMPATIBLE" not in own_resolutions + other_resolutions
                ):
                    replayed_conflict_pairs.add(normalized_pair)
                    left, right = normalized_pair
                    replayed_states: dict[tuple[str, int], str] = {}
                    for historical_event in raw_events:
                        if not isinstance(historical_event, dict):
                            continue
                        historical_key = (
                            historical_event.get("decision_id"),
                            historical_event.get("proposal_revision"),
                        )
                        historical_state = historical_event.get("new_state")
                        if historical_key in {left, right} and isinstance(historical_state, str):
                            replayed_states[historical_key] = historical_state
                        if (
                            replayed_states.get(left) in ACTIVE_FOR_CONFLICT
                            and replayed_states.get(right) in ACTIVE_FOR_CONFLICT
                        ):
                            self.issue(
                                "STATE.CONFLICT",
                                "conflicting decisions were simultaneously active without an explicit "
                                f"BOTH_COMPATIBLE resolution: {_display_decision(left)} / {_display_decision(right)}",
                                decision=decision,
                            )
                            break
                decision_active = decision.get("decision_state") in ACTIVE_FOR_CONFLICT
                other_active = other.get("decision_state") in ACTIVE_FOR_CONFLICT
                if decision_active and other_active:
                    if "BOTH_COMPATIBLE" not in own_resolutions + other_resolutions:
                        self.issue(
                            "STATE.CONFLICT",
                            f"both conflicting decisions are active without an explicit BOTH_COMPATIBLE resolution: {_display_decision(target)}",
                            decision=decision,
                        )
                elif decision_active and other.get("decision_state") in {"PROPOSED", "DISCUSSED", "APPROVED"}:
                    if "THIS_SELECTED" not in own_resolutions and "OTHER_SELECTED" not in other_resolutions:
                        self.issue(
                            "STATE.CONFLICT",
                            f"active decision has an unresolved competing proposal {_display_decision(target)}",
                            decision=decision,
                        )
                elif other_active and decision.get("decision_state") in {"PROPOSED", "DISCUSSED", "APPROVED"}:
                    if "OTHER_SELECTED" not in own_resolutions and "THIS_SELECTED" not in other_resolutions:
                        self.issue(
                            "STATE.CONFLICT",
                            f"pending decision does not record selection of active {_display_decision(target)}",
                            decision=decision,
                        )

            conflict_keys = {
                target
                for target in (self._resolve_ref(reference) for reference in decision.get("conflicts", []))
                if target is not None
            }
            resolution_targets: set[tuple[str, int]] = set()
            for resolution in decision.get("conflict_resolutions", []):
                if not isinstance(resolution, dict):
                    continue
                target = self._resolve_ref(resolution.get("with_decision"))
                if target in resolution_targets:
                    self.issue(
                        "STATE.CONFLICT",
                        "a decision may record only one resolution for each conflicting revision",
                        decision=decision,
                    )
                elif target is not None:
                    resolution_targets.add(target)
                if target not in conflict_keys:
                    self.issue(
                        "STATE.CONFLICT",
                        "conflict resolution does not correspond to a declared conflict",
                        decision=decision,
                    )
                    continue
                resolution_value = resolution.get("resolution")
                target_decision = self.decisions.get(target)
                if resolution_value == "THIS_SELECTED" and target_decision is not None:
                    if decision.get("decision_state") not in ACTIVE_FOR_CONFLICT | {"APPROVED"} or target_decision.get(
                        "decision_state"
                    ) in ACTIVE_FOR_CONFLICT | {"APPROVED"}:
                        self.issue(
                            "STATE.CONFLICT",
                            "THIS_SELECTED conflicts with the recorded active decision states",
                            decision=decision,
                        )
                elif resolution_value == "OTHER_SELECTED" and target_decision is not None:
                    if target_decision.get("decision_state") not in ACTIVE_FOR_CONFLICT | {"APPROVED"} or decision.get(
                        "decision_state"
                    ) in ACTIVE_FOR_CONFLICT | {"APPROVED"}:
                        self.issue(
                            "STATE.CONFLICT",
                            "OTHER_SELECTED conflicts with the recorded active decision states",
                            decision=decision,
                        )
                elif resolution_value == "DEFERRED" and decision.get("decision_state") != "HELD":
                    self.issue(
                        "STATE.CONFLICT",
                        "DEFERRED resolution requires the owning decision to be HELD",
                        decision=decision,
                    )
                if resolution_value == "BOTH_COMPATIBLE":
                    matching_authority_events = [
                        event
                        for event in self._events_for_decision(decision)
                        if event.get("event_type") == "CONFLICT_RESOLUTION_ACCEPTED"
                        and event.get("authority_kind") == "USER"
                        and event.get("proposal_fingerprint")
                        == decision.get("proposal_fingerprint")
                        and event.get("details", {}).get("conflict_resolution_hash")
                        == _content_hash(resolution)
                    ]
                    if len(matching_authority_events) != 1:
                        self.issue(
                            "STATE.CONFLICT_AUTHORITY",
                            "BOTH_COMPATIBLE requires exactly one current USER-authority conflict-resolution event",
                            decision=decision,
                        )
                    else:
                        replayed_states: dict[tuple[str, int], str] = {}
                        simultaneous_active_position: int | None = None
                        for position, historical_event in enumerate(raw_events):
                            if not isinstance(historical_event, dict):
                                continue
                            historical_key = (
                                historical_event.get("decision_id"),
                                historical_event.get("proposal_revision"),
                            )
                            historical_state = historical_event.get("new_state")
                            if historical_key in {key, target} and isinstance(
                                historical_state, str
                            ):
                                replayed_states[historical_key] = historical_state
                            if (
                                replayed_states.get(key) in ACTIVE_FOR_CONFLICT
                                and replayed_states.get(target) in ACTIVE_FOR_CONFLICT
                            ):
                                simultaneous_active_position = position
                                break
                        authority_position = event_positions.get(
                            matching_authority_events[0].get("event_id"), -1
                        )
                        if (
                            simultaneous_active_position is not None
                            and authority_position >= simultaneous_active_position
                        ):
                            self.issue(
                                "STATE.CONFLICT_AUTHORITY",
                                "BOTH_COMPATIBLE user acceptance must precede the conflicting decisions becoming simultaneously active",
                                decision=decision,
                            )

        incoming = {key: 0 for key in dependency_graph}
        for targets in dependency_graph.values():
            for target in targets:
                incoming[target] += 1
        pending = [key for key, count in incoming.items() if count == 0]
        processed = 0
        while pending:
            key = pending.pop()
            processed += 1
            for target in dependency_graph.get(key, []):
                incoming[target] -= 1
                if incoming[target] == 0:
                    pending.append(target)
        if processed != len(dependency_graph):
            cyclic = next(key for key, count in incoming.items() if count > 0)
            self.issue("STATE.DEPENDENCY", "dependency graph contains a cycle", decision=cyclic)

    def _validate_supersession(self) -> None:
        for key, decision in self.decisions.items():
            links = decision.get("supersession_links", [])
            by_relation: dict[str, list[tuple[str, int]]] = {"SUPERSEDES": [], "SUPERSEDED_BY": []}
            for link in links:
                if not isinstance(link, dict):
                    continue
                target = self._resolve_ref(link)
                relation = link.get("relation")
                if target is None or target not in self.decisions:
                    self.issue(
                        "STATE.SUPERSESSION",
                        f"orphaned supersession link {link!r}",
                        decision=decision,
                    )
                    continue
                if relation in by_relation:
                    by_relation[relation].append(target)
                if target[0] != key[0]:
                    self.issue(
                        "STATE.SUPERSESSION",
                        "proposal revisions may supersede only revisions with the same stable decision ID",
                        decision=decision,
                    )
                    continue
                if relation == "SUPERSEDES" and target[1] >= key[1]:
                    self.issue(
                        "STATE.SUPERSESSION",
                        "SUPERSEDES must point from a newer proposal revision to an older revision",
                        decision=decision,
                    )
                if relation == "SUPERSEDED_BY" and target[1] <= key[1]:
                    self.issue(
                        "STATE.SUPERSESSION",
                        "SUPERSEDED_BY must point from an older proposal revision to a newer revision",
                        decision=decision,
                    )
                reverse_relation = "SUPERSEDED_BY" if relation == "SUPERSEDES" else "SUPERSEDES"
                reverse = any(
                    item.get("relation") == reverse_relation and self._resolve_ref(item) == key
                    for item in self.decisions[target].get("supersession_links", [])
                    if isinstance(item, dict)
                )
                if not reverse:
                    self.issue(
                        "STATE.SUPERSESSION",
                        f"supersession link to {_display_decision(target)} is not reciprocal",
                        decision=decision,
                    )
            if decision.get("decision_state") == "SUPERSEDED" and not by_relation["SUPERSEDED_BY"]:
                self.issue(
                    "STATE.SUPERSESSION",
                    "SUPERSEDED decision lacks a SUPERSEDED_BY link",
                    decision=decision,
                )
            if decision.get("decision_state") == "SUPERSEDED" and not any(
                target[0] == key[0] and target[1] > key[1]
                for target in by_relation["SUPERSEDED_BY"]
            ):
                self.issue(
                    "STATE.SUPERSESSION",
                    "SUPERSEDED decision must identify a later proposal revision as its successor",
                    decision=decision,
                )

    def _validate_locks(self) -> None:
        all_events = self.state.get("events", [])
        for event in all_events:
            if not isinstance(event, dict) or event.get("event_type") not in {
                "LOCK_CREATED",
                "LOCK_RELEASED",
            }:
                continue
            referenced_lock_id = event.get("details", {}).get("lock_id")
            if referenced_lock_id not in self.locks:
                self.issue(
                    "STATE.LOCK",
                    f"{event.get('event_type')} event refers to unknown lock {referenced_lock_id!r}",
                )
        for lock_id, lock in self.locks.items():
            if lock.get("status") == "RELEASED" and (not lock.get("released_at") or not lock.get("released_by")):
                self.issue("STATE.LOCK", f"released lock {lock_id!r} needs released_at and released_by")
            if (
                lock.get("status") == "RELEASED"
                and _timestamp_key(lock.get("released_at"))
                < _timestamp_key(lock.get("created_at"))
            ):
                self.issue("STATE.LOCK", f"released lock {lock_id!r} predates its creation")
            if lock.get("status") == "ACTIVE" and (lock.get("released_at") is not None or lock.get("released_by") is not None):
                self.issue("STATE.LOCK", f"active lock {lock_id!r} cannot contain release metadata")
            if not any(
                lock.get("source_fingerprint") in {source.get("byte_hash"), source.get("extracted_text_hash")}
                for source in self.sources.values()
            ):
                self.issue("STATE.LOCK", f"lock {lock_id!r} is not bound to a registered source fingerprint")

            creation_positions = [
                position
                for position, event in enumerate(all_events)
                if isinstance(event, dict)
                and event.get("event_type") == "LOCK_CREATED"
                and event.get("details", {}).get("lock_id") == lock_id
                and event.get("timestamp") == lock.get("created_at")
                and event.get("actor") == lock.get("creating_authority")
                and event.get("source_fingerprint") == lock.get("source_fingerprint")
                and event.get("details", {}).get("lock_payload_hash")
                == _content_hash(_lock_creation_payload(lock))
            ]
            if len(creation_positions) != 1:
                self.issue(
                    "STATE.LOCK",
                    f"lock {lock_id!r} requires exactly one canonical LOCK_CREATED event",
                )
            release_positions = [
                position
                for position, event in enumerate(all_events)
                if isinstance(event, dict)
                and event.get("event_type") == "LOCK_RELEASED"
                and event.get("details", {}).get("lock_id") == lock_id
                and event.get("timestamp") == lock.get("released_at")
                and event.get("actor") == lock.get("released_by")
                and event.get("source_fingerprint") == lock.get("source_fingerprint")
                and event.get("details", {}).get("lock_release_payload_hash")
                == _content_hash(_lock_release_payload(lock))
            ]
            if lock.get("type") == "USER_LOCK":
                user_creation_positions = [
                    position
                    for position in creation_positions
                    if all_events[position].get("authority_kind") == "USER"
                ]
                if len(user_creation_positions) != 1:
                    self.issue(
                        "STATE.LOCK_AUTHORITY",
                        f"user lock {lock_id!r} must be created by USER authority",
                    )
                user_release_positions = [
                    position
                    for position in release_positions
                    if all_events[position].get("authority_kind") == "USER"
                ]
                if lock.get("status") == "RELEASED" and len(user_release_positions) != 1:
                    self.issue(
                        "STATE.LOCK_AUTHORITY",
                        f"user lock {lock_id!r} may be released only by USER authority",
                    )
            if lock.get("status") == "RELEASED" and len(release_positions) != 1:
                self.issue(
                    "STATE.LOCK",
                    f"released lock {lock_id!r} requires exactly one canonical LOCK_RELEASED event",
                )
            if lock.get("status") == "ACTIVE" and any(
                isinstance(event, dict)
                and event.get("event_type") == "LOCK_RELEASED"
                and event.get("details", {}).get("lock_id") == lock_id
                for event in all_events
            ):
                self.issue(
                    "STATE.LOCK",
                    f"active lock {lock_id!r} cannot have a LOCK_RELEASED event",
                )
            if creation_positions and release_positions and release_positions[0] <= creation_positions[0]:
                self.issue(
                    "STATE.LOCK",
                    f"lock {lock_id!r} release event does not follow its creation event",
                )

        for decision in self.decisions.values():
            decision_anchors = (decision.get("location"), decision.get("anchor_text"))
            implementation = decision.get("implementation_result")
            implementation_time = (
                _timestamp_key(implementation.get("implemented_at"))
                if isinstance(implementation, dict)
                else float("inf")
            )
            derived_lock_ids = {
                lock_id
                for lock_id, lock in self.locks.items()
                if isinstance(lock.get("scope_anchor"), str)
                and any(
                    _scope_anchors_overlap(lock["scope_anchor"], decision_anchor)
                    for decision_anchor in decision_anchors
                )
                and _timestamp_key(lock.get("created_at")) <= implementation_time
            }
            declared_lock_ids = set(decision.get("affected_lock_ids", []))
            omitted_lock_ids = sorted(derived_lock_ids - declared_lock_ids)
            if omitted_lock_ids:
                self.issue(
                    "STATE.LOCK",
                    f"decision scope intersects locks omitted from affected_lock_ids: {omitted_lock_ids}",
                    decision=decision,
                )
            for lock_id in sorted(declared_lock_ids | derived_lock_ids):
                lock = self.locks.get(lock_id)
                if lock is None:
                    self.issue("STATE.LOCK", f"affected lock {lock_id!r} is not registered", decision=decision)
                    continue
                if (
                    self.check == "ready-to-implement"
                    and lock.get("status") == "ACTIVE"
                    and decision.get("decision_state") == "AUTHORIZED"
                ):
                    self.issue(
                        "STATE.LOCK",
                        f"active lock {lock_id!r} blocks pending implementation",
                        decision=decision,
                    )
                if lock is not None:
                    creation_positions = [
                        position
                        for position, event in enumerate(all_events)
                        if isinstance(event, dict)
                        and event.get("event_type") == "LOCK_CREATED"
                        and event.get("details", {}).get("lock_id") == lock_id
                        and event.get("timestamp") == lock.get("created_at")
                        and event.get("actor") == lock.get("creating_authority")
                        and event.get("source_fingerprint") == lock.get("source_fingerprint")
                        and event.get("details", {}).get("lock_payload_hash")
                        == _content_hash(_lock_creation_payload(lock))
                    ]
                    release_positions = [
                        position
                        for position, event in enumerate(all_events)
                        if isinstance(event, dict)
                        and event.get("event_type") == "LOCK_RELEASED"
                        and event.get("details", {}).get("lock_id") == lock_id
                        and event.get("timestamp") == lock.get("released_at")
                        and event.get("actor") == lock.get("released_by")
                        and event.get("source_fingerprint") == lock.get("source_fingerprint")
                        and event.get("details", {}).get("lock_release_payload_hash")
                        == _content_hash(_lock_release_payload(lock))
                    ]
                    if not creation_positions:
                        continue
                    creation_position = creation_positions[0]
                    release_position = (
                        release_positions[0]
                        if lock.get("status") == "RELEASED" and release_positions
                        else float("inf")
                    )
                    for event_position, event in enumerate(all_events):
                        if not isinstance(event, dict) or (
                            event.get("decision_id") != decision.get("decision_id")
                            or event.get("proposal_revision") != decision.get("proposal_revision")
                        ):
                            continue
                        if event.get("new_state") not in {"AUTHORIZED", "IMPLEMENTED"}:
                            continue
                        if creation_position <= event_position < release_position:
                            self.issue(
                                "STATE.LOCK",
                                f"lock {lock_id!r} was active when the decision advanced to {event.get('new_state')}",
                                decision=decision,
                            )

    def _validate_local_fixes(self) -> None:
        all_events = self.state.get("events", [])
        current_source_ids = set(self.state.get("run", {}).get("current_source_ids", []))
        for local_fix_id, local_fix in self.local_fixes.items():
            implemented_hunks = local_fix.get("implemented_hunk_ids", [])
            matching_authorization_positions: list[int] = []
            authorized_source_id = local_fix.get("source_id")
            authorized_source_fingerprint = local_fix.get("source_fingerprint")
            authorized_source = self.sources.get(authorized_source_id)
            if (
                authorized_source_id not in current_source_ids
                or not isinstance(authorized_source, dict)
                or not authorized_source.get("content_authority")
                or not self._source_matches_fingerprint(
                    authorized_source_id, authorized_source_fingerprint
                )
            ):
                self.issue(
                    "STATE.LOCAL_FIX",
                    f"local fix {local_fix_id!r} is not bound to a current content-authority source",
                )
            if local_fix.get("authorized"):
                if not local_fix.get("authorized_by") or not local_fix.get("authorized_at"):
                    self.issue(
                        "STATE.LOCAL_FIX",
                        f"authorized local fix {local_fix_id!r} needs authorization actor and timestamp",
                    )
                matching_authorization_positions = [
                    position
                    for position, event in enumerate(all_events)
                    if isinstance(event, dict)
                    and event.get("event_type") == "LOCAL_FIX_AUTHORIZED"
                    and event.get("details", {}).get("local_fix_id") == local_fix_id
                    and event.get("authority_kind") == "USER"
                    and event.get("actor") == local_fix.get("authorized_by")
                    and event.get("timestamp") == local_fix.get("authorized_at")
                    and event.get("details", {}).get("local_fix_payload_hash")
                    == _content_hash(_local_fix_authorization_payload(local_fix))
                    and event.get("source_id") == authorized_source_id
                    and event.get("source_fingerprint") == authorized_source_fingerprint
                ]
                if not matching_authorization_positions:
                    self.issue(
                        "STATE.LOCAL_FIX",
                        f"authorized local fix {local_fix_id!r} lacks a matching USER event bound to its exact payload and current content-authority source",
                    )
            elif local_fix.get("authorized_by") is not None or local_fix.get("authorized_at") is not None:
                self.issue(
                    "STATE.LOCAL_FIX",
                    f"unauthorized local fix {local_fix_id!r} cannot carry authorization metadata",
                )
            if implemented_hunks and (
                not local_fix.get("authorized") or local_fix.get("candidate_hash") is None
            ):
                self.issue(
                    "STATE.LOCAL_FIX",
                    f"implemented local fix {local_fix_id!r} must be authorized and bound to a candidate hash",
                )
            if implemented_hunks and not any(
                artifact.get("candidate_hash") == local_fix.get("candidate_hash")
                for artifact in self.artifacts.values()
            ):
                self.issue(
                    "STATE.LOCAL_FIX",
                    f"implemented local fix {local_fix_id!r} is not bound to a registered artifact hash",
                )
            if implemented_hunks:
                bound_artifacts = [
                    artifact
                    for artifact in self.artifacts.values()
                    if artifact.get("candidate_hash") == local_fix.get("candidate_hash")
                ]
                for artifact in bound_artifacts:
                    if (
                        authorized_source_id not in artifact.get("baseline_source_ids", [])
                        or artifact.get("source_hash") != authorized_source_fingerprint
                    ):
                        self.issue(
                            "STATE.LOCAL_FIX",
                            f"implemented local fix {local_fix_id!r} candidate is not based on its exact authorized source",
                            artifact=artifact.get("artifact_id"),
                        )
                    creation_positions = [
                        position
                        for position, event in enumerate(all_events)
                        if isinstance(event, dict)
                        and event.get("event_type") == "ARTIFACT_CREATED"
                        and event.get("artifact_id") == artifact.get("artifact_id")
                        and event.get("artifact_hash") == artifact.get("candidate_hash")
                        and event.get("timestamp") == artifact.get("created_at")
                    ]
                    if not creation_positions:
                        self.issue(
                            "STATE.LOCAL_FIX",
                            f"implemented local fix {local_fix_id!r} is bound to a candidate without an exact ARTIFACT_CREATED event",
                            artifact=artifact.get("artifact_id"),
                        )
                    elif not matching_authorization_positions or min(
                        matching_authorization_positions
                    ) >= min(creation_positions):
                        self.issue(
                            "STATE.LOCAL_FIX",
                            f"implemented local fix {local_fix_id!r} was not authorized before its exact candidate was created",
                            artifact=artifact.get("artifact_id"),
                        )
            if not implemented_hunks and local_fix.get("candidate_hash") is not None:
                self.issue(
                    "STATE.LOCAL_FIX",
                    f"unimplemented local fix {local_fix_id!r} cannot be bound to a candidate hash",
                )

    def _candidate_manifest_index(self) -> dict[str, dict[str, Any]]:
        if not isinstance(self.candidate, dict):
            return {}
        entries = self.candidate.get("artifacts")
        if not isinstance(entries, list):
            return {}
        indexed: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                self.issue(
                    "STATE.CANDIDATE_MANIFEST",
                    "every candidate-manifest artifact must be an object",
                )
                continue
            if not isinstance(entry.get("artifact_id"), str) or not entry.get("artifact_id"):
                self.issue(
                    "STATE.CANDIDATE_MANIFEST",
                    "every candidate-manifest artifact needs a nonempty artifact_id",
                )
                continue
            artifact_id = entry["artifact_id"]
            if artifact_id in indexed:
                self.issue(
                    "STATE.CANDIDATE_MANIFEST",
                    f"duplicate candidate-manifest artifact {artifact_id!r}",
                    artifact=artifact_id,
                )
            else:
                indexed[artifact_id] = entry
        return indexed

    def _validate_artifacts(self) -> None:
        candidate_index = self._candidate_manifest_index() if self.check != "diagnostic" else {}
        candidate_manifest_has_array = (
            self.check != "diagnostic"
            and isinstance(self.candidate, dict)
            and isinstance(self.candidate.get("artifacts"), list)
        )
        current_artifact_id = self.state.get("run", {}).get("current_artifact_id")
        if self.candidate is not None and self.check != "diagnostic":
            if not isinstance(self.candidate, dict) or not isinstance(self.candidate.get("artifacts"), list):
                self.issue("STATE.CANDIDATE_MANIFEST", "candidate manifest must contain an artifacts array")
            elif self.candidate.get("schema_version") != "1.0.0":
                self.issue("STATE.CANDIDATE_MANIFEST", "candidate manifest schema_version must be '1.0.0'")
            elif self.candidate.get("run_id") != self.state.get("run", {}).get("run_id"):
                self.issue("STATE.CANDIDATE_MANIFEST", "candidate manifest run_id does not match the state")
            for candidate_artifact_id in candidate_index:
                if candidate_artifact_id not in self.artifacts:
                    self.issue(
                        "STATE.CANDIDATE_MANIFEST",
                        "candidate manifest contains an artifact absent from state.artifacts",
                        artifact=candidate_artifact_id,
                    )

        for candidate_artifact_id, candidate in candidate_index.items():
            state_artifact = self.artifacts.get(candidate_artifact_id)
            if state_artifact is None:
                continue
            for field in (
                "path",
                "baseline_source_ids",
                "candidate_hash",
                "artifact_status",
                "relationship_to_baseline",
                "actual_submission_artifact",
                "format",
            ):
                if candidate.get(field) != state_artifact.get(field):
                    self.issue(
                        "STATE.CANDIDATE_MANIFEST",
                        f"candidate manifest {field} does not match state artifact",
                        artifact=candidate_artifact_id,
                    )

        for artifact_id, artifact in self.artifacts.items():
            path_suffix = Path(artifact.get("path", "")).suffix.lower()
            suffix_formats = {
                ".pdf": "PDF",
                ".docx": "DOCX",
                ".txt": "TXT",
                ".md": "MD",
                ".markdown": "MD",
                ".json": "JSON",
            }
            suffix_format = suffix_formats.get(path_suffix)
            if suffix_format is not None and artifact.get("format") != suffix_format:
                self.issue(
                    "STATE.ARTIFACT_FORMAT",
                    f"artifact path suffix {path_suffix!r} contradicts declared format {artifact.get('format')!r}",
                    artifact=artifact_id,
                )
            for source_id in artifact.get("baseline_source_ids", []):
                if source_id not in self.sources:
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        f"artifact baseline source {source_id!r} is not registered",
                        artifact=artifact_id,
                    )
            if artifact.get("source_hash") not in {
                source.get("byte_hash") for source in self.sources.values()
            } | {source.get("extracted_text_hash") for source in self.sources.values()}:
                self.issue(
                    "STATE.ARTIFACT_BINDING",
                    "artifact source_hash does not match a registered baseline source",
                    artifact=artifact_id,
                )
            baseline_sources = [
                self.sources[source_id]
                for source_id in artifact.get("baseline_source_ids", [])
                if source_id in self.sources
            ]
            if baseline_sources and artifact.get("source_hash") not in {
                fingerprint
                for source in baseline_sources
                for fingerprint in (source.get("byte_hash"), source.get("extracted_text_hash"))
                if fingerprint is not None
            }:
                self.issue(
                    "STATE.ARTIFACT_BINDING",
                    "artifact source_hash does not match any source named in baseline_source_ids",
                    artifact=artifact_id,
                )
            verification = artifact.get("verification")
            if artifact.get("artifact_status") == "VERIFIED":
                if not isinstance(verification, dict):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "VERIFIED artifact requires a verification record",
                        artifact=artifact_id,
                    )
                elif (
                    verification.get("status") != "VERIFIED"
                    or verification.get("candidate_hash") != artifact.get("candidate_hash")
                    or not verification.get("actual_artifact_inspected")
                ):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "artifact verification must be VERIFIED and bound to the exact inspected candidate hash",
                        artifact=artifact_id,
                    )
            elif isinstance(verification, dict) and verification.get("status") == "VERIFIED":
                self.issue(
                    "STATE.ARTIFACT_BINDING",
                    "non-VERIFIED artifact cannot retain a current VERIFIED record",
                    artifact=artifact_id,
                )
            if artifact.get("layout_relevant") and artifact.get("artifact_status") == "VERIFIED":
                if not isinstance(verification, dict) or verification.get("layout_result") != "PASS":
                    self.issue(
                        "STATE.LAYOUT_VERIFICATION",
                        "layout-relevant VERIFIED artifact requires layout_result PASS on the actual artifact",
                        artifact=artifact_id,
                    )
            if (
                artifact.get("actual_submission_artifact")
                and (artifact.get("format") == "PDF" or path_suffix == ".pdf")
                and not artifact.get("layout_relevant")
            ):
                self.issue(
                    "STATE.LAYOUT_VERIFICATION",
                    "an actual submission PDF is necessarily layout-relevant",
                    artifact=artifact_id,
                )

            if candidate_manifest_has_array and artifact_id == current_artifact_id:
                candidate = candidate_index.get(artifact_id)
                if candidate is None:
                    self.issue(
                        "STATE.CANDIDATE_MANIFEST",
                        "state artifact is missing from candidate manifest",
                        artifact=artifact_id,
                    )

            all_events = self.state.get("events", [])
            artifact_event_pairs = [
                (position, event)
                for position, event in enumerate(all_events)
                if isinstance(event, dict) and event.get("artifact_id") == artifact_id
            ]
            artifact_events = [event for _, event in artifact_event_pairs]
            if artifact.get("artifact_status") == "VERIFIED":
                created = [
                    event
                    for event in artifact_events
                    if event.get("event_type") == "ARTIFACT_CREATED"
                    and event.get("artifact_hash") == artifact.get("candidate_hash")
                    and event.get("timestamp") == artifact.get("created_at")
                ]
                if len(created) != 1:
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "VERIFIED artifact requires exactly one ARTIFACT_CREATED event for its exact hash",
                        artifact=artifact_id,
                    )
                matching = [
                    event
                    for event in artifact_events
                    if event.get("event_type") == "ARTIFACT_VERIFIED"
                    and event.get("artifact_hash") == artifact.get("candidate_hash")
                    and isinstance(verification, dict)
                    and event.get("timestamp") == verification.get("completed_at")
                    and event.get("actor") == verification.get("actor")
                ]
                if not matching:
                    self.issue(
                        "STATE.LATE_EDIT",
                        "VERIFIED artifact lacks an ARTIFACT_VERIFIED event for its exact hash",
                        artifact=artifact_id,
                    )
                else:
                    verified_positions = [
                        index
                        for index, event in enumerate(all_events)
                        if isinstance(event, dict)
                        and event.get("artifact_id") == artifact_id
                        and event.get("event_type") == "ARTIFACT_VERIFIED"
                        and event.get("artifact_hash") == artifact.get("candidate_hash")
                        and isinstance(verification, dict)
                        and event.get("timestamp") == verification.get("completed_at")
                        and event.get("actor") == verification.get("actor")
                    ]
                    if len(verified_positions) != 1:
                        self.issue(
                            "STATE.ARTIFACT_BINDING",
                            "VERIFIED artifact requires exactly one canonical ARTIFACT_VERIFIED event",
                            artifact=artifact_id,
                        )
                    first_verified_position = min(verified_positions)
                    for event in all_events[first_verified_position + 1 :]:
                        if (
                            isinstance(event, dict)
                            and event.get("artifact_id") == artifact_id
                            and event.get("event_type")
                            in {"ARTIFACT_CREATED", "ARTIFACT_MODIFIED", "ARTIFACT_INVALIDATED"}
                        ):
                            self.issue(
                                "STATE.LATE_EDIT",
                                "artifact was created, modified, or invalidated after verification; a new artifact ID/hash with UNVERIFIED status is required",
                                artifact=artifact_id,
                            )
                        if (
                            isinstance(event, dict)
                            and event.get("artifact_id") == artifact_id
                            and (
                                event.get("event_type")
                                in {"DECISION_IMPLEMENTED", "DECISION_VERIFIED"}
                                or event.get("new_state") in {"IMPLEMENTED", "VERIFIED"}
                            )
                        ):
                            self.issue(
                                "STATE.LATE_EDIT",
                                "decision implementation or verification was recorded after final artifact verification",
                                artifact=artifact_id,
                            )
                    created_positions = [
                        position
                        for position, event in artifact_event_pairs
                        if event.get("event_type") == "ARTIFACT_CREATED"
                        and event.get("artifact_hash") == artifact.get("candidate_hash")
                        and event.get("timestamp") == artifact.get("created_at")
                    ]
                    if created_positions:
                        created_position = min(created_positions)
                        for position, event in artifact_event_pairs:
                            if (
                                event.get("event_type")
                                not in {"DECISION_IMPLEMENTED", "DECISION_VERIFIED"}
                                and event.get("new_state") not in {"IMPLEMENTED", "VERIFIED"}
                            ):
                                continue
                            if event.get("artifact_hash") != artifact.get("candidate_hash"):
                                continue
                            if position <= created_position:
                                self.issue(
                                    "STATE.ARTIFACT_BINDING",
                                    "decision implementation/verification precedes creation of its exact artifact",
                                    artifact=artifact_id,
                                )
                            if position >= first_verified_position:
                                self.issue(
                                    "STATE.LATE_EDIT",
                                    "decision implementation/verification must precede final artifact verification",
                                    artifact=artifact_id,
                                )

    def _validate_attestations(self) -> None:
        requirements: dict[str, dict[str, Any]] = {}
        for requirement in self.state.get("gate_applicability", []):
            if not isinstance(requirement, dict) or not isinstance(requirement.get("check_id"), str):
                continue
            check_id = requirement["check_id"]
            if check_id in requirements:
                self.issue("STATE.ATTESTATION", f"duplicate gate applicability record {check_id!r}")
            requirements[check_id] = requirement

        attestations_by_check: dict[str, list[dict[str, Any]]] = {}
        seen_attestations: set[str] = set()
        for attestation in self.state.get("attestations", []):
            if not isinstance(attestation, dict):
                continue
            attestation_id = attestation.get("attestation_id")
            if isinstance(attestation_id, str):
                if attestation_id in seen_attestations:
                    self.issue("STATE.ATTESTATION", f"duplicate attestation ID {attestation_id!r}")
                seen_attestations.add(attestation_id)
            attestations_by_check.setdefault(attestation.get("check_id"), []).append(attestation)
            artifact_id = attestation.get("artifact_id")
            source_id = attestation.get("source_id")
            if artifact_id is not None:
                artifact = self.artifacts.get(artifact_id)
                if artifact is None or attestation.get("artifact_hash") != artifact.get("candidate_hash"):
                    self.issue(
                        "STATE.ATTESTATION_BINDING",
                        "attestation artifact ID/hash does not match a registered exact artifact",
                        artifact=artifact_id,
                    )
            if source_id is not None and not self._source_matches_fingerprint(
                source_id, attestation.get("source_fingerprint")
            ):
                self.issue(
                    "STATE.ATTESTATION_BINDING",
                    "attestation source ID/fingerprint does not match a registered source",
                )
            if artifact_id is None and source_id is None:
                self.issue(
                    "STATE.ATTESTATION_BINDING",
                    "attestation must bind either a source or an artifact",
                )
            if attestation.get("authority_kind") not in {"USER", "REVIEWER"}:
                self.issue(
                    "STATE.ATTESTATION_AUTHORITY",
                    "qualitative attestations require USER or REVIEWER authority",
                    artifact=artifact_id,
                )

        mode = {
            "diagnostic": "DIAGNOSTIC",
            "ready-to-implement": "IMPLEMENTATION",
            "ready-to-release": "RELEASE",
        }[self.check]
        current_artifact_id = self.state.get("run", {}).get("current_artifact_id")
        current_artifact = self.artifacts.get(current_artifact_id) if current_artifact_id else None
        current_source_ids = set(self.state.get("run", {}).get("current_source_ids", []))
        attestation_source_ids = {
            source_id
            for source_id, source in self.sources.items()
            if source_id in current_source_ids and source.get("content_authority")
        }
        if self.check == "diagnostic" and not attestation_source_ids:
            # A diagnostic may still assess source-independent scientific
            # integrity while explicitly reporting content authority and its
            # dependent narrative gates as NOT_ASSESSABLE.
            attestation_source_ids = current_source_ids
        current_source_pairs = {
            (source_id, source.get("byte_hash"))
            for source_id, source in self.sources.items()
            if source_id in attestation_source_ids
        } | {
            (source_id, source.get("extracted_text_hash"))
            for source_id, source in self.sources.items()
            if source_id in attestation_source_ids
            and source.get("extracted_text_hash") is not None
        }
        binding_cutoff = max(
            (
                _timestamp_key(binding.get("timestamp"))
                for decision in self.decisions.values()
                for binding in decision.get("source_bindings", [])
                if isinstance(binding, dict)
                and binding.get("binding_type") == "SOURCE_REVALIDATED"
                and binding.get("source_id") in current_source_ids
            ),
            default=_timestamp_key(self.state.get("run", {}).get("started_at")),
        )
        narrative_hard_gates_required = (
            self.state.get("run", {}).get("document_type")
            in NARRATIVE_HARD_GATE_DOCUMENT_TYPES
        )
        required_registry_ids = (
            set(RELEASE_GATE_IDS) if self.check == "ready-to-release" else set(BASE_GATE_IDS)
        )
        if narrative_hard_gates_required:
            required_registry_ids.update(NARRATIVE_HARD_GATE_IDS)
        for check_id in sorted(required_registry_ids - set(requirements)):
            self.issue(
                "STATE.RELEASE_GATE_REGISTRY"
                if self.check == "ready-to-release"
                else "STATE.GATE_REGISTRY",
                f"{mode.lower()} gate {check_id!r} has no explicit applicability record",
                artifact=current_artifact_id,
            )
        for check_id in sorted(required_registry_ids & set(requirements)):
            if mode not in requirements[check_id].get("required_for", []):
                self.issue(
                    "STATE.RELEASE_GATE_REGISTRY"
                    if self.check == "ready-to-release"
                    else "STATE.GATE_REGISTRY",
                    f"gate {check_id!r} is not declared required for {mode}",
                    artifact=current_artifact_id,
                )
        has_current_content_authority = any(
            source.get("is_current") and source.get("content_authority")
            for source in self.sources.values()
        )
        always_applicable = set(BASE_GATE_IDS)
        if narrative_hard_gates_required:
            always_applicable.update(NARRATIVE_HARD_GATE_IDS)
        if self.check == "ready-to-release":
            always_applicable.update(
                {"final_actual_artifact", "post_implementation_blind", "tired_reader"}
            )
            if current_artifact is not None and (
                current_artifact.get("layout_relevant")
                or (
                    current_artifact.get("actual_submission_artifact")
                    and (
                        current_artifact.get("format") == "PDF"
                        or Path(current_artifact.get("path", "")).suffix.lower() == ".pdf"
                    )
                )
            ):
                always_applicable.add("layout_verification")
        elif self.check == "diagnostic" and not has_current_content_authority:
            # Diagnosis may expose genuinely unresolved current-source authority
            # and source-dependent narrative gates as NOT_ASSESSABLE, but an
            # available authority cannot be opted out.
            always_applicable.discard("current_source_authority")
            always_applicable.difference_update(NARRATIVE_HARD_GATE_IDS)
            unresolved_gate_ids = {"current_source_authority"}
            if narrative_hard_gates_required:
                unresolved_gate_ids.update(NARRATIVE_HARD_GATE_IDS)
            for check_id in sorted(unresolved_gate_ids & set(requirements)):
                if requirements[check_id].get("applicability") != "NOT_ASSESSABLE":
                    self.issue(
                        "STATE.GATE_REGISTRY",
                        f"gate {check_id!r} must be NOT_ASSESSABLE until current content authority is resolved",
                        artifact=current_artifact_id,
                    )
        for check_id in sorted(always_applicable & set(requirements)):
            if requirements[check_id].get("applicability") != "APPLICABLE":
                self.issue(
                    "STATE.RELEASE_GATE_REGISTRY"
                    if self.check == "ready-to-release"
                    else "STATE.GATE_REGISTRY",
                    f"gate {check_id!r} is mandatory and cannot be marked NOT_APPLICABLE or NOT_ASSESSABLE for {mode}",
                    artifact=current_artifact_id,
                )
        for check_id, requirement in requirements.items():
            if mode not in requirement.get("required_for", []):
                continue
            applicability = requirement.get("applicability")
            if applicability == "NOT_ASSESSABLE":
                self.issue(
                    "STATE.ATTESTATION",
                    f"qualitative gate {check_id!r} is NOT_ASSESSABLE for the available inputs",
                    severity="WARNING" if self.check == "diagnostic" else "ERROR",
                    artifact=current_artifact_id,
                )
                continue
            if applicability == "NOT_APPLICABLE":
                continue
            matching = attestations_by_check.get(check_id, [])
            if self.check == "ready-to-release" and current_artifact is not None:
                matching = [
                    item
                    for item in matching
                    if item.get("artifact_id") == current_artifact_id
                    and item.get("artifact_hash") == current_artifact.get("candidate_hash")
                ]
                verification = current_artifact.get("verification")
                created_time = _timestamp_key(current_artifact.get("created_at"))
                verified_time = (
                    _timestamp_key(verification.get("completed_at"))
                    if isinstance(verification, dict)
                    else float("-inf")
                )
                in_sequence: list[dict[str, Any]] = []
                for item in matching:
                    item_time = _timestamp_key(item.get("timestamp"))
                    if item_time <= created_time or item_time >= verified_time:
                        self.issue(
                            "STATE.ATTESTATION_SEQUENCE",
                            f"attestation for {check_id!r} falls outside artifact creation-to-verification sequence",
                            artifact=current_artifact_id,
                        )
                    else:
                        in_sequence.append(item)
                matching = in_sequence
            elif self.check in {"diagnostic", "ready-to-implement"}:
                matching = [
                    item
                    for item in matching
                    if (item.get("source_id"), item.get("source_fingerprint")) in current_source_pairs
                    and _timestamp_key(item.get("timestamp")) > binding_cutoff
                ]
            latest_attestation = (
                max(
                    enumerate(matching),
                    key=lambda pair: (_timestamp_key(pair[1].get("timestamp")), pair[0]),
                )[1]
                if matching
                else None
            )
            if latest_attestation is None:
                self.issue(
                    "STATE.ATTESTATION",
                    f"applicable gate {check_id!r} lacks a current attestation bound to the review target",
                    artifact=current_artifact_id,
                )
            elif self.check == "diagnostic":
                if latest_attestation.get("result") == "NOT_APPLICABLE":
                    self.issue(
                        "STATE.ATTESTATION",
                        f"applicable diagnostic gate {check_id!r} cannot be attested NOT_APPLICABLE",
                        artifact=current_artifact_id,
                    )
            elif latest_attestation.get("result") != "PASS":
                self.issue(
                    "STATE.ATTESTATION",
                    f"applicable gate {check_id!r} lacks a current PASS attestation bound to the review target",
                    artifact=current_artifact_id,
                )

        if self.check == "ready-to-release":
            if current_artifact is not None and isinstance(current_artifact.get("verification"), dict):
                applicable = {
                    check_id
                    for check_id in RELEASE_GATE_IDS
                    if requirements.get(check_id, {}).get("applicability") == "APPLICABLE"
                }
                recorded = set(current_artifact["verification"].get("check_ids", []))
                for check_id in sorted(applicable - recorded):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        f"artifact verification record omits applicable release check {check_id!r}",
                        artifact=current_artifact_id,
                    )

    def _validate_diagnostic(self) -> None:
        if self.state.get("run", {}).get("operation") != "DIAGNOSE":
            self.issue(
                "STATE.DIAGNOSTIC_MODE",
                "diagnostic check requires run.operation DIAGNOSE",
                severity="WARNING",
            )
        if self.candidate is not None or self.diff_map is not None:
            self.issue(
                "STATE.DIAGNOSTIC_SIDECAR",
                "candidate/diff sidecars are ignored for a diagnostic validation",
                severity="WARNING",
            )

    def _validate_ready_to_implement(self) -> None:
        if self.state.get("run", {}).get("operation") not in {"RECEIPT", "IMPLEMENT"}:
            self.issue(
                "STATE.READY_TO_IMPLEMENT",
                "ready-to-implement requires run.operation RECEIPT or IMPLEMENT",
            )
        authorized = [
            decision for decision in self.decisions.values() if decision.get("decision_state") == "AUTHORIZED"
        ]
        if not authorized:
            self.issue("STATE.READY_TO_IMPLEMENT", "no decision is in AUTHORIZED state")
        for decision in authorized:
            if decision.get("support_status") != "SUPPORTED":
                self.issue(
                    "STATE.READY_TO_IMPLEMENT",
                    "authorized implementation set contains a decision without SUPPORTED evidence",
                    decision=decision,
                )
            if decision.get("source_impact") not in {"CURRENT", "UNCHANGED"}:
                self.issue(
                    "STATE.READY_TO_IMPLEMENT",
                    "authorized implementation set contains a stale or obsolete decision",
                    decision=decision,
                )

    def _validate_ready_to_release(self) -> None:
        if self.state.get("run", {}).get("operation") != "RELEASE":
            self.issue("STATE.RELEASE_MODE", "ready-to-release requires run.operation RELEASE")
        if self.candidate is None:
            self.issue("STATE.RELEASE_SIDECAR", "ready-to-release requires --candidate")
        elif not isinstance(self.candidate, dict):
            self.issue("STATE.RELEASE_SIDECAR", "candidate manifest root must be a JSON object")
        if self.diff_map is None:
            self.issue("STATE.RELEASE_SIDECAR", "ready-to-release requires --diff-map")
        elif not isinstance(self.diff_map, dict):
            self.issue("STATE.RELEASE_SIDECAR", "diff map root must be a JSON object")

        run = self.state.get("run", {})
        artifact_id = run.get("current_artifact_id")
        artifact = self.artifacts.get(artifact_id) if isinstance(artifact_id, str) else None
        if artifact is None:
            self.issue("STATE.RELEASE_ARTIFACT", "run.current_artifact_id must identify the release candidate")
            return
        if not artifact.get("actual_submission_artifact"):
            self.issue(
                "STATE.RELEASE_ARTIFACT",
                "release candidate is not designated as the actual submission artifact",
                artifact=artifact_id,
            )
        if artifact.get("artifact_status") != "VERIFIED":
            self.issue(
                "STATE.RELEASE_ARTIFACT",
                "exact release candidate is not VERIFIED",
                artifact=artifact_id,
            )
        current_content_hashes = {
            fingerprint
            for source in self.sources.values()
            if source.get("is_current") and source.get("content_authority")
            for fingerprint in (source.get("byte_hash"), source.get("extracted_text_hash"))
            if fingerprint is not None
        }
        if artifact.get("source_hash") not in current_content_hashes:
            self.issue(
                "STATE.RELEASE_ARTIFACT",
                "release candidate was not derived from a current content-authority source hash",
                artifact=artifact_id,
            )
        current_source_ids = set(self.state.get("run", {}).get("current_source_ids", []))
        if not current_source_ids.intersection(artifact.get("baseline_source_ids", [])):
            self.issue(
                "STATE.RELEASE_ARTIFACT",
                "release candidate does not identify any current source as its baseline",
                artifact=artifact_id,
            )
        verification = artifact.get("verification")
        if not isinstance(verification, dict) or not verification.get("actual_artifact_inspected"):
            self.issue(
                "STATE.RELEASE_ARTIFACT",
                "release verification did not inspect the actual submission artifact",
                artifact=artifact_id,
            )

        if self.source_root is None:
            self.issue(
                "STATE.EXACT_SOURCE_HASH",
                "ready-to-release requires a source root for authoritative source re-hashing",
                artifact=artifact_id,
            )
        else:
            root = self.source_root.resolve()
            for source_id in sorted(current_source_ids):
                source = self.sources.get(source_id)
                if not isinstance(source, dict) or not source.get("content_authority"):
                    continue
                declared_value = source.get("path")
                if not isinstance(declared_value, str):
                    self.issue(
                        "STATE.EXACT_SOURCE_HASH",
                        f"current source {source_id!r} has no resolvable path",
                        artifact=artifact_id,
                    )
                    continue
                declared = Path(declared_value)
                if declared.is_absolute():
                    self.issue(
                        "STATE.EXACT_SOURCE_HASH",
                        f"current source {source_id!r} must use a path relative to --source-root",
                        artifact=artifact_id,
                    )
                    continue
                try:
                    actual_path = (root / declared).resolve(strict=True)
                    actual_path.relative_to(root)
                    if not actual_path.is_file():
                        raise OSError("path is not a regular file")
                    source_bytes = actual_path.read_bytes()
                except (OSError, ValueError) as exc:
                    self.issue(
                        "STATE.EXACT_SOURCE_HASH",
                        f"cannot read authoritative source {declared_value!r}: {exc}",
                        artifact=artifact_id,
                    )
                    continue
                actual_hash = f"sha256:{hashlib.sha256(source_bytes).hexdigest()}"
                if actual_hash != source.get("byte_hash"):
                    self.issue(
                        "STATE.EXACT_SOURCE_HASH",
                        f"authoritative source {source_id!r} bytes do not match its registered byte_hash",
                        artifact=artifact_id,
                    )
                    continue
                if source.get("media_type") == "text/plain":
                    try:
                        text_hash = f"sha256:{hashlib.sha256(source_bytes.decode('utf-8').encode('utf-8')).hexdigest()}"
                    except UnicodeDecodeError as exc:
                        self.issue(
                            "STATE.EXACT_SOURCE_HASH",
                            f"text source {source_id!r} is not valid UTF-8: {exc}",
                            artifact=artifact_id,
                        )
                        continue
                    if text_hash != source.get("extracted_text_hash"):
                        self.issue(
                            "STATE.EXACT_SOURCE_HASH",
                            f"authoritative text source {source_id!r} does not match its extracted_text_hash",
                            artifact=artifact_id,
                        )
                        continue
                self.release_source_bytes[source_id] = source_bytes

        artifact_path_value = artifact.get("path")
        if self.artifact_root is None or not isinstance(artifact_path_value, str):
            self.issue(
                "STATE.EXACT_ARTIFACT_HASH",
                "ready-to-release requires a resolvable artifact root and candidate path",
                artifact=artifact_id,
            )
        else:
            declared_path = Path(artifact_path_value)
            if declared_path.is_absolute():
                self.issue(
                    "STATE.EXACT_ARTIFACT_HASH",
                    "candidate path must be relative to --artifact-root",
                    artifact=artifact_id,
                )
            try:
                root = self.artifact_root.resolve()
                actual_path = (root / declared_path).resolve(strict=True)
                actual_path.relative_to(root)
                if not actual_path.is_file():
                    raise OSError("path is not a regular file")
                candidate_bytes = actual_path.read_bytes()
                actual_hash = f"sha256:{hashlib.sha256(candidate_bytes).hexdigest()}"
            except (OSError, ValueError) as exc:
                self.issue(
                    "STATE.EXACT_ARTIFACT_HASH",
                    f"cannot read exact release artifact {artifact_path_value!r}: {exc}",
                    artifact=artifact_id,
                )
            else:
                if actual_hash != artifact.get("candidate_hash"):
                    self.issue(
                        "STATE.EXACT_ARTIFACT_HASH",
                        "exact release artifact bytes do not match the registered candidate_hash",
                        artifact=artifact_id,
                    )
                else:
                    self.release_candidate_bytes = candidate_bytes

        for decision in self.decisions.values():
            if decision.get("decision_state") == "AUTHORIZED":
                self.issue(
                    "STATE.AUTHORIZED_SUBSET",
                    "authorized decision remains unimplemented in the release candidate",
                    decision=decision,
                    artifact=artifact_id,
                )
            implementation = decision.get("implementation_result")
            if isinstance(implementation, dict) and decision.get("decision_state") != "SUPERSEDED":
                if decision.get("decision_state") != "VERIFIED":
                    self.issue(
                        "STATE.AUTHORIZED_SUBSET",
                        "current implemented decision must be VERIFIED before release",
                        decision=decision,
                        artifact=artifact_id,
                    )
                if (
                    implementation.get("artifact_id") != artifact_id
                    or implementation.get("candidate_hash") != artifact.get("candidate_hash")
                ):
                    self.issue(
                        "STATE.ARTIFACT_BINDING",
                        "current implemented decision is not bound to the exact release candidate",
                        decision=decision,
                        artifact=artifact_id,
                    )

        verification_time = (
            _timestamp_key(verification.get("completed_at"))
            if isinstance(verification, dict)
            else float("-inf")
        )
        created_time = _timestamp_key(artifact.get("created_at"))
        for local_fix_id, local_fix in self.local_fixes.items():
            if (
                local_fix.get("candidate_hash") != artifact.get("candidate_hash")
                or not local_fix.get("implemented_hunk_ids")
            ):
                continue
            check_id = f"local_fix_semantics:{local_fix_id}"
            matching = [
                (index, attestation)
                for index, attestation in enumerate(self.state.get("attestations", []))
                if isinstance(attestation, dict)
                and attestation.get("check_id") == check_id
                and attestation.get("artifact_id") == artifact_id
                and attestation.get("artifact_hash") == artifact.get("candidate_hash")
            ]
            for _, attestation in matching:
                attestation_time = _timestamp_key(attestation.get("timestamp"))
                if attestation_time <= created_time or attestation_time >= verification_time:
                    self.issue(
                        "STATE.ATTESTATION_SEQUENCE",
                        f"attestation for {check_id!r} falls outside artifact creation-to-verification sequence",
                        artifact=artifact_id,
                    )
            latest = (
                max(
                    matching,
                    key=lambda pair: (_timestamp_key(pair[1].get("timestamp")), pair[0]),
                )[1]
                if matching
                else None
            )
            latest_time = _timestamp_key(latest.get("timestamp")) if latest is not None else float("-inf")
            if (
                latest is None
                or latest.get("result") != "PASS"
                or latest_time <= created_time
                or latest_time >= verification_time
            ):
                self.issue(
                    "STATE.LOCAL_FIX",
                    f"implemented local fix {local_fix_id!r} lacks a current PASS attestation that it is non-semantic",
                    artifact=artifact_id,
                )

        self._validate_diff_map(artifact)

    def _validate_diff_map(self, artifact: dict[str, Any]) -> None:
        if not isinstance(self.diff_map, dict):
            if self.diff_map is not None:
                self.issue(
                    "STATE.DIFF_BINDING",
                    "diff map root must be a JSON object",
                    artifact=artifact.get("artifact_id"),
                )
            return
        artifact_id = artifact.get("artifact_id")
        candidate_hash = artifact.get("candidate_hash")
        if self.diff_map.get("schema_version") != "1.0.0":
            self.issue(
                "STATE.DIFF_BINDING",
                "diff map schema_version must be '1.0.0'",
                artifact=artifact_id,
            )
        if self.diff_map.get("candidate_artifact_id") != artifact_id or self.diff_map.get(
            "candidate_hash"
        ) != candidate_hash:
            self.issue(
                "STATE.DIFF_BINDING",
                "diff map is not bound to the exact release candidate ID/hash",
                artifact=artifact_id,
            )
        hunks = self.diff_map.get("hunks")
        if not isinstance(hunks, list):
            self.issue("STATE.DIFF_BINDING", "diff map must contain a hunks array", artifact=artifact_id)
            return
        self._validate_complete_diff_coverage(artifact, hunks)
        hunk_ids: set[str] = set()
        mapped_by_decision: dict[tuple[str, int], set[str]] = {}
        mapped_by_local_fix: dict[str, set[str]] = {}
        for hunk in hunks:
            if not isinstance(hunk, dict):
                self.issue("STATE.DIFF_BINDING", "every diff hunk must be an object", artifact=artifact_id)
                continue
            hunk_id = hunk.get("hunk_id")
            if not isinstance(hunk_id, str) or not hunk_id:
                self.issue("STATE.DIFF_BINDING", "diff hunk lacks a nonempty hunk_id", artifact=artifact_id)
                continue
            if hunk_id in hunk_ids:
                self.issue("STATE.DIFF_BINDING", f"duplicate diff hunk {hunk_id!r}", artifact=artifact_id)
            hunk_ids.add(hunk_id)
            kind = hunk.get("kind")
            if kind == "SUBSTANTIVE":
                hunk_decision_id = hunk.get("decision_id")
                hunk_revision = hunk.get("proposal_revision")
                if (
                    not isinstance(hunk_decision_id, str)
                    or not hunk_decision_id
                    or not isinstance(hunk_revision, int)
                    or isinstance(hunk_revision, bool)
                ):
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"substantive hunk {hunk_id!r} needs a string decision_id and integer proposal_revision",
                        artifact=artifact_id,
                    )
                    continue
                key = (hunk_decision_id, hunk_revision)
                decision = self.decisions.get(key)
                if decision is None:
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"substantive hunk {hunk_id!r} maps to an unknown decision revision",
                        artifact=artifact_id,
                    )
                    continue
                if decision.get("decision_state") != "VERIFIED" or not self._has_transition(
                    decision, "AUTHORIZED", current_source=True
                ):
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"substantive hunk {hunk_id!r} is not mapped to an authorized, verified decision",
                        decision=decision,
                        artifact=artifact_id,
                    )
                mapped_by_decision.setdefault(key, set()).add(hunk_id)
                if hunk.get("local_fix_id") is not None:
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"substantive hunk {hunk_id!r} cannot also map to a local fix",
                        decision=decision,
                        artifact=artifact_id,
                    )
            elif kind == "LOCAL_FIX":
                local_fix_id = hunk.get("local_fix_id")
                if not isinstance(local_fix_id, str):
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"local hunk {hunk_id!r} needs a string local_fix_id",
                        artifact=artifact_id,
                    )
                    continue
                local_fix = self.local_fixes.get(local_fix_id)
                if local_fix is None or not local_fix.get("authorized"):
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"local hunk {hunk_id!r} is not mapped to an authorized local-fix record",
                        artifact=artifact_id,
                    )
                elif (
                    hunk_id not in local_fix.get("implemented_hunk_ids", [])
                    or local_fix.get("candidate_hash") != candidate_hash
                ):
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"local hunk {hunk_id!r} is not bound to this candidate in the local-fix log",
                        artifact=artifact_id,
                    )
                mapped_by_local_fix.setdefault(local_fix_id, set()).add(hunk_id)
                if hunk.get("decision_id") is not None or hunk.get("proposal_revision") is not None:
                    self.issue(
                        "STATE.DIFF_AUTHORIZATION",
                        f"local hunk {hunk_id!r} cannot also map to a substantive decision",
                        artifact=artifact_id,
                    )
            else:
                self.issue(
                    "STATE.DIFF_AUTHORIZATION",
                    f"hunk {hunk_id!r} has invalid kind {kind!r}",
                    artifact=artifact_id,
                )

        for key, decision in self.decisions.items():
            implementation = decision.get("implementation_result")
            if not isinstance(implementation, dict):
                continue
            if (
                decision.get("decision_state") == "SUPERSEDED"
                and (
                    implementation.get("artifact_id") != artifact_id
                    or implementation.get("candidate_hash") != candidate_hash
                )
            ):
                continue
            expected = set(implementation.get("diff_hunk_ids", []))
            mapped = mapped_by_decision.get(key, set())
            if expected != mapped:
                self.issue(
                    "STATE.DIFF_BINDING",
                    f"implementation_result hunks {sorted(expected)} do not match diff-map hunks {sorted(mapped)}",
                    decision=decision,
                    artifact=artifact_id,
                )
        for local_fix_id, local_fix in self.local_fixes.items():
            if local_fix.get("candidate_hash") != candidate_hash:
                continue
            expected = set(local_fix.get("implemented_hunk_ids", []))
            mapped = mapped_by_local_fix.get(local_fix_id, set())
            if expected != mapped:
                self.issue(
                    "STATE.DIFF_BINDING",
                    f"local-fix log hunks {sorted(expected)} do not match diff-map hunks {sorted(mapped)}",
                    artifact=artifact_id,
                )

    def _validate_complete_diff_coverage(
        self, artifact: dict[str, Any], hunks: list[Any]
    ) -> None:
        """Require exact mapped coverage of every text-line or binary-byte delta."""

        artifact_id = artifact.get("artifact_id")
        baseline_ids = [
            source_id
            for source_id in artifact.get("baseline_source_ids", [])
            if source_id in self.release_source_bytes
        ]
        if len(baseline_ids) != 1 or self.release_candidate_bytes is None:
            self.issue(
                "STATE.DIFF_COVERAGE",
                "direct diff verification requires exactly one re-hashed content baseline and readable candidate bytes",
                artifact=artifact_id,
            )
            return
        baseline_id = baseline_ids[0]
        baseline_bytes = self.release_source_bytes[baseline_id]
        baseline_hash = f"sha256:{hashlib.sha256(baseline_bytes).hexdigest()}"
        candidate_hash = f"sha256:{hashlib.sha256(self.release_candidate_bytes).hexdigest()}"
        comparison_mode = self.diff_map.get("comparison_mode")
        artifact_format = artifact.get("format")
        expected_mode = (
            "UTF8_TEXT_LINES"
            if artifact_format in {"TXT", "MD", "JSON"}
            else "BINARY_BYTES"
        )
        if (
            comparison_mode != expected_mode
            or self.diff_map.get("baseline_source_id") != baseline_id
            or self.diff_map.get("baseline_hash") != baseline_hash
            or self.diff_map.get("candidate_hash") != candidate_hash
        ):
            self.issue(
                "STATE.DIFF_COVERAGE",
                f"diff map is not bound to the exact re-hashed baseline/candidate {expected_mode} comparison",
                artifact=artifact_id,
            )
        if expected_mode == "UTF8_TEXT_LINES":
            try:
                baseline_units: Any = baseline_bytes.decode("utf-8").splitlines(keepends=True)
                candidate_units: Any = self.release_candidate_bytes.decode("utf-8").splitlines(
                    keepends=True
                )
            except UnicodeDecodeError as exc:
                self.issue(
                    "STATE.DIFF_COVERAGE",
                    f"UTF8_TEXT_LINES comparison cannot decode baseline/candidate: {exc}",
                    artifact=artifact_id,
                )
                return
            canonical_delta_spans = [
                (operation, a0, a1, b0, b1)
                for operation, a0, a1, b0, b1 in difflib.SequenceMatcher(
                    None, baseline_units, candidate_units, autojunk=False
                ).get_opcodes()
                if operation != "equal"
            ]
        else:
            baseline_units = baseline_bytes
            candidate_units = self.release_candidate_bytes
            # A general-purpose minimal binary diff is not linear in the worst
            # case, and SequenceMatcher over raw PDF/DOCX bytes becomes
            # quadratic on realistic repetitive payloads. Binary coverage is
            # therefore proof-carrying: declared monotone spans, exact slice
            # hashes, byte-identical gaps, and edge-minimal edit-group bounds
            # together prove that no byte delta is outside a mapped hunk.
            canonical_delta_spans = None

        declared: list[tuple[str, int, int, int, int, dict[str, Any]]] = []
        malformed = False
        for hunk in hunks:
            if not isinstance(hunk, dict):
                malformed = True
                continue
            key_values = (
                hunk.get("operation"),
                hunk.get("baseline_start"),
                hunk.get("baseline_end"),
                hunk.get("candidate_start"),
                hunk.get("candidate_end"),
            )
            if (
                key_values[0] not in {"replace", "delete", "insert"}
                or any(not isinstance(value, int) or isinstance(value, bool) for value in key_values[1:])
            ):
                malformed = True
                continue
            operation, a0, a1, b0, b1 = key_values
            if (
                a0 < 0
                or b0 < 0
                or a1 < a0
                or b1 < b0
                or a1 > len(baseline_units)
                or b1 > len(candidate_units)
            ):
                malformed = True
                continue
            slices_equal = (
                canonical_delta_spans is not None
                and _ranges_equal(
                    baseline_units,
                    a0,
                    a1,
                    candidate_units,
                    b0,
                    b1,
                )
            )
            operation_shape_valid = (
                operation == "replace"
                and a0 < a1
                and b0 < b1
                and not slices_equal
            ) or (
                operation == "delete" and a0 < a1 and b0 == b1
            ) or (
                operation == "insert" and a0 == a1 and b0 < b1
            )
            if not operation_shape_valid:
                malformed = True
            declared.append((operation, a0, a1, b0, b1, hunk))
        declared = sorted(declared, key=lambda item: (item[1], item[3], item[2], item[4]))
        if canonical_delta_spans is not None:
            for _, a0, a1, b0, b1, _ in declared:
                if not any(
                    canonical_a0 <= a0 <= a1 <= canonical_a1
                    and canonical_b0 <= b0 <= b1 <= canonical_b1
                    for (
                        _,
                        canonical_a0,
                        canonical_a1,
                        canonical_b0,
                        canonical_b1,
                    ) in canonical_delta_spans
                ):
                    malformed = True
        else:
            # Treat directly adjacent binary hunks as one edit group for
            # boundary minimality. Without this normalization, a delete of the
            # whole baseline followed by an insert of the whole candidate (or
            # the reverse order) could absorb unchanged prefix/suffix bytes and
            # evade the single-replace check.
            binary_groups: list[list[tuple[str, int, int, int, int, dict[str, Any]]]] = []
            for item in declared:
                if (
                    not binary_groups
                    or item[1] != binary_groups[-1][-1][2]
                    or item[3] != binary_groups[-1][-1][4]
                ):
                    binary_groups.append([item])
                else:
                    binary_groups[-1].append(item)
            for group in binary_groups:
                _, a0, _, b0, _, _ = group[0]
                _, _, a1, _, b1, _ = group[-1]
                if (
                    a0 < a1
                    and b0 < b1
                    and (
                        baseline_units[a0] == candidate_units[b0]
                        or baseline_units[a1 - 1] == candidate_units[b1 - 1]
                    )
                ):
                    # Stable boundary bytes belong in the verified unchanged
                    # gaps, not inside a broad replacement or composite edit.
                    malformed = True
        baseline_cursor = 0
        candidate_cursor = 0
        for _, a0, a1, b0, b1, hunk in declared:
            if a0 < baseline_cursor or b0 < candidate_cursor:
                malformed = True
                continue
            if not _ranges_equal(
                baseline_units,
                baseline_cursor,
                a0,
                candidate_units,
                candidate_cursor,
                b0,
            ):
                malformed = True
            expected_baseline_hash = _range_sha256(baseline_units, a0, a1)
            expected_candidate_hash = _range_sha256(candidate_units, b0, b1)
            if (
                hunk.get("baseline_lines_hash") != expected_baseline_hash
                or hunk.get("candidate_lines_hash") != expected_candidate_hash
            ):
                self.issue(
                    "STATE.DIFF_COVERAGE",
                    f"hunk {hunk.get('hunk_id')!r} slice hashes do not match the exact declared slices",
                    artifact=artifact_id,
                )
            baseline_cursor = a1
            candidate_cursor = b1
        if not _ranges_equal(
            baseline_units,
            baseline_cursor,
            len(baseline_units),
            candidate_units,
            candidate_cursor,
            len(candidate_units),
        ):
            malformed = True
        if malformed:
            self.issue(
                "STATE.DIFF_COVERAGE",
                "declared hunks do not reconstruct the complete baseline-to-candidate delta with unchanged gaps",
                artifact=artifact_id,
            )


class _MachineReadableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        issue = Issue("INPUT.ARGUMENT", "ERROR", None, None, message)
        raise SystemExit(_emit("invocation", [issue], input_error=True))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _MachineReadableArgumentParser(description="Validate GatedSprint v2 state and sidecars")
    parser.add_argument("--state", type=Path, required=True, help="gatedsprint-state.json")
    parser.add_argument("--baseline", type=Path, required=True, help="baseline-manifest.json")
    parser.add_argument("--candidate", type=Path, help="candidate-manifest.json")
    parser.add_argument("--diff-map", type=Path, help="diff-map.json")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="base directory for relative candidate artifact paths (defaults to candidate-manifest directory)",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        help="base directory for relative authoritative source paths (defaults to baseline-manifest directory)",
    )
    parser.add_argument(
        "--check",
        required=True,
        choices=("diagnostic", "ready-to-implement", "ready-to-release"),
    )
    return parser.parse_args(argv)


def _emit(check: str, issues: Iterable[Issue], *, input_error: bool = False) -> int:
    issue_list = list(issues)
    errors = sum(issue.severity == "ERROR" for issue in issue_list)
    warnings = sum(issue.severity == "WARNING" for issue in issue_list)
    result = "FAIL" if errors else "PASS"
    payload = {
        "check": check,
        "result": result,
        "error_count": errors,
        "warning_count": warnings,
        "issues": [asdict(issue) for issue in issue_list],
    }
    print(json.dumps(payload, sort_keys=True))
    print(
        f"GatedSprint {check}: {result} ({errors} error{'s' if errors != 1 else ''}, "
        f"{warnings} warning{'s' if warnings != 1 else ''})",
        file=sys.stderr,
    )
    if input_error:
        return 2
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "gatedsprint-state.schema.json"
    loaded: dict[str, Any] = {}
    input_issues: list[Issue] = []
    requested = {
        "state": args.state,
        "baseline": args.baseline,
        "candidate": args.candidate,
        "diff_map": args.diff_map,
        "schema": schema_path,
    }
    for label, path in requested.items():
        if path is None:
            continue
        try:
            loaded[label] = _load_json(path)
        except FileNotFoundError:
            input_issues.append(
                Issue("INPUT.FILE", "ERROR", None, None, f"{label} file not found: {path}")
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            input_issues.append(
                Issue("INPUT.JSON", "ERROR", None, None, f"cannot read {label} JSON {path}: {exc}")
            )
    if input_issues:
        return _emit(args.check, input_issues, input_error=True)

    state = loaded.get("state")
    baseline = loaded.get("baseline")
    schema = loaded.get("schema")
    if not isinstance(state, dict) or not isinstance(baseline, dict) or not isinstance(schema, dict):
        issue = Issue("INPUT.JSON", "ERROR", None, None, "state, baseline, and schema roots must be objects")
        return _emit(args.check, [issue], input_error=True)

    validator = StateValidator(
        state=state,
        baseline=baseline,
        candidate=loaded.get("candidate"),
        diff_map=loaded.get("diff_map"),
        check=args.check,
        schema=schema,
        artifact_root=(
            args.artifact_root.resolve()
            if args.artifact_root is not None
            else args.candidate.resolve().parent
            if args.candidate is not None
            else None
        ),
        source_root=(
            args.source_root.resolve()
            if args.source_root is not None
            else args.baseline.resolve().parent
        ),
    )
    return _emit(args.check, validator.run())


if __name__ == "__main__":
    raise SystemExit(main())
