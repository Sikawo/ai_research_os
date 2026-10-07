"""Dependency-free layered configuration loading.

JSON is fully supported.  YAML support intentionally covers the conservative
data-only subset used by the framework's configuration files: mappings,
sequences, quoted/unquoted scalars, and inline lists/maps.  It does not execute
tags or constructors.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping

from .validation import validate_mapping


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ConfigSource:
    path: Path
    kind: str


def deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings; overlay scalars and lists replace defaults."""

    result = copy.deepcopy(dict(base))
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    result: list[str] = []
    for character in line:
        if escaped:
            result.append(character)
            escaped = False
            continue
        if character == "\\":
            result.append(character)
            escaped = True
            continue
        if quote:
            result.append(character)
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            result.append(character)
            quote = character
            continue
        if character == "#" and (not result or result[-1].isspace()):
            break
        result.append(character)
    return "".join(result).rstrip()


def _split_inline(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    for character in value:
        if quote:
            current.append(character)
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
            current.append(character)
        elif character in "[{(":
            depth += 1
            current.append(character)
        elif character in "]})":
            depth -= 1
            current.append(character)
        elif character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current or value:
        parts.append("".join(current).strip())
    return parts


def _split_key_value(value: str) -> tuple[str, str] | None:
    quote: str | None = None
    depth = 0
    for index, character in enumerate(value):
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "[{(":
            depth += 1
        elif character in "]})":
            depth -= 1
        elif (
            character == ":"
            and depth == 0
            and (index + 1 == len(value) or value[index + 1].isspace())
        ):
            return value[:index].strip(), value[index + 1 :].strip()
    return None


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    lowered = text.casefold()
    if lowered in {"null", "~", "none"}:
        return None
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [] if not inner else [_parse_scalar(part) for part in _split_inline(inner)]
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        result: dict[str, Any] = {}
        if inner:
            for part in _split_inline(inner):
                pair = _split_key_value(part)
                if not pair:
                    raise ConfigError(f"Invalid inline mapping entry: {part!r}")
                key, item = pair
                result[str(_parse_scalar(key))] = _parse_scalar(item)
        return result
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError) as exc:
            raise ConfigError(f"Invalid quoted scalar: {text!r}") from exc
    if re.fullmatch(r"[-+]?\d+", text):
        try:
            return int(text)
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\.\d+)(?:[eE][-+]?\d+)?", text):
        try:
            return float(text)
        except ValueError:
            pass
    return text


def parse_simple_yaml(text: str) -> Any:
    """Parse safe configuration YAML without external dependencies."""

    tokens: list[tuple[int, str, int]] = []
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise ConfigError(f"Tabs are not allowed for indentation (line {line_number})")
        cleaned = _strip_comment(raw_line)
        if not cleaned.strip() or cleaned.lstrip().startswith("---"):
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        tokens.append((indent, cleaned.strip(), line_number))
    if not tokens:
        return {}

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens) or tokens[index][0] < indent:
            return {}, index
        is_list = tokens[index][1] == "-" or tokens[index][1].startswith("- ")
        container: list[Any] | dict[str, Any] = [] if is_list else {}
        while index < len(tokens):
            current_indent, content, line_number = tokens[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ConfigError(f"Unexpected indentation on line {line_number}")
            if is_list:
                if not (content == "-" or content.startswith("- ")):
                    break
                remainder = content[1:].strip()
                index += 1
                if not remainder:
                    if index < len(tokens) and tokens[index][0] > indent:
                        item, index = parse_block(index, tokens[index][0])
                    else:
                        item = None
                    container.append(item)
                    continue
                pair = _split_key_value(remainder)
                if pair:
                    key, raw_value = pair
                    item_mapping: dict[str, Any] = {}
                    if raw_value:
                        item_mapping[key] = _parse_scalar(raw_value)
                    elif index < len(tokens) and tokens[index][0] > indent:
                        nested, index = parse_block(index, tokens[index][0])
                        item_mapping[key] = nested
                    else:
                        item_mapping[key] = None
                    if index < len(tokens) and tokens[index][0] > indent:
                        continuation, index = parse_block(index, tokens[index][0])
                        if not isinstance(continuation, Mapping):
                            raise ConfigError(
                                f"List mapping continuation must be a mapping (line {line_number})"
                            )
                        item_mapping.update(continuation)
                    container.append(item_mapping)
                else:
                    container.append(_parse_scalar(remainder))
                continue

            if content.startswith("- "):
                break
            pair = _split_key_value(content)
            if not pair:
                raise ConfigError(f"Expected key: value on line {line_number}")
            key, raw_value = pair
            if not key:
                raise ConfigError(f"Empty mapping key on line {line_number}")
            index += 1
            if raw_value:
                container[key] = _parse_scalar(raw_value)
            elif index < len(tokens) and tokens[index][0] > indent:
                nested, index = parse_block(index, tokens[index][0])
                container[key] = nested
            else:
                container[key] = None
        return container, index

    parsed, final_index = parse_block(0, tokens[0][0])
    if final_index != len(tokens):
        _, _, line_number = tokens[final_index]
        raise ConfigError(f"Could not parse YAML near line {line_number}")
    return parsed


def load_config_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Unable to read configuration {config_path}: {exc}") from exc
    try:
        if config_path.suffix.casefold() == ".json":
            parsed = json.loads(text)
        elif config_path.suffix.casefold() in {".yaml", ".yml"}:
            parsed = parse_simple_yaml(text)
        else:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = parse_simple_yaml(text)
    except (json.JSONDecodeError, ConfigError) as exc:
        raise ConfigError(f"Invalid configuration {config_path}: {exc}") from exc
    validate_mapping(parsed, path=str(config_path))
    return dict(parsed)


def load_config_directory(
    path: str | os.PathLike[str], *, filenames: Iterable[str] | None = None
) -> dict[str, Any]:
    directory = Path(path).expanduser()
    if not directory.is_dir():
        raise ConfigError(f"Configuration directory does not exist: {directory}")
    selected = set(filenames or ())
    result: dict[str, Any] = {}
    for config_path in sorted(directory.iterdir()):
        if not config_path.is_file() or config_path.suffix.casefold() not in {
            ".json",
            ".yaml",
            ".yml",
        }:
            continue
        if selected and config_path.name not in selected and config_path.stem not in selected:
            continue
        value = load_config_file(config_path)
        key = config_path.stem
        result[key] = deep_merge(result.get(key, {}), value) if key in result else value
    return result


def load_config_source(source: Mapping[str, Any] | str | os.PathLike[str] | None) -> dict[str, Any]:
    if source is None:
        return {}
    if isinstance(source, Mapping):
        return copy.deepcopy(dict(source))
    path = Path(source).expanduser()
    return load_config_directory(path) if path.is_dir() else load_config_file(path)


def select_private_config_source(
    *,
    explicit_dir: str | os.PathLike[str] | None = None,
    env_var: str = "ACADEMIC_PI_PRIVATE_CONFIG_DIR",
    environ: Mapping[str, str] | None = None,
    existing_private_dirs: Iterable[str | os.PathLike[str]] = (),
    local_dir: str | os.PathLike[str] | None = None,
    example_dir: str | os.PathLike[str] | None = None,
    allow_example: bool = False,
) -> ConfigSource | None:
    """Resolve exactly one private overlay according to explicit precedence."""

    if explicit_dir is not None:
        candidate = Path(explicit_dir).expanduser()
        if not candidate.is_dir():
            raise ConfigError(f"Explicit private config directory is unavailable: {candidate}")
        return ConfigSource(candidate, "explicit")
    environment = os.environ if environ is None else environ
    configured = environment.get(env_var)
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_dir():
            raise ConfigError(f"{env_var} points to an unavailable directory: {candidate}")
        return ConfigSource(candidate, "environment")
    for item in existing_private_dirs:
        candidate = Path(item).expanduser()
        if candidate.is_dir():
            return ConfigSource(candidate, "existing_private")
    if local_dir is not None and Path(local_dir).expanduser().is_dir():
        return ConfigSource(Path(local_dir).expanduser(), "repo_local")
    if allow_example and example_dir is not None and Path(example_dir).expanduser().is_dir():
        return ConfigSource(Path(example_dir).expanduser(), "example")
    return None


def load_config_overlay(
    public_defaults: Mapping[str, Any] | str | os.PathLike[str] | None,
    *,
    private_dir: str | os.PathLike[str] | None = None,
    env_var: str = "ACADEMIC_PI_PRIVATE_CONFIG_DIR",
    environ: Mapping[str, str] | None = None,
    existing_private_dirs: Iterable[str | os.PathLike[str]] = (),
    local_dir: str | os.PathLike[str] | None = None,
    example_dir: str | os.PathLike[str] | None = None,
    allow_example: bool = False,
) -> dict[str, Any]:
    defaults = load_config_source(public_defaults)
    source = select_private_config_source(
        explicit_dir=private_dir,
        env_var=env_var,
        environ=environ,
        existing_private_dirs=existing_private_dirs,
        local_dir=local_dir,
        example_dir=example_dir,
        allow_example=allow_example,
    )
    if source is None:
        return defaults
    overlay = load_config_directory(source.path)
    merged = deep_merge(defaults, overlay)
    merged.setdefault("_config", {})
    if isinstance(merged["_config"], MutableMapping):
        merged["_config"].update({"overlay_kind": source.kind})
    return merged


def load_overlay_chain(*sources: Mapping[str, Any] | str | os.PathLike[str]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        merged = deep_merge(merged, load_config_source(source))
    return merged
