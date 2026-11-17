"""The optional feedback form and its privacy controls."""

import logging

import pytest

from dinkydash import mail
from dinkydash.store import FileStore
from tests.conftest import client_for
from web import create_app, feedback

CONFIG = """\
family_name: "The Wilsons"
timezone: "Europe/Berlin"
people:
  - id: mia12345
    name: "Mia"
    date_of_birth: "2017-03-15"
calendars:
  - id: cal12345
    label: "School"
    url: "https://example.com/private-xxxx/basic.ics"
    enabled: true
"""

ADDRESS = "parent@example.com"
MESSAGE = "The countdown for half term is a day out."

# The dock itself, not its class: the stylesheet is shared, so every page
# carries the rule whether or not it carries the pill.
PILL = 'id="feedback-dock"'


class Outbox:
    """A stand-in for `mail.send` that remembers what it was asked to send."""

    def __init__(self, raises=None):
        self.sent = []
        self.raises = raises

    def __call__(self, to, subject, text, **kwargs):
        self.sent.append({"to": to, "subject": subject, "text": text, **kwargs})
        if self.raises:
            raise self.raises

    @property
    def only(self):
        assert len(self.sent) == 1, f"expected one email, got {len(self.sent)}"
        return self.sent[0]


@pytest.fixture
def outbox(monkeypatch):
    box = Outbox()
    monkeypatch.setattr(mail, "send", box)
    return box


@pytest.fixture(autouse=True)
def a_mail_key(monkeypatch):
    """The form is offered because there is somewhere to send it."""
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.test")


@pytest.fixture(autouse=True)
def no_redirected_mailbox(monkeypatch):
    """Where feedback goes is the default here, whatever the machine has set.

    A developer with a real `DINKYDASH_FEEDBACK_TO` in the environment would
    otherwise fail the tests that assert the default, and pass the one below
    for the wrong reason.
    """
    monkeypatch.delenv(feedback.FEEDBACK_TO, raising=False)


# -- what a message is made of ----------------------------------------------

class TestComposing:
    def test_the_message_comes_first(self):
        assert feedback.compose(MESSAGE).startswith(MESSAGE)



    def test_a_self_hosted_message_has_no_family_and_says_so(self):
        body = feedback.compose(MESSAGE)
        assert "Family:" not in body
        assert "self-hosted" in body

    def test_the_subject_names_the_sender_so_a_mailbox_can_thread(self):
        assert feedback.subject_for() == "PompDash feedback (self-hosted)"

    def test_line_endings_are_normalised_and_the_words_are_not_touched(self):
        assert feedback.clean("  one\r\ntwo  ") == "one\ntwo"

    def test_nothing_written_cleans_to_nothing(self):
        assert feedback.clean("   \r\n  ") == ""
        assert feedback.clean(None) == ""


class TestWhereItGoes:
    """The mailbox is movable; the address the app prints is not."""

    def test_by_default_it_is_the_address_we_give_out(self):
        assert feedback.recipient() == mail.support_address()

    def test_a_chosen_mailbox_wins(self, monkeypatch):
        monkeypatch.setenv(feedback.FEEDBACK_TO, "elsewhere@example.com")
        assert feedback.recipient() == "elsewhere@example.com"

    def test_a_blank_one_is_no_choice(self, monkeypatch):
        monkeypatch.setenv(feedback.FEEDBACK_TO, "   ")
        assert feedback.recipient() == mail.support_address()

    def test_moving_it_leaves_the_address_on_the_page_alone(self, monkeypatch):
        monkeypatch.setenv(feedback.FEEDBACK_TO, "elsewhere@example.com")
        assert feedback.support_address() == mail.support_address()
        assert feedback.support_address() != feedback.recipient()


class TestWhetherItExists:
    def test_it_is_off_without_a_way_to_send(self, monkeypatch):
        monkeypatch.delenv("SENDGRID_API_KEY")
        assert feedback.enabled() is False

    def test_a_blank_key_is_no_key(self, monkeypatch):
        monkeypatch.setenv("SENDGRID_API_KEY", "   ")
        assert feedback.enabled() is False

    def test_it_is_on_with_one(self):
        assert feedback.enabled() is True


# -- self-hosted ------------------------------------------------------------

@pytest.fixture
def single(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG)
    return client_for(create_app(FileStore(path)))


class TestSelfHosted:
    def test_the_page_is_there(self, single):
        assert single.get("/settings/feedback").status_code == 200

    def test_it_sends_with_no_account_behind_it(self, single, outbox):
        single.post("/settings/feedback", data={"message": MESSAGE})
        assert outbox.only["text"].startswith(MESSAGE)
        assert outbox.only["reply_to"] is None

    def test_with_no_mail_provider_there_is_no_page(self, single, monkeypatch):
        monkeypatch.delenv("SENDGRID_API_KEY")
        assert single.get("/settings/feedback").status_code == 404

    def test_and_no_pill(self, single, monkeypatch):
        monkeypatch.delenv("SENDGRID_API_KEY")
        assert PILL not in single.get("/settings/").get_data(as_text=True)


class TestSending:
    def test_it_goes_to_the_support_inbox(self, single, outbox):
        single.post("/settings/feedback", data={"message": MESSAGE})
        assert outbox.only["to"] == mail.support_address()

    def test_or_to_the_mailbox_that_was_chosen_instead(self, single, outbox, monkeypatch):
        monkeypatch.setenv(feedback.FEEDBACK_TO, "elsewhere@example.com")
        single.post("/settings/feedback", data={"message": MESSAGE})
        assert outbox.only["to"] == "elsewhere@example.com"
        # Still the family's own address to reply to, wherever it landed.
        assert outbox.only["reply_to"] is None



    def test_it_says_so_and_goes_back_to_the_settings(self, single, outbox):
        response = single.post("/settings/feedback", data={"message": MESSAGE},
                               follow_redirects=True)
        assert "gone to a person" in response.get_data(as_text=True)



class TestRefusing:
    def test_an_empty_message_sends_nothing_and_says_why(self, single, outbox):
        response = single.post("/settings/feedback", data={"message": "   "})
        assert outbox.sent == []
        assert "Write something first" in response.get_data(as_text=True)

    def test_too_long_sends_nothing_and_offers_the_address_instead(self, single, outbox):
        response = single.post("/settings/feedback",
                               data={"message": "x" * (feedback.LONGEST + 1)})
        assert outbox.sent == []
        assert mail.support_address() in response.get_data(as_text=True)

    def test_what_was_typed_is_handed_back_rather_than_lost(self, single, outbox):
        response = single.post("/settings/feedback",
                               data={"message": "x" * (feedback.LONGEST + 1)})
        assert "x" * 100 in response.get_data(as_text=True)

    def test_the_limit_stops_the_next_one(self, single, outbox):
        from web.routes.settings import MOST_FEEDBACK

        for _ in range(MOST_FEEDBACK):
            single.post("/settings/feedback", data={"message": MESSAGE})
        response = single.post("/settings/feedback", data={"message": MESSAGE})
        assert len(outbox.sent) == MOST_FEEDBACK
        assert "more than this form takes" in response.get_data(as_text=True)

    def test_a_send_that_fails_apologises_and_keeps_the_words(self, single, monkeypatch):
        monkeypatch.setattr(mail, "send", Outbox(raises=mail.MailError("nope")))
        response = single.post("/settings/feedback", data={"message": MESSAGE})
        page = response.get_data(as_text=True)
        assert "did not send" in page
        assert MESSAGE in page


class TestWhatIsNeverWritten:
    def test_a_sent_message_is_not_in_the_log(self, single, outbox, caplog):
        with caplog.at_level(logging.DEBUG):
            single.post("/settings/feedback", data={"message": MESSAGE})
        assert MESSAGE not in caplog.text
        assert ADDRESS not in caplog.text

    def test_nor_is_one_that_failed(self, single, monkeypatch, caplog):
        monkeypatch.setattr(mail, "send", Outbox(raises=mail.MailError("nope")))
        with caplog.at_level(logging.DEBUG):
            single.post("/settings/feedback", data={"message": MESSAGE})
        assert MESSAGE not in caplog.text


class TestWhereThePillIs:
    def test_on_a_settings_page(self, single):
        assert PILL in single.get("/settings/").get_data(as_text=True)

    def test_and_on_the_pages_below_it(self, single):
        assert PILL in single.get("/settings/system").get_data(as_text=True)

    def test_never_on_the_dashboard(self, single):
        page = single.get("/").get_data(as_text=True)
        assert PILL not in page


    def test_not_on_the_page_it_leads_to(self, single):
        assert PILL not in single.get("/settings/feedback").get_data(as_text=True)

    def test_the_settings_home_keeps_a_way_in_that_cannot_be_dismissed(self, single):
        assert "/settings/feedback" in single.get("/settings/").get_data(as_text=True)
