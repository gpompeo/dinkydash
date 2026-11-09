"""The shopping list: caps, ticking, the twenty-four-hour clear, and the phone routes."""

from datetime import datetime, timedelta, timezone

import pytest

from dinkydash import shopping
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def add(items, text="Milk", quantity="", by="mia1", now=NOW):
    return shopping.add_item(items, text, quantity, by, now)


class TestRules:
    def test_adding_trims_and_records_who_and_when(self):
        items, problem = add([], "  Milk ", " 2 litres ")
        assert problem is None
        assert items[0]["text"] == "Milk" and items[0]["quantity"] == "2 litres"
        assert items[0]["added_by"] == "mia1" and items[0]["bought_at"] is None
        assert items[0]["added_at"] == NOW.isoformat(timespec="seconds") and items[0]["id"]

    def test_blank_text_is_refused_in_plain_english(self):
        items, problem = add([], "   ")
        assert items == [] and "what" in problem.lower()

    def test_text_and_quantity_caps(self):
        _, problem = add([], "x" * 81)
        assert "80" in problem
        assert add([], "x" * 80)[1] is None
        _, problem = add([], "Milk", "q" * 41)
        assert "40" in problem
        assert add([], "Milk", "q" * 40)[1] is None

    def test_the_hundred_item_cap(self):
        items = []
        for n in range(100):
            items, problem = add(items, f"Item {n}")
            assert problem is None
        items, problem = add(items, "One more")
        assert len(items) == 100 and "100" in problem

    def test_edit_keeps_who_added_it(self):
        items, _ = add([], "Milk")
        edited, problem = shopping.edit_item(items, items[0]["id"], "Oat milk", "1", NOW)
        assert problem is None
        assert edited[0]["text"] == "Oat milk" and edited[0]["added_by"] == "mia1"
        assert shopping.edit_item(items, items[0]["id"], "x" * 81, "", NOW)[1]

    def test_tick_and_untick(self):
        items, _ = add([], "Milk")
        bought = shopping.set_bought(items, items[0]["id"], True, NOW)
        assert bought[0]["bought_at"] == NOW.isoformat(timespec="seconds")
        assert shopping.set_bought(bought, items[0]["id"], False, NOW)[0]["bought_at"] is None

    def test_delete(self):
        items, _ = add([], "Milk")
        assert shopping.delete_item(items, items[0]["id"]) == []

    def test_bought_items_clear_after_twenty_four_hours(self):
        items, _ = add([], "Milk")
        items = shopping.set_bought(items, items[0]["id"], True, NOW)
        assert shopping.current(items, NOW + timedelta(hours=23)) == items
        assert shopping.current(items, NOW + timedelta(hours=24)) == []

    def test_clear_bought_keeps_the_rest(self):
        items, _ = add([], "Milk")
        items, _ = add(items, "Eggs")
        items = shopping.set_bought(items, items[0]["id"], True, NOW)
        assert [i["text"] for i in shopping.clear_bought(items)] == ["Eggs"]


CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
features:
  shopping: true
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
    c = client_for(create_app(store))
    c.post("/h/who", data={"person": "mia1"})
    return c


def texts(store):
    return [i["text"] for i in store.load_shopping()]


class TestStore:
    def test_a_missing_or_damaged_file_reads_as_empty(self, store):
        assert store.load_shopping() == []
        (store.base / "shopping.json").write_text("{nope")
        assert store.load_shopping() == []

    def test_update_round_trips(self, store):
        store.update_shopping(lambda items: add(items, "Milk")[0])
        assert texts(store) == ["Milk"]


class TestRoutes:
    def test_add_edit_tick_untick_delete(self, client, store):
        assert client.post("/h/shopping/add", data={"text": "Milk", "quantity": "2"}).status_code == 302
        item = store.load_shopping()[0]
        assert item["added_by"] == "mia1"
        client.post(f"/h/shopping/{item['id']}/edit", data={"text": "Oat milk", "quantity": ""})
        assert texts(store) == ["Oat milk"]
        client.post(f"/h/shopping/{item['id']}/tick", data={"done": "1"})
        assert store.load_shopping()[0]["bought_at"]
        client.post(f"/h/shopping/{item['id']}/tick", data={"done": "0"})
        assert store.load_shopping()[0]["bought_at"] is None
        client.post(f"/h/shopping/{item['id']}/delete")
        assert texts(store) == []

    def test_clear_bought(self, client, store):
        client.post("/h/shopping/add", data={"text": "Milk"})
        client.post("/h/shopping/add", data={"text": "Eggs"})
        milk = store.load_shopping()[0]["id"]
        client.post(f"/h/shopping/{milk}/tick", data={"done": "1"})
        client.post("/h/shopping/clear")
        assert texts(store) == ["Eggs"]

    def test_checkbox_submits_checked_and_unchecked_values(self, client, store):
        from werkzeug.datastructures import MultiDict

        client.post("/h/shopping/add", data={"text": "Milk"})
        item = store.load_shopping()[0]
        url = f"/h/shopping/{item['id']}/tick"
        client.post(url, data=MultiDict([("done", "1"), ("done", "0")]))
        assert store.load_shopping()[0]["bought_at"]
        assert 'type="checkbox" name="done" value="1" checked' in client.get("/h/shopping").get_data(as_text=True)
        client.post(url, data=MultiDict([("done", "0")]))
        assert store.load_shopping()[0]["bought_at"] is None

    def test_a_refusal_is_shown_and_nothing_is_saved(self, client, store):
        response = client.post("/h/shopping/add", data={"text": "x" * 81}, follow_redirects=True)
        assert b"80 characters" in response.data
        assert texts(store) == []

    def test_the_list_is_shown_and_escaped(self, client):
        client.post("/h/shopping/add", data={"text": "<b>Milk</b>"})
        page = client.get("/h/shopping").data
        assert b"&lt;b&gt;Milk&lt;/b&gt;" in page and b"<b>Milk</b>" not in page

    def test_no_name_picked_is_refused(self, store, monkeypatch):
        monkeypatch.delenv(parent.PASSWORD_VARIABLE, raising=False)
        bare = client_for(create_app(store))
        bare.get("/h/who")
        assert bare.post("/h/shopping/add", data={"text": "Milk"}).status_code == 401
        assert texts(store) == []

    def test_without_csrf_is_refused(self, client, store):
        assert client.post("/h/shopping/add", data={"text": "Milk", "csrf_token": "bad"}).status_code in (400, 403)
        assert texts(store) == []

    def test_the_tab_follows_the_switch(self, client, store):
        store.config_path.write_text(CONFIG.replace("shopping: true", "shopping: false"))
        assert client.get("/h/shopping").status_code == 404
        assert client.post("/h/shopping/add", data={"text": "Milk"}).status_code == 404
        assert texts(store) == []

    def test_an_unknown_item_is_a_404(self, client):
        assert client.post("/h/shopping/nope/tick", data={"done": "1"}).status_code == 404
