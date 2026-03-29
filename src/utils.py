"""Shared utilities."""

from datetime import datetime, date, timedelta


def business_days_since(dt_str: str) -> int:
    """Count Mon-Fri business days between dt_str and today."""
    if not dt_str:
        return 0
    try:
        updated = datetime.fromisoformat(dt_str).date()
        today = date.today()
        days = 0
        current = updated
        while current < today:
            if current.weekday() < 5:  # Mon=0 … Fri=4
                days += 1
            current += timedelta(days=1)
        return days
    except Exception:
        return 0
