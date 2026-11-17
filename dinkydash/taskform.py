"""The task editor's recurrence and assignment, as a form shows them and as a task stores them.

Pure: the caller passes the family's `today` and a posted form (anything with `get` and `getlist`).
Problems are returned as field name -> plain-English message, never raised, so the editor can show
every one at once.
"""

from datetime import date

from .recurrence import KINDS

WEEKDAYS = [0, 1, 2, 3, 4]
WEEKEND = [5, 6]
MAX_EVERY = 365
FIXED, ROTATE, ANYONE, EVERYONE = "fixed", "rotate", "anyone", "everyone"
MODES = (FIXED, ROTATE, ANYONE, EVERYONE)
# The modes that name people in order, so a job with nobody listed is skipped.
NAMED_MODES = (FIXED, ROTATE)

# What the editor offers, in order. Weekdays and Weekends are presets of the stored "weekdays" kind.
RECURRENCE_CHOICES = (
    ("daily", "Every day"), ("weekdays", "Weekdays"), ("weekends", "Weekends"),
    ("days", "Chosen days"), ("interval", "Every few days"),
    ("monthly_day", "Monthly, on a date"), ("monthly_nth", "Monthly, on a weekday"),
    ("once", "Once"),
)
MODE_CHOICES = (
    (FIXED, "One person", "Always the first person in the list below."),
    (ROTATE, "Taking turns", "Passes it on each time it comes up, in the order below."),
    (ANYONE, "Anyone", "Shown for the whole family; whoever does it ticks it."),
    (EVERYONE, "Everyone", "Each person has their own tick."),
)
NTH_CHOICES = ((1, "First"), (2, "Second"), (3, "Third"), (4, "Fourth"), (-1, "Last"))
DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _int(value):
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _iso(value):
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        return None


def recurrence_state(rec, today):
    """The values the form's recurrence controls start with, for a stored rule (or none)."""
    rec = rec if isinstance(rec, dict) else {}
    kind = rec.get("kind") if rec.get("kind") in KINDS else "daily"
    days = sorted({d for d in rec.get("days") or [] if isinstance(d, int) and 0 <= d <= 6})
    if kind == "weekdays":
        kind = "weekdays" if days == WEEKDAYS else "weekends" if days == WEEKEND else "days"
    every = rec.get("every")
    nth, weekday, day = rec.get("nth"), rec.get("weekday"), rec.get("day")
    return {
        "kind": kind,
        "days": days,
        "every": every if isinstance(every, int) and 1 <= every <= MAX_EVERY else 2,
        "start": _iso(rec.get("start") or "") or today.isoformat(),
        "day": day if isinstance(day, int) and 1 <= day <= 31 else 1,
        "nth": nth if nth in (1, 2, 3, 4, -1) else 1,
        "weekday": weekday if isinstance(weekday, int) and 0 <= weekday <= 6 else 0,
        "date": _iso(rec.get("date") or "") or "",
    }


def recurrence_from_form(form, today):
    """The rule a posted form describes, with the problems that stop it being stored."""
    kind = form.get("rec_kind", "")
    if kind == "daily":
        return {"kind": "daily"}, {}
    if kind == "weekdays":
        return {"kind": "weekdays", "days": list(WEEKDAYS)}, {}
    if kind == "weekends":
        return {"kind": "weekdays", "days": list(WEEKEND)}, {}
    if kind == "days":
        days = sorted({d for d in map(_int, form.getlist("rec_days")) if d is not None and 0 <= d <= 6})
        if not days:
            return {}, {"rec_days": "Choose at least one day of the week."}
        return {"kind": "weekdays", "days": days}, {}
    if kind == "interval":
        every = _int(form.get("rec_every", ""))
        if every is None or not 1 <= every <= MAX_EVERY:
            return {}, {"rec_every": f"Choose a number of days from 1 to {MAX_EVERY}."}
        raw = form.get("rec_start", "").strip()
        start = _iso(raw) if raw else today.isoformat()
        if start is None:
            return {}, {"rec_start": "The first day should look like 2026-03-15."}
        return {"kind": "interval", "every": every, "start": start}, {}
    if kind == "monthly_day":
        day = _int(form.get("rec_day", ""))
        if day is None or not 1 <= day <= 31:
            return {}, {"rec_day": "Choose a day of the month from 1 to 31."}
        return {"kind": "monthly_day", "day": day}, {}
    if kind == "monthly_nth":
        nth, weekday = _int(form.get("rec_nth", "")), _int(form.get("rec_weekday", ""))
        if nth not in (1, 2, 3, 4, -1):
            return {}, {"rec_nth": "Choose first, second, third, fourth or last."}
        if weekday is None or not 0 <= weekday <= 6:
            return {}, {"rec_weekday": "Choose a day of the week."}
        return {"kind": "monthly_nth", "nth": nth, "weekday": weekday}, {}
    if kind == "once":
        day = _iso(form.get("rec_date", ""))
        if day is None:
            return {}, {"rec_date": "Choose the day it happens, like 2026-12-24."}
        return {"kind": "once", "date": day}, {}
    return {}, {"rec_kind": "Choose how often it comes up."}


def draft_state(form, today):
    """The recurrence controls as posted, kept as typed so a refused form redisplays unchanged."""
    state = recurrence_state(None, today)
    kind = form.get("rec_kind", "")
    state["kind"] = kind if kind in dict(RECURRENCE_CHOICES) else "daily"
    state["days"] = sorted({d for d in map(_int, form.getlist("rec_days")) if d is not None and 0 <= d <= 6})
    for name, key in (("every", "rec_every"), ("start", "rec_start"), ("day", "rec_day"),
                      ("date", "rec_date")):
        if key in form:
            state[name] = form.get(key, "").strip()
    for name, key in (("nth", "rec_nth"), ("weekday", "rec_weekday")):
        value = _int(form.get(key, ""))
        if value is not None:
            state[name] = value
    return state


def _ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def describe(rec, today):
    """A recurrence in words for the list page: "Every day", "Weekends", "Every 3 days"."""
    state = recurrence_state(rec, today)
    kind = state["kind"]
    if kind == "daily":
        return "Every day"
    if kind == "weekdays":
        return "Weekdays"
    if kind == "weekends":
        return "Weekends"
    if kind == "days":
        return ", ".join(DAY_NAMES[d][:3] for d in state["days"]) or "No days chosen"
    if kind == "interval":
        return "Every day" if state["every"] == 1 else f"Every {state['every']} days"
    if kind == "monthly_day":
        return f"Monthly, on the {_ordinal(state['day'])}"
    if kind == "monthly_nth":
        nth = dict(NTH_CHOICES)[state["nth"]].lower()
        return f"Monthly, on the {nth} {DAY_NAMES[state['weekday']]}"
    return f"Once, {state['date']}" if state["date"] else "Once"
