"""Configurable public-release privacy and secret checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Pattern

from .models import JsonModel


DEFAULT_SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("private_key", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("aws_access_key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    (
        "assigned_secret",
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}",
    ),
    # Split the local-path markers so this source file does not match the
    # patterns it defines when the release gate scans changed public files.
    ("mac_local_path", r"/" r"Users/[^/\s]+/"),
    ("windows_local_path", r"(?i)\b[A-Z]:\\" r"Users\\[^\\\s]+\\"),
)

MAX_CONFIGURED_RULES = 256
MAX_CONFIGURED_RULE_LENGTH = 4_096

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "credential",
        "credentials",
    }
)


@dataclass
class PrivacyFinding(JsonModel):
    kind: str = "privacy"
    message: str = ""
    location: str | None = None
    pattern: str | None = None


class PrivacyViolation(ValueError):
    def __init__(self, findings: Iterable[PrivacyFinding]) -> None:
        self.findings = tuple(findings)
        summary = "; ".join(
            f"{item.location or '<value>'}: {item.message}" for item in self.findings
        )
        super().__init__(summary or "Privacy guard rejected content")


class PrivacyConfigError(ValueError):
    """Raised without echoing a potentially sensitive configured rule."""


def _normalize_rules(value: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        raise PrivacyConfigError(f"{field_name} must be a sequence of strings")
    try:
        rules = tuple(value)
    except TypeError as exc:
        raise PrivacyConfigError(f"{field_name} must be a sequence of strings") from exc
    if len(rules) > MAX_CONFIGURED_RULES:
        raise PrivacyConfigError(f"{field_name} contains too many rules")
    if any(not isinstance(item, str) for item in rules):
        raise PrivacyConfigError(f"{field_name} must contain only strings")
    if any(len(item) > MAX_CONFIGURED_RULE_LENGTH for item in rules):
        raise PrivacyConfigError(f"{field_name} contains an oversized rule")
    return tuple(item for item in rules if item)


def _config_bool(value: Any, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PrivacyConfigError(f"{field_name} must be a boolean")
    return value


class PrivacyGuard:
    """Scan explicitly supplied public content; never discovers private files."""

    def __init__(
        self,
        *,
        forbidden_literals: Iterable[str] = (),
        forbidden_regexes: Iterable[str] = (),
        include_default_secret_patterns: bool = True,
        case_sensitive_literals: bool = False,
    ) -> None:
        self.forbidden_literals = _normalize_rules(
            forbidden_literals,
            field_name="forbidden_literals",
        )
        configured_regexes = _normalize_rules(
            forbidden_regexes,
            field_name="forbidden_regexes",
        )
        self.case_sensitive_literals = case_sensitive_literals
        expressions: list[tuple[str, str]] = []
        if include_default_secret_patterns:
            expressions.extend(DEFAULT_SECRET_PATTERNS)
        expressions.extend(("configured_regex", item) for item in configured_regexes)
        compiled: list[tuple[str, Pattern[str]]] = []
        for kind, expression in expressions:
            try:
                compiled.append((kind, re.compile(expression)))
            except re.error:
                raise PrivacyConfigError(
                    "privacy guard contains an invalid regular expression"
                ) from None
        self.patterns = tuple(compiled)

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "PrivacyGuard":
        value: Mapping[str, Any] | Any = {} if config is None else config
        if not isinstance(value, Mapping):
            raise PrivacyConfigError("privacy guard configuration must be an object")
        if "privacy_guard" in value:
            nested = value["privacy_guard"]
            if not isinstance(nested, Mapping):
                raise PrivacyConfigError("privacy_guard must be an object")
            value = nested
        return cls(
            forbidden_literals=value.get("forbidden_literals", ()),
            forbidden_regexes=value.get("forbidden_regexes", ()),
            include_default_secret_patterns=_config_bool(
                value.get("include_default_secret_patterns", True),
                field_name="include_default_secret_patterns",
            ),
            case_sensitive_literals=_config_bool(
                value.get("case_sensitive_literals", False),
                field_name="case_sensitive_literals",
            ),
        )

    def scan_text(self, text: str, *, location: str | None = None) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        haystack = text if self.case_sensitive_literals else text.casefold()
        for literal in self.forbidden_literals:
            needle = literal if self.case_sensitive_literals else literal.casefold()
            if needle in haystack:
                findings.append(
                    PrivacyFinding(
                        kind="forbidden_literal",
                        message="configured forbidden literal is present",
                        location=location,
                    )
                )
        for kind, pattern in self.patterns:
            if pattern.search(text):
                findings.append(
                    PrivacyFinding(
                        kind=kind,
                        message=f"content matched {kind} guard",
                        location=location,
                        # Configured expressions may themselves contain private
                        # text. Keep them out of serializable findings.
                        pattern=None if kind == "configured_regex" else pattern.pattern,
                    )
                )
        return findings

    def scan_mapping(
        self, value: Mapping[str, Any], *, location: str = "$"
    ) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []

        def visit(item: Any, path: str) -> None:
            if isinstance(item, Mapping):
                for raw_key, child in item.items():
                    key = str(raw_key)
                    child_path = f"{path}.{key}"
                    if key.casefold() in SENSITIVE_KEYS and child not in (
                        None,
                        "",
                        [],
                        {},
                    ):
                        findings.append(
                            PrivacyFinding(
                                kind="sensitive_key",
                                message=f"non-empty sensitive field {key!r}",
                                location=child_path,
                            )
                        )
                    visit(child, child_path)
            elif isinstance(item, (list, tuple)):
                for index, child in enumerate(item):
                    visit(child, f"{path}[{index}]")
            elif isinstance(item, str):
                findings.extend(self.scan_text(item, location=path))

        visit(value, location)
        return findings

    def scan_files(
        self,
        paths: Iterable[str | Path],
        *,
        max_bytes: int = 2_000_000,
    ) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                if path.is_symlink():
                    findings.append(
                        PrivacyFinding(
                            kind="symlink",
                            message="symbolic links require explicit review",
                            location=str(path),
                        )
                    )
                    continue
                if not path.is_file():
                    findings.append(
                        PrivacyFinding(
                            kind="unreadable",
                            message="public-release path is not a regular file",
                            location=str(path),
                        )
                    )
                    continue
                if path.stat().st_size > max_bytes:
                    findings.append(
                        PrivacyFinding(
                            kind="oversize",
                            message=f"file exceeds privacy scan limit of {max_bytes} bytes",
                            location=str(path),
                        )
                    )
                    continue
                with path.open("rb") as handle:
                    raw = handle.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    findings.append(
                        PrivacyFinding(
                            kind="oversize",
                            message=f"file exceeds privacy scan limit of {max_bytes} bytes",
                            location=str(path),
                        )
                    )
                    continue
                if b"\x00" in raw:
                    findings.append(
                        PrivacyFinding(
                            kind="binary",
                            message="binary file requires explicit review",
                            location=str(path),
                        )
                    )
                    continue
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                findings.append(
                    PrivacyFinding(
                        kind="unreadable",
                        message="could not scan file as UTF-8 text",
                        location=str(path),
                    )
                )
                continue
            findings.extend(self.scan_text(text, location=str(path)))
        return findings

    def assert_safe_text(self, text: str, *, location: str | None = None) -> None:
        findings = self.scan_text(text, location=location)
        if findings:
            raise PrivacyViolation(findings)

    def assert_safe_mapping(self, value: Mapping[str, Any], *, location: str = "$") -> None:
        findings = self.scan_mapping(value, location=location)
        if findings:
            raise PrivacyViolation(findings)

    def assert_safe_files(self, paths: Iterable[str | Path]) -> None:
        findings = self.scan_files(paths)
        if findings:
            raise PrivacyViolation(findings)


PublicReleaseGuard = PrivacyGuard
