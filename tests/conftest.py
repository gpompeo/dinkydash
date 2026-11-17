"""Browser-like test client carrying CSRF tokens on writes."""

from flask.testing import FlaskClient

CSRF_KEY = "csrf"
CSRF_FIELD = "csrf_token"


class SigningClient(FlaskClient):
    """A client that carries this session's CSRF token on every write.

    A caller-supplied `headers={"Cookie": ...}` is folded into this client's
    own cookie jar first, rather than left on the request: `session_transaction`
    below reads and re-saves that jar for the CSRF token, and Werkzeug builds
    a request's `Cookie` header from the jar alone once it holds anything,
    silently dropping a cookie passed as a plain header instead of merging it.
    """

    WRITES = {"POST", "PUT", "PATCH", "DELETE"}

    def open(self, *args, **kwargs):
        headers = kwargs.get("headers")
        extra_cookie = headers.pop("Cookie", None) if headers else None
        if extra_cookie:
            for part in extra_cookie.split(";"):
                name, _, value = part.strip().partition("=")
                if name:
                    self.set_cookie(name, value)
        if kwargs.get("method", "GET").upper() in self.WRITES:
            with self.session_transaction() as stored:
                token = stored.get(CSRF_KEY)
                if not token:
                    token = stored[CSRF_KEY] = "a-test-csrf-token"
            data = kwargs.get("data")
            if data is None:
                kwargs["data"] = {CSRF_FIELD: token}
            elif isinstance(data, dict):
                data.setdefault(CSRF_FIELD, token)
        return super().open(*args, **kwargs)


def client_for(app):
    """`app.test_client()`, signing its writes. What every fixture here uses."""
    app.test_client_class = SigningClient
    app.config["TESTING"] = True
    return app.test_client()
