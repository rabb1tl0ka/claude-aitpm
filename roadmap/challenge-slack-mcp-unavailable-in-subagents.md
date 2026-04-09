# Challenge: Slack MCP not available in SDK subagents

## What's the problem

The nudge-drafter agent (and any other SDK subagent spawned via `anthropic.Agents`) cannot access the Slack MCP tools at runtime. When it tries, it gets `No matching deferred tools found`. This means the agent can't read Slack channel history for context when drafting nudges.

Observed in live test (2026-04-09):
```
[nudge-drafter] No Slack tool available (known issue — not accessible here).
No vault files matched. I have enough from JIRA context to draft all 13.
```

The agent recovered gracefully and drafted from Jira data only — but nudge quality is lower than it could be. Slack context (recent team discussions, handoffs, decisions made in thread) would make nudges more specific and relevant.

## Why it matters

- Nudge quality depends on context. A comment like "João handed off to Ryan on Apr 6" came from Jira. A richer nudge could also reference what was said in Slack around that handoff.
- The vault file fallback also failed (no files matched) — so the agent is operating with Jira-only context in subagent mode.
- This affects any future subagent that needs to read Slack (e.g. a digest drafter, a risk summariser).

## Constraints

- Must not: require the user to manually pass Slack data into every agent call
- Must not: break the current working flow (agent degrades gracefully today)
- Must: work within the Claude Agent SDK subagent execution model

## Approaches considered

| Approach | Status | Why ruled out / still open |
|---|---|---|
| Use Slack MCP directly in subagent | Ruled out | MCP tools not forwarded to SDK subagents — confirmed limitation |
| Read Slack in Python before agent runs (like Steps 1+2) | Open | Python already calls Slack API for posting — could extend to reading channel history and passing it as context in the prompt |
| Pass Slack cursors + recent messages as pre-fetched JSON | Open | Same pattern as child tickets — Python fetches, agent receives. Keeps agent stateless. |
| Use main agent (not subagent) for nudge drafting | Open | Would require restructuring the two-phase monitor; loses the Haiku/Sonnet cost split |

## Open questions

1. How much Slack history is actually useful per nudge? Last N messages per channel, or only messages mentioning the ticket key?
2. Would pre-fetching Slack context in Python add meaningful latency to the monitor run?
3. Is the nudge quality gap (Jira-only vs Jira+Slack) significant enough in practice to justify the work? Live test on 2026-04-09 showed solid results without Slack context.
