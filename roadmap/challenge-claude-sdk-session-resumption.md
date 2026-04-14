---
status: todo
priority: medium
owner: ""
---

# Challenge: Claude Code SDK Session Resumption

## One-Line Overview
Determine whether the Claude Code SDK supports session resumption so TLU revision agents can maintain cross-section consistency after partial approvals.

## Context

TLU sections are posted as 3 independent Slack messages, each approved separately. When Bruno replies to one section (e.g., Risks) to request a revision, the agent spawns fresh with no memory of the other sections or the original generation run. This means:

- Cross-section consistency isn't guaranteed after revisions
- The agent can't reason about "why I wrote Where We Are the way I did" when revising Risks
- Each revision is stateless beyond what's stored in `state.json`

## The question

Does the Claude Code SDK's `query()` support resuming a previous session by ID?

The Claude Code CLI supports `--resume <session-id>`. If the SDK exposes equivalent functionality via `ClaudeAgentOptions`, the architecture becomes:

1. Store the session ID returned from the TLU generation run in `state["pending_tlu"]`
2. When Bruno replies to any TLU section thread, resume that session instead of spawning fresh
3. The agent has full conversational memory: what it generated, why, what Jira data it saw

## What to investigate

- Does `ClaudeAgentOptions` or `query()` accept a `session_id` / `resume` parameter?
- If yes: what's the session lifetime? Is it bounded by cost/turns?
- If yes: does the resumed session retain MCP tool access from the original run?
- If no: is there a workaround (e.g., serialising and replaying the message history)?

## Why this matters beyond TLU

Session resumption would be broadly useful anywhere the AI TPM needs to reason across multiple user interactions on the same artifact — not just TLU sections.
