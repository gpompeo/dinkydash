"""The wall screen's own address when parent sign-in is on. Single mode only.

    GET /s/<token>                        the dashboard
    GET /s/<token>/manifest.webmanifest   so a tablet can save it to a home screen
    GET /s/<token>/changes                the change counter, for the board script

With sign-in on, `/` needs a session and a wall screen has nobody to sign in, so
the dashboard moves to a secret address. With sign-in off these answer 404 and
the dashboard stays at `/`.

**The token is a bearer credential.** It is random, created the first time a
parent opens the screen page in settings, and kept in `auth.json` through the
store, never in `config.yaml`. Rotating it is the only revocation. Every response
here is `noindex` and `no-store`, the page asks nothing of a third party, and a
wrong token gets the same 404 whether it was mistyped, rotated away or invented.
The token is never put in a page or a log: `auth.NoTokens` scrubs `/s/...`
from both request loggers.

**Only misses are rate limited.** A real screen reloads for years and must never
be refused; a wrong token counts against its caller.
"""

import hmac
import logging
import secrets

from flask import (Blueprint, abort, current_app, flash, make_response, redirect,
                   render_template, request, url_for)

from web import parent, ratelimit
from web.family import current_store
from web.routes.board import change_counter, manifest_for, render_board

log = logging.getLogger(__name__)

bp = Blueprint("wall", __name__)
admin_bp = Blueprint("wall_admin", __name__)

TOKEN_KEY = "screen_token"

# Thirty wrong tokens per caller an hour, like the hosted screen.
MOST_MISSES = 30
PER_SECONDS = 3600

HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store, private",
}


def screen_token(store):
    """The wall token, made on first use."""
    token = store.load_auth().get(TOKEN_KEY)
    if isinstance(token, str) and token:
        return token

    def make(auth):
        if not (isinstance(auth.get(TOKEN_KEY), str) and auth[TOKEN_KEY]):
            auth[TOKEN_KEY] = secrets.token_urlsafe(24)

    return store.update_auth(make)[TOKEN_KEY]


def token_matches(store, attempt):
    stored = store.load_auth().get(TOKEN_KEY)
    if not isinstance(stored, str) or not stored:
        return False
    return hmac.compare_digest(attempt.encode("utf-8"), stored.encode("utf-8"))


@bp.record_once
def _build_the_limiter(state):
    state.app.config.setdefault(
        "WALL_LIMITER", ratelimit.Limiter(MOST_MISSES, PER_SECONDS))


def _respond(body, status=200):
    response = make_response(body, status)
    for header, value in HEADERS.items():
        response.headers[header] = value
    return response


def _refused():
    """404 for any wrong token, 429 once a caller has missed too often."""
    if not current_app.config["WALL_LIMITER"].allow(parent.caller()):
        log.warning("Wall screen lookups from one caller are over the limit.")
        return _respond(render_template(
            "screen_refused.html", heading="Too many tries",
            detail="Wait a while, then reload this page."), 429)
    return _respond(render_template(
        "screen_refused.html", heading="This screen link does not work",
        detail="Check it against the one on your settings page. If the link "
               "was changed, every screen needs the new one."), 404)


@bp.before_request
def _only_when_on():
    if not parent.enabled():
        abort(404)


def _checked(token):
    store = current_store()
    return store if token_matches(store, token) else None


@bp.route("/s/<token>")
def board(token):
    store = _checked(token)
    if store is None:
        return _refused()
    return _respond(render_board(
        store, manifest_url=url_for("wall.manifest", token=token),
        changes_url=url_for("wall.changes", token=token)))


@bp.route("/s/<token>/manifest.webmanifest")
def manifest(token):
    store = _checked(token)
    if store is None:
        return _refused()
    return _respond(manifest_for(store.load_config(), url_for("wall.board", token=token)))


@bp.route("/s/<token>/changes")
def changes(token):
    store = _checked(token)
    if store is None:
        return _refused()
    return _respond(make_response(*change_counter(store)))


# -- a parent reads and rotates the address ---------------------------------

@admin_bp.before_request
def _parents_only():
    if not parent.enabled():
        abort(404)
    return parent.guard()


@admin_bp.route("/")
def screen_page():
    link = url_for("wall.board", token=screen_token(current_store()), _external=True)
    return _respond(render_template("settings/wall_link.html", link=link))


@admin_bp.route("/rotate", methods=["POST"])
def rotate():
    current_store().update_auth(
        lambda auth: auth.__setitem__(TOKEN_KEY, secrets.token_urlsafe(24)))
    flash("New screen link made. Every screen needs it.", "ok")
    return redirect(url_for("wall_admin.screen_page"))
