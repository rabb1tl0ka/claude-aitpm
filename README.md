# Claude AITPM - AI Technical Project Manager

An AI-powered PM bot that monitors JIRA, surfaces activity to Slack, and lets you take action from your phone - without opening a laptop.

## What it does

Runs continuously and monitors all tickets under your watched epics (defined in your radar file). Every 60 minutes it:

- **Surfaces activity** - status changes (good news included), new comments with full text
- **Flags stale tickets** - by priority: P1 = 1 day, P2 = 2 days, P3 = 4 days (active sprint only)
- **Detects unblocked tickets** - when a blocker moves to Done, drafts a notification to the assignee
- **Flags planning gaps** - tickets with no sprint assigned, one alert per ticket with a link
- **Posts all findings to your private channel** - alerts for your awareness, drafts for your approval

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

Mention `@aitpm` in your private channel with any command and it responds in thread - same as talking to Claude Code on your laptop, with full project context loaded.

Examples:
- `@aitpm what's the status on payments?`
- `@aitpm draft an update for the backend team on Network Search v3`
- `@aitpm set sprint 42 on PROJ-123`

---

## Getting Started (new project)

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Set environment variables

Create a `.env` file at the project root:

```
SLACK_BOT_TOKEN=xoxb-...
ATLASSIAN_EMAIL=you@yourcompany.com
ATLASSIAN_API_TOKEN=...
ATLASSIAN_SITE=yourcompany.atlassian.net
CLAUDE_CODE_OAUTH_TOKEN=...
```

- **ATLASSIAN_API_TOKEN** — generate at https://id.atlassian.com/manage-profile/security/api-tokens
- **ATLASSIAN_SITE** — your Atlassian domain, e.g. `yourcompany.atlassian.net` (no `https://`)
- **CLAUDE_CODE_OAUTH_TOKEN** — run `claude setup-token` in your terminal. The bot uses `claude-agent-sdk` with `setting_sources=["user"]`, routing all LLM calls through your Claude Code subscription. No separate Anthropic API key needed.

### 3. Create your config

```bash
cp configs/example.yaml configs/your-project.yaml
```

Edit `configs/your-project.yaml` and fill in every key. The file is fully documented with inline comments. Key things to set:

| Key | What it is |
|-----|-----------|
| `tpm_name` | Your display name — used in first-person nudge comments |
| `aitpm_name` | Your AI twin's name — used in agent persona and Slack replies |
| `tpm_slack_user_id` | Your Slack user ID — find it: click your name → View profile → More (···) → Copy member ID |
| `jira_project_key` | Your Jira project key (e.g. `ENG`, `PROJ`) |
| `jira_radar_file` | Path to your radar file — see step 4 |
| `slack_aitpm_channel` | Private channel where the bot posts alerts and drafts |
| `slack_channels` | Team channels available for outbound draft messages |
| `slack_channel_ids` | Channel IDs for reading history (Slack API requires IDs, not names) |

### 4. Create your radar file

The radar file defines which epics and tickets the bot monitors. Copy the template:

```bash
cp configs/radar_template.md ~/path/to/your-radar.md
```

Follow the instructions inside the template to write your Step 1 and Step 2 JQL queries. Point `jira_radar_file` in your config to this file.

### 5. Slack app scopes required

```
channels:history
channels:read
chat:write
reactions:add
reactions:read
```

### 6. Run

```bash
# Start the bot (uses cloudsort config by default — pass --config to override)
python3 main.py --config your-project

# One-shot runs (useful for testing)
python3 main.py --config your-project --once monitor
python3 main.py --config your-project --once digest
python3 main.py --config your-project --once poll

# Force a full ticket fetch (ignores incremental cache)
python3 main.py --config your-project --refresh-cache
```

---

## Configuration reference

See `configs/example.yaml` for the full documented config. Key sections:

```yaml
# Identity
tpm_name: "Alex"
aitpm_name: "Alex AI TPM"
tpm_slack_user_id: ""

# Jira
jira_project_key: PROJ
jira_radar_file: ~/path/to/radar.md

# Slack
slack_aitpm_channel: "#proj-aitpm"
slack_channels:
  general: "#proj-general"
  backend: "#proj-backend"

# Staleness thresholds (business days before nudge)
staleness_thresholds:
  P1: 1
  P2: 2
  P3: 4
  P4: null   # never nudge

# Schedule
schedule:
  monitor_interval_min: 60
  approval_interval_min: 3
  timezone: "America/New_York"
  work_hours_start: 8
  work_hours_end: 21

# Toggle monitor analysis blocks
monitor_features:
  status_changes: true
  comment_activity: true
  staleness: true
  planning_gaps: false
  dependency_chains: true
  scope_summary: false
```

## Radar file

The bot reads the radar file defined in `jira_radar_file`. It runs the Step 1 JQL to get current watched epics, then Step 2 to fetch all active child tickets. See `configs/radar_template.md` for the expected format and instructions.

## Architecture

```
main.py             - scheduler loop, approval poll, inbound check
src/agents.py       - Claude agent prompts (monitor, command, revision, jira comment, nudge drafter)
src/slack_client.py - all Slack I/O
src/config.py       - config loader
src/state.py        - state persistence + Jira REST fetch helpers
configs/            - project configs (one yaml per project)
state/              - runtime state and agent output files
logs/               - timestamped log files
```

Agents do all JIRA analysis and write JSON output files. Python reads those files and handles all Slack I/O. Agents never post to Slack directly.

## User map

The bot maintains a `user_map` in `state/state.json` that maps JIRA display names to accountIds. This is used for proper JIRA @mentions in comments (ADF format) so assignees actually get notified.

Built automatically — every monitor run extracts accountIds from ticket assignee fields and merges them in. No manual maintenance needed.

## State

`state/state.json` persists:
- Known ticket states (status, assignee, last updated, sprint state, blocker keys)
- Pending drafts awaiting approval
- Last run timestamps
- Slack channel cursors (for incremental history reads)
- User map (displayName to accountId)

Delete `state/state.json` to force a full re-evaluation on next run.
