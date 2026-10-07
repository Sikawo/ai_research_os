# Experiment Registration Workflow

This repository supports interactive, request-file, and AI-chat-assisted
experiment registration paths.

The public repository contains reusable framework code only. Keep experiment
instances in a separate research workspace. Set `RESEARCH_OS_WORKSPACE_ROOT` to
that workspace's absolute path, or run commands from inside it. The workspace
must contain `LAB_SCHEMA.md` and `EXPERIMENT_INDEX.md`; personal locations and
private data never belong in this public repository.

The existing interactive workflow remains available:

```bash
python3 Scripts/register_experiment.py
```

Use it when the researcher wants Terminal to ask each question one at a time.

## Phase 2 Request-File Workflow

The Phase 2 workflow lets a researcher describe an experiment in ChatGPT and
ask ChatGPT to create a structured request YAML file. The user then registers
the experiment with one command:

```bash
research-os new-exp ~/Downloads/experiment_request_<experiment_id>.yaml
```

If `research-os` is not installed on `PATH`, run the repository wrapper
directly:

```bash
Scripts/research-os new-exp ~/Downloads/experiment_request_<experiment_id>.yaml
```

The shorter downloaded-file flow can also select the newest matching request in
the user's Downloads folder:

```bash
research-os new-exp --latest-download
```

`--latest-download` prints the selected file path, parsed `experiment_id`,
project, and cloud target before running. It asks for confirmation unless
`--yes` is supplied.

The request format is documented in:

```text
Templates/experiment_request_template.yaml
```

The script creates the same durable repository metadata as the interactive
workflow:

- `Experiments/<experiment_id>/manifest.yaml`
- `Experiments/<experiment_id>/summary.md`
- one appended row in `EXPERIMENT_INDEX.md`
- optionally, one appended row in `PROJECT_REGISTRY.md`

Raw data stay external. The request file should store safe external references,
such as Box-relative paths, cloud folder names, or other stable external
pointers. Do not include local absolute paths, local file URLs, or raw source URL
fields in repository metadata.

After a fully successful `research-os new-exp` run, the consumed request YAML is
deleted by default. Use `--keep-request` to preserve it. The request file is not
deleted if parsing, repository metadata creation, cloud folder completion,
auto-commit, or auto-push fails.

If no `storage` block is provided, the command runs the Git metadata
registration only and skips cloud folder creation. If `storage.create_cloud_folder:
true` is present, the first supported backend is the local/synced-folder adapter
for Box Drive or another synced folder provider.

Example storage block:

```yaml
storage:
  provider: box
  mode: synced_folder
  create_cloud_folder: true
  parent_ref: default_experiments_parent
  folder_template: standard_experiment_v1

git:
  auto_commit: true
  auto_push: true
```

Local configuration supplies execution-only paths such as the synced folder
parent. A typical user config is:

```yaml
storage:
  default_provider: box
  box:
    mode: synced_folder
    experiments_parent: <Box Drive Experiments folder>

git:
  auto_commit: true
  auto_push: true
  commit_only_generated_paths: true

safety:
  forbid_absolute_paths_in_git_metadata: true
  forbid_raw_data_modification: true
  allowed_cloud_actions:
    - create_folder
    - create_readme
```

The CLI discovers config from `--config`, `RESEARCH_OS_CONFIG`,
`config/research_os_config.yaml`, or `~/.config/research_os/config.yaml`.
Execution-only local absolute paths from config, or from `storage.parent_path`,
must not be written to committed Git metadata.

The synced-folder adapter creates or completes:

```text
<cloud_experiments_parent>/
└── <experiment_id>/
    ├── README.md
    ├── raw_data/
    ├── analysis_runs/
    ├── processed_data/
    ├── final_outputs/
    └── docs/
```

If the cloud experiment folder already exists, the command creates missing
standard directories and leaves existing files unchanged. It never deletes,
renames, moves, normalizes, or overwrites raw data. If `README.md` already
exists, it is left unchanged.

When Git automation is enabled, the command stages only the generated metadata
allowlist:

```text
EXPERIMENT_INDEX.md
Experiments/<experiment_id>/manifest.yaml
Experiments/<experiment_id>/summary.md
PROJECT_REGISTRY.md
```

`PROJECT_REGISTRY.md` is included only when project creation was explicitly
requested and performed. The command refuses unrelated staged files, checks that
the branch is `main`, and runs `git pull --ff-only` before generating metadata
files. After metadata generation, it uses `git add -- <allowlist>`, verifies the
staged paths exactly match the allowlist, commits with `Register experiment
<experiment_id>`, and pushes only when configured.

## Project Registry Behavior

If `project.project_id` already exists in `PROJECT_REGISTRY.md`, the script uses
that project.

If the project is missing and the request includes:

```yaml
project:
  create_if_missing: true
```

the script appends a new project row using `project_id`, `display_name`,
`description`, and `status`.

If the project is missing and `create_if_missing` is false or absent, the script
stops and asks the user to either use an existing project ID or set
`create_if_missing: true`.

## Git Behavior

The legacy metadata script,
`Scripts/register_experiment_from_request.py`, still only updates repository
files and leaves Git actions human-controlled.

The command-style workflow, `research-os new-exp`, can optionally auto-commit
and auto-push when enabled by local config or the request YAML. Those Git
actions are constrained to the generated experiment metadata allowlist described
above. If auto-commit is not enabled, the command leaves the metadata diff for
human review.

## Command Wrapper

The `aiexp` wrapper prints concise guidance for the request-file workflow. It
does not create request files, run registration, run validation, stage, commit,
push, or upload anything.

## Downloadable YAML AI Chat Rule

When the user asks to start or register an experiment, the AI assistant must use
the request-file workflow. It should not directly register the experiment
through a GitHub connector when the intended workflow requires cloud folder
creation, because cloud folder creation must be performed by the local CLI or a
future provider adapter.

### Hard AI behavior contract

Experiment registration belongs to the configured research workspace. Direct
GitHub editing is the wrong route for experiment registration: AI assistants must not directly
create GitHub issues, pull requests, Markdown experiment notes, `manifest.yaml`,
`summary.md`, `EXPERIMENT_INDEX.md`, or `Experiments/` folders for a new
experiment.

a private research vault can store planning notes only after an experiment has
a canonical `EXP_...` ID, but it is not the experiment-registration source of
truth. The correct AI output is a downloadable request YAML plus exactly one
local command:

```bash
RESEARCH_OS_WORKSPACE_ROOT=<research_workspace> <ai_research_os_checkout>/Scripts/research-os new-exp --latest-download --keep-request
```

The user can continue to speak casually in Japanese or English. The AI should
normalize the metadata, provide the request file as a download, and let the
local Python workflow create repository metadata and any requested cloud
folder.

Regression example:

- Bad: `DEMO-PROJECT-20300101-001`
- Good: `EXP_20300104_demo_feasibility`

### Short natural-language trigger rule

The user should be able to use short, natural phrases. The AI should accept
reasonable wording variation and should not require a canonical command string.
When the current conversation is about this repository or the user tags GitHub,
treat short phrases such as the following as experiment-registration intent:

- "実験登録して"
- "実験を登録して"
- "この実験を登録"
- "新しい実験"
- "新規実験"
- "実験追加"
- "実験入れて"
- "今日の実験"
- "この条件で登録"
- "start experiment"
- "new experiment"
- "register experiment"
- "register this experiment"
- "log this experiment"
- "add this experiment"

For these short triggers, the AI should immediately enter the request-file
workflow: inspect `PROJECT_REGISTRY.md` if needed, infer metadata that is clear
from the user's message, ask only for missing metadata, generate a downloadable
`experiment_request_*.yaml`, and provide exactly one local registration command.

When the user says they want to start or register an experiment, the AI should
guide the user through the Phase 2 request-file workflow. It should not tell
the user to run the old interactive script first.

Trigger phrases include:

- "実験したい"
- "実験を始めたい"
- "今日の実験を登録したい"
- "I want to start an experiment"
- "register this experiment"

The AI should ask only for metadata that is missing from the user's message:

- project
- date
- biological material/cells
- stimulus
- assay
- readout
- comparison
- raw data location
- status
- optional notes

The AI should normalize:

- `project_id` as snake_case
- `experiment_id` as `EXP_YYYYMMDD_short-description`

If the project is missing, the AI should explain that the project is not yet in
`PROJECT_REGISTRY.md`. It should propose `create_if_missing: true` only after
the user confirms that a new project should be added.

The AI must:

1. Ask only for missing experiment metadata.
2. Generate a valid `experiment_request_*.yaml` file.
3. Provide the YAML as a downloadable file.
4. Provide exactly one pasteable terminal command that registers the experiment
   from the downloaded YAML.
5. Avoid requiring the user to paste long YAML text into Terminal.
6. Prefer the downloaded-file workflow over heredoc `/tmp` blocks.
7. Use a heredoc fallback only if the user explicitly asks for no download.
8. Avoid direct GitHub edits to `PROJECT_REGISTRY.md`, `EXPERIMENT_INDEX.md`,
   `Experiments/`, or `Analysis/` unless the user explicitly asks to bypass the
   request-YAML workflow.

Preferred command, robust when `research-os` is not on `PATH`:

```bash
RESEARCH_OS_WORKSPACE_ROOT=<research_workspace> <ai_research_os_checkout>/Scripts/research-os new-exp --latest-download --keep-request
```

If `research-os` is installed on `PATH`, this is also acceptable:

```bash
RESEARCH_OS_WORKSPACE_ROOT=<research_workspace> research-os new-exp --latest-download --keep-request
```

The assistant should mention that `research-os new-exp` deletes the consumed
YAML after success unless `--keep-request` is used. AI-provided commands should
use `--keep-request` by default so the downloaded request file remains available
for review and reproducibility.

Safety requirements:

- never include local absolute filesystem paths in
  repository metadata
- convert raw data paths to repo-safe external references, such as Box-relative
  paths, cloud folder names, or other stable external references
- ask the user to confirm ambiguous raw data references before registration
- never read raw data contents
- never require pasted long heredoc YAML blocks unless explicitly requested
- never read raw data contents
