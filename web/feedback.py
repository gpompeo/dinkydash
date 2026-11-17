"""Send optional feedback without storing or logging its contents."""

import os

# The key `dinkydash.mail` sends with, named here rather than imported so that
# asking whether the form can work costs nothing and imports nothing. That is
# with no key the pill is not drawn and the route is a 404.
MAIL_KEY = "SENDGRID_API_KEY"

# Where the form sends, when it should not be the address the app publishes.
# Named here for the same reason `MAIL_KEY` is: reading it costs no import.
FEEDBACK_TO = "DINKYDASH_FEEDBACK_TO"

# What one message may carry. Generous, because somebody describing a bug may
# paste the thing that went wrong, and short enough that the form is not a way
# to post arbitrary volume through our sending account. Anything longer is
# refused rather than truncated: silently dropping the end of what a person
# wrote is worse than telling them it did not fit.
LONGEST = 4000

SUBJECT = "DinkyDash feedback"


def enabled():
    """Is there anywhere to send feedback? Read at render time, never cached."""
    return bool(os.environ.get(MAIL_KEY, "").strip())


def clean(message):
    """The message as it will be sent: trimmed, and with no stray carriage returns.

    Line endings are normalised because a browser posts `\\r\\n` and the body is
    read in a mail client, not a terminal. Nothing else is stripped — this is
    somebody's own sentence and it is not ours to edit.
    """
    text = (message or "").replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def compose(message):
    """Put the message first and identify its self-hosted origin."""
    return f"{message}\n\n--\nFrom: a self-hosted dashboard\n"


def subject_for():
    return f"{SUBJECT} (self-hosted)"


def recipient():
    """Read the chosen mailbox at send time, defaulting to support."""
    chosen = os.environ.get(FEEDBACK_TO, "").strip()
    return chosen or support_address()


def submit(message):
    """Send feedback; raise `mail.MailError` if delivery fails."""
    from dinkydash import mail

    mail.send(recipient(), subject_for(), compose(message), reply_to=None)


def support_address():
    """The address the app gives out: the fallback for a send that did not go.

    Where feedback lands as well, unless `recipient()` has been pointed
    elsewhere.
    """
    from dinkydash import mail

    return mail.support_address()
