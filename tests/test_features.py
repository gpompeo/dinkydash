"""Feature switches: each hides everything it owns and loses no data."""

import pytest

from dinkydash import config as config_module
from dinkydash.board import build_view
from dinkydash.store import FileStore
from tests.conftest import client_for
from tests.test_board import CONFIG as BOARD_CONFIG, TODAY, payload
from web import create_app

CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - name: "Mia"
    date_of_birth: "2017-03-15"
recurring:
  - title: "Set the table"
    choices: ["Mia"]
special_dates:
  - title: "Christmas"
    date: "12/25"
"""


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def client(config_path):
    return client_for(create_app(FileStore(config_path)))


def stored(config_path):
    return config_module.load_config(config_path)


class TestMigration:
    def test_an_existing_install_keeps_tasks_and_special_dates_and_gets_shopping_off(self):
        config = config_module.with_defaults({})
        assert config["features"] == {"tasks": True, "special_dates": True, "shopping": False}

    def test_a_partial_block_is_filled_in(self):
        config = config_module.with_defaults({"features": {"tasks": False}})
        assert config["features"] == {"tasks": False, "special_dates": True, "shopping": False}

    def test_a_junk_value_falls_back_to_the_default(self):
        config = config_module.with_defaults({"features": {"tasks": "maybe"}})
        assert config["features"]["tasks"] is True
        assert config_module.with_defaults({"features": "nope"})["features"]["tasks"] is True

    def test_defaults_are_not_shared_between_loads(self):
        first = config_module.with_defaults({})
        first["features"]["tasks"] = False
        assert config_module.with_defaults({})["features"]["tasks"] is True


class TestWall:
    def view(self, **features):
        config = config_module.with_defaults({**BOARD_CONFIG, "features": features})
        return build_view(config, payload("2026-09-03"), TODAY)

    def test_nothing_configured_looks_as_before(self):
        view = build_view(dict(BOARD_CONFIG), payload("2026-09-03"), TODAY)
        assert view["chores"] and view["countdowns"]

    def test_tasks_off_hides_the_chores_only(self):
        view = self.view(tasks=False)
        assert view["chores"] == []
        assert view["countdowns"]

    def test_special_dates_off_hides_the_whole_coming_up_card(self):
        # Birthdays are countdowns too, so none may remain.
        view = self.view(special_dates=False)
        assert view["countdowns"] == []
        assert view["chores"]


class TestSettingsHome:
    def test_the_switches_are_offered(self, client):
        html = client.get("/settings/").get_data(as_text=True)
        for name in ("tasks", "special_dates", "shopping"):
            assert f'name="{name}"' in html

    def test_switching_off_saves_and_keeps_the_data(self, client, config_path):
        client.get("/settings/")
        client.post("/settings/features", data={"tasks": "on", "shopping": "on"})
        saved = stored(config_path)
        assert saved["features"] == {"tasks": True, "special_dates": False, "shopping": True}
        assert saved["special_dates"][0]["title"] == "Christmas"

    def test_switching_back_on_restores_it(self, client, config_path):
        client.post("/settings/features", data={})
        client.post("/settings/features", data={"tasks": "on", "special_dates": "on"})
        html = client.get("/settings/special_dates").get_data(as_text=True)
        assert "Christmas" in html
        assert stored(config_path)["recurring"][0]["title"] == "Set the table"

    def test_tasks_off_hides_chores_in_settings(self, client):
        client.post("/settings/features", data={"special_dates": "on"})
        home = client.get("/settings/").get_data(as_text=True)
        assert "/settings/recurring" not in home
        assert "/settings/special_dates" in home
        assert client.get("/settings/recurring").status_code == 404

    def test_special_dates_off_hides_them_in_settings(self, client):
        client.post("/settings/features", data={"tasks": "on"})
        home = client.get("/settings/").get_data(as_text=True)
        assert "/settings/special_dates" not in home
        assert "/settings/recurring" in home
        assert client.get("/settings/special_dates").status_code == 404

    def test_the_wall_follows_the_switch(self, client):
        client.get("/settings/")
        assert "Coming up" in client.get("/").get_data(as_text=True)
        client.post("/settings/features", data={"tasks": "on"})
        wall = client.get("/").get_data(as_text=True)
        assert "Coming up" not in wall
