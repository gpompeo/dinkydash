"""Optional parent sign-in: off by default, a password and a session when on."""

import logging

import pytest

from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent

CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - name: "Mia"
    date_of_birth: "2017-03-15"
"""

PASSWORD = "correct horse battery"


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return FileStore(path)


@pytest.fixture
def open_client(store, monkeypatch):
    monkeypatch.delenv(parent.PASSWORD_VARIABLE, raising=False)
    return client_for(create_app(store))


@pytest.fixture
def locked(store, monkeypatch):
    monkeypatch.setenv(parent.PASSWORD_VARIABLE, PASSWORD)
    monkeypatch.setenv("DINKYDASH_SECRET_KEY", "test-key-not-the-public-one")
    return client_for(create_app(store))


def sign_in(client, password=PASSWORD):
    client.get("/signin")
    return client.post("/signin", data={"password": password})


class TestOffByDefault:
    def test_settings_are_open(self, open_client):
        assert open_client.get("/settings/").status_code == 200

    def test_the_sign_in_pages_do_not_exist(self, open_client):
        assert open_client.get("/signin").status_code == 404
        assert open_client.post("/signout").status_code == 404

    def test_no_sign_out_button_is_offered(self, open_client):
        assert b"/signout" not in open_client.get("/settings/").data


class TestWhenOn:
    def test_settings_need_a_session(self, locked):
        response = locked.get("/settings/")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/signin")

    def test_a_write_is_refused_without_a_session(self, locked, store):
        locked.get("/signin")
        response = locked.post("/settings/features", data={})
        assert response.status_code == 302

    def test_the_wrong_password_is_refused(self, locked):
        response = sign_in(locked, "nope")
        assert response.status_code == 401
        assert locked.get("/settings/").status_code == 302

    def test_the_right_password_opens_settings(self, locked):
        assert sign_in(locked).status_code == 302
        assert locked.get("/settings/").status_code == 200

    def test_signing_out_closes_them_again(self, locked):
        sign_in(locked)
        assert locked.post("/signout").status_code == 302
        assert locked.get("/settings/").status_code == 302

    def test_the_session_cookie_lasts_thirty_days(self, locked):
        cookie = sign_in(locked).headers["Set-Cookie"]
        assert "Max-Age=2592000" in cookie or "Expires=" in cookie
        assert "HttpOnly" in cookie

    def test_the_wall_dashboard_is_unchanged(self, locked):
        assert locked.get("/").status_code == 200

    def test_the_session_cookie_is_signed_with_the_secret_key(self, store, monkeypatch):
        monkeypatch.setenv(parent.PASSWORD_VARIABLE, PASSWORD)
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "key-one")
        one = client_for(create_app(store))
        sign_in(one)
        cookie = one.get_cookie("session")
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "key-two")
        two = client_for(create_app(store))
        two.set_cookie("session", cookie.value)
        assert two.get("/settings/").status_code == 302


class TestConfiguration:
    def test_it_refuses_to_start_on_the_public_key(self, store, monkeypatch):
        monkeypatch.setenv(parent.PASSWORD_VARIABLE, PASSWORD)
        monkeypatch.delenv("DINKYDASH_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="DINKYDASH_SECRET_KEY"):
            create_app(store)


class TestCsrf:
    def test_a_sign_in_without_the_token_is_refused(self, locked):
        from flask.testing import FlaskClient

        raw = FlaskClient.open
        response = raw(locked, "/signin", method="POST", data={"password": PASSWORD})
        assert response.status_code == 400


class TestRateLimit:
    def test_too_many_attempts_are_refused(self, locked):
        for _ in range(parent.MOST_FAILURES):
            assert sign_in(locked, "nope").status_code == 401
        assert sign_in(locked, "nope").status_code == 429
        # Even the right password waits out the window.
        assert sign_in(locked).status_code == 429

    def test_the_password_is_not_logged(self, locked, caplog):
        with caplog.at_level(logging.DEBUG):
            sign_in(locked, "hunter2-wrong")
            sign_in(locked)
        assert "hunter2-wrong" not in caplog.text
        assert PASSWORD not in caplog.text
