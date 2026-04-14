---
status: todo
priority: medium
owner: ""
---

# Idea: Per-Config State Files

## One-Line Overview
Split the shared state.json into per-config files to eliminate cross-project state collisions as AI TPM expands to multiple projects.

## Problem

`state.json` is currently shared across all projects. As AI TPM expands to support multiple project configs (e.g. `cloudsort.yaml`, `acme.yaml`), a single state file creates collisions — pending drafts, ticket states, TLU progress, etc. from different projects would all mix together.

## Idea

Split state into per-config files:

- `state-cloudsort.json` — paired with `configs/cloudsort.yaml`
- `state-acme.json` — paired with `configs/acme.yaml`
- `state.json` — reserved for state that is not project-specific (e.g. scheduler heartbeat)

The config name (without extension) determines the state filename: `state-{config_name}.json`.

## Benefits

- Clean isolation between projects
- Multi-project support becomes trivial — run two instances with different `--config` flags, no state bleed
- Easier to inspect/debug state for a specific project
- `state.json` stays lean (only truly global state)

## Implementation notes

- `src/state.py` loads/saves state — change `STATE_FILE` to be derived from `cfg["_config_name"]` (injected at load time in `main.py`)
- Migration: rename existing `state.json` to `state-cloudsort.json` on first run if a cloudsort config is active
- `.gitignore` already ignores `state/` so no changes needed there
