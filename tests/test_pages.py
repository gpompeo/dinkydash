"""Dashboard pages: which exist, which a screen may show, and how a screen is set up.

Everything here is pure: the registry, a screen's setup read from its link, and
the choice of page. The browser behaviour is in `tests/test_board_pages_browser.py`.
"""

from dinkydash import pages
from dinkydash.pages import Page

TWO = (Page("main", "Dashboard"),
       Page("week", "Week", feature="tasks"),
       Page("shop", "Shopping", feature="shopping"))


class TestAvailability:
    def test_the_real_registry_offers_the_week_only_with_a_calendar(self):
        assert [p.key for p in pages.available({})] == ["main"]
        calendars = {"calendars": [{"label": "F", "url": "https://example.com/private-xxxx"}]}
        assert [p.key for p in pages.available(calendars)] == ["main", "week"]

    def test_the_main_dashboard_is_always_available(self):
        config = {"features": {"tasks": False, "shopping": False, "special_dates": False}}
        assert [p.key for p in pages.available(config, TWO)] == ["main"]

    def test_a_page_follows_its_feature_switch(self):
        on = {"features": {"tasks": True, "shopping": False}}
        assert [p.key for p in pages.available(on, TWO)] == ["main", "week"]

    def test_a_page_can_be_withheld_by_a_condition(self):
        gated = (Page("main", "Dashboard"), Page("x", "X", when=lambda config: False))
        assert [p.key for p in pages.available({}, gated)] == ["main"]


class TestSetupFromTheLink:
    def test_no_options_means_static_main_no_rotation_thirty_seconds(self):
        setup, problems = pages.parse_setup({})
        assert (setup.touch, setup.page, setup.rotate, setup.interval) == (False, "main", False, 30)
        assert problems == {}

    def test_every_option_is_read(self):
        setup, problems = pages.parse_setup(
            {"mode": "touch", "page": "week", "rotate": "1", "every": "45"})
        assert (setup.touch, setup.page, setup.rotate, setup.interval) == (True, "week", True, 45)
        assert problems == {}

    def test_rotation_off_is_explicit(self):
        setup, _ = pages.parse_setup({"rotate": "0"})
        assert setup.rotate is False

    def test_a_bad_interval_falls_back_to_thirty_and_is_reported(self):
        for bad in ("", "abc", "0", "4", "-5", "3601", "1.5", "99999999999999999999"):
            setup, problems = pages.parse_setup({"every": bad, "rotate": "1"})
            assert setup.interval == 30, bad
            if bad:
                assert "every" in problems, bad

    def test_the_interval_bounds_are_accepted(self):
        for good, value in (("5", 5), ("3600", 3600)):
            setup, problems = pages.parse_setup({"every": good})
            assert (setup.interval, problems) == (value, {})

    def test_an_unknown_mode_is_static(self):
        setup, problems = pages.parse_setup({"mode": "weird"})
        assert setup.touch is False and "mode" in problems

    def test_two_setups_are_independent(self):
        a, _ = pages.parse_setup({"mode": "touch", "rotate": "1", "every": "10"})
        b, _ = pages.parse_setup({"page": "week"})
        assert (a.touch, a.rotate, a.interval) == (True, True, 10)
        assert (b.touch, b.rotate, b.page) == (False, False, "week")


class TestChoosingAPage:
    def keys(self, *names):
        return [Page(n, n) for n in names]

    def test_the_selected_page_is_shown_when_available(self):
        assert pages.initial_key("week", self.keys("main", "week")) == "week"

    def test_an_unknown_or_disabled_page_falls_back_to_main(self):
        assert pages.initial_key("gone", self.keys("main", "week")) == "main"
        assert pages.initial_key("week", self.keys("main")) == "main"

    def test_a_missing_main_falls_back_to_the_first_available(self):
        assert pages.initial_key("main", self.keys("week")) == "week"

    def test_nothing_available_is_main(self):
        assert pages.initial_key("week", []) == "main"


class TestTheLink:
    def test_defaults_add_nothing_to_the_link(self):
        setup, _ = pages.parse_setup({})
        assert pages.link_query(setup) == {}

    def test_only_what_differs_is_written(self):
        setup, _ = pages.parse_setup(
            {"mode": "touch", "page": "week", "rotate": "1", "every": "45"})
        assert pages.link_query(setup) == {
            "mode": "touch", "page": "week", "rotate": "1", "every": "45"}

    def test_the_interval_is_only_written_when_rotation_is_on(self):
        setup, _ = pages.parse_setup({"every": "45"})
        assert "every" not in pages.link_query(setup)

    def test_a_link_reads_back_to_the_same_setup(self):
        original, _ = pages.parse_setup(
            {"mode": "touch", "page": "shop", "rotate": "1", "every": "12"})
        again, _ = pages.parse_setup(pages.link_query(original))
        assert again == original
