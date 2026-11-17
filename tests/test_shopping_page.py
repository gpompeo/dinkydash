"""The read-only shopping page: its registration, its view, the page and the refresh.

Behaviour through public interfaces. The browser layout is in
`tests/test_shopping_page_browser.py`.
"""

from datetime import datetime

import pytest

from dinkydash import board, pages, shopping as shopping_module
from dinkydash.board import build_view
from dinkydash.config import tzinfo_for
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app

CONFIG = {"family_name": "The Wilsons", "timezone": "Europe/Berlin", "theme": "dark",
          "features": {"tasks": True, "special_dates": True, "shopping": True}}
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=tzinfo_for(CONFIG))
TODAY = NOW.date()
SECTION = '<section class="page" data-page="shopping"'


def item(n, bought_at=None, quantity="", text=None):
    return {"id": f"i{n}", "text": text or f"Thing {n}", "quantity": quantity,
            "added_by": "mia", "added_at": "2026-09-03T08:00:00", "bought_at": bought_at}


def view(items, on=True):
    config = dict(CONFIG, features=dict(CONFIG["features"], shopping=on))
    return build_view(config, None, TODAY, now=NOW, shopping=items)["shopping_page"]


class TestRegistration:
    def test_it_is_registered_after_the_week_with_its_own_partial(self):
        assert [p.key for p in pages.REGISTRY] == ["main", "week", "shopping"]
        assert pages.REGISTRY[2].template == "_shopping.html"

    def test_it_is_offered_only_while_shopping_is_on(self):
        on, off = {"features": {"shopping": True}}, {"features": {"shopping": False}}
        assert [p.key for p in pages.available(on)] == ["main", "shopping"]
        assert [p.key for p in pages.available(off)] == ["main"]
        assert [p.key for p in pages.available({})] == ["main"]


class TestView:
    def test_unbought_items_with_their_quantities(self):
        v = view([item(1, quantity="2 litres"), item(2)])
        assert v["items"] == [{"text": "Thing 1", "quantity": "2 litres"},
                              {"text": "Thing 2", "quantity": ""}]
        assert v["more"] == 0

    def test_bought_items_are_not_unbought(self):
        items = [item(1, bought_at="2026-09-03T09:00:00+02:00"), item(2)]
        assert [i["text"] for i in view(items)["items"]] == ["Thing 2"]

    def test_an_item_bought_long_ago_is_gone(self):
        items = [item(1, bought_at="2026-08-01T09:00:00+02:00"), item(2)]
        assert [i["text"] for i in view(items)["items"]] == ["Thing 2"]

    def test_an_empty_list_has_nothing_and_no_count(self):
        assert view([]) == {"items": [], "more": 0}
        assert view(None) == {"items": [], "more": 0}

    def test_a_long_list_is_capped_and_counts_the_rest(self):
        n = board.MAX_SHOPPING_PAGE + 7
        v = view([item(i) for i in range(n)])
        assert len(v["items"]) == board.MAX_SHOPPING_PAGE and v["more"] == 7

    def test_the_page_holds_more_than_the_wall_card(self):
        assert board.MAX_SHOPPING_PAGE > board.MAX_SHOPPING

    def test_the_list_cap_fits_without_a_count(self):
        v = view([item(i) for i in range(shopping_module.MAX_ITEMS)])
        assert len(v["items"]) + v["more"] == shopping_module.MAX_ITEMS

    def test_switched_off_the_view_is_empty_and_the_data_is_untouched(self):
        items = [item(1)]
        assert view(items, on=False) == {"items": [], "more": 0}
        assert items == [item(1)]

    def test_the_wall_card_is_unchanged(self):
        v = build_view(CONFIG, None, TODAY, now=NOW, shopping=[item(n) for n in range(11)])
        assert len(v["shopping"]) == 8 and v["shopping_more"] == 3


@pytest.fixture
def home(tmp_path):
    (tmp_path / "config.yaml").write_text(
        'family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n'
        'features:\n  tasks: true\n  special_dates: true\n  shopping: true\n')
    return tmp_path


@pytest.fixture
def store(home):
    return FileStore(home / "config.yaml")


def seed(store, items):
    store.update_shopping(lambda _: items)


def section(html):
    html = html[html.index(SECTION):]
    return html[:html.index("</section>")]


class TestThePage:
    def test_it_lists_unbought_items_and_quantities(self, store):
        seed(store, [item(1, quantity="2 litres", text="Milk"), item(2, text="Bread")])
        html = client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True)
        body = section(html)
        assert "Milk" in body and "2 litres" in body and "Bread" in body
        assert 'data-screen-page="shopping"' in html

    def test_bought_items_are_not_listed(self, store):
        seed(store, [item(1, text="Milk"),
                     item(2, text="Bread", bought_at=datetime.now().astimezone().isoformat())])
        body = section(client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True))
        assert "Milk" in body and "Bread" not in body

    def test_an_empty_list_says_so(self, store):
        body = section(client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True))
        assert "Nothing to get" in body
        assert "shop-page-item" not in body

    def test_only_bought_items_is_also_empty(self, store):
        seed(store, [item(1, bought_at=datetime.now().astimezone().isoformat())])
        body = section(client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True))
        assert "Nothing to get" in body

    def test_a_long_list_counts_the_rest(self, store):
        seed(store, [item(i) for i in range(board.MAX_SHOPPING_PAGE + 5)])
        body = section(client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True))
        assert "+5 more" in body

    def test_it_is_read_only(self, store):
        seed(store, [item(1)])
        body = section(client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True))
        assert "<form" not in body and "<button" not in body and "<a " not in body
        assert "<input" not in body

    def test_item_text_is_escaped(self, store):
        seed(store, [item(1, text="<script>alert(1)</script>", quantity="<b>2</b>")])
        html = client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html and "<b>2</b>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_when_shopping_is_off_the_page_is_not_offered_and_data_stays(self, home, store):
        seed(store, [item(1, text="Milk")])
        (home / "config.yaml").write_text(
            'family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n'
            'features:\n  tasks: true\n  special_dates: true\n  shopping: false\n')
        html = client_for(create_app(store)).get("/?page=shopping").get_data(as_text=True)
        assert SECTION not in html and "Milk" not in html
        assert 'data-screen-page="main"' in html
        assert store.load_shopping()[0]["text"] == "Milk"

    def test_it_is_in_the_navigation_when_on(self, store):
        html = client_for(create_app(store)).get("/?mode=touch").get_data(as_text=True)
        assert SECTION in html

    def test_a_phone_side_change_moves_the_change_counter(self, store):
        client = client_for(create_app(store))
        before = client.get("/changes").get_data(as_text=True)
        seed(store, [item(1)])
        assert client.get("/changes").get_data(as_text=True) != before

    def test_the_wall_has_no_shopping_write_route(self, store):
        client = client_for(create_app(store))
        for path in ("/shopping", "/shopping/add", "/s/shopping"):
            assert client.post(path).status_code in (404, 405)
