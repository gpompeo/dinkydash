"""The current-week calendar page: the date range, the fetch window, the view and the page.

Behaviour through public interfaces. The browser layout is in
`tests/test_week_browser.py`.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from dinkydash import board, config as config_module, pages, runner, week
from dinkydash.board import build_view
from dinkydash.calendars import fetch_events, parse_feed
from dinkydash.generate import generate
from dinkydash.store import FileStore
from tests.conftest import client_for
from tests.test_generate import FakeClient
from web import create_app

BERLIN = config_module.tzinfo_for({"timezone": "Europe/Berlin"})
CONFIG = {"family_name": "The Wilsons", "timezone": "Europe/Berlin", "theme": "dark",
          "calendars": [{"label": "Family", "url": "https://example.com/private-xxxx.ics"}]}


def event(day, time_="09:00", title="Swimming", all_day=False, **extra):
    return {"title": title, "date": day, "time": None if all_day else time_,
            "all_day": all_day, "start": f"{day}T{time_ or '00:00'}:00+01:00",
            "location": None, "calendar": "Family", **extra}


class TestTheRange:
    def test_sunday_is_the_default(self):
        assert week.week_start_of({}) == "sunday"
        assert week.week_start_of({"week_start": "someday"}) == "sunday"

    def test_a_week_is_seven_days_from_the_start_day(self):
        # Thursday 3 September 2026.
        days = week.days(date(2026, 9, 3), "sunday")
        assert days[0] == date(2026, 8, 30) and days[-1] == date(2026, 9, 5)
        assert len(days) == 7

    @pytest.mark.parametrize("start,first", [
        ("monday", date(2026, 8, 31)), ("tuesday", date(2026, 9, 1)),
        ("wednesday", date(2026, 9, 2)), ("thursday", date(2026, 9, 3)),
        ("friday", date(2026, 8, 28)), ("saturday", date(2026, 8, 29)),
        ("sunday", date(2026, 8, 30)),
    ])
    def test_every_start_day(self, start, first):
        days = week.days(date(2026, 9, 3), start)
        assert days[0] == first
        assert days[0].strftime("%A").lower() == start
        assert days[0] <= date(2026, 9, 3) <= days[-1]

    def test_across_a_month_boundary(self):
        assert week.days(date(2026, 3, 2), "sunday")[0] == date(2026, 3, 1)
        assert week.days(date(2026, 3, 1), "monday")[0] == date(2026, 2, 23)

    def test_across_a_year_boundary(self):
        days = week.days(date(2027, 1, 1), "monday")  # a Friday
        assert days[0] == date(2026, 12, 28) and days[-1] == date(2027, 1, 3)

    def test_the_start_day_itself_opens_a_new_week(self):
        assert week.days(date(2026, 9, 6), "sunday")[0] == date(2026, 9, 6)
        assert week.days(date(2026, 9, 5), "sunday")[-1] == date(2026, 9, 5)

    def test_the_label_names_the_range(self):
        assert week.range_label(week.days(date(2026, 9, 3), "sunday")) == "30 August – 5 September"
        assert week.range_label(week.days(date(2026, 9, 9), "sunday")) == "6 – 12 September"
        assert week.range_label(week.days(date(2027, 1, 1), "monday")) == \
            "28 December 2026 – 3 January 2027"


class TestTheSetting:
    def test_a_missing_setting_is_sunday(self):
        assert config_module.with_defaults({})["week_start"] == "sunday"

    def test_a_saved_day_is_kept_in_any_case(self):
        assert config_module.with_defaults({"week_start": "Monday"})["week_start"] == "monday"

    @pytest.mark.parametrize("bad", ["", "funday", 3, None, ["monday"]])
    def test_anything_else_falls_back_to_sunday(self, bad):
        assert config_module.with_defaults({"week_start": bad})["week_start"] == "sunday"


class TestTheFetchWindow:
    def test_the_window_can_start_before_today(self, monkeypatch):
        seen = []

        def fake_fetch(url, start, end, tzinfo, label=None, timeout=30, shared_with=None):
            seen.append((start, end))
            return []

        monkeypatch.setattr("dinkydash.calendars.fetch_feed", fake_fetch)
        fetch_events([{"label": "F", "url": "x"}], date(2026, 9, 3), BERLIN,
                     since=date(2026, 8, 30))
        assert seen == [(date(2026, 8, 30), date(2026, 9, 17))]

    def test_no_since_means_from_today(self, monkeypatch):
        seen = []
        monkeypatch.setattr("dinkydash.calendars.fetch_feed",
                            lambda url, start, end, *a, **k: seen.append(start) or [])
        fetch_events([{"label": "F", "url": "x"}], date(2026, 9, 3), BERLIN)
        assert seen == [date(2026, 9, 3)]

    def test_an_earlier_event_in_the_window_is_parsed_on_its_own_day(self):
        ical = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:1\r\n"
                "DTSTART:20260831T080000Z\r\nDTEND:20260831T090000Z\r\n"
                "SUMMARY:Monday swim\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        events = parse_feed(ical, date(2026, 8, 30), date(2026, 9, 17), BERLIN, label="F")
        assert [(e["title"], e["date"], e["time"]) for e in events] == \
            [("Monday swim", "2026-08-31", "10:00")]


CONFIG_YAML = ('family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n'
               'calendars:\n  - label: "Family"\n    url: "https://example.com/private-xxxx.ics"\n')


@pytest.fixture
def home(tmp_path):
    (tmp_path / "config.yaml").write_text(CONFIG_YAML)
    return tmp_path


@pytest.fixture
def store(home):
    return FileStore(home / "config.yaml")


def stored(home):
    return json.loads((home / "dashboard_data.json").read_text())


def fetcher(seen, events=(), ok=True):
    def _fetch(calendars, today, tzinfo, days_ahead=14, timeout=30, since=None):
        seen.append({"today": today, "since": since, "days_ahead": days_ahead})
        return list(events), [{"label": "Family", "ok": ok, "detail": "", "count": 0}]
    return _fetch


class TestRefresh:
    def test_the_fetch_reaches_back_to_the_start_of_the_familys_week(self, store, monkeypatch):
        seen = []
        monkeypatch.setattr(runner, "fetch_events", fetcher(seen))
        # 23:30 UTC on Thursday 3 September is already Friday in Berlin.
        runner.refresh_calendars(store.load_config(), store,
                                 now=datetime(2026, 9, 3, 23, 30, tzinfo=timezone.utc))
        assert seen[0]["today"] == date(2026, 9, 4)
        assert seen[0]["since"] == date(2026, 8, 30)

    def test_it_follows_the_week_start_setting(self, home, store, monkeypatch):
        (home / "config.yaml").write_text(CONFIG_YAML + 'week_start: "monday"\n')
        seen = []
        monkeypatch.setattr(runner, "fetch_events", fetcher(seen))
        runner.refresh_calendars(store.load_config(), store,
                                 now=datetime(2026, 9, 6, 12, tzinfo=timezone.utc))  # a Sunday
        assert seen[0]["since"] == date(2026, 8, 31)

    def test_a_failing_feed_keeps_its_events_from_earlier_this_week(self, home, store,
                                                                    monkeypatch):
        kept = event("2026-08-31", title="Monday swim")
        long_gone = event("2026-08-29", title="Last week")
        (home / "dashboard_data.json").write_text(json.dumps({"events": [long_gone, kept]}))
        monkeypatch.setattr(runner, "fetch_events", fetcher([], ok=False))
        runner.refresh_calendars(store.load_config(), store,
                                 now=datetime(2026, 9, 3, 8, tzinfo=timezone.utc))
        assert [e["title"] for e in stored(home)["events"]] == ["Monday swim"]

    def test_a_day_later_the_week_still_has_its_past_days(self, home, store, monkeypatch):
        # Midnight rolls the week on only when the start day arrives.
        (home / "dashboard_data.json").write_text(
            json.dumps({"events": [event("2026-08-31", title="Monday swim")]}))
        monkeypatch.setattr(runner, "fetch_events", fetcher([], ok=False))
        runner.refresh_calendars(store.load_config(), store,
                                 now=datetime(2026, 9, 5, 8, tzinfo=timezone.utc))
        assert [e["title"] for e in stored(home)["events"]] == ["Monday swim"]
        runner.refresh_calendars(store.load_config(), store,
                                 now=datetime(2026, 9, 6, 8, tzinfo=timezone.utc))  # new week
        assert stored(home)["events"] == []

    def test_changing_the_week_start_forgets_a_window_that_no_longer_fits(self, home, store):
        config = store.load_config()
        store.save_agenda(config, {"events": [event("2026-09-03")], "calendar_statuses": [],
                                   "calendars_fetched_at": "2026-09-03T08:00:00+00:00"})
        store.save_config(dict(config, week_start="monday"))
        assert store.load_payload(config)["events"] == []


class TestTheHeadlineStaysAboutNow:
    def test_earlier_days_of_the_week_never_reach_the_model(self):
        client = FakeClient()
        events = [event("2026-08-30", title="Secret Sunday appointment"),
                  event("2026-09-02", title="Wednesday dentist"),
                  event("2026-09-03", title="Swimming today"),
                  event("2026-09-04", title="Tomorrow's trip")]
        payload = generate({**CONFIG, "claude_model": "claude-haiku-4-5", "max_tokens": 1024},
                           date(2026, 9, 3), events, client=client)
        sent = client.messages.calls[0]["messages"][0]["content"]
        assert "Swimming today" in sent and "Tomorrow's trip" in sent
        assert "Secret Sunday appointment" not in sent and "Wednesday dentist" not in sent
        assert len(payload["events"]) == 4  # kept for the wall, never sent


TODAY = date(2026, 9, 3)  # a Thursday
SECTION = '<section class="page" data-page="week"'


def titles(day):
    """Every event title of a day, all-day first then the rows in order."""
    return [e["title"] for e in day["all_day"]] + \
        [e["title"] for r in day["rows"] for e in r["events"]]


class TestTheRowOfADay:
    @pytest.mark.parametrize("time_,row", [
        ("00:00", "morning"), ("11:59", "morning"), ("12:00", "afternoon"),
        ("17:59", "afternoon"), ("18:00", "evening"), ("23:59", "evening")])
    def test_the_boundaries(self, time_, row):
        assert week.row_of(time_) == row

    def test_it_reads_a_full_start_too(self):
        assert week.row_of("2026-09-02T17:59:00+01:00") == "afternoon"

    def test_the_boundaries_are_named_constants(self):
        assert (week.AFTERNOON_STARTS, week.EVENING_STARTS) == (12, 18)
        assert [key for key, _ in week.ROWS] == ["morning", "afternoon", "evening"]

    @pytest.mark.parametrize("bad", [None, "", "soon", "25:00"])
    def test_an_unreadable_time_has_no_row(self, bad):
        assert week.row_of(bad) is None


class TestTheView:
    def view(self, events, config=None, today=TODAY):
        return build_view({**CONFIG, **(config or {})}, {"events": events}, today)["week"]

    def test_seven_days_in_the_configured_order_with_past_days(self):
        shown = self.view([event("2026-08-30", title="Sunday brunch"),
                           event("2026-09-03"), event("2026-09-05", title="Party")])
        assert [d["date"] for d in shown["days"]] == [
            "2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02",
            "2026-09-03", "2026-09-04", "2026-09-05"]
        assert [titles(d)[0] for d in shown["days"] if titles(d)] == \
            ["Sunday brunch", "Swimming", "Party"]
        assert shown["range"] == "30 August – 5 September"

    def test_monday_start_changes_the_range(self):
        shown = self.view([], {"week_start": "monday"})
        assert shown["days"][0]["date"] == "2026-08-31" and shown["days"][-1]["date"] == "2026-09-06"

    def test_today_and_past_are_marked(self):
        days = self.view([])["days"]
        assert [d["today"] for d in days].count(True) == 1
        assert days[4]["today"] and days[3]["past"] and not days[5]["past"]

    def test_day_names_and_numbers(self):
        day = self.view([])["days"][0]
        assert (day["weekday"], day["weekday_name"], day["day"]) == ("Sun", "Sunday", 30)

    def test_events_outside_the_week_are_not_shown(self):
        shown = self.view([event("2026-08-29"), event("2026-09-06")])
        assert all(not titles(d) for d in shown["days"])

    def test_an_empty_day_is_empty_and_still_has_its_three_rows(self):
        day = self.view([])["days"][1]
        assert day["empty"] and day["special"] == [] and day["all_day"] == []
        assert [r["label"] for r in day["rows"]] == ["Morning", "Afternoon", "Evening"]
        assert all(r["events"] == [] and r["more"] == 0 for r in day["rows"])

    def test_all_day_events_sit_above_the_rows_not_in_them(self):
        day = self.view([event("2026-09-01", "00:00", "Inset day", all_day=True),
                         event("2026-09-01", "08:00", "School run")])["days"][2]
        assert [e["title"] for e in day["all_day"]] == ["Inset day"]
        assert [e["title"] for e in day["rows"][0]["events"]] == ["School run"]
        assert not day["empty"]

    @pytest.mark.parametrize("time_,row", [
        ("00:00", 0), ("11:59", 0), ("12:00", 1), ("17:59", 1), ("18:00", 2), ("23:59", 2)])
    def test_a_timed_event_lands_in_the_row_its_start_falls_in(self, time_, row):
        day = self.view([event("2026-09-02", time_, "X")])["days"][3]
        assert [len(r["events"]) for r in day["rows"]] == [int(i == row) for i in range(3)]

    def test_a_timed_event_with_an_unreadable_time_is_listed_with_the_all_day_ones(self):
        day = self.view([event("2026-09-02", "soon", "Mystery", start="soon"),
                         event("2026-09-02", "08:00", "School run")])["days"][3]
        assert [e["title"] for e in day["all_day"]] == ["Mystery"]
        assert [e["title"] for e in day["rows"][0]["events"]] == ["School run"]
        assert not day["empty"]

    def test_all_day_events_are_not_capped(self):
        many = [event("2026-09-02", "00:00", f"Day {i}", all_day=True) for i in range(8)]
        day = self.view(many)["days"][3]
        assert len(day["all_day"]) == 8

    def test_events_keep_their_order_within_a_row(self):
        day = self.view([event("2026-09-02", "10:00", "Later"),
                         event("2026-09-02", "08:00", "Earlier")])["days"][3]
        assert [e["title"] for e in day["rows"][0]["events"]] == ["Earlier", "Later"]

    def test_times_follow_the_clock_setting(self):
        evening = event("2026-09-02", "15:45")
        assert self.view([evening])["days"][3]["rows"][1]["events"][0]["time"] == "15:45"
        assert self.view([evening], {"clock": "12h"})["days"][3]["rows"][1]["events"][0]["time"] \
            == "3:45 pm"

    def test_twelve_hour_times_are_written_in_their_own_row(self):
        late = event("2026-09-02", "23:59")
        row = self.view([late], {"clock": "12h"})["days"][3]["rows"][2]
        assert row["events"][0]["time"] == "11:59 pm"

    PEOPLE = [{"id": "a", "name": "Ada", "date_of_birth": "2015-09-02"}]
    SPECIAL = [{"title": "Name day", "emoji": "🎉", "date": "09/04"}]

    def test_a_birthday_and_a_special_date_lead_their_day(self):
        shown = self.view([], {"people": self.PEOPLE, "special_dates": self.SPECIAL})["days"]
        assert [(s["emoji"], s["title"]) for s in shown[3]["special"]] == \
            [("🎂", "Ada's birthday")]
        assert [(s["emoji"], s["title"]) for s in shown[5]["special"]] == [("🎉", "Name day")]
        assert not shown[3]["empty"]
        assert shown[2]["special"] == [] and shown[4]["special"] == []

    def test_the_special_dates_switch_hides_both_like_the_countdowns(self):
        config = {"people": self.PEOPLE, "special_dates": self.SPECIAL,
                  "features": {"special_dates": False}}
        assert all(d["special"] == [] for d in self.view([], config)["days"])

    def test_a_leap_day_is_found_in_a_leap_year_week(self):
        config = {"special_dates": [{"title": "Leap", "emoji": "", "date": "02/29"}]}
        week_of = self.view([], config, today=date(2028, 2, 28))["days"]
        assert [d["special"][0]["title"] for d in week_of if d["special"]] == ["Leap"]
        assert [d["date"] for d in week_of if d["special"]] == ["2028-02-29"]

    def test_a_calendar_that_hides_locations_does_not_show_them(self):
        config = {"calendars": [{"label": "Family", "url": "x", "show_locations": False}]}
        shown = self.view([event("2026-09-02", location="12 Private Road")], config)
        assert "12 Private Road" not in json.dumps(shown)

    def test_a_crowded_day_is_capped_and_counts_the_rest(self):
        many = [event("2026-09-02", f"{i % 12:02d}:00", f"Thing {i}")
                for i in range(board.MAX_WEEK_EVENTS + 3)]
        many.append(event("2026-09-02", "19:00", "Dinner"))
        day = self.view(many)["days"][3]
        morning, afternoon, evening = day["rows"]
        assert len(morning["events"]) == board.MAX_WEEK_EVENTS
        assert len(evening["events"]) == 1 and evening["more"] == 0
        assert day["all_day"] == []

    def test_more_than_the_cap_counts_in_that_row_only(self):
        n = board.MAX_WEEK_EVENTS + 2
        many = [event("2026-09-02", f"{i % 12:02d}:00", f"M{i}") for i in range(n)]
        many.append(event("2026-09-02", "13:00", "Lunch"))
        morning, afternoon, evening = self.view(many)["days"][3]["rows"]
        assert (len(morning["events"]), morning["more"]) == (board.MAX_WEEK_EVENTS, 2)
        assert (len(afternoon["events"]), afternoon["more"]) == (1, 0)
        assert (len(evening["events"]), evening["more"]) == (0, 0)

    def test_the_week_is_worked_out_from_the_date_not_the_payload(self):
        # A payload fetched days ago still produces today's week.
        later = self.view([event("2026-09-02")], today=date(2026, 9, 6))
        assert later["days"][0]["date"] == "2026-09-06"

    def test_the_payload_is_not_changed(self):
        events = [event("2026-09-02", location="Pool")]
        before = json.dumps(events)
        self.view(events, {"clock": "12h"})
        assert json.dumps(events) == before


class TestThePage:
    def test_it_is_registered_in_the_navigation(self):
        assert [p.key for p in pages.REGISTRY][:2] == ["main", "week"]
        assert pages.REGISTRY[1].template == "_week.html"

    def test_it_needs_a_calendar_to_show(self):
        assert [p.key for p in pages.available(CONFIG)] == ["main", "week"]
        assert [p.key for p in pages.available({"calendars": []})] == ["main"]
        paused = {"calendars": [{"label": "F", "url": "x", "enabled": False}]}
        assert [p.key for p in pages.available(paused)] == ["main"]


@pytest.fixture
def client(home):
    store = FileStore(home / "config.yaml")
    config = store.load_config()
    today = config_module.today_for(config)
    store.save_agenda(config, {
        "events": [event(today.isoformat(), "09:00", "<script>alert(1)</script>")],
        "calendar_statuses": [], "calendars_fetched_at": datetime.now(timezone.utc).isoformat()})
    return client_for(create_app(store))


class TestTheRoute:
    def test_a_week_section_is_drawn_read_only(self, client):
        html = client.get("/?page=week").get_data(as_text=True)
        assert SECTION in html and "data-week" in html
        section = html[html.index(SECTION):]
        section = section[:section.index("</section>")]
        assert "<form" not in section and "<button" not in section and "<a " not in section

    def test_event_titles_are_escaped(self, client):
        html = client.get("/?page=week").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_the_page_opens_on_week_when_asked(self, client):
        assert 'data-screen-page="week"' in client.get("/?page=week").get_data(as_text=True)

    def test_without_calendars_the_page_is_not_offered(self, home):
        (home / "config.yaml").write_text('family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n')
        html = client_for(create_app(FileStore(home / "config.yaml"))).get("/?page=week") \
            .get_data(as_text=True)
        assert SECTION not in html and 'data-screen-page="main"' in html


class TestSettings:
    @pytest.fixture
    def settings(self, home):
        store = FileStore(home / "config.yaml")
        return client_for(create_app(store)), store

    def test_the_system_page_offers_every_day_with_sunday_chosen(self, settings):
        html = settings[0].get("/settings/system").get_data(as_text=True)
        assert 'name="week_start"' in html
        for name in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
            assert f">{name}<" in html
        assert 'value="sunday" selected' in html

    def test_a_chosen_day_is_saved(self, settings):
        client, store = settings
        client.post("/settings/system", data={"family_name": "The Wilsons",
                                              "timezone": "Europe/Berlin", "week_start": "monday"})
        assert store.load_config()["week_start"] == "monday"

    def test_an_unknown_day_leaves_the_setting_alone(self, settings):
        client, store = settings
        client.post("/settings/system", data={"family_name": "The Wilsons",
                                              "week_start": "funday"})
        assert store.load_config()["week_start"] == "sunday"


class TestGuidance:
    def test_the_setting_and_the_data_handling_are_documented(self):
        from pathlib import Path
        guide = (Path(__file__).resolve().parent.parent / "doc/self-hosting.md").read_text()
        assert "`week_start`" in guide
        assert "The week page" in guide and "never added to the headline prompt" in guide
