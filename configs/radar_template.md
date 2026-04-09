# [Your Name] Watching Radar

JQL queries to surface the tickets this AI TPM monitors. The agent uses Step 1 to discover active epics,
then Step 2 to fetch all child tickets under them.

## Step 1 — Get Watched Epics (run to refresh)

Tweak this query to match how your team labels or organises epics. Common approaches:
- Filter by a label (e.g. `labels = MyLabel`)
- Filter by fix version (e.g. `fixVersion = "v3.0"`)
- Filter by assignee instead of watcher

```
project = PROJ AND labels = MyLabel AND watcher = currentUser() AND status not in (Done, Rejected, Parked) AND type in (Epic)
```

Extract the epic keys from the results and plug them into Step 2 below.

## Step 2 — Get Child Tickets (the actual radar)

Replace the epic keys in the list with the ones from Step 1. The agent reads this JQL directly.

```
watcher = currentUser() AND "Epic Link" in (PROJ-1, PROJ-2, PROJ-3) AND statusCategory != Done
```

## Epic Reference (last refreshed: YYYY-MM-DD)

Update this table whenever you refresh Step 2. Useful as a quick human reference — not read by the agent.

| Epic | Summary | Status | Fix Version |
|------|---------|--------|-------------|
| PROJ-1 | Epic title here | In Progress | v1.0 |
| PROJ-2 | Epic title here | Planning | v1.0 |

## Notes

- Watcher is set automatically when you comment on a ticket — no manual tagging needed.
- To refresh: run Step 1, extract epic keys, update the list in Step 2.
- Add `AND updated >= -3d` to Step 2 to narrow to recently active tickets when the list gets noisy.
- Any free-text notes you add here are included in the agent's context — use them for project-specific
  nuance the agent should know about (e.g. "P2 tickets in the Payments epic are time-sensitive").
