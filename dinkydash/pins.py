"""Member PINs: hashed with the standard library's scrypt, compared in constant time.

Pure functions. Where a hash is kept is the storage layer's business, and the
PIN itself is never stored, returned or logged.

A PIN is four to eight digits. It is a speed bump between family members on a
shared home network, not a bank card, which is why it is short and why the
caller is expected to rate limit attempts.
"""

import base64
import hashlib
import hmac
import re
import secrets

MIN_DIGITS = 4
MAX_DIGITS = 8

# scrypt's cost parameters. 16 MiB of memory per hash: slow enough to make
# guessing a stolen file expensive, light enough for a Raspberry Pi.
_N, _R, _P = 2 ** 14, 8, 1
_SCHEME = "scrypt"

_PIN = re.compile(rf"[0-9]{{{MIN_DIGITS},{MAX_DIGITS}}}")


def valid_pin(pin):
    """Four to eight ASCII digits, and nothing else."""
    return isinstance(pin, str) and _PIN.fullmatch(pin) is not None


def hash_pin(pin):
    """A self-describing hash of this PIN with a fresh random salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "$".join((_SCHEME, str(_N), str(_R), str(_P), _b64(salt), _b64(digest)))


def check_pin(pin, stored):
    """Does this PIN match the stored hash? A malformed hash matches nothing."""
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != _SCHEME:
            return False
        digest = hashlib.scrypt(pin.encode("utf-8"), salt=_unb64(salt), n=int(n),
                                r=int(r), p=int(p), dklen=len(_unb64(expected)))
        return hmac.compare_digest(digest, _unb64(expected))
    except (AttributeError, ValueError, TypeError):
        return False


def _b64(raw):
    return base64.b64encode(raw).decode("ascii")


def _unb64(text):
    return base64.b64decode(text.encode("ascii"), validate=True)
