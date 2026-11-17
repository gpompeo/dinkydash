"""Calendar checks use the family's day even across midnight on the server."""

from datetime import datetime

import pytest

from dinkydash import config as config_module
from dinkydash.store import FileStore
from tests.conftest import client_for
from tests.test_calendars import all_day, ical
from web import create_app


@pytest.mark.parametrize("timezone,instant,expected", [
    ("Europe/Berlin", "2026-09-02T23:30:00+00:00", "2026-09-03"),
    ("America/Los_Angeles", "2026-09-03T01:30:00+00:00", "2026-09-02"),
])
def test_check_uses_the_family_date(timezone, instant, expected, monkeypatch, tmp_path):
    now = datetime.fromisoformat(instant)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)

    monkeypatch.setattr(config_module, "datetime", Clock)
    config = config_module.with_defaults({"timezone": timezone})
    store = FileStore(tmp_path / "config.yaml")
    store.save_config(config)
    app = create_app(store)

    # Exercise the real describe/parse path; only the network and clock are fake.
    feed = ical(*(all_day(day, day.replace("-", ""), f"Plans for {day}")
                  for day in ["2026-09-02", "2026-09-03", "2026-09-04"]))
    monkeypatch.setattr("dinkydash.calendars.fetch_text", lambda *a, **kw: feed)
    client = client_for(app)
    response = client.post("/settings/calendars/new", data={
        "action": "check", "label": "Family", "url": "https://calendar.example/test.ics",
    })
    assert response.status_code == 200
    assert f"Next up: Plans for {expected}, {expected}" in response.get_data(as_text=True)
