# Incremental Fetch & Caching

**Date:** 2026-03-29
**Branch:** feat/smart-nudge-drafter
**Status:** Implemented — pending end-to-end test

---

## Problem

Every monitor run fetches all 51+ child tickets from JIRA regardless of what changed. This is:
- **Wasteful** — most tickets haven't changed since the last run
- **Token-expensive** — 51 tickets × analysis = large agent context every time
- **Rate-limit prone** — hitting Claude's token limits mid-run (observed in testing)

The monitor already stores `last_monitor_run` in state.json. We're not using it for anything other than logging.

---

## Solution: Epic Key Cache + Incremental JQL

### One cache level: epic keys only

Cache the list of watched epic keys. Epics rarely change — only when a new feature is kicked off or the radar file is updated. No need to cache ticket IDs separately.

**Why ticket ID caching is unnecessary:**
When a ticket is created or added to a watched epic, its `updated` timestamp is set to now. The incremental JQL `updated >= last_run` will surface it automatically on the next run. New tickets are self-announcing.

### Incremental JQL for hourly runs

Instead of:
```
"Epic Link" in (epic_keys)  →  all 51 tickets every time
```

Use:
```
"Epic Link" in (epic_keys) AND updated >= "last_run_timestamp"  →  only changed tickets
```

Merge the small batch of changed tickets with the full `ticket_states` in state.json to reconstruct the complete picture — without fetching unchanged tickets.

### Full fetch preserved for the 8AM digest

The 8AM digest already does a complete fetch. This becomes the daily state.json rebuild — no new mechanism needed. It's the natural "refresh cache" that happens every morning.

---

## Architecture

### Cache file: `state/epic_cache.json`

```json
{
  "epic_keys": ["CLOUD-6255", "CLOUD-6288", "CLOUD-6297", "..."],
  "cached_at": "2026-03-29T17:00:00Z"
}
```

Simple. No TTL in the file — the `--refresh-cache` flag and the 8AM digest handle invalidation.

### Per-run logic

```
1. Load epic_cache.json
   → if missing or --refresh-cache: run Step 1 (fetch epics), save cache
   → else: use cached epic keys

2. Determine fetch mode
   → if last_monitor_run is None OR run_type == "digest": full fetch (all tickets)
   → else: incremental fetch (updated >= last_monitor_run only)

3. Fetch tickets
   → full: "Epic Link" in (epic_keys)  — same as today
   → incremental: "Epic Link" in (epic_keys) AND updated >= "YYYY-MM-DDTHH:MM:SS"

4. Merge (incremental only)
   → start with ticket_states from state.json as base
   → overwrite with freshly fetched tickets (they have latest data)
   → result: complete picture with minimal API calls

5. Continue with analysis as normal
```

### Edge cases handled

| Scenario | How it's handled |
|---|---|
| New ticket added to watched epic | `updated >= last_run` surfaces it automatically |
| Ticket moved OUT of a watched epic | Stays in ticket_states until next digest full refresh |
| New epic added to radar | Detected on next run if `--refresh-cache` passed, or at 8AM digest |
| Monitor was down for hours | Incremental still works — catches everything updated since last run |
| Cold start (no state.json) | `last_monitor_run` is None → falls back to full fetch |
| `--refresh-cache` flag | Forces Step 1 re-fetch + full ticket fetch |

---

## `--refresh-cache` flag

Added to `main.py` CLI args. Triggers:
1. Re-fetch Step 1 (epics) → overwrite `epic_cache.json`
2. Full ticket fetch (ignores `last_monitor_run`)
3. Rebuilds `state.json` ticket_states completely

Use when:
- You add a new epic to the radar file
- You want to force a clean slate

```bash
python3 main.py --once monitor --refresh-cache
```

---

## Expected token savings

| Run type | Tickets fetched | Relative cost |
|---|---|---|
| Current (always full) | 51 every run | baseline |
| Incremental (hourly) | ~5 on a quiet hour, ~15 on an active day | ~10-30% of baseline |
| Full (8AM digest or --refresh-cache) | 51 | same as baseline |

On a typical workday with 8 hourly runs: 1 full (8AM) + 7 incremental. If average 10 changed tickets per incremental run: `(1×51) + (7×10) = 121` total tickets fetched vs `8×51 = 408`. **~70% reduction.**

---

## Implementation Steps (with incremental tests)

### Step 1 — Add `--refresh-cache` CLI flag to `main.py`
- Add `--refresh-cache` arg to argparse
- Pass it through to the monitor runner
- **Test:** `python3 main.py --help` → confirm flag appears

### Step 2 — Add epic cache read/write to `src/state.py`
- `load_epic_cache(project_dir)` → returns list of epic keys or None
- `save_epic_cache(project_dir, epic_keys)` → writes `state/epic_cache.json`
- **Test:** call both functions manually in a Python shell, confirm file is written and read back correctly

### Step 3 — Update Step 1 in monitor prompt
- If cache exists and `--refresh-cache` not set: skip Bash fetch, use cached keys directly
- If cache missing or `--refresh-cache`: run Bash fetch, save result to cache
- **Test:** run monitor once to populate cache → check `state/epic_cache.json` exists → run again → confirm Step 1 Bash call is skipped in logs

### Step 4 — Add incremental JQL to Step 2 in monitor prompt
- Pass `last_monitor_run` and `is_full_fetch` into the prompt
- Agent uses incremental JQL when `is_full_fetch=False`
- Agent uses full JQL when `is_full_fetch=True` (digest, cold start, --refresh-cache)
- **Test:** run monitor twice in a row → second run should show far fewer tickets in Step 2 output (only those updated in the last ~2 mins)

### Step 5 — Add merge logic to monitor prompt
- After incremental fetch, agent merges new data into the Known Ticket States from state.json
- Unchanged tickets use their last-known state
- **Test:** confirm monitor_output.json `ticket_states` contains all tracked tickets (not just the incremental batch)

### Step 6 — End-to-end test
- Run `python3 main.py --once monitor` → confirm incremental path used
- Run `python3 main.py --once digest` → confirm full fetch used
- Run `python3 main.py --once monitor --refresh-cache` → confirm epic cache rebuilt + full fetch
- Check token cost vs previous runs

---

## What stays the same

- 8AM digest: always full fetch, no change to existing behavior
- `ticket_states` in state.json: still written after every run (full or incremental)
- Slack cursors, user_map, pending_drafts: unaffected
- The agent's analysis logic: no change — it always sees a complete ticket picture
