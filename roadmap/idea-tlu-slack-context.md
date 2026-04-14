---
status: todo
priority: medium
owner: ""
---

# Idea: TLU Generation — Slack Channel History as Data Source

## One-Line Overview
Enrich TLU generation by injecting the past week's Slack channel history alongside Jira state and meeting notes, capturing decisions that never make it into Jira.

## Problem

TLU generation currently pulls from Jira state and meeting notes only. Slack is often where the real signal lives — decisions made in `#cloudsort_backend`, blockers flagged in `#cloudsort_chat`, async updates that never make it into Jira tickets or formal notes.

## Proposed solution

Before spawning the TLU generation agent, fetch the last week's message history from the configured project Slack channels (same channels already defined in `slack_channel_ids` in config). Inject the relevant messages into the generation prompt alongside Jira state and meeting notes.

```
## Slack Activity for This Week
### #cloudsort_backend (Apr 6–10)
[messages...]

### #cloudsort_chat (Apr 6–10)
[messages...]
```

## Implementation notes

- Slack MCP is not available in SDK subagents — channel history must be fetched in Python via `get_channel_history()` before the agent is spawned, then passed as text in the prompt (same pattern as meeting notes)
- Filter by date range (week_start to week_end) using message `ts`
- Skip bot messages (`is_bot_message()`) to avoid noise from the AI TPM's own posts
- May need truncation/summarisation if channels are high-volume — raw dumps could blow the context window

## Config

No new config needed — `slack_channel_ids` already maps channel names to IDs.

## Why this matters

Jira reflects what was planned and tracked. Slack reflects what actually happened. The gap between the two is often the most interesting content for a TLU.
