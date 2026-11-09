"""Streaks: computed from completions and config, never stored (PRD section 6)."""

from datetime import date, timedelta

from dinkydash import streaks
from dinkydash.context import tasks_for

TODAY = date(2026, 3, 18)  # a Wednesday


def day(n):
    return TODAY - timedelta(days=n)


def config(tasks, people=("p1", "p2")):
    return {"people": [{"id": i, "name": f"Name {i}", "date_of_birth": "2015-05-05"} for i in people], "tasks": tasks}


def task(tid="t1", mode="fixed", people=("p1",), kind="daily", **extra):
    return {"id": tid, "title": tid, "emoji": "", "recurrence": {"kind": kind},
            "assignment": {"mode": mode, "people": list(people)}, **extra}


def done(task_id, n, person="p1"):
    return {"task_id": task_id, "date": day(n).isoformat(), "person_id": person,
            "completed_at": "x"}


def test_counts_consecutive_done_days_ending_yesterday_when_today_is_open():
    cfg = config([task()])
    assert streaks.person_streak(cfg, "p1", [done("t1", 1), done("t1", 2), done("t1", 3)], TODAY) == 3


def test_today_done_counts():
    cfg = config([task()])
    assert streaks.person_streak(cfg, "p1", [done("t1", 0), done("t1", 1)], TODAY) == 2


def test_today_open_is_skipped_not_a_miss():
    cfg = config([task()])
    assert streaks.person_streak(cfg, "p1", [done("t1", 1)], TODAY) == 1


def test_missed_due_day_ends_the_streak():
    cfg = config([task()])
    assert streaks.person_streak(cfg, "p1", [done("t1", 1), done("t1", 3)], TODAY) == 1


def test_day_with_nothing_due_neither_extends_nor_breaks():
    # Weekly on Wednesdays only: the days between are skipped.
    cfg = config([task(kind="interval") | {"recurrence": {"kind": "interval", "every": 7,
                                                            "start": day(14).isoformat()}}])
    assert streaks.person_streak(cfg, "p1", [done("t1", 7), done("t1", 14)], TODAY) == 2


def test_everything_due_must_be_done():
    cfg = config([task("a"), task("b")])
    assert streaks.person_streak(cfg, "p1", [done("a", 1), done("b", 1), done("a", 2)], TODAY) == 1


def test_a_streak_survives_a_rename():
    cfg = config([task()])
    before = streaks.person_streak(cfg, "p1", [done("t1", 1), done("t1", 2)], TODAY)
    cfg["people"][0]["name"] = "Someone else"
    cfg["tasks"][0]["title"] = "Renamed"
    assert streaks.person_streak(cfg, "p1", [done("t1", 1), done("t1", 2)], TODAY) == before == 2


def test_other_peoples_completions_do_not_count():
    cfg = config([task()])
    assert streaks.person_streak(cfg, "p1", [done("t1", 1, "p2")], TODAY) == 0


def test_nothing_ever_due_is_zero():
    assert streaks.person_streak(config([]), "p1", [], TODAY) == 0


def test_everyone_task_is_due_for_each_person():
    cfg = config([task(mode="everyone", people=())])
    comps = [done("t1", 1, "p1"), done("t1", 1, "p2")]
    assert streaks.person_streak(cfg, "p1", comps, TODAY) == 1
    assert streaks.person_streak(cfg, "p2", [done("t1", 2, "p2")], TODAY) == 0


def test_anyone_tasks_are_not_part_of_a_persons_streak():
    cfg = config([task(mode="anyone", people=())])
    assert streaks.person_streak(cfg, "p1", [], TODAY) == 0


def test_rotation_follows_the_assignee_for_each_day():
    cfg = config([task(mode="rotate", people=("p1", "p2"))])
    # Alternate days: p1 has every other day. Their streak only needs their own days.
    p1_days = [n for n in range(1, 7)
               if any(t["person_ids"] == ["p1"] for t in tasks_for(cfg, day(n)))]
    comps = [done("t1", n) for n in p1_days]
    assert streaks.person_streak(cfg, "p1", comps, TODAY) == len(p1_days)


def test_anyone_task_streak_counts_occurrences_with_any_completion():
    cfg = config([task(mode="anyone", people=())])
    comps = [done("t1", 1, "p1"), done("t1", 2, "p2"), done("t1", 4, "p1")]
    assert streaks.task_streak(cfg, "t1", comps, TODAY) == 2


def test_anyone_task_today_open_skipped_today_done_counts():
    cfg = config([task(mode="anyone", people=())])
    assert streaks.task_streak(cfg, "t1", [done("t1", 1)], TODAY) == 1
    assert streaks.task_streak(cfg, "t1", [done("t1", 0), done("t1", 1)], TODAY) == 2


def test_best_streak_is_the_longest_run():
    cfg = config([task()])
    comps = [done("t1", n) for n in (1, 2, 5, 6, 7, 8)]
    assert streaks.person_streak(cfg, "p1", comps, TODAY) == 2
    assert streaks.best_person_streak(cfg, "p1", comps, TODAY) == 4


def test_history_is_capped_at_400_days():
    cfg = config([task()])
    comps = [done("t1", n) for n in range(1, 500)]
    assert streaks.person_streak(cfg, "p1", comps, TODAY) <= streaks.MAX_DAYS


# -- the wall card -----------------------------------------------------------

from dinkydash.board import build_view  # noqa: E402


def view_with(tasks, completions, people=("p1", "p2")):
    cfg = config(tasks, people) | {"timezone": "UTC"}
    return build_view(cfg, None, TODAY, completions=completions)


def test_the_card_shows_done_state_and_streaks():
    view = view_with([task("a"), task("b", people=("p2",))],
                     [done("a", 0), done("a", 1), done("a", 2)])
    states = {t["id"]: t["done"] for t in view["tasks"]}
    assert states == {"a": True, "b": False}
    assert {"name": "Name p1", "days": 3} in view["streaks"]


def test_yesterday_group_lists_what_was_left_open():
    view = view_with([task("a"), task("b", people=("p2",))], [done("a", 1)])
    assert [r["title"] for r in view["yesterday"]] == ["b"]
    assert view["yesterday"][0]["assigned_to"] == "Name p2"


def test_anyone_task_carries_its_own_streak():
    view = view_with([task("a", mode="anyone", people=())], [done("a", 1, "p2"), done("a", 2)])
    assert view["tasks"][0]["streak"] == 2
    assert view["yesterday"] == []


def test_without_completions_the_card_is_the_plain_list():
    view = view_with([task("a")], None)
    assert "done" not in view["tasks"][0] and view["yesterday"] == []


def test_the_rendered_wall_marks_done_and_offers_the_shed_hooks(tmp_path):
    from dinkydash.store import FileStore
    from tests.conftest import client_for
    from web import create_app
    path = tmp_path / "config.yaml"
    path.write_text("family_name: Test\ntimezone: UTC\npeople:\n  - {id: p1, name: Mia, date_of_birth: 2015-05-05}\ntasks:\n"
                    "  - {id: t1, title: Feed the fish, emoji: x, recurrence: {kind: daily},"
                    " assignment: {mode: fixed, people: [p1]}}\n")
    store = FileStore(path)
    from dinkydash import config as config_module
    today = config_module.today_for(store.load_config())
    store.record_completion({"task_id": "t1", "date": (today - timedelta(days=1)).isoformat(),
                             "person_id": "p1", "completed_at": "x"}, today)
    page = client_for(create_app(store)).get("/").get_data(as_text=True)
    assert "Mia: 1 day" in page
    store.record_completion({"task_id": "t1", "date": today.isoformat(),
                             "person_id": "p1", "completed_at": "x"}, today)
    page = client_for(create_app(store)).get("/").get_data(as_text=True)
    assert 'class="chore done"' in page
    assert "Mia: 2 days" in page
