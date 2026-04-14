"""TLU utilities — pure Python, no API calls. Fully unit-testable."""

import os
import re
from datetime import date, datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

_TLU_KEYWORDS = ("tlu", "traffic light", "traffic-light", "weekly update", "weekly status")


def detect_tlu_intent(command_text: str) -> bool:
    """Return True if command_text is a TLU generation request."""
    lower = command_text.lower()
    return any(kw in lower for kw in _TLU_KEYWORDS)


# ---------------------------------------------------------------------------
# Week parsing
# ---------------------------------------------------------------------------

def parse_week(command_text: str, today: date | None = None) -> tuple[date, date]:
    """Parse a Mon-Fri week from a command string.

    Returns (week_start, week_end) where week_start is Monday and week_end is Friday.

    Handles:
      "last week"
      "week of Apr 7" / "week of 2026-04-07"
      "Apr 7" / "April 7"
      Falls back to last completed Mon-Fri week if no date found.
    """
    if today is None:
        today = date.today()

    text = command_text.lower()

    # Try ISO date: 2026-04-07
    m = re.search(r'(\d{4}-\d{2}-\d{2})', command_text)
    if m:
        ref = date.fromisoformat(m.group(1))
        return _week_of(ref)

    # Try month-name date: "Apr 7", "April 7", "apr 13"
    month_names = {
        "jan": 1, "january": 1, "feb": 2, "february": 2,
        "mar": 3, "march": 3, "apr": 4, "april": 4,
        "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    m = re.search(r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|'
                  r'jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|'
                  r'dec(?:ember)?)\s+(\d{1,2})', text)
    if m:
        month = month_names[m.group(1)]
        day = int(m.group(2))
        year = today.year
        try:
            ref = date(year, month, day)
        except ValueError:
            ref = date(year - 1, month, day)
        return _week_of(ref)

    # Default: last completed Mon-Fri week
    return _last_completed_week(today)


def _week_of(ref: date) -> tuple[date, date]:
    """Return the Mon-Fri week containing ref."""
    monday = ref - timedelta(days=ref.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def _last_completed_week(today: date) -> tuple[date, date]:
    """Return the most recently completed Mon-Fri week (not the current week)."""
    # Go back to last Monday
    days_since_monday = today.weekday()  # 0=Mon, 6=Sun
    last_monday = today - timedelta(days=days_since_monday + 7)
    last_friday = last_monday + timedelta(days=4)
    return last_monday, last_friday


# ---------------------------------------------------------------------------
# State freshness
# ---------------------------------------------------------------------------

def is_state_fresh(state: dict, max_age_hours: int = 24) -> bool:
    """Return True if last_monitor_run is within max_age_hours."""
    last_run = state.get("last_monitor_run")
    if not last_run:
        return False
    try:
        last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - last_dt
        return age.total_seconds() < max_age_hours * 3600
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Meeting notes discovery
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    re.compile(r'(\d{4})-(\d{2})-(\d{2})'),   # YYYY-MM-DD
    re.compile(r'(\d{4})(\d{2})(\d{2})'),       # YYYYMMDD
]


def _extract_date_from_filename(filename: str) -> date | None:
    """Try to extract a date from a filename. Returns None if no date found."""
    for pat in _DATE_PATTERNS:
        m = pat.search(filename)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def discover_meeting_notes(notes_dir: str, week_start: date, week_end: date) -> list[str]:
    """Return absolute paths of meeting note files dated within [week_start, week_end].

    Scans {notes_dir}/meeting-notes/ for .md files with parseable dates in their names.
    Files with no date in the filename are skipped.
    """
    meeting_dir = os.path.join(notes_dir, "meeting-notes")
    if not os.path.isdir(meeting_dir):
        return []

    matched = []
    for fname in sorted(os.listdir(meeting_dir)):
        if not fname.endswith(".md"):
            continue
        file_date = _extract_date_from_filename(fname)
        if file_date is None:
            continue
        if week_start <= file_date <= week_end:
            matched.append(os.path.join(meeting_dir, fname))
    return matched


# ---------------------------------------------------------------------------
# TLU file I/O
# ---------------------------------------------------------------------------

_SECTION_KEYS = ("where_we_are", "achievements", "risks")
_SECTION_HEADINGS = {
    "where_we_are": "## Where We Are",
    "achievements": "## Achievements",
    "risks": "## Risks",
}
_SECTION_ORDER = ["where_we_are", "achievements", "risks"]


def tlu_local_path(notes_path: str, week_end: date) -> str:
    """Return the canonical local path for a TLU file."""
    filename = f"{week_end.isoformat()}-tlu.md"
    return os.path.join(notes_path, "traffic-lights", filename)


def extract_tlu_section(local_path: str, section_key: str) -> str:
    """Extract a section's content from a local TLU markdown file.

    Reads from the section heading until the next ## heading (or EOF).
    Returns empty string if not found.
    """
    if not os.path.isfile(local_path):
        return ""
    with open(local_path) as f:
        content = f.read()

    heading = _SECTION_HEADINGS.get(section_key)
    if not heading:
        return ""

    # Find heading
    start_idx = content.find(f"\n{heading}")
    if start_idx == -1:
        start_idx = content.find(heading)
        if start_idx == -1:
            return ""

    # Find next ## heading
    after_heading = content.find("\n## ", start_idx + len(heading))
    if after_heading == -1:
        section_content = content[start_idx:].strip()
    else:
        section_content = content[start_idx:after_heading].strip()

    return section_content


def next_pending_section(pending_tlu: dict) -> str | None:
    """Return the next section key that has status 'pending', in order."""
    sections = pending_tlu.get("sections", {})
    for key in _SECTION_ORDER:
        if sections.get(key, {}).get("status") == "pending":
            return key
    return None
