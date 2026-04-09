# Feature Spec: Pre-fetch Ticket Comments in Python

## Branch

`feat/python-prefetch-comments`

## Goal

Move two `getJiraIssue` calls that currently happen inside agent prompts into deterministic Python pre-steps, so the agent receives comment data already resolved rather than having to make tool calls at runtime.

## Affected flows

1. **`run_monitor` — `comment_activity` feature**: agent currently calls `getJiraIssue` with `comment` for tickets updated since last run with no status change.
2. **`run_nudge_drafter` — Step 1**: agent currently calls `getJiraIssue` with `comment,parent,customfield_10014` for each stale ticket.

## Expected advantages / benefits

- Removes non-deterministic agent tool calls — comment fetch is now guaranteed and consistent
- Minor token savings on tool call overhead (the data itself still goes into the prompt)
- Real gains in latency and reliability: Python REST calls are fast and don't consume agent turns
- Fewer max_turns needed in nudge-drafter (Step 1 eliminated)

## Downsides / risks

- More Python logic to maintain
- `fetch_ticket_details` makes one REST call per ticket key — could be slow if many tickets (unlikely in practice)
- Error in Python fetch silently omits a ticket's context rather than letting the agent retry

---

## Implementation

### New function: `state.fetch_ticket_details`

```python
def fetch_ticket_details(ticket_keys: list, fields: list = ["comment", "parent", "customfield_10014"]) -> dict
```

- One REST call per key: `GET /rest/api/3/issue/{key}?fields=...`
- Returns `{key: {latest_comment, full_comments, parent_key}}`
- On HTTP error: logs the error, skips the key (does not raise)

### `run_monitor` change

Before building the prompt (when `comment_activity` is enabled):

1. Filter `child_tickets` in Python: keys where `updated > last_run` (parsed as datetime) AND status matches previous `ticket_states` entry
2. Call `fetch_ticket_details(comment_activity_keys, fields=["comment"])`
3. Inject pre-resolved comment data into the `comment_activity` prompt section
4. Remove the `getJiraIssue` instruction from that section

### `run_nudge_drafter` change

At the top of the function, before building the prompt:

1. Call `fetch_ticket_details([t["key"] for t in pending_nudges])`
2. Replace Step 1 in the prompt with a pre-resolved block
3. Remove the `getJiraIssue` call instruction

---

## Decisions

- Parse `updated` field to `datetime` for comparison (not string comparison)
- `fetch_ticket_details` logs errors and skips failed keys rather than raising
