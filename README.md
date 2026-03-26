# Claude AITPM - AI Technical Project Manager

An AI-powered PM bot that monitors JIRA, surfaces activity to Slack, and lets you take action from your phone - without opening a laptop.

## What it does

Runs continuously and monitors all tickets under your watched JB epics (defined in the JB Radar file). Every 60 minutes it:

- **Surfaces activity** - status changes (good news included), new comments with full text
- **Flags stale tickets** - by priority: P1 = 1 day, P2 = 2 days, P3 = 4 days (active sprint only)
- **Detects unblocked tickets** - when a blocker moves to Done, drafts a notification to the assignee
- **Flags planning gaps** - tickets with no sprint assigned, one alert per ticket with a link
- **Posts all findings to `#cloudsort_aitpm`** - alerts for your awareness, drafts for your approval

Approval poll runs every minute (24/7, not gated to work hours) - picks up your replies and ✅ reactions.

## Approval flow

Each draft requires your approval before anything is sent:

- Reply `"send that"` or react ✅ → bot executes the action
- Reply with edits → bot revises and posts the updated draft
- Reply with a question or command → bot answers or acts on it

## Actions the bot can take (after your approval)

| Action | Trigger |
|--------|---------|
| Post Slack message to team channel | Unblock notification |
| Post JIRA comment on a ticket | Staleness nudge |

## @aitpm commands

Mention `@aitpm` in `#cloudsort_aitpm` with any command and it responds in thread - same as talking to Claude Code on your laptop, with full project context loaded.

Examples:
- `@aitpm what's the status on payments?`
- `@aitpm draft an update for the backend team on Network Search v3`
- `@aitpm set sprint 161 on CLOUD-6521`

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file:

```
SLACK_BOT_TOKEN=xoxb-...
CLAUDE_CODE_OAUTH_TOKEN=...
```

### 3. Configure the project

Edit `configs/cloudsort.yaml`:

```yaml
owner_slack_user_id: "U02GXNG41GE"  # your Slack user ID
```

Find your Slack user ID: click your name → View profile → More (···) → Copy member ID.

### 4. Slack app scopes required

```
channels:history
channels:read
chat:write
reactions:add
reactions:read
```

### 5. Run

```bash
# Start the server
python3 main.py

# One-shot runs (for testing)
python3 main.py --once monitor
python3 main.py --once digest
python3 main.py --once poll
```

## Configuration

`configs/cloudsort.yaml`:

```yaml
project_name: CloudSort
owner_slack_user_id: ""          # your Slack user ID
jira_project_key: CLOUD
jira_radar_file: ~/path/to/jb-watching-radar.md
staleness_thresholds:
  P1: 1                          # days before nudge
  P2: 2
  P3: 4
  P4: null                       # never nudge
slack_aitpm_channel: "#cloudsort_aitpm"
slack_channels:
  general: "#cloudsort_chat"
  backend: "#cloudsort_backend"
  webapp: "#cloudsort_webapp"
  design: "#cloudsort_design"
sprint:
  name: ""                       # update each sprint
  start: ""
  end: ""
schedule:
  monitor_interval_min: 60
  approval_interval_min: 1
  timezone: "Europe/Lisbon"
```

## JB Radar file

The bot reads the radar file defined in `jira_radar_file`. It runs Step 1 JQL dynamically to get current watched epics, then Step 2 to get all active child tickets. The epic list in the radar file is a human reference - the bot always fetches fresh.

## Architecture

```
main.py          - scheduler loop, approval poll, inbound check
src/agents.py    - Claude agent prompts (monitor, command, revision, jira comment)
src/slack_client.py - all Slack I/O
src/config.py    - config loader
src/state.py     - state persistence (state/state.json)
configs/         - project configs (one yaml per project)
state/           - runtime state and agent output files
logs/            - timestamped log files
```

Agents do all JIRA analysis and write JSON output files. Python reads those files and handles all Slack I/O. Agents never post to Slack directly.

## State

`state/state.json` persists:
- Known ticket states (status, assignee, last updated, sprint state, blocker keys)
- Pending drafts awaiting approval
- Last run timestamps

Delete `state/state.json` to force a full re-evaluation on next run.
