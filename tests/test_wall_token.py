"""The wall screen's token address in single mode, with parent sign-in on."""

import json
import logging
import stat

import pytest

from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent
from web.routes.auth import NoTokens
from web.routes.wall import TOKEN_KEY

CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - id: mia1
    name: "Mia"
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
def locked_app(store, monkeypatch):
    monkeypatch.setenv(parent.PASSWORD_VARIABLE, PASSWORD)
    monkeypatch.setenv("DINKYDASH_SECRET_KEY", "test-key-not-the-public-one")
    return create_app(store)


@pytest.fixture
def locked(locked_app):
    return client_for(locked_app)


def parent_client(app):
    client = client_for(app)
    client.get("/signin")
    client.post("/signin", data={"password": PASSWORD})
    return client


def token_of(app):
    client = parent_client(app)
    html = client.get("/settings/wall/").get_data(as_text=True)
    start = html.index("/s/") + 3
    end = html.index("<", start)
    return html[start:end].strip()


def test_with_sign_in_off_nothing_changes(open_client):
    assert open_client.get("/").status_code == 200
    assert open_client.get("/s/anything").status_code == 404
    assert open_client.get("/settings/wall/").status_code == 404


def test_plain_address_redirects_to_sign_in(locked):
    response = locked.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signin")


def test_health_check_stays_open(locked):
    assert locked.get("/healthz").status_code == 200


def test_token_address_shows_the_dashboard_without_a_session(locked_app):
    token = token_of(locked_app)
    wall = client_for(locked_app)
    response = wall.get(f"/s/{token}")
    assert response.status_code == 200
    assert "The Wilsons" in response.get_data(as_text=True)


def test_page_is_noindex_no_store_and_never_echoes_the_token(locked_app):
    token = token_of(locked_app)
    response = client_for(locked_app).get(f"/s/{token}")
    assert "noindex" in response.headers["X-Robots-Tag"]
    assert "no-store" in response.headers["Cache-Control"]
    assert token not in response.get_data(as_text=True).replace(
        f"/s/{token}/manifest.webmanifest", "").replace(f"/s/{token}/changes", "")


def test_manifest_and_counter_work_at_the_token(locked_app):
    token = token_of(locked_app)
    wall = client_for(locked_app)
    assert wall.get(f"/s/{token}/manifest.webmanifest").status_code == 200
    counter = wall.get(f"/s/{token}/changes")
    assert counter.status_code == 200 and counter.get_data(as_text=True).isdigit()
    assert f'data-changes="/s/{token}/changes"' in wall.get(f"/s/{token}").get_data(as_text=True)


def test_wrong_token_is_a_404_that_does_not_echo_it(locked):
    response = locked.get("/s/not-the-token-1234")
    assert response.status_code == 404
    assert "not-the-token-1234" not in response.get_data(as_text=True)
    assert "noindex" in response.headers["X-Robots-Tag"]


def test_no_token_made_yet_is_a_404(locked):
    assert locked.get("/s/x").status_code == 404


def test_misses_are_rate_limited(locked):
    codes = [locked.get(f"/s/wrong{i}").status_code for i in range(32)]
    assert codes[0] == 404 and codes[-1] == 429


def test_real_token_is_not_limited_by_requests(locked_app):
    token = token_of(locked_app)
    wall = client_for(locked_app)
    assert all(wall.get(f"/s/{token}").status_code == 200 for _ in range(40))


def test_token_is_in_an_owner_only_file_and_not_the_config(locked_app, store):
    token = token_of(locked_app)
    auth_path = store.base / "auth.json"
    assert json.loads(auth_path.read_text())[TOKEN_KEY] == token
    assert stat.S_IMODE(auth_path.stat().st_mode) == 0o600
    assert token not in (store.base / "config.yaml").read_text()


def test_token_is_stable_until_rotated(locked_app):
    assert token_of(locked_app) == token_of(locked_app)


def test_rotation_kills_the_old_token(locked_app):
    old = token_of(locked_app)
    client = parent_client(locked_app)
    client.get("/settings/wall/")
    response = client.post("/settings/wall/rotate")
    assert response.status_code == 302
    new = token_of(locked_app)
    assert new != old
    wall = client_for(locked_app)
    assert wall.get(f"/s/{old}").status_code == 404
    assert wall.get(f"/s/{new}").status_code == 200


def test_screen_settings_need_a_parent(locked):
    assert locked.get("/settings/wall/").status_code == 302
    assert locked.post("/settings/wall/rotate").status_code in (302, 400)


def test_access_log_scrubber_covers_the_routes():
    record = logging.LogRecord("gunicorn.access", logging.INFO, "", 0, "%(U)s", None, None)
    record.args = {"U": "/s/secret-token-abc/changes"}
    NoTokens().filter(record)
    assert "secret-token-abc" not in record.args["U"]
    record = logging.LogRecord("werkzeug", logging.INFO, "", 0, '"%s" %s', ('GET /s/secret-token-abc/manifest.webmanifest HTTP/1.1', 200), None)
    NoTokens().filter(record)
    assert "secret-token-abc" not in record.getMessage()
