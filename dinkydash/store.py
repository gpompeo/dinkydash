"""The storage seam: where a family's config, dashboard and history are kept.

FileStore keeps config.yaml and two JSON files; PostgresStore keeps rows keyed
on a family. The config dict is the contract, and both expose seven operations:

    load_config()                save_config(config, invalidate_calendars=())
    load_payload(config)         save_agenda(config, agenda)
                                 save_brief(config, brief)
    recent_notes(config, days)   record_note(config, entry, keep)

The runner, the dashboard route and the settings routes take a store and never
learn which one they were given.

**The dashboard is read whole and written in halves**, and that is the shape rather
than an accident. A refresh owns the agenda; the daily brief owns the words.
They run on different clocks, and the brief's write is separated from its read
by a slow model call — so a single `save_payload` meant a refresh that landed
during that call was overwritten by stale keys, silently, while the button that
triggered it said it had worked (DIN-28). Two operations that each write only
what they own makes that impossible rather than merely unlikely; in Postgres
they are already two tables, so it is also the more honest mapping.

Settings saves clear affected calendars under the same lock as agenda writes.
`save_agenda` returns False if the saved calendar settings no longer match the
fetch; the runner then stops before generating a brief from obsolete results.

The payload and history calls are handed the config because `FileStore` needs
two keys out of it — `data_file` and `content_history_file` — to know where to
write. Those are storage-layer keys: they mean nothing in cloud mode, and this
is the only module that reads them.

This module and `config.py` are the only places under `dinkydash/` that touch
a file.
"""

import hashlib
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - Windows has no flock
    fcntl = None

from . import config as config_module
from . import history as history_module
from .calendars import feed_label

log = logging.getLogger(__name__)

# What a calendar refresh owns, and the only keys `save_agenda` will write.
# Everything else in the payload belongs to the brief. Named here rather than in
# the runner because it is the storage contract's own vocabulary: both
# implementations enforce it, and no caller can talk its way past it.
AGENDA_KEYS = ("events", "calendar_statuses", "calendars_fetched_at")

# Beside the config, never in it. Holds secrets, so it stays out of git.
AUTH_FILE = "auth.json"

# Completions older than this many days are dropped whenever one is written.
COMPLETIONS_FILE = "completions.json"
KEEP_COMPLETIONS_DAYS = 400

# Files beside the config whose change moves `change_token()`.
CHANGE_FILES = ("completions.json", "shopping.json")


class FileStore:
    """One family, as files beside its own `config.yaml`.

    A relative `data_file` or `content_history_file` resolves against the
    config's own directory, so `generate.py --config /tmp/scratch.yaml` keeps
    its generated files with it rather than in whatever directory it was run
    from.
    """

    def __init__(self, config_path=None):
        path = Path(config_path) if config_path else config_module.config_path()
        self.config_path = path.expanduser()
        self.base = self.config_path.parent

    # -- the config ---------------------------------------------------------

    def load_config(self):
        """The config as a plain dict, defaults filled in and old shapes migrated."""
        with _locked(self.base):
            return config_module.load_config(self.config_path)

    def save_config(self, config, *, invalidate_calendars=()):
        """Save settings and invalidate changed calendars under the same lock."""
        with _locked(self.base):
            try:
                previous = config_module.load_config(self.config_path)
            except FileNotFoundError:
                previous = {}
            agenda = invalidated_agenda(previous, config, self.load_payload(previous),
                                        invalidate_calendars)
            if agenda is not None:
                # Clear first: even a failed config write must not leave a new
                # privacy setting visible beside events fetched before it.
                self._replace(previous, _is_agenda_key, agenda)
            config_module.save_config(config, self.config_path)

    # -- the dashboard ----------------------------------------------------------

    def load_payload(self, config):
        """The last generated dashboard, or None when there is not a usable one."""
        payload = _read_json(self._data_path(config), "the stored dashboard")
        return payload if isinstance(payload, dict) else None

    def save_agenda(self, config, agenda):
        """Publish only if the saved calendar settings still match the fetch."""
        with _locked(self.base):
            current = config_module.load_config(self.config_path)
            if calendar_config(current) != calendar_config(config):
                return False
            self._replace(config, _is_agenda_key,
                          {k: agenda[k] for k in AGENDA_KEYS if k in agenda})
            return True

    def save_brief(self, config, brief):
        """Replace the model's words, leaving the fetched window alone.

        Agenda keys are dropped rather than trusted, so a caller handing over a
        whole payload cannot resurrect a stale agenda through this door.
        """
        with _locked(self.base):
            self._replace(config, lambda key: not _is_agenda_key(key),
                          {k: v for k, v in brief.items() if not _is_agenda_key(k)})

    def _replace(self, config, owns, updates):
        """Replace this half's fields. The caller holds the config-directory lock."""
        path = self._data_path(config)
        stored = _read_json(path, "the stored dashboard")
        if not isinstance(stored, dict):
            stored = {}
        payload = {k: v for k, v in stored.items() if not owns(k)}
        payload.update(updates)
        _write_json(path, payload)

    # -- noticing a change from another device -------------------------------

    def change_token(self):
        """A number that moves whenever the config, completions, shopping list or payload do.

        Built from each file's modification time and size, never its content, so
        the number can be served to a wall screen without carrying anything of
        the family's. A missing file counts as a value of its own, so creating
        or deleting one moves the number too. Only a change in the number means
        anything; it is not ordered.
        """
        paths = [self.config_path, self._data_path(self.load_config())]
        paths += [self.base / name for name in CHANGE_FILES]
        marks = []
        for path in paths:
            try:
                info = path.stat()
                marks.append(f"{info.st_mtime_ns}:{info.st_size}")
            except OSError:
                marks.append("-")
        digest = hashlib.sha256("|".join(marks).encode()).digest()
        return int.from_bytes(digest[:6], "big")

    # -- tasks ticked off ----------------------------------------------------

    def load_completions(self, since=None):
        """Completions as `{task_id, date, person_id, completed_at}`, from `since` on.

        `since` is a date; `date` in each entry is an ISO date string, which
        sorts as dates do. A missing or damaged file reads as no completions.
        """
        found = _read_json(self.base / COMPLETIONS_FILE, "the completions")
        found = [c for c in found if _is_completion(c)] if isinstance(found, list) else []
        if since is not None:
            found = [c for c in found if c["date"] >= since.isoformat()]
        return found

    def record_completion(self, entry, today):
        """Add one completion (once per task, date and person), then trim old ones."""
        self._change_completions(
            lambda found: found if _same_completion(entry, found) else found + [entry], today)

    def remove_completion(self, entry, today):
        self._change_completions(
            lambda found: [c for c in found if not _same_completion(entry, [c])], today)

    def drop_person_completions(self, person_id):
        """A person who is deleted takes their completions with them."""
        with _locked(self.base):
            found = self.load_completions()
            kept = [c for c in found if c["person_id"] != person_id]
            if len(kept) != len(found):
                _write_json(self.base / COMPLETIONS_FILE, kept)

    def _change_completions(self, change, today):
        """Read, change, trim to the last 400 days and replace, all under the lock."""
        with _locked(self.base):
            oldest = (today - timedelta(days=KEEP_COMPLETIONS_DAYS)).isoformat()
            kept = [c for c in change(self.load_completions()) if c["date"] >= oldest]
            _write_json(self.base / COMPLETIONS_FILE, kept)

    # -- who may sign in ---------------------------------------------------

    def load_auth(self):
        """Member PIN hashes and the like, from `auth.json` beside the config.

        Kept out of `config.yaml`, which is exported and edited by hand. The file
        is created owner-only (mode 0600) and is gitignored.
        """
        auth = _read_json(self.base / AUTH_FILE, "the sign-in file")
        return auth if isinstance(auth, dict) else {}

    def update_auth(self, change):
        """Apply `change(auth)` to a fresh read, under the lock, and save it.

        A function rather than a whole-dict save, so two features that each own
        a key in this file cannot overwrite one another.
        """
        with _locked(self.base):
            auth = self.load_auth()
            change(auth)
            _write_json(self.base / AUTH_FILE, auth)
            return auth

    # -- what was written recently ------------------------------------------

    def recent_notes(self, config, days):
        """The note text from the last `days` entries, oldest first."""
        return history_module.recent_notes(self._history(config), days)

    def record_note(self, config, entry, keep=30):
        """Add one entry to the history, keeping the most recent `keep`.

        Never raises. A history that cannot be written costs a repeated octopus
        fact in a fortnight; it is not worth losing a written dashboard over.
        """
        try:
            _write_json(self._history_path(config),
                        history_module.appended(self._history(config), entry, keep))
        except Exception as exc:
            log.warning("Could not write the note history: %s", exc)

    def _history(self, config):
        history = _read_json(self._history_path(config), "the note history")
        if history is None:
            return []
        if not isinstance(history, list):
            log.warning("The note history is not a list; ignoring it")
            return []
        return history

    # -- where the files are ------------------------------------------------

    def _data_path(self, config):
        return self._resolve(config.get("data_file") or config_module.DEFAULTS["data_file"])

    def _history_path(self, config):
        return self._resolve(config.get("content_history_file")
                             or config_module.DEFAULTS["content_history_file"])

    def _resolve(self, value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.base / path


def _is_completion(entry):
    return isinstance(entry, dict) and all(
        isinstance(entry.get(k), str) and entry[k]
        for k in ("task_id", "date", "person_id"))


def _same_completion(entry, found):
    return any((c["task_id"], c["date"], c["person_id"])
               == (entry["task_id"], entry["date"], entry["person_id"]) for c in found)


def _is_agenda_key(key):
    return key in AGENDA_KEYS


def calendar_config(config):
    """Fetch inputs, grouped by the label carried by stored events.

    Ignore item IDs so backfilling them does not invalidate a working agenda.
    Keep duplicate labels together: changing either source invalidates that label.
    """
    feeds = {}
    for entry in config.get("calendars") or []:
        if isinstance(entry, dict):
            feeds.setdefault(feed_label(entry), []).append(
                {key: value for key, value in entry.items() if key != "id"})
    return (config.get("timezone") or config_module.DEFAULTS["timezone"],
            int(config.get("calendar_days_ahead") or 14), feeds)


def invalidated_agenda(previous, current, payload, labels=()):
    """Drop affected events and the fetch stamp, or return None for no change."""
    before, after = calendar_config(previous), calendar_config(current)
    if payload is None or (before == after and not labels):
        return None
    changed = set(labels) | {label for label in before[2].keys() | after[2].keys()
                            if before[2].get(label) != after[2].get(label)}
    return {key: [entry for entry in payload.get(key) or []
                  if before[:2] == after[:2] and entry.get(label_key) not in changed]
            for key, label_key in (("events", "calendar"), ("calendar_statuses", "label"))}


@contextmanager
def _locked(directory):
    """An exclusive lock on the directory, for one read and one write.

    **The directory rather than a lock file beside the data**, and that is the
    point: a sidecar would have to be protected from anything that syncs or
    prunes that directory, and if it ever were not, a copy landing mid-write
    would unlink the inode a running tick still holds. The next writer would then
    create a fresh file, take a lock on a different inode, and serialise against
    nobody — silently. A directory's inode survives all of that, and there is no
    file to remember to exclude.

    Lock the config directory for settings and payload writes, including when
    `data_file` points elsewhere. No network call runs under this lock. Cloud
    mode coordinates config and agenda writes with a family-row lock instead.
    """
    if fcntl is None:  # Windows; the dashboard runs on Linux and macOS
        yield
        return
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        # No directory to lock means the write is about to fail anyway, and it
        # will say why far more clearly than a lock error would.
        yield
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _read_json(path, what):
    """Parsed JSON, or None when there is nothing usable there.

    Never raises. A missing file means this family has not got one yet, and an
    unreadable one must not take the dashboard down with it — the caller carries on
    as though it were absent, and the next write replaces it.
    """
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("Could not read %s (%s); carrying on as if it were not there", what, exc)
        return None


def _write_json(path, data):
    """Write via a temporary file and rename, so a reader sees old or new, never half."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(path))
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
