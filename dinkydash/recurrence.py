"""Which days a task occurs on, and which occurrence a day is.

Pure functions of a task dict and a calendar date. The caller works out "today" in the family's
timezone and passes the date in, so a daylight-saving change cannot move or skip a day: nothing
here reads a clock or does arithmetic on instants.

A task's `recurrence` holds a `kind` and the fields that kind uses (see doc/prd-household-modules.md
section 4.1). The occurrence index counts occurrences, never days of the year: it is the number of
occurrences in the half-open span from the anchor up to the day. The anchor is `recurrence.start`
when set, otherwise a fixed date, so an index never depends on the year boundary.
"""

import calendar
from datetime import date, timedelta

KINDS = ("daily", "weekdays", "interval", "monthly_day", "monthly_nth", "once")

# Fixed anchor for kinds with no start date. Any date works; it only has to never change.
EPOCH = date(2000, 1, 1)


def _as_date(value) -> date | None:
    """A date from a `date` or an ISO string (YAML gives either); None when it is neither."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _month_last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _monthly_date(rec: dict, year: int, month: int) -> date | None:
    """The one occurrence in a month, or None when the rule is malformed.

    A day number the month lacks falls on the month's last day.
    """
    last = _month_last_day(year, month)
    if rec["kind"] == "monthly_day":
        day = rec.get("day")
        if not isinstance(day, int) or isinstance(day, bool) or not 1 <= day <= 31:
            return None
        return date(year, month, min(day, last))
    nth, weekday = rec.get("nth"), rec.get("weekday")
    if nth not in (1, 2, 3, 4, -1) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
        return None
    if nth == -1:
        end = date(year, month, last)
        return end - timedelta(days=(end.weekday() - weekday) % 7)
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (nth - 1))


def _weekdays(rec: dict) -> frozenset[int]:
    days = rec.get("days") or ()
    return frozenset(d for d in days if isinstance(d, int) and 0 <= d <= 6)


def _every(rec: dict) -> int:
    every = rec.get("every")
    return every if isinstance(every, int) and not isinstance(every, bool) and every >= 1 else 1


def occurs_on(task: dict, day: date) -> bool:
    """Whether the task is due on `day`. A malformed rule never occurs."""
    rec = task.get("recurrence") or {}
    kind = rec.get("kind")
    if kind == "daily":
        return True
    if kind == "weekdays":
        return day.weekday() in _weekdays(rec)
    if kind == "interval":
        start = _as_date(rec.get("start"))
        return start is not None and day >= start and (day - start).days % _every(rec) == 0
    if kind in ("monthly_day", "monthly_nth"):
        return _monthly_date(rec, day.year, day.month) == day
    if kind == "once":
        return _as_date(rec.get("date")) == day
    return False


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def _count_before(rec: dict, anchor: date, day: date) -> int:
    """Occurrences d with anchor <= d < day, for anchor <= day."""
    span = (day - anchor).days
    kind = rec["kind"]
    if kind == "daily":
        return span
    if kind == "weekdays":
        chosen = _weekdays(rec)
        whole, rest = divmod(span, 7)
        partial = sum(1 for i in range(rest) if (anchor + timedelta(days=whole * 7 + i)).weekday() in chosen)
        return whole * len(chosen) + partial
    if kind == "interval":
        every = _every(rec)
        return (span + every - 1) // every
    # Monthly kinds have exactly one occurrence per month.
    months = _months_between(anchor, day) + 1
    first = _monthly_date(rec, anchor.year, anchor.month)
    last = _monthly_date(rec, day.year, day.month)
    if first is None or last is None:
        return 0
    return months - (first < anchor) - (last >= day)


def occurrence_index(task: dict, day: date) -> int:
    """How many occurrences come before `day`, counted from the recurrence's anchor.

    On an occurrence day this is that occurrence's zero-based number, so it is what rotation
    divides. A `once` task has one occurrence, so its index is 0. A day before the anchor counts
    backwards, so the sequence stays consistent either side of it.
    """
    rec = task.get("recurrence") or {}
    if rec.get("kind") == "once" or rec.get("kind") not in KINDS:
        return 0
    anchor = _as_date(rec.get("start")) or EPOCH
    if day >= anchor:
        return _count_before(rec, anchor, day)
    return -_count_before(rec, day, anchor)
