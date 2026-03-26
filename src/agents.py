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

log = logging.getLogger("aitpm")

PROJECT_DIR = str(Path(__file__).parent.parent)

_MONITOR_TOOLS = [
    "mcp__cloudsort-jira__searchJiraIssuesUsingJql",
    "mcp__cloudsort-jira__getJiraIssue",
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


async def run_monitor(cfg: dict, state: dict, run_type: str = "monitor") -> None:
    """Run JIRA monitor. Writes drafts to state/monitor_output.json for Python to post."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    last_run = state.get("last_monitor_run") or "never"
    ticket_states = json.dumps(state.get("ticket_states", {}), indent=2)
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

    output_file = os.path.join(PROJECT_DIR, "state", "monitor_output.json")

    prompt = f"""You are the AI AITPM (AI Technical Project Manager) for CloudSort.
This is a {run_label} run. Your output will be posted to Slack by the Python runner.

## Context
- Project: {cfg['project_name']}
- JIRA project key: {cfg['jira_project_key']}
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

## Step 1: Fetch watched epics dynamically
Use `mcp__cloudsort-jira__searchJiraIssuesUsingJql` directly — do NOT call getAccessibleAtlassianResources first.
Run the Step 1 JQL from the radar file to get the current list of watched epics. Extract the epic keys from the results.

## Step 2: Fetch all active child tickets
Run the Step 2 JQL from the radar file, substituting the epic keys you just retrieved in Step 1.
Request ONLY these fields to keep the response small: summary, status, assignee, updated, priority, issuelinks, customfield_10020.
The sprint data is in `customfield_10020` — it's an array of sprint objects with `state` ("active", "future", "closed") and `name`.
A ticket is in the active sprint if any entry in `customfield_10020` has `state: "active"`.
Set maxResults to 100.

## Step 3: Analyse every ticket — report all meaningful activity

This is an activity feed, not just a problem detector. Surface good news too.

### 3a — Status changes
Compare each ticket's current status to Known Ticket States from last run.
Report ALL status changes — progress is good news worth surfacing:
- 🟢 Advanced (e.g. In Progress → In Review, In Review → Done)
- 🔴 Regressed or newly blocked

### 3b — New comment activity
If a ticket's `updated` timestamp is newer than last run and its status has NOT changed, a comment was likely added.
For each such ticket: call `mcp__cloudsort-jira__getJiraIssue` with the `comment` field to fetch the latest comment.
Surface this as a type "alert" including:
- Ticket key, title and a link: <https://cloudsort.atlassian.net/browse/TICKET-KEY|TICKET-KEY: Title>
- Who commented and what they said (latest comment text, quoted)
Do not suggest actions — Bruno will reply to this alert with instructions if needed.

### 3c — Staleness check
JIRA's `updated` field reflects ALL activity including comments and status changes — it is the single source of truth.
Apply staleness thresholds by ticket priority:
{staleness_info}
- P4 tickets: never nudge
- Tickets with no sprint assigned: never nudge — they are backlog items
- Tickets in a future or closed sprint: never nudge
- Only nudge tickets where the sprint field shows state = "active"
A ticket is stale if its `updated` timestamp exceeds the threshold for its priority, relative to now ({now}), AND its sprint state is "active".
For stale tickets: before drafting a nudge, call `mcp__cloudsort-jira__getJiraIssue` with the `comment` field to fetch the latest comments on the ticket.
Use the most recent comment as context:
- If the last comment already explains the delay (e.g. "waiting on design", "will finish tomorrow") — acknowledge it in the nudge rather than asking cold. Example: "Hey @[assignee] - saw your last note about [X]. Any update since then?"
- If there are no comments or the last comment is old and vague — ask for a straightforward status update. Example: "Hey @[assignee] - no updates here in N days. What's the current status?"
- Neutral tone throughout, not assuming there's a blocker
- Tag the assignee by @mention (use their JIRA display name) so they get a notification
- No comma after the @mention
- If the ticket has no assignee: do NOT create a jira_comment draft. Instead create a type "alert" flagging that the ticket is stale and unassigned so Bruno can assign it.
- The draft shown to Bruno must include the ticket title and a link so he knows what he's approving:
  Format the `text` field as: "<https://cloudsort.atlassian.net/browse/TICKET-KEY|TICKET-KEY: Ticket title>\n\nProposed comment:\n[comment text]"
- Set `action` to "jira_comment" and `ticket_key` to the ticket key

### 3d — Planning gaps
For tickets with no sprint assigned (customfield_10020 is null or empty): create ONE SEPARATE type "alert" post per ticket. Do NOT group them into one message.
Each alert must follow this exact format:
"<https://cloudsort.atlassian.net/browse/TICKET-KEY|TICKET-KEY: Ticket title> — no sprint assigned"
Example: "<https://cloudsort.atlassian.net/browse/CLOUD-6521|CLOUD-6521: WEB: List payment methods> — no sprint assigned"
Bruno will reply to each individual alert with instructions (e.g. "set sprint 161"). Do not nudge assignees.

### 3e — Dependency chain check
For each ticket, inspect its `issuelinks` field for blocking relationships:
- If a ticket is blocked by another ticket and that blocker's status is now Done:
  - Check Known Ticket States: was the blocker already Done last run? If yes, skip (already notified).
  - If this is new: create a draft unblock notification to the assignee of the newly-unblocked ticket.
- Use `blocker_keys` in Known Ticket States to detect changes in blocking relationships.

{"### 3f — Full digest scope" if is_digest else "### 3f — Monitor scope"}
{"Summarise ALL radar tickets grouped by epic: current status, assignee, progress, risks. This is the daily snapshot." if is_digest else "Report everything that changed or needs attention since last run. If nothing changed and nothing is stale, posts array can be empty."}

## Step 4: Write output file
Write a JSON file at this exact absolute path: {output_file}

Each item in `posts` is one of two types:

**Type 1 — Alert (for Bruno only)**
Use for: status changes, comment activity, staleness alerts, digest summaries — anything Bruno should know about but that doesn't require a team message right now.
{{
  "type": "alert",
  "text": "<message — concise, no em dashes>",
  "target_channel": null,
  "context": "<one-line description>"
}}

**Type 2 — Draft (Bruno reviews, then sends)**
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
  "text": "<https://cloudsort.atlassian.net/browse/TICKET-KEY|TICKET-KEY: Ticket title>\n\nProposed comment:\n[comment text for Bruno to review]",
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
  "ticket_states": {{
    "<TICKET-KEY>": {{
      "status": "<status>",
      "assignee": "<name or null>",
      "summary": "<summary>",
      "last_updated": "<ISO timestamp from JIRA updated field>",
      "priority": "<priority>",
      "blocker_keys": ["<list of ticket keys blocking this ticket, empty if none>"],
      "sprint_state": "<active|future|closed|none>"
    }}
  }}
}}

## Rules
- No em dashes in writing
- Be direct and concise
- Good news (progress, completions) is worth reporting — don't filter it out
- Write the output file now
"""

    model = "sonnet" if is_digest else "haiku"
    log.info(f"[monitor-{run_type}] Prompt ready ({len(prompt)} chars). Calling agent...")
    await _run(prompt, _MONITOR_TOOLS, model=model, max_turns=30, label=f"monitor-{run_type}")


async def run_revision(original_draft: str, feedback: str, context: str) -> str | None:
    """Spawn agent to revise a draft based on Bruno's feedback. Returns revised text or None."""
    output_file = os.path.join(PROJECT_DIR, "state", "revision_output.json")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt = f"""You are the AI AITPM for CloudSort. Revise a draft message based on Bruno's feedback.

## Original draft
{original_draft}

## Context
{context}

## Bruno's feedback
{feedback}

## Instructions
1. Apply Bruno's changes to the draft
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

    prompt = f"""You are the AI AITPM for CloudSort. Bruno sent you a command via Slack.
Respond as you would in a full Claude Code session — you have complete project context below.

## Context
- Project: {cfg['project_name']}
- JIRA project key: {cfg['jira_project_key']}
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

## Pending drafts awaiting Bruno's approval
{pending_summary}

## Bruno's command
{command_text}

---

## Instructions
1. Understand what Bruno is asking — answer it fully, same as you would in a Claude Code session
2. Use `mcp__cloudsort-jira__searchJiraIssuesUsingJql` or `mcp__cloudsort-jira__getJiraIssue` as needed — do NOT call getAccessibleAtlassianResources first
3. JIRA comment replies have a `parentId` field but appear in the same flat list — look at ALL comments to find all activity
4. If Bruno asks you to comment on a ticket or transition it, do it directly using the available tools
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


async def run_jira_comment(ticket_key: str, comment_text: str) -> bool:
    """Post an approved comment to a JIRA ticket. Returns True on success."""
    prompt = f"""Post the following comment to JIRA ticket {ticket_key}.

Comment text:
{comment_text}

Use `mcp__cloudsort-jira__addCommentToJiraIssue` directly. Do NOT call getAccessibleAtlassianResources first.
The cloudId is: cloudsort.atlassian.net
"""
    try:
        await _run(prompt, _JIRA_COMMENT_TOOLS, model="haiku", max_turns=3, label="jira-comment")
        return True
    except Exception as e:
        log.error(f"[jira-comment] Failed to post comment on {ticket_key}: {e}")
        return False


def run_monitor_sync(cfg: dict, state: dict, run_type: str = "monitor") -> None:
    asyncio.run(run_monitor(cfg, state, run_type))


def run_revision_sync(original_draft: str, feedback: str, context: str) -> str | None:
    return asyncio.run(run_revision(original_draft, feedback, context))


def run_command_sync(cfg: dict, state: dict, command_text: str) -> dict | None:
    return asyncio.run(run_command(cfg, state, command_text))


def run_jira_comment_sync(ticket_key: str, comment_text: str) -> bool:
    return asyncio.run(run_jira_comment(ticket_key, comment_text))
