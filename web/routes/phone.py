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

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   session, url_for)

from dinkydash import config as config_module
from dinkydash import pins
from web import manifest as manifest_module
from web import parent, ratelimit
from web.family import current_store

bp = Blueprint("phone", __name__)
pins_bp = Blueprint("pins", __name__)

# The session key that says whose phone this is.
PERSON = "phone_person"

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
    return _render("phone/home.html", person=person, tabs=tabs,
                   current=name or (keys[0] if keys else None))


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
