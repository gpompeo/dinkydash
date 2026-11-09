"""`recurring` becomes `tasks` on load, and nobody's turn moves on the day of the upgrade."""

from datetime import date, timedelta

import pytest

from dinkydash import config as config_module
from dinkydash.context import tasks_for


def legacy(today_choices=("Mia", "Theo", "Ines"), extra=()):
    return {
        "people": [{"name": "Mia"}, {"name": "Theo"}, {"name": "Ines"}],
        "recurring": [{"title": "Set the table", "emoji": "🍽", "choices": list(today_choices)},
                      *extra],
    }


def old_rule(choices, day):
    return choices[day.timetuple().tm_yday % len(choices)]


@pytest.mark.parametrize("day", [date(2026, 1, 1), date(2026, 3, 14), date(2026, 12, 31),
                                 date(2028, 2, 29)])
def test_the_person_on_duty_on_the_day_of_the_upgrade_is_unchanged(day):
    config = config_module.with_defaults(legacy(), today=day)
    assert tasks_for(config, day)[0]["assigned_to"] == old_rule(["Mia", "Theo", "Ines"], day)


def test_it_agrees_with_the_old_rule_until_the_year_boundary():
    start = date(2026, 3, 1)
    choices = ["Mia", "Theo", "Ines"]
    config = config_module.with_defaults(legacy(), today=start)
    for n in range((date(2026, 12, 31) - start).days + 1):
        day = start + timedelta(days=n)
        assert tasks_for(config, day)[0]["assigned_to"] == old_rule(choices, day)


def test_it_differs_from_the_old_rule_only_where_the_old_year_restarted():
    # 2026 has 365 days, which 3 does not divide: the old rule jumps at 1 January.
    start = date(2026, 12, 30)
    config = config_module.with_defaults(legacy(), today=start)
    new_year = date(2027, 1, 1)
    old = old_rule(["Mia", "Theo", "Ines"], new_year)
    assert tasks_for(config, new_year)[0]["assigned_to"] != old
    # And the new rule keeps handing over one person at a time across it.
    order = [tasks_for(config, start + timedelta(days=n))[0]["assigned_to"] for n in range(5)]
    assert all(order[i] != order[i + 1] for i in range(4))
    assert order[0] == order[3]


def test_chores_become_daily_rotating_tasks_with_person_ids():
    config = config_module.with_defaults(legacy(), today=date(2026, 5, 1))
    assert "recurring" not in config
    [task] = config["tasks"]
    ids = {p["name"]: p["id"] for p in config["people"]}
    assert task["recurrence"] == {"kind": "daily"}
    assert task["assignment"]["mode"] == "rotate"
    assert task["assignment"]["people"] == [ids["Mia"], ids["Theo"], ids["Ines"]]
    assert task["id"] and task["title"] == "Set the table" and task["emoji"] == "🍽"


def test_a_rename_after_the_upgrade_changes_nothing():
    day = date(2026, 5, 1)
    config = config_module.with_defaults(legacy(), today=day)
    before = tasks_for(config, day)[0]["person_ids"]
    config["people"][0]["name"] = "Anna"
    config["people"][1]["name"] = "Tom"
    assert tasks_for(config, day)[0]["person_ids"] == before


def test_a_name_matching_nobody_is_dropped_from_the_rotation():
    raw = legacy(("Mia", "Ghost", "Theo"))
    config = config_module.with_defaults(raw, today=date(2026, 5, 1))
    assert len(config["tasks"][0]["assignment"]["people"]) == 2


def test_a_chore_with_nobody_migrates_and_stays_off_the_wall():
    config = config_module.with_defaults(legacy((), ), today=date(2026, 5, 1))
    assert config["tasks"][0]["assignment"]["people"] == []
    assert tasks_for(config, date(2026, 5, 1)) == []


def test_a_config_that_already_has_tasks_is_left_alone():
    raw = {"tasks": [{"id": "x", "title": "Bins"}], "recurring": [{"title": "Old", "choices": []}]}
    config = config_module.with_defaults(raw, today=date(2026, 5, 1))
    assert config["tasks"] == [{"id": "x", "title": "Bins"}]


def test_with_no_chores_there_are_no_tasks():
    assert config_module.with_defaults({}, today=date(2026, 5, 1))["tasks"] == []


def test_the_migration_keeps_to_the_caps():
    chores = [{"title": f"Chore {n}", "choices": []} for n in range(50)]
    chores[0]["title"] = "x" * 200
    config = config_module.with_defaults({"recurring": chores}, today=date(2026, 5, 1))
    assert len(config["tasks"]) == config_module.MAX_TASKS
    assert len(config["tasks"][0]["title"]) == config_module.MAX_TITLE_LENGTH


def test_a_hand_edited_file_over_the_caps_still_shows_only_the_caps():
    tasks = [{"id": f"t{n}", "title": "y" * 200, "recurrence": {"kind": "daily"},
              "assignment": {"mode": "anyone"}} for n in range(60)]
    due = tasks_for({"tasks": tasks}, date(2026, 5, 1))
    assert len(due) == config_module.MAX_TASKS
    assert all(len(t["title"]) == config_module.MAX_TITLE_LENGTH for t in due)
