# PRD: household modules — tasks, shopping, toggles and sign-in

Status: agreed, not started. Work is broken down in GitHub Issues, with one milestone per phase.
This document holds engineering intent only: what each feature does, how it is built, and how it is
checked. Wording that a customer reads follows [voice.md](voice.md) and
[terminology.md](terminology.md).

## 1. Problem

The dashboard is a passive display. It says whose turn a chore is, and nothing can be ticked off, so
it cannot tell a family whether anything happened. Three gaps follow:

1. **Chores are a rota, not a routine.** A chore rotates one person per day, whatever the day is.
   Weekday and weekend jobs, weekly jobs and one-off reminders cannot be expressed.
2. **Nothing is written back.** There is no check-in, so there is nothing to build a streak or any
   other encouragement on.
3. **The app does one family's calendar and nothing else.** A shared shopping list is the most
   common thing a wall screen in a kitchen is asked for.

A fourth gap sits underneath: every part of the app is on or off together. A family that wants the
agenda and the shopping list, but not chores or countdowns, cannot have that.

## 2. Goals and non-goals

### Goals

- Each optional module can be switched on and off, with its data kept.
- Chores and reminders become one module, **Tasks**, with real recurrence, assignment rules,
  check-ins from a phone and a per-person streak.
- A family shopping list that is edited on a phone and shown on the wall.
- Optional sign-in for the self-hosted app, so it can be reached beyond the local network and so a
  phone knows who is ticking.
- The wall screen stays read-only and calm, and follows changes from phones within about fifteen
  seconds.

### Non-goals

- **Multi-tenant cloud mode.** It stays in the repository, frozen: this work adds nothing to it. A
  separate issue evaluates removing it.
- Touch interaction on the wall screen.
- Points, badges, leaderboards, rewards.
- Times of day on tasks. The agenda already carries anything with a clock time.
- Categories, stores or multiple lists for shopping.
- Telling the model about completions, streaks or the shopping list.
- Push (SSE or WebSocket) updates.

## 3. Settled decisions

| # | Decision |
|---|---|
| D1 | The phone is the write path. The wall screen is read-only and shows the results. |
| D2 | Chores and reminders merge into one module, **Tasks**. Existing chores migrate without changing anyone's turn on the day of the upgrade. |
| D3 | Always on: headline, agenda, family. Toggleable: Tasks, Special dates, Shopping. Toggling off hides the feature and keeps the data. |
| D4 | Streaks are per person, plus per task for tasks assigned to "Anyone". |
| D5 | Three phases, delivered in order (section 5). |
| D6 | Recurrence: daily, chosen weekdays (with Weekdays and Weekends presets), every N days, monthly on a day number, monthly on the first, second, third, fourth or last weekday, and once. |
| D7 | Assignment: a fixed person, rotating, anyone, or everyone. Rotation counts occurrences, not days of the year. |
| D8 | A streak counts consecutive days on which everything due for the person was done. Days with nothing due neither extend nor break it. A missed due day resets it. No freezes. |
| D9 | The wall refreshes as it does now and also polls a change counter about every fifteen seconds. |
| D10 | The model is told which tasks are due today and nothing about completions or streaks. |
| D11 | Wall tasks card: today's tasks with done state and streaks, plus a "Yesterday, still open" group that sheds first. |
| D12 | The phone page covers today and yesterday. Parents correct any date in the last fourteen days on the Activity page. |
| D13 | The module is named **Tasks** in the interface; "Whose turn" becomes an assignment option. |
| D14 | Shopping: one list, with text, an optional quantity, who added it and when. |
| D15 | Ticking moves an item to Bought. Bought items clear after twenty-four hours or by "Clear bought". |
| D16 | The wall shows about eight unbought items, then "+N more". Autocomplete is not in the first release. |
| D17 | Sign-in is opt-in. See section 7. |
| D18 | Completions are keyed on stable person ids. A rename keeps streaks; deleting a person deletes their completions. |
| D19 | Special dates off hides the whole "Coming up" card, birthdays included. There is no separate birthday switch. |
| D20 | Defaults: existing installs keep Tasks and Special dates on and get Shopping off. |
| D21 | Celebration on finishing the day and "best streak" appear on the phone only. |
| D22 | Shopping items, completions and streaks never reach the model. Caps: 40 tasks, 100 shopping items, 80-character titles, 40-character quantities. |
| D23 | Activity page in settings: streaks, a thirty-day grid per person, and every unticked due occurrence in the last fourteen days with a one-tap tick. |
| D24 | Single mode is the product. Cloud code is frozen. |

## 4. Design

### 4.1 Configuration

New and changed top-level keys, all passing through the config dict and `with_defaults`:

```yaml
features:            # D3, D20
  tasks: true
  special_dates: true
  shopping: false

tasks:               # replaces `recurring`
  - id: ...
    title: Set the table
    emoji: "🍽️"
    recurrence:
      kind: daily | weekdays | interval | monthly_day | monthly_nth | once
      days: [0, 1, 2, 3, 4]      # weekdays: Monday = 0
      every: 3                   # interval: every N days
      start: 2026-01-05          # interval and rotation anchor
      day: 15                    # monthly_day
      nth: 1 | 2 | 3 | 4 | -1    # monthly_nth, -1 is the last
      weekday: 4                 # monthly_nth
      date: 2026-12-24           # once
    assignment:
      mode: fixed | rotate | anyone | everyone
      people: [<person id>, ...]
```

`recurring` is migrated on load by `with_defaults`: each chore becomes a daily task with
`assignment.mode: rotate`, its names converted to person ids, and a rotation offset chosen so the
person on duty on the day of the upgrade is unchanged. Rotation then counts occurrences, so it
differs from the old day-of-year rule at the year boundary, where the old rule restarted.

Shopping items and completions are not config: they change too often and grow without bound.

### 4.2 Engine (pure)

All of it lives under `dinkydash/` and takes `today` as a parameter.

- `recurrence.py` — `occurs_on(task, day) -> bool` and `occurrence_index(task, day) -> int`.
- `context.py` — `compute_chore_assignments` is replaced by `tasks_for(config, day)`, returning each
  due task with its assignees.
- `streaks.py` — `person_streak(person_id, tasks, completions, today)` and
  `task_streak(task, completions, today)`, computed from the completions, never stored.
- `board.build_view` gains the tasks card, the yesterday group and the shopping card, each gated by
  `features`.
- `prompt.py` is passed the tasks due today and nothing else new (D10).

### 4.3 Storage

The storage seam grows, for `FileStore` only. `PostgresStore` is not changed (D24), so the new
operations are absent there and the features are forced off when cloud mode is selected.

- `load_completions(since)`, `record_completion(entry)`, `remove_completion(entry)`.
  Completions are a list of `{task_id, date, person_id, completed_at}` in `completions.json` beside
  the config, trimmed to the last 400 days on write.
- `load_shopping()` and `save_shopping(items)`, in `shopping.json`. An item is
  `{id, text, quantity, added_by, added_at, bought_at}`.
- `change_token()` — a value that changes whenever the config, completions, shopping list or
  payload change, for the counter in 4.5.
- Both files are gitignored, written atomically, and read only by `store.py` (the "only files that
  open a file" rule in CLAUDE.md still holds).

### 4.4 Interface

| Surface | Route | Notes |
|---|---|---|
| Wall dashboard | `/`, or `/s/<token>` with sign-in on | Read-only. Tasks card, optional yesterday group, shopping card. |
| Phone page | `/h` | Tabs for the enabled features only. Tasks, Shopping, and who the phone is. |
| Activity | `/settings/activity` | Parent only when sign-in is on. |
| Feature switches | Settings home | One switch per module. |
| Task editor | `/settings/tasks` | Recurrence and assignment pickers; replaces the Chores section. |
| Change counter | `/changes`, `/s/<token>/changes`, `/h/changes` | Returns a number and nothing else. |

Interface rules:

- Every length is in `rem` or `em`, and every colour is a token (web/CLAUDE.md).
- The tasks card sheds the yesterday group first when it overflows, then the oldest done tasks. The
  shopping card shows about eight items then "+N more", on the same fit logic as countdowns.
- Yesterday's open tasks use the neutral card style. No red, no warning icon, no banner.
- The phone page is built for a thumb, installs through the existing phone manifest, and makes no
  third-party request.
- Mockups for the task editor, the phone page and the Activity page are added to `design/` before
  each is built, with their reasoning, as for the existing screens.

### 4.5 Following phones from the wall

The page keeps its full refresh. Alongside it, a small script fetches the change counter about every
fifteen seconds and triggers the existing refresh path when the number moves. The endpoint carries
no family content, is `no-store`, and follows the access rule of the page it serves. A failed fetch
is silent; the full refresh still runs.

## 5. Phases

Each phase is a GitHub milestone, shipped and usable on its own.

### Phase 1 — toggles, sign-in, phone page shell, change counter

- `features` block, migration default (D20), settings switches.
- Opt-in sign-in (section 7), the phone page shell with "who are you", and the change counter
  wired into the wall.
- Special dates behind its switch.

Acceptance:

- With nothing configured, behaviour is unchanged for an existing install: no sign-in, same pages.
- Switching a feature off removes it from the wall, the settings home and the phone page, and
  switching it back on restores its data.
- With `DINKYDASH_PARENT_PASSWORD` set, `/settings` and `/h` are refused without a session, `/`
  redirects to sign-in, and the wall works at `/s/<token>`.
- Editing the config in another browser moves the wall within the poll interval.

### Phase 2 — tasks

- `tasks` config, the `recurring` migration, the recurrence engine, assignment modes.
- Completions storage, check-in on the phone, streaks, the wall card, the yesterday group.
- The Activity page and parent corrections.
- Glossary, README and settings copy updated in the same change (section 9).

Acceptance:

- A migrated chore shows the same person on the day of the upgrade.
- Each recurrence kind produces the right days across month ends, leap years and daylight-saving
  changes, in the family's timezone.
- A person's streak survives a rename, ends at a missed due day, and is unmoved by a day with
  nothing due.
- A member can tick only what section 7 allows; a parent can tick any date in the last fourteen
  days and nothing older or later.
- The prompt contains the due tasks and no completion or streak data.

### Phase 3 — shopping

- `shopping.json`, the phone tab, the wall card, auto-clear after twenty-four hours.

Acceptance:

- Items can be added, edited, ticked, un-ticked and deleted from the phone, subject to section 7.
- Bought items disappear from the list after twenty-four hours and on "Clear bought".
- No shopping text appears in any prompt (a test asserts it).
- The caps in D22 are enforced on the server with a plain-English refusal.

## 6. Streak rules (precise)

- A task is **due for a person** on a day when it occurs that day and the person is a fixed
  assignee, the rotating assignee for that occurrence, or one of "everyone".
- A day is **done** for a person when every task due for them that day has a completion for them.
- A person's streak counts back from today across days with something due: done days count, a
  not-done day ends the streak. Today counts once it is done and is skipped, not counted as a miss,
  while it is still open. Days with nothing due are skipped.
- A task assigned to "Anyone" has its own streak: consecutive occurrences with at least one
  completion, by anyone. Who did it is recorded.
- Streaks are capped at 400 days by the history limit.

## 7. Sign-in

Opt-in. With `DINKYDASH_PARENT_PASSWORD` unset the app behaves as it does today (open on the
local network, no authentication by design) and the phone page works on trust: pick your name, and
anyone can tick anything.

With it set:

- **Parent:** signs in with the password. Settings, Activity, corrections, PIN and token
  management.
- **Member:** a person from the People list who picks their name on the phone page and enters a PIN
  if the parent set one. A member ticks their own tasks and "Anyone" tasks, and adds, edits, ticks
  and deletes shopping items. A member cannot tick another person's task.
- **Wall:** the dashboard moves to `/s/<token>`, a random token created on first use and rotatable
  from settings. `/` redirects to sign-in. The token page is `noindex` and `no-store`, makes no
  third-party request, never echoes the token, and answers a wrong token with a 404.
- **Storage:** the parent password comes from the environment. Member PINs and the screen token live
  in `auth.json`: gitignored, mode 0600, PINs hashed with the standard library's `scrypt`, compared
  in constant time. Nothing goes in `config.yaml`, which is exported and edited by hand.
- **Session:** a signed cookie keyed on `DINKYDASH_SECRET_KEY`, thirty days on a phone, CSRF checked
  on every writing form (the existing session code, and the test that walks the templates, apply).
- **Abuse:** failed sign-ins and screen-token misses are rate limited per IP with the existing
  in-process limiter. Tokens and PINs stay out of every log; the access-log scrubber covers the new
  routes.
- **Recovery:** a forgotten PIN is reset by a parent; a forgotten parent password is changed in the
  environment and the app restarted.

## 8. Privacy and safety

- Task titles and today's assignees go to the model, as chore titles do now. Shopping items,
  completions and streaks do not. The privacy page and sub-processor list are unchanged, and a test
  fails if a shopping string or a completion reaches a prompt.
- User-entered text (titles, quantities, names) is escaped by the template engine; no new `|safe`.
- Every new writing route checks CSRF and the access rule in section 7 before it reads the body.
- Tests invent their people, as elsewhere in the suite. Nothing real is committed.

## 9. Documents that change with the code

- `README.md` and `doc/terminology.md`: remove "nothing to tick off" and "no completion checkbox"
  when Phase 2 ships; add Tasks, Shopping, Activity and the phone page to the glossary.
- The chores blurb in `web/routes/settings.py` becomes the Tasks blurb.
- `doc/running-it.md`: the sign-in variables, `auth.json`, and what to back up
  (`completions.json`, `shopping.json`).
- `config.example.yaml`: `features` and `tasks`, with fake names.
- `.gitignore`: `completions.json`, `shopping.json`, `auth.json`.
- `CLAUDE.md`, `dinkydash/CLAUDE.md` and `web/CLAUDE.md`: the seams and routes above.

## 10. Test plan

New tests live in `tests/`, one file per module:

- `test_recurrence.py` — every kind, month ends, leap day, last weekday in 4- and 5-week months,
  daylight-saving days.
- `test_task_migration.py` — `recurring` to `tasks`, same person on the day of the upgrade.
- `test_streaks.py` — rename, delete, skipped days, today open versus done, anyone tasks.
- `test_completions_store.py` — add, remove, trim at 400 days, atomic write.
- `test_shopping.py` — caps, ticking, twenty-four-hour clear.
- `test_features.py` — each switch hides everything it owns and loses no data.
- `test_auth_single.py` — off by default, roles, permissions, PIN hashing, rate limits, redirects,
  token page headers, 404 on a wrong token, log scrubbing, CSRF.
- `test_change_counter.py` — moves on each kind of change, carries no content.
- `test_private_prompt.py` — shopping and completions never reach `build_user_prompt`.
- Existing board, settings and config tests that mention chores are updated, not deleted.

## 11. Points chosen while writing this document

These were not discussed and are defaults to confirm or change in the relevant issue:

1. A monthly day that a month lacks (the 31st) falls on the month's last day, as a 29 February
   birthday falls on 28 February in a common year.
2. A PIN is four to eight digits.
3. The celebration runs when a person's last due task of the day is ticked, once per day.
4. The cloud-mode code that reads `recurring` is updated only as far as keeping the suite green;
   the features are forced off there (section 4.3).
5. The poll pauses while the page is hidden and resumes on focus.

## 12. Roadmap (not in these phases)

- Tell the headline about streaks and completions, with the privacy-page change that implies.
- Shopping autocomplete from a ninety-day history.
- Touch interaction on the wall screen.
- Push updates (SSE) behind the same page hook.
- Evaluate removing the frozen cloud mode.
- Review `doc/operations.md`.
