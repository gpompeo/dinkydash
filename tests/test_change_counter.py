"""The change counter: moves on each kind of change, carries no content."""

import pytest

from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent

CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - id: mia1
    name: "Mia"
    date_of_birth: "2017-03-15"
"""


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return FileStore(path)


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.delenv(parent.PASSWORD_VARIABLE, raising=False)
    return client_for(create_app(store))


def bump(path, text):
    """Rewrite a file with different content and a different modification time."""
    path.write_text(text)
    stamp = path.stat().st_mtime_ns + 1_000_000_000
    import os
    os.utime(path, ns=(stamp, stamp))


def test_token_is_a_number(store):
    assert isinstance(store.change_token(), int)


def test_token_is_steady_when_nothing_changes(store):
    assert store.change_token() == store.change_token()


def test_token_moves_when_the_config_changes(store):
    before = store.change_token()
    config = store.load_config()
    config["family_name"] = "The Joneses"
    store.save_config(config)
    assert store.change_token() != before


def test_token_moves_when_the_payload_changes(store):
    before = store.change_token()
    config = store.load_config()
    store.save_brief(config, {"headline": "Hello"})
    assert store.change_token() != before


@pytest.mark.parametrize("name", ["completions.json", "shopping.json"])
def test_token_moves_when_those_files_change(store, name):
    path = store.base / name
    before = store.change_token()
    bump(path, "[]")
    created = store.change_token()
    assert created != before
    bump(path, '[{"x": 1}]')
    assert store.change_token() != created


def test_token_carries_no_content(store):
    config = store.load_config()
    store.save_brief(config, {"headline": "Secret birthday for Mia"})
    token = str(store.change_token())
    assert "Mia" not in token and "Secret" not in token and token.isdigit()


def test_wall_endpoint_is_a_bare_number_and_no_store(client):
    response = client.get("/changes")
    assert response.status_code == 200
    assert response.data.decode().isdigit()
    assert "no-store" in response.headers["Cache-Control"]
    assert response.mimetype == "text/plain"


def test_wall_endpoint_follows_a_change(client, store):
    first = client.get("/changes").data
    store.save_brief(store.load_config(), {"headline": "Changed"})
    assert client.get("/changes").data != first


def test_wall_page_tells_the_script_where_to_poll(client):
    html = client.get("/").data.decode()
    assert 'data-changes="/changes"' in html


def test_phone_endpoint_needs_a_name_picked(client):
    response = client.get("/h/changes")
    assert response.status_code == 401
    assert response.data == b""
    assert "no-store" in response.headers["Cache-Control"]


def test_phone_endpoint_answers_once_a_name_is_picked(client):
    client.get("/h/who")
    client.post("/h/who", data={"person": "mia1"})
    response = client.get("/h/changes")
    assert response.status_code == 200
    assert response.data.decode().isdigit()
    assert "no-store" in response.headers["Cache-Control"]


def test_script_polls_quietly_and_pauses_while_hidden(client):
    html = client.get("/").data.decode()
    assert "POLL_SECONDS = 15" in html
    assert "document.hidden" in html
    assert 'addEventListener("visibilitychange"' in html
