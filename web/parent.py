"""Optional parent sign-in for a self-hosted install.

With `DINKYDASH_PARENT_PASSWORD` unset nothing here does anything: the settings
are open on the local network. With it set, everything
under `/settings` needs a session, and the session comes from typing that
password at `/signin`.

**The password lives in the environment and nowhere else.** It is never
written to a file, a log line or a template. It is compared in constant time.

**The cookie is the login, so it must be signed with a key only the owner
knows.** The fallback key is public (it is in the source), so turning sign-in
on without `DINKYDASH_SECRET_KEY` refuses to start rather than offering a lock
anybody can forge a key for.

**Sign-in attempts are limited per caller.** On a home network the socket
address is private, which `ratelimit.client_ip` deliberately treats as "cannot
tell callers apart"; here the socket address is used anyway, because a
limiter that never fires on a LAN would be no limiter. Behind a reverse proxy
every caller then shares one bucket, which errs towards refusing too much.
"""

import hmac
import os

from flask import current_app, redirect, request, session, url_for

from . import ratelimit

PASSWORD_VARIABLE = "DINKYDASH_PARENT_PASSWORD"

# The session key that says a parent has signed in.
PARENT = "parent"

# Ten wrong passwords in a quarter of an hour, per caller.
MOST_FAILURES = 10
FAILURE_SECONDS = 900


def password():
    """The configured parent password, or "" when sign-in is off."""
    return os.environ.get(PASSWORD_VARIABLE, "")


def enabled():
    """Sign-in is on: a password is set, in single mode (cloud has its own)."""
    from . import SINGLE

    return bool(password()) and current_app.config["MODE"] == SINGLE


def is_parent():
    return bool(session.get(PARENT))


def check_configuration(app):
    """Refuse a lock that anyone could pick: sign-in needs a private key."""
    from . import SELF_HOSTED_KEY

    if password() and app.secret_key == SELF_HOSTED_KEY:
        raise RuntimeError(
            f"{PASSWORD_VARIABLE} is set but DINKYDASH_SECRET_KEY is not. "
            "Sessions are signed with that key, and the default is public."
        )


def guard():
    """Single mode with sign-in on: no parent session, no settings."""
    if not enabled() or is_parent():
        return None
    return redirect(url_for("parent.sign_in"))


def caller():
    return ratelimit.client_ip(request) or request.remote_addr or ""


def password_matches(attempt):
    # Bytes, for the reason `session.check_csrf` compares bytes.
    return hmac.compare_digest(attempt.encode("utf-8"), password().encode("utf-8"))


def limiter():
    return current_app.config["PARENT_LIMITER"]
