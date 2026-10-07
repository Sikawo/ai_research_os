"""Command-line interface for the credential-free Academic PI deployment."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ...core.config import ConfigError, load_config_overlay
from ...core.models import json_safe
from ...core.state import InMemoryStateStore, JsonFileStateStore
from .service import AcademicPiService


ConnectorFactory = Callable[[Mapping[str, Any]], Any]
_CONNECTOR_CAPABILITIES = {"discovery", "verification", "email", "report"}
_CAPABILITY_METHODS = {
    "discovery": ("discover",),
    "verification": ("verify",),
    "email": (
        "fetch_unprocessed",
        "mark_processed",
        "mark_needs_review",
        "mark_error",
    ),
    "report": ("deliver",),
}
_FORBIDDEN_PLUGIN_KEYS = {"module", "class", "callable", "entrypoint", "import"}
_STATE_MUTATING_COMMANDS = {
    "daily",
    "weekly",
    "scan-source",
    "scan-rss",
    "scan-email",
    "scan-institution",
    "verify",
    "evaluate",
    "refresh-qol",
    "reject",
    "restore",
}
_STATE_READING_COMMANDS = {
    "show", "active", "deadlines", "coverage", "source-health",
    "target-health", "handoff",
}
_STATE_REQUIRED_COMMANDS = _STATE_MUTATING_COMMANDS | _STATE_READING_COMMANDS
_EXAMPLE_COMMANDS = {"validate-config", "dry-run"}


@dataclass(frozen=True)
class ConnectorBundle:
    """Validated connector instances ready for ``AcademicPiService`` injection."""

    discovery: tuple[Any, ...] = ()
    verification: Any | None = None
    email: Any | None = None
    reports: tuple[Any, ...] = ()


def _default_public_config() -> Path:
    return Path(__file__).resolve().parent / "config"


def load_academic_config(
    public_config: str | os.PathLike[str] | Mapping[str, Any] | None = None,
    *,
    private_config_dir: str | os.PathLike[str] | None = None,
    allow_example: bool = False,
) -> dict[str, Any]:
    source = public_config
    if source is None:
        default = _default_public_config()
        source = default if default.is_dir() else {}
    example_dir = Path(__file__).resolve().parent / "templates"
    if allow_example:
        if private_config_dir is not None:
            raise ConfigError(
                "--allow-example cannot be combined with --private-config-dir; "
                "example mode deliberately ignores private overlays"
            )
        # Example mode is deterministic even when a private-overlay environment
        # variable or ignored repo-local profile exists.  Treat the synthetic
        # template directory as the explicit overlay and label it accurately.
        config = load_config_overlay(source, private_dir=example_dir)
        config.setdefault("_config", {})
        if isinstance(config["_config"], dict):
            config["_config"]["overlay_kind"] = "example"
    else:
        existing_private = os.environ.get("CAREER_JOB_AGENT_PRIVATE_CONFIG_DIR")
        config = load_config_overlay(
            source,
            private_dir=private_config_dir,
            existing_private_dirs=(existing_private,) if existing_private else (),
            local_dir=Path(__file__).resolve().parents[2] / "profiles" / "local",
        )
    # Example filenames retain `.example` to make their synthetic nature clear
    # on disk; normalize them to the same runtime keys used by private overlays.
    for key in (
        "candidate_profile",
        "preferences",
        "target_institutions",
        "email_sources",
        "source_overrides",
        "scoring_overrides",
        "connectors",
    ):
        example_key = f"{key}.example"
        if example_key in config and (allow_example or key not in config):
            config[key] = config.pop(example_key)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="academic-pi",
        description="Discover, evaluate, track, and report academic PI opportunities.",
    )
    parser.add_argument("--config", help="Public config file or directory")
    parser.add_argument("--private-config-dir", help="Private overlay directory")
    parser.add_argument(
        "--state",
        help="Private JSON state path (required for standalone state-dependent commands)",
    )
    parser.add_argument(
        "--allow-example",
        action="store_true",
        help="Force synthetic example configuration for validate-config or dry-run",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("daily", help="Run the idempotent daily workflow")
    subparsers.add_parser("weekly", help="Run the comprehensive weekly audit")

    scan_source = subparsers.add_parser("scan-source", help="Scan one configured source connector")
    scan_source.add_argument("source")
    scan_rss = subparsers.add_parser("scan-rss", help="Scan one configured RSS source")
    scan_rss.add_argument("source")
    subparsers.add_parser("scan-email", help="Scan configured Gmail alerts only")
    scan_institution = subparsers.add_parser(
        "scan-institution", help="Scan one target institution"
    )
    scan_institution.add_argument("institution")

    for name in ("verify", "evaluate", "refresh-qol", "show", "reject", "restore", "handoff"):
        command = subparsers.add_parser(name)
        command.add_argument("job")
        if name in {"reject", "restore"}:
            command.add_argument("--reason")
        if name == "handoff":
            command.add_argument(
                "--evidence-ref",
                action="append",
                required=True,
                help=(
                    "Authorized private evidence-ledger reference; repeat for "
                    "additional references"
                ),
            )

    subparsers.add_parser("active", help="Show current active Tier 1/2 roles")
    deadlines = subparsers.add_parser("deadlines", help="Show upcoming fixed deadlines")
    deadlines.add_argument("--days", type=int)
    subparsers.add_parser("coverage", help="Show source and institution coverage")
    subparsers.add_parser("source-health", help="Show email, RSS, and source health")
    subparsers.add_parser("target-health", help="Show target-institution health")
    subparsers.add_parser("validate-config", help="Validate merged configuration")
    dry_run = subparsers.add_parser("dry-run", help="Run without durable state or delivery writes")
    dry_run.add_argument("--run-type", choices=("daily", "weekly"), default="daily")
    return parser


def _serialize(value: Any) -> str:
    if isinstance(value, list):
        value = [item.to_dict() if hasattr(item, "to_dict") else item for item in value]
    elif isinstance(value, Mapping):
        value = {
            key: [item.to_dict() if hasattr(item, "to_dict") else item for item in item_value]
            if isinstance(item_value, list)
            else item_value
            for key, item_value in value.items()
        }
    elif hasattr(value, "to_dict"):
        value = value.to_dict()
    return json.dumps(json_safe(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _connector_section(config: Mapping[str, Any]) -> Mapping[str, Any]:
    section = config.get("connectors", {})
    return section if isinstance(section, Mapping) else {}


def _plugin_rows(section: Mapping[str, Any]) -> list[Any]:
    rows = section.get("plugins", section.get("connectors", ()))
    if rows is None:
        return []
    if isinstance(rows, Mapping):
        return [{"id": key, **dict(value)} for key, value in rows.items() if isinstance(value, Mapping)]
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        return list(rows)
    return []


def _binding_ids(section: Mapping[str, Any], capability: str) -> list[str]:
    bindings = section.get("bindings", {})
    if not isinstance(bindings, Mapping):
        return []
    value = bindings.get(capability)
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value]
    return []


def _source_rows(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = config.get("source_catalog", config.get("sources", ()))
    if isinstance(value, Mapping):
        value = value.get("sources", ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows = [dict(item) for item in value if isinstance(item, Mapping)]
    overrides = config.get("source_overrides", {})
    source_overrides = overrides.get("sources", {}) if isinstance(overrides, Mapping) else {}
    if isinstance(source_overrides, Mapping):
        for row in rows:
            override = source_overrides.get(row.get("id"))
            if isinstance(override, Mapping):
                row.update(override)
    society_rows = overrides.get("society_sources", ()) if isinstance(overrides, Mapping) else ()
    if isinstance(society_rows, Sequence) and not isinstance(society_rows, (str, bytes)):
        by_id = {str(row.get("id")): row for row in rows if row.get("id")}
        for item in society_rows:
            if not isinstance(item, Mapping) or not item.get("source_id"):
                continue
            source_id = str(item["source_id"])
            if source_id in by_id:
                by_id[source_id].update(dict(item))
            else:
                rows.append({"id": source_id, **dict(item)})
    return rows


def _source_is_enabled(row: Mapping[str, Any]) -> bool:
    if "enabled" in row:
        return row.get("enabled") is True
    return row.get("enabled_by_default", True) is True


def validate_connector_config(
    config: Mapping[str, Any],
    *,
    available_factory_names: Iterable[str] | None = None,
    require_operational_capabilities: bool = False,
) -> list[str]:
    """Validate connector declarations, bindings, capabilities, and source references."""

    errors: list[str] = []
    raw_section = config.get("connectors", {})
    if raw_section is not None and not isinstance(raw_section, Mapping):
        return ["connectors must be a mapping loaded from connectors.yaml"]
    section = _connector_section(config)
    version = section.get("version", 1)
    if version != 1:
        errors.append("connectors.version must be 1")
    raw_plugins = section.get("plugins", section.get("connectors", ()))
    if raw_plugins is not None and not isinstance(raw_plugins, (Mapping, list, tuple)):
        errors.append("connectors.plugins must be a list or mapping")
    if isinstance(raw_plugins, Mapping):
        for identifier, declaration in raw_plugins.items():
            if not isinstance(declaration, Mapping):
                errors.append(
                    f"connectors.plugins.{identifier} must be a mapping"
                )
    bindings = section.get("bindings", {})
    if bindings is not None and not isinstance(bindings, Mapping):
        errors.append("connectors.bindings must be a mapping")

    factory_names = set(available_factory_names) if available_factory_names is not None else None
    definitions: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(_plugin_rows(section)):
        path = f"connectors.plugins[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{path} must be a mapping")
            continue
        forbidden = sorted(_FORBIDDEN_PLUGIN_KEYS.intersection(row))
        if forbidden:
            errors.append(
                f"{path} contains forbidden dynamic-loading keys: {', '.join(forbidden)}"
            )
        identifier = str(row.get("id") or "").strip()
        if not identifier:
            errors.append(f"{path}.id is required")
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", identifier):
            errors.append(f"{path}.id must use lowercase letters, digits, '_' or '-'")
        if identifier in definitions:
            errors.append(f"{path}.id duplicates connector {identifier!r}")
        definitions[identifier] = row

        factory = str(row.get("factory") or "").strip()
        if not factory:
            errors.append(f"{path}.factory is required")
        elif (
            row.get("enabled", True) is True
            and factory_names is not None
            and factory not in factory_names
        ):
            errors.append(
                f"{path}.factory {factory!r} is not registered in the host allowlist"
            )
        raw_capabilities = row.get("capabilities", ())
        if not isinstance(raw_capabilities, Sequence) or isinstance(
            raw_capabilities, (str, bytes)
        ):
            errors.append(f"{path}.capabilities must be a list")
            capabilities: set[str] = set()
        else:
            capabilities = {str(item) for item in raw_capabilities}
            if not capabilities:
                errors.append(f"{path}.capabilities must not be empty")
            invalid = sorted(capabilities - _CONNECTOR_CAPABILITIES)
            if invalid:
                errors.append(f"{path}.capabilities contains unknown values: {', '.join(invalid)}")
        if not isinstance(row.get("enabled", True), bool):
            errors.append(f"{path}.enabled must be boolean")
        if not isinstance(row.get("options", {}), Mapping):
            errors.append(f"{path}.options must be a mapping")

    bound_by_capability: dict[str, list[str]] = {}
    for capability in sorted(_CONNECTOR_CAPABILITIES):
        raw_binding = bindings.get(capability) if isinstance(bindings, Mapping) else None
        if raw_binding not in (None, "") and not isinstance(raw_binding, (str, list, tuple)):
            errors.append(f"connectors.bindings.{capability} must be a string or list")
        identifiers = _binding_ids(section, capability)
        bound_by_capability[capability] = identifiers
        if len(identifiers) != len(set(identifiers)):
            errors.append(f"connectors.bindings.{capability} contains duplicate IDs")
        if capability in {"verification", "email"} and len(identifiers) > 1:
            errors.append(f"connectors.bindings.{capability} accepts at most one connector")
        for identifier in identifiers:
            definition = definitions.get(identifier)
            if definition is None:
                errors.append(
                    f"connectors.bindings.{capability} references unknown connector {identifier!r}"
                )
                continue
            if definition.get("enabled", True) is not True:
                errors.append(
                    f"connectors.bindings.{capability} references disabled connector {identifier!r}"
                )
            capabilities = definition.get("capabilities", ())
            if capability not in capabilities:
                errors.append(
                    f"connector {identifier!r} is bound for {capability} but does not declare that capability"
                )

    for identifier, definition in definitions.items():
        if definition.get("enabled", True) is not True:
            continue
        for capability in definition.get("capabilities", ()):
            if capability in _CONNECTOR_CAPABILITIES and identifier not in bound_by_capability.get(
                str(capability), ()
            ):
                errors.append(
                    f"enabled connector {identifier!r} declares {capability} but is not bound"
                )

    source_rows = _source_rows(config)
    source_ids = {str(row.get("id")) for row in source_rows if row.get("id")}
    source_by_id = {
        str(row.get("id")): row for row in source_rows if row.get("id")
    }
    overrides = config.get("source_overrides", {})
    override_sources = overrides.get("sources", {}) if isinstance(overrides, Mapping) else {}
    if isinstance(override_sources, Mapping):
        for source_id in override_sources:
            if str(source_id) not in source_ids:
                errors.append(
                    f"source_overrides.sources references unknown source {source_id!r}"
                )
    for identifier in bound_by_capability.get("discovery", ()):
        if identifier not in source_ids:
            errors.append(
                f"discovery connector {identifier!r} has no matching source_catalog.sources id"
            )
        elif not _source_is_enabled(source_by_id[identifier]):
            errors.append(
                f"discovery connector {identifier!r} is bound to a disabled source"
            )
    if require_operational_capabilities:
        if not bound_by_capability.get("discovery") and not bound_by_capability.get("email"):
            errors.append(
                "operational configuration requires at least one discovery or email connector binding"
            )
        if not bound_by_capability.get("verification"):
            errors.append(
                "operational configuration requires a verification connector binding"
            )
        bound_discovery = set(bound_by_capability.get("discovery", ()))
        for identifier, row in sorted(source_by_id.items()):
            if (
                _source_is_enabled(row)
                and row.get("supports_direct_search") is True
                and identifier not in bound_discovery
            ):
                errors.append(
                    f"enabled searchable source {identifier!r} has no discovery connector binding"
                )
    return errors


def _connector_supports(connector: Any, capability: str) -> bool:
    return all(callable(getattr(connector, method, None)) for method in _CAPABILITY_METHODS[capability])


def build_connector_bundle(
    config: Mapping[str, Any],
    *,
    connector_factories: Mapping[str, ConnectorFactory] | None = None,
) -> ConnectorBundle:
    """Build connectors only through factories explicitly registered by the host.

    Configuration selects an allowlisted factory by name. It cannot provide an
    import path, module, class, or arbitrary callable expression.
    """

    factories = dict(connector_factories or {})
    bad_factories = sorted(name for name, factory in factories.items() if not callable(factory))
    if bad_factories:
        raise ConfigError(
            "Registered connector factories are not callable: " + ", ".join(bad_factories)
        )
    errors = validate_connector_config(
        config, available_factory_names=factories.keys()
    )
    if errors:
        raise ConfigError("; ".join(errors))

    section = _connector_section(config)
    definitions = {
        str(row["id"]): row
        for row in _plugin_rows(section)
        if isinstance(row, Mapping) and row.get("id") and row.get("enabled", True) is True
    }
    required_ids = {
        identifier
        for capability in _CONNECTOR_CAPABILITIES
        for identifier in _binding_ids(section, capability)
    }
    instances: dict[str, Any] = {}
    for identifier in sorted(required_ids):
        definition = definitions[identifier]
        factory_name = str(definition["factory"])
        try:
            connector = factories[factory_name](dict(definition))
        except Exception as exc:
            raise ConfigError(
                f"Connector factory {factory_name!r} failed for {identifier!r}: {exc}"
            ) from exc
        actual_id = str(
            getattr(connector, "connector_id", getattr(connector, "id", "")) or ""
        )
        if actual_id != identifier:
            raise ConfigError(
                f"Connector {identifier!r} factory returned connector_id {actual_id!r}"
            )
        for capability in definition.get("capabilities", ()):
            if capability in _CONNECTOR_CAPABILITIES and not _connector_supports(
                connector, str(capability)
            ):
                methods = ", ".join(_CAPABILITY_METHODS[str(capability)])
                raise ConfigError(
                    f"Connector {identifier!r} declares {capability} but lacks methods: {methods}"
                )
        instances[identifier] = connector

    discovery = tuple(instances[item] for item in _binding_ids(section, "discovery"))
    verification_ids = _binding_ids(section, "verification")
    email_ids = _binding_ids(section, "email")
    reports = tuple(instances[item] for item in _binding_ids(section, "report"))
    return ConnectorBundle(
        discovery=discovery,
        verification=instances[verification_ids[0]] if verification_ids else None,
        email=instances[email_ids[0]] if email_ids else None,
        reports=reports,
    )


def _require_command_connectors(
    args: argparse.Namespace, bundle: ConnectorBundle
) -> None:
    command = args.command
    if command in {"scan-source", "scan-rss", "scan-institution"} and not bundle.discovery:
        raise ConfigError(
            f"{command} requires a discovery connector bound in connectors.yaml"
        )
    if command in {"scan-source", "scan-rss"}:
        available = {
            str(getattr(connector, "connector_id", getattr(connector, "id", "")))
            for connector in bundle.discovery
        }
        if args.source not in available:
            raise ConfigError(
                f"{command} {args.source!r} has no bound discovery connector"
            )
    if command == "scan-email" and bundle.email is None:
        raise ConfigError("scan-email requires an email connector bound in connectors.yaml")
    if command in {"verify", "evaluate"} and bundle.verification is None:
        raise ConfigError(
            f"{command} requires a verification connector bound in connectors.yaml"
        )
    if command in {"daily", "weekly", "dry-run"}:
        if command == "dry-run" and args.allow_example:
            return
        if not bundle.discovery and bundle.email is None:
            raise ConfigError(
                f"{command} requires at least one discovery or email connector bound in connectors.yaml"
            )
        if bundle.verification is None:
            raise ConfigError(
                f"{command} requires a verification connector bound in connectors.yaml"
            )


def _loaded_config(args: argparse.Namespace) -> dict[str, Any]:
    return load_academic_config(
        args.config,
        private_config_dir=args.private_config_dir,
        allow_example=args.allow_example,
    )


def _service_from_args(
    args: argparse.Namespace,
    *,
    connector_factories: Mapping[str, ConnectorFactory] | None = None,
) -> AcademicPiService:
    config = _loaded_config(args)
    contract_errors = AcademicPiService(config=config).validate_config(
        strict_contracts=True
    )
    if contract_errors:
        raise ConfigError(
            "Invalid Academic PI configuration: " + "; ".join(contract_errors)
        )
    if args.command in _STATE_REQUIRED_COMMANDS and not args.state:
        raise ConfigError(
            f"{args.command} requires an explicit durable --state path; "
            "use dry-run for a non-mutating check"
        )
    connector_errors = validate_connector_config(
        config,
        available_factory_names=(connector_factories or {}).keys(),
        require_operational_capabilities=(
            args.command in {"daily", "weekly"}
            or (args.command == "dry-run" and not args.allow_example)
        ),
    )
    if connector_errors:
        raise ConfigError("; ".join(connector_errors))
    bundle = build_connector_bundle(config, connector_factories=connector_factories)
    _require_command_connectors(args, bundle)
    if args.state and args.command in _STATE_READING_COMMANDS and not Path(args.state).expanduser().is_file():
        raise ConfigError(f"{args.command} requires an existing durable --state file")
    state = (
        JsonFileStateStore(args.state, create=args.command != "dry-run")
        if args.state
        else InMemoryStateStore()
    )
    return AcademicPiService(
        config=config,
        state_store=state,
        discovery_connectors=bundle.discovery,
        verification_connector=bundle.verification,
        report_connectors=bundle.reports,
        email_connector=bundle.email,
    )


def _config_errors(
    config: Mapping[str, Any],
    *,
    connector_factories: Mapping[str, ConnectorFactory] | None = None,
    require_operational_capabilities: bool = True,
) -> list[str]:
    service = AcademicPiService(config=config)
    errors = list(service.validate_config(strict_contracts=True))
    errors.extend(
        validate_connector_config(
            config,
            available_factory_names=(connector_factories or {}).keys(),
            require_operational_capabilities=require_operational_capabilities,
        )
    )
    if not errors and _plugin_rows(_connector_section(config)):
        try:
            build_connector_bundle(config, connector_factories=connector_factories)
        except ConfigError as exc:
            errors.append(str(exc))
    return list(dict.fromkeys(errors))


def _overlay_kind(config: Mapping[str, Any], *, injected: bool = False) -> str:
    metadata = config.get("_config", {})
    if isinstance(metadata, Mapping) and metadata.get("overlay_kind"):
        return str(metadata["overlay_kind"])
    return "injected" if injected else "public_only"


def main(
    argv: Sequence[str] | None = None,
    *,
    service: AcademicPiService | None = None,
    connector_factories: Mapping[str, ConnectorFactory] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.allow_example and args.command not in _EXAMPLE_COMMANDS:
            raise ConfigError(
                "--allow-example is limited to validate-config and dry-run demonstrations"
            )
        if args.command == "validate-config":
            config = service.config if service is not None else _loaded_config(args)
            errors = _config_errors(
                config,
                connector_factories=connector_factories,
                require_operational_capabilities=not args.allow_example,
            )
            overlay_kind = _overlay_kind(config, injected=service is not None)
            if errors:
                print(
                    _serialize(
                        {
                            "valid": False,
                            "overlay_kind": overlay_kind,
                            "errors": errors,
                        }
                    ),
                    end="",
                )
                return 2
            print(
                _serialize(
                    {"valid": True, "overlay_kind": overlay_kind, "errors": []}
                ),
                end="",
            )
            return 0

        if service is not None:
            contract_errors = service.validate_config(strict_contracts=True)
            if contract_errors:
                raise ConfigError(
                    "Invalid Academic PI configuration: "
                    + "; ".join(contract_errors)
                )
            active_service = service
        else:
            active_service = _service_from_args(
                args, connector_factories=connector_factories
            )
        command = args.command
        if command == "daily":
            print(active_service.daily().report, end="")
        elif command == "weekly":
            print(active_service.weekly().report, end="")
        elif command == "scan-source":
            print(active_service.scan_source(args.source).report, end="")
        elif command == "scan-rss":
            print(active_service.scan_rss(args.source).report, end="")
        elif command == "scan-email":
            print(active_service.scan_email().report, end="")
        elif command == "scan-institution":
            print(active_service.scan_institution(args.institution).report, end="")
        elif command == "verify":
            print(_serialize(active_service.verify(args.job)), end="")
        elif command == "evaluate":
            print(_serialize(active_service.evaluate(args.job)), end="")
        elif command == "refresh-qol":
            print(_serialize(active_service.refresh_qol(args.job)), end="")
        elif command == "show":
            print(_serialize(active_service.show(args.job)), end="")
        elif command == "active":
            print(_serialize(active_service.active()), end="")
        elif command == "deadlines":
            print(_serialize(active_service.deadlines(days=args.days)), end="")
        elif command == "coverage":
            print(_serialize(active_service.coverage()), end="")
        elif command == "source-health":
            print(_serialize(active_service.source_health()), end="")
        elif command == "target-health":
            print(_serialize(active_service.target_health()), end="")
        elif command == "reject":
            print(_serialize(active_service.reject(args.job, reason=args.reason)), end="")
        elif command == "restore":
            print(_serialize(active_service.restore(args.job, reason=args.reason)), end="")
        elif command == "handoff":
            evidence = [
                {
                    "ref": reference,
                    "strength": "uncertain",
                    "authorized_for_handoff": True,
                }
                for reference in args.evidence_ref
            ]
            print(_serialize(active_service.handoff(args.job, evidence=evidence)), end="")
        elif command == "dry-run":
            print(active_service.dry_run(args.run_type).report, end="")
        else:  # pragma: no cover - argparse enforces this
            parser.error(f"Unsupported command: {command}")
        return 0
    except (ConfigError, ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f"academic-pi: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
