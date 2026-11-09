"""Who may tick which task on which day. Pure: the caller supplies the date.

The rule, in one place so the phone route and the Activity page agree:

- A **date** is allowed when it is today or yesterday; a parent signed in may
  also correct any day in the last fourteen. Nothing later than today, ever.
- A **task** must be due that day (`context.tasks_for`), and the credited person
  must be one it is for: its assignees, or anybody for an "Anyone" task.
- With sign-in on, a **member** may credit only themselves, which covers their
  own tasks and "Anyone" tasks and nobody else's. A parent, and anybody at all
  when sign-in is off, may credit any valid person.
"""

from datetime import timedelta

from .context import tasks_for

MEMBER_DAYS_BACK = 1
PARENT_DAYS_BACK = 14


def days_back(is_parent):
    return PARENT_DAYS_BACK if is_parent else MEMBER_DAYS_BACK


def date_allowed(day, today, is_parent):
    return today - timedelta(days=days_back(is_parent)) <= day <= today


def person_for(config, task_id, day, person_id):
    """Whether `person_id` can be credited with `task_id` on `day`, ignoring who is asking."""
    for task in tasks_for(config, day):
        if task["id"] != task_id:
            continue
        if task["mode"] == "anyone":
            return any(p.get("id") == person_id for p in config.get("people") or []
                       if isinstance(p, dict))
        return person_id in task["person_ids"]
    return False


def may_tick(config, *, task_id, day, person_id, today, actor_id, restricted, is_parent):
    """The whole rule. `restricted` is sign-in on and the actor not a parent."""
    if not date_allowed(day, today, is_parent):
        return False
    if restricted and person_id != actor_id:
        return False
    return person_for(config, task_id, day, person_id)
