"""Send optional feedback without storing or logging its contents."""

import os

# The settings `dinkydash.mail` sends with, named here rather than imported so
# that asking whether the form can work costs nothing and imports nothing.
MAIL_KEY = "SENDGRID_API_KEY"
MAIL_FROM = "DINKYDASH_MAIL_FROM"
MAIL_REPLY_TO = "DINKYDASH_MAIL_REPLY_TO"

# Where the form sends. There is no default: the install chooses its own.
FEEDBACK_TO = "DINKYDASH_FEEDBACK_TO"

# What one message may carry. Generous, because somebody describing a bug may
# paste the thing that went wrong, and short enough that the form is not a way
# to post arbitrary volume through our sending account. Anything longer is
# refused rather than truncated: silently dropping the end of what a person
# wrote is worse than telling them it did not fit.
LONGEST = 4000

SUBJECT = "PompDash feedback"


def enabled():
    """Is feedback fully configured? Read at render time, never cached.

    It needs a key, a sender, a reply-to and a recipient; with any missing the
    form is not offered.
    """
    return all(os.environ.get(name, "").strip()
               for name in (MAIL_KEY, MAIL_FROM, MAIL_REPLY_TO, FEEDBACK_TO))


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
    """The configured mailbox, read at send time. Empty when unset."""
    return os.environ.get(FEEDBACK_TO, "").strip()


def submit(message):
    """Send feedback; raise `mail.MailError` if delivery fails."""
    from dinkydash import mail

    mail.send(recipient(), subject_for(), compose(message), reply_to=None)

