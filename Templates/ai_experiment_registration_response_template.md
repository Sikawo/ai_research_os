# AI Experiment Registration Response Template

Use this response shape when an AI assistant prepares an experiment request YAML
for the user. The YAML must be a downloadable file, not a long heredoc, unless
the user explicitly asks for no download.

The request YAML should include `experiment.date` and
`experiment.short_description`; the local Python workflow builds the final
`EXP_YYYYMMDD_slug` ID. Do not generate a new Python script for an individual
experiment.

## Proposed experiment ID

`EXP_YYYYMMDD_slug`

## Download

[Download experiment_request_EXP_YYYYMMDD_slug.yaml]

## Run

```bash
RESEARCH_OS_WORKSPACE_ROOT=<research_workspace> <ai_research_os_checkout>/Scripts/research-os new-exp --latest-download --keep-request
```

## This will create

* `Experiments/EXP_YYYYMMDD_slug/manifest.yaml`
* `Experiments/EXP_YYYYMMDD_slug/summary.md`
* one row in `EXPERIMENT_INDEX.md`
* optional cloud folder, if requested
