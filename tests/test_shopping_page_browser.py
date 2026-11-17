"""The shopping page in a real browser: it fits the documented screens in both themes.

Sample items only, in a throwaway data directory. Nothing here is real family data.
"""

import os
import threading
from datetime import datetime

import pytest
from werkzeug.serving import make_server

from dinkydash.store import FileStore
from web import create_app

SIZES = [(800, 480), (1280, 720), (1024, 768)]
CONFIG = ('family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n'
          'features:\n  tasks: true\n  special_dates: true\n  shopping: true\n')
STAMP = datetime(2026, 9, 3, 8, 0).isoformat()


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


def items(count):
    names = ["Milk", "Bread", "Eggs", "Apples", "Pasta", "Tomatoes", "Oat drink with a rather long name "
             "that has to wrap onto a second line"]
    return [{"id": f"i{n}", "text": f"{names[n % len(names)]} {n}" if n >= len(names) else names[n],
             "quantity": "2 litres" if n % 3 == 0 else "", "added_by": "mia",
             "added_at": STAMP, "bought_at": None} for n in range(count)]


@pytest.fixture(scope="module", params=["dark", "light"])
def origin(request, tmp_path_factory):
    folder = tmp_path_factory.mktemp("shopping")
    (folder / "config.yaml").write_text(CONFIG + f'theme: "{request.param}"\n')
    store = FileStore(folder / "config.yaml")
    store.update_shopping(lambda _: items(100))
    server = make_server("127.0.0.1", 0, create_app(store))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", store
    server.shutdown()


MEASURE = """() => {
    const list = document.querySelector('.shop-page-list');
    const box = document.querySelector('[data-shopping-page]').getBoundingClientRect();
    const rows = Array.from(document.querySelectorAll('.shop-page-item:not(.shed)'));
    const inside = rows.every(r => { const b = r.getBoundingClientRect();
        return b.left >= -0.5 && b.right <= innerWidth + 0.5 && b.bottom <= innerHeight + 0.5; });
    const more = document.querySelector('.shop-page-more');
    return {visible: box.width > 0, shown: rows.length, inside,
            clipped: list ? list.scrollHeight > list.clientHeight + 1 : false,
            hscroll: document.documentElement.scrollWidth > innerWidth,
            vscroll: document.documentElement.scrollHeight > innerHeight + 1,
            more: more && !more.hidden ? more.textContent : '',
            text: Math.min(...rows.map(r => parseFloat(getComputedStyle(r).fontSize)))};
}"""


@pytest.mark.parametrize("width,height", SIZES)
def test_a_long_list_fits_and_counts_what_it_hid(browser, origin, width, height):
    url, store = origin
    store.update_shopping(lambda _: items(100))
    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        page.goto(f"{url}/?page=shopping", wait_until="networkidle")
        found = page.evaluate(MEASURE)
        assert found["visible"] and found["inside"] and not found["clipped"]
        assert not found["hscroll"] and not found["vscroll"]
        assert 0 < found["shown"] < 100
        assert found["more"] == f"+{100 - found['shown']} more"
        assert found["text"] >= 12
    finally:
        page.close()


@pytest.mark.parametrize("width,height", SIZES)
def test_a_short_list_shows_everything_without_a_count(browser, origin, width, height):
    url, store = origin
    store.update_shopping(lambda _: items(5))
    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        page.goto(f"{url}/?page=shopping", wait_until="networkidle")
        found = page.evaluate(MEASURE)
        assert found["shown"] == 5 and found["more"] == "" and not found["hscroll"]
    finally:
        page.close()


@pytest.mark.parametrize("width,height", SIZES)
def test_an_empty_list_has_a_clear_empty_state(browser, origin, width, height):
    url, store = origin
    store.update_shopping(lambda _: [])
    page = browser.new_page(viewport={"width": width, "height": height})
    try:
        page.goto(f"{url}/?page=shopping", wait_until="networkidle")
        assert page.is_visible(".shop-page-empty")
        assert page.inner_text(".shop-page-empty") == "Nothing to get"
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    finally:
        page.close()
