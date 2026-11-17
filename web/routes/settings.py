"""The settings UI.

Every list section — people, pets, tasks, dates, calendars — is the same
shape: a list, an edit form, a delete. So they share one pair of routes driven
by the SECTIONS table below rather than five near-identical copies.

Writes go straight back to config.yaml through ruamel's round-trip mode, so the
comments in the file survive being edited from a phone.
"""

import logging
from urllib.parse import urlencode
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)

from dinkydash import config as config_module
from dinkydash.config import THEME_COLOURS, theme_of
from dinkydash import pages as pages_module
from dinkydash import schedule, taskform
from dinkydash.calendars import FeedError, addresses, describe_feed, feed_label
from dinkydash.claude_client import GenerationError
from dinkydash.clock import CLOCKS, DEFAULT_CLOCK, clock_of, format_time
from dinkydash.context import compute_birthday_info, parse_monthday, tasks_for
from dinkydash.runner import refresh_calendars
from dinkydash.runner import run as run_generation
from web import parent
from web import feedback as feedback_module
from web import manifest as manifest_module
from web import ratelimit
from web import setup as setup_module
from web.emoji import one_emoji
from web.family import current_store
from web.urls import board_path

log = logging.getLogger(__name__)

bp = Blueprint("settings", __name__)

# The one `date` field is a date of birth, so the form bounds it between this
# year and today, and `validate` refuses anything outside. A browser's date
# input accepts any year from 0001 — a flick of the year wheel on a phone, or
# a dropped keystroke, saved "0017-03-04" without complaint, and the People
# page then read "2009 years old". Nobody alive was born before 1900.
EARLIEST_BIRTH_YEAR = 1900

# How much feedback one family may send in an hour. Somebody with something to
# say writes once, occasionally twice; past this it is a script or a stuck
# button, and either way it is our sending reputation being spent rather than
# theirs. In this process only, like the sign-in limit beside it — a bound on
# abuse, not a quota.
MOST_FEEDBACK = 5
FEEDBACK_SECONDS = 3600



@bp.record_once
def _build_the_feedback_limiter(state):
    """Give each app its own feedback limiter."""
    state.app.config.setdefault(
        "FEEDBACK_LIMITER", ratelimit.Limiter(MOST_FEEDBACK, FEEDBACK_SECONDS))


@bp.before_request
def _needs_a_session():
    """Protect settings when parent sign-in is enabled."""
    return parent.guard()


# Each field is (name, label, kind, required, help). `kind` decides both the
# input rendered and how the posted value is parsed back.
SECTIONS = {
    "people": {
        "key": "people",
        "title": "People",
        "singular": "person",
        "add_label": "Add a person",
        "blurb": "Birthdays here become countdowns, and names here are who tasks rotate between.",
        "fields": [
            ("name", "Name", "text", True, ""),
            ("date_of_birth", "Date of birth", "date", True, "Used for ages and the birthday countdown."),
            ("avatar_emoji", "Emoji", "emoji", False, ""),
            ("avatar_color", "Colour", "color", False, ""),
            ("interests", "Interests", "textarea", False,
             "Can shape the headline — try “dinosaurs, drawing, swimming”."),
        ],
    },
    "pets": {
        "key": "pets",
        "title": "Pets",
        "singular": "pet",
        "add_label": "Add a pet",
        "blurb": "The headline can mention them.",
        "fields": [
            ("name", "Name", "text", True, ""),
            ("type", "Kind of animal", "text", False, "Dog, cat, rabbit…"),
            ("avatar_emoji", "Emoji", "emoji", False, ""),
        ],
    },
    "tasks": {
        "key": "tasks",
        "title": "Tasks",
        "singular": "task",
        "add_label": "Add a task",
        "blurb": "Things that need doing, on the days they come up. Each one can be one person's, "
                 "shared out in turns, for anyone, or for everyone.",
        "fields": [
            ("title", "Task", "text", True, ""),
            ("emoji", "Emoji", "emoji", False, ""),
            ("recurrence", "How often", "recurrence", False, ""),
            ("mode", "Whose job", "assignment", False, ""),
            ("choices", "Who, in order", "people", False,
             "One person uses the first name; Taking turns uses the order. Anyone and Everyone "
             "ignore this list."),
        ],
    },
    "special_dates": {
        "key": "special_dates",
        "title": "Special dates",
        "singular": "date",
        "add_label": "Add a date",
        "blurb": "These come back every year, so there is no year to fill in. Birthdays are counted down already.",
        "fields": [
            ("title", "What is it", "text", True, ""),
            ("emoji", "Emoji", "emoji", False, ""),
            ("date", "Date", "monthday", True, "Day and month — it repeats every year."),
        ],
    },
    "calendars": {
        "key": "calendars",
        "title": "Calendars",
        "singular": "calendar",
        "add_label": "Add a calendar",
        # **The disclosure where somebody is actually about to paste a calendar
        # link**, not only in a policy nobody opens. It says what leaves and
        # what does not, in the same breath as the field that causes it.
        "blurb": "Every calendar you switch on is merged into one agenda. Titles and times are "
                 "sent to Anthropic each morning so Claude can write the daily headline; an event "
                 "kept off the dashboard by a guest list is never stored and never sent.",
        "fields": [
            ("label", "Calendar name", "text", True,
             "A name to help you recognise this calendar in settings, such as “Family” or “School”. "
             "It won't appear on the dashboard."),
            ("url", "Calendar link (iCal / ICS)", "url", True,
             "Paste the calendar's sharing link here. HTTPS and webcal:// links work."),
            ("shared_with", "Only show events shared with", "emails", False,
             "Email addresses, with commas between them. Only events with one of these people "
             "on the guest list, or organised by them, go on the dashboard — the rest of this "
             "calendar stays private. Use the address on the invitation. Leave it empty to "
             "show everything."),
            ("enabled", "Show on the dashboard", "checkbox", False, ""),
            ("show_locations", "Show where each event is", "checkbox", False,
             "Turn this off if the addresses take up too much room on the dashboard."),
        ],
    },
}

EMOJI_SUGGESTIONS = {
    "people": ["🦖", "⚽", "🎨", "☕", "🚀", "🎸", "🐙", "📚"],
    "pets": ["🐕", "🐈", "🐰", "🐠", "🐹", "🐦", "🐢", "🐴"],
    "tasks": ["🍽", "🦴", "🗑", "🧺", "🛏", "🌱", "🧹", "📦"],
    "special_dates": ["🎄", "☀️", "🚂", "🎃", "✈️", "🎆", "🥚", "🍂"],
}

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# How often the calendars are re-fetched. A short list rather than a free
# number: the useful range is bounded at both ends, and Google's own feed is
# cached, so anything under a quarter of an hour would be a promise we cannot
# keep. The engine takes any integer — these are what the page offers.
REFRESH_CHOICES = (15, 30, 60, 360, 1440)


def current_config():
    config = current_store().load_config()
    if config_module.ensure_ids(config):
        # A config written by hand, or before ids existed. Give its items ids
        # once, so the links on this page keep meaning the same thing.
        save(config)
    return config


def save(config, *, invalidate_calendars=()):
    current_store().save_config(config, invalidate_calendars=invalidate_calendars)


# The sections each switch owns. Off, they are not offered and their routes
# answer 404; the data stays in the config.
SECTION_FEATURES = {"tasks": "tasks", "special_dates": "special_dates"}

# Section names an earlier release put in URLs. Forms already open on a screen still post to them,
# so they resolve to the current name before any handler, switch or form sees them.
LEGACY_SECTION_NAMES = {"recurring": "tasks"}


@bp.url_value_preprocessor
def _use_current_section_name(endpoint, values):
    """Serve an old section URL through the same view as its current one.

    One view means one feature check, one sign-in guard and one write, whichever URL a form used.
    """
    if values and values.get("section_name") in LEGACY_SECTION_NAMES:
        values["section_name"] = LEGACY_SECTION_NAMES[values["section_name"]]


def task_form(config, task):
    """A task as the Tasks form shows it: who is in the rotation, by person id.

    `names` is the same list as words, for the list page; `rec` and `mode` are the recurrence
    and assignment controls' starting values.
    """
    by_id = {p.get("id"): p.get("name", "") for p in config.get("people") or []
             if isinstance(p, dict) and p.get("id")}
    people = (task.get("assignment") or {}).get("people") or []
    chosen = [i for i in people if i in by_id]
    assignment_mode = (task.get("assignment") or {}).get("mode")
    today = config_module.today_for(config)
    return {"id": task.get("id"), "title": task.get("title", ""), "emoji": task.get("emoji", ""),
            "choices": chosen, "names": [by_id[i] for i in chosen],
            "rec": taskform.recurrence_state(task.get("recurrence"), today),
            "start": taskform._iso(task.get("start") or "") or "",
            "created": task.get("created") or "",
            "when": taskform.describe(task.get("recurrence"), today),
            "mode": assignment_mode if assignment_mode in taskform.MODES else taskform.ROTATE}


def known_person_ids(config, ids):
    """The posted person ids that belong to somebody in this family, once each, in order."""
    known = {p.get("id") for p in config.get("people") or [] if isinstance(p, dict) and p.get("id")}
    return [i for i in dict.fromkeys(ids or []) if i and i in known]


def task_from_form(config, existing, submitted):
    """The task to store for a submitted Tasks form.

    `submitted` carries the checked `recurrence` and the assignment `mode`; the rotation offset is kept from
    `existing`.
    The form posts person ids and only ids of people in the family are kept, so a later rename
    changes nothing and no empty id reaches an assignment.
    """
    task = dict(existing or {})
    assignment = dict(task.get("assignment") or {"offset": 0})
    assignment["mode"] = submitted["mode"]
    assignment["people"] = known_person_ids(config, submitted.get("choices"))
    task.update({"title": submitted["title"], "emoji": submitted.get("emoji", ""),
                 "recurrence": submitted["recurrence"], "assignment": assignment})
    if submitted.get("start"):
        task["start"] = submitted["start"]
    else:
        task.pop("start", None)
    if not existing and submitted.get("created"):
        task["created"] = submitted["created"]
    return task


def read_rules(form, submitted, item, stored, today):
    """Put the posted recurrence and assignment on `submitted`; return the problems with them.

    A post with no `rec_kind` is not from the editor's controls, so the task keeps what it has.
    `submitted["rec"]` is what the form redisplays; `submitted["recurrence"]` is what is stored.
    """
    stored_start = (stored or {}).get("start") or ""
    submitted["start"], problems = taskform.start_from_form(form, today, stored_start)
    submitted["created"] = (stored or {}).get("created") or (today.isoformat() if stored is None else "")
    if "rec_kind" not in form:
        stored = stored or {}
        submitted["recurrence"] = stored.get("recurrence") or {"kind": "daily"}
        submitted["mode"] = item.get("mode") or taskform.ROTATE
        submitted["rec"] = item.get("rec")
        return problems
    submitted["rec"] = taskform.draft_state(form, today)
    submitted["recurrence"], rule_problems = taskform.recurrence_from_form(form, today)
    problems.update(rule_problems)
    if not rule_problems and "task_start" not in problems:
        first = taskform.effective_start(submitted["start"], submitted["created"])
        problems.update(taskform.once_problem(submitted["recurrence"], first))
    assignment_mode = form.get("mode", "")
    if assignment_mode not in taskform.MODES:
        problems["mode"] = "Choose whose job it is."
    submitted["mode"] = assignment_mode if assignment_mode in taskform.MODES else taskform.ROTATE
    return problems


def section_or_404(name):
    section = SECTIONS.get(name)
    if not section:
        abort(404)
    feature = SECTION_FEATURES.get(name)
    if feature and not config_module.feature_on(current_config(), feature):
        abort(404)
    return section


def parse_field(field, form, existing):
    """Read one posted field back into its config value."""
    name, _label, kind, required, _help = field
    if kind == "checkbox":
        return name in form
    if kind == "people":
        values = [v for v in form.getlist(name) if v]
        return values
    if kind == "emails":
        # One text box, stored as a list: what the engine compares against.
        return addresses(form.get(name, ""))
    if kind == "monthday":
        month = form.get(f"{name}_month", "").strip()
        day = form.get(f"{name}_day", "").strip()
        try:
            return f"{int(month):02d}/{int(day):02d}"
        except ValueError:
            # Keep incomplete/malformed input for validation and redisplay.
            return f"{month}/{day}"
    value = form.get(name, "").strip()
    if kind == "date" and value:
        # <input type="date"> already gives YYYY-MM-DD.
        return value
    return value


def validate(section, item, today):
    """Return field names mapped to human-readable validation errors.

    `today` is the family's own date: a date of birth after it is a typo,
    and so is one before EARLIEST_BIRTH_YEAR. The message names the year the
    form received, because the input itself can show "0017" quite quietly.
    """
    problems = {}
    for name, label, kind, required, _help in section["fields"]:
        value = item.get(name)
        if required and not value:
            problems[name] = ("Choose at least one person." if kind == "people"
                              else f"{label} is needed.")
        if kind == "date" and value:
            try:
                dob = datetime.strptime(str(value), "%Y-%m-%d").date()
            except ValueError:
                problems[name] = f"{label} should look like 2017-03-15."
            else:
                if dob.year < EARLIEST_BIRTH_YEAR:
                    problems[name] = (f"{label} has the year {dob.year:04d}. "
                                      "Check the year and try again.")
                elif dob > today:
                    problems[name] = (f"{label} is in the future. "
                                      "Check the year and try again.")
        if kind == "monthday":
            try:
                parse_monthday(value)
            except ValueError:
                problems[name] = "Choose a valid day and month. February can have up to 29 days."
        if kind == "emails":
            for address in value or []:
                if "@" not in address:
                    problems[name] = (f"“{address}” is not an email address. Use the address "
                                      "on the invitation, like sam@example.com.")
                    break
        if kind == "emoji" and value and not one_emoji(str(value)):
            problems[name] = "Choose one emoji."
    return problems


@bp.route("/")
def home():
    config = current_config()
    today = config_module.today_for(config)
    payload = current_store().load_payload(config)

    tzinfo = config_module.tzinfo_for(config)
    clock = clock_of(config)
    # The first brief is due immediately; the next tick's timing depends on the host.
    status = {"state": "waiting",
              "detail": "No dashboard has been generated yet. The next run writes it."}
    if payload:
        generated_for = payload.get("generated_for_date")
        written = _clock(payload.get("generated_at"), tzinfo, clock)
        if generated_for == today.isoformat():
            status = {"state": "ready",
                      "detail": f"Today's dashboard is up — written {written or 'earlier'}."}
        elif generated_for:
            status = {"state": "stale", "detail": f"Showing the dashboard from {generated_for}."}
        # A refresh with no brief yet leaves a payload holding only the agenda,
        # so an unwritten dashboard stays "waiting" rather than claiming a date.
        fetched = _clock(payload.get("calendars_fetched_at"), tzinfo, clock)
        if fetched:
            status["detail"] += f" Calendars refreshed {fetched}."

    calendars = config.get("calendars") or []
    broken = [c for c in (payload or {}).get("calendar_statuses", []) if c.get("ok") is False]
    tasks = [c for c in config.get("tasks") or [] if isinstance(c, dict)]

    counts = {
        "people": len(config.get("people") or []),
        "pets": len(config.get("pets") or []),
        "tasks": len(tasks),
        "special_dates": len(config.get("special_dates") or []),
        "calendars": len(calendars),
        # A task with nobody to take it is skipped on the dashboard. Say so on
        # the row rather than counting it as assigned.
        "tasks_unassigned": sum(
            1 for c in tasks
            if (c.get("assignment") or {}).get("mode") in taskform.NAMED_MODES
            and not task_form(config, c)["choices"]),
    }

    # Show the checklist until setup and the first dashboard are complete.
    setup = setup_module.status(config, payload)
    setting_up = setup["in_progress"]
    screen = screen_for_setup() if setting_up and setup["ready"] else None

    return render_template(
        "settings/home.html", config=config, status=status, counts=counts,
        broken=broken, sections=SECTIONS, cadence=cadence_summary(config),
        setup=setup, setting_up=setting_up, screen=screen,
        calendars_on=any(c.get("enabled") for c in calendars if isinstance(c, dict)),
        board_link=board_path(),
        family_name_is_default=config_module.family_name_is_default(config),
    )


def screen_for_setup():
    """The dashboard's local address for the setup checklist."""
    return {"link": url_for("board.index", _external=True), "qr": None}


@bp.route("/features", methods=["POST"])
def set_features():
    """The home page's switches. A ticked box is on; the data is never touched."""
    config = current_config()
    config["features"] = {name: name in request.form
                          for name in config_module.FEATURE_DEFAULTS}
    save(config)
    flash("Saved.", "ok")
    return redirect(url_for("settings.home"))


@bp.route("/timezone", methods=["POST"])
def set_timezone():
    """One tap on the checklist: the zone the phone itself is set to.

    Guessing a timezone from an IP address is wrong often enough to be worse
    than asking (`config.starter_config`). The phone's own clock setting is a
    different thing, and offering it back is still asking: the page reads it
    with `Intl.DateTimeFormat` and puts it on a button, and nothing is written
    until the button is pressed. Anything that is not a zone this Python
    knows is refused, so the form cannot write nonsense into the config.
    """
    name = request.form.get("timezone", "").strip()
    known = False
    if name and len(name) <= 64:
        try:
            ZoneInfo(name)
            known = True
        except Exception:  # ZoneInfoNotFoundError, or a key that is not a key
            known = False
    if not known:
        flash("That is not a time zone this dashboard knows. Pick one under Family & system.",
              "error")
        return redirect(url_for("settings.home"))
    config = current_config()
    config["timezone"] = name
    save(config)
    flash(f"Time zone set to {name}.", "ok")
    return redirect(url_for("settings.home"))


def _clock(stamp, tzinfo, clock=None):
    """An ISO timestamp as the time on the family's own clock, or None.

    Stamps are written in UTC. The server is often not in the family's timezone
    — a Pi is frequently left on UTC — so timestamps must be converted.
    Written in whichever clock they read, so this page does not contradict the
    dashboard it is describing.
    """
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return format_time(moment.astimezone(tzinfo), clock or DEFAULT_CLOCK)


@bp.route("/manifest.webmanifest")
def manifest():
    """The name and icon a phone gives this page on its home screen.

    Read straight from the store rather than through `current_config`: fetching
    a manifest must not be able to write config.yaml.
    """
    config = current_store().load_config()
    family = config.get("family_name")
    return manifest_module.response(
        id=url_for("settings.home"),
        name="PompDash settings",
        # What fits under the icon. Not "Settings" — that is already an app.
        short_name="PompDash",
        description=f"Change what {family} sees on the dashboard." if family
                    else "Change what the dashboard shows.",
        start_url=url_for("settings.home"),
        background_color=THEME_COLOURS[theme_of(config)],
        theme_color=THEME_COLOURS[theme_of(config)],
    )


@bp.route("/generate", methods=["POST"])
def generate_now():
    """Rewrite the daily headline on request."""
    config = current_config()
    first = not (current_store().load_payload(config) or {}).get("generated_for_date")
    try:
        payload = run_generation(config, current_store())
    except GenerationError as exc:
        flash(str(exc), "error")
    except Exception as exc:  # a broken feed or an unreadable file shouldn't 500 the UI
        log.exception("Generation failed")
        flash(f"Generation failed: {exc}", "error")
    else:
        what = "Your first daily headline is written" if first else "Daily headline rewritten"
        flash(f"{what} — “{payload['headline']}”", "ok")
    return redirect(url_for("settings.home"))


@bp.route("/<section_name>")
def section_list(section_name):
    section = section_or_404(section_name)
    config = current_config()
    items = config.get(section["key"]) or []
    today = config_module.today_for(config)

    extras = {}
    if section_name == "people":
        extras["birthdays"] = [compute_birthday_info(p, today) for p in items]
    if section_name == "tasks":
        today_for = {t["id"]: t["assigned_to"] for t in tasks_for(config, today)}
        extras["turns"] = [[{"assigned_to": today_for[c["id"]]}] if c.get("id") in today_for else []
                           for c in items]
        items = [task_form(config, c) for c in items]
    if section_name == "special_dates":
        extras["dates"] = []
        for item in items:
            try:
                display = parse_monthday(item.get("date")).strftime("%-d %B")
            except ValueError:
                display = "Check this date — it is not shown on the dashboard"
            extras["dates"].append(display)

    return render_template(
        "settings/list.html", section=section, section_name=section_name,
        items=items, extras=extras, config=config,
    )


@bp.route("/<section_name>/<item_id>", methods=["GET", "POST"])
def section_edit(section_name, item_id):
    section = section_or_404(section_name)
    config = current_config()
    items = config.setdefault(section["key"], [])
    today = config_module.today_for(config)

    is_new = item_id == "new"
    if is_new:
        item = {}
        if section_name == "tasks":
            item = task_form(config, {})
        if section_name == "calendars":
            item = {"enabled": True, "show_locations": True,
                    "label": suggested_calendar_label(config)}
        index = None
    else:
        index, item = config_module.find_item(items, item_id)
        if item is None:
            abort(404)
        if section_name == "tasks":
            stored_task, item = item, task_form(config, item)
        if section_name == "calendars" and "show_locations" not in item:
            # Absent means shown, so the box starts ticked and the copy keeps
            # the file as it was until somebody saves.
            item = {**item, "show_locations": True}

    saved_item = dict(item)
    problems, checked = {}, None

    if request.method == "POST":
        submitted = dict(item)
        for field in section["fields"]:
            submitted[field[0]] = parse_field(field, request.form, item)
        task_problems = {}
        if section_name == "tasks":
            submitted["choices"] = known_person_ids(config, submitted["choices"])
            task_problems = read_rules(request.form, submitted, item,
                                       None if is_new else stored_task, today)

        if section_name == "tasks" and (request.form.get("move_choice")
                                            or request.form.get("action") == "update_choices"):
            # No-JavaScript ordering edits the submitted draft, never storage.
            direction, _, person = request.form.get("move_choice", "").partition(":")
            choices = submitted["choices"]
            if person in choices and direction in ("up", "down"):
                position = choices.index(person)
                target = position + (-1 if direction == "up" else 1)
                if 0 <= target < len(choices):
                    choices[position], choices[target] = choices[target], choices[position]
            item = submitted
        elif request.form.get("action") == "check":
            checked = check_feed(submitted, config)
            item = submitted
        else:
            problems = validate(section, submitted, today)
            if section_name == "tasks":
                problems.update(task_problems)
                if submitted["mode"] in taskform.NAMED_MODES and not submitted["choices"]:
                    problems["choices"] = "Choose at least one person."
                too_long = len(submitted.get("title") or "") > config_module.MAX_TITLE_LENGTH
                if too_long:
                    problems["title"] = (f"Keep the task to {config_module.MAX_TITLE_LENGTH} "
                                         "characters or fewer.")
                if is_new and len(items) >= config_module.MAX_TASKS:
                    problems["title"] = (f"You can have up to {config_module.MAX_TASKS} tasks. "
                                         "Remove one to add another.")
            if not problems:
                # The mark `starter_config` puts on an invented person or pet.
                # Saving the form is the touch that makes the item theirs,
                # whatever they left in the boxes.
                submitted.pop(config_module.INVENTED, None)
                if section_name == "tasks":
                    submitted = task_from_form(config, None if is_new else stored_task, submitted)
                if is_new:
                    submitted["id"] = config_module.new_id(
                        i.get("id") for i in items if isinstance(i, dict)
                    )
                    items.append(submitted)
                else:
                    submitted["id"] = item_id
                    items[index] = submitted
                # Pressing Save explicitly refreshes this calendar even when
                # the values are unchanged. The store also detects changed or
                # removed sources and clears them in the same operation.
                save(config, invalidate_calendars=(feed_label(submitted),)
                     if section_name == "calendars" else ())
                if section_name == "calendars" and setup_module.status(
                        config, current_store().load_payload(config))["in_progress"]:
                    # Setting up there is no Refresh button to point at, and the
                    # next step is on the checklist, not on this list.
                    flash(f"Saved {feed_label(submitted)}. Its events reach the dashboard "
                          f"within a few minutes.", "ok")
                    return redirect(url_for("settings.home"))
                if section_name == "calendars":
                    flash(f"Saved {feed_label(submitted)}. The dashboard picks up the change at "
                          f"the next refresh — press Refresh calendars if you don't want to wait.",
                          "ok")
                else:
                    flash(f"Saved {submitted.get('name') or submitted.get('title') or 'it'}.", "ok")
                return redirect(url_for("settings.section_list", section_name=section_name))
            item = submitted

    selected = item.get("choices") or []
    everyone = {p["id"]: {"id": p["id"], "name": p.get("name", "")}
                for p in config.get("people") or [] if isinstance(p, dict) and p.get("id")}
    participants = [everyone[i] for i in dict.fromkeys([*selected, *everyone]) if i in everyone]
    return render_template(
        "settings/edit.html", section=section, section_name=section_name,
        item=item, item_id=item_id, is_new=is_new, problems=problems,
        checked=checked, config=config, months=MONTHS,
        email_steps=False,
        task_choices={"recurrence": taskform.RECURRENCE_CHOICES, "modes": taskform.MODE_CHOICES,
                      "nth": taskform.NTH_CHOICES, "days": taskform.DAY_NAMES},
        date_min=f"{EARLIEST_BIRTH_YEAR}-01-01", date_max=today.isoformat(),
        emoji=EMOJI_SUGGESTIONS.get(section_name, []),
        # The picker's dialog is drawn once, after the form, and only where there is an
        # emoji to choose. Each section has at most one.
        emoji_field=next((f[0] for f in section["fields"] if f[2] == "emoji"), None),
        colors=config_module.AVATAR_COLORS, people=participants,
        draft_changed=any((item.get(name) or None) != (saved_item.get(name) or None)
                          for name, *_ in section["fields"]),
        removal=removal_prompt(config, section, saved_item) if not is_new else None,
        # Where to find a link is for somebody who has not pasted one yet, or
        # whose link has just failed. A working calendar does not need it.
        link_help=section_name == "calendars" and (
            is_new or not saved_item.get("url") or "url" in problems
            or bool(checked and checked.get("link_help"))),
    )


def suggested_calendar_label(config):
    """A name for a new calendar, filled in so it need not be typed.

    The name never reaches the dashboard — it is how the settings list and the
    feed status refer to the calendar — so making somebody invent one before
    they can paste the link they came with is friction for nothing. "Family"
    for the first; after that a numbered one, because two feeds with one name
    are filed together (`calendars.feed_label`) and the second would silently
    inherit the first's events when it failed. Whatever is filled in can be
    typed over.
    """
    taken = {feed_label(c).strip().lower() for c in config.get("calendars") or []
             if isinstance(c, dict)}
    if "family" not in taken:
        return "Family"
    number = 2
    while f"calendar {number}" in taken:
        number += 1
    return f"Calendar {number}"


def check_feed(item, config):
    """Fetch a pasted iCal URL and describe what came back.

    With a guest list on the form, the answer is "3 of the 24" — and a red
    "none of them" when the list matches nobody. That case is the failure the
    old global filter hid: a working link, a full calendar, and a dashboard with
    nothing on it. Red, because that is exactly what saving would give.
    """
    url = (item.get("url") or "").strip()
    if not url:
        return {"ok": False, "message": "Paste a link first."}
    wanted = addresses(item.get("shared_with"))
    try:
        found = describe_feed(
            url, config_module.tzinfo_for(config),
            today=config_module.today_for(config),
            days_ahead=int(config.get("calendar_days_ahead") or 14),
            shared_with=wanted,
        )
    except FeedError as exc:
        if exc.status_code in (401, 403, 404, 410) or exc.invalid_data:
            if exc.status_code in (401, 403):
                message = "This calendar isn't allowing PompDash to read it."
            elif exc.status_code in (404, 410):
                message = ("We couldn't find a calendar at this link. It may be private, "
                           "out of date, or copied incorrectly.")
            else:
                message = ("This link didn't return readable calendar data. It may open "
                           "a calendar webpage or a sign-in page instead.")
            return {"ok": False, "link_help": True, "message": message,
                    "recovery": "Copy a fresh iCal / ICS sharing link from your calendar's "
                                "settings, paste it above, then test again. See the provider "
                                "instructions above for the right link."}
        return {"ok": False, "message": str(exc)}
    except GenerationError as exc:
        return {"ok": False, "message": str(exc)}
    days = found["days_ahead"]
    if not found["total"]:
        return {"ok": True, "message":
                f"That link works, but there is nothing on it in the next {days} days."}
    who = ", ".join(wanted)
    if wanted and not found["count"]:
        return {"ok": False, "message":
                f"That link works and has {found['total']} events in the next {days} days, "
                f"but none of them is shared with {who}. Check the address — it has to be "
                f"the one on the invitation."}
    if wanted:
        count = found["count"]
        lead = (f"{count} of the {found['total']} events over the next {days} days "
                f"{'is' if count == 1 else 'are'} shared with {who}.")
    else:
        lead = f"{found['count']} events over the next {days} days."
    nxt = found["next"]
    tail = ""
    if nxt:
        when = "all day" if nxt["all_day"] else format_time(
            nxt.get("start") or nxt.get("time"), clock_of(config))
        tail = f" Next up: {nxt['title']}, {nxt['date']} at {when}."
    return {"ok": True, "message": lead + tail}


def removal_prompt(config, section, item):
    """Name what will be removed, including the effects on task assignments."""
    name = item.get("name") or item.get("title") or item.get("label") or section["singular"]
    message = "This cannot be undone."
    if section["key"] == "people":
        message += f" {name} will also be removed from task assignments."
        unassigned = [c["title"] for c in config.get("tasks") or []
                      if (c.get("assignment") or {}).get("people")
                      and all(p == item.get("id") for p in c["assignment"]["people"])]
        if unassigned:
            message += " These tasks will have nobody assigned: " + ", ".join(unassigned) + "."
    elif section["key"] == "calendars":
        message += " Stored events from this calendar will also be removed."
    return {"title": f"Remove {name}?", "message": message,
            "confirm": f"Remove {name}", "cancel": f"Keep {name}"}


def confirm_action(prompt, cancel_url, fields=None):
    """A normal confirmation page also works without JavaScript."""
    return render_template("settings/confirm.html", prompt=prompt,
                           cancel_url=cancel_url, fields=fields or {})


@bp.route("/<section_name>/<item_id>/delete", methods=["POST"])
def section_delete(section_name, item_id):
    section = section_or_404(section_name)
    config = current_config()
    items = config.get(section["key"]) or []
    index, removed = config_module.find_item(items, item_id)
    if removed is None:
        abort(404)
    if request.form.get("confirmed") != "yes":
        return confirm_action(removal_prompt(config, section, removed),
                              url_for("settings.section_edit", section_name=section_name,
                                      item_id=item_id))
    items.pop(index)
    if section_name == "people":
        # Deleting Mia means Mia is gone from the dashboard, turns included.
        config_module.drop_from_tasks(config, removed.get("id"))
        if hasattr(current_store(), "drop_person_completions"):
            current_store().drop_person_completions(removed.get("id"))
    save(config)
    flash(f"Removed {removed.get('name') or removed.get('title') or removed.get('label') or 'it'}.", "ok")
    return redirect(url_for("settings.section_list", section_name=section_name))


@bp.route("/<section_name>/<item_id>/move", methods=["POST"])
def section_move(section_name, item_id):
    """Reorder displayed items; this does not change a task's participants."""
    section = section_or_404(section_name)
    config = current_config()
    items = config.get(section["key"]) or []
    index, item = config_module.find_item(items, item_id)
    if item is None:
        abort(404)
    target = index + (-1 if request.form.get("direction") == "up" else 1)
    if 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]
        save(config)
    return redirect(url_for("settings.section_list", section_name=section_name))


@bp.route("/screen", methods=["GET", "POST"])
def screen():
    """Edit dashboard colours."""
    config = current_config()
    if request.method == "POST":
        theme = request.form.get("theme")
        if theme in config_module.THEMES:
            config["theme"] = theme
            save(config)
            flash(f"Colours set to {theme}.", "ok")
        return redirect(url_for("settings.screen"))
    return render_template("settings/screen.html", config=config,
                           themes=config_module.THEMES)


@bp.route("/screen/setup")
def screen_setup():
    """Make the link for one screen: touch or not, first page, rotation.

    A read: the setup is in the link it makes and nowhere on the server, so
    each screen is set up by its own link and none can alter another.
    """
    config = current_config()
    setup, problems = pages_module.parse_setup(request.args)
    shown = pages_module.available(config)
    setup = pages_module.Setup(
        touch=setup.touch, page=pages_module.initial_key(setup.page, shown),
        rotate=setup.rotate, interval=setup.interval)
    if parent.enabled():
        from web.routes.wall import screen_token
        base = url_for("wall.board", token=screen_token(current_store()), _external=True)
    else:
        base = url_for("board.index", _external=True)
    query = pages_module.link_query(setup)
    link = base + ("?" + urlencode(query) if query else "")
    return render_template(
        "settings/screen_setup.html", setup=setup, problems=problems, pages=shown,
        link=link, minimum=pages_module.MIN_INTERVAL, maximum=pages_module.MAX_INTERVAL,
        default_interval=pages_module.DEFAULT_INTERVAL)


def describe_minutes(minutes):
    """An interval as the page says it — "Every hour", not "60"."""
    if minutes == 1440:
        return "Once a day"
    if minutes >= 60 and minutes % 60 == 0:
        hours = minutes // 60
        return "Every hour" if hours == 1 else f"Every {hours} hours"
    return "Every minute" if minutes == 1 else f"Every {minutes} minutes"


def cadence_choices(current):
    """The offered intervals, plus whatever the file already says if it differs.

    A hand-edited `refresh_minutes: 45` is a real setting, and a select that
    could not show it would silently rewrite it the first time anyone saved.
    """
    minutes = sorted(set(REFRESH_CHOICES) | {current})
    return [(m, describe_minutes(m)) for m in minutes]


def cadence_values(config):
    """The two keys as the form wants them — an int and an "HH:MM" string.

    `brief_time` stays `HH:MM` whatever clock the family reads: it is the value
    of an `<input type="time">`, which takes that shape on the wire and draws it
    in the reader's own locale. The prose below is the part that follows the
    setting.
    """
    return {
        "refresh_minutes": int(schedule.refresh_interval(config).total_seconds() // 60),
        "brief_time": schedule.brief_time(config).strftime("%H:%M"),
    }


def cadence_summary(config):
    """The one line the settings home shows: "Calendars every hour · daily headline at 06:00"."""
    values = cadence_values(config)
    cadence = describe_minutes(values["refresh_minutes"])
    written = format_time(schedule.brief_time(config), clock_of(config))
    return (f"Calendars {cadence[:1].lower()}{cadence[1:]} · "
            f"daily headline at {written}")


@bp.route("/refresh", methods=["GET", "POST"])
def refresh():
    """The two cadences: how often the calendars are fetched, and when the brief is written."""
    config = current_config()
    stored = cadence_values(config)
    choices = cadence_choices(stored["refresh_minutes"])
    allowed = {m for m, _ in choices}
    values, problems = stored, []

    if request.method == "POST":
        # Show back what was submitted, not what is still on disk.
        values = {
            "refresh_minutes": request.form.get("refresh_minutes", "").strip(),
            "brief_time": request.form.get("brief_time", "").strip(),
        }
        minutes, brief = None, None
        try:
            minutes = int(values["refresh_minutes"])
        except ValueError:
            pass
        if minutes not in allowed:
            problems.append("Pick one of the calendar intervals offered.")
        try:
            # <input type="time"> posts "HH:MM", but "HH:MM:SS" with a step set.
            brief = time.fromisoformat(values["brief_time"]).strftime("%H:%M")
        except ValueError:
            problems.append("The time the daily headline is written should look like 06:00.")

        if not problems:
            config["refresh_minutes"] = minutes
            config["brief_time"] = config_module.quoted(brief)
            save(config)
            flash("Saved.", "ok")
            return redirect(url_for("settings.refresh"))

    return render_template(
        "settings/refresh.html", config=config, values=values,
        problems=problems, choices=choices,
    )


@bp.route("/refresh-now", methods=["POST"])
def refresh_now():
    """Fetch the calendars and nothing else — the free half of "Rewrite daily headline"."""
    config = current_config()
    try:
        payload = refresh_calendars(config, current_store())
    except GenerationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("settings.home"))
    except Exception as exc:  # a broken feed or an unwritable file shouldn't 500 the UI
        log.exception("Calendar refresh failed")
        flash(f"Could not refresh the calendars: {exc}", "error")
        return redirect(url_for("settings.home"))

    count = len(payload.get("events") or [])
    days = int(config.get("calendar_days_ahead") or 14)
    broken = [s for s in payload.get("calendar_statuses") or [] if s.get("ok") is False]
    message = f"Calendars refreshed — {count} event{'' if count == 1 else 's'} over the next {days} days."
    if broken:
        # Named, because "which one" is the first thing anybody asks. The URL
        # stays out of it: it is a password.
        message += (f" {len(broken)} didn't answer: "
                    f"{', '.join(sorted(s['label'] for s in broken))}.")
    flash(message, "error" if broken else "ok")
    return redirect(url_for("settings.home"))


@bp.route("/system", methods=["GET", "POST"])
def system():
    """Edit the family's name, clock, location and model."""
    config = current_config()
    if request.method == "POST":
        config["family_name"] = request.form.get("family_name", "").strip()
        config["location"] = request.form.get("location", "").strip()
        timezone = request.form.get("timezone", "").strip()
        if timezone:
            config["timezone"] = timezone
        clock = request.form.get("clock", "").strip()
        if clock in CLOCKS:
            config["clock"] = clock
        model = request.form.get("claude_model", "").strip()
        if model:
            config["claude_model"] = model
        save(config)
        flash("Saved.", "ok")
        return redirect(url_for("settings.system"))

    try:
        from zoneinfo import available_timezones
        zones = sorted(available_timezones())
    except Exception:
        zones = [config.get("timezone", "UTC")]
    # Each choice is labelled with what the formatter actually prints, so the
    # example beside it cannot drift from the times on the wall.
    names = {"24h": "24-hour", "12h": "12-hour"}
    clocks = [(name, f"{names[name]} ({format_time(time(15, 45), name)})")
              for name in CLOCKS]
    return render_template("settings/system.html", config=config, zones=zones,
                           clocks=clocks)


# -- telling us something ---------------------------------------------------

NOTHING_WRITTEN = "Write something first, then press Send."
TOO_LONG = ("That is longer than this form sends. Trim it to {longest:,} characters, "
            "or email it to {support} instead.")
TOO_MUCH = ("That is more than this form takes in an hour. Email {support} and it "
            "will reach the same person.")
DID_NOT_GO = ("That did not send — the fault is ours, not yours. Try again in a "
              "minute, or email it to {support}.")
IT_WENT = "Thank you — that has gone to a person, and every one is read."


@bp.route("/feedback", methods=["GET", "POST"])
def feedback():
    """Tell us something: one form, one email, nothing stored (DIN-34).

    A 404 rather than a disabled page when there is nowhere to send it. The
    condition is `feedback.enabled()`, which is the same one the pill in
    `settings/base.html` is drawn behind, so a route that cannot work is never a
    route somebody is offered. It is also what keeps `dinkydash.mail` unimported
    on a machine with no mail provider.

    The settings guard also protects this page when parent sign-in is on.
    """
    if not feedback_module.enabled():
        abort(404)
    if request.method == "GET":
        return _feedback_page()

    message = feedback_module.clean(request.form.get("message"))
    support = feedback_module.support_address()
    if not message:
        return _feedback_page(message, NOTHING_WRITTEN)
    if len(message) > feedback_module.LONGEST:
        return _feedback_page(message, TOO_LONG.format(
            longest=feedback_module.LONGEST, support=support))

    limiter = current_app.config["FEEDBACK_LIMITER"]
    if not limiter.allow(_who_is_writing()):
        return _feedback_page(message, TOO_MUCH.format(support=support))

    # Imported here for the reason the route is gated at all: on a machine with
    # no key, nothing on this path is ever reached, so nothing imports `mail`.
    from dinkydash.mail import MailError

    try:
        feedback_module.submit(message)
    except MailError as exc:
        # The exception, never the message. What somebody wrote is theirs, and
        # what failed is our mail provider.
        log.warning("A feedback message did not go out: %s", exc)
        return _feedback_page(message, DID_NOT_GO.format(support=support))

    # That one went, and nothing of what it said.
    log.info("A feedback message was sent.")
    flash(IT_WENT, "ok")
    return redirect(url_for("settings.home"))


def _feedback_page(message=None, problem=None):
    """The form, empty or holding back what somebody has already typed."""
    return render_template("settings/feedback.html", message=message,
                           problem=problem, longest=feedback_module.LONGEST,
                           support=feedback_module.support_address())


def _who_is_writing():
    """Rate-limit feedback by the caller's address."""
    return parent.caller()
