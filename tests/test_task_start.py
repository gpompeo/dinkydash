"""A task is never due before its effective start: its explicit `start`, else its `created` day."""

from datetime import date, timedelta

import pytest

from dinkydash import activity, checkin, config as config_module, context, streaks
from dinkydash.board import build_view
from dinkydash.recurrence import occurrence_index, occurs_on
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent

TODAY = date(2026, 3, 18)


def day(n):
    return TODAY - timedelta(days=n)


def task(rec=None, **extra):
    return {"id": "t1", "title": "Bins", "emoji": "", "recurrence": rec or {"kind": "daily"},
            "assignment": {"mode": "fixed", "people": ["p1"], "offset": 0}, **extra}


def config(*tasks):
    return {"people": [{"id": "p1", "name": "Mia", "date_of_birth": "2015-05-05"}],
            "tasks": list(tasks)}


def done(n):
    return {"task_id": "t1", "date": day(n).isoformat(), "person_id": "p1", "completed_at": "x"}


RECURRENCES = {
    "daily": {"kind": "daily"},
    "weekdays": {"kind": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]},
    "interval": {"kind": "interval", "every": 1, "start": "2026-01-01"},
    "monthly_day": {"kind": "monthly_day", "day": 10},
    "monthly_nth": {"kind": "monthly_nth", "nth": 1, "weekday": 0},
}


class TestEffectiveStart:
    def test_a_task_created_today_is_not_due_earlier(self):
        t = task(created=TODAY.isoformat())
        assert occurs_on(t, TODAY)
        assert not any(occurs_on(t, day(n)) for n in range(1, 15))

    def test_a_future_start_hides_the_task_until_then(self):
        t = task(start=(TODAY + timedelta(days=3)).isoformat(), created=TODAY.isoformat())
        assert not occurs_on(t, TODAY)
        assert occurs_on(t, TODAY + timedelta(days=3))

    def test_an_explicit_start_beats_creation_and_may_backfill(self):
        t = task(start=day(5).isoformat(), created=TODAY.isoformat())
        assert occurs_on(t, day(5)) and not occurs_on(t, day(6))

    def test_dates_may_be_yaml_dates_as_well_as_strings(self):
        assert not occurs_on(task(created=TODAY), day(1))

    @pytest.mark.parametrize("name", RECURRENCES)
    def test_every_kind_respects_the_start(self, name):
        rec = RECURRENCES[name]
        free = task(rec)
        bounded = task(rec, start=day(3).isoformat())
        for n in range(60):
            d = day(n)
            assert occurs_on(bounded, d) == (occurs_on(free, d) and d >= day(3))

    def test_a_once_task_before_its_start_never_occurs(self):
        t = task({"kind": "once", "date": day(2).isoformat()}, start=day(1).isoformat())
        assert not occurs_on(t, day(2))

    def test_an_unreadable_start_is_ignored_rather_than_hiding_the_task(self):
        assert occurs_on(task(start="soon"), day(5))

    def test_a_legacy_task_keeps_its_history(self):
        assert all(occurs_on(task(), day(n)) for n in range(400))


class TestIntervalCadenceAndRotation:
    def test_interval_cadence_stays_on_its_own_anchor(self):
        rec = {"kind": "interval", "every": 3, "start": day(9).isoformat()}
        free = task(rec)
        bounded = task(rec, start=day(4).isoformat())  # not on the cadence
        due = [n for n in range(9, -1, -1) if occurs_on(bounded, day(n))]
        assert due == [n for n in (9, 6, 3, 0) if n <= 4]

    def test_the_start_never_shifts_a_rotation(self):
        free = task({"kind": "daily"})
        bounded = task({"kind": "daily"}, start=day(4).isoformat())
        for n in range(10):
            assert occurrence_index(bounded, day(n)) == occurrence_index(free, day(n))

    def test_assignments_agree_on_the_days_both_are_due(self):
        rot = {"mode": "rotate", "people": ["p1", "p2"], "offset": 1}
        people = [{"id": "p1", "name": "Mia"}, {"id": "p2", "name": "Sam"}]
        free = {**task(), "assignment": rot}
        bounded = {**free, "start": day(4).isoformat()}
        for n in range(5):
            a = context.tasks_for({"people": people, "tasks": [free]}, day(n))
            b = context.tasks_for({"people": people, "tasks": [bounded]}, day(n))
            assert a == b


class TestSurfacesAgree:
    def cfg(self):
        return config(task(created=day(2).isoformat()))

    def test_activity_unticked_and_grid(self):
        rows = activity.unticked(self.cfg(), [], TODAY)
        assert sorted(r["date"] for r in rows) == [day(n).isoformat() for n in (2, 1, 0)]
        cells = activity.grid(self.cfg(), "p1", [], TODAY)
        assert [c["state"] for c in cells[-4:]] == ["none", "missed", "missed", "open"]

    def test_streaks_ignore_days_before_the_start(self):
        cfg = self.cfg()
        completions = [done(2), done(1), done(0)]
        assert streaks.person_streak(cfg, "p1", completions, TODAY) == 3
        assert streaks.best_person_streak(cfg, "p1", completions, TODAY) == 3
        assert streaks.task_streak(cfg, "t1", completions, TODAY) == 3
        # Before the start nothing is due, so a gap there ends nothing.
        assert streaks.person_streak(cfg, "p1", [done(1), done(0)], TODAY) == 2

    def test_correction_permission_follows_the_start(self):
        kw = dict(task_id="t1", person_id="p1", today=TODAY, actor_id=None,
                  restricted=False, is_parent=True)
        assert checkin.may_tick(self.cfg(), day=day(2), **kw)
        assert not checkin.may_tick(self.cfg(), day=day(3), **kw)

    def test_the_dashboard_view_hides_a_future_task(self):
        cfg = config(task(start=(TODAY + timedelta(days=1)).isoformat()))
        assert context.tasks_for(cfg, TODAY) == []
        assert context.tasks_for(cfg, TODAY + timedelta(days=1))


class TestChangingTheStartKeepsCompletions:
    def test_moving_later_excludes_and_moving_back_restores(self):
        completions = [done(5), done(4)]
        t = task(created=day(10).isoformat())
        assert checkin.person_for(config(t), "t1", day(5), "p1")
        later = {**t, "start": day(1).isoformat()}
        assert not checkin.person_for(config(later), "t1", day(5), "p1")
        assert len(completions) == 2
        assert streaks.person_streak(config(later), "p1", completions, TODAY) == 0
        back = {k: v for k, v in later.items() if k != "start"}
        assert checkin.person_for(config(back), "t1", day(5), "p1")


class TestEditor:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.delenv(parent.PASSWORD_VARIABLE, raising=False)
        path = tmp_path / "config.yaml"
        path.write_text(
            'family_name: "W"\ntimezone: "Pacific/Kiritimati"\npeople:\n'
            '  - {id: mia00001, name: "Mia", date_of_birth: "2017-03-15"}\n'
            "tasks:\n"
            "  - id: old0001\n    title: Old\n    recurrence: {kind: daily}\n"
            "    assignment: {mode: anyone, people: [], offset: 0}\n")
        self.path = path
        return client_for(create_app(FileStore(path)))

    def tasks(self):
        return {t["id"]: t for t in config_module.load_config(self.path)["tasks"]}

    def today(self):
        return config_module.today_for(config_module.load_config(self.path)).isoformat()

    def post(self, client, where, **data):
        form = {"title": "Walk", "rec_kind": "daily", "mode": "anyone", **data}
        return client.post(f"/settings/tasks/{where}", data=form)

    def test_a_new_task_records_the_household_creation_date(self, client):
        assert self.post(client, "new").status_code == 302
        new = next(t for i, t in self.tasks().items() if i != "old0001")
        assert str(new["created"]) == self.today()
        assert "start" not in new

    def test_an_explicit_start_is_saved_and_may_be_in_the_past_or_future(self, client):
        for start in ("2020-01-01", "2099-01-01"):
            self.post(client, "new", task_start=start)
        starts = {str(t.get("start")) for i, t in self.tasks().items() if i != "old0001"}
        assert starts == {"2020-01-01", "2099-01-01"}

    def test_editing_preserves_creation_and_clearing_the_start_falls_back(self, client):
        self.post(client, "new", task_start="2099-01-01")
        tid = next(i for i in self.tasks() if i != "old0001")
        created = self.tasks()[tid]["created"]
        self.post(client, tid, title="Renamed", task_start="")
        edited = self.tasks()[tid]
        assert edited["created"] == created and "start" not in edited

    def test_editing_a_legacy_task_does_not_invent_a_date(self, client):
        self.post(client, "old0001", title="Older")
        assert "created" not in self.tasks()["old0001"]
        assert "start" not in self.tasks()["old0001"]

    def test_a_post_without_the_start_field_keeps_the_stored_start(self, client):
        self.post(client, "new", task_start="2099-01-01")
        tid = next(i for i in self.tasks() if i != "old0001")
        self.post(client, tid, title="Renamed")
        assert str(self.tasks()[tid]["start"]) == "2099-01-01"

    def test_a_bad_start_is_a_field_error(self, client):
        response = self.post(client, "new", task_start="tomorrow")
        assert response.status_code == 200
        assert b"error-task_start" in response.data

    def test_a_one_off_before_its_start_is_rejected_with_a_field_error(self, client):
        response = self.post(client, "new", rec_kind="once", rec_date="2026-01-01",
                             task_start="2026-02-01")
        assert response.status_code == 200
        assert b"error-rec_date" in response.data
        assert len(self.tasks()) == 1

    def test_a_new_one_off_in_the_past_is_before_its_creation_date(self, client):
        response = self.post(client, "new", rec_kind="once", rec_date="2020-01-01")
        assert response.status_code == 200 and b"error-rec_date" in response.data

    def test_a_backdated_start_lets_a_past_one_off_through(self, client):
        response = self.post(client, "new", rec_kind="once", rec_date="2020-01-01",
                             task_start="2019-12-01")
        assert response.status_code == 302

    def test_the_edit_page_shows_the_start(self, client):
        self.post(client, "new", task_start="2099-01-01")
        tid = next(i for i in self.tasks() if i != "old0001")
        assert b'name="task_start"' in client.get(f"/settings/tasks/{tid}").data
        assert b'value="2099-01-01"' in client.get(f"/settings/tasks/{tid}").data
