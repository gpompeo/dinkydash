"""The phone page: pick your name, then the tabs for the features that are on.

Registered in single mode only. Two blueprints live here: `phone` at `/h`,
which a family member uses, and `pins` under `/settings/pins`, where a parent
sets and resets PINs.

**With sign-in off the page works on trust**: pick your name and carry on.
With it on, a person with a PIN must type it, wrong tries are rate limited, and
a parent who has signed in may pick anybody without one. A person with no PIN
set can be picked by anyone who can reach the page, which is what "optional"
means. The name picked is the only thing the session holds about the phone.

**Hashes live in `auth.json`**, through the store, never in `config.yaml`.
Nothing here logs a PIN, and no template echoes one.
"""

from datetime import date, timedelta

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   session, url_for)

from dinkydash import config as config_module
from dinkydash import checkin, pins, shopping, streaks
from dinkydash.context import tasks_for
from web import manifest as manifest_module
from web import parent, ratelimit
from web.family import current_store
from web.routes.board import change_counter

bp = Blueprint("phone", __name__)
pins_bp = Blueprint("pins", __name__)

# The session key that says whose phone this is.
PERSON = "phone_person"
# The day this phone last celebrated, so a finished day is celebrated once.
CELEBRATED = "phone_celebrated"

# Ten wrong PINs in a quarter of an hour, per caller.
MOST_FAILURES = 10
FAILURE_SECONDS = 900

WRONG = "That PIN didn't work."
SLOW_DOWN = "Too many tries. Wait a few minutes, then try again."
NEEDS_PIN = "Type your PIN to continue."

NO_STORE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


@bp.record_once
def _build_the_limiter(state):
    state.app.config.setdefault(
        "PIN_LIMITER", ratelimit.Limiter(MOST_FAILURES, FAILURE_SECONDS))


def _limiter():
    return current_app.config["PIN_LIMITER"]


def _config():
    """The config, with every person given an id first, as the settings pages do."""
    store = current_store()
    config = store.load_config()
    if config_module.ensure_ids(config):
        store.save_config(config)
    return config


def _people(config):
    return [p for p in config.get("people") or [] if isinstance(p, dict) and p.get("id")]


def _person(config, person_id):
    _, person = config_module.find_item(_people(config), person_id)
    return person


def _has_pin(person_id):
    return bool((current_store().load_auth().get("pins") or {}).get(person_id))


def _tabs(config):
    """The tabs this phone offers: the features that are on, and no others."""
    tabs = []
    if config_module.feature_on(config, "tasks"):
        tabs.append(("tasks", "Tasks"))
    if config_module.feature_on(config, "shopping"):
        tabs.append(("shopping", "Shopping"))
    return tabs


def _render(template, **context):
    page = render_template(template, **context)
    return page, 200, NO_STORE


@bp.route("/h/manifest.webmanifest")
def manifest():
    """What a phone needs to save this page. Carries no family content."""
    return manifest_module.response(
        id=url_for("phone.home"),
        name="DinkyDash",
        short_name="DinkyDash",
        description="Tick off tasks and add to the shopping list.",
        start_url=url_for("phone.home"),
        background_color="#fffaf5",
        theme_color="#fffaf5",
    )


@bp.route("/h/changes")
def changes():
    """The change counter for this page: only a phone that has picked a name."""
    if _person(_config(), session.get(PERSON)) is None:
        return "", 401, NO_STORE
    return change_counter(current_store())


@bp.route("/h", strict_slashes=False)
def home():
    return _tab(None)


@bp.route("/h/<tab>")
def tab(tab):
    return _tab(tab)


def _tab(name):
    config = _config()
    person = _person(config, session.get(PERSON))
    if person is None:
        session.pop(PERSON, None)
        return redirect(url_for("phone.who"))
    tabs = _tabs(config)
    keys = [key for key, _ in tabs]
    if name is not None and name not in keys:
        abort(404)
    current = name or (keys[0] if keys else None)
    days = _task_days(config, person) if current == "tasks" else []
    items = _shopping_items(config) if current == "shopping" else []
    return _render("phone/home.html", person=person, tabs=tabs, current=current, days=days,
                   open_items=[i for i in items if not i.get("bought_at")],
                   bought_items=[i for i in items if i.get("bought_at")],
                   names={p["id"]: p.get("name", "") for p in _people(config)},
                   limits={"text": shopping.MAX_TEXT, "quantity": shopping.MAX_QUANTITY},
                   streak=_streak(config, person) if current == "tasks" else None)


def _streak(config, person):
    """This person's running and best streak. Shown here only, never on the wall."""
    today = config_module.today_for(config)
    since = today - timedelta(days=streaks.MAX_DAYS)
    done = current_store().load_completions(since)
    return {"now": streaks.person_streak(config, person["id"], done, today),
            "best": streaks.best_person_streak(config, person["id"], done, today)}


def _celebrate(config, person_id, day, today):
    """Say well done when `person_id`'s last task due on `day` is ticked, once a day."""
    if day != today or session.get(CELEBRATED) == day.isoformat():
        return
    done = {(c["task_id"], c["date"], c["person_id"])
            for c in current_store().load_completions(today)}
    due = [t for t in tasks_for(config, day)
           if t["mode"] != "anyone" and person_id in t["person_ids"]]
    if not due or any((t["id"], day.isoformat(), person_id) not in done for t in due):
        return
    session[CELEBRATED] = day.isoformat()
    name = (_person(config, person_id) or {}).get("name", "")
    run = streaks.person_streak(config, person_id, current_store().load_completions(
        today - timedelta(days=streaks.MAX_DAYS)), today)
    flash(f"That's everything for today, {name}. Well done!"
          + (f" {run} days in a row." if run > 1 else ""), "ok")


def _restricted():
    """Sign-in is on and this phone is not a parent's: ticks are for oneself only."""
    return parent.enabled() and not parent.is_parent()


def _task_days(config, person):
    """Yesterday's and today's tasks as rows a phone can tick, today first.

    A row is one person's share of a task, so an "Everyone" task has a row each
    and an "Anyone" task has one, credited to whoever ticks it. A member sees
    only the rows they may tick.
    """
    store = current_store()
    today = config_module.today_for(config)
    yesterday = today - timedelta(days=1)
    done = {(c["task_id"], c["date"], c["person_id"]): c for c in store.load_completions(yesterday)}
    named = {p["id"]: p.get("name", "") for p in _people(config)}
    days = []
    for day, label in ((today, "Today"), (yesterday, "Yesterday")):
        rows = []
        for task in tasks_for(config, day):
            if task["mode"] == "anyone":
                doers = [c["person_id"] for c in done.values()
                         if c["task_id"] == task["id"] and c["date"] == day.isoformat()]
                # Credited to the phone's owner on a tick; a finished one shows who did it.
                who = doers[0] if doers else person["id"]
                rows.append(dict(task, person_id=who, who="Anyone", done=bool(doers),
                                 can=not doers or not _restricted() or who == person["id"]))
                continue
            for person_id in task["person_ids"]:
                if _restricted() and person_id != person["id"]:
                    continue
                rows.append(dict(task, person_id=person_id, who=named.get(person_id, ""),
                                 done=(task["id"], day.isoformat(), person_id) in done, can=True))
        days.append({"label": label, "date": day.isoformat(), "rows": rows})
    return days


@bp.route("/h/tick", methods=["POST"])
def tick():
    """Tick or untick one task for one person on one day.

    The access rule runs on the session and the config before anything in the
    body is read for meaning: CSRF is checked app-wide ahead of this function,
    and the date, task and person are only claims until `checkin.may_tick`
    says so.
    """
    config = _config()
    actor = _person(config, session.get(PERSON))
    if actor is None:
        return "", 401, NO_STORE
    try:
        day = date.fromisoformat(request.form.get("date", ""))
    except ValueError:
        abort(400)
    task_id = request.form.get("task_id", "")
    person_id = request.form.get("person") or actor["id"]
    today = config_module.today_for(config)
    if not checkin.may_tick(config, task_id=task_id, day=day, person_id=person_id, today=today,
                            actor_id=actor["id"], restricted=_restricted(),
                            is_parent=parent.enabled() and parent.is_parent()):
        abort(403)
    entry = {"task_id": task_id, "date": day.isoformat(), "person_id": person_id,
             "completed_at": config_module.now_for(config).isoformat(timespec="seconds")}
    store = current_store()
    if request.form.get("done") == "0":
        store.remove_completion(entry, today)
    else:
        store.record_completion(entry, today)
        _celebrate(config, person_id, day, today)
    return redirect(url_for("phone.tab", tab="tasks"))


# -- the shopping list --------------------------------------------------------

def _shopping_items(config):
    return shopping.current(current_store().load_shopping(), config_module.now_for(config))


def _shopper():
    """Who is writing to the list, or an early refusal.

    The Shopping switch comes first so a hidden module answers 404 to every
    route; then a phone with no name picked gets 401. CSRF has already been
    checked app-wide. With sign-in on, every member may write to the list, so
    being a named person is the whole access rule.
    """
    config = _config()
    if not config_module.feature_on(config, "shopping"):
        abort(404)
    actor = _person(config, session.get(PERSON))
    if actor is None:
        abort(401)
    return config, actor


def _change_list(change):
    """Run `change(items, now)` on the stored list; flash a problem and keep it if there is one."""
    config, actor = _shopper()
    now = config_module.now_for(config)
    problems = []

    def apply(items):
        items = shopping.current(items, now)
        changed, problem = change(items, now, actor)
        if problem:
            problems.append(problem)
            return items
        return changed

    current_store().update_shopping(apply)
    for problem in problems:
        flash(problem, "error")
    return redirect(url_for("phone.tab", tab="shopping"))


def _known(items, item_id):
    if not any(i["id"] == item_id for i in items):
        abort(404)


@bp.route("/h/shopping/add", methods=["POST"])
def shopping_add():
    return _change_list(lambda items, now, actor: shopping.add_item(
        items, request.form.get("text"), request.form.get("quantity"), actor["id"], now))


@bp.route("/h/shopping/clear", methods=["POST"])
def shopping_clear():
    return _change_list(lambda items, now, actor: (shopping.clear_bought(items), None))


@bp.route("/h/shopping/<item_id>/edit", methods=["POST"])
def shopping_edit(item_id):
    def change(items, now, actor):
        _known(items, item_id)
        return shopping.edit_item(items, item_id, request.form.get("text"),
                                  request.form.get("quantity"), now)
    return _change_list(change)


@bp.route("/h/shopping/<item_id>/tick", methods=["POST"])
def shopping_tick(item_id):
    def change(items, now, actor):
        _known(items, item_id)
        return shopping.set_bought(items, item_id, request.form.get("done") != "0", now), None
    return _change_list(change)


@bp.route("/h/shopping/<item_id>/delete", methods=["POST"])
def shopping_delete(item_id):
    def change(items, now, actor):
        _known(items, item_id)
        return shopping.delete_item(items, item_id), None
    return _change_list(change)


def _pinned(people):
    """Who must type a PIN here: only with sign-in on, and never for a parent."""
    if not parent.enabled() or parent.is_parent():
        return set()
    return {p["id"] for p in people if _has_pin(p["id"])}


@bp.route("/h/who", methods=["GET", "POST"])
def who():
    config = _config()
    people = _people(config)
    pinned = _pinned(people)
    if request.method == "GET":
        return _render("phone/who.html", people=people, pinned=pinned)

    person = _person(config, request.form.get("person", ""))
    if person is None:
        return redirect(url_for("phone.who"))
    if person["id"] in pinned:
        attempt = request.form.get("pin", "")
        if not attempt:
            return _who_refused(people, pinned, person, NEEDS_PIN, 401)
        # Every attempt counts, right or wrong, for the reason the parent
        # password's does.
        if not _limiter().allow(parent.caller()):
            return _who_refused(people, pinned, person, SLOW_DOWN, 429)
        stored = current_store().load_auth()["pins"][person["id"]]
        if not pins.check_pin(attempt, stored):
            return _who_refused(people, pinned, person, WRONG, 401)
    # Keep a parent's session: picking a name on their own phone must not sign
    # them out of the settings. Anyone else starts a fresh session.
    if not parent.is_parent():
        session.clear()
    session.permanent = True
    session[PERSON] = person["id"]
    return redirect(url_for("phone.home"))


def _who_refused(people, pinned, person, problem, status):
    page = render_template("phone/who.html", people=people, pinned=pinned,
                           asking=person["id"], problem=problem)
    return page, status, NO_STORE


@bp.route("/h/leave", methods=["POST"])
def leave():
    session.pop(PERSON, None)
    return redirect(url_for("phone.who"))


# -- a parent sets and resets PINs ------------------------------------------

@pins_bp.before_request
def _parents_only():
    if not parent.enabled():
        abort(404)
    return parent.guard()


@pins_bp.route("/")
def pin_list():
    config = _config()
    pinned = set((current_store().load_auth().get("pins") or {}))
    return render_template("settings/pins.html", people=_people(config), pinned=pinned,
                           min_digits=pins.MIN_DIGITS, max_digits=pins.MAX_DIGITS)


@pins_bp.route("/<person_id>", methods=["POST"])
def set_pin(person_id):
    config = _config()
    person = _person(config, person_id)
    if person is None:
        abort(404)
    pin = request.form.get("pin", "")
    if not pins.valid_pin(pin):
        flash(f"A PIN is {pins.MIN_DIGITS} to {pins.MAX_DIGITS} digits, numbers only.", "error")
        return redirect(url_for("pins.pin_list"))
    hashed = pins.hash_pin(pin)
    current_store().update_auth(lambda auth: auth.setdefault("pins", {}).update({person_id: hashed}))
    flash(f"PIN set for {person.get('name')}.", "ok")
    return redirect(url_for("pins.pin_list"))


@pins_bp.route("/<person_id>/reset", methods=["POST"])
def reset_pin(person_id):
    config = _config()
    person = _person(config, person_id)
    if person is None:
        abort(404)
    current_store().update_auth(lambda auth: (auth.get("pins") or {}).pop(person_id, None))
    flash(f"{person.get('name')} doesn't need a PIN any more.", "ok")
    return redirect(url_for("pins.pin_list"))
