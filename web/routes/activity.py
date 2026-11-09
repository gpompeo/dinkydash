"""The Activity page: streaks, a thirty-day grid and corrections. Single mode only.

Under `/settings/activity`, so with sign-in on it is a parent's page and
`parent.guard()` is the whole of the access rule; with it off, it is open like
the rest of the settings. A correction goes through `checkin.may_tick` as a
parent's: any day in the last fourteen, never one later than today, and only a
task that was due that day for a person it was for.
"""

from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from dinkydash import activity, checkin, streaks
from dinkydash import config as config_module
from web import parent
from web.family import current_store

bp = Blueprint("activity", __name__)


@bp.before_request
def _a_parent_with_tasks_on():
    refused = parent.guard()
    if refused:
        return refused
    if not config_module.feature_on(current_store().load_config(), "tasks"):
        abort(404)


def _people(config):
    return [p for p in config.get("people") or [] if isinstance(p, dict) and p.get("id")]


@bp.route("", strict_slashes=False)
def page():
    store = current_store()
    config = store.load_config()
    today = config_module.today_for(config)
    done = store.load_completions(today - timedelta(days=streaks.MAX_DAYS))
    people = [{"person": p,
               "now": streaks.person_streak(config, p["id"], done, today),
               "best": streaks.best_person_streak(config, p["id"], done, today),
               "cells": activity.grid(config, p["id"], done, today)}
              for p in _people(config)]
    named = {p["id"]: p.get("name", "") for p in _people(config)}
    rows = [dict(r, day=date.fromisoformat(r["date"]),
                 who=named.get(r["person_id"], "Anyone"))
            for r in activity.unticked(config, done, today)]
    return render_template("settings/activity.html", people=people, rows=rows,
                           household=_people(config))


@bp.route("/tick", methods=["POST"])
def tick():
    store = current_store()
    config = store.load_config()
    try:
        day = date.fromisoformat(request.form.get("date", ""))
    except ValueError:
        abort(400)
    # An "Anyone" task has no person of its own, so the form asks who did it;
    # a correction is only ever credited to somebody named.
    person_id = request.form.get("person", "")
    if not person_id:
        abort(400)
    task_id = request.form.get("task_id", "")
    today = config_module.today_for(config)
    if not checkin.may_tick(config, task_id=task_id, day=day, person_id=person_id, today=today,
                            actor_id=None, restricted=False, is_parent=True):
        abort(403)
    store.record_completion(
        {"task_id": task_id, "date": day.isoformat(), "person_id": person_id,
         "completed_at": config_module.now_for(config).isoformat(timespec="seconds")}, today)
    flash("Ticked.", "ok")
    return redirect(url_for("activity.page"))
