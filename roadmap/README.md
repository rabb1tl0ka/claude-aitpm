# Roadmap

This directory contains specs, ideas, and challenges for contributors to pick up.

## File prefixes

| Prefix | Meaning |
|---|---|
| `feat-` | Fully specced feature — ready to implement. Branch name and test plan included. |
| `idea-` | Early exploration — interesting direction, not yet fully designed. Good for discussion. |
| `challenge-` | Problem to solve — the what is clear, the how is open. |

## How to contribute

1. Pick a `feat-` file that interests you
2. Read it fully — branch name, implementation steps, test plan, and open questions are all in there
3. Open that branch and implement
4. If you have questions, open an issue referencing the spec file

For `idea-` and `challenge-` files, contributions can be a PR that evolves the file itself (design, research, proposal) before any code is written.

## Current roadmap

| File | Type | Summary |
|---|---|---|
| [feat-team-aitpm.md](feat-team-aitpm.md) | Feature | Expose the bot to the full team on Slack with rate limiting and TPM approval gate |
| [idea-on-demand-digest.md](idea-on-demand-digest.md) | Idea | Replace scheduled 8AM digest with on-demand `@aitpm digest` command |
| [idea-deduplicate-alerts.md](idea-deduplicate-alerts.md) | Idea | Skip re-alerting on tickets already in pending_drafts to reduce Slack noise |
| [idea-reply-to-any-alert.md](idea-reply-to-any-alert.md) | Idea | Turn every bot message into an actionable thread — reply with free-form instructions |
| [idea-team-query-cache.md](idea-team-query-cache.md) | Idea | Cache team @aitpm responses to avoid redundant agent runs |
| [challenge-slack-mcp-unavailable-in-subagents.md](challenge-slack-mcp-unavailable-in-subagents.md) | Challenge | Slack MCP not accessible in SDK subagents — nudges drafted from Jira context only |

## Archived

Implemented or rejected specs live in `archived/`. Move a file there when it's done — no deletion.

| File | Status |
|---|---|
| [feat-generic-aitpm.md](archived/feat-generic-aitpm.md) | Implemented |
| [feat-python-diff-precompute.md](archived/feat-python-diff-precompute.md) | Implemented |

## Templates

| File | Use for |
|---|---|
| [template-feat.md](template-feat.md) | Fully specced features ready to implement |
| [template-idea.md](template-idea.md) | Early-stage ideas to explore |
| [template-challenge.md](template-challenge.md) | Known problems with open solutions |
