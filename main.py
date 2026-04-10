#!/usr/bin/env python3
"""Claude AITPM — AI Technical Project Manager.

Usage:
    python3 main.py                      # Run scheduler (long-running)
    python3 main.py --config cloudsort   # Specify config (default: cloudsort)
    python3 main.py --once monitor       # Run hourly monitor once and exit
    python3 main.py --once digest        # Run 8AM digest once and exit
    python3 main.py --once poll          # Run approval poll + inbound check once and exit
"""

import argparse
import json
import logging
import os
import time
import uuid
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo  # kept for digest date tracking

from dotenv import load_dotenv

load_dotenv()

from src.config import load_config, get_project_dir
from src.state import load_state, save_state, update_slack_cursors, load_epic_cache, save_epic_cache, fetch_epic_keys, fetch_child_tickets, tickets_to_states
from src.agents import run_monitor_sync, run_nudge_drafter_sync, run_revision_sync, run_command_sync, run_jira_comment_sync
from src.slack_client import (
    post_message, add_reaction, get_channel_history,
    get_thread_replies, get_message_reactions, is_bot_message, is_bot_mention, detect_intent,
    resolve_channel,
)

LISBON_TZ = ZoneInfo("Europe/Lisbon")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging() -> logging.Logger:
    log_dir = os.path.join(get_project_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    logger = logging.getLogger("aitpm")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(os.path.join(log_dir, f"{ts}_aitpm.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ---------------------------------------------------------------------------
# Monitor: run agent → read output → post drafts to Slack
# ---------------------------------------------------------------------------

def run_monitor(cfg: dict, state: dict, run_type: str, log: logging.Logger, refresh_cache: bool = False) -> None:
    project_dir = get_project_dir()
    output_file = os.path.join(project_dir, "state", "monitor_output.json")

    # Resolve epic keys — Python fetches if no cache or refresh forced
    epic_cache = None if refresh_cache else load_epic_cache(project_dir)
    if epic_cache:
        log.info(f"[monitor] Epic cache hit: {len(epic_cache)} epics.")
    else:
        reason = "--refresh-cache" if refresh_cache else "no cache"
        log.info(f"[monitor] Epic cache miss ({reason}). Fetching from Jira...")
        epic_cache = fetch_epic_keys(cfg, project_dir)
        log.info(f"[monitor] Fetched {len(epic_cache)} epic keys from Jira, cache saved.")

    is_full_fetch = run_type == "digest" or refresh_cache or state.get("last_monitor_run") is None
    log.info(f"[monitor] Fetch mode: {'FULL' if is_full_fetch else 'INCREMENTAL'}")

    # Fetch child tickets — deterministic Python, not LLM
    child_tickets = fetch_child_tickets(epic_cache, last_run=state.get("last_monitor_run"), is_full_fetch=is_full_fetch)
    log.info(f"[monitor] Fetched {len(child_tickets)} child tickets.")

    # Build ticket_states from fetch data — Python owns this, not the agent
    fresh_states = tickets_to_states(child_tickets)
    if is_full_fetch:
        state["ticket_states"] = fresh_states
        log.info(f"[monitor] ticket_states replaced: {len(fresh_states)} tickets (full fetch)")
    else:
        existing = state.get("ticket_states", {})
        state["ticket_states"] = {**existing, **fresh_states}
        log.info(f"[monitor] ticket_states merged: {len(fresh_states)} fresh + {len(existing) - len(set(existing) & set(fresh_states))} preserved = {len(state['ticket_states'])} total")

    # Clean up previous output
    if os.path.isfile(output_file):
        os.remove(output_file)

    run_monitor_sync(cfg, state, run_type, epic_cache=epic_cache, child_tickets=child_tickets, is_full_fetch=is_full_fetch)

    if not os.path.isfile(output_file):
        log.warning(f"[monitor] Agent finished but no output file found.")
        return

    with open(output_file) as f:
        output = json.load(f)
    os.remove(output_file)

    # Phase 2: nudge drafter — only runs when stale tickets exist
    pending_nudges = output.get("pending_nudges", [])
    if pending_nudges:
        nudge_output_file = os.path.join(project_dir, "state", "nudge_output.json")
        if os.path.isfile(nudge_output_file):
            os.remove(nudge_output_file)
        run_nudge_drafter_sync(cfg, state, pending_nudges)
        if os.path.isfile(nudge_output_file):
            with open(nudge_output_file) as f:
                nudge_output = json.load(f)
            os.remove(nudge_output_file)
            output.setdefault("posts", []).extend(nudge_output.get("posts", []))
            new_cursors = nudge_output.get("slack_cursors", {})
            if new_cursors:
                update_slack_cursors(state, new_cursors)
                log.info(f"[monitor] Slack cursors updated for {len(new_cursors)} channel(s).")
        else:
            log.warning("[monitor] Nudge drafter finished but no output file found.")

    aitpm_channel = cfg["slack_aitpm_channel"]
    channel_id = resolve_channel(aitpm_channel)


    # Merge any newly discovered users into the user map
    new_users = output.get("user_map", {})
    if new_users:
        state.setdefault("user_map", {}).update(new_users)
    state["last_monitor_run"] = output.get("run_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    state["channel_id"] = channel_id

    # Post to #cloudsort_aitpm
    posts = output.get("posts", output.get("drafts", []))  # fallback for old key name
    if not posts:
        log.info("[monitor] Nothing to post.")
    for post in posts:
        text = post.get("text", "").strip()
        if not text:
            continue
        post_type = post.get("type", "alert")
        target = post.get("target_channel")

        action = post.get("action", "slack")
        ticket_key = post.get("ticket_key")

        if post_type == "draft":
            if action == "jira_comment":
                full_text = f"{text}\n\n_Approve to post as JIRA comment on {ticket_key} — reply \"send that\" or edit._"
            elif target:
                full_text = f"{text}\n\n_Approve to send to {target} — reply \"send that\" or edit._"
            else:
                full_text = text
        else:
            # Pure alert — no footer, no action needed
            full_text = text

        ts = post_message(aitpm_channel, full_text)

        entry = {
            "id": str(uuid.uuid4()),
            "slack_ts": ts,
            "channel_id": channel_id,
            "draft_text": text,
            "action": action,
            "ticket_key": ticket_key,
            "target_channel": target if post_type == "draft" else None,
            "context": post.get("context", ""),
            "posted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": post_type,
            "status": "pending",
            "last_reply_ts": None,
        }
        state.setdefault("pending_drafts", []).append(entry)
        log.info(f"[monitor] {post_type.capitalize()} posted: {post.get('context', text[:50])}")

    save_state(project_dir, state)


# ---------------------------------------------------------------------------
# Approval poll: check threads for the TPM's replies
# ---------------------------------------------------------------------------

def run_approval_poll(cfg: dict, state: dict, log: logging.Logger) -> None:
    pending = state.get("pending_drafts", [])
    if not pending:
        log.debug("[poll] No pending drafts.")
        return

    project_dir = get_project_dir()
    aitpm_channel = cfg["slack_aitpm_channel"]
    changed = False

    for draft in pending:
        if draft.get("status") == "sent":
            continue
        slack_ts = draft.get("slack_ts")
        if not slack_ts:
            continue

        # Check for ✅ reaction approval first
        tpm_id = cfg.get("tpm_slack_user_id", "")
        reactions = get_message_reactions(aitpm_channel, slack_ts)
        reacted_approve = any(
            r["name"] == "white_check_mark" and (not tpm_id or tpm_id in r.get("users", []))
            for r in reactions
        )
        if reacted_approve and draft.get("status") != "sent":
            log.info(f"[poll] Reaction approval detected for: {draft.get('context', slack_ts)}")
            action = draft.get("action", "slack")
            target = draft.get("target_channel")
            if action == "jira_comment":
                ticket_key = draft.get("ticket_key")
                comment_text = draft["draft_text"]
                if "Proposed comment:" in comment_text:
                    comment_text = comment_text.split("Proposed comment:")[-1].strip()
                success = run_jira_comment_sync(ticket_key, comment_text, state.get("user_map"))
                if success:
                    post_message(aitpm_channel, f"✅ Comment posted on {ticket_key}", thread_ts=slack_ts)
                else:
                    post_message(aitpm_channel, f"⚠️ Failed to post comment on {ticket_key}", thread_ts=slack_ts)
            elif target:
                post_message(target, draft["draft_text"])
                post_message(aitpm_channel, f"✅ Sent to {target}", thread_ts=slack_ts)
            else:
                post_message(aitpm_channel, "✅ Noted.", thread_ts=slack_ts)
            add_reaction(aitpm_channel, slack_ts)
            draft["status"] = "sent"
            changed = True
            continue

        replies = get_thread_replies(aitpm_channel, slack_ts)
        # Skip parent message (index 0), look at TPM's replies only
        tpm_replies = [r for r in replies[1:] if not is_bot_message(r)]
        if not tpm_replies:
            continue

        # Only process new replies from the owner
        tpm_id = cfg.get("tpm_slack_user_id", "")
        if tpm_id:
            tpm_replies = [r for r in tpm_replies if r.get("user") == tpm_id]
        last_seen = draft.get("last_reply_ts") or "0"
        new_replies = [r for r in tpm_replies if r.get("ts", "0") > last_seen]
        if not new_replies:
            continue

        latest_reply = new_replies[-1]
        reply_text = latest_reply.get("text", "")
        intent = detect_intent(reply_text)

        post_type = draft.get("type", "draft")

        # Alert replies are always treated as commands regardless of phrasing
        if post_type == "alert":
            log.info(f"[poll] Alert reply detected: {reply_text[:80]}")
            context = f"Context: {draft.get('context', '')}\n\nOriginal alert:\n{draft['draft_text']}"
            result = run_command_sync(cfg, state, f"{reply_text}\n\n{context}")
            if result and result.get("response"):
                post_message(aitpm_channel, result["response"], thread_ts=slack_ts)
            draft["last_reply_ts"] = latest_reply.get("ts")
            changed = True

        elif intent == "approve":
            action = draft.get("action", "slack")
            target = draft.get("target_channel")
            if action == "jira_comment":
                ticket_key = draft.get("ticket_key")
                # Extract the actual comment text — strip the header block the TPM saw
                comment_text = draft["draft_text"]
                if "Proposed comment:" in comment_text:
                    comment_text = comment_text.split("Proposed comment:")[-1].strip()
                success = run_jira_comment_sync(ticket_key, comment_text, state.get("user_map"))
                if success:
                    post_message(aitpm_channel, f"✅ Comment posted on {ticket_key}", thread_ts=slack_ts)
                else:
                    post_message(aitpm_channel, f"⚠️ Failed to post comment on {ticket_key}", thread_ts=slack_ts)
            elif target:
                post_message(target, draft["draft_text"])
                post_message(aitpm_channel, f"✅ Sent to {target}", thread_ts=slack_ts)
            else:
                post_message(aitpm_channel, "✅ Noted.", thread_ts=slack_ts)
            add_reaction(aitpm_channel, slack_ts)
            draft["status"] = "sent"
            log.info(f"[poll] Draft approved and sent: {draft.get('context', slack_ts)}")
            changed = True

        elif intent in ("command", "question"):
            log.info(f"[poll] {intent.capitalize()} detected: {reply_text[:80]}")
            context = f"Context: {draft.get('context', '')}\n\nOriginal draft:\n{draft['draft_text']}"
            result = run_command_sync(cfg, state, f"{reply_text}\n\n{context}")
            if result and result.get("response"):
                post_message(aitpm_channel, result["response"], thread_ts=slack_ts)
                draft["last_reply_ts"] = latest_reply.get("ts")
                log.info(f"[poll] {intent.capitalize()} handled in thread.")
            changed = True

        elif intent == "edit":
            log.info(f"[poll] Edit request detected: {reply_text[:80]}")
            revised = run_revision_sync(cfg, draft["draft_text"], reply_text, draft.get("context", ""))
            if revised:
                post_message(aitpm_channel, f"Revised draft:\n\n{revised}", thread_ts=slack_ts)
                draft["draft_text"] = revised
                draft["last_reply_ts"] = latest_reply.get("ts")
                log.info(f"[poll] Revision posted.")
            else:
                log.warning("[poll] Revision agent returned no output.")
            changed = True

    if changed:
        # Remove sent drafts
        state["pending_drafts"] = [d for d in pending if d.get("status") != "sent"]
        save_state(project_dir, state)


# ---------------------------------------------------------------------------
# Inbound check: scan #cloudsort_aitpm for @aitpm commands
# ---------------------------------------------------------------------------

def run_inbound_check(cfg: dict, state: dict, log: logging.Logger) -> None:
    project_dir = get_project_dir()
    aitpm_channel = cfg["slack_aitpm_channel"]
    last_check = state.get("last_inbound_check")

    now_ts = str(datetime.now(timezone.utc).timestamp())
    state["last_inbound_check"] = now_ts
    save_state(project_dir, state)

    messages = get_channel_history(aitpm_channel, oldest=last_check, limit=20)

    # Find top-level messages from the owner that mention the bot
    tpm_id = cfg.get("tpm_slack_user_id", "")
    commands = [
        m for m in messages
        if not is_bot_message(m)
        and (not tpm_id or m.get("user") == tpm_id)
        and (not m.get("thread_ts") or m.get("thread_ts") == m.get("ts"))  # top-level only
        and is_bot_mention(m.get("text", ""))
    ]

    if not commands:
        log.debug("[inbound] No @aitpm commands found.")
        return

    channel_id = resolve_channel(aitpm_channel)

    for msg in commands:
        command_text = msg["text"]
        msg_ts = msg["ts"]
        log.info(f"[inbound] Command: {command_text[:80]}")

        result = run_command_sync(cfg, state, command_text)
        if not result:
            post_message(aitpm_channel, "I ran into an issue processing that. Try again.", thread_ts=msg_ts)
            continue

        # Reply in thread with the response
        response = result.get("response", "Done.")
        post_message(aitpm_channel, response, thread_ts=msg_ts)

        # If agent also wants to draft a team message, add it as a pending draft
        team_draft = result.get("draft_for_team")
        if team_draft:
            draft_ts = post_message(aitpm_channel, f"Draft for your review:\n\n{team_draft}")
            state.setdefault("pending_drafts", []).append({
                "id": str(uuid.uuid4()),
                "slack_ts": draft_ts,
                "channel_id": channel_id,
                "draft_text": team_draft,
                "target_channel": result.get("draft_target_channel"),
                "context": f"From command: {command_text[:60]}",
                "posted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "pending",
                "last_reply_ts": None,
            })
            save_state(project_dir, state)


# ---------------------------------------------------------------------------
# Schedule helpers
# ---------------------------------------------------------------------------

def is_work_hours(now: datetime, cfg: dict) -> bool:
    schedule = cfg.get("schedule", {})
    start = schedule.get("work_hours_start", 8)
    end = schedule.get("work_hours_end", 21)
    return now.weekday() < 5 and start <= now.hour < end


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Claude AITPM")
    parser.add_argument("--config", default="cloudsort", help="Config name (default: cloudsort)")
    parser.add_argument(
        "--once",
        choices=["monitor", "digest", "poll"],
        help="Run once and exit",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        default=False,
        help="Force re-fetch of epic keys and full ticket fetch, ignoring cache",
    )
    args = parser.parse_args()

    log = setup_logging()
    cfg = load_config(args.config)
    project_dir = get_project_dir()

    log.info(f"=== Claude AITPM — {cfg['project_name']} ===")

    if args.once:
        state = load_state(project_dir)
        if args.once == "poll":
            run_approval_poll(cfg, state, log)
            run_inbound_check(cfg, state, log)
        else:
            run_monitor(cfg, state, run_type=args.once, log=log, refresh_cache=args.refresh_cache)
        log.info("Done.")
        return

    tz = ZoneInfo(cfg.get("schedule", {}).get("timezone", "Europe/Lisbon"))
    monitor_interval_min = cfg.get("schedule", {}).get("monitor_interval_min", 60)
    approval_interval_min = cfg.get("schedule", {}).get("approval_interval_min", 3)

    last_monitor_run: datetime | None = None
    last_poll_run: datetime | None = None
    last_digest_date: date | None = None

    log.info(f"Monitor: every {monitor_interval_min} min | Poll: every {approval_interval_min} min")
    log.info("Running. Press Ctrl+C to stop.")

    try:
        while True:
            now = datetime.now(tz)
            state = load_state(project_dir)

            # 8AM digest
            if now.hour == 8 and last_digest_date != now.date():
                log.info("Running 8AM digest...")
                run_monitor(cfg, state, run_type="digest", log=log)
                last_digest_date = now.date()
                last_monitor_run = now

            # Hourly monitor
            elif last_monitor_run is None or (
                (now - last_monitor_run).total_seconds() >= monitor_interval_min * 60
            ):
                log.info("Running hourly monitor...")
                run_monitor(cfg, state, run_type="monitor", log=log, refresh_cache=args.refresh_cache)
                last_monitor_run = now

            # Approval poll + inbound check
            if last_poll_run is None or (
                (now - last_poll_run).total_seconds() >= approval_interval_min * 60
            ):
                log.info(f"[poll] Running at {now.strftime('%H:%M:%S')}...")
                run_approval_poll(cfg, state, log)
                run_inbound_check(cfg, state, log)
                last_poll_run = now

            time.sleep(30)

    except KeyboardInterrupt:
        log.info("AITPM stopped.")


if __name__ == "__main__":
    main()
