---
status: todo
priority: medium
owner: ""
---

# Idea: TLU Regen — Cancel In-Progress TLU

## One-Line Overview
Allow cancelling an in-progress TLU and regenerating without manually editing state.json, by detecting regen intent and offering a cancel+regen flow.

## Problem

If Bruno asks to regenerate a TLU while one is already in progress (sections pending approval in Slack), the agent blocks with "A TLU is already in progress." The only way to proceed is to manually edit `state.json` to clear `pending_tlu` and remove `tlu_section` drafts from `pending_drafts`.

## Proposed solution

Detect regen intent when a TLU is already in progress and offer a cancel + regen flow:

1. Agent recognises the request as a regen (same `detect_tlu_intent` logic)
2. Since `pending_tlu` exists, instead of blocking, it posts a confirmation: "A TLU is already in progress for week of {week}. Reply 'yes' to cancel it and regenerate."
3. On confirmation: clear `pending_tlu`, remove `tlu_section` drafts from `pending_drafts`, proceed with generation

Alternatively, skip the confirmation and treat a regen request as an implicit cancel — since the user explicitly asked for a fresh report, the intent is unambiguous.

## Notes

- Old TLU section messages in Slack will remain (no way to delete them via MCP), but they'll be orphaned — no state backing them, so approval attempts will be silently ignored or produce a warning
- The local `.md` file will be overwritten by the new generation run
