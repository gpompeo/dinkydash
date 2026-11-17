"""Reading the task editor's recurrence and assignment fields back into a task."""

from datetime import date

from dinkydash import taskform

TODAY = date(2026, 3, 4)


def read(**form):
    return taskform.recurrence_from_form(MultiDict(form), TODAY)


class MultiDict(dict):
    def getlist(self, key):
        value = self.get(key, [])
        return value if isinstance(value, list) else [value]


class TestRecurrence:
    def test_every_day(self):
        assert read(rec_kind="daily") == ({"kind": "daily"}, {})

    def test_weekdays_and_weekends_are_presets(self):
        assert read(rec_kind="weekdays")[0] == {"kind": "weekdays", "days": [0, 1, 2, 3, 4]}
        assert read(rec_kind="weekends")[0] == {"kind": "weekdays", "days": [5, 6]}

    def test_chosen_days_are_sorted_and_checked(self):
        assert read(rec_kind="days", rec_days=["4", "1", "1", "9", "x"])[0] == {
            "kind": "weekdays", "days": [1, 4]}
        assert "rec_days" in read(rec_kind="days")[1]

    def test_every_n_days_starts_today_when_blank(self):
        assert read(rec_kind="interval", rec_every="3", rec_start="")[0] == {
            "kind": "interval", "every": 3, "start": "2026-03-04"}

    def test_every_n_days_refuses_nonsense(self):
        for bad in ("0", "-2", "x", "", "400"):
            assert "rec_every" in read(rec_kind="interval", rec_every=bad)[1]
        assert "rec_start" in read(rec_kind="interval", rec_every="2", rec_start="soon")[1]

    def test_monthly_on_a_day_number(self):
        assert read(rec_kind="monthly_day", rec_day="31")[0] == {"kind": "monthly_day", "day": 31}
        assert "rec_day" in read(rec_kind="monthly_day", rec_day="32")[1]

    def test_monthly_on_a_weekday(self):
        assert read(rec_kind="monthly_nth", rec_nth="-1", rec_weekday="4")[0] == {
            "kind": "monthly_nth", "nth": -1, "weekday": 4}
        assert "rec_nth" in read(rec_kind="monthly_nth", rec_nth="5", rec_weekday="4")[1]
        assert "rec_weekday" in read(rec_kind="monthly_nth", rec_nth="2", rec_weekday="7")[1]

    def test_once_needs_a_date(self):
        assert read(rec_kind="once", rec_date="2026-12-24")[0] == {
            "kind": "once", "date": "2026-12-24"}
        assert "rec_date" in read(rec_kind="once", rec_date="")[1]

    def test_an_unknown_kind_is_refused(self):
        assert "rec_kind" in read(rec_kind="sometimes")[1]


class TestStateForTheForm:
    def test_presets_are_recognised(self):
        assert taskform.recurrence_state({"kind": "weekdays", "days": [4, 0, 1, 2, 3]}, TODAY)["kind"] == "weekdays"
        assert taskform.recurrence_state({"kind": "weekdays", "days": [5, 6]}, TODAY)["kind"] == "weekends"
        state = taskform.recurrence_state({"kind": "weekdays", "days": [1]}, TODAY)
        assert state["kind"] == "days" and state["days"] == [1]

    def test_round_trip_of_every_kind(self):
        for rec in ({"kind": "daily"}, {"kind": "interval", "every": 2, "start": "2026-01-05"},
                    {"kind": "monthly_day", "day": 15}, {"kind": "monthly_nth", "nth": 2, "weekday": 0},
                    {"kind": "once", "date": "2026-12-24"}, {"kind": "weekdays", "days": [0, 2]}):
            state = taskform.recurrence_state(rec, TODAY)
            posted = {"rec_kind": state["kind"], "rec_days": [str(d) for d in state["days"]],
                      "rec_every": str(state["every"]), "rec_start": state["start"],
                      "rec_day": str(state["day"]), "rec_nth": str(state["nth"]),
                      "rec_weekday": str(state["weekday"]), "rec_date": state["date"]}
            assert read(**posted) == (rec, {})

    def test_a_missing_or_malformed_rule_shows_every_day(self):
        assert taskform.recurrence_state(None, TODAY)["kind"] == "daily"
        assert taskform.recurrence_state({"kind": "bogus"}, TODAY)["kind"] == "daily"
