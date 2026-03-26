"""State file manager — persists channel ID, pending drafts, ticket states."""

import json
import os


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
    }


def save_state(project_dir: str, state: dict) -> None:
    path = _state_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
