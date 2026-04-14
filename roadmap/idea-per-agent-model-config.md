---
status: todo
priority: low
owner: ""
---

# Idea: Per-Agent Model Config

## One-Line Overview
Let users override the Claude model per agent in the project config YAML, eliminating hardcoded model selections in source code.

## Problem

Agent model selection is currently hardcoded in `src/agents.py`. Changing which model a given agent uses requires a code change.

## Proposed solution

Add a `models:` block to `configs/{project}.yaml` that lets the user override the model per agent:

```yaml
models:
  monitor: haiku          # default
  nudge_drafter: haiku    # default
  revision: haiku         # default
  tlu_generation: sonnet  # default
  tlu_revision: sonnet    # default
  command: haiku          # default
```

Unset keys fall back to a global default (haiku). Each `run_*` function reads its model via a helper like `cfg_model(cfg, "tlu_revision", default="haiku")`.

## Why not now

- Touches `configs/`, `src/config.py`, and every agent function
- Deserves its own branch
- Current hardcoded values are reasonable defaults for production use
