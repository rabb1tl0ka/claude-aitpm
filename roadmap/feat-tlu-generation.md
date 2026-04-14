---
status: done
priority: high
owner: "@rabb1tl0ka"
---

# Feature Spec: TLU Generation

## One-Line Overview
Enable the AI TPM to generate weekly Traffic Light Updates on demand, pulling Jira + meeting notes, posting sections to Slack for approval, then pushing to Notion.

## Branch

`feat/tlu-generation`

## Goal

Enable the AI TPM to generate a weekly Traffic Light Update (TLU) on demand. Bruno sends a message to `#cloudsort_aitpm` (the AI TPM bot picks it up via the inbound check — the exact Slack handle depends on the bot app name, the tag syntax is illustrative). The agent pulls Jira state + relevant meeting notes, generates the TLU, saves it locally in the vault, posts it to Slack section-by-section for approval, and on approval pushes each section to the corresponding Notion TLU page.

---

## Trigger

Bruno sends a message in `#cloudsort_aitpm` with a request like (the bot's actual Slack handle is determined by the app name, not hardcoded here):

> "generate TLU for last week"
> "draft the TLU for the week of Apr 7"

The `run_command` agent detects the intent and routes to `run_tlu_generation`.

---

## Week definition

- Always **Monday to Friday** of the target week.
- "Last week" = the most recently completed Mon–Fri window relative to today.
- If Bruno specifies a date, derive the Mon–Fri window that contains it.

---

## Generation flow

```
1. Determine target week (Mon–Fri dates)
2. Check state freshness
   - If state.json last_monitor_run < 24h ago → use existing state
   - Else → call run_monitor_sync() to refresh Jira data
3. Scan {project_notes_path}/meeting-notes/ for files dated within target week
   - Match on filenames containing YYYYMMDD or YYYY-MM-DD within the week range
4. Generate TLU content (Claude agent with full context)
5. Save to {project_notes_path}/traffic-lights/YYYY-MM-DD-tlu.md
   (date = Friday of the target week)
6. Post sections to Slack for approval (one message per section)
7. On approval → push section to Notion TLU page
```

---

## TLU sections

Three sections, posted as three independent Slack messages simultaneously. Each follows the existing approval workflow (✅ reaction or "approved" = push to Notion; reply = revise and re-post). Sections can be approved in any order.

| Section | Slack heading | Notion destination |
|---|---|---|
| Where We Are | `## Where We Are` | Notes section of Notion TLU page |
| Achievements | `## Achievements` | Achievements section of Notion TLU page |
| Risks | `## Risks` | Risks section of Notion TLU page |

A completion message is posted to Slack once all three sections are pushed to Notion.

---

## Config additions

### `configs/cloudsort.yaml` and `configs/example.yaml`

```yaml
# Path to local project vault (Obsidian or similar)
project_notes_path: ~/loka/vaults/loka2026/projects/cloudsort

# Notion TLU — set to the most recent known TLU page URL (copy from browser).
# Used to resolve the parent DB ID so searches are scoped to this project's TLU DB only.
# Update this after each TLU is pushed (the agent keeps this in sync automatically).
notion_last_tlu_page_url: ""   # e.g. "https://www.notion.so/loka/Apr-13-33f46e8c24378185934bca03f02c0369"
```

---

## State additions (`state.json`)

```json
{
  "pending_tlu": {
    "week_start": "2026-04-07",
    "week_end": "2026-04-11",
    "local_path": "/abs/path/to/traffic-lights/2026-04-11-tlu.md",
    "notion_page_id": "<resolved from notion_last_tlu_page_url>",
    "sections": {
      "where_we_are": { "status": "pending | approved | pushed", "slack_ts": "<ts>" },
      "achievements":  { "status": "pending | approved | pushed", "slack_ts": "<ts>" },
      "risks":         { "status": "pending | approved | pushed", "slack_ts": "<ts>" }
    }
  }
}
```

No section content in state — the local file is the source of truth. When a section is approved, its content is read from `local_path`.

---

## New: `run_tlu_generation` in `src/agents.py`

```python
async def run_tlu_generation(cfg: dict, state: dict, week_start: date, week_end: date) -> dict | None:
```

**Steps:**
1. Check `state["last_monitor_run"]` — if stale, call `run_monitor_sync()` and reload state
2. Read meeting notes files from `{project_notes_path}/meeting-notes/` where filename date falls within `[week_start, week_end]`
3. Build generation prompt with: Jira state, meeting notes content, existing TLU examples (last 2 TLUs for format reference), week dates
4. Call Claude agent → returns `{where_we_are, achievements, risks}`
5. Write full TLU markdown to `{project_notes_path}/traffic-lights/{week_end}-tlu.md`
6. Parse `notion_page_id` directly from `cfg["notion_last_tlu_page_url"]` — no Notion search needed. The config URL always points to the current week's TLU page (named after the Monday of the week). Store `notion_page_id` in `pending_tlu`.
7. Post `## Where We Are` section to `#cloudsort_aitpm` as a pending draft (same structure as existing `pending_drafts`)
8. Save `pending_tlu` to state

---

## New: `run_tlu_notion_push` in `src/agents.py`

```python
async def run_tlu_notion_push(cfg: dict, state: dict, section: str, content: str) -> None:
```

Called by `run_approval_poll` when a TLU section draft is approved. Pushes content to the corresponding Notion TLU page section via Notion MCP. Then posts the next pending section to Slack (if any remain).

---

## Changes to `run_command` in `src/agents.py`

Add intent detection for TLU generation requests. When detected:
- Parse the target week from the command text
- Call `run_tlu_generation(cfg, state, week_start, week_end)`

---

## Changes to `run_approval_poll` in `main.py`

- When a pending draft has `type: "tlu_section"`, route approval to `run_tlu_notion_push` instead of the standard Slack send
- After push, post next section if `pending_tlu` has more sections with `status: "pending"`
- When all 3 sections are pushed, post a completion message: "TLU for week of {week_start} fully published to Notion."

---

## Meeting notes file discovery

Files in `{project_notes_path}/meeting-notes/` are matched if their filename contains a date string (YYYYMMDD or YYYY-MM-DD) that falls within `[week_start, week_end]`. Files with no parseable date in the filename are skipped.

---

## TLU generation prompt context

| Source | What's included |
|---|---|
| Jira state | `state["ticket_states"]` — all tracked epics and child tickets |
| Meeting notes | Full content of matched files for the target week |
| Format reference | Last 2 TLUs from `{project_notes_path}/traffic-lights/` |
| Sprint info | `cfg["sprint"]` if set |
| Radar file | `cfg["jira_radar_file"]` |

---

## Notion page discovery

No search needed. The page ID is parsed directly from `cfg["notion_last_tlu_page_url"]`.

The Notion TLU page is always named after the **Monday of the current week** (e.g., "Apr 13") — its content covers the previous week. The user keeps `notion_last_tlu_page_url` in config pointing to the current week's page and updates it each week.

No Notion pages are ever created by this agent.

---

## Testing methodology

**Rule:** Test each step as it's implemented. Do not wait until the end.

**Rule:** Never call live Jira or Notion APIs during tests — use synthetic data that matches the expected schema. This avoids burning tokens and makes tests deterministic.

### Synthetic data fixtures (`tests/fixtures/`)

| File | Purpose |
|---|---|
| `tlu_state.json` | Fake `state["ticket_states"]` with a handful of epics and child tickets |
| `tlu_meeting_notes/` | 2–3 fake `.md` files with dates in filenames covering a test week |
| `tlu_notion_page.json` | Fake Notion API response for a TLU page (includes `parent.database_id`) |
| `tlu_existing.md` | One existing TLU in the expected format (for format reference context) |

### Tests to run after each implementation step

| Step | Test | How |
|---|---|---|
| Config helpers | `parse_notion_page_id(url)` extracts correct ID | `python3 -c` one-liner |
| Config helpers | `get_project_notes_path(cfg)` expands `~` correctly | `python3 -c` one-liner |
| Meeting note discovery | Correct files matched for a given week, undated files skipped | `python3 tests/test_tlu.py::test_meeting_note_discovery` |
| State freshness check | Stale vs. fresh state correctly detected from `last_monitor_run` | `python3 tests/test_tlu.py::test_state_freshness` |
| TLU file write | File written to correct path with correct filename and all 3 sections present | `python3 tests/test_tlu.py::test_tlu_file_write` |
| Notion page ID parsing | ID extracted correctly from various URL formats | `python3 tests/test_tlu.py::test_notion_url_parsing` |
| Pending draft structure | `pending_tlu` written to state with correct schema, no content stored | `python3 tests/test_tlu.py::test_pending_tlu_state` |
| Approval routing | `run_approval_poll` routes `tlu_section` drafts to `run_tlu_notion_push` | Mock `run_tlu_notion_push`, assert called |

### What is NOT tested here

- Live Jira API calls (covered by existing monitor tests)
- Live Notion API calls (trust the MCP)
- Live Slack posting (trust the existing approval workflow)

---

## Not in scope

- Creating Notion TLU pages (managed by external system)
- Reading vault subdirs other than `meeting-notes/` (v1 scope)
- Scheduling TLU generation (always on-demand via `@aitpm`)
- Multi-week TLU generation in a single command
