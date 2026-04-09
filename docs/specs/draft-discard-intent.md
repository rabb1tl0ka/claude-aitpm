# Draft Discard Intent

**Date:** 2026-03-29
**Status:** Idea — not yet implemented

---

## Problem

When the approval poll posts a draft to #cloudsort_aitpm, Bruno can approve it, edit it, or ask the command agent questions about it. But there's no way to dismiss a draft without sending it. The draft stays in `pending_drafts` indefinitely until the next monitor run overwrites it or it gets approved.

Use case: Bruno replies "we can't close this spike yet — João hasn't created the child tasks" and wants to discard the nudge entirely, not send it, not revise it.

---

## Solution

Add a "discard" intent to `detect_intent()` in `slack_client.py`. When detected, remove the draft from `pending_drafts` and confirm in the thread.

### Trigger phrases (examples)
- "discard", "skip", "ignore this", "cancel", "don't send", "not yet", "hold off"

### Behavior
1. Poll detects reply as `intent == "discard"`
2. Draft removed from `pending_drafts`
3. Bot replies in thread: "Got it, discarded."
4. State saved

### Optional: discard with reason
If Bruno adds context after the discard phrase (e.g. "skip — João hasn't created the child tasks"), store the reason as a note on the ticket in `ticket_states` so the next monitor run has context and doesn't re-nudge immediately.

---

## Implementation Steps

### Step 1 — Add "discard" to `detect_intent()` in `slack_client.py`
- Add discard keywords to the intent classifier
- **Test:** call `detect_intent("skip this")` → returns `"discard"`

### Step 2 — Handle discard in `run_approval_poll()` in `main.py`
- Add `elif intent == "discard":` branch
- Remove draft from pending list, post "Got it, discarded." in thread
- **Test:** reply "skip" to a pending draft → confirm it disappears from `pending_drafts` in state.json

### Step 3 — Optional: store discard reason in ticket_states
- If reply is "skip — <reason>", extract reason and store in `ticket_states[ticket_key]["discard_note"]`
- Monitor uses `discard_note` to avoid re-nudging on the next run
- **Test:** reply "skip — waiting on child tasks" → confirm note in state.json, confirm no nudge on next run for that ticket
