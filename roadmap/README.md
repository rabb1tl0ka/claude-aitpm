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

| File | Status | Priority | Owner | One-Line Overview |
|---|---|---|---|---|
| [feat-team-aitpm.md](feat-team-aitpm.md) | ⏳ todo | high | | Expose the AI TPM to the full team via Slack so anyone can query project status, feature context, and sprint state — with write operations held for Bruno's approval. |
| [feat-tlu-generation.md](feat-tlu-generation.md) | ✅ done | high | @rabb1tl0ka | Enable the AI TPM to generate weekly Traffic Light Updates on demand, pulling Jira + meeting notes, posting sections to Slack for approval, then pushing to Notion. |
| [challenge-slack-mcp-unavailable-in-subagents.md](challenge-slack-mcp-unavailable-in-subagents.md) | ⏳ todo | high | | Identify why Slack MCP tools are inaccessible in SDK subagents and find a path to giving them Slack context for higher-quality nudges. |
| [idea-deduplicate-alerts.md](idea-deduplicate-alerts.md) | ⏳ todo | medium | | Prevent duplicate alerts from firing on every fetch run by checking pending_drafts before generating new alerts for the same ticket. |
| [idea-on-demand-digest.md](idea-on-demand-digest.md) | ⏳ todo | medium | | Replace the scheduled 8AM digest with an on-demand `@aitpm digest` command to eliminate unnecessary token burns and deliver the digest when actually needed. |
| [idea-per-config-state.md](idea-per-config-state.md) | ⏳ todo | medium | | Split the shared state.json into per-config files to eliminate cross-project state collisions as AI TPM expands to multiple projects. |
| [idea-reply-to-any-alert.md](idea-reply-to-any-alert.md) | ⏳ todo | medium | | Make every bot-posted Slack message an actionable thread so Bruno can reply with free-form instructions without needing @aitpm syntax. |
| [idea-tlu-regen-cancel.md](idea-tlu-regen-cancel.md) | ⏳ todo | medium | | Allow cancelling an in-progress TLU and regenerating without manually editing state.json, by detecting regen intent and offering a cancel+regen flow. |
| [idea-tlu-slack-context.md](idea-tlu-slack-context.md) | ⏳ todo | medium | | Enrich TLU generation by injecting the past week's Slack channel history alongside Jira state and meeting notes, capturing decisions that never make it into Jira. |
| [challenge-claude-sdk-session-resumption.md](challenge-claude-sdk-session-resumption.md) | ⏳ todo | medium | | Determine whether the Claude Code SDK supports session resumption so TLU revision agents can maintain cross-section consistency after partial approvals. |
| [challenge-orphaned-slack-drafts.md](challenge-orphaned-slack-drafts.md) | ⏳ todo | medium | | Solve Slack draft messages becoming orphaned after state resets, causing silent failures or confusion when Bruno tries to approve them. |
| [idea-per-agent-model-config.md](idea-per-agent-model-config.md) | ⏳ todo | low | | Let users override the Claude model per agent in the project config YAML, eliminating hardcoded model selections in source code. |
| [idea-team-query-cache.md](idea-team-query-cache.md) | ⏳ todo | low | | Cache team query responses by normalized prompt to avoid redundant agent runs when multiple people ask similar questions. |

*(The table above is automatically maintained by Claude Code. Do not edit it manually.)*

## Archived

Implemented or rejected specs live in `archived/`. Move a file there when it's done — no deletion.

| File | Status |
|---|---|
| [feat-generic-aitpm.md](archived/feat-generic-aitpm.md) | Implemented |
| [feat-python-diff-precompute.md](archived/feat-python-diff-precompute.md) | Implemented |
| [feat-python-prefetch-comments.md](archived/feat-python-prefetch-comments.md) | Implemented |

## Templates

| File | Use for |
|---|---|
| [templates/template-feat.md](templates/template-feat.md) | Fully specced features ready to implement |
| [templates/template-idea.md](templates/template-idea.md) | Early-stage ideas to explore |
| [templates/template-challenge.md](templates/template-challenge.md) | Known problems with open solutions |
