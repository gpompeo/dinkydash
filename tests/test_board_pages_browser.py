"""Page navigation and rotation in a real browser.

Timers run on Playwright's fake clock so a thirty-second rotation is checked
without waiting. A second page is registered for the run because the product
ships only the main dashboard.
"""

import os
import threading

import pytest
from werkzeug.serving import make_server

from dinkydash import pages
from dinkydash.pages import Page
from dinkydash.store import FileStore
from web import create_app

CONFIG = 'family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n'


def _launch(playwright):
    errors = []
    for kwargs in ({}, {"channel": "chrome"}):
        try:
            return playwright.chromium.launch(**kwargs)
        except Exception as exc:
            errors.append(f"{kwargs or 'bundled'}: {exc}")
    message = "Chromium is not available (" + "; ".join(errors) + ")."
    if os.environ.get("CI"):
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    manager = sync_playwright().start()
    launched = _launch(manager)
    yield launched
    launched.close()
    manager.stop()


@pytest.fixture(scope="module")
def origin(tmp_path_factory):
    folder = tmp_path_factory.mktemp("pages")
    config = folder / "config.yaml"
    config.write_text(CONFIG)
    saved = pages.REGISTRY
    pages.REGISTRY = (Page("main", "Dashboard"), Page("week", "Week"),
                      Page("shop", "Shopping", feature="shopping"))
    server = make_server("127.0.0.1", 0, create_app(FileStore(config)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    pages.REGISTRY = saved


def open_screen(browser, origin, query="", touch=False, size=(1024, 768)):
    context = browser.new_context(viewport={"width": size[0], "height": size[1]},
                                  has_touch=touch)
    page = context.new_page()
    page.clock.install()
    page.goto(f"{origin}/{query}", wait_until="networkidle")
    return context, page


def shown(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('body > [data-page]'))"
        ".filter(n => !n.hidden).map(n => n.getAttribute('data-page'))")


class TestStaticScreen:
    def test_stays_on_its_selected_page(self, browser, origin):
        context, page = open_screen(browser, origin, "?page=week")
        page.clock.run_for(10 * 60 * 1000)
        assert shown(page) == ["week"]
        assert page.locator("nav.pager").count() == 0
        context.close()

    def test_an_unavailable_selection_shows_the_dashboard(self, browser, origin):
        context, page = open_screen(browser, origin, "?page=shop")
        assert shown(page) == ["main"]
        context.close()


class TestRotation:
    def test_advances_at_the_configured_interval_among_available_pages(self, browser, origin):
        context, page = open_screen(browser, origin, "?rotate=1&every=10")
        assert shown(page) == ["main"]
        page.clock.run_for(9_000)
        assert shown(page) == ["main"]
        page.clock.run_for(2_000)
        assert shown(page) == ["week"]
        page.clock.run_for(10_000)
        assert shown(page) == ["main"]      # wraps; "shop" is switched off
        context.close()

    def test_default_interval_is_thirty_seconds(self, browser, origin):
        context, page = open_screen(browser, origin, "?rotate=1")
        page.clock.run_for(29_000)
        assert shown(page) == ["main"]
        page.clock.run_for(2_000)
        assert shown(page) == ["week"]
        context.close()

    def test_a_refresh_keeps_the_page_on_screen(self, browser, origin):
        context, page = open_screen(browser, origin, "?page=week")
        page.clock.run_for(6 * 60 * 1000)     # past the dashboard's own refresh
        assert shown(page) == ["week"]
        context.close()


class TestTouch:
    def controls(self, page):
        return page.locator("nav.pager")

    def test_navigation_icons_move_between_pages(self, browser, origin):
        context, page = open_screen(browser, origin, "?mode=touch", touch=True)
        page.get_by_role("button", name="Next page").click()
        assert shown(page) == ["week"]
        page.get_by_role("button", name="Next page").click()
        assert shown(page) == ["main"]
        page.get_by_role("button", name="Previous page").click()
        assert shown(page) == ["week"]
        context.close()

    def test_swiping_moves_between_pages(self, browser, origin):
        context, page = open_screen(browser, origin, "?mode=touch", touch=True)
        swipe = """([fromX, toX]) => {
            const send = (type, x) => {
                const t = new Touch({identifier: 1, target: document.body, clientX: x, clientY: 300});
                document.dispatchEvent(new TouchEvent(type, {
                    touches: type === 'touchend' ? [] : [t], changedTouches: [t], bubbles: true}));
            };
            send('touchstart', fromX); send('touchend', toX);
        }"""
        page.evaluate(swipe, [600, 300])
        assert shown(page) == ["week"]
        page.evaluate(swipe, [300, 600])
        assert shown(page) == ["main"]
        page.evaluate(swipe, [300, 320])        # too short to count
        assert shown(page) == ["main"]
        context.close()

    def test_a_non_touch_screen_ignores_swipes(self, browser, origin):
        context, page = open_screen(browser, origin, "", touch=True)
        page.evaluate("""() => {
            const mk = (x) => new Touch({identifier: 1, target: document.body, clientX: x, clientY: 300});
            document.dispatchEvent(new TouchEvent('touchstart', {touches: [mk(600)], changedTouches: [mk(600)], bubbles: true}));
            document.dispatchEvent(new TouchEvent('touchend', {touches: [], changedTouches: [mk(200)], bubbles: true}));
        }""")
        assert shown(page) == ["main"]
        context.close()

    def test_manual_navigation_restarts_the_timer(self, browser, origin):
        context, page = open_screen(browser, origin, "?mode=touch&rotate=1&every=10", touch=True)
        page.clock.run_for(8_000)
        page.get_by_role("button", name="Next page").click()     # now on week at t=8
        page.clock.run_for(8_000)                                 # t=16: 8s since the tap
        assert shown(page) == ["week"]
        page.clock.run_for(3_000)                                 # 11s since the tap
        assert shown(page) == ["main"]
        context.close()

    def test_the_toggle_starts_and_stops_rotation_and_survives_a_reload(self, browser, origin):
        context, page = open_screen(browser, origin, "?mode=touch&every=10", touch=True)
        toggle = page.get_by_role("button", name="Rotate pages automatically")
        assert toggle.get_attribute("aria-pressed") == "false"
        page.clock.run_for(15_000)
        assert shown(page) == ["main"]
        toggle.click()
        assert toggle.get_attribute("aria-pressed") == "true"
        page.clock.run_for(11_000)
        assert shown(page) == ["week"]
        page.reload(wait_until="networkidle")
        toggle = page.get_by_role("button", name="Rotate pages automatically")
        assert toggle.get_attribute("aria-pressed") == "true"
        toggle.click()
        page.reload(wait_until="networkidle")
        assert page.get_by_role("button", name="Rotate pages automatically").get_attribute("aria-pressed") == "false"
        context.close()

    def test_the_setting_belongs_to_the_browser_that_changed_it(self, browser, origin):
        one, a = open_screen(browser, origin, "?mode=touch", touch=True)
        a.get_by_role("button", name="Rotate pages automatically").click()
        two, b = open_screen(browser, origin, "?mode=touch", touch=True)
        assert b.get_by_role("button", name="Rotate pages automatically").get_attribute("aria-pressed") == "false"
        one.close(); two.close()


@pytest.mark.parametrize("size", [(800, 480), (1280, 720), (1024, 768)])
def test_navigation_fits_the_documented_sizes(browser, origin, size):
    context, page = open_screen(browser, origin, "?mode=touch", touch=True, size=size)
    page.evaluate("() => document.fonts.ready")
    box = page.locator("nav.pager").bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= size[1] + 0.5
    assert page.evaluate("() => document.body.scrollHeight <= window.innerHeight + 1")
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    for button in page.locator("nav.pager button").all():
        b = button.bounding_box()
        assert b["width"] >= 43.5 and b["height"] >= 43.5
    context.close()
