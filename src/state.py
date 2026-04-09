"""State file manager — persists channel ID, pending drafts, ticket states."""

import base64
import json
import os
import re
import urllib.request
from datetime import date, datetime, timezone, timedelta


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


def _parse_step1_jql(radar_path: str) -> str:
    """Extract the Step 1 JQL from the radar markdown file."""
    expanded = os.path.expanduser(radar_path)
    with open(expanded) as f:
        content = f.read()
    # Find the Step 1 section and grab the first fenced code block in it
    step1_match = re.search(r"## Step 1.*?```\n(.+?)```", content, re.DOTALL)
    if not step1_match:
        raise ValueError(f"Could not find Step 1 JQL in radar file: {expanded}")
    return step1_match.group(1).strip()


def _business_days_since(dt_str: str | None) -> int:
    if not dt_str:
        return 0
    try:
        updated = datetime.fromisoformat(dt_str).date()
        today = date.today()
        days = 0
        current = updated
        while current < today:
            if current.weekday() < 5:
                days += 1
            current += timedelta(days=1)
        return days
    except Exception:
        return 0


def fetch_epic_keys(cfg: dict, project_dir: str) -> list:
    """Fetch epic keys from Jira using Step 1 JQL from the radar file. Saves to cache."""
    jql = _parse_step1_jql(cfg["jira_radar_file"])
    email = os.environ["ATLASSIAN_EMAIL"]
    token = os.environ["ATLASSIAN_API_TOKEN"]
    site = os.environ["ATLASSIAN_SITE"]

    payload = json.dumps({"jql": jql, "fields": ["key"], "maxResults": 100}).encode()
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"https://{site}/rest/api/3/search/jql",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)

    keys = [issue["key"] for issue in data["issues"]]
    save_epic_cache(project_dir, keys)
    return keys


def fetch_child_tickets(epic_keys: list, last_run: str | None = None, is_full_fetch: bool = True) -> list:
    """Fetch child tickets for the given epic keys from Jira REST API.

    Full fetch: all non-Done tickets under the epics.
    Incremental: only tickets updated since last_run.
    """
    keys_str = ", ".join(epic_keys)
    jql = f'watcher = currentUser() AND "Epic Link" in ({keys_str}) AND statusCategory != Done'
    if not is_full_fetch and last_run and last_run != "never":
        jql += f' AND updated >= "{last_run}"'

    email = os.environ["ATLASSIAN_EMAIL"]
    token = os.environ["ATLASSIAN_API_TOKEN"]
    site = os.environ["ATLASSIAN_SITE"]

    payload = json.dumps({
        "jql": jql,
        "fields": ["key", "summary", "status", "assignee", "updated", "priority", "issuelinks", "customfield_10020"],
        "maxResults": 200,
    }).encode()
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"https://{site}/rest/api/3/search/jql",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)

    tickets = []
    for issue in data["issues"]:
        f = issue["fields"]
        assignee = f.get("assignee") or {}
        sprints = f.get("customfield_10020") or []
        links = f.get("issuelinks") or []
        tickets.append({
            "key": issue["key"],
            "summary": f.get("summary"),
            "status": (f.get("status") or {}).get("name"),
            "assignee": assignee.get("displayName"),
            "assignee_id": assignee.get("accountId"),
            "updated": f.get("updated"),
            "priority": (f.get("priority") or {}).get("name"),
            "sprint_state": "active" if any(s.get("state") == "active" for s in sprints) else "none",
            "business_days_stale": _business_days_since(f.get("updated")),
            "blockers": [
                lnk["inwardIssue"]["key"] for lnk in links
                if lnk.get("type", {}).get("inward") == "is blocked by" and "inwardIssue" in lnk
            ],
        })
    return tickets
