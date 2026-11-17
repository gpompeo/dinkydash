"""Task settings live at /settings/tasks; /settings/recurring keeps working, identically."""

import pytest

from dinkydash import config as config_module
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent

CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - id: mia00001
    name: "Mia"
    date_of_birth: "2017-03-15"
tasks:
  - id: table01
    title: "Set the table"
    recurrence: {kind: daily}
    assignment: {mode: rotate, people: [mia00001], offset: 0}
  - id: bins001
    title: "Bins"
    recurrence: {kind: daily}
    assignment: {mode: rotate, people: [mia00001], offset: 0}
"""

PASSWORD = "correct horse battery"
BOTH = ["tasks", "recurring"]


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def client(config_path, monkeypatch):
    monkeypatch.delenv(parent.PASSWORD_VARIABLE, raising=False)
    return client_for(create_app(FileStore(config_path)))


def saved(config_path):
    return config_module.load_config(config_path)["tasks"]


def titles(config_path):
    return [t["title"] for t in saved(config_path)]


def new_task(title="Walk the dog"):
    return {"title": title, "rec_kind": "daily", "mode": "anyone"}


@pytest.mark.parametrize("section", BOTH)
class TestBothPaths:
    def test_the_list_shows_the_tasks(self, client, section):
        html = client.get(f"/settings/{section}").get_data(as_text=True)
        assert "Set the table" in html and "Bins" in html

    def test_a_task_is_created_once(self, client, config_path, section):
        response = client.post(f"/settings/{section}/new", data=new_task())
        assert response.status_code == 302
        assert titles(config_path) == ["Set the table", "Bins", "Walk the dog"]

    def test_the_edit_page_opens_and_a_task_is_edited(self, client, config_path, section):
        assert b"Set the table" in client.get(f"/settings/{section}/table01").data
        client.post(f"/settings/{section}/table01", data=new_task("Lay the table"))
        assert titles(config_path) == ["Lay the table", "Bins"]

    def test_a_task_is_deleted_once(self, client, config_path, section):
        client.post(f"/settings/{section}/table01/delete", data={"confirmed": "yes"})
        assert titles(config_path) == ["Bins"]

    def test_a_task_is_moved_once(self, client, config_path, section):
        client.post(f"/settings/{section}/table01/move", data={"direction": "down"})
        assert titles(config_path) == ["Bins", "Set the table"]

    def test_an_unknown_task_is_a_404(self, client, section):
        assert client.get(f"/settings/{section}/nosuchid").status_code == 404


class TestCanonical:
    def test_the_home_page_links_to_tasks_only(self, client):
        html = client.get("/settings/").get_data(as_text=True)
        assert 'href="/settings/tasks"' in html
        assert "/settings/recurring" not in html

    @pytest.mark.parametrize("path", ["/settings/tasks", "/settings/tasks/new",
                                      "/settings/tasks/table01"])
    def test_pages_link_and_post_to_tasks_only(self, client, path):
        assert "/settings/recurring" not in client.get(path).get_data(as_text=True)

    def test_saving_redirects_to_the_canonical_list(self, client):
        response = client.post("/settings/recurring/new", data=new_task())
        assert response.headers["Location"].endswith("/settings/tasks")

    def test_a_saved_task_keeps_the_stored_format(self, client, config_path):
        client.post("/settings/recurring/new", data={**new_task(), "mode": "rotate",
                                                     "choices": ["mia00001"]})
        task = saved(config_path)[-1]
        assert task["recurrence"] == {"kind": "daily"}
        assert task["assignment"]["mode"] == "rotate"
        assert task["assignment"]["people"] == ["mia00001"]
        assert "mode" not in task and "rec" not in task


class TestFeatureSwitch:
    @pytest.fixture
    def off(self, client):
        client.post("/settings/features", data={"special_dates": "on"})
        return client

    @pytest.mark.parametrize("section", BOTH)
    def test_every_task_path_is_a_404(self, off, config_path, section):
        before = config_path.read_text()
        assert off.get(f"/settings/{section}").status_code == 404
        assert off.get(f"/settings/{section}/new").status_code == 404
        assert off.get(f"/settings/{section}/table01").status_code == 404
        assert off.post(f"/settings/{section}/new", data=new_task()).status_code == 404
        assert off.post(f"/settings/{section}/table01/delete",
                        data={"confirmed": "yes"}).status_code == 404
        assert off.post(f"/settings/{section}/table01/move",
                        data={"direction": "down"}).status_code == 404
        assert titles(config_path) == ["Set the table", "Bins"]
        assert "Walk the dog" not in config_path.read_text()
        assert before.count("table01") == config_path.read_text().count("table01")


class TestSignIn:
    @pytest.fixture
    def locked(self, config_path, monkeypatch):
        monkeypatch.setenv(parent.PASSWORD_VARIABLE, PASSWORD)
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "test-key-not-the-public-one")
        return client_for(create_app(FileStore(config_path)))

    @pytest.mark.parametrize("section", BOTH)
    def test_signed_out_is_sent_to_sign_in_and_nothing_is_written(self, locked, config_path, section):
        locked.get("/signin")
        for response in (locked.get(f"/settings/{section}"),
                         locked.post(f"/settings/{section}/new", data=new_task()),
                         locked.post(f"/settings/{section}/table01/delete",
                                     data={"confirmed": "yes"}),
                         locked.post(f"/settings/{section}/table01/move",
                                     data={"direction": "down"})):
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/signin")
        assert titles(config_path) == ["Set the table", "Bins"]

    @pytest.mark.parametrize("section", BOTH)
    def test_signed_in_works(self, locked, config_path, section):
        locked.get("/signin")
        locked.post("/signin", data={"password": PASSWORD})
        assert locked.get(f"/settings/{section}").status_code == 200
        locked.post(f"/settings/{section}/new", data=new_task())
        assert "Walk the dog" in titles(config_path)


@pytest.mark.parametrize("section", BOTH)
class TestCsrf:
    def test_writes_without_a_token_are_refused(self, config_path, section):
        app = create_app(FileStore(config_path))
        app.config["TESTING"] = True
        plain = app.test_client()
        before = config_path.read_text()
        assert plain.post(f"/settings/{section}/new", data=new_task()).status_code == 400
        assert plain.post(f"/settings/{section}/table01", data=new_task()).status_code == 400
        assert plain.post(f"/settings/{section}/table01/delete",
                          data={"confirmed": "yes"}).status_code == 400
        assert plain.post(f"/settings/{section}/table01/move",
                          data={"direction": "down"}).status_code == 400
        plain.get(f"/settings/{section}")
        assert plain.post(f"/settings/{section}/new",
                          data={**new_task(), "csrf_token": "wrong"}).status_code == 400
        assert config_path.read_text() == before
