# Feature Spec: Pre-compute Diff in Python

## Branch

Implement in a new branch off `main`: `feat/python-diff-precompute`

## Goal

On incremental monitor runs, Python computes the diff between fresh ticket data and known ticket states before the agent runs. Instead of passing all tickets + all known states and asking the LLM to figure out what changed, the agent receives a pre-classified diff and formats the output.

## Expected advantages / benefits

- ~2,000-3,000 tokens saved per incremental run (varies by how many tickets are actionable)
- On quiet runs (nothing changed), agent receives near-zero ticket data and can immediately output an empty `posts` array
- Agent output becomes more deterministic — less sensitive to LLM reasoning variance
- Faster runs due to reduced context size

## Downsides / risks

- Removes agent's ability to apply nuanced judgment (e.g. deciding a borderline status change isn't worth surfacing)
- More Python logic to maintain — classification bugs in Python silently affect agent output
- Digest runs still need full ticket list for scope_summary — adds complexity handling both modes

---

## Context

### Current flow (incremental run)
1. Python fetches fresh tickets via Jira REST API (Step 2) — e.g. 10 updated tickets
2. Agent receives:
   - ALL 35 child tickets (fresh fetch, ~3,247 tokens)
   - ALL 52 known ticket states, slimmed to `{status, last_updated}` (~1,180 tokens after current optimisation)
3. Agent reasons through what changed, what's stale, what's blocked, etc.
4. Agent produces `posts`, `pending_nudges`, `ticket_states` in output JSON

### Proposed flow (incremental run)
1. Python fetches fresh tickets (same as now)
2. **Python computes the diff** — classifies tickets into actionable buckets
3. Agent receives only the pre-classified diff (~200-500 tokens on a quiet run)
4. Agent formats output — less reasoning, more formatting

### Files involved
- `src/state.py` — add `compute_diff()` function
- `src/agents.py` — update `run_monitor()` to pass diff instead of raw tickets + known states on incremental runs
- `main.py` — pass `known_ticket_states` into `run_monitor` (already in `state`, just needs threading through)
- `tests/test_preflight.py` — add diff validation step

---

## Design Decision: Two Options (unresolved — ask Bruno before implementing)

### Option A: Pre-filtered ticket list
Python filters the fresh tickets to only "interesting" ones and passes a smaller list. Agent still does the analysis but on a reduced set.

- Pro: minimal change to agent logic and prompt structure
- Con: agent still re-reasons about why each ticket is interesting; token savings are partial

### Option B: Pre-classified diff (recommended)
Python computes structured buckets and passes them directly. Agent role shifts from **analyzer** to **formatter**.

- Pro: maximum token savings; agent output is near-deterministic; faster runs
- Con: removes agent's ability to apply nuanced judgment (e.g. deciding a status change isn't worth surfacing); more Python logic to maintain

**Bruno's position (from conversation):** Leaning toward Option B but wants to think about the tradeoff — specifically whether losing agent judgment is acceptable. Resolve this before starting implementation.

---

## Option B: Detailed Design

### Python diff function — `compute_diff(fresh_tickets, known_states, last_run, staleness_thresholds, active_features)`

Located in `src/state.py`. Returns a dict with one key per active feature:

```python
{
    "status_changes": [
        {
            "key": "CLOUD-123",
            "summary": "WEB: implement search bar",
            "assignee": "Zoran Grbusic",
            "from_status": "In Progress",
            "to_status": "In Review"
        }
    ],
    "new_comments": [
        {
            "key": "CLOUD-456",
            "summary": "BE SPIKE: payment methods",
            "assignee": "luis.carvalho",
            "updated": "2026-04-09T10:00:00Z"
        }
    ],
    "stale_tickets": [
        {
            "key": "CLOUD-789",
            "summary": "WEB: List payment methods",
            "assignee": null,
            "priority": "P2",
            "business_days_stale": 5,
            "sprint_state": "active"
        }
    ],
    "planning_gaps": [
        {
            "key": "CLOUD-012",
            "summary": "WEB: change DNS",
            "assignee": "Zoran Grbusic"
        }
    ],
    "unblocked": [
        {
            "key": "CLOUD-345",
            "summary": "WEB: edit page",
            "assignee": "Gorjan Ivanovski",
            "blocker_resolved": "CLOUD-999"
        }
    ]
}
```

Only keys for active features are included (check `active_features` dict, same as `monitor_features` from config).

### Classification logic per bucket

**`status_changes`** (feature: `status_changes`):
```
for ticket in fresh_tickets:
    known = known_states.get(ticket["key"])
    if known and ticket["status"] != known["status"]:
        → add to status_changes with from/to
```

**`new_comments`** (feature: `comment_activity`):
```
for ticket in fresh_tickets:
    known = known_states.get(ticket["key"])
    if known and ticket["updated"] > known["last_updated"] and ticket["status"] == known["status"]:
        → add to new_comments
```
Note: the agent still needs to call `mcp__cloudsort-jira__getJiraIssue` to fetch the actual comment text. Python can only detect that a comment likely happened — it can't read the comment content without an extra API call. Pass the ticket key and the agent handles the fetch.

**`stale_tickets`** (feature: `staleness`):
```
for ticket in fresh_tickets:
    threshold = staleness_thresholds.get(ticket["priority"])
    if threshold and ticket["business_days_stale"] > threshold and ticket["sprint_state"] == "active":
        → add to stale_tickets
```

**`planning_gaps`** (feature: `planning_gaps`):
```
for ticket in fresh_tickets:
    if ticket["sprint_state"] == "none":
        → add to planning_gaps
```

**`unblocked`** (feature: `dependency_chains`):
```
for ticket in fresh_tickets:
    known = known_states.get(ticket["key"])
    if not known: continue
    for blocker_key in ticket["blockers"]:
        blocker_known = known_states.get(blocker_key)
        blocker_fresh = fresh_ticket_map.get(blocker_key)
        blocker_status = (blocker_fresh or blocker_known or {}).get("status")
        blocker_was_done = (blocker_known or {}).get("status") == "Done"
        if blocker_status == "Done" and not blocker_was_done:
            → add to unblocked
```

### Digest exception

When `run_type == "digest"` (`is_digest == True`), the `scope_summary` feature requires ALL tickets for the full snapshot. In this case:
- Skip the pre-compute diff entirely for scope_summary
- Pass the full ticket list to the agent as today
- Other features (status_changes, staleness, etc.) can still use the diff

Simplest approach: on digest runs, pass both the diff AND the full ticket list. The agent uses the diff for per-feature sections and the full list for the summary.

### Agent prompt changes

Replace the current Step 3 instructions for each active feature with diff-aware versions:

**Before (current):**
```
### Status changes
Compare each ticket's current status to Known Ticket States from last run.
Report ALL status changes...
```

**After:**
```
### Status changes
Python has pre-computed these. Report each one:
{diff["status_changes"] as JSON}
```

Remove "Known Ticket States" from the prompt context entirely on incremental runs — the diff replaces it.

### Output schema — no change

The agent still outputs the same `ticket_states` structure in the JSON file. Python still does the merge. This is unchanged.

---

## Changes Required

| File | Change |
|---|---|
| `src/state.py` | Add `compute_diff(fresh_tickets, known_states, last_run, staleness_thresholds, active_features) -> dict` |
| `src/agents.py` | On incremental runs: pass `diff` instead of full tickets + known states; update Step 3 prompt blocks to use diff buckets; keep full ticket list for digest scope_summary |
| `main.py` | Call `compute_diff()` after `fetch_child_tickets()`; pass result to `run_monitor_sync()` |
| `tests/test_preflight.py` | Add step 3: run `compute_diff()` on the fetched tickets + current state, print bucket sizes |

---

## Test Plan

1. **Unit test `compute_diff()`** with synthetic data:
   - Ticket with changed status → appears in `status_changes`
   - Ticket with newer `updated` but same status → appears in `new_comments`
   - Ticket exceeding staleness threshold with `sprint_state == "active"` → appears in `stale_tickets`
   - Ticket with `sprint_state == "none"` → appears in `planning_gaps`
   - Ticket whose blocker just became Done → appears in `unblocked`
   - Ticket with no changes → appears in NO bucket

2. **Preflight test** (`tests/test_preflight.py --diff`):
   - Loads current state + fetches fresh tickets
   - Runs `compute_diff()`
   - Prints each bucket with counts
   - Verifies no ticket appears in multiple buckets (status change + new comment = ambiguous, should prefer status_changes)

3. **Token comparison**: add `--measure-tokens` flag to preflight that prints old prompt size vs new prompt size

---

## Open Questions

1. **Option A vs Option B** — confirm with Bruno before starting
2. **Ambiguous tickets**: a ticket can have both a status change AND a new comment (both `status` changed and `updated` is newer). Which bucket wins? Suggested: `status_changes` takes priority, skip `new_comments` for that ticket.
3. **New tickets** (not in `known_states`): first time we've seen them. They have no diff baseline. Suggested: add a `new_tickets` bucket, or include them in `status_changes` with `from_status: null`.
   **Confirmed real case (2026-04-09):** CLOUD-6561 (child of CLOUD-6300, watched by Bruno) was fetched in a full fetch run but never surfaced — it had no entry in Known Ticket States so the agent's diff found nothing to compare against. Ticket was already "In Review" when first seen. This is a bug on full fetch runs: new tickets with non-trivial status (anything other than "To Do") should be surfaced as "first seen" entries, not silently skipped. Also note: CLOUD-6561 was saved to ticket_states with `assignee: None`, `priority: None`, `summary: None` — field extraction also failed for this ticket, worth investigating separately.
   **Full fetch vs incremental distinction:** on incremental, skipping new tickets is acceptable (they'll appear next full fetch). On full fetch, new tickets with status != "To Do" must surface.
4. **Deleted/done tickets**: tickets that were in `known_states` but not in the fresh fetch (moved to Done and filtered out by JQL). These disappear silently. Worth a `completed` bucket for the digest summary?
