"""Streaks, worked out from the completions every time and never stored.

Pure: the caller supplies the config, the completions and today. The rules are
in doc/prd-household-modules.md section 6:

- A person's day is **done** when every task due for them has a completion for
  them. Tasks for "Anyone" belong to the task's own streak, not a person's.
- Days with nothing due are skipped. A due day not done ends the streak.
- Today counts once done and is skipped, not missed, while it is open.
- History reaches back `MAX_DAYS`, the length the completions are kept for.
"""

from datetime import timedelta

from .context import tasks_for
from .recurrence import occurs_on

MAX_DAYS = 400


def _keys(completions):
    return {(c["task_id"], c["date"], c["person_id"]) for c in completions}


def _results(today, outcome):
    """One of "done", "open" or None for each day, newest first, today included.

    `outcome(day)` gives True (done), False (due, not done) or None (nothing due).
    """
    for back in range(MAX_DAYS):
        day = today - timedelta(days=back)
        result = outcome(day)
        if result is None:
            continue
        yield day, result


def _count(today, outcome):
    run = 0
    for day, ok in _results(today, outcome):
        if ok:
            run += 1
        elif day != today:
            break
    return run


def _best(today, outcome):
    best = run = 0
    for day, ok in _results(today, outcome):
        if ok:
            run += 1
            best = max(best, run)
        elif day != today:
            run = 0
    return best


def _person_outcome(config, person_id, completions):
    have = _keys(completions)

    def outcome(day):
        due = [t for t in tasks_for(config, day)
               if t["mode"] != "anyone" and person_id in t["person_ids"]]
        if not due:
            return None
        return all((t["id"], day.isoformat(), person_id) in have for t in due)
    return outcome


def _task_outcome(config, task_id, completions):
    task = next((t for t in config.get("tasks") or []
                 if isinstance(t, dict) and t.get("id") == task_id), None)
    on = {(c["task_id"], c["date"]) for c in completions}

    def outcome(day):
        if task is None or not occurs_on(task, day):
            return None
        return (task_id, day.isoformat()) in on
    return outcome


def person_streak(config, person_id, completions, today):
    return _count(today, _person_outcome(config, person_id, completions))


def best_person_streak(config, person_id, completions, today):
    return _best(today, _person_outcome(config, person_id, completions))


def task_streak(config, task_id, completions, today):
    """Consecutive occurrences with at least one completion, by anybody."""
    return _count(today, _task_outcome(config, task_id, completions))
