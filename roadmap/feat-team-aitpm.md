---
status: todo
priority: high
owner: ""
---

# Feature Spec: Team AI TPM

## One-Line Overview
Expose the AI TPM to the full team via Slack so anyone can query project status, feature context, and ticket state — writes execute immediately with TPM notification, deletes require TPM approval.

> **Terminology:** "TPM" in this spec always means the Human TPM / project owner (the person running claude-aitpm). "AI TPM" means the agent.

## Branch

`feat/team-aitpm`

## Goal

Expose the AI TPM to the full team via Slack. Team members can query project status, feature context, ticket state, and blockers by mentioning `@aitpm` in the configured Slack channel. Write operations execute immediately — team members already have Jira access, the AI TPM is not a permission layer. The TPM is notified of all writes. Delete operations are the one hard gate: always require TPM approval before execution.

## Target users

Any team member defined in `team_members` config — name, role, and Slack ID. Roles are freeform (Backend, Design, QA, Sales, etc.). No assumptions about sprint cadence or ceremonies.

## Use cases

### Daily queries (high frequency)
- "What's the status of CLOUD-XXXX?"
- "What's blocking me right now?"
- "Is the design for [feature] ready?"
- "What should I be working on this sprint?"
- "Who's working on X?"

### Write requests (execute immediately, TPM notified)
- "Move CLOUD-XXXX to In Review"
- "Add a comment to CLOUD-XXXX saying I'm blocked on the API"
- "Flag CLOUD-XXXX as blocked by CLOUD-YYYY"
- "Remind me to follow up on CLOUD-XXXX tomorrow"
- "Save a note that we decided to drop feature Y"

### Delete requests (always gated — TPM must approve)
- "Delete CLOUD-XXXX"
- "Remove the link between CLOUD-XXXX and CLOUD-YYYY"

### Ceremony prep (medium frequency)
- "Summarize what changed since yesterday" — standup
- "What's left in this sprint?" — sprint health
- "What did we ship this sprint?" — retro input
- "What tickets aren't planned yet?" — planning gaps
- "Give me the full scope of [epic]" — kickoff context

### Feature context
- "What's the goal of [epic]?"
- "Why did we go with X over Y?" — decisions in vault notes
- "How does [feature] work at a high level?"

---

## Design decisions

### Write notification
Writes execute immediately — the AI TPM is not a permission layer on top of Jira. Team members already have direct Jira access; the AI TPM is just a faster interface. After executing, the AI TPM posts a notification to `slack_aitpm_channel`:

> *"Zoran moved CLOUD-6329 to In Review."*

TPM stays informed without becoming a bottleneck.

### Delete gating
Deletes are irreversible, so they always require TPM approval before execution. The AI TPM posts to `slack_aitpm_channel`:

> *"Zoran asked to delete CLOUD-6329. Approve? Reject?"*

TPM replies in thread — same approval flow as existing pending_drafts.

### Team member notes
Each team member has a notes directory at `{project_notes_path}/team/{member_slug}/`. Notes are open to all team members — any member can ask "what are Zoran's notes on this?" The AI TPM notifies the TPM (no gate) when a note is saved.

### Rate limiting
Max N commands per user per hour (configurable). Tracked in state. On limit hit, bot replies in thread: "You've hit the limit for now — try again in X minutes."

### Intent classification
Before executing any team command, a lightweight classify step determines the intent: read, write, delete, or note. Routes accordingly.

### Persona
The AI TPM responds as itself — a project assistant with access to tickets, vault notes, and project context. It does not speak as the TPM or impersonate them. First-person framing ("I decided X") is reserved for nudge comments to the TPM only.

### Unknown answers — escalate to TPM
When the AI TPM cannot answer a question from available data (Jira, vault, team notes), it does not guess. It:
1. Tells the team member: *"I don't have enough context to answer that. Let me check with [TPM name]."*
2. Posts to `slack_aitpm_channel`: *"Zoran asked: '[question]' — I couldn't find an answer. What should I tell him?"*
3. When the TPM replies, relays the answer back to Zoran in the original thread.

This keeps the TPM in the loop without making them a bottleneck on queries the AI TPM *can* answer.

---

## Implementation

### Config additions (`config.yaml`)

```yaml
team_access:
  enabled: false                    # feature flag — off by default
  allowed_slack_user_ids: []        # empty = owner only; ["*"] = all workspace members
  max_commands_per_user_per_hour: 5

team_members:
  - name: "Zoran"
    role: "Backend"
    slack_id: "U12345"
  - name: "Ana"
    role: "Design"
    slack_id: "U67890"
  # roles are freeform: Backend, Frontend, Mobile, Design, QA, Sales, etc.
```

### State additions (`state.json`)

```json
{
  "user_command_counts": {
    "<slack_user_id>": ["<iso_ts>", "<iso_ts>"]   // rolling list of command timestamps
  },
  "pending_deletes": [
    {
      "id": "<uuid>",
      "requester_id": "<slack_user_id>",
      "requester_name": "<display_name>",
      "command_text": "...",
      "tool": "<tool_name>",
      "tool_args": {},
      "slack_ts": "<ts of approval post in slack_aitpm_channel>",
      "status": "pending",
      "posted_at": "..."
    }
  ],
  "pending_escalations": [
    {
      "id": "<uuid>",
      "requester_id": "<slack_user_id>",
      "requester_name": "<display_name>",
      "question": "...",
      "original_thread_ts": "<ts of requester's message>",
      "slack_ts": "<ts of escalation post in slack_aitpm_channel>",
      "status": "pending",
      "posted_at": "..."
    }
  ]
}
```

### New: `src/utils.py` — rate limiter

```python
def check_rate_limit(state: dict, user_id: str, max_per_hour: int) -> bool:
    """Returns True if user is within limit, False if exceeded. Prunes stale entries."""
```

### New: `safe_read` tool wrapper (`src/tools.py`)

Wraps `Read`, `Glob`, and `Bash` calls. Before executing, checks whether any resolved path is inside a `private/` directory. If so, returns an error rather than the file contents. This is enforcement at the tool layer — not prompt-level instruction.

```python
def is_private_path(path: str) -> bool:
    """Returns True if path contains a /private/ component."""
```

All team-facing tool calls route through this wrapper.

### New: `run_team_command` in `src/agents.py`

```python
async def run_team_command(cfg: dict, state: dict, command_text: str, requester: dict) -> dict | None:
```

- Prompt includes requester context (name, role from `team_members`)
- Returns `{response: str, intent: "read" | "write" | "delete" | "note", tool: str | None, tool_args: dict | None}`

### Changes to `run_inbound_check` in `main.py`

1. Check `team_access.enabled` — if off, owner-only behaviour unchanged
2. Check if user is in `allowed_slack_user_ids` (or `"*"`)
3. Call rate limiter — reject with message if exceeded
4. Classify intent:
   - `read` → execute with `_TEAM_READ_TOOLS` → reply in thread
   - `write` → execute with `_TEAM_WRITE_TOOLS` → reply in thread → notify TPM in `slack_aitpm_channel`
   - `delete` → post approval request to `slack_aitpm_channel` → add to `pending_deletes` → tell requester "waiting for TPM approval"
   - `note` → write to `{project_notes_path}/team/{member_slug}/` → reply in thread → notify TPM in `slack_aitpm_channel`

### Changes to `run_approval_poll` in `main.py`

- Poll `pending_deletes`: on TPM reply → approve: execute delete, notify requester; reject: notify requester
- Poll `pending_escalations`: on TPM reply → relay TPM's answer verbatim back to requester in their original thread

---

## Tool sets

### `_TEAM_READ_TOOLS`
```python
[
    "mcp__cloudsort-jira__searchJiraIssuesUsingJql",
    "mcp__cloudsort-jira__getJiraIssue",
    "safe_read",   # wraps Read — blocks private/ paths
    "safe_glob",   # wraps Glob — blocks private/ paths
    "safe_bash",   # wraps Bash — blocks private/ paths
]
```

### `_TEAM_WRITE_TOOLS`
```python
[
    "mcp__cloudsort-jira__transitionJiraIssue",
    "mcp__cloudsort-jira__addCommentToJiraIssue",
    "mcp__cloudsort-jira__createIssueLink",
    "mcp__cloudsort-jira__editJiraIssue",
    "mcp__cloudsort-jira__addWorklogToJiraIssue",
    "mcp__cloudsort-jira__createJiraIssue",
]
```

No delete tools (those are gated and executed only after TPM approval). No Slack tools (team member already has Slack).

---

## Not in V1

- Query response cache (see `idea-team-query-cache.md`) — add once query volume justifies it
- Multi-project support — team commands scoped to the same project config as the owner
- Listening in channels other than the configured `slack_aitpm_channel`
- Soft-suggest on unknown answers: AI TPM makes a best-effort inference from vault/sprint context instead of hard-escalating — add once escalation volume in practice justifies the complexity

---

## Implementation plan (ready to code)

**Branch:** `feat/team-aitpm`

**Session to resume:** `227ead9e-b38a-418f-8a90-bc345ac75d7b`  
*(Resume with: `claude --resume 227ead9e-b38a-418f-8a90-bc345ac75d7b` in `/home/rabb1tl0ka/loka/code/claude-aitpm/roadmap`)*

**Confirmed design decision:** `run_team_command` is a single agent with read + write tools. For delete requests the agent classifies and returns `intent: "delete"` + `tool_args` without executing — Python handles the gate.

**V1 note on `private/` enforcement:** `is_private_path()` utility exists in `src/tools.py` and is injected into the agent system prompt. Full tool-layer interception (true `safe_read`/`safe_glob`/`safe_bash`) is a V2 upgrade pending custom tool registration in the SDK.

### Files to create

| File | What |
|---|---|
| `src/tools.py` | `is_private_path(path) -> bool` |

### Files to modify

| File | What changes |
|---|---|
| `src/utils.py` | Add `check_rate_limit()`, `member_to_slug()` |
| `src/state.py` | Add `pending_deletes`, `pending_escalations`, `user_command_counts` defaults in `load_state()` |
| `src/agents.py` | Add `_TEAM_READ_TOOLS`, `_TEAM_WRITE_TOOLS`, `run_team_command()` + sync wrapper. Output: `state/team_command_output.json` → `{response, intent, tool, tool_args, note_content}` |
| `main.py` | Add `_handle_team_inbound()`, `_execute_team_write()`, `_handle_team_note()`. Extend `run_inbound_check()` for team messages. Extend `run_approval_poll()` for `pending_deletes` + `pending_escalations` |
| `configs/example.yaml` | Add `team_access` + `team_members` blocks |
| `configs/cloudsort.yaml` | Add `team_access` (disabled) + `team_members` with placeholder Slack IDs |

---

## Risks

- Classification step could misidentify a delete as a write and execute it immediately — mitigated by prompting the agent to be conservative (when in doubt, classify as delete)
- Rate limit state grows unboundedly if never pruned — prune timestamps older than 1h on every check
- Team members could ask for sensitive info (e.g. billing details, user data) — `run_team_command` prompt should scope responses to project context only
- `private/` dir contents leaked to team — mitigated by `safe_read`/`safe_glob`/`safe_bash` wrappers enforcing path filtering at the tool layer, not just via prompt
