"""The calendar week: which seven days, starting on which day.

Pure: dates in, dates out. The week is worked out from the family's `today` and
their `week_start` setting every time, never stored, so a dashboard whose last
calendar fetch was a day ago still shows the right seven days.
"""

from datetime import timedelta

# Monday is 0, matching `date.weekday()`.
WEEK_STARTS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DEFAULT_WEEK_START = "sunday"
DAYS_IN_WEEK = 7


def week_start_of(config):
    """The day this family's week starts on. Anything unrecognised is Sunday."""
    setting = (config or {}).get("week_start")
    if isinstance(setting, str) and setting.strip().lower() in WEEK_STARTS:
        return setting.strip().lower()
    return DEFAULT_WEEK_START


def first_day(today, week_start=DEFAULT_WEEK_START):
    """The most recent `week_start` on or before `today`."""
    index = WEEK_STARTS.index(week_start) if week_start in WEEK_STARTS \
        else WEEK_STARTS.index(DEFAULT_WEEK_START)
    return today - timedelta(days=(today.weekday() - index) % DAYS_IN_WEEK)


def days(today, week_start=DEFAULT_WEEK_START):
    """The seven dates of the week containing `today`, in order."""
    first = first_day(today, week_start)
    return [first + timedelta(days=offset) for offset in range(DAYS_IN_WEEK)]


def range_label(week):
    """`6 – 12 September`, or both months, or both years when the week crosses them."""
    first, last = week[0], week[-1]
    if first.year != last.year:
        return f"{first.strftime('%-d %B %Y')} – {last.strftime('%-d %B %Y')}"
    if first.month != last.month:
        return f"{first.strftime('%-d %B')} – {last.strftime('%-d %B')}"
    return f"{first.day} – {last.strftime('%-d %B')}"
