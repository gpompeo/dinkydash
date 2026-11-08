"""The phone page: who are you, PINs, and tabs for the features that are on."""

import json
import logging
import stat

import pytest

from dinkydash import pins
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
  - id: sam1
    name: "Sam"
    date_of_birth: "2019-06-01"
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


def pick(client, person, pin=None):
    client.get("/h/who")
    data = {"person": person}
    if pin is not None:
        data["pin"] = pin
    return client.post("/h/who", data=data)


def set_pin(client, person, pin):
    return client.post(f"/settings/pins/{person}", data={"pin": pin})


class TestPinHashing:
    def test_a_pin_is_four_to_eight_digits(self):
        assert all(pins.valid_pin(p) for p in ("1234", "12345678", "0000"))
        assert not any(pins.valid_pin(p) for p in ("123", "123456789", "12a4", "", " 1234", "١٢٣٤"))

    def test_the_hash_checks_and_does_not_contain_the_pin(self):
        stored = pins.hash_pin("4821")
        assert stored.startswith("scrypt$")
        assert "4821" not in stored
        assert pins.check_pin("4821", stored)
        assert not pins.check_pin("4822", stored)

    def test_the_same_pin_hashes_differently_each_time(self):
        assert pins.hash_pin("4821") != pins.hash_pin("4821")

    def test_a_malformed_hash_matches_nothing(self):
        for junk in ("", "x", "scrypt$1$2", "md5$1$1$1$AA==$AA==", None):
            assert not pins.check_pin("4821", junk)


class TestOpenInstall:
    def test_the_page_asks_who_you_are(self, open_client):
        response = open_client.get("/h")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/h/who")
        page = open_client.get("/h/who").get_data(as_text=True)
        assert "Mia" in page and "Sam" in page

    def test_picking_a_name_shows_the_phone_page(self, open_client):
        assert pick(open_client, "mia1").status_code == 302
        page = open_client.get("/h")
        assert page.status_code == 200
        assert "Mia" in page.get_data(as_text=True)

    def test_an_unknown_person_goes_back_to_the_picker(self, open_client):
        assert pick(open_client, "nobody").headers["Location"].endswith("/h/who")
        assert open_client.get("/h").status_code == 302

    def test_not_me_forgets_the_name(self, open_client):
        pick(open_client, "mia1")
        open_client.post("/h/leave")
        assert open_client.get("/h").status_code == 302

    def test_the_page_is_no_store_and_noindex(self, open_client):
        pick(open_client, "mia1")
        headers = open_client.get("/h").headers
        assert headers["Cache-Control"] == "no-store"
        assert "noindex" in headers["X-Robots-Tag"]

    def test_no_sign_in_pages_exist_for_pins(self, open_client):
        assert open_client.get("/settings/pins/").status_code == 404


class TestTabs:
    def tabs(self, client):
        pick(client, "mia1")
        page = client.get("/h").get_data(as_text=True)
        return ("Tasks" in page and 'href="/h/tasks"' in page,
                'href="/h/shopping"' in page)

    def test_only_the_features_that_are_on_get_a_tab(self, open_client, store):
        assert self.tabs(open_client) == (True, False)

        config = store.load_config()
        config["features"] = {"tasks": False, "special_dates": True, "shopping": True}
        store.save_config(config)
        assert self.tabs(open_client) == (False, True)

        config["features"] = {"tasks": False, "special_dates": True, "shopping": False}
        store.save_config(config)
        assert self.tabs(open_client) == (False, False)

    def test_a_tab_for_a_feature_that_is_off_is_not_there(self, open_client):
        pick(open_client, "mia1")
        assert open_client.get("/h/shopping").status_code == 404
        assert open_client.get("/h/tasks").status_code == 200


class TestManifest:
    def test_it_installs_through_the_phone_manifest(self, open_client):
        pick(open_client, "mia1")
        page = open_client.get("/h").get_data(as_text=True)
        assert 'rel="manifest" href="/h/manifest.webmanifest"' in page
        manifest = open_client.get("/h/manifest.webmanifest")
        body = manifest.get_json(force=True)
        assert manifest.mimetype == "application/manifest+json"
        assert body["start_url"] == "/h"
        assert body["display"] == "standalone"
        assert "Wilsons" not in manifest.get_data(as_text=True)

    def test_its_id_differs_from_the_other_two_apps(self, open_client):
        ids = {open_client.get(url).get_json(force=True)["id"]
               for url in ("/h/manifest.webmanifest", "/manifest.webmanifest",
                           "/settings/manifest.webmanifest")}
        assert len(ids) == 3

    def test_the_page_makes_no_third_party_request(self, open_client):
        pick(open_client, "mia1")
        for url in ("/h/who", "/h"):
            page = open_client.get(url).get_data(as_text=True)
            assert "http://" not in page and "https://" not in page.replace(
                "https://www.w3.org", "")


class TestSettingPins:
    def test_a_parent_sets_a_pin_and_it_is_hashed_in_auth_json(self, locked_app, store):
        client = parent_client(locked_app)
        assert set_pin(client, "mia1", "4821").status_code == 302
        auth_file = store.base / "auth.json"
        stored = json.loads(auth_file.read_text())["pins"]["mia1"]
        assert pins.check_pin("4821", stored)
        assert "4821" not in auth_file.read_text()
        assert "4821" not in (store.base / "config.yaml").read_text()

    def test_the_file_is_owner_only(self, locked_app, store):
        set_pin(parent_client(locked_app), "mia1", "4821")
        assert stat.S_IMODE((store.base / "auth.json").stat().st_mode) == 0o600

    def test_a_bad_pin_is_refused_in_plain_english(self, locked_app, store):
        client = parent_client(locked_app)
        client.post("/settings/pins/mia1", data={"pin": "12"})
        assert not (store.base / "auth.json").exists()
        assert b"4 to 8 digits" in client.get("/settings/pins/").data

    def test_a_parent_can_reset_a_pin(self, locked_app, store):
        client = parent_client(locked_app)
        set_pin(client, "mia1", "4821")
        client.post("/settings/pins/mia1/reset")
        assert "mia1" not in store.load_auth()["pins"]
        member = client_for(locked_app)
        assert pick(member, "mia1").headers["Location"].endswith("/h")

    def test_an_unknown_person_is_a_404(self, locked_app):
        assert set_pin(parent_client(locked_app), "nobody", "4821").status_code == 404

    def test_pins_need_a_parent_session(self, locked):
        assert locked.get("/settings/pins/").status_code == 302
        assert set_pin(locked, "mia1", "4821").status_code == 302

    def test_other_keys_in_the_auth_file_survive(self, locked_app, store):
        store.update_auth(lambda auth: auth.update({"screen_token": "keep-me"}))
        set_pin(parent_client(locked_app), "mia1", "4821")
        assert store.load_auth()["screen_token"] == "keep-me"

    def test_settings_home_links_to_pins_when_sign_in_is_on(self, locked_app):
        assert b"Phone PINs" in parent_client(locked_app).get("/settings/").data

    def test_settings_home_does_not_when_it_is_off(self, open_client):
        assert b"Phone PINs" not in open_client.get("/settings/").data


class TestSignInOn:
    @pytest.fixture
    def with_pin(self, locked_app):
        set_pin(parent_client(locked_app), "mia1", "4821")
        return client_for(locked_app)

    def test_the_page_is_refused_without_a_session(self, locked):
        response = locked.get("/h")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/h/who")

    def test_the_right_pin_continues(self, with_pin):
        assert pick(with_pin, "mia1", "4821").headers["Location"].endswith("/h")
        assert with_pin.get("/h").status_code == 200

    def test_a_wrong_pin_is_refused(self, with_pin):
        assert pick(with_pin, "mia1", "0000").status_code == 401
        assert with_pin.get("/h").status_code == 302

    def test_no_pin_typed_is_refused(self, with_pin):
        assert pick(with_pin, "mia1").status_code == 401
        assert with_pin.get("/h").status_code == 302

    def test_a_person_without_a_pin_just_picks_their_name(self, with_pin):
        assert pick(with_pin, "sam1").headers["Location"].endswith("/h")

    def test_only_a_person_with_a_pin_is_asked_for_one(self, with_pin):
        page = with_pin.get("/h/who").get_data(as_text=True)
        assert 'name="pin"' in page
        assert page.count('name="pin"') == 1

    def test_a_signed_in_parent_may_pick_anybody(self, locked_app, with_pin):
        client = parent_client(locked_app)
        assert pick(client, "mia1").headers["Location"].endswith("/h")
        # ...and is still signed in to the settings.
        assert client.get("/settings/").status_code == 200

    def test_a_pin_left_over_from_sign_in_is_not_asked_for_when_it_is_off(
            self, locked_app, store, monkeypatch):
        set_pin(parent_client(locked_app), "mia1", "4821")
        monkeypatch.delenv(parent.PASSWORD_VARIABLE)
        client = client_for(create_app(store))
        assert pick(client, "mia1").headers["Location"].endswith("/h")

    def test_wrong_pins_are_rate_limited(self, with_pin):
        for _ in range(10):
            assert pick(with_pin, "mia1", "0000").status_code == 401
        assert pick(with_pin, "mia1", "0000").status_code == 429
        assert pick(with_pin, "mia1", "4821").status_code == 429

    def test_the_pin_is_not_logged_or_echoed(self, with_pin, caplog):
        with caplog.at_level(logging.DEBUG):
            response = pick(with_pin, "mia1", "9137")
            pick(with_pin, "mia1", "4821")
        assert "9137" not in caplog.text and "4821" not in caplog.text
        assert "9137" not in response.get_data(as_text=True)

    def test_a_member_session_does_not_open_the_settings(self, with_pin):
        pick(with_pin, "mia1", "4821")
        assert with_pin.get("/settings/").status_code == 302
