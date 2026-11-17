# The engine, the storage seam, and the clock

Guidance for `dinkydash/`. The root `CLAUDE.md` holds the rules that apply
to every change; this file holds the ones that only bite here.

`streaks.py` (`person_streak`, `best_person_streak`, `task_streak`) works out streaks from config and completions on every call; nothing stores them, and the prompt never sees them. `board.build_view(..., completions=)` adds done state, streaks and the yesterday group, and `None` leaves the plain list.

## The storage seam

Seven operations, on one object, and nothing above them knows what is behind it:

```python
load_config()                save_config(config, invalidate_calendars=())
load_payload(config)         save_agenda(config, agenda)
                             save_brief(config, brief)
recent_notes(config, days)   record_note(config, entry, keep)
```

`FileStore` also has `load_completions(since)`, `record_completion(entry, today)`, `remove_completion(entry, today)` and `drop_person_completions(person_id)` for `completions.json` (entries `{task_id, date, person_id, completed_at}`, keyed on person ids, trimmed to 400 days on every write, replaced atomically; the date rules live in `checkin.py`), and `change_token()` (a number from the modification time and size of the config, payload, `completions.json` and `shopping.json`; never their content, so `/changes` can serve it) and `load_auth()` and `update_auth(change)` for `auth.json` (member PIN hashes and the screen token under `screen_token`).

`FileStore(config_path)` stores the config and household data in files. The runner receives a
store; web routes use `web.family.current_store()`. Construct the store at the entry points and
pass it below them so tests and separate checkouts can use independent paths.

- `store.py` and `config.py` are the only files under `dinkydash/` that open a file.
- `data_file` and `content_history_file` are storage-layer keys retained for compatibility.
- The dashboard is read whole and written in halves. `save_agenda` accepts only `AGENDA_KEYS`;
  `save_brief` accepts the other keys. Each half is replaced rather than merged.
- `FileStore` takes a short `flock` on the config directory for settings and payload writes.
  Calendar settings are compared under that lock before publishing a fetch; settings saves clear
  changed calendars and the fetch stamp, so an old fetch cannot restore an invalidated agenda.

## Household modules in the engine

Pure modules, all taking dates and data and never reading the clock or a file: `recurrence.py`
(`occurs_on`, `occurrence_index`; malformed rules never occur), `streaks.py` (worked out from
completions each time, never stored), `activity.py` (the thirty-day grid), `checkin.py` (who may tick
which day), `pins.py` (scrypt hashes), `taskform.py` (task form state and plain-English description).
A task is never due before `recurrence.effective_start` (its `start`, else `created`; neither means no limit); the boundary lives in `occurs_on` so every surface agrees, and it never moves the occurrence anchor. `context.tasks_for(config, day)` resolves assignment, and rotation counts `occurrence_index` plus
`assignment.offset`. `FileStore` owns `completions.json` (trimmed to 400 days on write),
`shopping.json`, `auth.json` and `change_token()`. Shopping text never goes into a prompt.

## What the payload holds, and what it does not

The payload stores only what cannot be recomputed: the model's `headline`, plus the
fetched calendar window (from the first day of the family's week, `week.first_day`, to 14 days ahead,
not just today; `week_start` is part of what invalidates a stored agenda). The headline prompt still
gets only today's events and the next few days' titles, so earlier days of the week never reach the model. `note` and `note_kind` are still on the
brief, empty when a new one is written, so an older file and an export keep their shape.
The dashboard does not render a note. Chores, countdowns and ages are pure functions of
config + date, so `board.build_view` recomputes them on every render.

That split is deliberate and load-bearing: when a morning's generation fails, the times, turns and
countdowns on the wall are still **today's**. Yesterday's fetch reached 14 days ahead, so today's
agenda is still in it. The stale headline is replaced by a computed one (`"3 things on today,
starting at 08:20."`) because a day-old AI headline can be actively wrong, and the banner says
so once the brief was due.

**Stale and late are two different questions, and only one of them may raise the banner.** A
dashboard is stale from local midnight, which is when the words stop being today's; the brief is
not *owed* until `brief_time`, so `build_view` also takes `now` and asks `schedule.brief_due`
whether anything is actually missing. Between the two the wall shows the computed headline
and says nothing else — an amber "today's headline hasn't arrived" before it was due
reports a fault that has not happened, in a kitchen, all night. More than a day behind is late at
any hour, and a caller with no clock to pass gets the plain answer.

That same 14-day window is where **tomorrow's** agenda comes from, so it survives a failed run too.

The payload carries two stamps, **both in UTC**: `generated_at` (when the brief was written) and
`calendars_fetched_at` (when the feeds were last fetched, and what `schedule.due` reads). UTC
because the server is routinely not on the family's clock — a Pi is often left on UTC rather than the family's timezone. They are rendered in the family's timezone at the point of display,
which on the settings home is `_clock(stamp, tzinfo)`. Slicing the characters out of the ISO
string would show the server's hour.

## Two cadences, one tick

The fetch and the model call ran together only because history put them there, and it meant an
appointment added at 09:00 was not on the wall until the next morning. They now run on their own
clocks, chosen by the family:

```
[cron */5m] -> generate.py --tick -> schedule.due(config, payload, now)
                                       refresh? -> runner.refresh_calendars()
                                                     fetch every enabled feed, merge, sort
                                                     write events + calendars_fetched_at
                                       brief?   -> runner.write_brief()
                                                     build the prompt, call Claude
                                                     write headline + note, append to history
                                       neither  -> exit 0, silently

[browser]   -> app.py             -> board.build_view(config, payload, today)
                                       renders web/templates/board.html
```

`refresh_minutes` (default 60) and `brief_time` (default `"06:00"`, on the family's clock) are
ordinary config keys, so they migrate through `with_defaults`.
`runner.run` is still both halves in order, which is what a plain `python generate.py` and the
settings page's **Rewrite daily headline** do — the old `0 6 * * *` line keeps working, it just never sees a
same-day change. **Refresh calendars**, beside it, is `refresh_calendars` alone: no key needed, no
money spent, and the thing most people pressing the other button actually wanted.

Both keys are edited at `/settings/refresh` rather than in YAML. The select offers five intervals
and nothing else, but it also offers **whatever the file already says** — a hand-edited
`refresh_minutes: 45` has to survive somebody opening the page and pressing Save, or the UI quietly
overrules the file. `brief_time` is written back through `config.quoted()`: bare `06:00` is a string
to ruamel and a sexagesimal integer to a YAML 1.1 parser, and this file is meant to be hand-editable
with either.

**The dashboard's own reload is derived, not stored** (`board.reload_seconds`). Five minutes is the
ceiling; only a `refresh_minutes` shorter than that lowers it, because reloading faster than the
calendars are fetched just redraws the same thing. A parent picks "how soon does a change show up",
not a browser knob — so there is no separate setting for it and the template reads
`view.reload_seconds` rather than deciding. The page acts on it by fetching a fresh copy and
swapping it in, not by reloading, so a copy that never arrives leaves the last dashboard on the
wall; `view.today` and `view.timezone` are there for the same script to say which day that
dashboard was for (`web/CLAUDE.md`, "The dashboard's layout").

These rules hold this together:

- **`due()` is pure and takes `now` as an aware datetime.** No clock, no I/O. That is what lets the
  same function drive a Pi's cron tick. A brief is
  due when `generated_for_date` is not today *in the family's timezone* and the local clock has
  passed `brief_time`; a refresh is due when `calendars_fetched_at` is missing or older than
  `refresh_minutes`.
- **The first brief is due immediately** when `generated_for_date` is absent — **for a set-up
  family** (`config.is_set_up`: no person or pet still marked `invented`, and a timezone other
  than the UTC default). The starter household and the untouched example file are not one, and a
  brief about them would be a paid call for invented children; the tick writes nothing until the
  answers are real. The dashboard is shown regardless, under a headline worked out from the day
  (`board.build_view`, state `first`). Calendar-only payloads still qualify once set up.
- **A refresh must not touch `headline`, `note` or `generated_for_date`**, and it now cannot: it
  writes through `store.save_agenda`, which only accepts `store.AGENDA_KEYS`. A fresh agenda under
  yesterday's brief is exactly the amber-banner state `board.build_view` already handles, and the
  whole point of the split.
- **A failure is not handled, it is simply due again.** Nothing is written, so the next tick asks
  the same question and gets the same answer. That is the retry, and it is why there is no backoff
  or attempt counter anywhere.

Two consequences worth knowing.

**A feed that does not answer keeps its own last-known events**, because a missing event is
invisible while a stale one is still on the right day. The keeping is per feed, not per fetch: the
feeds that answered are always fresh, or one dead URL would freeze the whole dashboard for as long as
nobody fixed it. `runner._with_last_known` does the merge, keyed on the `calendar` label each event
carries, and only inside the current window — so a permanently broken feed empties out over a
fortnight instead of growing a tail of appointments that already happened. A *paused* feed keeps
nothing: switching a calendar off means switching it off. The failure is recorded in
`calendar_statuses` and shown on the settings page, and the stamp is written either way, so a broken
feed is retried on the configured cadence rather than every tick.

**A feed is trimmed to the window before it is parsed.** `calendars._trim` drops, as text, every
VEVENT that cannot fall inside `[start, end]`, and keeps whatever the parser needs to decide that for
itself: recurring events and their exceptions, extra dates, VTIMEZONE blocks, and any event whose
dates it cannot read. The reason is memory, not speed: `icalendar` builds an object for every
property of every event, a decade-long personal calendar is 8 MB and 14,000 of them, and parsing one
cost ~200 MB with ~250 MB kept by the process afterwards — more than two gunicorn workers can hold in
a 512 MB container. The rule is that over-keeping is always safe and
under-keeping is a hidden appointment, so every doubt resolves to keep, and `tests/test_feed_trim.py`
asserts that the trimmed parse gives exactly what the untrimmed one gave.

**A tick takes an exclusive `flock` on `.tick.lock` and skips itself if another holds it**
(`generate.only_one_tick`). Its job is money, not consistency — the storage split is what stops two
writers clobbering each other, and this stops a second tick paying Anthropic for a brief the first
one is already writing. A tick can outlive its five-minute slot — several feeds timing out, then
a slow model call — and the next one would find the brief still unwritten, pay for it a second time,
write a second history entry, and race the first over the payload. The overlapping tick exits 0
instead: whatever is owed is still owed five minutes later. It is deliberately only around the tick.
**Rewrite daily headline** is a person asking for something, and should do it.

## The guest list on a calendar

A calendar entry's `shared_with` is a list of email addresses, and `parse_feed` keeps only the
events with one of them on the guest list or as the organiser. A personal calendar full of work
and private appointments then contributes the family things and nothing else:

- **It is per feed, not global.** The school calendar has no guests, and the global
  `calendar_filter_emails` this replaced emptied it — which is why that key was dropped.
- **It matches `ORGANIZER` as well as `ATTENDEE`, and any one address is enough.** An event the
  partner arranged lists them as organiser, and a Google feed does not always list the organiser
  as a guest of their own event. The old filter looked at `ATTENDEE` alone and required every
  address, so it missed everything they had arranged.
- **It runs before the event dict is built** (`calendars._events`), so a hidden event is never in
  the payload, on the dashboard or in the prompt — and the guest list itself is never stored. The
  dict carries no addresses, and the log says how many addresses a feed has, never which.
- **`describe_feed` counts before and after**, so **Check this link** can say a working link has
  24 events and none of them match. A list that matches nobody looks exactly like an empty
  calendar from the dashboard, and that silent zero was the old filter's failure mode.
- **Saving or removing a calendar forgets what it last said**, through the store's config save.
  Its events, statuses and the fetch stamp go, so the next tick owes a refresh. Publication checks
  also reject a fetch still using the previous settings, including failed-fetch fallback data.
  A rejected refresh stops the tick before the model call; the next tick loads the new config.
  The stored events cannot be re-filtered instead: they carry no addresses, by design.

`addresses()` is the one normaliser — list or comma-separated string in, lowercase list out, with
`mailto:` stripped — and both the form and the engine go through it, so a hand-written
`shared_with: jess@example.com` works the same as the list the settings UI writes.

## Config

`config.yaml` is the single source of truth, and the settings UI writes it back. Loads and saves go
through ruamel round-trip mode with `indent(mapping=2, sequence=4, offset=2)`, so comments, key
order and indentation all survive an edit made from a phone. There is a test asserting a save
changes exactly the lines it means to.

`config.example.yaml` documents every key. Two are migrated on load: a single `calendar_url` becomes
the first entry in `calendars`, and `calendar_filter_emails` becomes that entry's `shared_with` — or
is dropped with a warning when there is no single URL to attach it to. A `recurring` chore list is
not migrated: `with_defaults` raises `ConfigError` for the key, because converting it needs a
decision a loader cannot make and dropping it would lose the family's chores. Every caller sees the
error before anything is written; `doc/upgrading.md` says how to move to `tasks`.

Every item in the five edited lists — people, pets, tasks, special_dates, calendars — carries a
short `id`. The settings UI addresses items by it, because a position is not an identity: delete the
first person and everyone below renumbers onto somebody else's edit form. Ids are backfilled by
`ensure_ids`, which the settings UI calls on load and saves once if it added any. Deliberately not
part of `load_config` — loading must not rewrite the file, and the engine never reads ids.
`_add_id` puts the id *first* in the mapping: ruamel hangs the comment introducing the next section
off the last item of the previous one, so an appended key lands under the wrong heading.

Ids let the settings UI address items without relying on their positions.
