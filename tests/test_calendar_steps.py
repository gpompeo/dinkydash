"""The calendar help is available on a phone."""

import pytest

from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app

CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - id: mia12345
    name: "Mia"
    date_of_birth: "2017-03-15"
"""

NOTE = "Google only shows this link on a computer."
BUTTON = "Email me the steps"


# -- self-hosted ------------------------------------------------------------

@pytest.fixture
def single(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return client_for(create_app(FileStore(path)))


class TestSelfHosted:
    def test_the_note_is_on_the_form(self, single):
        page = single.get("/settings/calendars/new").get_data(as_text=True)
        assert NOTE in page
        # Before the steps that are folded away, not inside them.
        assert page.index(NOTE) < page.index("Where do I find my calendar link?")

    def test_but_there_is_no_account_to_email(self, single):
        page = single.get("/settings/calendars/new").get_data(as_text=True)
        assert BUTTON not in page
        assert single.post("/settings/calendar-steps").status_code in (404, 405)
