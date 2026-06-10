from __future__ import annotations

from datetime import date, datetime
import re

from ..models import AttendanceResult


def parse_korean_date(text: str, default_year: int | None = None) -> date | None:
    """Parse common Korean cafe date strings into ``date`` where possible."""
    text = text.strip()
    default_year = default_year or datetime.now().year
    patterns = [
        (r"(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", True),
        (r"(\d{1,2})[.\-/월\s]+(\d{1,2})", False),
    ]
    for pattern, has_year in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        if has_year:
            y, m, d = map(int, match.groups()[:3])
        else:
            y = default_year
            m, d = map(int, match.groups()[:2])
        try:
            return date(y, m, d)
        except ValueError:
            return None
    return None


def evaluate_activity(member_id: str, date_texts: list[str], start: date, end: date) -> AttendanceResult:
    active_dates = {d for txt in date_texts if (d := parse_korean_date(txt)) and start <= d <= end}
    return AttendanceResult(member_id=member_id, active_dates=active_dates)
