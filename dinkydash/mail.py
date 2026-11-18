"""Send optional feedback through SendGrid without logging message contents."""

import logging
import os

import requests

logger = logging.getLogger(__name__)

SEND_URL = "https://api.sendgrid.com/v3/mail/send"
DEFAULT_TIMEOUT = 10

# The display name on a message. The sender and reply-to addresses have no
# default: they come from `DINKYDASH_MAIL_FROM` and `DINKYDASH_MAIL_REPLY_TO`,
# and a send without them is refused rather than guessed.
DEFAULT_FROM_NAME = "PompDash"


class MailError(Exception):
    """A message did not go out."""


class MailRefused(MailError):
    """The message was never attempted, because it could not be.

    A missing key or an address that is not an address is a configuration fault
    and will fail identically on every retry. `FeedRefused` subclasses
    `FeedError` for the same reason: a caller that only wants to know "did it
    go" catches the parent, and one that wants to know "is it worth trying
    again" checks the subclass.
    """


def send(to, subject, text, html=None, transport=None, api_key=None,
         sender=None, sender_name=None, reply_to=None, timeout=DEFAULT_TIMEOUT):
    """Send one message. Returns None, raises `MailError` if it did not go.

    `transport` is the seam the tests use. It takes the same arguments
    `requests.post` does and must behave the same way, which is why the default
    is literally `requests.post` rather than a wrapper around it.

    `reply_to` overrides where a reply lands; without it the configured
    `DINKYDASH_MAIL_REPLY_TO` is used. It goes through `_clean_address` like
    the recipient does — a value that reaches a header is a header injection
    wherever it came from. A missing sender or reply-to is a refusal.
    """
    recipient = _clean_address(to)
    key = _clean_key(api_key if api_key is not None else os.environ.get("SENDGRID_API_KEY"))
    from_address = _clean_address(sender or os.environ.get("DINKYDASH_MAIL_FROM"),
                                  "DINKYDASH_MAIL_FROM is not set")
    reply = _reply(reply_to)
    post = transport or requests.post

    body = {
        "personalizations": [{"to": [{"email": recipient}]}],
        "from": {"email": from_address, "name": sender_name or DEFAULT_FROM_NAME},
        "reply_to": reply,
        "subject": subject,
        "content": _content(text, html),
    }

    try:
        response = post(
            SEND_URL,
            json=body,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.exceptions.InvalidHeader:
        # `from None`, and it is the whole point of this branch. `requests`
        # puts the offending header *value* in this exception's message —
        # "...in header value: 'Bearer SG.REALKEY\n'" — and the only variable
        # header here is the Authorization one. Chaining it would print the key
        # in every traceback that reaches a log, past the sanitised
        # message. `_clean_key` should mean this never fires; this is the belt
        # to its braces, and it stays even if a future header makes it possible
        # again.
        raise MailError(
            "could not send the email: the request headers were rejected"
        ) from None
    except requests.RequestException as exc:
        raise MailError(f"could not send the email: {_why(exc)}") from exc

    status = getattr(response, "status_code", None)
    if status is None or not 200 <= status < 300:
        raise MailError(f"could not send the email: the server said {status}")

    # The address is personal data and the subject can name a person, so this
    # says that a send happened and nothing about who or what. `calendars`
    # logs the label rather than the URL for the same reason.
    logger.info("Sent one email via SendGrid.")


def _content(text, html):
    """SendGrid wants plain text first when both are present, and wants one of them.

    The order is not cosmetic: it decides which part a client shows when it can
    render both, and getting it backwards means the plain-text fallback wins in
    clients that should show the HTML.
    """
    if not (text or "").strip():
        raise MailRefused("an email needs a plain-text body")
    content = [{"type": "text/plain", "value": text}]
    if html:
        content.append({"type": "text/html", "value": html})
    return content


def _clean_address(to, missing="no email address to send to"):
    """The recipient, or a refusal. No validation beyond what protects the account.

    A malformed address is worth catching here rather than discovering as a
    hard bounce against the sender's reputation. This is not an attempt to validate
    email addresses properly, which is not possible — it rejects what is
    obviously not one, and lets SendGrid judge the rest.

    A newline is the one that matters. Anything reaching a header is a header
    injection, and although this sends JSON rather than SMTP, the rule holds
    wherever the value ends up next.
    """
    address = (to or "").strip()
    if not address:
        raise MailRefused(missing)
    if any(c in address for c in "\r\n"):
        raise MailRefused("that email address contains a line break")
    if address.count("@") != 1 or address.startswith("@") or address.endswith("@"):
        raise MailRefused("that does not look like an email address")
    return address


def _clean_key(key):
    """The send-only key, checked before it can reach an HTTP header.

    The key should be scoped to `mail.send` alone. It comes from the
    environment: never a literal, never per-family.

    **This exists to keep the key out of tracebacks.** `requests` validates
    header values and quotes the bad one in `InvalidHeader`, so a key carrying
    a stray newline — the usual shape of a copy-paste or an env var set from a
    file — would put itself in an exception message. Catching it here means the
    request is never built, and none of these messages names the value.

    A trailing newline is repaired rather than refused, because it is almost
    always the transport's fault rather than the operator's. Anything else
    unusual is refused: a key with a space in the middle is a wrong key, and
    guessing at what was meant would send mail on a credential nobody chose.
    """
    if key is None or not key.strip():
        raise MailRefused("SENDGRID_API_KEY is not set")
    cleaned = key.strip()
    if not cleaned.isascii() or any(c.isspace() for c in cleaned):
        raise MailRefused(
            "SENDGRID_API_KEY contains whitespace or non-ASCII characters"
        )
    return cleaned


def _reply(reply_to):
    """The `reply_to` block, from the caller or from `DINKYDASH_MAIL_REPLY_TO`.

    The name is a label the sender chose for themselves, so only the configured
    address carries it: "PompDash" on somebody else's mailbox would be a mail
    client showing our name against theirs.
    """
    if reply_to:
        return {"email": _clean_address(reply_to)}
    configured = os.environ.get("DINKYDASH_MAIL_REPLY_TO")
    return {"email": _clean_address(configured, "DINKYDASH_MAIL_REPLY_TO is not set"),
            "name": DEFAULT_FROM_NAME}


def _why(exc):
    """Why a send failed, in words that carry no secret.

    `requests` puts the full URL in the message of a connection error, and the
    `Authorization` header can surface in a repr. Neither is something to write
    to a log that a support person reads. The endpoint is not secret, but the
    habit is what keeps `calendars._why` honest.
    """
    if isinstance(exc, requests.Timeout):
        return "the server did not answer in time"
    if isinstance(exc, requests.ConnectionError):
        return "could not reach the server"
    return type(exc).__name__
