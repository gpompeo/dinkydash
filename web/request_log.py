"""Keep credential-bearing screen URLs out of access logs."""

import logging
import re

SCREEN_PREFIX = r"((?:/|%2f)(?:s|%73|%53)(?:/|%2f))"
A_SCREEN = re.compile(SCREEN_PREFIX + r"\S*", re.IGNORECASE)
A_SCREEN_TARGET = re.compile(SCREEN_PREFIX + r".*", re.IGNORECASE | re.DOTALL)
REDACTED = r"\1[redacted]"


class NoTokens(logging.Filter):
    def filter(self, record):
        if record.name == "gunicorn.access" and isinstance(record.args, dict):
            path = record.args.get("U")
            if isinstance(path, str):
                record.args["U"] = A_SCREEN_TARGET.sub(REDACTED, path)
        elif (record.name == "werkzeug" and isinstance(record.args, tuple)
              and record.args and isinstance(record.args[0], str)):
            target, separator, protocol = record.args[0].rpartition(" HTTP/")
            if not separator:
                target, protocol = record.args[0], ""
            record.args = (A_SCREEN_TARGET.sub(REDACTED, target) + separator + protocol,
                           *record.args[1:])
        message = record.getMessage()
        redacted = A_SCREEN.sub(REDACTED, message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def quieten_the_request_log():
    for name in ("werkzeug", "gunicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, NoTokens) for f in logger.filters):
            logger.addFilter(NoTokens())
