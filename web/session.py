"""Signed local sessions, cookie flags and CSRF protection."""

import hmac
import secrets
from datetime import timedelta

from flask import abort, request, session
from flask.sessions import SecureCookieSessionInterface

# The CSRF token: where it is kept, and what the form calls it.
CSRF_KEY = "csrf"
CSRF_FIELD = "csrf_token"

# Everything that must not change anything. RFC 9110's safe methods.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# How long a sign-in lasts. A dashboard on a wall is furniture and its owner should
# not be signed out of the settings for it every fortnight.
SESSION_LIFETIME = timedelta(days=30)


def configure(app):
    """Cookie flags, the CSRF check, and `csrf_token()` for the templates."""
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        PERMANENT_SESSION_LIFETIME=SESSION_LIFETIME,
    )
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.before_request(check_csrf)
    app.session_interface = CookieSession()


class CookieSession(SecureCookieSessionInterface):
    """Flask's signed cookie, except that a static file never carries it.

    Flask re-signs a permanent session on every response — the signature
    carries a timestamp, so the cookie's value changes each time — and marks
    any response that read the session `Vary: Cookie`. Right for a page, and
    wrong for a font: a cached file that varies on a cookie whose value moves
    with every page is a file the cache can never match, however long it was
    told to keep it. `web/assets.py` gives a versioned static file a year;
    this is what makes the year mean anything.
    """

    def save_session(self, app, session, response):
        if request.endpoint == "static":
            return
        super().save_session(app, session, response)


# -- who is signed in -------------------------------------------------------

def sign_out():
    session.clear()


# -- proving a form came from us --------------------------------------------

def csrf_token():
    """The token for this session, minted on first use.

    A template global, so a form gets it by calling it — there is no route that
    has to remember to pass it, and therefore no form that quietly loses it.
    """
    token = session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_KEY] = token
    return token


def check_csrf():
    """Refuse any write that did not carry this session's token.

    Registered as an app-wide `before_request` rather than per blueprint, so a
    route added later is covered by having been added. `compare_digest` because
    this is the one comparison in the login path where both sides are known to
    the attacker's browser and a timing difference would be real.

    **There is no switch to turn this off**, and that is on purpose: a
    `CSRF_ENABLED` flag is a flag somebody eventually sets wrongly in
    production, and it would leave the accepting path untested everywhere else.
    The test client in `tests/conftest.py` carries the token the way a browser
    does, so every form POST in the suite goes through this function.
    """
    if request.method in SAFE_METHODS:
        return None
    held = session.get(CSRF_KEY) or ""
    sent = request.form.get(CSRF_FIELD) or request.headers.get("X-CSRF-Token") or ""
    # Compared as bytes, and not for tidiness: `compare_digest` raises
    # `TypeError` on a `str` with a non-ASCII character in it, and the string
    # being compared came out of a form somebody else filled in. A 500 where a
    # 400 belongs is a bug anyone could trigger with one emoji.
    if not held or not hmac.compare_digest(sent.encode("utf-8"), held.encode("utf-8")):
        # 400 rather than 403: the usual cause is a page left open until the
        # session behind it went, and the fix is to reload it.
        abort(400, "That page was out of date. Go back, reload it and try again.")
    return None
