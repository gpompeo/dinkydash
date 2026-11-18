"""The week page in a real browser: it fits the documented screens and the themes.

A calendar is configured and a payload written for the run, so the page is
offered and has events (past ones included). Nothing here is real family data.
"""

import os
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
from werkzeug.serving import make_server

from dinkydash import config as config_module
from dinkydash.store import FileStore
from web import create_app

SIZES = [(800, 480), (1280, 720), (1024, 768)]
CONFIG = ('family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\nweek_start: "monday"\n'
          'people:\n  - name: "Ada"\n    date_of_birth: "{birth}"\n'
          'special_dates:\n  - title: "Name day"\n    emoji: "🎉"\n    date: "{special}"\n'
          'calendars:\n  - label: "Family"\n    url: "https://example.com/private-xxxx.ics"\n')


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


def _events(today):
    week_start = today - timedelta(days=today.weekday())
    rows = [(0, "Swimming lesson", "09:30"), (0, "Piano", "16:30"), (1, "Inset day", None),
            (2, "Dentist appointment with a rather long title", "14:15"),
            (4, "Parents' evening", "19:00"), (6, "Lunch at Oma's", "12:30")]
    rows += [(3, f"Busy thing {i}", f"{8 + i:02d}:00") for i in range(9)]
    events = []
    for offset, title, time_ in rows:
        day = (week_start + timedelta(days=offset)).isoformat()
        events.append({"title": title, "date": day, "time": time_, "all_day": time_ is None,
                       "start": f"{day}T{time_ or '00:00'}:00+01:00", "location": "Hall",
                       "calendar": "Family"})
    return events


@pytest.fixture(scope="module", params=["dark", "light"])
def origin(request, tmp_path_factory):
    folder = tmp_path_factory.mktemp("week")
    path = folder / "config.yaml"
    monday = date.today() - timedelta(days=date.today().weekday())
    birth = f"2015-{(monday + timedelta(days=1)):%m-%d}"
    special = f"{(monday + timedelta(days=3)):%m/%d}"
    path.write_text(CONFIG.format(birth=birth, special=special) + f'theme: "{request.param}"\n')
    store = FileStore(path)
    config = store.load_config()
    store.save_agenda(config, {"events": _events(config_module.today_for(config)),
                               "calendar_statuses": [],
                               "calendars_fetched_at": datetime.now(timezone.utc).isoformat()})
    server = make_server("127.0.0.1", 0, create_app(store))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.parametrize("width,height", SIZES)
def test_the_week_fits_the_screen_in_both_themes(browser, origin, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        page.goto(f"{origin}/?page=week", wait_until="networkidle")
        found = page.evaluate("""() => {
            const week = document.querySelector('[data-week]');
            const box = week.getBoundingClientRect();
            const days = Array.from(document.querySelectorAll('.week-day'));
            const inside = days.every(d => { const r = d.getBoundingClientRect();
                return r.left >= -0.5 && r.right <= innerWidth + 0.5 && r.bottom <= innerHeight + 0.5; });
            const clipped = days.filter(d => d.scrollHeight > d.clientHeight + 1).length;
            return {visible: box.width > 0, days: days.length, inside, clipped,
                    hscroll: document.documentElement.scrollWidth > innerWidth,
                    title: Math.min(...Array.from(document.querySelectorAll('.week-title'))
                        .map(n => parseFloat(getComputedStyle(n).fontSize))),
                    rows: document.querySelectorAll('.week-gutter-label').length,
                    bands: document.querySelectorAll('.week-band').length,
                    special: document.querySelectorAll('.week-special-item').length,
                    today: document.querySelectorAll('.week-day.today').length};
        }""")
        assert found["rows"] == 3 and found["bands"] == 21 and found["special"] == 2
        assert found["visible"] and found["days"] == 7 and found["today"] == 1
        assert found["inside"] and not found["hscroll"] and found["clipped"] == 0
        assert found["title"] >= 12
        first = page.get_attribute(".week-day .week-weekday", "aria-label")
        assert first == "Monday"
    finally:
        page.close()


@pytest.mark.parametrize("width,height", SIZES)
def test_the_bands_line_up_across_the_week(browser, origin, width, height):
    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        page.goto(f"{origin}/?page=week", wait_until="networkidle")
        found = page.evaluate("""() => {
            const out = {};
            for (const key of ['morning', 'afternoon', 'evening']) {
                const cells = Array.from(document.querySelectorAll(`.week-band[data-band="${key}"]`));
                const boxes = cells.map(c => c.getBoundingClientRect());
                const label = document.querySelector(`.week-gutter-label[data-band="${key}"]`)
                    .getBoundingClientRect();
                out[key] = {n: cells.length,
                    tops: Math.max(...boxes.map(b => b.top)) - Math.min(...boxes.map(b => b.top)),
                    heights: Math.max(...boxes.map(b => b.height)) - Math.min(...boxes.map(b => b.height)),
                    overflow: cells.filter(c => c.scrollHeight > c.clientHeight + 1).length,
                    centred: Math.abs((label.top + label.bottom) / 2 - (boxes[0].top + boxes[0].bottom) / 2),
                    tall: label.height > label.width,
                    size: parseFloat(getComputedStyle(document.querySelector('.week-gutter-label')).fontSize)};
            }
            return out;
        }""")
        for key, band in found.items():
            assert band["n"] == 7, key
            assert band["tops"] < 0.5 and band["heights"] < 0.5, key
            assert band["overflow"] == 0, key
            assert band["centred"] < 1 and band["tall"] and band["size"] >= 12, key
    finally:
        page.close()
