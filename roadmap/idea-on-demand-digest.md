# Idea: On-demand digest instead of scheduled 8AM run

## What's the idea

Replace the scheduled 8AM digest with an on-demand command: `@aitpm digest`. Bruno triggers it when he wants a full picture — before a sprint review, on Monday morning, after a holiday — rather than burning tokens every day at 8am regardless of need.

## Expected advantages / benefits

- Eliminates the most token-heavy run of the day when it's not needed
- Digest is more useful when Bruno actually wants it vs. arriving unsolicited every morning
- Reduces noise — daily summaries on quiet days have low signal
- If `scope_summary` feature flag is already `false`, the scheduled digest is identical to a monitor run — the schedule becomes pointless
- Simplifies the scheduler in `main.py` (one less time-based condition)

## Downsides / risks

- Loses the "passive morning briefing" — Bruno has to remember to ask for it
- The 8AM digest also triggers a full fetch (cache refresh) which catches any drift between incremental state and Jira reality. On-demand would need to replicate this or schedule the full fetch separately.

## What's been tried already

Nothing yet. Currently the digest is hardcoded to fire at 8AM in `main.py`:
```python
if now.hour == 8 and last_digest_date != now.date():
    run_monitor(cfg, state, run_type="digest", log=log)
```
The `run_command` agent already exists and handles `@aitpm` commands — digest could be routed through it or as a dedicated `run_type="digest"` trigger from there.

## Open questions

1. Should the on-demand digest still do a full fetch (cache refresh), or use the current incremental state?
2. Should the scheduled 8AM slot be repurposed as a silent full fetch / cache refresh (no LLM, just Python syncing state) instead of being dropped entirely?
3. Is there value in keeping a weekly scheduled digest (e.g. Monday 8AM) even if the daily one is dropped?
