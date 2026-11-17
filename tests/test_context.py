"""Ages, birthdays, countdowns and task assignment.

Every test injects the date. Nothing here is allowed to depend on when it runs —
that was the bug class this suite exists to catch.
"""

from datetime import date

import pytest

from dinkydash.context import (anniversary, build_countdowns, compute_age,
                               compute_birthday_info, compute_special_date_info,
                               tasks_for)


class TestAnniversary:
    def test_ordinary_date(self):
        assert anniversary(2026, 3, 15) == date(2026, 3, 15)

    def test_leap_day_in_a_leap_year_stays_put(self):
        assert anniversary(2028, 2, 29) == date(2028, 2, 29)

    def test_leap_day_is_observed_on_the_28th_otherwise(self):
        assert anniversary(2026, 2, 29) == date(2026, 2, 28)


class TestAge:
    def test_before_the_birthday(self):
        assert compute_age(date(2017, 3, 15), date(2026, 3, 14)) == 8

    def test_on_the_birthday(self):
        assert compute_age(date(2017, 3, 15), date(2026, 3, 15)) == 9

    def test_after_the_birthday(self):
        assert compute_age(date(2017, 3, 15), date(2026, 3, 16)) == 9

    def test_leap_day_child_ages_up_on_the_28th(self):
        # Born 29 Feb 2016; in 2026 the anniversary is observed on the 28th.
        assert compute_age(date(2016, 2, 29), date(2026, 2, 27)) == 9
        assert compute_age(date(2016, 2, 29), date(2026, 2, 28)) == 10


class TestBirthdayInfo:
    person = {"name": "Mia", "date_of_birth": "2017-03-15"}

    def test_counts_down_within_the_year(self):
        info = compute_birthday_info(self.person, date(2026, 3, 3))
        assert info["days_until_birthday"] == 12
        assert info["current_age"] == 8
        assert info["turning"] == 9

    def test_rolls_into_next_year_once_past(self):
        info = compute_birthday_info(self.person, date(2026, 3, 16))
        assert info["days_until_birthday"] == 364
        assert info["turning"] == 10

    def test_on_the_day_itself(self):
        info = compute_birthday_info(self.person, date(2026, 3, 15))
        assert info["days_until_birthday"] == 0
        assert info["turning"] == 9

    def test_accepts_a_real_date_object(self):
        # ruamel parses unquoted YAML dates into date objects.
        info = compute_birthday_info(
            {"name": "Theo", "date_of_birth": date(2019, 6, 20)}, date(2026, 6, 19)
        )
        assert info["days_until_birthday"] == 1


class TestSpecialDates:
    def test_counts_down_to_this_year(self):
        info = compute_special_date_info(
            {"title": "Christmas", "date": "12/25"}, date(2026, 9, 3)
        )
        assert info["days_until"] == 113

    def test_rolls_over_after_the_date_passes(self):
        info = compute_special_date_info(
            {"title": "Christmas", "date": "12/25"}, date(2026, 12, 26)
        )
        assert info["days_until"] == 364

    def test_leap_day_returns_to_the_29th_in_a_leap_year(self):
        # From 2027 the next 29 Feb is a real one, not the rolled-back 28th.
        info = compute_special_date_info(
            {"title": "Leap party", "date": "02/29"}, date(2027, 6, 1)
        )
        assert info["days_until"] == (date(2028, 2, 29) - date(2027, 6, 1)).days


PEOPLE = [{"id": "mia", "name": "Mia"}, {"id": "theo", "name": "Theo"}, {"id": "ines", "name": "Ines"}]


def config_with(*tasks):
    return {"people": PEOPLE, "tasks": list(tasks)}


def task(mode, people=(), offset=0, recurrence=None, title="Set the table"):
    return {"id": "t1", "title": title, "emoji": "🍽", "recurrence": recurrence or {"kind": "daily"},
            "assignment": {"mode": mode, "people": list(people), "offset": offset}}


def names(config, day):
    return [t["assigned_to"] for t in tasks_for(config, day)]


class TestTaskAssignment:
    rotation = ["mia", "theo", "ines"]

    def test_rotate_hands_over_each_day_and_cycles_through_everyone(self):
        config = config_with(task("rotate", self.rotation))
        seen = [names(config, date(2026, 9, 3 + n))[0] for n in range(3)]
        assert sorted(seen) == ["Ines", "Mia", "Theo"]

    def test_rotate_is_stable_for_a_given_day(self):
        config = config_with(task("rotate", self.rotation))
        assert tasks_for(config, date(2026, 9, 3)) == tasks_for(config, date(2026, 9, 3))

    def test_rotation_counts_occurrences_not_days(self):
        weekdays = {"kind": "weekdays", "days": [0]}
        config = config_with(task("rotate", ["mia", "theo"], recurrence=weekdays))
        # Consecutive Mondays alternate; the days between are not occurrences.
        assert names(config, date(2026, 9, 7)) != names(config, date(2026, 9, 14))
        assert names(config, date(2026, 9, 7)) == names(config, date(2026, 9, 21))
        assert names(config, date(2026, 9, 8)) == []

    def test_offset_moves_where_the_rotation_starts(self):
        day = date(2026, 9, 3)
        first = names(config_with(task("rotate", self.rotation, offset=0)), day)
        shifted = names(config_with(task("rotate", self.rotation, offset=1)), day)
        assert first != shifted

    def test_fixed_is_one_person_every_time(self):
        config = config_with(task("fixed", ["theo"]))
        assert {names(config, date(2026, 9, 3 + n))[0] for n in range(5)} == {"Theo"}

    def test_everyone_is_every_person_in_the_family(self):
        due = tasks_for(config_with(task("everyone")), date(2026, 9, 3))
        assert due[0]["assigned_to"] == "Everyone"
        assert due[0]["person_ids"] == ["mia", "theo", "ines"]

    def test_anyone_is_nobody_in_particular(self):
        due = tasks_for(config_with(task("anyone")), date(2026, 9, 3))
        assert due[0]["assigned_to"] == "Anyone"
        assert due[0]["person_ids"] == []

    def test_a_task_not_due_today_is_left_out(self):
        once = task("anyone", recurrence={"kind": "once", "date": "2026-12-24"})
        assert tasks_for(config_with(once), date(2026, 9, 3)) == []
        assert len(tasks_for(config_with(once), date(2026, 12, 24))) == 1

    def test_a_rotation_with_nobody_in_it_is_skipped(self):
        assert tasks_for(config_with(task("rotate", [])), date(2026, 9, 3)) == []

    def test_handles_no_tasks_at_all(self):
        assert tasks_for({}, date(2026, 9, 3)) == []

    def test_assignment_follows_the_id_so_a_rename_changes_nothing(self):
        config = config_with(task("fixed", ["theo"]))
        before = tasks_for(config, date(2026, 9, 3))[0]
        config["people"] = [dict(p, name="Thea") if p["id"] == "theo" else p for p in PEOPLE]
        after = tasks_for(config, date(2026, 9, 3))[0]
        assert (before["person_ids"], after["assigned_to"]) == (["theo"], "Thea")

    def test_an_id_with_no_person_is_skipped_before_the_rotation_is_counted(self):
        config = config_with(task("rotate", ["gone", "mia", "theo"]))
        assert {names(config, date(2026, 9, 3 + n))[0] for n in range(2)} == {"Mia", "Theo"}


class TestCountdowns:
    def test_merges_and_sorts_soonest_first(self):
        countdowns = build_countdowns(
            [{"name": "Mia", "date_of_birth": "2017-03-15"}],
            [{"title": "Christmas", "emoji": "🎄", "date": "12/25"}],
            date(2026, 9, 3),
        )
        assert [c["days"] for c in countdowns] == sorted(c["days"] for c in countdowns)
        assert countdowns[0]["title"] == "Christmas"  # 113 days vs 193

    def test_limit_takes_the_soonest(self):
        countdowns = build_countdowns(
            [{"name": "Mia", "date_of_birth": "2017-03-15"},
             {"name": "Theo", "date_of_birth": "2019-06-20"}],
            [{"title": "Christmas", "emoji": "🎄", "date": "12/25"}],
            date(2026, 9, 3), limit=2,
        )
        assert len(countdowns) == 2
        assert countdowns[0]["days"] <= countdowns[1]["days"]

    def test_empty_config_is_fine(self):
        assert build_countdowns(None, None, date(2026, 9, 3)) == []


@pytest.mark.parametrize("day", [date(2026, 1, 1), date(2026, 2, 28), date(2026, 12, 31)])
def test_rotation_never_indexes_out_of_range(day):
    config = config_with(task("rotate", ["mia", "theo"], offset=5))
    assert names(config, day)[0] in {"Mia", "Theo"}
