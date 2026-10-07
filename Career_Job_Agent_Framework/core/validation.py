"""Small dependency-free validation helpers for public configuration/models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str
    code: str = "invalid"


class SchemaValidationError(ValueError):
    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{item.path}: {item.message}" for item in self.issues)
        super().__init__(summary or "Schema validation failed")


def validate_mapping(
    value: Any,
    *,
    required: Sequence[str] = (),
    field_types: Mapping[str, type | tuple[type, ...]] | None = None,
    path: str = "$",
    raise_on_error: bool = True,
) -> list[ValidationIssue]:
    """Validate only required keys and declared types, leaving extensions open."""

    issues: list[ValidationIssue] = []
    if not isinstance(value, Mapping):
        issues.append(ValidationIssue(path, "expected a mapping", "type"))
    else:
        for key in required:
            if key not in value or value[key] is None or value[key] == "":
                issues.append(
                    ValidationIssue(f"{path}.{key}", "required value is missing", "required")
                )
        for key, expected in (field_types or {}).items():
            if key in value and value[key] is not None and not isinstance(value[key], expected):
                if isinstance(expected, tuple):
                    names = ", ".join(item.__name__ for item in expected)
                else:
                    names = expected.__name__
                issues.append(
                    ValidationIssue(
                        f"{path}.{key}",
                        f"expected {names}; got {type(value[key]).__name__}",
                        "type",
                    )
                )
    if issues and raise_on_error:
        raise SchemaValidationError(issues)
    return issues


def require_json_mapping(value: Any, *, path: str = "$") -> Mapping[str, Any]:
    validate_mapping(value, path=path)
    return value
