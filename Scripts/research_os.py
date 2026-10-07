#!/usr/bin/env python3
"""
Small command-style entry point for reusable research-workspace workflows.

The first implemented command is:

    research-os new-exp <request.yaml>

It intentionally reuses Scripts/register_experiment_from_request.py for the
canonical Git metadata write.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from register_experiment import (
    STATUS_VALUES,
    build_experiment_id,
    experiment_id_in_index,
    find_repo_root,
    load_summary_template,
    parse_experiment_date,
)
from register_experiment_from_request import (
    DEFAULT_RAW_DATA_NOTES,
    RequestValidationError,
    location_with_required_fields,
    optional_text,
    read_request_file,
    register_from_request,
    required_mapping,
    required_text,
    validate_project_request,
)

REQUEST_PATTERNS = ("experiment_request_*.yaml", "experiment_request_*.yml")
DEFAULT_FOLDER_TEMPLATE = ("raw_data", "analysis_runs", "processed_data", "final_outputs", "docs")
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "research_os" / "config.yaml"


@dataclass(frozen=True)
class ExperimentRequestInfo:
    request_path: Path
    experiment_id: str
    project_id: str
    purpose: str
    storage: Mapping[str, Any]
    git: Mapping[str, Any]
    cloud_target: str


@dataclass(frozen=True)
class CloudResult:
    experiment_dir: Path | None
    created: list[Path]
    skipped: list[Path]


class CommandError(RuntimeError):
    """Raised when the command cannot safely continue."""


class GitRunner:
    def __call__(
        self,
        args: Sequence[str],
        cwd: Path,
        *,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            cwd=str(cwd),
            capture_output=capture,
            text=True,
            check=False,
        )


def parse_config_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset needed for local config files."""

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    pending_list_key: tuple[int, dict[str, Any], str] | None = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            raise CommandError(f"Config line {lineno}: tabs are not supported.")

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            raise CommandError(f"Config line {lineno}: indentation must use two spaces.")

        line = raw_line.strip()
        if line.startswith("- "):
            if pending_list_key is None:
                raise CommandError(f"Config line {lineno}: list item has no parent key.")
            list_indent, parent, key = pending_list_key
            if indent != list_indent + 2:
                raise CommandError(f"Config line {lineno}: list indentation is invalid.")
            value = line[2:].strip()
            if not value:
                raise CommandError(f"Config line {lineno}: list item needs a value.")
            if parent.get(key) == {}:
                parent[key] = []
            if not isinstance(parent.get(key), list):
                raise CommandError(f"Config line {lineno}: parent key '{key}' is not a list.")
            parent[key].append(parse_scalar(value))
            continue

        pending_list_key = None
        if ":" not in line:
            raise CommandError(f"Config line {lineno}: expected 'key: value'.")

        key, rest = line.split(":", 1)
        key = key.strip()
        value_text = rest.strip()
        if not key:
            raise CommandError(f"Config line {lineno}: empty keys are not supported.")

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise CommandError(f"Config line {lineno}: invalid indentation.")

        parent = stack[-1][1]
        if key in parent:
            raise CommandError(f"Config line {lineno}: duplicate key '{key}'.")

        if value_text == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            pending_list_key = (indent, parent, key)
        else:
            parent[key] = parse_scalar(value_text)

    return root


def parse_scalar(text: str) -> str | bool:
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return text[1:-1].replace('\\"', '"').replace("\\n", "\n")
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("\\'", "'")
    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    return text


def load_config(repo_root: Path, config_path: Path | None = None) -> dict[str, Any]:
    candidates: list[Path] = []
    env_path = os.environ.get("RESEARCH_OS_CONFIG")
    if config_path is not None:
        candidates.append(config_path.expanduser())
    elif env_path:
        candidates.append(Path(env_path).expanduser())
    else:
        candidates.extend(
            [
                repo_root / "config" / "research_os_config.yaml",
                DEFAULT_CONFIG_PATH,
            ]
        )

    for path in candidates:
        if path.is_file():
            return parse_config_yaml(path.read_text(encoding="utf-8"))
    return {}


def find_latest_download(downloads_dir: Path) -> Path:
    matches: list[Path] = []
    for pattern in REQUEST_PATTERNS:
        matches.extend(downloads_dir.expanduser().glob(pattern))
    files = [path for path in matches if path.is_file()]
    if not files:
        raise CommandError(
            f"No request YAML found in {downloads_dir} matching "
            f"{', '.join(REQUEST_PATTERNS)}."
        )
    return max(files, key=lambda path: (path.stat().st_mtime, path.name))


def choose_request_path(args: argparse.Namespace) -> Path:
    if args.latest_download:
        downloads = Path(args.downloads_dir).expanduser() if args.downloads_dir else Path.home() / "Downloads"
        return find_latest_download(downloads)
    if args.request_yaml is None:
        raise CommandError("Provide a request YAML path or use --latest-download.")
    return Path(args.request_yaml).expanduser()


def request_bool(section: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = section.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise RequestValidationError(f"Field {key} must be true or false.")


def as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_request_info(request_path: Path) -> ExperimentRequestInfo:
    request = read_request_file(request_path)
    project = required_mapping(request, "project")
    experiment = required_mapping(request, "experiment")

    date_text = required_text(experiment, "date", "experiment")
    yyyymmdd, _iso_date = parse_experiment_date(date_text)
    experiment_id = build_experiment_id(
        yyyymmdd,
        required_text(experiment, "short_description", "experiment"),
    )
    project_id = required_text(project, "project_id", "project")
    purpose = required_text(experiment, "purpose", "experiment")
    storage = as_mapping(request.get("storage"))
    git = as_mapping(request.get("git"))

    cloud_target = "none"
    if request_bool(storage, "create_cloud_folder", False):
        provider = storage.get("provider") or storage.get("default_provider") or "configured provider"
        parent_ref = storage.get("parent_ref") or storage.get("parent_path") or "configured parent"
        cloud_target = f"{provider}:{parent_ref}/{experiment_id}"

    return ExperimentRequestInfo(
        request_path=request_path,
        experiment_id=experiment_id,
        project_id=project_id,
        purpose=purpose,
        storage=storage,
        git=git,
        cloud_target=cloud_target,
    )


def confirm_execution(info: ExperimentRequestInfo, *, assume_yes: bool, action_label: str = "experiment registration") -> None:
    print(f"Selected request YAML: {info.request_path}")
    print(f"Parsed experiment_id: {info.experiment_id}")
    print(f"Project: {info.project_id}")
    print(f"Cloud target: {info.cloud_target}")
    if assume_yes:
        return
    answer = input(f"Proceed with {action_label}? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise CommandError("Canceled before making changes.")


def config_section(config: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    current: Any = config
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, Mapping) else {}


def resolve_storage_parent(
    storage: Mapping[str, Any],
    config: Mapping[str, Any],
) -> Path:
    explicit_parent = storage.get("parent_path")
    if isinstance(explicit_parent, str) and explicit_parent.strip():
        return Path(explicit_parent).expanduser()

    provider = storage.get("provider") or config_section(config, "storage").get("default_provider")
    if not isinstance(provider, str) or not provider.strip():
        raise CommandError("storage.provider or storage.default_provider config is required.")

    parent_ref = storage.get("parent_ref")
    provider_config = config_section(config, "storage", provider)
    if parent_ref in {None, "", "default_experiments_parent"}:
        configured_parent = provider_config.get("experiments_parent")
    else:
        configured_parent = provider_config.get(str(parent_ref))

    if not isinstance(configured_parent, str) or not configured_parent.strip():
        raise CommandError(
            f"No configured storage parent for provider '{provider}' and parent_ref "
            f"'{parent_ref or 'default_experiments_parent'}'."
        )
    return Path(configured_parent).expanduser()


class SyncedFolderStorageAdapter:
    def __init__(self, parent: Path) -> None:
        self.parent = parent

    def create_or_complete(self, info: ExperimentRequestInfo) -> CloudResult:
        if self.parent.exists() and not self.parent.is_dir():
            raise CommandError(f"Storage parent is not a directory: {self.parent}")
        self.parent.mkdir(parents=True, exist_ok=True)

        exp_dir = self.parent / info.experiment_id
        created: list[Path] = []
        skipped: list[Path] = []

        if exp_dir.exists() and not exp_dir.is_dir():
            raise CommandError(f"Cloud experiment path exists but is not a directory: {exp_dir}")
        if exp_dir.exists():
            skipped.append(exp_dir)
        else:
            exp_dir.mkdir()
            created.append(exp_dir)

        for name in DEFAULT_FOLDER_TEMPLATE:
            child = exp_dir / name
            if child.exists() and not child.is_dir():
                raise CommandError(f"Cloud path exists but is not a directory: {child}")
            if child.exists():
                skipped.append(child)
            else:
                child.mkdir()
                created.append(child)

        readme = exp_dir / "README.md"
        if readme.exists() and not readme.is_file():
            raise CommandError(f"Cloud README path exists but is not a file: {readme}")
        if readme.exists():
            skipped.append(readme)
        else:
            readme.write_text(cloud_readme_text(info), encoding="utf-8")
            created.append(readme)

        return CloudResult(experiment_dir=exp_dir, created=created, skipped=skipped)


def cloud_readme_text(info: ExperimentRequestInfo) -> str:
    return (
        f"# {info.experiment_id}\n\n"
        f"Purpose: {info.purpose}\n\n"
        "Raw data immutability rule: raw data in `raw_data/` must not be renamed, "
        "moved, normalized, or overwritten after capture.\n\n"
        "Folder usage:\n"
        "- `raw_data/`: immutable source data only.\n"
        "- `analysis_runs/`: analysis run inputs, logs, and reproducible run records.\n"
        "- `processed_data/`: derived data products.\n"
        "- `final_outputs/`: final figures, tables, and report-ready files.\n"
        "- `docs/`: supporting human-readable notes and exported documents.\n\n"
        "AI-readable metadata: research workspace/"
        f"Experiments/{info.experiment_id}/\n\n"
        "Next human action: create the corresponding eNotebook entry manually.\n"
    )


def require_cloud_folder_request(info: ExperimentRequestInfo) -> None:
    if not request_bool(info.storage, "create_cloud_folder", False):
        raise CommandError(
            "--cloud-folder-only requires storage.create_cloud_folder: true in the request YAML. "
            "This prevents the command from silently doing nothing."
        )


def create_cloud_folder_if_requested(
    info: ExperimentRequestInfo,
    config: Mapping[str, Any],
) -> CloudResult:
    if not request_bool(info.storage, "create_cloud_folder", False):
        return CloudResult(experiment_dir=None, created=[], skipped=[])

    mode = info.storage.get("mode") or config_section(config, "storage", str(info.storage.get("provider", ""))).get("mode")
    if mode not in {"synced_folder", None, ""}:
        raise CommandError(f"Unsupported storage.mode for first adapter: {mode}")

    parent = resolve_storage_parent(info.storage, config)
    adapter = SyncedFolderStorageAdapter(parent)
    return adapter.create_or_complete(info)


def preflight_repo_metadata_registration(info: ExperimentRequestInfo, repo_root: Path) -> None:
    """
    Validate that register_from_request is expected to succeed without writing.

    This mirrors the existing request-file registration checks closely enough to
    catch known repository-side failures before creating a synced cloud folder.
    """

    request = read_request_file(info.request_path)
    project_section = required_mapping(request, "project")
    experiment_section = required_mapping(request, "experiment")
    context_section = required_mapping(request, "experimental_context")
    locations_section = required_mapping(request, "locations")
    summary_section = required_mapping(request, "summary")

    validate_project_request(repo_root, project_section)

    date_text = required_text(experiment_section, "date", "experiment")
    try:
        yyyymmdd, _iso_date = parse_experiment_date(date_text)
    except ValueError as e:
        raise RequestValidationError(f"Invalid experiment.date: {e}") from e

    status = required_text(experiment_section, "status", "experiment")
    if status not in STATUS_VALUES:
        allowed = ", ".join(STATUS_VALUES)
        raise RequestValidationError(f"Invalid experiment.status '{status}'. Use one of: {allowed}.")

    short_description = required_text(experiment_section, "short_description", "experiment")
    try:
        experiment_id = build_experiment_id(yyyymmdd, short_description)
    except ValueError as e:
        raise RequestValidationError(f"Invalid experiment.short_description: {e}") from e
    if experiment_id != info.experiment_id:
        raise CommandError(
            f"Preflight experiment_id mismatch: request info has {info.experiment_id}, "
            f"but request parses as {experiment_id}."
        )

    exp_dir = repo_root / "Experiments" / experiment_id
    if exp_dir.exists():
        raise RequestValidationError(f"Refusing to overwrite existing folder: {exp_dir}")

    index_path = repo_root / "EXPERIMENT_INDEX.md"
    index_text = index_path.read_text(encoding="utf-8")
    if experiment_id_in_index(index_text, experiment_id):
        raise RequestValidationError(f"experiment_id already present in {index_path}: {experiment_id}")

    required_text(experiment_section, "purpose", "experiment")
    for field in ("biological_material", "stimulus", "assay", "readout", "comparison"):
        required_text(context_section, field, "experimental_context")
    location_with_required_fields(locations_section, "note_location", ("system", "reference"))
    location_with_required_fields(
        locations_section,
        "raw_data_location",
        ("system", "path_or_url"),
        {"notes": DEFAULT_RAW_DATA_NOTES},
    )
    location_with_required_fields(locations_section, "processed_data_location", ("system", "path_or_url"))
    location_with_required_fields(locations_section, "analysis_location", ("system", "path"))
    required_text(summary_section, "short_title", "summary")
    required_text(summary_section, "index_summary", "summary")
    optional_text(summary_section, "freeform_notes", "(none)")
    load_summary_template(repo_root)


def rel_path(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def generated_paths(repo_root: Path, result: Mapping[str, Any]) -> list[str]:
    paths = [
        rel_path(repo_root, Path(result["manifest_path"])),
        rel_path(repo_root, Path(result["summary_path"])),
        rel_path(repo_root, Path(result["index_path"])),
    ]
    if result.get("project_registry_updated"):
        paths.append(rel_path(repo_root, Path(result["project_registry_path"])))
    return sorted(paths)


def scan_generated_metadata(repo_root: Path, paths: Sequence[str]) -> None:
    forbidden_prefixes = (
        "/" + "Users/",
        "/" + "home/",
        "/" + "Volumes/",
        "file:" + "//",
    )
    for rel in paths:
        path = repo_root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_prefixes:
            if marker in text:
                raise CommandError(
                    f"Generated Git metadata contains forbidden local path marker "
                    f"'{marker}' in {rel}."
                )


def should_auto_commit(info: ExperimentRequestInfo, config: Mapping[str, Any]) -> bool:
    git_config = config_section(config, "git")
    return request_bool(info.git, "auto_commit", request_bool(git_config, "auto_commit", False))


def should_auto_push(info: ExperimentRequestInfo, config: Mapping[str, Any]) -> bool:
    git_config = config_section(config, "git")
    return request_bool(info.git, "auto_push", request_bool(git_config, "auto_push", False))


def run_git_checked(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    repo_root: Path,
    args: Sequence[str],
    label: str,
) -> subprocess.CompletedProcess[str]:
    proc = runner(["git", *args], repo_root, capture=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise CommandError(f"{label} failed: {detail}")
    return proc


def cached_paths(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    repo_root: Path,
) -> list[str]:
    proc = run_git_checked(
        runner,
        repo_root,
        ["diff", "--cached", "--name-only"],
        "git diff --cached --name-only",
    )
    return sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())


def prepare_git_for_metadata_write(
    repo_root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> None:
    runner = runner or GitRunner()
    branch = run_git_checked(runner, repo_root, ["branch", "--show-current"], "git branch").stdout.strip()
    if branch != "main":
        raise CommandError(f"Refusing to auto-commit on branch '{branch}'. Expected 'main'.")

    pre_staged = cached_paths(runner, repo_root)
    if pre_staged:
        raise CommandError("Unrelated staged files block auto-commit: " + ", ".join(pre_staged))

    run_git_checked(runner, repo_root, ["pull", "--ff-only"], "git pull --ff-only")


def commit_generated_paths(
    repo_root: Path,
    experiment_id: str,
    allowlist: Sequence[str],
    *,
    auto_push: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> None:
    runner = runner or GitRunner()
    allowed = sorted(allowlist)

    run_git_checked(runner, repo_root, ["add", "--", *allowed], "git add generated paths")

    staged = cached_paths(runner, repo_root)
    if staged != allowed:
        raise CommandError(
            "Staged paths do not exactly match generated allowlist. "
            f"staged={staged}; allowed={allowed}"
        )

    run_git_checked(
        runner,
        repo_root,
        ["commit", "-m", f"Register experiment {experiment_id}"],
        "git commit",
    )
    if auto_push:
        run_git_checked(runner, repo_root, ["push"], "git push")


def delete_request_after_success(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def print_cloud_result(cloud_result: CloudResult) -> None:
    if cloud_result.experiment_dir is not None:
        print(f"Cloud folder: {cloud_result.experiment_dir}")
        if cloud_result.created:
            print("Created cloud paths:")
            for path in cloud_result.created:
                print(f"  {path}")
        if cloud_result.skipped:
            print("Existing cloud paths left unchanged:")
            for path in cloud_result.skipped:
                print(f"  {path}")


def print_e_notebook_action(info: ExperimentRequestInfo, cloud_result: CloudResult) -> None:
    cloud_folder = cloud_result.experiment_dir.name if cloud_result.experiment_dir else info.experiment_id
    print()
    print("Next human action:")
    print("Create an eNotebook entry with this title:")
    print(info.experiment_id)
    print()
    print("Paste this into the eNotebook:")
    print(f"AI-readable metadata: Experiments/{info.experiment_id}/")
    print(f"Cloud folder: {cloud_folder}")


def print_cloud_only_next_action(info: ExperimentRequestInfo, cloud_result: CloudResult) -> None:
    cloud_folder = cloud_result.experiment_dir.name if cloud_result.experiment_dir else info.experiment_id
    print()
    print("Next human action:")
    print("Use the cloud folder for raw data capture and storage:")
    print(cloud_folder)
    print()
    print("Git metadata was not modified. If this experiment is not already registered in")
    print("the research workspace, run the same request without --cloud-folder-only later.")


def new_exp(args: argparse.Namespace) -> int:
    try:
        repo_root = find_repo_root()
        config = load_config(repo_root, Path(args.config).expanduser() if args.config else None)
        request_path = choose_request_path(args)
        info = build_request_info(request_path)

        if args.cloud_folder_only:
            require_cloud_folder_request(info)
            confirm_execution(info, assume_yes=args.yes, action_label="cloud folder completion only")
            cloud_result = create_cloud_folder_if_requested(info, config)
            if cloud_result.experiment_dir is None:
                raise CommandError("Cloud folder was not created or completed.")
            if not args.keep_request:
                delete_request_after_success(info.request_path)
        else:
            confirm_execution(info, assume_yes=args.yes)
            auto_commit = should_auto_commit(info, config)
            auto_push = should_auto_push(info, config)
            if auto_push and not auto_commit:
                raise CommandError("git.auto_push requires git.auto_commit.")
            git_runner = GitRunner()
            if auto_commit:
                prepare_git_for_metadata_write(repo_root, runner=git_runner)

            preflight_repo_metadata_registration(info, repo_root)
            cloud_result = create_cloud_folder_if_requested(info, config)
            result = register_from_request(info.request_path, repo_root)
            allowed_paths = generated_paths(repo_root, result)
            scan_generated_metadata(repo_root, allowed_paths)

            if auto_commit:
                commit_generated_paths(
                    repo_root,
                    info.experiment_id,
                    allowed_paths,
                    auto_push=auto_push,
                    runner=git_runner,
                )

            if not args.keep_request:
                delete_request_after_success(info.request_path)

    except (
        FileNotFoundError,
        OSError,
        RequestValidationError,
        ValueError,
        CommandError,
    ) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.cloud_folder_only:
        print(f"Prepared cloud folder only: {info.experiment_id}")
        print_cloud_result(cloud_result)
        print("Request YAML preserved." if args.keep_request else "Request YAML deleted after success.")
        print_cloud_only_next_action(info, cloud_result)
    else:
        print(f"Registered experiment: {info.experiment_id}")
        print_cloud_result(cloud_result)
        print("Request YAML preserved." if args.keep_request else "Request YAML deleted after success.")
        print_e_notebook_action(info, cloud_result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-os")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_exp_parser = subparsers.add_parser(
        "new-exp",
        description="Register a new experiment from a downloaded request YAML file.",
    )
    new_exp_parser.add_argument("request_yaml", nargs="?", help="Path to experiment_request_*.yaml")
    new_exp_parser.add_argument(
        "--latest-download",
        action="store_true",
        help="Use the newest experiment_request_*.yaml or .yml file in Downloads.",
    )
    new_exp_parser.add_argument("--downloads-dir", help=argparse.SUPPRESS)
    new_exp_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    new_exp_parser.add_argument(
        "--keep-request",
        action="store_true",
        help="Keep the request YAML after successful completion.",
    )
    new_exp_parser.add_argument(
        "--cloud-folder-only",
        action="store_true",
        help=(
            "Create or complete only the configured experiment cloud/data folder "
            "and standard subfolders; do not update Git metadata."
        ),
    )
    new_exp_parser.add_argument("--config", help="Path to local research_os config YAML.")
    new_exp_parser.set_defaults(func=new_exp)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "new-exp" and args.latest_download and args.request_yaml:
        parser.error("new-exp accepts either a request YAML path or --latest-download, not both.")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
