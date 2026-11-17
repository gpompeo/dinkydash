"""One theme setting, three surfaces, and the PompDash name and icons.

`theme` in config.yaml is `light` or `dark`; a missing or unrecognised value is
dark. The dashboard, the settings UI and the phone page all read it, and every
colour they paint comes from the tokens in `web/templates/_theme.html`.
"""

import json
import re
from pathlib import Path

import pytest

from dinkydash import config as config_module
from dinkydash.board import build_view
from dinkydash.config import DEFAULT_THEME, THEME_COLOURS, theme_of
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, parent

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "web" / "templates"
THEME_FILE = TEMPLATES / "_theme.html"

PEOPLE = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - id: mia1
    name: "Mia"
    date_of_birth: "2017-03-15"
"""


def app_with(tmp_path, monkeypatch, theme_line=""):
    monkeypatch.delenv(parent.PASSWORD_VARIABLE, raising=False)
    path = tmp_path / "config.yaml"
    path.write_text(PEOPLE + theme_line)
    return create_app(FileStore(path))


def surfaces(client):
    """The three pages that must agree, as HTML."""
    client.get("/h/who")
    return {
        "dashboard": client.get("/").get_data(as_text=True),
        "settings": client.get("/settings/").get_data(as_text=True),
        "phone": client.get("/h/who").get_data(as_text=True),
    }


class TestResolution:
    def test_a_missing_theme_is_dark(self):
        assert theme_of({}) == "dark" == DEFAULT_THEME

    def test_an_unrecognised_theme_is_dark(self):
        assert theme_of({"theme": "neon"}) == "dark"
        assert theme_of({"theme": None}) == "dark"

    @pytest.mark.parametrize("saved", ["light", "dark"])
    def test_an_explicit_theme_keeps_its_meaning(self, saved):
        assert theme_of({"theme": saved}) == saved

    def test_with_defaults_migrates_a_missing_theme_to_dark(self):
        assert config_module.with_defaults({})["theme"] == "dark"

    @pytest.mark.parametrize("saved", ["light", "dark"])
    def test_with_defaults_leaves_a_saved_theme_alone(self, saved):
        assert config_module.with_defaults({"theme": saved})["theme"] == saved

    def test_the_example_config_defaults_to_dark(self):
        text = (REPO / "config.example.yaml").read_text()
        assert re.search(r"^theme: dark\s*$", text, re.M)

    def test_the_dashboard_view_carries_the_resolved_theme_and_its_colour(self):
        view = build_view({}, None, __import__("datetime").date(2026, 9, 3))
        assert view["theme"] == "dark"
        assert view["theme_colour"] == THEME_COLOURS["dark"]


class TestOneSettingDrivesEverySurface:
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_every_page_is_drawn_in_the_saved_theme(self, tmp_path, monkeypatch, theme):
        client = client_for(app_with(tmp_path, monkeypatch, f"theme: {theme}\n"))
        for name, page in surfaces(client).items():
            assert f'data-theme="{theme}"' in page.split("<head>")[0], name
            assert f'<meta name="theme-color" content="{THEME_COLOURS[theme]}">' in page, name

    def test_no_theme_saved_means_dark_everywhere(self, tmp_path, monkeypatch):
        client = client_for(app_with(tmp_path, monkeypatch))
        for name, page in surfaces(client).items():
            assert 'data-theme="dark"' in page.split("<head>")[0], name

    def test_changing_it_in_settings_changes_all_three(self, tmp_path, monkeypatch):
        client = client_for(app_with(tmp_path, monkeypatch, "theme: dark\n"))
        client.get("/settings/screen")
        client.post("/settings/screen", data={"theme": "light"})
        for name, page in surfaces(client).items():
            assert 'data-theme="light"' in page.split("<head>")[0], name

    def test_the_manifests_paint_the_themes_own_colour(self, tmp_path, monkeypatch):
        for theme in ("light", "dark"):
            client = client_for(app_with(tmp_path, monkeypatch, f"theme: {theme}\n"))
            for url in ("/manifest.webmanifest", "/settings/manifest.webmanifest",
                        "/h/manifest.webmanifest"):
                manifest = client.get(url).get_json(force=True)
                assert manifest["theme_color"] == THEME_COLOURS[theme], url
                assert manifest["background_color"] == THEME_COLOURS[theme], url

    def test_the_picker_previews_each_theme_in_its_own_palette(self, tmp_path, monkeypatch):
        client = client_for(app_with(tmp_path, monkeypatch, "theme: dark\n"))
        page = client.get("/settings/screen").get_data(as_text=True)
        for theme in ("light", "dark"):
            assert f'<div data-theme="{theme}"' in page
        assert re.search(r'<input type="radio" name="theme" value="dark" checked', page)


class TestTokens:
    def test_no_template_hard_codes_a_colour_outside_the_theme_file(self):
        hex_or_fn = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(\s*\d")
        offenders = []
        for path in TEMPLATES.rglob("*.html"):
            if path == THEME_FILE:
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                # `&#9650;` style entities and `#anchor` links are not colours.
                scrubbed = re.sub(r"&#\d+;|href=\"#[^\"]*\"|url\(#[^)]*\)", "", line)
                if hex_or_fn.search(scrubbed):
                    offenders.append(f"{path.relative_to(REPO)}:{number}")
        assert offenders == []

    def test_the_page_colours_match_the_bg_tokens(self):
        css = THEME_FILE.read_text()
        dark = css[css.index("macro dark_tokens"):css.index("macro light_tokens")]
        light = css[css.index("macro light_tokens"):css.index('<style id="theme-tokens">')]
        assert re.search(r"--bg: (#\w+);", dark).group(1) == THEME_COLOURS["dark"]
        assert re.search(r"--bg: (#\w+);", light).group(1) == THEME_COLOURS["light"]

    def test_both_themes_define_the_same_tokens(self):
        css = THEME_FILE.read_text()
        dark = css[css.index("macro dark_tokens"):css.index("macro light_tokens")]
        light = css[css.index("macro light_tokens"):css.index('<style id="theme-tokens">')]
        names = lambda block: set(re.findall(r"(--[\w-]+):", block))
        assert names(dark) == names(light)

    def test_every_token_a_template_reads_is_defined(self):
        defined = set(re.findall(r"(--[\w-]+):", THEME_FILE.read_text()))
        own = {"--time-column", "--display", "--shell", "--radius", "--preview-width",
               "--device-ratio"}
        used = set()
        for path in TEMPLATES.rglob("*.html"):
            used |= set(re.findall(r"var\((--[\w-]+)", path.read_text()))
        assert used - defined - own == set()


def _luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(macro):
    css = THEME_FILE.read_text()
    start = css.index(f"macro {macro}")
    block = css[start:css.index("endmacro", start)]
    return dict(re.findall(r"(--[\w-]+): (#[0-9a-fA-F]{6});", block))


class TestContrast:
    @pytest.mark.parametrize("macro", ["dark_tokens", "light_tokens"])
    def test_text_and_status_colours_read_on_every_surface(self, macro):
        t = _tokens(macro)
        for surface in ("--bg", "--surface", "--warm"):
            for name in ("--text", "--text-mid", "--text-muted", "--accent", "--accent-dark",
                         "--purple", "--green", "--amber", "--danger"):
                assert _ratio(t[name], t[surface]) >= 4.5, (macro, name, surface)

    @pytest.mark.parametrize("macro", ["dark_tokens", "light_tokens"])
    def test_a_filled_button_label_reads_on_its_fill(self, macro):
        t = _tokens(macro)
        assert _ratio(t["--on-accent"], t["--accent"]) >= 4.5
        assert _ratio(t["--on-accent"], t["--accent-pressed"]) >= 4.5
        assert _ratio(t["--on-accent"], t["--danger"]) >= 4.5
        assert _ratio(t["--on-accent"], t["--danger-dark"]) >= 4.5

    @pytest.mark.parametrize("macro", ["dark_tokens", "light_tokens"])
    def test_control_edges_and_the_focus_ring_are_visible(self, macro):
        t = _tokens(macro)
        for surface in ("--bg", "--surface"):
            assert _ratio(t["--control-edge"], t[surface]) >= 3.0, (macro, surface)
            assert _ratio(t["--accent"], t[surface]) >= 3.0, (macro, surface)

    @pytest.mark.parametrize("macro", ["dark_tokens", "light_tokens"])
    def test_chore_pill_text_reads_on_the_card(self, macro):
        t = _tokens(macro)
        for name in ("--chore-1-fg", "--chore-2-fg", "--warn-fg"):
            assert _ratio(t[name], t["--surface"]) >= 4.5, (macro, name)
        assert _ratio(t["--warn-fg"], t["--warn-bg"]) >= 4.5


class TestFocusAndStates:
    def test_the_shared_sheet_keeps_a_keyboard_ring_and_hover_press_rules(self):
        base = (TEMPLATES / "settings" / "base.html").read_text()
        assert ":focus-visible { outline: 2px solid var(--accent)" in base
        assert "@media (hover: hover)" in base
        assert ".btn:not(:disabled):active" in base


class TestName:
    def test_every_surface_says_pompdash_and_none_says_the_old_name(self, tmp_path, monkeypatch):
        client = client_for(app_with(tmp_path, monkeypatch))
        pages = surfaces(client)
        pages["signin"] = client.get("/h/who").get_data(as_text=True)
        for name, page in pages.items():
            assert "DinkyDash" not in page, name
        assert "PompDash" in pages["settings"] and "PompDash" in pages["phone"]

    def test_the_manifests_are_named_pompdash(self, tmp_path, monkeypatch):
        client = client_for(app_with(tmp_path, monkeypatch))
        phone = client.get("/h/manifest.webmanifest").get_json(force=True)
        settings = client.get("/settings/manifest.webmanifest").get_json(force=True)
        assert phone["name"] == phone["short_name"] == "PompDash"
        assert settings["name"] == "PompDash settings"
        assert settings["short_name"] == "PompDash"

    def test_no_user_facing_template_or_doc_uses_the_old_name(self):
        scanned = [*TEMPLATES.rglob("*.html"), REPO / "README.md", REPO / "config.example.yaml",
                   REPO / "doc" / "self-hosting.md", REPO / "doc" / "running-it.md",
                   REPO / "doc" / "calendar-links.md", REPO / "web" / "static" / "favicon.svg"]
        assert [str(p) for p in scanned if "DinkyDash" in p.read_text()] == []

    def test_the_licence_and_its_attribution_are_untouched(self):
        licence = (REPO / "LICENSE").read_text()
        assert "MIT License" in licence
        assert "Copyright (c) 2021-2026 Caspar Wrede" in licence
        assert "[LICENSE](LICENSE)" in (REPO / "README.md").read_text()


class TestIcons:
    def test_the_mark_and_the_generator_use_the_same_palette(self):
        svg = (REPO / "web" / "static" / "favicon.svg").read_text().lower()
        generator = (REPO / "scripts" / "generate_icons.py").read_text().lower()
        for colour in re.findall(r"#[0-9a-f]{6}", svg):
            rgb = tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
            assert str(rgb)[:-1] in generator, colour

    def test_the_home_screen_pngs_exist_at_their_sizes(self):
        from PIL import Image
        static = REPO / "web" / "static"
        for name, size in [("apple-touch-icon.png", 180), ("icon-192.png", 192),
                           ("icon-512.png", 512), ("icon-maskable-512.png", 512)]:
            assert Image.open(static / name).size == (size, size), name
