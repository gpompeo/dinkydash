"""What the Activity page shows, worked out from config and completions.

Pure: the caller supplies the config, the completions and today. Nothing here
decides who may change what; `checkin.may_tick` does.

- The **grid** is one cell per day for the last `GRID_DAYS`, oldest first:
  "done" (everything due for the person is ticked), "missed" (something due is
  not), "open" (today, not finished yet) or "none" (nothing due).
- The **unticked** list is every due occurrence in the last
  `checkin.PARENT_DAYS_BACK` days without a completion, newest first. An
  "Anyone" task is one row, and stops being listed once anybody has done it.
"""

from datetime import timedelta

from .checkin import PARENT_DAYS_BACK
from .context import tasks_for

GRID_DAYS = 30


def _have(completions):
    return {(c["task_id"], c["date"], c["person_id"]) for c in completions}


def grid(config, person_id, completions, today):
    have = _have(completions)
    cells = []
    for back in range(GRID_DAYS - 1, -1, -1):
        day = today - timedelta(days=back)
        due = [t for t in tasks_for(config, day)
               if t["mode"] != "anyone" and person_id in t["person_ids"]]
        if not due:
            state = "none"
        elif all((t["id"], day.isoformat(), person_id) in have for t in due):
            state = "done"
        else:
            state = "open" if day == today else "missed"
        cells.append({"date": day.isoformat(), "state": state})
    return cells


def unticked(config, completions, today):
    have = _have(completions)
    anyone = {(c["task_id"], c["date"]) for c in completions}
    rows = []
    for back in range(PARENT_DAYS_BACK + 1):
        day = today - timedelta(days=back)
        iso = day.isoformat()
        for task in tasks_for(config, day):
            if task["mode"] == "anyone":
                if (task["id"], iso) not in anyone:
                    rows.append({"task": task, "date": iso, "person_id": None})
                continue
            for person_id in task["person_ids"]:
                if (task["id"], iso, person_id) not in have:
                    rows.append({"task": task, "date": iso, "person_id": person_id})
    return rows
