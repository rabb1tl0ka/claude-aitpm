# Jira Data Fetching: MCP vs CLI vs REST

**Date:** 2026-03-29
**Status:** Tested and concluded
**Context:** Monitor agent hitting token overflow errors when fetching child tickets via MCP JQL search.

---

## The Problem

The `searchJiraIssuesUsingJql` MCP tool returns full Jira JSON blobs. Even with field selection, 51 tickets produce ~216k characters — well over the tool result token limit. The agent recovers (it reads the saved overflow file, extracts keys, rewrites parsing scripts) but wastes multiple turns doing so.

Sample error sequence observed:
1. JQL search → 216k chars → overflow, saved to temp file
2. Read temp file → 25,039 tokens → exceeds 25,000 limit
3. Agent writes inline Python to parse it → `AttributeError: 'NoneType' has no attribute 'replace'` (fields nested under `.fields`, not flat)
4. Agent rewrites script, extracts data, continues

The monitor completed correctly but burned ~6 extra turns on recovery.

---

## Tools Evaluated

### Rovo Dev CLI — eliminated

Atlassian's AI coding assistant (their answer to Claude Code). Built on top of ACLI, requires it as a dependency. Using an AI agent to feed data to another AI agent is circular, unpredictable, and costs Rovo credits. Not relevant here.

### ACLI `workitem search` — eliminated

Tested. The `--fields` flag is a hard whitelist limited to: `issuetype, key, assignee, priority, status, summary`. Both `updated` and `sprint` (and `customfield_10020`) are rejected with an error. This is not a configuration issue — it's a deliberate or overlooked scope restriction in ACLI's output layer. Multiple Atlassian community threads confirm this, with Atlassian staff leaving related questions unanswered.

```
✗ Error: fields 'updated, sprint' are not allowed
```

`updated` is required for staleness detection. Sprint state is required for nudge filtering. ACLI `workitem search` can't support this use case.

### ACLI `sprint list-workitems` — viable but incomplete

Requires `--sprint int` and `--board int`. Sprint ID changes each sprint so it would need to be stored in config and updated manually. Gives sprint membership natively (sidesteps the sprint field problem) but still has the same `--fields` whitelist — `updated` is still inaccessible.

### Jira REST API via curl + jq — winner ✓

Tested successfully. Uses the same API token from `.env`. Full field access, output shaped by `jq` before entering agent context.

---

## Solution: curl + Jira REST API + jq

### Endpoint

```
POST https://cloudsort.atlassian.net/rest/api/3/search/jql
```

Note: the old `GET /rest/api/3/search` endpoint is deprecated and returns an error. Use the POST version.

### Command

```bash
source .env && curl -s -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
  -X POST \
  -H "Content-Type: application/json" \
  "https://$ATLASSIAN_SITE/rest/api/3/search/jql" \
  -d '{
    "jql": "issueType in (Story, Task, Bug) AND \"Epic Link\" in (CLOUD-6255, ...)",
    "fields": ["key","summary","status","assignee","updated","priority","issuelinks","customfield_10020"],
    "maxResults": 100
  }' | jq '[.issues[] | {
    key,
    summary: .fields.summary,
    status: .fields.status.name,
    assignee: .fields.assignee.displayName,
    updated: .fields.updated,
    priority: .fields.priority.name,
    sprint_state: (.fields.customfield_10020 // [] | map(select(.state == "active")) | if length > 0 then "active" else "none" end),
    blockers: ([.fields.issuelinks[]? | select(.type.inward == "is blocked by") | .inwardIssue.key] // [])
  }]'
```

### Output size (tested)

| Approach | Tickets | Output size |
|---|---|---|
| MCP `searchJiraIssuesUsingJql` | 51 | ~216k chars (overflows) |
| curl + jq (all fields needed) | 100 | ~30k chars |

**7x smaller on more tickets, all required fields present.**

### Sample output

```json
[
  {
    "key": "CLOUD-6539",
    "summary": "[Bug] Invalid input value for enum event_eventtype",
    "status": "To Do",
    "assignee": "João Pedro Fontes",
    "updated": "2026-03-25T08:10:47.706-0700",
    "priority": "P1",
    "sprint_state": "active",
    "blockers": []
  }
]
```

---

## Implementation Plan

### What changes

1. Add `Bash` to `_MONITOR_TOOLS` in `agents.py`
2. Update monitor prompt Step 2: replace MCP JQL call with `curl` + `jq` command
3. Auth: already in `.env` — no new secrets needed

### What stays the same

- MCP for writes: comments (`addCommentToJiraIssue`) and transitions (`transitionJiraIssue`) — low volume, no overflow risk, ADF @mention support
- Step 1 (epic fetch) via MCP — small result set, no overflow issue in practice

### Auth

API token stored in `.env` (`ATLASSIAN_API_TOKEN`, `ATLASSIAN_EMAIL`, `ATLASSIAN_SITE`). Already gitignored. No additional setup required — ACLI was installed and authenticated as a prerequisite but the curl approach uses the token directly, not ACLI's stored credentials.

---

## Open Questions (resolved)

| Question | Answer |
|---|---|
| Does ACLI expose sprint data via `--fields`? | No — hard whitelist, sprint and updated both rejected |
| Does `customfield_10020` work in ACLI? | No — same error |
| Does the REST API give us all needed fields? | Yes — tested, all fields confirmed |
| Is the old `/rest/api/3/search` endpoint still valid? | No — deprecated, returns error. Use `POST /rest/api/3/search/jql` |
| What's the output size with curl + jq? | ~30k chars for 100 tickets (vs 216k for 51 via MCP) |
