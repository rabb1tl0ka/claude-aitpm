# Feature Spec: Team AI TPM

## Branch

`feat/team-aitpm`

## Goal

Expose the AI TPM to the full team via Slack. Team members can query project status, feature context, sprint state, and blockers by mentioning `@aitpm` in `#cloudsort_aitpm`. Write operations (Jira comments, transitions) are held for Bruno's approval before execution.

## Target users

Frontend devs, backend devs, designers — following 2-week agile sprints with daily scrums, sprint planning, retros, and kickoffs.

---

## Use cases

### Daily queries (high frequency)
- "What's the status of CLOUD-XXXX?"
- "What's blocking me right now?"
- "Is the design for [feature] ready?"
- "What should I be working on this sprint?"
- "Who's working on X?"

### Write requests (gated through Bruno)
- "Move CLOUD-XXXX to In Review"
- "Add a comment to CLOUD-XXXX saying I'm blocked on the API"
- "Flag CLOUD-XXXX as blocked by CLOUD-YYYY"

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

### Write gating
Write requests are never executed directly by a team member. The bot holds the request, posts to `#cloudsort_aitpm`:

> *"@Zoran wants to move CLOUD-6329 to In Review. Approve? Edit? Reject?"*

Bruno replies in thread — same approval flow as existing pending_drafts.

### Rate limiting
Max N commands per user per hour (configurable). Tracked in state. On limit hit, bot replies in thread: "You've hit the limit for now — try again in X minutes."

### Read vs. write classification
Before executing any team command, a lightweight classify step determines if it's a read query or a write request. Read → execute immediately with read-only tools. Write → hold for approval.

### Persona
Team-facing responses drop the first-person PM framing used in nudge comments. The bot responds as the AI TPM assistant, not as Bruno.

---

## Implementation

### Config additions (`config.yaml`)

```yaml
team_access:
  enabled: false                    # feature flag — off by default
  allowed_slack_user_ids: []        # empty = owner only; ["*"] = all workspace members
  max_commands_per_user_per_hour: 5
```

### State additions (`state.json`)

```json
{
  "user_command_counts": {
    "<slack_user_id>": ["<iso_ts>", "<iso_ts>"]   // rolling list of command timestamps
  },
  "pending_team_requests": [
    {
      "id": "<uuid>",
      "requester_id": "<slack_user_id>",
      "requester_name": "<display_name>",
      "command_text": "...",
      "classified_as": "write",
      "slack_ts": "<ts of approval post in #cloudsort_aitpm>",
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

### New: `run_team_command` in `src/agents.py`

```python
async def run_team_command(cfg: dict, state: dict, command_text: str, requester: dict) -> dict | None:
```

- Uses a read-only tool set: `searchJiraIssuesUsingJql`, `getJiraIssue`, `Read`, `Glob`, `Bash`
- Prompt includes requester context and explicitly forbids write operations
- Returns `{response: str, requires_write: bool, write_description: str | None}`

### Changes to `run_inbound_check` in `main.py`

1. Check `team_access.enabled` — if off, owner-only behaviour unchanged
2. Check if user is in `allowed_slack_user_ids` (or `"*"`)
3. Call rate limiter — reject with message if exceeded
4. Classify intent: read or write?
   - Read → `run_team_command` → reply in thread
   - Write → post approval request to `#cloudsort_aitpm` → add to `pending_team_requests`

### Changes to `run_approval_poll` in `main.py`

- Also poll `pending_team_requests`
- On Bruno's reply: approve → execute write → notify requester in their original thread; reject → notify requester

---

## Tool sets

### `_TEAM_READ_TOOLS`
```python
[
    "mcp__cloudsort-jira__searchJiraIssuesUsingJql",
    "mcp__cloudsort-jira__getJiraIssue",
    "Read",
    "Glob",
    "Bash",
]
```

No write tools. No Slack tools (team member already has Slack).

---

## Not in V1

- Query response cache (see `idea-team-query-cache.md`) — add once query volume justifies it
- Multi-project support — team commands scoped to the same project config as the owner
- Per-user permission levels (some users can write, others read-only) — everyone is read-only for now
- Listening in channels other than `#cloudsort_aitpm`

---

## Risks

- Classification step could misidentify a write request as read — mitigated by prompting the agent to be conservative (when in doubt, classify as write)
- Rate limit state grows unboundedly if never pruned — prune timestamps older than 1h on every check
- Team members could ask for sensitive info (e.g. billing details, user data) — `run_team_command` prompt should scope responses to project/sprint context only
