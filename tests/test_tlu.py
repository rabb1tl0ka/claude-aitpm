#!/usr/bin/env python3
"""Unit tests for TLU utilities — pure Python, no API calls, no agents.

All tests use synthetic data from tests/fixtures/.
Run with: python3 tests/test_tlu.py

Uses synthetic data that matches the schema of real Jira and Notion responses.
No live API calls are made — this avoids burning tokens and keeps tests deterministic.
"""

import json
import os
import sys
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tlu import (
    detect_tlu_intent,
    parse_week,
    is_state_fresh,
    discover_meeting_notes,
    tlu_local_path,
    extract_tlu_section,
    next_pending_section,
)
from src.config import get_project_notes_path, parse_notion_page_id

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
MEETING_NOTES_DIR = os.path.join(FIXTURES, "tlu_meeting_notes")
SAMPLE_TLU = os.path.join(FIXTURES, "tlu_sample.md")


def ok(label):
    print(f"OK  {label}")


def fail(label, detail=""):
    print(f"FAIL  {label}: {detail}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 1. Notion URL parsing
# ---------------------------------------------------------------------------
def test_notion_url_parsing():
    cases = [
        ("https://www.notion.so/loka/Apr-13-33f46e8c24378185934bca03f02c0369",
         "33f46e8c24378185934bca03f02c0369"),
        ("https://www.notion.so/loka/Mar-06-abc123def456abc123def456abc12345",
         "abc123def456abc123def456abc12345"),
        ("https://www.notion.so/33f46e8c-2437-8185-934b-ca03f02c0369",
         "33f46e8c24378185934bca03f02c0369"),
        ("https://www.notion.so/", None),
    ]
    for url, expected in cases:
        result = parse_notion_page_id(url)
        if result != expected:
            fail("notion_url_parsing", f"url={url!r} → got {result!r}, expected {expected!r}")
    ok("notion_url_parsing")


# ---------------------------------------------------------------------------
# 2. Config helpers
# ---------------------------------------------------------------------------
def test_config_helpers():
    cfg = {"project_notes_path": "~/loka/vaults/test"}
    result = get_project_notes_path(cfg)
    if not result.startswith("/"):
        fail("get_project_notes_path", f"Expected absolute path, got {result!r}")
    if not result.endswith("loka/vaults/test"):
        fail("get_project_notes_path", f"Wrong path: {result!r}")
    ok("get_project_notes_path expands ~")

    assert get_project_notes_path({}) is None
    ok("get_project_notes_path returns None when not set")


# ---------------------------------------------------------------------------
# 3. TLU intent detection
# ---------------------------------------------------------------------------
def test_detect_tlu_intent():
    positives = [
        "generate TLU for last week",
        "draft the traffic light update for Apr 7",
        "hey can you create the weekly status report",
        "TLU please",
        "generate traffic-light update",
    ]
    negatives = [
        "what's blocking CLOUD-100",
        "add a comment to CLOUD-101",
        "summarize sprint 161",
    ]
    for text in positives:
        if not detect_tlu_intent(text):
            fail("detect_tlu_intent", f"Should detect TLU intent in: {text!r}")
    for text in negatives:
        if detect_tlu_intent(text):
            fail("detect_tlu_intent", f"Should NOT detect TLU intent in: {text!r}")
    ok("detect_tlu_intent")


# ---------------------------------------------------------------------------
# 4. Week parsing
# ---------------------------------------------------------------------------
def test_parse_week():
    today = date(2026, 4, 13)  # Monday

    # "last week" from a Monday → previous Mon-Fri
    start, end = parse_week("generate TLU for last week", today=today)
    assert start == date(2026, 4, 6), f"Got start={start}"
    assert end == date(2026, 4, 10), f"Got end={end}"
    ok(f"parse_week 'last week' from Monday: {start} to {end}")

    # ISO date
    start, end = parse_week("draft TLU for 2026-04-07", today=today)
    assert start == date(2026, 4, 6), f"Got start={start}"
    assert end == date(2026, 4, 10), f"Got end={end}"
    ok(f"parse_week ISO date 2026-04-07: {start} to {end}")

    # Month name
    start, end = parse_week("generate the TLU for Apr 7", today=today)
    assert start == date(2026, 4, 6), f"Got start={start}"
    assert end == date(2026, 4, 10), f"Got end={end}"
    ok(f"parse_week 'Apr 7': {start} to {end}")

    # No date in command → fall back to last completed week
    start, end = parse_week("generate TLU", today=today)
    assert start == date(2026, 4, 6), f"Got start={start}"
    assert end == date(2026, 4, 10), f"Got end={end}"
    ok(f"parse_week fallback (no date): {start} to {end}")


# ---------------------------------------------------------------------------
# 5. State freshness
# ---------------------------------------------------------------------------
def test_state_freshness():
    now = datetime.now(timezone.utc)

    # Fresh: 1h ago
    fresh_state = {"last_monitor_run": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert is_state_fresh(fresh_state), "Should be fresh (1h ago)"
    ok("is_state_fresh: True for 1h-old state")

    # Stale: 25h ago
    stale_state = {"last_monitor_run": (now - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert not is_state_fresh(stale_state), "Should be stale (25h ago)"
    ok("is_state_fresh: False for 25h-old state")

    # No last_monitor_run
    assert not is_state_fresh({}), "Should be stale (no last_monitor_run)"
    ok("is_state_fresh: False for empty state")


# ---------------------------------------------------------------------------
# 6. Meeting note discovery
# ---------------------------------------------------------------------------
def test_meeting_note_discovery():
    # Build a fake notes_dir structure pointing at our fixtures
    # discover_meeting_notes looks for {notes_dir}/meeting-notes/
    notes_dir = FIXTURES
    # We have:
    #   tlu_meeting_notes/jb-working-session-20260407.md  → Apr 7 ✓
    #   tlu_meeting_notes/payments-sync-2026-04-09.md     → Apr 9 ✓
    #   tlu_meeting_notes/fatih-1on1-20260320.md          → Mar 20 ✗
    #   tlu_meeting_notes/inbox.md                         → no date ✗
    #
    # BUT discover_meeting_notes looks for {notes_dir}/meeting-notes/
    # Our fixtures dir has tlu_meeting_notes/, not meeting-notes/
    # So we use a tmp symlink approach — or just point notes_dir one level up.
    # Simpler: create a meeting-notes subdir in fixtures pointing at our files.

    import tempfile, shutil
    with tempfile.TemporaryDirectory() as tmpdir:
        mn_dir = os.path.join(tmpdir, "meeting-notes")
        os.makedirs(mn_dir)
        for fname in os.listdir(MEETING_NOTES_DIR):
            shutil.copy(os.path.join(MEETING_NOTES_DIR, fname), os.path.join(mn_dir, fname))

        week_start = date(2026, 4, 6)   # Monday
        week_end   = date(2026, 4, 10)  # Friday

        found = discover_meeting_notes(tmpdir, week_start, week_end)
        fnames = [os.path.basename(f) for f in found]

        assert "jb-working-session-20260407.md" in fnames, f"Missing Apr 7 file. Got: {fnames}"
        assert "payments-sync-2026-04-09.md" in fnames, f"Missing Apr 9 file. Got: {fnames}"
        assert "fatih-1on1-20260320.md" not in fnames, f"Mar 20 file should be excluded. Got: {fnames}"
        assert "inbox.md" not in fnames, f"Undated file should be excluded. Got: {fnames}"
        ok(f"discover_meeting_notes: found {len(found)} file(s) for Apr 6-10: {fnames}")

    # Non-existent dir returns empty list
    result = discover_meeting_notes("/nonexistent/path", week_start, week_end)
    assert result == [], f"Expected [], got {result}"
    ok("discover_meeting_notes: empty list for non-existent dir")


# ---------------------------------------------------------------------------
# 7. TLU local path
# ---------------------------------------------------------------------------
def test_tlu_local_path():
    path = tlu_local_path("/some/vault", date(2026, 4, 10))
    assert path == "/some/vault/traffic-lights/2026-04-10-tlu.md", f"Got: {path}"
    ok(f"tlu_local_path: {path}")


# ---------------------------------------------------------------------------
# 8. Section extraction from local TLU file
# ---------------------------------------------------------------------------
def test_extract_tlu_section():
    content = extract_tlu_section(SAMPLE_TLU, "where_we_are")
    assert "Sprint 161" in content, f"Expected 'Sprint 161' in Where We Are. Got:\n{content[:200]}"
    assert "Achievements" not in content, "Where We Are should not bleed into Achievements"
    ok("extract_tlu_section: where_we_are")

    content = extract_tlu_section(SAMPLE_TLU, "achievements")
    assert "e2e payment flow" in content.lower(), f"Expected achievement content. Got:\n{content[:200]}"
    ok("extract_tlu_section: achievements")

    content = extract_tlu_section(SAMPLE_TLU, "risks")
    assert "Risk #1" in content, f"Expected risk content. Got:\n{content[:200]}"
    ok("extract_tlu_section: risks")

    content = extract_tlu_section("/nonexistent.md", "risks")
    assert content == "", f"Expected empty string for missing file. Got: {content!r}"
    ok("extract_tlu_section: empty string for missing file")


# ---------------------------------------------------------------------------
# 9. next_pending_section
# ---------------------------------------------------------------------------
def test_next_pending_section():
    pending_tlu = {
        "sections": {
            "where_we_are": {"status": "pushed"},
            "achievements":  {"status": "pending"},
            "risks":         {"status": "pending"},
        }
    }
    assert next_pending_section(pending_tlu) == "achievements"
    ok("next_pending_section: skips pushed, returns first pending")

    all_pushed = {
        "sections": {
            "where_we_are": {"status": "pushed"},
            "achievements":  {"status": "pushed"},
            "risks":         {"status": "pushed"},
        }
    }
    assert next_pending_section(all_pushed) is None
    ok("next_pending_section: None when all pushed")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running TLU unit tests (synthetic data, no API calls)\n")
    test_notion_url_parsing()
    test_config_helpers()
    test_detect_tlu_intent()
    test_parse_week()
    test_state_freshness()
    test_meeting_note_discovery()
    test_tlu_local_path()
    test_extract_tlu_section()
    test_next_pending_section()
    print("\nAll TLU tests passed.")
