"""Activity: the grid, the unticked list and the parent-only page (PRD D12, D23)."""

from datetime import date, timedelta

import pytest

from dinkydash import activity
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent

TODAY = date(2026, 3, 18)


def day(n):
    return TODAY - timedelta(days=n)


def config(tasks):
    return {"people": [{"id": i, "name": n, "date_of_birth": "2015-05-05"}
                       for i, n in (("p1", "Mia"), ("p2", "Sam"))], "tasks": tasks}


def task(tid="t1", mode="fixed", people=("p1",)):
    return {"id": tid, "title": tid.upper(), "emoji": "", "recurrence": {"kind": "daily"},
            "assignment": {"mode": mode, "people": list(people)}}


def done(task_id, n, person="p1"):
    return {"task_id": task_id, "date": day(n).isoformat(), "person_id": person, "completed_at": "x"}


class TestGrid:
    def test_thirty_days_oldest_first_ending_today(self):
        cells = activity.grid(config([task()]), "p1", [done("t1", 1)], TODAY)
        assert len(cells) == 30
        assert cells[-1]["date"] == TODAY.isoformat() and cells[0]["date"] == day(29).isoformat()

    def test_done_missed_and_nothing_due(self):
        cfg = config([task()])
        cells = activity.grid(cfg, "p1", [done("t1", 1)], TODAY)
        assert cells[-2]["state"] == "done"
        assert cells[-3]["state"] == "missed"
        assert activity.grid(cfg, "p2", [], TODAY)[-3]["state"] == "none"

    def test_today_left_open_is_not_a_miss(self):
        assert activity.grid(config([task()]), "p1", [], TODAY)[-1]["state"] == "open"


class TestUnticked:
    def test_lists_due_occurrences_in_the_last_fourteen_days_newest_first(self):
        rows = activity.unticked(config([task()]), [done("t1", 1)], TODAY)
        assert [r["date"] for r in rows][0] == TODAY.isoformat()
        assert day(1).isoformat() not in [r["date"] for r in rows]
        assert day(14).isoformat() in [r["date"] for r in rows]
        assert day(15).isoformat() not in [r["date"] for r in rows]

    def test_an_everyone_task_lists_each_person_missing(self):
        cfg = config([task(mode="everyone", people=("p1", "p2"))])
        rows = activity.unticked(cfg, [done("t1", 1, "p1")], TODAY)
        assert [(r["person_id"]) for r in rows if r["date"] == day(1).isoformat()] == ["p2"]

    def test_an_anyone_task_is_one_row_until_somebody_has_done_it(self):
        cfg = config([task(mode="anyone", people=())])
        assert len([r for r in activity.unticked(cfg, [], TODAY) if r["date"] == day(2).isoformat()]) == 1
        rows = activity.unticked(cfg, [done("t1", 2, "p2")], TODAY)
        assert day(2).isoformat() not in [r["date"] for r in rows]


CONFIG = """\
timezone: "UTC"
people:
  - id: mia1
    name: "Mia"
    date_of_birth: "2017-03-15"
tasks:
  - id: bins
    title: "Bins"
    recurrence: {kind: daily}
    assignment: {mode: fixed, people: [mia1]}
"""
PASSWORD = "correct horse battery"


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return FileStore(path)


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.delenv(parent.PASSWORD_VARIABLE, raising=False)
    return client_for(create_app(store))


def today_of(store):
    from dinkydash import config as c
    return c.today_for(store.load_config())


class TestPage:
    def test_shows_streaks_grid_and_unticked(self, client):
        page = client.get("/settings/activity").get_data(as_text=True)
        assert "Mia" in page and "Bins" in page and "Not ticked" in page

    def test_one_tap_tick_records_and_a_second_removes_nothing_older(self, client, store):
        today = today_of(store)
        old = today - timedelta(days=10)
        r = client.post("/settings/activity/tick",
                        data={"task_id": "bins", "date": old.isoformat(), "person": "mia1"})
        assert r.status_code == 302
        assert any(c["date"] == old.isoformat() for c in store.load_completions())

    def test_refuses_older_than_fourteen_days_and_the_future(self, client, store):
        today = today_of(store)
        for d in (today - timedelta(days=15), today + timedelta(days=1)):
            r = client.post("/settings/activity/tick",
                            data={"task_id": "bins", "date": d.isoformat(), "person": "mia1"})
            assert r.status_code == 403
        assert store.load_completions() == []

    def test_refuses_a_task_not_due_or_a_stranger(self, client, store):
        today = today_of(store).isoformat()
        assert client.post("/settings/activity/tick", data={
            "task_id": "nope", "date": today, "person": "mia1"}).status_code == 403
        assert client.post("/settings/activity/tick", data={
            "task_id": "bins", "date": today, "person": "zzz"}).status_code == 403
        assert client.post("/settings/activity/tick", data={
            "task_id": "bins", "date": "junk", "person": "mia1"}).status_code == 400


class TestSignIn:
    @pytest.fixture
    def locked(self, store, monkeypatch):
        monkeypatch.setenv(parent.PASSWORD_VARIABLE, PASSWORD)
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "test-key-not-the-public-one")
        return client_for(create_app(store))

    def test_only_a_parent_reaches_it(self, locked):
        assert locked.get("/settings/activity").status_code == 302
        today = date.today().isoformat()
        assert locked.post("/settings/activity/tick", data={
            "task_id": "bins", "date": today, "person": "mia1"}).status_code == 302
        locked.get("/signin")
        locked.post("/signin", data={"password": PASSWORD})
        assert locked.get("/settings/activity").status_code == 200

    def test_a_member_on_the_phone_cannot_use_it(self, locked):
        locked.get("/h/who")
        locked.post("/h/who", data={"person": "mia1"})
        assert locked.get("/settings/activity").status_code == 302
