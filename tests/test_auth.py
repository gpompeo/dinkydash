"""Session cookies and CSRF protection for the self-hosted app."""

import pathlib
import re
import pytest
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app

REPO = pathlib.Path(__file__).resolve().parent.parent
CONFIG = 'family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n'

@pytest.fixture
def single(tmp_path):
    (tmp_path / "config.yaml").write_text(CONFIG)
    return create_app(FileStore(tmp_path / "config.yaml"))

def test_cookie_flags(single):
    assert single.config["SESSION_COOKIE_SECURE"] is False
    assert single.config["SESSION_COOKIE_HTTPONLY"] is True
    assert single.config["SESSION_COOKIE_SAMESITE"] == "Lax"


class TestCsrf:
    """A page in another tab cannot submit changes on behalf of a family."""

    @pytest.fixture
    def plain(self, single):
        """A client that does *not* fill the token in for itself."""
        single.config["TESTING"] = True
        return single.test_client()

    def test_a_write_with_no_token_is_refused(self, plain):
        response = plain.post("/settings/system", data={"family_name": "The Bakers"})
        assert response.status_code == 400

    def test_a_write_with_the_wrong_token_is_refused(self, plain):
        plain.get("/settings/system")  # mints a real one into the session
        response = plain.post("/settings/system",
                              data={"family_name": "The Bakers",
                                    "csrf_token": "not-the-one"})
        assert response.status_code == 400

    def test_the_right_token_goes_through(self, single):
        client = client_for(single)
        assert client.post("/settings/system",
                           data={"family_name": "The Bakers",
                                 "timezone": "UTC"}).status_code == 302

    def test_a_token_full_of_emoji_is_a_400_not_a_500(self, plain):
        # `hmac.compare_digest` raises TypeError on a non-ASCII `str`.
        plain.get("/settings/system")
        assert plain.post("/settings/system",
                          data={"family_name": "The Bakers",
                                "csrf_token": "🎈🎈🎈"}).status_code == 400

    def test_a_read_needs_nothing(self, plain):
        assert plain.get("/settings/").status_code == 200

    def test_the_refusal_does_not_write_anything(self, plain, tmp_path):
        before = (tmp_path / "config.yaml").read_text()
        plain.post("/settings/system", data={"family_name": "The Bakers"})
        assert (tmp_path / "config.yaml").read_text() == before

    def test_every_form_that_writes_carries_the_field(self):
        """A form added without one is a form that stops working, silently."""
        missing, seen = [], 0
        for path in (REPO / "web" / "templates").rglob("*.html"):
            text = path.read_text()
            for form in re.findall(r"<form\b.*?</form>", text, re.S):
                if 'method="post"' not in form:
                    continue
                seen += 1
                if "csrf_token" not in form:
                    missing.append(str(path.relative_to(REPO)))
        assert missing == []
        # Or a regex that stopped matching would make this pass by finding none.
        assert seen >= 9
