# Challenge: Orphaned Slack Draft Messages

## Problem

When state is reset (e.g., TLU regen, manual state fix, monitor restart), pending draft messages already posted to Slack become orphaned — they exist in Slack but have no backing state. If Bruno reacts or replies to them, the approval poll either ignores them silently or produces a confusing error.

This affects all draft types: nudges, alerts, TLU sections. Any state reset creates orphans.

## Why it's hard

- The Slack MCP has no delete message capability — orphaned messages can't be cleaned up
- Even if delete were available, the bot only knows a message's `ts` at post time — if state is lost, the `ts` is gone too
- Storing `ts` in state helps recovery but doesn't solve deletion

## Potential directions

1. **Graceful degradation** — when the poll encounters a reply/reaction on a draft whose state is gone, post a thread reply: "This draft is no longer active. Request a new one if needed." Prevents silent confusion.

2. **Draft tombstoning** — instead of removing drafts from state on reset, mark them `"status": "cancelled"` and keep the `slack_ts`. The poll can then post a cancellation notice in the thread and skip further processing.

3. **Message editing** — if the Slack MCP ever gains edit-message support, cancelled drafts could be edited in-place to show a ~~strikethrough~~ or "CANCELLED" prefix.

4. **Expiry** — drafts older than N days are auto-expired by the poll, with an optional thread notice.

## Notes

- Option 2 (tombstoning) is the most robust and works within current constraints — no delete needed, state stays consistent, Bruno gets feedback in thread
- The challenge is ensuring all reset paths (manual, regen, monitor restart) go through a tombstone routine rather than hard-deleting from `pending_drafts`
