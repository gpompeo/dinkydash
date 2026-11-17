"""How the dashboard route turns a screen's link into page markup.

Two screens are two requests with different queries over the same household:
each is set up by its own link and nothing is stored on the server.
"""

import re

import pytest

from dinkydash import pages
from dinkydash.pages import Page
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app

CONFIG = 'family_name: "The Wilsons"\ntimezone: "Europe/Berlin"\n'


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return FileStore(path)


@pytest.fixture
def client(store):
    return client_for(create_app(store))


@pytest.fixture
def two_pages(monkeypatch):
    monkeypatch.setattr(pages, "REGISTRY", (
        Page("main", "Dashboard"),
        Page("week", "Week", feature="tasks"),
        Page("hidden", "Hidden", when=lambda config: False),
    ))


def body_tag(html):
    return re.search(r"<body[^>]*>", html).group(0)


def sections(html):
    return re.findall(r'<section class="page"[^>]*data-page="([^"]+)"', html)


class TestSinglePage:
    def test_no_navigation_and_no_extra_sections(self, client):
        html = client.get("/?mode=touch&rotate=1").get_data(as_text=True)
        assert "<nav" not in html
        assert sections(html) == []
        assert 'data-screen-pages="1"' in body_tag(html)

    def test_the_existing_dashboard_is_still_there_by_default(self, client):
        html = client.get("/").get_data(as_text=True)
        assert 'class="board"' in html and "data-reload" in html


class TestSetupInTheMarkup:
    def test_defaults(self, client, two_pages):
        tag = body_tag(client.get("/").get_data(as_text=True))
        assert 'data-screen-mode="static"' in tag
        assert 'data-screen-page="main"' in tag
        assert 'data-screen-rotate="0"' in tag
        assert 'data-screen-every="30"' in tag

    def test_a_link_sets_this_screen_only(self, client, two_pages):
        a = body_tag(client.get("/?mode=touch&page=week&rotate=1&every=12")
                     .get_data(as_text=True))
        b = body_tag(client.get("/").get_data(as_text=True))
        assert 'data-screen-mode="touch"' in a and 'data-screen-page="week"' in a
        assert 'data-screen-rotate="1"' in a and 'data-screen-every="12"' in a
        assert 'data-screen-mode="static"' in b and 'data-screen-page="main"' in b

    def test_an_unavailable_page_falls_back_to_main(self, client, two_pages):
        for wanted in ("hidden", "nope"):
            tag = body_tag(client.get(f"/?page={wanted}").get_data(as_text=True))
            assert 'data-screen-page="main"' in tag

    def test_a_feature_switched_off_removes_its_page(self, store, two_pages):
        store.save_config({**store.load_config(), "features": {"tasks": False}})
        html = client_for(create_app(store)).get("/?mode=touch&page=week").get_data(as_text=True)
        assert sections(html) == []
        assert 'data-screen-pages="1"' in body_tag(html)
        assert 'data-screen-page="main"' in body_tag(html)

    def test_a_bad_interval_is_thirty(self, client, two_pages):
        tag = body_tag(client.get("/?rotate=1&every=banana").get_data(as_text=True))
        assert 'data-screen-every="30"' in tag

    def test_other_pages_are_in_the_markup_but_hidden(self, client, two_pages):
        html = client.get("/").get_data(as_text=True)
        assert sections(html) == ["week"]
        assert re.search(r'<section class="page"[^>]*data-page="week"[^>]*hidden', html)
        assert "hidden" not in sections(html)


class TestNavigationMarkup:
    def test_a_touch_screen_with_pages_gets_labelled_controls(self, client, two_pages):
        html = client.get("/?mode=touch").get_data(as_text=True)
        nav = re.search(r'<nav class="pager".*?</nav>', html, re.S).group(0)
        assert 'aria-label="Dashboard pages"' in nav
        for name in ("Previous page", "Next page", "Rotate pages automatically"):
            assert f'aria-label="{name}"' in nav
        assert "<svg" in nav and "aria-pressed" in nav

    def test_a_non_touch_screen_has_no_controls(self, client, two_pages):
        assert "<nav" not in client.get("/").get_data(as_text=True)

    def test_the_manifest_keeps_the_setup(self, client, two_pages):
        response = client.get("/manifest.webmanifest?mode=touch&rotate=1")
        assert "mode=touch" in response.get_data(as_text=True)
        assert "rotate=1" in response.get_data(as_text=True)
        assert "mode" not in client.get("/manifest.webmanifest").get_data(as_text=True)

    def test_the_page_points_at_a_manifest_with_the_same_setup(self, client, two_pages):
        html = client.get("/?mode=touch").get_data(as_text=True)
        assert re.search(r'rel="manifest" href="[^"]*manifest\.webmanifest\?mode=touch', html)


class TestWallToken:
    def test_a_token_screen_has_its_own_setup(self, store, monkeypatch, two_pages):
        monkeypatch.setenv("DINKYDASH_PARENT_PASSWORD", "correct horse battery")
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "test-key-not-the-public-one")
        from web.routes.wall import screen_token
        token = screen_token(store)
        client = client_for(create_app(store))
        html = client.get(f"/s/{token}?mode=touch&rotate=1").get_data(as_text=True)
        assert 'data-screen-mode="touch"' in html and 'data-screen-rotate="1"' in html
        manifest = client.get(f"/s/{token}/manifest.webmanifest?mode=touch").get_data(as_text=True)
        assert "mode=touch" in manifest
        plain = client.get(f"/s/{token}").get_data(as_text=True)
        assert 'data-screen-mode="static"' in plain


class TestSetupPage:
    def test_it_makes_a_link_without_writing_anything(self, client, store):
        before = store.load_config()
        html = client.get("/settings/screen/setup?mode=touch&rotate=1&every=45").get_data(as_text=True)
        assert "mode=touch" in html and "rotate=1" in html and "every=45" in html
        assert store.load_config() == before

    def test_the_default_link_has_no_query(self, client):
        html = client.get("/settings/screen/setup").get_data(as_text=True)
        assert re.search(r"user-select:all;\">http://localhost/<", html)

    def test_a_bad_interval_is_said_and_the_link_stays_usable(self, client):
        html = client.get("/settings/screen/setup?rotate=1&every=2").get_data(as_text=True)
        assert 'aria-invalid="true"' in html and "from 5 to 3600" in html
        assert "every=" not in html.split("Link for this screen", 1)[1]

    def test_the_first_page_choice_lists_only_available_pages(self, client, two_pages):
        html = client.get("/settings/screen/setup").get_data(as_text=True)
        assert 'value="week"' in html and 'value="hidden"' not in html

    def test_it_is_linked_from_the_screen_page(self, client):
        assert "/settings/screen/setup" in client.get("/settings/screen").get_data(as_text=True)

    def test_with_sign_in_the_link_is_the_wall_address(self, store, monkeypatch):
        monkeypatch.setenv("DINKYDASH_PARENT_PASSWORD", "correct horse battery")
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "test-key-not-the-public-one")
        client = client_for(create_app(store))
        client.get("/signin")
        client.post("/signin", data={"password": "correct horse battery"})
        html = client.get("/settings/screen/setup?mode=touch").get_data(as_text=True)
        assert "/s/" in html and "mode=touch" in html
