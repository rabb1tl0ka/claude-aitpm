"""Claude agent spawner — agents do JIRA analysis and write output to files.
Slack I/O is handled by Python (slack_client.py), not by agents.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, AssistantMessage, query

from .state import fetch_ticket_details

log = logging.getLogger("aitpm")

PROJECT_DIR = str(Path(__file__).parent.parent)

_MONITOR_TOOLS = [
    "mcp__cloudsort-jira__searchJiraIssuesUsingJql",
    "mcp__cloudsort-jira__getJiraIssue",
    "Bash",
    "Read",
    "Write",
]

_JIRA_COMMENT_TOOLS = [
    "mcp__cloudsort-jira__addCommentToJiraIssue",
]

_COMMAND_TOOLS = [
    "mcp__cloudsort-jira__searchJiraIssuesUsingJql",
    "mcp__cloudsort-jira__getJiraIssue",
    "mcp__cloudsort-jira__addCommentToJiraIssue",
    "mcp__cloudsort-jira__getTransitionsForJiraIssue",
    "mcp__cloudsort-jira__transitionJiraIssue",
    "Read",
    "Write",
]

_NUDGE_TOOLS = [
    "mcp__cloudsort-jira__getJiraIssue",  # Step 2: epic description fallback when no vault note found
    "mcp__claude_ai_Slack__slack_read_channel",
    "Bash",
    "Read",
    "Glob",
    "Write",
]


def _atlassian_browse_url() -> str:
    return f"https://{os.environ['ATLASSIAN_SITE']}/browse"


def _options(tools: list, model: str = "haiku", max_turns: int = 20) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=model,
        allowed_tools=tools,
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        cwd=PROJECT_DIR,
        setting_sources=["user"],
    )


async def _run(prompt: str, tools: list, model: str = "haiku", max_turns: int = 20, label: str = "aitpm") -> None:
    log.info(f"[{label}] Spawning agent (model={model}, tools={len(tools)})...")
    try:
        async for message in query(prompt=prompt, options=_options(tools, model, max_turns)):
            msg_type = type(message).__name__
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        preview = block.text[:300].replace("\n", " ")
                        log.info(f"[{label}] [Assistant] {preview}{'...' if len(block.text) > 300 else ''}")
                    elif hasattr(block, "type") and block.type == "tool_use":
                        log.info(f"[{label}] → {block.name}({_tool_args_preview(block)})")
            elif hasattr(message, "content") and message.content:
                preview = str(message.content)[:300].replace("\n", " ")
                log.info(f"[{label}] [{msg_type}] {preview}{'...' if len(str(message.content)) > 300 else ''}")
            elif isinstance(message, ResultMessage):
                log.info(f"[{label}] Done. Cost: ${message.total_cost_usd:.4f}")
            else:
                log.info(f"[{label}] [{msg_type}]")
    except Exception as e:
        log.error(f"[{label}] Error: {e}")


def _tool_args_preview(block) -> str:
    try:
        args = block.input or {}
        parts = []
        for k, v in list(args.items())[:2]:
            v_str = str(v)[:60].replace("\n", " ")
            parts.append(f"{k}={v_str!r}")
        return ", ".join(parts)
    except Exception:
        return "..."


def _read_radar_file(path: str) -> str:
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        return f"(radar file not found: {expanded})"
    with open(expanded) as f:
        return f.read()


async def run_monitor(cfg: dict, state: dict, run_type: str = "monitor", epic_cache: list | None = None, child_tickets: list | None = None, is_full_fetch: bool = True) -> None:
    """Run JIRA monitor. Writes drafts to state/monitor_output.json for Python to post."""
    tpm_name = cfg.get("tpm_name", "the PM")
    aitpm_name = cfg.get("aitpm_name", "AI TPM")
    atlassian_url = _atlassian_browse_url()
    jira_key = cfg["jira_project_key"]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    last_run = state.get("last_monitor_run") or "never"
    ticket_states = json.dumps(
        {k: {"status": v.get("status"), "last_updated": v.get("last_updated")}
         for k, v in state.get("ticket_states", {}).items()},
        indent=2
    )
    radar_content = _read_radar_file(cfg["jira_radar_file"])
    staleness_thresholds = cfg.get("staleness_thresholds", {"P1": 1, "P2": 2, "P3": 4, "P4": None})
    staleness_info = "\n".join(
        f"  - {p}: {d} day(s)" if d else f"  - {p}: no nudge"
        for p, d in staleness_thresholds.items()
    )

    sprint_info = ""
    s = cfg.get("sprint", {})
    if s.get("name"):
        sprint_info = f"Current sprint: {s['name']} ({s.get('start', '?')} to {s.get('end', '?')})"

    slack_channels = cfg.get("slack_channels", {})
    channels_info = "\n".join(f"  - {k}: {v}" for k, v in slack_channels.items())

    is_digest = run_type == "digest"
    run_label = "8AM DIGEST + RISK ASSESSMENT" if is_digest else "HOURLY MONITOR"
    feats = cfg.get("monitor_features", {})

    output_file = os.path.join(PROJECT_DIR, "state", "monitor_output.json")

    # Pre-fetch comments for comment_activity: tickets updated since last_run with status unchanged
    comment_data: dict = {}
    if feats.get("comment_activity", True) and last_run != "never" and child_tickets:
        prev_ticket_states = state.get("ticket_states", {})
        try:
            last_run_dt = datetime.fromisoformat(last_run).replace(tzinfo=timezone.utc) if last_run != "never" else None
        except ValueError:
            last_run_dt = None
        if last_run_dt:
            activity_keys = []
            for t in child_tickets:
                updated_str = t.get("updated")
                if not updated_str:
                    continue
                try:
                    updated_dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if updated_dt <= last_run_dt:
                    continue
                prev_status = prev_ticket_states.get(t["key"], {}).get("status")
                if prev_status and t["status"] == prev_status:
                    activity_keys.append(t["key"])
            if activity_keys:
                log.info(f"[monitor] Pre-fetching comments for {len(activity_keys)} tickets with new activity...")
                comment_data = fetch_ticket_details(activity_keys, fields=["comment"])

    # Step 1 is resolved by Python before the agent runs — epic_cache is always populated here
    epic_keys_str = ",".join(epic_cache)
    step1_block = f"""## Step 1: Epic keys (pre-resolved)
The Python runner already fetched or loaded these from cache. Use them directly:
`{epic_keys_str}`
"""

    fetch_mode = "full" if is_full_fetch else f"incremental (since {last_run})"
    step2_block = f"""## Step 2: Child tickets (pre-fetched)
The Python runner already fetched these via Jira REST API ({fetch_mode}). Do NOT make any Bash or API calls for this step.

```json
{json.dumps(child_tickets or [], indent=2)}
```

Use this list for all analysis in Step 3.
For `user_map`: extract `assignee` (displayName) and `assignee_id` (accountId) from each ticket.
"""

    # --- Step 3: build analysis blocks from active features ---
    step3_sections = []

    if feats.get("status_changes", True):
        step3_sections.append("""### Status changes
Compare each ticket's current status to Known Ticket States from last run.
Report ALL status changes — progress is good news worth surfacing:
- 🟢 Advanced (e.g. In Progress → In Review, In Review → Done)
- 🔴 Regressed or newly blocked""")

    if feats.get("comment_activity", True):
        if comment_data:
            comment_data_json = json.dumps(comment_data, indent=2)
            step3_sections.append(f"""### New comment activity (pre-fetched)
The Python runner already identified tickets updated since last run with no status change, and fetched their latest comments. Do NOT call getJiraIssue for these.

```json
{comment_data_json}
```

For each ticket in the above data that has a `latest_comment`: surface it as a type "alert" including:
- Ticket key, title and a link: <{atlassian_url}/TICKET-KEY|TICKET-KEY: Title>
- Who commented and what they said (latest comment text, quoted)
Do not suggest actions — {tpm_name} will reply to this alert with instructions if needed.""")
        else:
            step3_sections.append("""### New comment activity
No tickets with new comment activity detected (either no updates since last run, or all updates were status changes). Skip this section.""")

    if feats.get("staleness", True):
        step3_sections.append(f"""### Staleness check
Each ticket in the Step 2 data includes a `business_days_stale` field — use it directly, do not recompute.
Apply staleness thresholds by ticket priority:
{staleness_info}
- P4 tickets: never nudge
- Tickets with `sprint_state` != "active": never nudge (backlog, future, or closed sprint)
- A ticket is stale if `business_days_stale` exceeds the threshold for its priority AND `sprint_state` is "active"

For stale tickets with an assignee: add them to `pending_nudges` in the output — do NOT draft the comment text here. A dedicated Sonnet agent handles nudge drafting in a second pass.
For stale tickets with NO assignee: create a type "alert" flagging that the ticket is stale and unassigned so {tpm_name} can assign it.""")

    if feats.get("planning_gaps", True):
        step3_sections.append(f"""### Planning gaps
For tickets with no sprint assigned (customfield_10020 is null or empty): create ONE SEPARATE type "alert" post per ticket. Do NOT group them into one message.
Each alert must follow this exact format:
"<{atlassian_url}/TICKET-KEY|TICKET-KEY: Ticket title> — no sprint assigned"
Example: "<{atlassian_url}/{jira_key}-XXXX|{jira_key}-XXXX: Example ticket title> — no sprint assigned"
{tpm_name} will reply to each individual alert with instructions (e.g. "set sprint 161"). Do not nudge assignees.""")

    if feats.get("dependency_chains", True):
        step3_sections.append("""### Dependency chain check
For each ticket, inspect its `blockers` field for blocking relationships:
- If a ticket is blocked by another ticket and that blocker's status is now Done:
  - Check Known Ticket States: was the blocker already Done last run? If yes, skip (already notified).
  - If this is new: create a draft unblock notification to the assignee of the newly-unblocked ticket.
- Use `blocker_keys` in Known Ticket States to detect changes in blocking relationships.""")

    if feats.get("scope_summary", True):
        if is_digest:
            step3_sections.append("### Digest summary\nSummarise ALL radar tickets grouped by epic: current status, assignee, progress, risks. This is the daily snapshot.")
        else:
            step3_sections.append("### Monitor scope\nReport everything that changed or needs attention since last run. If nothing changed and nothing is stale, posts array can be empty.")

    if step3_sections:
        step3_block = "## Step 3: Analyse every ticket — report all meaningful activity\n\nThis is an activity feed, not just a problem detector. Surface good news too.\n\n" + "\n\n".join(step3_sections)
    else:
        step3_block = "## Step 3: No analysis features enabled — skip to Step 4."

    prompt = f"""You are {aitpm_name} (AI Technical Project Manager) for {cfg['project_name']}.
This is a {run_label} run. Your output will be posted to Slack by the Python runner.

## Context
- Project: {cfg['project_name']}
- JIRA project key: {jira_key}
- Current time (UTC): {now}
- Last monitor run: {last_run}
- Staleness thresholds (no update = nudge after N days):
{staleness_info}
{f"- {sprint_info}" if sprint_info else ""}

## Available team channels for outbound messages
{channels_info}

## Radar File
{radar_content}

## Known Ticket States (from last run)
{ticket_states}

---

{step1_block}
{step2_block}
{step3_block}

## Step 4: Write output file
Write a JSON file at this exact absolute path: {output_file}

Each item in `posts` is one of two types:

**Type 1 — Alert (for {tpm_name} only)**
Use for: status changes, comment activity, staleness alerts, digest summaries — anything {tpm_name} should know about but that doesn't require a team message right now.
{{
  "type": "alert",
  "text": "<{atlassian_url}/TICKET-KEY|TICKET-KEY: Ticket title> — <concise message, no em dashes>",
  "target_channel": null,
  "context": "<one-line description>"
}}

**Type 2 — Draft ({tpm_name} reviews, then sends)**
Two subtypes based on `action`:

`action: "slack"` — unblock notifications sent to the team channel:
{{
  "type": "draft",
  "action": "slack",
  "text": "<draft message — include ticket key and title, be direct and friendly>",
  "target_channel": "<most relevant team channel>",
  "ticket_key": null,
  "context": "<one-line description>"
}}

`action: "jira_comment"` — staleness nudges posted as a JIRA comment on the ticket:
{{
  "type": "draft",
  "action": "jira_comment",
  "text": "<{atlassian_url}/TICKET-KEY|TICKET-KEY: Ticket title>\\n\\nProposed comment:\\n[comment text for {tpm_name} to review]",
  "target_channel": null,
  "ticket_key": "<TICKET-KEY>",
  "context": "<one-line description>"
}}

Full file structure:
{{
  "run_type": "{run_type}",
  "run_at": "{now}",
  "posts": [
    {{ "type": "alert|draft", "text": "...", "target_channel": null or "#channel", "context": "..." }}
  ],
  "pending_nudges": [
    {{
      "ticket_key": "<TICKET-KEY>",
      "summary": "<ticket summary>",
      "assignee": "<displayName>",
      "priority": "<priority>",
      "business_days_stale": "<int>",
      "sprint_state": "active"
    }}
  ],
  "user_map": {{
    "<displayName>": "<accountId>"
  }}
}}

For `user_map`: extract the `displayName` and `accountId` from every assignee field you encounter across all tickets. Include all of them — this builds a local cache of JIRA users automatically.
Do NOT include `ticket_states` in the output — Python builds this directly from the fetch data.

## Rules
- No em dashes in writing
- Be direct and concise
- Good news (progress, completions) is worth reporting — don't filter it out
- Write the output file now
"""

    model = "sonnet" if is_digest else "haiku"
    log.info(f"[monitor-{run_type}] Prompt ready ({len(prompt)} chars). Calling agent...")
    await _run(prompt, _MONITOR_TOOLS, model=model, max_turns=30, label=f"monitor-{run_type}")


async def run_revision(cfg: dict, original_draft: str, feedback: str, context: str) -> str | None:
    """Spawn agent to revise a draft based on the owner's feedback. Returns revised text or None."""
    tpm_name = cfg.get("tpm_name", "the PM")
    aitpm_name = cfg.get("aitpm_name", "AI TPM")
    output_file = os.path.join(PROJECT_DIR, "state", "revision_output.json")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt = f"""You are {aitpm_name} for {cfg['project_name']}. Revise a draft message based on {tpm_name}'s feedback.

## Original draft
{original_draft}

## Context
{context}

## {tpm_name}'s feedback
{feedback}

## Instructions
1. Apply {tpm_name}'s changes to the draft
2. Keep the same purpose and tone, just incorporate the feedback
3. Write the result to this exact absolute path: {output_file}
{{
  "revised_text": "<revised message text>",
  "revised_at": "{now}"
}}

## Rules
- No em dashes
- Be direct and concise
- No "Hey team" openers
"""

    # Clean up any previous revision output
    if os.path.isfile(output_file):
        os.remove(output_file)

    await _run(prompt, ["Write"], model="haiku", max_turns=5, label="revision")

    if os.path.isfile(output_file):
        with open(output_file) as f:
            result = json.load(f)
        os.remove(output_file)
        return result.get("revised_text")
    return None


async def run_command(cfg: dict, state: dict, command_text: str) -> dict | None:
    """Handle an @aitpm command. Returns result dict or None."""
    tpm_name = cfg.get("tpm_name", "the PM")
    aitpm_name = cfg.get("aitpm_name", "AI TPM")
    atlassian_url = _atlassian_browse_url()

    output_file = os.path.join(PROJECT_DIR, "state", "command_output.json")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    radar_content = _read_radar_file(cfg["jira_radar_file"])
    ticket_states = json.dumps(state.get("ticket_states", {}), indent=2)
    staleness_thresholds = cfg.get("staleness_thresholds", {"P1": 1, "P2": 2, "P3": 4, "P4": None})
    staleness_info = "\n".join(
        f"  - {p}: {d} day(s)" if d else f"  - {p}: no nudge"
        for p, d in staleness_thresholds.items()
    )

    sprint_info = ""
    s = cfg.get("sprint", {})
    if s.get("name"):
        sprint_info = f"Current sprint: {s['name']} ({s.get('start', '?')} to {s.get('end', '?')})"

    slack_channels = cfg.get("slack_channels", {})
    channels_info = "\n".join(f"  - {k}: {v}" for k, v in slack_channels.items())

    pending_drafts = state.get("pending_drafts", [])
    pending_summary = json.dumps(
        [{"context": d.get("context"), "status": d.get("status"), "target_channel": d.get("target_channel")} for d in pending_drafts],
        indent=2
    ) if pending_drafts else "None"

    atlassian_site = os.environ["ATLASSIAN_SITE"]
    prompt = f"""You are {aitpm_name} for {cfg['project_name']}. {tpm_name} sent you a command via Slack.
Respond as you would in a full Claude Code session — you have complete project context below.

## Context
- Project: {cfg['project_name']}
- JIRA project key: {cfg['jira_project_key']}
- JIRA cloudId: {atlassian_site}
- Current time (UTC): {now}
- Staleness thresholds: P1={staleness_thresholds.get('P1')}d, P2={staleness_thresholds.get('P2')}d, P3={staleness_thresholds.get('P3')}d, P4=none
- Last monitor run: {state.get("last_monitor_run") or "never"}
{f"- {sprint_info}" if sprint_info else ""}

## Team Slack channels
{channels_info}

## Radar File
{radar_content}

## Known Ticket States (from last monitor run)
{ticket_states}

## Pending drafts awaiting {tpm_name}'s approval
{pending_summary}

## {tpm_name}'s command
{command_text}

---

## Instructions
1. Understand what {tpm_name} is asking — answer it fully, same as you would in a Claude Code session
2. Use `mcp__cloudsort-jira__searchJiraIssuesUsingJql` or `mcp__cloudsort-jira__getJiraIssue` as needed — use the cloudId from Context above, do NOT call getAccessibleAtlassianResources
3. JIRA comment replies have a `parentId` field but appear in the same flat list — look at ALL comments to find all activity
4. If {tpm_name} asks you to comment on a ticket or transition it, do it directly using the available tools
5. Write your response to this exact absolute path: {output_file}
{{
  "response": "<your answer — concise, direct, no em dashes>",
  "draft_for_team": "<optional: message to draft for team review, or null>",
  "draft_target_channel": "<team channel if draft_for_team is set, else null>"
}}

## Rules
- Direct and concise
- No em dashes
- No fluff
"""

    if os.path.isfile(output_file):
        os.remove(output_file)

    log.info(f"[command] Handling: {command_text[:80]}")
    await _run(prompt, _COMMAND_TOOLS, model="sonnet", max_turns=20, label="command")

    if os.path.isfile(output_file):
        with open(output_file) as f:
            result = json.load(f)
        os.remove(output_file)
        return result
    return None


async def run_jira_comment(ticket_key: str, comment_text: str, user_map: dict | None = None) -> bool:
    """Post an approved comment to a JIRA ticket. Returns True on success."""
    atlassian_site = os.environ["ATLASSIAN_SITE"]
    user_map_info = ""
    if user_map:
        entries = "\n".join(f"  {name}: {account_id}" for name, account_id in user_map.items())
        user_map_info = f"""
## User map (displayName -> accountId)
Use these accountIds for proper JIRA @mentions in ADF format:
{entries}

For mentions, use ADF format:
{{"type": "mention", "attrs": {{"id": "<accountId>", "text": "@DisplayName"}}}}
"""

    prompt = f"""Post the following comment to JIRA ticket {ticket_key}.

Comment text:
{comment_text}
{user_map_info}
Use `mcp__cloudsort-jira__addCommentToJiraIssue` directly. Do NOT call getAccessibleAtlassianResources first.
The cloudId is: {atlassian_site}
If the comment contains @mentions, use proper ADF mention nodes with the accountIds from the user map above.
"""
    try:
        await _run(prompt, _JIRA_COMMENT_TOOLS, model="haiku", max_turns=3, label="jira-comment")
        return True
    except Exception as e:
        log.error(f"[jira-comment] Failed to post comment on {ticket_key}: {e}")
        return False


async def run_nudge_drafter(cfg: dict, state: dict, pending_nudges: list) -> None:
    """Draft smart, contextual nudge comments for stale tickets using Sonnet.
    Reads vault notes + Slack context. Writes state/nudge_output.json."""
    tpm_name = cfg.get("tpm_name", "the PM")
    aitpm_name = cfg.get("aitpm_name", "AI TPM")
    atlassian_url = _atlassian_browse_url()
    jira_key = cfg["jira_project_key"]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    features_vault_path = os.path.expanduser(cfg.get("features_vault_path", ""))
    slack_channel_ids = cfg.get("slack_channel_ids", {})
    output_file = os.path.join(PROJECT_DIR, "state", "nudge_output.json")

    # Pre-fetch JIRA context (comment history + parent/epic) for all stale tickets
    nudge_keys = [t["ticket_key"] for t in pending_nudges]
    log.info(f"[nudge-drafter] Pre-fetching JIRA context for {len(nudge_keys)} ticket(s)...")
    ticket_details = fetch_ticket_details(nudge_keys)
    ticket_details_json = json.dumps(ticket_details, indent=2)

    slack_channels_info = "\n".join(
        f"  {name}: id={cid}, oldest={state.get('slack_cursors', {}).get(cid, '(14 days ago — first run)')}"
        for name, cid in slack_channel_ids.items()
    )
    nudges_json = json.dumps(pending_nudges, indent=2)

    prompt = f"""You are {aitpm_name} for {cfg['project_name']}. Draft smart, contextual JIRA nudge comments for stale tickets.

## Current time (UTC)
{now}

## Stale tickets to nudge
{nudges_json}

## For each ticket above, follow these steps:

### Step 1 — JIRA context (pre-fetched)
The Python runner already fetched comment history and parent/epic info for each ticket. Do NOT call getJiraIssue.

```json
{ticket_details_json}
```

Each entry contains:
- `summary`: ticket title
- `description`: full ticket description (acceptance criteria, open questions, decisions already made)
- `full_comments`: full comment history (what was last discussed, any blockers mentioned)
- `latest_comment`: the most recent comment
- `parent_key`: the parent epic key

### Step 2 — Look up feature vault note
Use Bash to search for the epic key in the vault:
```bash
grep -rl "EPIC-KEY" {features_vault_path}/
```
Replace EPIC-KEY with the actual epic key from Step 1.

**If a file is found:** read it — it contains the feature goal, current/future state context, implementation approach, dependencies, and open questions.

**If no file is found:**
1. Call `mcp__cloudsort-jira__getJiraIssue` on the epic key with field `description` to get the feature context.
2. Read the template at `{features_vault_path}/_feature_template.md`
3. Create a new vault note at `{features_vault_path}/EPIC-KEY.md` (replace EPIC-KEY with the actual key) by filling in the template with whatever you can derive from the Jira description. Leave sections as `TBD` where there is not enough information. Do NOT invent details.

### Step 3 — Read recent Slack messages
Read each channel below for recent team discussions:
{slack_channels_info}

Use `mcp__claude_ai_Slack__slack_read_channel` with the channel ID and the `oldest` timestamp shown.
Note the `ts` of the latest message in each channel — include these in the output as `slack_cursors`.
If a channel has no new messages, keep the same oldest timestamp.

### Step 4 — Draft the nudge comment
Combine all context to write a specific, non-robotic comment nudging the assignee.

Write in first person as the PM — do NOT use "{tpm_name}" or refer to the author in third person.

**Good (vault note + prior comments):**
"Hey @Daniela - last note here was about waiting on design mockups for the Edit Network payment flow. Any movement there? Trying to figure out if we're still on track."

**Good (comment history, no vault note):**
"Hey @gabriel.menezes - saw your note from last week about the API shape being unclear. Did that get sorted with the backend team?"

**Good (no prior context):**
"Hey @gabriel.menezes - {atlassian_url}/{jira_key}-XXXX has been quiet for 3 business days. Anything blocking this work, or is it moving along?"

**Rules:**
- Never just ask "what's the current status?" — reference something specific
- Neutral tone — not assuming there's a problem
- If the ticket has blockers, acknowledge them explicitly
- No comma after @mention
- Keep it short: 2-3 sentences max
- No em dashes
- Write in first person — do not refer to the PM by name (the comment will be posted under the PM's account)
- When referencing a ticket by key in comment text, use the full URL: {atlassian_url}/TICKET-KEY

### Step 5 — Write output file
Write JSON to: {output_file}

```json
{{
  "posts": [
    {{
      "type": "draft",
      "action": "jira_comment",
      "text": "<{atlassian_url}/TICKET-KEY|TICKET-KEY: Ticket title>\\n\\nProposed comment:\\n[your drafted comment]",
      "target_channel": null,
      "ticket_key": "TICKET-KEY",
      "context": "<one-line description>"
    }}
  ],
  "slack_cursors": {{
    "<channel_id>": "<latest_message_ts as string>"
  }}
}}
```

One post per stale ticket. Include all channel IDs in `slack_cursors`.
"""

    log.info(f"[nudge-drafter] Drafting {len(pending_nudges)} nudge(s) (model=sonnet)...")
    await _run(prompt, _NUDGE_TOOLS, model="sonnet", max_turns=40, label="nudge-drafter")


def run_monitor_sync(cfg: dict, state: dict, run_type: str = "monitor", epic_cache: list | None = None, child_tickets: list | None = None, is_full_fetch: bool = True) -> None:
    asyncio.run(run_monitor(cfg, state, run_type, epic_cache=epic_cache, child_tickets=child_tickets, is_full_fetch=is_full_fetch))


def run_nudge_drafter_sync(cfg: dict, state: dict, pending_nudges: list) -> None:
    asyncio.run(run_nudge_drafter(cfg, state, pending_nudges))


def run_revision_sync(cfg: dict, original_draft: str, feedback: str, context: str) -> str | None:
    return asyncio.run(run_revision(cfg, original_draft, feedback, context))


def run_command_sync(cfg: dict, state: dict, command_text: str) -> dict | None:
    return asyncio.run(run_command(cfg, state, command_text))


def run_jira_comment_sync(ticket_key: str, comment_text: str, user_map: dict | None = None) -> bool:
    return asyncio.run(run_jira_comment(ticket_key, comment_text, user_map))
