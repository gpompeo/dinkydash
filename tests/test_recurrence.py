"""Recurrence engine: which days a task occurs on and the occurrence index."""

from datetime import date, timedelta

import pytest

from dinkydash.recurrence import occurrence_index, occurs_on


def task(**recurrence):
    return {"id": "t", "title": "Set the table", "recurrence": recurrence}


def days(t, start, end):
    out, d = [], start
    while d <= end:
        if occurs_on(t, d):
            out.append(d)
        d += timedelta(days=1)
    return out


def test_daily_occurs_every_day():
    t = task(kind="daily")
    assert days(t, date(2026, 2, 26), date(2026, 3, 2)) == [date(2026, 2, 26) + timedelta(i) for i in range(5)]


def test_weekdays_and_weekends_presets():
    mon_fri = task(kind="weekdays", days=[0, 1, 2, 3, 4])
    weekend = task(kind="weekdays", days=[5, 6])
    assert [d.day for d in days(mon_fri, date(2026, 3, 2), date(2026, 3, 8))] == [2, 3, 4, 5, 6]
    assert [d.day for d in days(weekend, date(2026, 3, 2), date(2026, 3, 8))] == [7, 8]


def test_interval_every_two_weeks_via_start():
    t = task(kind="interval", every=14, start=date(2026, 1, 5))
    assert days(t, date(2026, 1, 1), date(2026, 2, 10)) == [date(2026, 1, 5), date(2026, 1, 19), date(2026, 2, 2)]


def test_interval_accepts_iso_string_start_and_ignores_days_before_start():
    t = task(kind="interval", every=3, start="2026-01-05")
    assert occurs_on(t, date(2026, 1, 8))
    assert not occurs_on(t, date(2026, 1, 2))


def test_monthly_day_falls_on_last_day_of_short_months():
    t = task(kind="monthly_day", day=31)
    assert days(t, date(2026, 1, 1), date(2026, 4, 30)) == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_monthly_day_29_in_leap_and_common_february():
    t = task(kind="monthly_day", day=29)
    assert occurs_on(t, date(2028, 2, 29))
    assert occurs_on(t, date(2027, 2, 28))
    assert not occurs_on(t, date(2027, 3, 1))


@pytest.mark.parametrize("nth, expected", [
    (1, date(2026, 5, 1)), (2, date(2026, 5, 8)), (3, date(2026, 5, 15)),
    (4, date(2026, 5, 22)), (-1, date(2026, 5, 29)),
])
def test_monthly_nth_friday_of_a_five_friday_month(nth, expected):
    t = task(kind="monthly_nth", nth=nth, weekday=4)
    assert days(t, date(2026, 5, 1), date(2026, 5, 31)) == [expected]


def test_last_weekday_in_four_and_five_week_months():
    t = task(kind="monthly_nth", nth=-1, weekday=0)  # last Monday
    assert days(t, date(2026, 2, 1), date(2026, 2, 28)) == [date(2026, 2, 23)]  # 4 Mondays
    assert days(t, date(2026, 3, 1), date(2026, 3, 31)) == [date(2026, 3, 30)]  # 5 Mondays


def test_last_weekday_when_month_ends_on_that_weekday():
    t = task(kind="monthly_nth", nth=-1, weekday=5)  # 28 Feb 2026 is a Saturday
    assert days(t, date(2026, 2, 1), date(2026, 2, 28)) == [date(2026, 2, 28)]


def test_once_occurs_only_on_its_date():
    t = task(kind="once", date=date(2026, 12, 24))
    assert days(t, date(2026, 12, 1), date(2026, 12, 31)) == [date(2026, 12, 24)]
    assert occurrence_index(t, date(2026, 12, 24)) == 0


def test_malformed_rules_never_occur():
    for rec in ({}, {"kind": "fortnightly"}, {"kind": "monthly_day"}, {"kind": "monthly_nth", "nth": 5, "weekday": 1},
                {"kind": "interval", "every": 2}, {"kind": "once"}, {"kind": "weekdays"}):
        assert not occurs_on({"recurrence": rec}, date(2026, 3, 1))
    assert not occurs_on({}, date(2026, 3, 1))


def test_dst_changes_do_not_shift_or_skip_days():
    # Europe/London springs forward on 29 March 2026 and falls back on 25 October 2026.
    t = task(kind="daily")
    for start in (date(2026, 3, 27), date(2026, 10, 23)):
        assert len(days(t, start, start + timedelta(days=4))) == 5
    weekly = task(kind="weekdays", days=[6])  # Sundays, the DST days
    assert days(weekly, date(2026, 3, 22), date(2026, 4, 5)) == [date(2026, 3, 22), date(2026, 3, 29), date(2026, 4, 5)]
    every2 = task(kind="interval", every=2, start=date(2026, 3, 27))
    assert [occurs_on(every2, date(2026, 3, 27) + timedelta(i)) for i in range(5)] == [True, False, True, False, True]


@pytest.mark.parametrize("t, start, end", [
    (task(kind="daily"), date(2026, 1, 1), date(2028, 3, 1)),
    (task(kind="weekdays", days=[0, 2, 5]), date(2026, 1, 1), date(2027, 3, 1)),
    (task(kind="interval", every=3, start=date(2026, 1, 5)), date(2026, 1, 5), date(2026, 9, 1)),
    (task(kind="monthly_day", day=31), date(2026, 1, 1), date(2028, 6, 1)),
    (task(kind="monthly_nth", nth=-1, weekday=4), date(2026, 1, 1), date(2028, 6, 1)),
    (task(kind="monthly_nth", nth=2, weekday=1, start=date(2026, 3, 20)), date(2026, 3, 20), date(2027, 6, 1)),
])
def test_index_counts_occurrences_and_runs_without_gaps(t, start, end):
    occurrences = days(t, start, end)
    first = occurrence_index(t, occurrences[0])
    assert [occurrence_index(t, d) for d in occurrences] == list(range(first, first + len(occurrences)))


def test_index_is_zero_at_start_and_ignores_the_year_boundary():
    t = task(kind="interval", every=7, start=date(2026, 1, 5))
    assert occurrence_index(t, date(2026, 1, 5)) == 0
    assert occurrence_index(t, date(2026, 12, 28)) == 51
    assert occurrence_index(t, date(2027, 1, 4)) == 52


def test_index_of_non_occurrence_counts_those_before_it():
    t = task(kind="weekdays", days=[0], start=date(2026, 3, 2))
    assert occurrence_index(t, date(2026, 3, 9)) == 1
    assert occurrence_index(t, date(2026, 3, 12)) == 2


def test_index_before_anchor_counts_backwards_consistently():
    t = task(kind="interval", every=2, start=date(2026, 3, 10))
    assert occurrence_index(t, date(2026, 3, 10)) == 0
    assert occurrence_index(t, date(2026, 3, 8)) == -1


def test_functions_are_pure_on_plain_dicts():
    t = task(kind="daily")
    before = repr(t)
    occurs_on(t, date(2026, 1, 1)); occurrence_index(t, date(2026, 1, 1))
    assert repr(t) == before
