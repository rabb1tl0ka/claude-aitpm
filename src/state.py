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
