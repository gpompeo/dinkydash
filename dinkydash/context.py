"""Deterministic context: ages, birthdays, countdowns, task assignment.

Nothing here calls the network or the model. Everything is a pure function of
the config plus the date you pass in, which is why the dashboard can recompute it
at render time even when the day's generated text is stale.
"""

import calendar as _calendar
from datetime import date, datetime

from .recurrence import occurrence_index, occurs_on


def anniversary(year, month, day):
    """Return the given month/day as it falls in `year`.

    February 29 exists only in leap years; in other years the anniversary is
    observed on February 28, so a leap-day birthday still counts down to a
    real date instead of raising ValueError. Any other invalid month/day is a
    config error and is left to raise.
    """
    if (month, day) == (2, 29) and not _calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, month, day)


def compute_age(dob, today):
    """Return age on `today` given a date-of-birth."""
    age = today.year - dob.year
    # Compare against the observed anniversary rather than the raw month/day,
    # so someone born on February 29 ages up on February 28 in common years —
    # the same day compute_birthday_info counts down to.
    if today < anniversary(today.year, dob.month, dob.day):
        age -= 1
    return age


def parse_dob(value):
    """Parse a YYYY-MM-DD date of birth from config."""
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def compute_birthday_info(person, today):
    """Return birthday countdown info for one person."""
    dob = parse_dob(person["date_of_birth"])
    current_age = compute_age(dob, today)

    birthday_this_year = anniversary(today.year, dob.month, dob.day)
    if birthday_this_year < today:
        next_birthday = anniversary(today.year + 1, dob.month, dob.day)
        turning = current_age + 1
    elif birthday_this_year == today:
        next_birthday = birthday_this_year
        turning = current_age
    else:
        next_birthday = birthday_this_year
        turning = current_age + 1

    return {
        "name": person["name"],
        "current_age": current_age,
        "turning": turning,
        "days_until_birthday": (next_birthday - today).days,
        "birthday_date": next_birthday.strftime("%-d %B"),
    }


def parse_monthday(value):
    """Validate an annual MM/DD date, using a leap year to allow 29 February."""
    month, day = (int(part) for part in str(value).split("/"))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("Month or day is out of range")
    return date(2000, month, day)


def compute_special_date_info(special_date, today):
    """Return countdown info for one recurring special date (MM/DD)."""
    annual = parse_monthday(special_date["date"])
    month, day = annual.month, annual.day
    target = anniversary(today.year, month, day)
    if target < today:
        # Recompute from month/day rather than bumping the year: a Feb 28 that
        # was rolled back from Feb 29 must become Feb 29 again in a leap year.
        target = anniversary(today.year + 1, month, day)
    return {
        "title": special_date["title"],
        "emoji": special_date.get("emoji", ""),
        "days_until": (target - today).days,
        "date_display": target.strftime("%-d %B"),
    }


def _assignees(config, task, day):
    """The people a task is for on `day`, as person dicts.

    Assignment names people by id, so a rename changes nothing here. An id with no person
    behind it is skipped before the rotation is counted.
    """
    assignment = task.get("assignment") or {}
    people = [p for p in config.get("people") or [] if isinstance(p, dict)]
    mode = assignment.get("mode")
    if mode == "everyone":
        return people
    by_id = {p.get("id"): p for p in people}
    named = [by_id[i] for i in assignment.get("people") or [] if i in by_id]
    if mode == "fixed":
        return named[:1]
    if mode == "rotate" and named:
        offset = assignment.get("offset")
        offset = offset if isinstance(offset, int) and not isinstance(offset, bool) else 0
        return [named[(occurrence_index(task, day) + offset) % len(named)]]
    return []


def tasks_for(config, day):
    """Each task due on `day` with who it is for.

    `assigned_to` is the words the dashboard and the prompt use. A task with nobody to give it to
    (a rotation or a fixed person who has been removed) is left out; "anyone" is its own answer.
    """
    due = []
    for task in config.get("tasks") or []:
        if not isinstance(task, dict) or not task.get("title") or not occurs_on(task, day):
            continue
        mode = (task.get("assignment") or {}).get("mode")
        people = _assignees(config, task, day)
        if mode == "anyone":
            label = "Anyone"
        elif mode == "everyone":
            label = "Everyone"
        elif people:
            label = ", ".join(p.get("name", "") for p in people)
        else:
            continue
        due.append({
            "id": task.get("id"),
            "emoji": task.get("emoji", ""),
            "title": task["title"],
            "mode": mode,
            "person_ids": [p.get("id") for p in people],
            "assigned_to": label,
        })
    return due


def build_countdowns(people, special_dates, today, limit=None):
    """Birthdays and special dates merged into one list, soonest first."""
    countdowns = []
    for person in people or []:
        info = compute_birthday_info(person, today)
        countdowns.append({
            "emoji": "🎂",
            "title": f"{info['name']}'s birthday",
            "days": info["days_until_birthday"],
        })
    for special_date in special_dates or []:
        try:
            info = compute_special_date_info(special_date, today)
        except (ValueError, KeyError):
            # Old or hand-edited dates stay available for repair in settings;
            # one invalid entry must not stop every countdown or the daily run.
            continue
        countdowns.append({
            "emoji": info["emoji"] or "📅",
            "title": info["title"],
            "days": info["days_until"],
        })
    countdowns.sort(key=lambda c: c["days"])
    return countdowns[:limit] if limit else countdowns
