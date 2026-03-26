"""Slack client — all Slack I/O via slack_sdk. No MCP dependency."""

import logging
import os

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

log = logging.getLogger("aitpm")

APPROVAL_PHRASES = {"send that", "good to go", "send", "approved", "approve", "✓", "👍", "lgtm"}
AITPM_TRIGGER = "@aitpm"

_channel_id_cache: dict[str, str] = {}
_bot_user_id: str | None = None


def get_client() -> WebClient:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise ValueError("SLACK_BOT_TOKEN not set in environment")
    return WebClient(token=token)


def resolve_channel(channel: str) -> str:
    """Resolve channel name to ID, with cache. Accepts name or ID."""
    if channel.startswith("C") and len(channel) > 8:
        return channel  # already an ID
    name = channel.lstrip("#")
    if name in _channel_id_cache:
        return _channel_id_cache[name]
    client = get_client()
    for channel_type in ["public_channel", "private_channel"]:
        resp = client.conversations_list(types=channel_type, limit=200, exclude_archived=True)
        for ch in resp.get("channels", []):
            if ch["name"] == name:
                _channel_id_cache[name] = ch["id"]
                return ch["id"]
    raise ValueError(f"Channel not found: {channel}")


def post_message(channel: str, text: str, thread_ts: str = None) -> str:
    """Post a message. Returns message ts."""
    channel_id = resolve_channel(channel)
    client = get_client()
    kwargs = {"channel": channel_id, "text": text}
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    resp = client.chat_postMessage(**kwargs)
    log.info(f"[slack] Posted to {channel} (ts={resp['ts']})")
    return resp["ts"]


def add_reaction(channel: str, ts: str, emoji: str = "white_check_mark") -> None:
    channel_id = resolve_channel(channel)
    client = get_client()
    try:
        client.reactions_add(channel=channel_id, timestamp=ts, name=emoji)
    except SlackApiError as e:
        if e.response["error"] != "already_reacted":
            log.warning(f"[slack] reaction error: {e.response['error']}")


def get_bot_user_id() -> str:
    """Return the bot's own Slack user ID (cached)."""
    global _bot_user_id
    if not _bot_user_id:
        resp = get_client().auth_test()
        _bot_user_id = resp["user_id"]
        log.info(f"[slack] Bot user ID: {_bot_user_id}")
    return _bot_user_id


def is_bot_mention(text: str) -> bool:
    """Check if the message mentions this bot."""
    return f"<@{get_bot_user_id()}>" in text


def get_channel_history(channel: str, oldest: str = None, limit: int = 20) -> list:
    channel_id = resolve_channel(channel)
    client = get_client()
    kwargs = {"channel": channel_id, "limit": limit}
    if oldest:
        kwargs["oldest"] = oldest
    resp = client.conversations_history(**kwargs)
    return resp.get("messages", [])


def get_thread_replies(channel: str, thread_ts: str) -> list:
    """Returns all messages in a thread (first msg is the parent)."""
    channel_id = resolve_channel(channel)
    client = get_client()
    resp = client.conversations_replies(channel=channel_id, ts=thread_ts)
    return resp.get("messages", [])


def get_message_reactions(channel: str, ts: str) -> list:
    """Returns reactions on a message."""
    channel_id = resolve_channel(channel)
    client = get_client()
    try:
        resp = client.reactions_get(channel=channel_id, timestamp=ts)
        return resp.get("message", {}).get("reactions", [])
    except SlackApiError as e:
        log.warning(f"[slack] reactions_get error: {e.response['error']}")
        return []


def is_bot_message(msg: dict) -> bool:
    return bool(msg.get("bot_id") or msg.get("subtype") == "bot_message")


_QUESTION_SIGNALS = {"?", "what", "why", "how", "suggest", "recommend", "should", "think", "opinion", "advice"}


def detect_intent(text: str) -> str:
    """Classify Bruno's reply: 'approve', 'command', 'question', 'edit', or 'none'."""
    lower = text.lower().strip()
    if not lower:
        return "none"
    if any(phrase in lower for phrase in APPROVAL_PHRASES):
        return "approve"
    if lower.startswith("<@"):  # explicit bot mention in a thread = new command
        return "command"
    if "?" in lower or any(word in lower.split() for word in _QUESTION_SIGNALS):
        return "question"
    return "edit"
