"""Thread-safe, bounded per-caller rate limits for local requests."""

import ipaddress
import threading
import time
from collections import OrderedDict, deque

# How many distinct keys are tracked before the oldest are forgotten. A flood
# wide enough to need more than this is a botnet rather than a nuisance, and
# forgetting is the right failure: a rate limiter that starts refusing everyone
# has turned an abusive account into an outage for every family.
MOST_KEYS = 10_000


class Limiter:
    """At most `most` events per `per` seconds, for each key.

    Thread-safe, because the service runs `--threads 4` and two requests from
    one address really do arrive at once.
    """

    def __init__(self, most, per, most_keys=MOST_KEYS):
        self.most = most
        self.per = per
        self.most_keys = most_keys
        self._seen = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key, now=None):
        """Record one event and say whether it was within the limit."""
        if not key:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._seen.get(key)
            if hits is None:
                hits = self._seen[key] = deque()
            self._seen.move_to_end(key)

            cutoff = now - self.per
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.most:
                return False
            hits.append(now)
            self._forget_the_oldest()
            return True

    def _forget_the_oldest(self):
        """Keep the map bounded. Called with the lock held."""
        while len(self._seen) > self.most_keys:
            self._seen.popitem(last=False)


# Recognise connecting-IP headers supplied by a trusted proxy when present.
CALLER_HEADERS = ("DO-Connecting-IP", "CF-Connecting-IP")


def client_ip(request):
    """Return a known caller address, or an empty key when unavailable."""
    for header in CALLER_HEADERS:
        value = request.headers.get(header, "").strip()
        if value:
            return value

    remote = (request.remote_addr or "").strip()
    return remote if _is_public(remote) else ""


def _is_public(address):
    """Could this be a real client on the internet?

    Note for anyone writing a test against this: `is_private` is true for the
    documentation ranges too — `192.0.2.0/24`, `198.51.100.0/24` and
    `203.0.113.0/24`, the ones examples are supposed to use. A test written
    with those goes down the fallback branch above and proves nothing.
    """
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (parsed.is_private or parsed.is_loopback or parsed.is_reserved
                or parsed.is_link_local or parsed.is_unspecified)
