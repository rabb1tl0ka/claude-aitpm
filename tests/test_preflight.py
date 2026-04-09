#!/usr/bin/env python3
"""Preflight test — validates the Python data-fetch pipeline before any agent call.

Tests:
  1. Epic keys: load from cache OR fetch fresh from Jira
  2. Child tickets: fetch from Jira using the epic keys

Usage:
    python3 tests/test_preflight.py                  # use cache if available
    python3 tests/test_preflight.py --refresh-cache  # force fresh epic fetch
    python3 tests/test_preflight.py --incremental    # simulate incremental child fetch
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.state import load_epic_cache, fetch_epic_keys, fetch_child_tickets

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "cloudsort.yaml")
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict:
    import yaml  # type: ignore
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-cache", action="store_true", help="Force fresh epic fetch, ignore cache")
    parser.add_argument("--incremental", action="store_true", help="Simulate incremental child fetch (uses last_monitor_run from state)")
    args = parser.parse_args()

    try:
        cfg = load_config()
    except Exception as e:
        print(f"FAIL  Config load: {e}")
        sys.exit(1)
    print(f"OK    Config loaded: {cfg['project_name']}")

    # --- Step 1: Epic keys ---
    print("\n--- Step 1: Epic keys ---")
    epic_keys = None if args.refresh_cache else load_epic_cache(PROJECT_DIR)
    if epic_keys and not args.refresh_cache:
        print(f"OK    Cache hit: {len(epic_keys)} epic keys")
    else:
        reason = "--refresh-cache" if args.refresh_cache else "no cache"
        print(f"      Cache miss ({reason}), fetching from Jira...")
        try:
            epic_keys = fetch_epic_keys(cfg, PROJECT_DIR)
            print(f"OK    Fetched {len(epic_keys)} epic keys from Jira, cache saved")
        except Exception as e:
            print(f"FAIL  Epic fetch: {e}")
            sys.exit(1)

    print(f"      Keys: {', '.join(epic_keys)}")

    # --- Step 2: Child tickets ---
    print("\n--- Step 2: Child tickets ---")
    last_run = None
    is_full_fetch = True
    if args.incremental:
        state_path = os.path.join(PROJECT_DIR, "state", "state.json")
        if os.path.isfile(state_path):
            with open(state_path) as f:
                state = json.load(f)
            last_run = state.get("last_monitor_run")
            is_full_fetch = last_run is None
        print(f"      Mode: {'FULL (no last_run in state)' if is_full_fetch else f'INCREMENTAL since {last_run}'}")
    else:
        print(f"      Mode: FULL")

    try:
        tickets = fetch_child_tickets(epic_keys, last_run=last_run, is_full_fetch=is_full_fetch)
    except Exception as e:
        print(f"FAIL  Child ticket fetch: {e}")
        sys.exit(1)

    print(f"OK    Fetched {len(tickets)} child tickets")

    # Breakdown by status
    from collections import Counter
    statuses = Counter(t["status"] for t in tickets)
    for status, count in sorted(statuses.items(), key=lambda x: -x[1]):
        print(f"      {count:3d}  {status}")

    # Stale tickets (business_days_stale > 0 and unassigned or stale)
    stale = [t for t in tickets if t.get("business_days_stale", 0) >= 2]
    print(f"\n      Stale (>=2 business days): {len(stale)}")
    for t in sorted(stale, key=lambda x: -x.get("business_days_stale", 0))[:5]:
        print(f"      {t['key']}  {t['business_days_stale']}d  {t.get('assignee') or 'unassigned'}  {t.get('summary','')[:60]}")

    print("\nAll preflight checks passed.")


if __name__ == "__main__":
    main()
