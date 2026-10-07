"""Canonical state interfaces and dependency-free implementations."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, TypeVar, runtime_checkable

from .changes import detect_evaluation_changes, detect_material_changes
from .identity import (
    are_duplicate_jobs,
    canonical_job_identity,
    coerce_job,
    merge_job_records,
    normalize_text,
)
from .models import (
    ApplicationRecord,
    ChangeRecord,
    InstitutionCoverageRecord,
    JobRecord,
    RunRecord,
    SourceCoverageRecord,
    UpsertResult,
    json_safe,
    utc_now,
)


TABLES = (
    "Jobs",
    "Runs",
    "Changes",
    "SourceCoverage",
    "InstitutionCoverage",
    "Applications",
)
STATE_SCHEMA_VERSION = 1


class StateStoreError(RuntimeError):
    pass


@runtime_checkable
class StateStore(Protocol):
    def upsert_job(
        self, job: JobRecord | Mapping[str, Any], *, record_changes: bool = True
    ) -> UpsertResult: ...

    def get_job(self, job_id: str) -> JobRecord | None: ...

    def list_jobs(self) -> list[JobRecord]: ...

    def record_run(self, run: RunRecord | Mapping[str, Any]) -> RunRecord: ...

    def list_runs(self) -> list[RunRecord]: ...

    def record_change(self, change: ChangeRecord | Mapping[str, Any]) -> ChangeRecord: ...

    def list_changes(self, *, job_id: str | None = None) -> list[ChangeRecord]: ...

    def upsert_source_coverage(
        self, coverage: SourceCoverageRecord | Mapping[str, Any]
    ) -> SourceCoverageRecord: ...

    def list_source_coverage(self) -> list[SourceCoverageRecord]: ...

    def upsert_institution_coverage(
        self, coverage: InstitutionCoverageRecord | Mapping[str, Any]
    ) -> InstitutionCoverageRecord: ...

    def list_institution_coverage(self) -> list[InstitutionCoverageRecord]: ...

    def upsert_application(
        self, application: ApplicationRecord | Mapping[str, Any]
    ) -> ApplicationRecord: ...

    def list_applications(self) -> list[ApplicationRecord]: ...

    def snapshot(self) -> dict[str, Any]: ...


def _coerce(model: type[Any], value: Any) -> Any:
    return value if isinstance(value, model) else model.from_dict(value)


def _has_evaluation_snapshot(job: JobRecord) -> bool:
    return bool(
        job.evaluation
        or job.fit_score is not None
        or job.tier
        or job.strongest_matches
        or job.meaningful_gaps
        or job.hard_blockers
    )


def _evaluation_snapshot(job: JobRecord, *, version: int) -> dict[str, Any]:
    return {
        "version": version,
        "superseded_at": utc_now(),
        "evaluation": copy.deepcopy(job.evaluation),
        "fit_score": job.fit_score,
        "tier": job.tier,
        "strongest_matches": copy.deepcopy(job.strongest_matches),
        "meaningful_gaps": copy.deepcopy(job.meaningful_gaps),
        "hard_blockers": copy.deepcopy(job.hard_blockers),
    }


def _evaluation_semantics(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    """Return score semantics without run-local observation timestamps."""

    return {
        str(key): copy.deepcopy(value)
        for key, value in evaluation.items()
        if key not in {"evaluated_at"}
    }


def _merge_evaluation_history(*collections: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    seen: set[str] = set()
    for collection in collections:
        for item in collection:
            marker = json.dumps(json_safe(item), sort_keys=True, ensure_ascii=False)
            if marker not in seen:
                seen.add(marker)
                history.append(copy.deepcopy(dict(item)))
    return history


class InMemoryStateStore:
    """Thread-safe canonical state suitable for tests and ephemeral runs."""

    def __init__(self, initial_state: Mapping[str, Any] | None = None) -> None:
        self._lock = threading.RLock()
        self._tables: dict[str, Any] = {
            "Jobs": {},
            "Runs": {},
            "Changes": [],
            "SourceCoverage": {},
            "InstitutionCoverage": {},
            "Applications": {},
        }
        if initial_state:
            self._load_snapshot(initial_state)

    def _load_snapshot(self, state: Mapping[str, Any]) -> None:
        tables = state.get("tables", state)
        if not isinstance(tables, Mapping):
            raise StateStoreError("State snapshot must contain a tables mapping")
        with self._lock:
            self._tables = {
                "Jobs": {},
                "Runs": {},
                "Changes": [],
                "SourceCoverage": {},
                "InstitutionCoverage": {},
                "Applications": {},
            }
            for raw in tables.get("Jobs", []):
                job = JobRecord.from_dict(raw)
                job_id = job.canonical_id or canonical_job_identity(job)
                job.canonical_id = job_id
                self._tables["Jobs"][job_id] = job.to_dict()
            for raw in tables.get("Runs", []):
                run = RunRecord.from_dict(raw)
                self._tables["Runs"][run.run_id] = run.to_dict()
            for raw in tables.get("Changes", []):
                self._tables["Changes"].append(ChangeRecord.from_dict(raw).to_dict())
            for raw in tables.get("SourceCoverage", []):
                coverage = SourceCoverageRecord.from_dict(raw)
                self._tables["SourceCoverage"][coverage.source_id] = coverage.to_dict()
            for raw in tables.get("InstitutionCoverage", []):
                coverage = InstitutionCoverageRecord.from_dict(raw)
                key = normalize_text(coverage.institution)
                self._tables["InstitutionCoverage"][key] = coverage.to_dict()
            for raw in tables.get("Applications", []):
                application = ApplicationRecord.from_dict(raw)
                self._tables["Applications"][application.job_id] = application.to_dict()

    def _matching_job_id(self, incoming: JobRecord) -> str | None:
        if incoming.canonical_id and incoming.canonical_id in self._tables["Jobs"]:
            return incoming.canonical_id
        for job_id, value in self._tables["Jobs"].items():
            if are_duplicate_jobs(JobRecord.from_dict(value), incoming):
                return job_id
        return None

    def upsert_job(
        self, job: JobRecord | Mapping[str, Any], *, record_changes: bool = True
    ) -> UpsertResult:
        incoming = copy.deepcopy(coerce_job(job))
        with self._lock:
            matched_id = self._matching_job_id(incoming)
            if matched_id is None:
                job_id = incoming.canonical_id or canonical_job_identity(incoming)
                if job_id in self._tables["Jobs"]:
                    matched_id = job_id
                else:
                    incoming.canonical_id = job_id
                    if incoming.evaluation and incoming.evaluation_version <= 0:
                        incoming.evaluation_version = 1
                    self._tables["Jobs"][job_id] = incoming.to_dict()
                    return UpsertResult(
                        action="inserted", job_id=job_id, record=incoming.to_dict()
                    )

            previous = JobRecord.from_dict(self._tables["Jobs"][matched_id])
            incoming.canonical_id = matched_id
            merged = merge_job_records(previous, incoming)
            # Human decisions are durable unless an explicit clear marker is supplied.
            clear_override = incoming.extra.get("clear_manual_override") is True
            if clear_override:
                merged.rejected = incoming.rejected
                # This is a one-shot command marker, not durable state.
                merged.extra.pop("clear_manual_override", None)
            elif previous.rejected:
                merged.rejected = True
            if previous.manual_review_state and not incoming.manual_review_state:
                merged.manual_review_state = previous.manual_review_state
            if previous.application and not incoming.application:
                merged.application = copy.deepcopy(previous.application)
            update_source = incoming.extra.get("update_source")
            evaluation_changes = detect_evaluation_changes(
                previous,
                merged,
                source=update_source,
            )
            if (
                incoming.evaluation
                and json_safe(_evaluation_semantics(previous.evaluation))
                != json_safe(_evaluation_semantics(merged.evaluation))
                and not evaluation_changes
            ):
                # Preserve version/history even when only a category score or
                # other nested evaluation detail changed outside the default
                # notification fields.
                evaluation_changes = detect_evaluation_changes(
                    previous,
                    merged,
                    fields=("evaluation",),
                    source=update_source,
                )
            if incoming.evaluation:
                prior_has_evaluation = _has_evaluation_snapshot(previous)
                prior_version = previous.evaluation_version or (
                    1 if prior_has_evaluation else 0
                )
                history = _merge_evaluation_history(
                    previous.evaluation_history,
                    incoming.evaluation_history,
                )
                if evaluation_changes and prior_has_evaluation:
                    history.append(
                        _evaluation_snapshot(previous, version=prior_version)
                    )
                merged.evaluation_history = history
                if evaluation_changes:
                    merged.evaluation_version = max(
                        prior_version + 1,
                        incoming.evaluation_version,
                        1,
                    )
                else:
                    merged.evaluation_version = max(
                        prior_version,
                        incoming.evaluation_version,
                    )
            changes = []
            if record_changes:
                changes.extend(
                    detect_material_changes(
                        previous,
                        merged,
                        source=update_source,
                    )
                )
                changes.extend(evaluation_changes)
            self._tables["Jobs"][matched_id] = merged.to_dict()
            for change in changes:
                self._tables["Changes"].append(change.to_dict())
            action = "unchanged" if previous.to_dict() == merged.to_dict() else "updated"
            return UpsertResult(
                action=action,
                job_id=matched_id,
                record=merged.to_dict(),
                previous=previous.to_dict(),
            )

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            value = self._tables["Jobs"].get(job_id)
            return JobRecord.from_dict(copy.deepcopy(value)) if value is not None else None

    def list_jobs(self) -> list[JobRecord]:
        with self._lock:
            return [
                JobRecord.from_dict(copy.deepcopy(value))
                for _, value in sorted(self._tables["Jobs"].items())
            ]

    def record_run(self, run: RunRecord | Mapping[str, Any]) -> RunRecord:
        value = copy.deepcopy(_coerce(RunRecord, run))
        with self._lock:
            self._tables["Runs"][value.run_id] = value.to_dict()
        return copy.deepcopy(value)

    def list_runs(self) -> list[RunRecord]:
        with self._lock:
            return [
                RunRecord.from_dict(copy.deepcopy(value))
                for _, value in sorted(self._tables["Runs"].items())
            ]

    def record_change(self, change: ChangeRecord | Mapping[str, Any]) -> ChangeRecord:
        value = copy.deepcopy(_coerce(ChangeRecord, change))
        with self._lock:
            marker = value.to_dict()
            if marker not in self._tables["Changes"]:
                self._tables["Changes"].append(marker)
        return copy.deepcopy(value)

    def list_changes(self, *, job_id: str | None = None) -> list[ChangeRecord]:
        with self._lock:
            values = self._tables["Changes"]
            if job_id is not None:
                values = [value for value in values if value.get("job_id") == job_id]
            return [ChangeRecord.from_dict(copy.deepcopy(value)) for value in values]

    def upsert_source_coverage(
        self, coverage: SourceCoverageRecord | Mapping[str, Any]
    ) -> SourceCoverageRecord:
        value = copy.deepcopy(_coerce(SourceCoverageRecord, coverage))
        with self._lock:
            old = self._tables["SourceCoverage"].get(value.source_id, {})
            merged = dict(old)
            merged.update(
                {key: item for key, item in value.to_dict().items() if item is not None}
            )
            self._tables["SourceCoverage"][value.source_id] = merged
            return SourceCoverageRecord.from_dict(copy.deepcopy(merged))

    def list_source_coverage(self) -> list[SourceCoverageRecord]:
        with self._lock:
            return [
                SourceCoverageRecord.from_dict(copy.deepcopy(value))
                for _, value in sorted(self._tables["SourceCoverage"].items())
            ]

    def upsert_institution_coverage(
        self, coverage: InstitutionCoverageRecord | Mapping[str, Any]
    ) -> InstitutionCoverageRecord:
        value = copy.deepcopy(_coerce(InstitutionCoverageRecord, coverage))
        key = normalize_text(value.institution)
        with self._lock:
            old = self._tables["InstitutionCoverage"].get(key, {})
            merged = dict(old)
            merged.update(
                {
                    field: item
                    for field, item in value.to_dict().items()
                    if item is not None and (item != [] or not old.get(field))
                }
            )
            self._tables["InstitutionCoverage"][key] = merged
            return InstitutionCoverageRecord.from_dict(copy.deepcopy(merged))

    def list_institution_coverage(self) -> list[InstitutionCoverageRecord]:
        with self._lock:
            return [
                InstitutionCoverageRecord.from_dict(copy.deepcopy(value))
                for _, value in sorted(self._tables["InstitutionCoverage"].items())
            ]

    def upsert_application(
        self, application: ApplicationRecord | Mapping[str, Any]
    ) -> ApplicationRecord:
        value = copy.deepcopy(_coerce(ApplicationRecord, application))
        with self._lock:
            old = self._tables["Applications"].get(value.job_id, {})
            merged = dict(old)
            incoming = value.to_dict()
            # Generating a package must never imply submission.
            if old.get("status") not in {None, "", "not_started"} and incoming.get(
                "status"
            ) in {
                None,
                "",
                "not_started",
            }:
                incoming["status"] = old.get("status")
                if old.get("submitted_at"):
                    incoming["submitted_at"] = old.get("submitted_at")
            merged.update(
                {
                    key: item
                    for key, item in incoming.items()
                    if item is not None and (item not in ([], {}) or not old.get(key))
                }
            )
            self._tables["Applications"][value.job_id] = merged
            return ApplicationRecord.from_dict(copy.deepcopy(merged))

    def list_applications(self) -> list[ApplicationRecord]:
        with self._lock:
            return [
                ApplicationRecord.from_dict(copy.deepcopy(value))
                for _, value in sorted(self._tables["Applications"].items())
            ]

    def read_table(self, table: str) -> list[dict[str, Any]]:
        if table not in TABLES:
            raise KeyError(f"Unknown state table: {table}")
        with self._lock:
            values = self._tables[table]
            if isinstance(values, Mapping):
                values = [value for _, value in sorted(values.items())]
            return copy.deepcopy(list(values))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": STATE_SCHEMA_VERSION,
                "tables": {table: self.read_table(table) for table in TABLES},
            }


R = TypeVar("R")


class JsonFileStateStore(InMemoryStateStore):
    """Atomic JSON state store for a caller-supplied private file path."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        create: bool = True,
        indent: int | None = 2,
    ) -> None:
        if path is None or not str(path).strip():
            raise ValueError("JsonFileStateStore requires a caller-supplied private path")
        self.path = Path(path).expanduser()
        self.indent = indent
        super().__init__()
        if self.path.exists():
            self._reload()
        elif create:
            self._persist()

    def _decode(self, raw: bytes) -> Mapping[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StateStoreError(f"Invalid JSON state at {self.path}: {exc}") from exc
        if not isinstance(value, Mapping):
            raise StateStoreError("JSON state root must be a mapping")
        version = value.get("schema_version", STATE_SCHEMA_VERSION)
        if version != STATE_SCHEMA_VERSION:
            raise StateStoreError(f"Unsupported state schema version: {version!r}")
        tables = value.get("tables", value)
        if not isinstance(tables, Mapping):
            raise StateStoreError("JSON state must contain a tables mapping")
        for table in TABLES:
            if table in tables and not isinstance(tables[table], list):
                raise StateStoreError(f"State table {table} must be a list")
        return value

    def _reload(self) -> None:
        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise StateStoreError(f"Unable to read state {self.path}: {exc}") from exc
        self._load_snapshot(self._decode(raw))

    def _encoded_snapshot(self) -> bytes:
        payload = json_safe(self.snapshot())
        text = json.dumps(
            payload,
            ensure_ascii=False,
            indent=self.indent,
            sort_keys=True,
            allow_nan=False,
        )
        raw = (text + "\n").encode("utf-8")
        self._decode(raw)
        return raw

    def _restore_bytes(self, previous: bytes | None) -> None:
        if previous is None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.restore-", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(previous)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    def _persist(self) -> None:
        raw = self._encoded_snapshot()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StateStoreError(f"Unable to create state directory: {exc}") from exc
        previous: bytes | None = None
        if self.path.exists():
            try:
                previous = self.path.read_bytes()
            except OSError as exc:
                raise StateStoreError(f"Unable to preserve prior state: {exc}") from exc
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.write-", dir=str(self.path.parent)
        )
        replaced = False
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            replaced = True
            read_back = self.path.read_bytes()
            self._decode(read_back)
            if read_back != raw:
                raise StateStoreError("State read-back did not match the atomic write")
        except Exception as exc:
            if replaced:
                self._restore_bytes(previous)
            if isinstance(exc, StateStoreError):
                raise
            raise StateStoreError(f"Atomic state write failed: {exc}") from exc
        finally:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    def _transaction(self, operation: Callable[[], R]) -> R:
        with self._lock:
            if self.path.exists():
                self._reload()
            prior_tables = copy.deepcopy(self._tables)
            try:
                result = operation()
                self._persist()
                # Validate through the normal loader and keep that canonical copy.
                self._reload()
                return result
            except Exception:
                self._tables = prior_tables
                raise

    def upsert_job(
        self, job: JobRecord | Mapping[str, Any], *, record_changes: bool = True
    ) -> UpsertResult:
        return self._transaction(
            lambda: super(JsonFileStateStore, self).upsert_job(
                job, record_changes=record_changes
            )
        )

    def record_run(self, run: RunRecord | Mapping[str, Any]) -> RunRecord:
        return self._transaction(lambda: super(JsonFileStateStore, self).record_run(run))

    def record_change(self, change: ChangeRecord | Mapping[str, Any]) -> ChangeRecord:
        return self._transaction(
            lambda: super(JsonFileStateStore, self).record_change(change)
        )

    def upsert_source_coverage(
        self, coverage: SourceCoverageRecord | Mapping[str, Any]
    ) -> SourceCoverageRecord:
        return self._transaction(
            lambda: super(JsonFileStateStore, self).upsert_source_coverage(coverage)
        )

    def upsert_institution_coverage(
        self, coverage: InstitutionCoverageRecord | Mapping[str, Any]
    ) -> InstitutionCoverageRecord:
        return self._transaction(
            lambda: super(JsonFileStateStore, self).upsert_institution_coverage(coverage)
        )

    def upsert_application(
        self, application: ApplicationRecord | Mapping[str, Any]
    ) -> ApplicationRecord:
        return self._transaction(
            lambda: super(JsonFileStateStore, self).upsert_application(application)
        )
