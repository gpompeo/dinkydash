"""Sign in and out as the parent, when the install asks for it.

Registered in single mode only; `web/parent.py` says what it protects. With no
password configured both routes answer 404, so a switched-off install exposes
no new page.
"""

from flask import (Blueprint, abort, redirect, render_template, request, session,
                   url_for)

from web import parent, ratelimit, session as user_session

bp = Blueprint("parent", __name__)

WRONG = "That password didn't work."
SLOW_DOWN = "Too many tries. Wait a few minutes, then try again."


@bp.record_once
def _build_the_limiter(state):
    state.app.config.setdefault(
        "PARENT_LIMITER", ratelimit.Limiter(parent.MOST_FAILURES, parent.FAILURE_SECONDS))


@bp.before_request
def _only_when_on():
    if not parent.enabled():
        abort(404)


@bp.route("/signin", methods=["GET", "POST"])
def sign_in():
    if parent.is_parent():
        return redirect(url_for("settings.home"))
    if request.method == "GET":
        return render_template("settings/parent_signin.html")

    # Every attempt counts, right or wrong: the limiter records on asking, and
    # ten tries in a quarter of an hour is plenty for somebody who knows it.
    if not parent.limiter().allow(parent.caller()):
        return render_template("settings/parent_signin.html", problem=SLOW_DOWN), 429
    if parent.password_matches(request.form.get("password", "")):
        session.clear()
        session.permanent = True
        session[parent.PARENT] = True
        return redirect(url_for("settings.home"))
    return render_template("settings/parent_signin.html", problem=WRONG), 401


@bp.route("/signout", methods=["POST"])
def sign_out():
    user_session.sign_out()
    return redirect(url_for("parent.sign_in"))
