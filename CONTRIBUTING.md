# Contributing

## Prerequisites

- Python 3.12+
- A Slack bot token with the required scopes (see README)
- Atlassian API token
- Claude Code OAuth token (`claude setup-token`)
- A project config and radar file (see README)

## Setup

```bash
git clone https://github.com/rabb1tl0ka/claude-aitpm.git
cd claude-aitpm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp configs/example.yaml configs/your-project.yaml
# fill in configs/your-project.yaml and create your radar file
cp .env.example .env
# fill in .env
```

## Running locally

Use `--once` to run a single pass without the full loop — much faster for testing:

```bash
# Run one monitor pass (fetch Jira state, generate alerts/drafts)
python3 main.py --config your-project --once monitor

# Run one approval poll pass (pick up reactions/replies)
python3 main.py --config your-project --once poll

# Run one digest pass
python3 main.py --config your-project --once digest

# Force a full ticket fetch (ignore incremental cache)
python3 main.py --config your-project --refresh-cache --once monitor
```

Logs land in `logs/`. Check there first when something looks off.

## Picking up a roadmap item

Roadmap lives in `roadmap/`. Three types:

| Prefix | Meaning |
|---|---|
| `feat-` | Fully specced — branch name, implementation steps, test plan all inside. Ready to build. |
| `idea-` | Early exploration — not yet fully designed. Good for discussion or turning into a `feat-`. |
| `challenge-` | Known problem, solution still open. |

When you pick something up, update the frontmatter:

```yaml
status: in-progress
owner: "@your-handle"
```

> The roadmap convention (templates, frontmatter rules, auto-generated table) comes from
> [LokaHQ/repo-roadmap](https://github.com/lokahq/repo-roadmap) — a reusable standard
> for tracking features, ideas, and challenges in any repo.

## Branch naming

```
feat/<slug>     — new feature
fix/<slug>      — bug fix
chore/<slug>    — tooling, config, convention updates
```

## Before opening a PR

- Run `--once monitor` against your config and verify the output looks sane
- Run `--once poll` and verify approval logic works
- Check `logs/` for any errors or unexpected agent output
- Make sure your config changes are reflected in `configs/example.yaml` if they're broadly applicable

## Adding a roadmap item

Use the templates in `roadmap/templates/`:

```bash
cp roadmap/templates/template-feat.md roadmap/feat-your-feature.md
# or template-idea.md / template-challenge.md
```

Fill in the frontmatter, title, and `## One-Line Overview`. Claude Code will keep the table in `roadmap/README.md` up to date automatically.
