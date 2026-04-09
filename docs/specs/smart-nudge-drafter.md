# Smart Nudge Drafter

**Date:** 2026-03-29
**Branch:** feat/smart-nudge-drafter
**Status:** Ready to implement

---

## Problem

Current staleness nudges are robotic and context-free:

> "Hey @Daniela Ilieva - no updates here in 4 days. What's the current status?"

Issues:
1. **Calendar days, not business days** — a ticket updated on Friday flagged as "2 days stale" on Sunday
2. **No feature context** — the agent knows the ticket but not what it's building or why it matters
3. **Ignores Slack** — team discussions happening in channels are invisible to the monitor
4. **Generic tone** — sounds like a dumb PM pinging "is it done yet?"

---

## Goals

Nudges should be:
- **Specific** — reference the actual work, not just the ticket key
- **Curious, not demanding** — ask about something concrete, not "what's the status?"
- **Context-aware** — informed by the feature goals, comment history, and recent Slack discussions
- **Business-day aware** — weekends don't count

---

## Data Sources Available

### 1. Ticket comment history
Already fetched via `mcp__cloudsort-jira__getJiraIssue` with `comment` field.
Tells us: what was last discussed, any blockers mentioned, last activity.

### 2. Epic description (JIRA)
Always fetched via `mcp__cloudsort-jira__getJiraIssue` on the parent epic.
Tells us: what the feature is trying to achieve — the "why" behind the ticket.
This is the baseline context source, available for every ticket.

### 3. Feature vault notes
Path: configured via `features_vault_path` in `configs/cloudsort.yaml`.
Default: `~/loka/vaults/loka2026/projects/cloudsort/jb/features/`
Format: structured .md files with JIRA epic key, feature description, stage progress, dependencies, blockers.
**Lookup:** each note contains the JIRA epic key — grep, not fuzzy matching:

```bash
grep -rl "CLOUD-6329" ~/loka/vaults/loka2026/projects/cloudsort/jb/features/
```

Not all epics have a note. When no vault note exists, fall back to the epic description from JIRA.

**Context priority:** vault note (richest) → JIRA epic description (always available) → ticket summary only

### 4. Slack channel messages
Channels in config: `#cloudsort_chat`, `#cloudsort_backend`, `#cloudsort_webapp`, `#cloudsort_design`.
Tells us: team discussions, blockers called out, decisions made, context not captured in JIRA.

**Workspace:** claude.ai Slack MCP reads from Loka's Slack workspace directly via Bruno's OAuth — confirmed working, no bot setup needed.

Read once per monitor run (not per ticket) using a cursor to avoid re-reading backlog.

---

## Architecture

### Business day calculation (Python)
Simple utility, not delegated to the agent:

```python
from datetime import date, timedelta

def business_days_since(dt_str: str) -> int:
    updated = datetime.fromisoformat(dt_str).date()
    today = date.today()
    days = 0
    current = updated
    while current < today:
        if current.weekday() < 5:  # Mon=0, Fri=4
            days += 1
        current += timedelta(days=1)
    return days
```

Injected into the monitor's known ticket states as `"business_days_stale": N`.
The agent uses this number directly — no date math in the prompt.

### Slack cursor tracking
State stored in `state/state.json`:

```json
{
  "slack_cursors": {
    "C049U0HNZQA": "1743000000.000000",
    "C014K67V7HB": "1743000000.000000",
    "CTFQHDVML":   "1743000000.000000",
    "C016JD80V08": "1743000000.000000"
  }
}
```

Cursor is the Slack message timestamp of the last message read (Unix float string, as returned by the API).
First run: read last 14 days (`oldest = now - 14 days` as Unix timestamp).
Subsequent runs: read since last cursor.
Read once at the start of the monitor run, passed as context to Phase 2.

### Two-phase monitor

**Phase 1 — Haiku (detection)**
- Fetch epics + tickets via REST API (unchanged)
- Detect status changes, new activity, planning gaps, dependencies
- Identify stale tickets using `business_days_stale` (pre-calculated by Python, not by the agent)
- Write `monitor_output.json` — stale tickets flagged with `"nudge_text": null` as placeholder

**Phase 2 — Sonnet 4.6 (nudge drafting)**
Only spawned when stale tickets exist in Phase 1 output.
For each stale ticket:
1. Fetch epic description from JIRA (`getJiraIssue` on epic key)
2. Grep `features_vault_path` for epic key → read vault note if found (richer than epic description)
3. Read ticket comment history
4. Pull relevant Slack messages from the batch fetched at run start
5. Draft a contextual, specific, non-robotic nudge
6. Write final drafts back to `monitor_output.json`

### Config changes (`configs/cloudsort.yaml`)

```yaml
features_vault_path: ~/loka/vaults/loka2026/projects/cloudsort/jb/features

slack_channels:
  general:
    name: "#cloudsort_chat"
    id: C049U0HNZQA
  backend:
    name: "#cloudsort_backend"
    id: C014K67V7HB
  webapp:
    name: "#cloudsort_webapp"
    id: CTFQHDVML
  design:
    name: "#cloudsort_design"
    id: C016JD80V08
```

Note: `slack_channels` structure changes from `name: "#channel"` to `name + id` per channel.
Code that reads channel names needs a small update.

---

## Nudge quality guidelines (for Sonnet prompt)

Bad:
> "Hey @Daniela - no updates here in 4 days. What's the current status?"

Good (vault note available):
> "Hey @Daniela - last note on this was about waiting on the design mockups for the Edit Network payment flow. Any movement there? Trying to figure out if we're still on track for the sprint."

Good (comment history only):
> "Hey @Daniela - saw your note from Tuesday about the API contract being unclear. Did that get resolved with the backend team?"

Good (epic description only, no prior comments):
> "Hey @Daniela - CLOUD-6417 has been quiet for 3 business days. Anything blocking you on the payment flow work, or is it moving along?"

Rules:
- No "What's the current status?" as the only question — too generic
- Reference something specific: last comment, feature goal, known dependency
- Neutral tone — not assuming there's a problem
- If blocked by another ticket: acknowledge the blocker explicitly
- If unassigned: do NOT draft a nudge — alert instead (already handled upstream)
- No comma after @mention (existing rule)
- Use business days in the message, not calendar days

---

## Implementation Steps

1. **Add `business_days_since()` to `src/utils.py` (new file)**
   - Called in `run_monitor()` before building prompt
   - Injects `business_days_stale` per ticket into the context passed to the agent

2. **Update `configs/cloudsort.yaml`**
   - Add `features_vault_path`
   - Update `slack_channels` to include `id` per channel

3. **Update `src/state.py`**
   - Add `slack_cursors` dict to state schema
   - Helper: `get_slack_oldest(state, channel_id)` → Unix timestamp (14 days back if no cursor)
   - Helper: `update_slack_cursor(state, channel_id, ts)`

4. **Update Phase 1 monitor prompt (Haiku)**
   - Remove staleness day calculation — use `business_days_stale` from injected context
   - Flag stale tickets with `"nudge_text": null` in output (Phase 2 fills it in)
   - Remove nudge drafting from this phase entirely

5. **New `run_nudge_drafter()` in `src/agents.py` (Sonnet 4.6)**
   - Tools: `Bash`, `Read`, `Glob`, `Write`, `mcp__cloudsort-jira__getJiraIssue`, `mcp__claude_ai_Slack__slack_read_channel`
   - Input: stale ticket list + their epic keys, Slack cursors, vault path, current Slack context
   - Output: updated `monitor_output.json` with `nudge_text` filled in for each draft

6. **Wire Phase 2 into `run_monitor()` in `src/agents.py`**
   - After Phase 1: check monitor_output.json for any `nudge_text: null` drafts
   - If any exist: call `run_nudge_drafter()`
   - After successful run: update Slack cursors in state

---

## Testing Plan

### Step 1 — Business day utility
Run `business_days_since()` manually with known dates:
- A Friday timestamp → tested on Sunday should return 0 (weekend gap)
- A Monday timestamp → tested on Wednesday should return 2
- A timestamp from 7 calendar days ago spanning a weekend should return 5

### Step 2 — Slack cursor baseline
- Clear `slack_cursors` from `state.json` to simulate first run
- Run monitor, confirm all 4 channels are read with 14-day lookback
- Check `state.json` after run — `slack_cursors` should be updated to latest message ts per channel
- Run monitor again — confirm only new messages are fetched (small or empty batch)

### Step 3 — Vault note lookup
- Run grep manually for a known epic key (e.g. `CLOUD-6329`) → should return `V3-Edit-Network.md`
- Run grep for a key with no vault note → should return empty, no crash
- Confirm fallback: epic description fetched from JIRA when no vault note found

### Step 4 — Nudge quality (Sonnet drafter)
- Trigger a run with at least one stale ticket
- Check that Phase 2 is spawned (visible in logs as `[nudge-drafter]`)
- Review drafted nudge text — must reference something specific (comment, feature goal, or blocker), not just "what's the status?"
- Confirm business days used in message text, not calendar days

### Step 5 — End-to-end clean run
- Run `python3 main.py` and let one full monitor cycle complete
- Verify in logs: Phase 1 completes, Phase 2 spawned only if stale tickets exist
- Check `monitor_output.json`: all `nudge_text` fields populated (not null)
- Review Slack `#cloudsort_aitpm` — nudge drafts posted for approval look contextual and specific
- Merge to main only after this passes

---

## Slack Channel IDs (confirmed)

| Channel | ID |
|---|---|
| `#cloudsort_chat` | `C049U0HNZQA` |
| `#cloudsort_backend` | `C014K67V7HB` |
| `#cloudsort_webapp` | `CTFQHDVML` |
| `#cloudsort_design` | `C016JD80V08` |

Confirmed reading from Loka workspace via claude.ai Slack MCP (Bruno's OAuth).

---

## Open Questions — All Resolved

| Question | Answer |
|---|---|
| Separate Sonnet agent or upgrade whole monitor? | Separate agent — costs nothing when no stale tickets |
| Does `slack_read_channel` support `oldest` timestamp? | ✓ Yes — Unix timestamp, tested |
| Does it support pagination? | ✓ Yes — cursor-based |
| Which Slack workspace does the MCP read? | ✓ Loka workspace — confirmed via Bruno's claude.ai OAuth |
| Should we cap nudges per run? | No — JIRA `updated` resets on comment, thresholds handle re-nudge timing |
| How many tickets get draft comments per run? | ~9 (not 36 — the rest are a summary alert) |
| Will posting a nudge reset staleness? | ✓ Yes — JIRA `updated` refreshes on any comment |
| Fallback when no vault note exists? | Fetch epic description from JIRA (`getJiraIssue`) |
