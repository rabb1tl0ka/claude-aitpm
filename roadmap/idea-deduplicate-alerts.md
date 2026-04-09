# Idea: Deduplicate alerts against pending_drafts

## What's the idea

Before the agent runs, Python checks `pending_drafts` for any alerts/drafts that are already pending for a given ticket. If one exists, skip generating a new alert for that ticket in this run. This prevents the same staleness or unassigned alert from firing repeatedly on every full fetch.

Observed problem (2026-04-09): 8 unassigned staleness alerts re-fired on a full fetch even though identical alerts had been posted in Run 1 earlier the same day.

## Expected advantages / benefits

- Reduces noise in `#cloudsort_aitpm` — same alert won't appear multiple times
- Preserves signal quality — if the channel fills with duplicates, Bruno starts ignoring it
- Zero token cost — deduplication is Python reading state.json before the agent runs
- Could be passed to the agent as a "skip list": "do not re-alert on these tickets — already pending"

## Downsides / risks

- If Bruno dismisses/ignores a pending draft without acting on it, the ticket would never re-alert until the draft is cleared
- Need to define "same alert" — by ticket key? by ticket key + alert type?
- Pending drafts accumulate if Bruno doesn't act — skip list grows stale over time

## What's been tried already

Nothing yet. `pending_drafts` already tracks status (`pending`, `sent`) and `ticket_key` per entry — the data needed for deduplication is already in state.json.

## Open questions

1. Should deduplication be by `ticket_key` only, or by `ticket_key + alert type` (e.g. staleness vs unassigned vs planning gap)?
2. What's the TTL on a pending alert? If a draft has been pending for 3 days with no action, should it re-fire?
3. Should "sent" drafts also suppress re-alerts, or only "pending" ones?
