"""The legacy `recurring` chore list is refused, never converted, dropped or written over."""

from datetime import date

import pytest

from dinkydash import config as config_module
from dinkydash.context import tasks_for
from dinkydash.store import FileStore

LEGACY = """\
family_name: "The Wilsons"
people:
  - name: "Mia"
recurring:
  - title: "Set the table"
    choices: ["Mia"]
"""

CURRENT = """\
# Our family
family_name: "The Wilsons"
people:
  - id: "p1"
    name: "Mia"
  - id: "p2"
    name: "Theo"
tasks:
  - id: "t1"
    title: "Set the table"
    recurrence:
      kind: daily
    assignment:
      mode: rotate
      people: ["p2", "p1"]
      offset: 1
"""


def test_a_legacy_config_is_refused_with_a_way_forward(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(LEGACY)
    with pytest.raises(config_module.ConfigError) as caught:
        config_module.load_config(path)
    message = str(caught.value)
    assert "recurring" in message and "tasks" in message and "doc/upgrading.md" in message


def test_refusing_a_legacy_config_leaves_the_file_untouched(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(LEGACY)
    with pytest.raises(config_module.ConfigError):
        FileStore(path).load_config()
    assert path.read_text() == LEGACY
    assert list(tmp_path.iterdir()) == [path]


def test_an_empty_legacy_key_is_refused_too():
    with pytest.raises(config_module.ConfigError):
        config_module.with_defaults({"recurring": [], "tasks": [{"id": "x", "title": "Bins"}]})


def test_the_legacy_chores_are_never_read_as_an_empty_task_list():
    raw = {"recurring": [{"title": "Old", "choices": ["Mia"]}]}
    with pytest.raises(config_module.ConfigError):
        config_module.with_defaults(raw)
    assert raw["recurring"][0]["title"] == "Old"


def test_saving_over_a_legacy_file_is_refused_and_keeps_it(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(LEGACY)
    with pytest.raises(config_module.ConfigError):
        FileStore(path).save_config({"family_name": "Other"})
    assert path.read_text() == LEGACY


def test_a_current_config_round_trips_unchanged(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CURRENT)
    store = FileStore(path)
    config = store.load_config()
    assert "_migrated" not in config
    before = tasks_for(config, date(2026, 5, 1))
    store.save_config(config)
    assert path.read_text().count("recurring") == 0
    again = store.load_config()
    assert again["tasks"][0]["assignment"] == {"mode": "rotate", "people": ["p2", "p1"], "offset": 1}
    assert [p["id"] for p in again["people"]] == ["p1", "p2"]
    assert tasks_for(again, date(2026, 5, 1)) == before


def test_loading_a_current_config_reports_nothing_for_the_settings_ui_to_save(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CURRENT)
    assert config_module.ensure_ids(config_module.load_config(path)) is False


def test_unrelated_migrations_still_run():
    config = config_module.with_defaults({"calendar_url": "https://example.com/a.ics"})
    assert config["calendars"][0]["url"] == "https://example.com/a.ics"


def test_a_hand_edited_file_over_the_caps_still_shows_only_the_caps():
    tasks = [{"id": f"t{n}", "title": "y" * 200, "recurrence": {"kind": "daily"},
              "assignment": {"mode": "anyone"}} for n in range(60)]
    due = tasks_for({"tasks": tasks}, date(2026, 5, 1))
    assert len(due) == config_module.MAX_TASKS
    assert all(len(t["title"]) == config_module.MAX_TITLE_LENGTH for t in due)


def test_the_generator_stops_on_a_legacy_config_and_leaves_it_alone(tmp_path, caplog):
    import generate

    path = tmp_path / "config.yaml"
    path.write_text(LEGACY)
    assert generate.main(["--tick", "--config", str(path)]) == 1
    assert "doc/upgrading.md" in caplog.text
    assert path.read_text() == LEGACY


def test_the_web_app_says_what_to_fix_and_leaves_the_file_alone(tmp_path):
    from tests.conftest import client_for
    from web import create_app

    path = tmp_path / "config.yaml"
    path.write_text(LEGACY)
    response = client_for(create_app(FileStore(path))).get("/")
    assert response.status_code == 500
    assert "doc/upgrading.md" in response.get_data(as_text=True)
    assert path.read_text() == LEGACY


def test_the_upgrade_guide_names_the_unsupported_shape_and_the_way_forward():
    from pathlib import Path

    guide = (Path(__file__).parent.parent / "doc" / "upgrading.md").read_text()
    assert "`recurring` is refused" in guide and "`tasks:`" in guide
