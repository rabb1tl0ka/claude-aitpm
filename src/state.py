"""State file manager — persists channel ID, pending drafts, ticket states."""

import json
import os
from datetime import datetime, timezone, timedelta


def _state_path(project_dir: str) -> str:
    return os.path.join(project_dir, "state", "state.json")


def load_state(project_dir: str) -> dict:
    path = _state_path(project_dir)
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return {
        "channel_id": None,
        "last_monitor_run": None,
        "last_digest_date": None,
        "last_inbound_check": None,
        "pending_drafts": [],
        "ticket_states": {},
        "slack_cursors": {},
        "user_map": {
            "Zoran Grbusic": "5bb78e559ba2930990f81b6b",
            "elena.gramatikovska": "633846019b32cfef93282f21",
            "João Vasconcelos": "609a692b75e875006f844c26",
            "João Pedro Fontes": "712020:cbf0ae72-986d-4cc4-91c4-a416a628c1c2",
            "luis.carvalho": "712020:3a1973e4-b239-47cc-82de-eb0a133905c2",
            "Gorjan Ivanovski": "712020:e7af773c-0e40-4844-9a8c-108092b90668",
            "gabriel.menezes": "712020:8568448e-64d2-4e63-94b7-852f211eb2e7",
            "Kristina Bazgaloska": "5dd2d73ba20e0c0e9ef6bc80",
            "Tamara Ilieva": "712020:73ee629b-b828-4156-a803-32502e903a14",
            "Daniela Ilieva": "5ff45f9a91bb2e0108d26eea",
            "Aleksandar Nedelkovski": "712020:6ec7761c-fe9f-417a-a200-d6ca0a0a264f",
        },
    }


def save_state(project_dir: str, state: dict) -> None:
    path = _state_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def get_slack_oldest(state: dict, channel_id: str) -> str:
    """Return the Slack timestamp to read from. Defaults to 14 days ago on first run."""
    cursors = state.get("slack_cursors", {})
    if channel_id in cursors:
        return cursors[channel_id]
    oldest = datetime.now(timezone.utc) - timedelta(days=14)
    return str(oldest.timestamp())


def update_slack_cursors(state: dict, updates: dict) -> None:
    """Merge new channel cursor timestamps into state."""
    state.setdefault("slack_cursors", {}).update(updates)


def _epic_cache_path(project_dir: str) -> str:
    return os.path.join(project_dir, "state", "epic_cache.json")


def load_epic_cache(project_dir: str) -> list | None:
    """Return cached epic keys, or None if no cache exists."""
    path = _epic_cache_path(project_dir)
    if os.path.isfile(path):
        with open(path) as f:
            data = json.load(f)
        return data.get("epic_keys")
    return None


def save_epic_cache(project_dir: str, epic_keys: list) -> None:
    path = _epic_cache_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"epic_keys": epic_keys, "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, f, indent=2)
