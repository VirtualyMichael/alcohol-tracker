"""Small, data-only helpers for daily ingestion summaries."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Mapping


def fill_daily_totals(
    totals: Mapping[date | datetime, float], today: date | None = None
) -> dict[date, float]:
    """Return every date from the first logged day through today, filling gaps with zero."""
    normalized = {key.date() if isinstance(key, datetime) else key: value for key, value in totals.items()}
    if not normalized:
        return {}
    first = min(normalized)
    last = max(today or date.today(), max(normalized))
    result: dict[date, float] = {}
    day = first
    while day <= last:
        result[day] = normalized.get(day, 0.0)
        day += timedelta(days=1)
    return result


def average_drinking_days(totals: Mapping[date | datetime, float], start: date, end: date) -> float:
    """Average drinking days per week, normalized from an inclusive date range."""
    start, end = _ordered(start, end)
    span = (end - start).days + 1
    return 7 * sum(value > 0 for _, value in _in_range(totals, start, end)) / span


def average_standard_drinks_per_day(
    totals: Mapping[date | datetime, float], start: date, end: date
) -> float:
    """Mean standard drinks over inclusive calendar dates, including zero days."""
    start, end = _ordered(start, end)
    span = (end - start).days + 1
    return sum(value for _, value in _in_range(totals, start, end)) / span


def _ordered(start: date, end: date) -> tuple[date, date]:
    return (start, max(start, end))


def _in_range(
    totals: Mapping[date | datetime, float], start: date, end: date
) -> list[tuple[date, float]]:
    selected = []
    for key, value in totals.items():
        day = key.date() if isinstance(key, datetime) else key
        if start <= day <= end:
            selected.append((day, value))
    return selected
