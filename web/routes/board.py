"""The dashboard and preview harness for the target screen sizes."""

import os
from datetime import timedelta

from urllib.parse import urlencode

from flask import (Blueprint, abort, current_app, redirect, render_template,
                   request, url_for)

from dinkydash import board as board_view
from dinkydash import pages as pages_module
from dinkydash import config as config_module
from dinkydash.config import THEME_COLOURS, theme_of
from dinkydash import streaks
from web import manifest as manifest_module
from web.family import current_store
from web.urls import board_path

bp = Blueprint("board", __name__)

PREVIEW_SIZES = [
    ("Raspberry Pi panel", 800, 480),
    ("TV / monitor", 1280, 720),
    ("Old iPad", 1024, 768),
]

OPEN_WITHOUT_SIGN_IN = {"board.healthz"}

@bp.before_request
def _needs_a_family():
    """Protect dashboard routes when parent sign-in is enabled."""
    if request.endpoint in OPEN_WITHOUT_SIGN_IN:
        return None
    # With sign-in on, the wall uses `/s/<token>`.
    from web import parent
    return parent.guard()


def change_counter(store):
    """The store's change token as a bare number, with no caching."""
    token = getattr(store, "change_token", None)
    if token is None:
        abort(404)
    return str(token()), 200, {"Cache-Control": "no-store", "X-Robots-Tag": "noindex",
                               "Content-Type": "text/plain; charset=utf-8"}


def current_config():
    return current_store().load_config()


@bp.route("/")
def index():
    """The dashboard, protected by parent sign-in when enabled."""
    return render_board(current_store())


def screen_setup(config):
    """This screen's setup from its own link, and the pages it may show.

    The link is the whole setup, so another screen on the same household is
    unaffected and nothing is stored.
    """
    setup, _ = pages_module.parse_setup(request.args)
    shown = pages_module.available(config)
    return setup, shown, {
        "touch": setup.touch,
        "initial": pages_module.initial_key(setup.page, shown),
        "rotate": setup.rotate,
        "interval": setup.interval,
        "main_label": next((p.label for p in shown if p.key == "main"), "Dashboard"),
        "pages": shown,
    }


def setup_suffix():
    """`?mode=touch&...` for this request's setup, or nothing at the defaults."""
    setup, _ = pages_module.parse_setup(request.args)
    query = pages_module.link_query(setup)
    return "?" + urlencode(query) if query else ""


@bp.route("/changes")
def changes():
    """The wall's change counter: a number and nothing else, same access as `/`."""
    return change_counter(current_store())


def render_board(store, manifest_url=None, changes_url=None):
    """Render the dashboard from the file-backed household store."""
    config = store.load_config()
    payload = store.load_payload(config)
    now = config_module.now_for(config)
    completions = store.load_completions(now.date() - timedelta(days=streaks.MAX_DAYS))
    view = board_view.build_view(config, payload, now.date(), now=now,
                                 completions=completions, shopping=store.load_shopping())
    if changes_url is None:
        changes_url = url_for("board.changes")
    view["screen"] = screen_setup(config)[2]
    return render_template("board.html", view=view, changes_url=changes_url,
                           manifest_url=(manifest_url or url_for("board.manifest")) + setup_suffix())


def manifest_for(config, url, suffix=""):
    """A wall panel saved to a tablet's home screen: full screen, no browser.

    Separate from the settings manifest, and deliberately so — one is a screen
    you leave on, the other is a page you visit. They must keep different
    `id`s: share one and the phone treats them as a single app.
    """
    # The saved app keeps its own background until the dashboard paints, so it has
    # to match the theme or a dark dashboard flashes white on every open.
    colour = THEME_COLOURS[theme_of(config)]
    return manifest_module.response(
        id=url,
        name=config.get("family_name") or "PompDash",
        short_name=config.get("family_name") or "PompDash",
        description="Today's agenda, whose turn it is, and what is coming up.",
        start_url=url + suffix,
        display="fullscreen",
        background_color=colour,
        theme_color=colour,
    )


@bp.route("/manifest.webmanifest")
def manifest():
    return manifest_for(current_config(), url_for("board.index"), setup_suffix())


@bp.route("/preview")
def preview():
    """Show the dashboard at each target screen size."""
    return render_template("preview.html", sizes=PREVIEW_SIZES,
                           board_url=board_path())


@bp.route("/healthz")
def healthz():
    """Report process health without reading household data."""
    return {
        "status": "ok",
        "commit": os.environ.get("GIT_SHA") or "unknown",
    }, 200, {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}
