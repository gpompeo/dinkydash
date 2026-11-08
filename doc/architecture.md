# Architecture

Read this when adding a module, moving code between layers, or deciding what a mode check may gate.
The rules that always apply (engine purity, the two storage invariants, single mode first) are in
[CLAUDE.md](../CLAUDE.md); this holds the detail.

## Two modes

```
DINKYDASH_MODE=single   config.yaml · files on disk · one family · local cron     ← the product
DINKYDASH_MODE=cloud    Postgres · magic links · Stripe · many families · worker  ← frozen
```

The engine, the dashboard template, the CSS, the calendar handling and the settings UI are shared by
both modes, so a change to them must not break the cloud suite. Mode gates four things and no
others — authentication, billing, where the config is stored, and what drives the scheduler. A mode
check anywhere else means the change is in the wrong layer.

**Where the dashboard is served is part of the authentication gate**, not a fifth thing. Single mode
puts it at `/`: one family, no session, the URL somebody types into a Pi's kiosk browser. Cloud mode
cannot, because a wall panel has no way to sign in — so there the dashboard is at `/s/<token>` and `/`
is the front door of the signed-in area. `board.render_board` is what the two routes share, so it is
one dashboard reached two ways rather than two that drift, and `tests/test_cloud_mode.py` asserts the
two are byte-identical apart from the one link that has to differ.

- **Self-hosted keeps working with no Postgres, no Stripe, no email provider**, and no network
  beyond the two things it fetches. A feature that needs a database is a cloud feature, or it is not
  a feature yet.
- **Hosted never assumes one family.** No module-level cache of "the" config, no singleton payload,
  no fixed path on disk. If a value is per-family, it is a parameter.
- **New settings go through the config dict**, so they survive both as commented YAML and as a
  `jsonb` column, with `with_defaults` migrating each on load. Nothing below the storage layer reads
  `config.yaml`.
- **New code in `dinkydash/` stays pure**, per the engine boundary. That purity is what makes the
  two modes one codebase rather than two.

## The engine boundary

```python
generate(config, today, events, recent_notes) -> payload dict
```

`today` is injected, events are fetched by the caller, and the payload comes back as data. This is
what lets one code path serve a Pi cron job and, later, a multi-tenant scheduler — and it is what
makes the logic testable. Do not reintroduce `date.today()`, `SCRIPT_DIR`, file reads, or `sys.exit`
inside `dinkydash/`.

## Module map

```
dinkydash/
├── context.py         ages, birthdays, countdowns, chore rotation (pure)
├── calendars.py       iCal fetch, parse, recurrence expansion, merge feeds
├── prompt.py          system + user prompt, note kinds, response schema
├── claude_client.py   the API call, with structured outputs
├── generate.py        orchestrator: config + date + events -> payload
├── board.py           payload + config -> what the template renders
├── config.py          config.yaml load/save (ruamel round-trip), item ids
├── clock.py           the only place a displayed time is formatted, in either shape
├── history.py         what the recent notes say, and how they trim (pure)
├── schedule.py        due(config, payload, now) -> what a tick owes (pure)
├── store.py           the seven storage operations; FileStore, the single-mode one
├── pgstore.py         PostgresStore, the cloud one. Imports psycopg; single mode never does
├── db.py              the connection pool and the migration runner (cloud only)
├── mail.py            one transactional email, over SendGrid (cloud only)
├── accounts.py        users, the links that sign them in, and sign-up (cloud only)
├── screens.py         the token that puts a dashboard on a wall (cloud only)
├── budget.py          what a family may spend on the model, and what everybody may
│                     (`accounts.delete_family` is the hard delete)
├── billing.py         hosted subscriptions: Stripe owns payments, Postgres owns access (cloud only)
├── lifecycle.py       trial and access boundaries, on the database's aware clock (cloud only)
├── growth.py          signups and activations per day, with no family in the row (cloud only)
├── sentry.py          error reports and the worker's check-in, and what neither may carry (cloud only)
└── runner.py          the two halves of the day, reading and writing through a store

web/
├── __init__.py        create_app(): the pool, the mode gates, the blueprints
├── family.py          which family a request is for, and its store
├── session.py         what the cookie carries: who is signed in, and CSRF
├── setup.py           the set-up checklist: what a new family still has to do, from the config
├── assets.py          static URLs with the file's content version, and the year they are cached for
├── ratelimit.py       a per-key counter, in this process (the per-IP half)
├── turnstile.py       the bot check in front of /login; off unless both keys are set
├── urls.py            app origins and dashboard paths, shared with the login-link CLI
├── emoji.py           what a free-text emoji field is allowed to hold
├── manifest.py        the two installable pages: a wall panel and a phone
├── feedback.py        what somebody can tell us: one form, one email, nothing kept
├── routes/board.py    the dashboard and the preview harness
├── routes/settings.py the settings UI (one table drives every list section)
├── routes/auth.py     /login, /login/link, /logout — cloud mode only
├── routes/screen.py   /s/<token> — the dashboard with no session, cloud mode only
├── routes/admin.py    /admin — signups and activations by week, for DINKYDASH_ADMIN_EMAILS only
├── routes/billing.py  signed-in payment actions, and the separately signed Stripe webhook
└── templates/         board.html, preview.html, auth/*.html, settings/*.html, admin/growth.html
```

## The storage seam

Seven operations, on one object, and nothing above them knows what is behind it — `FileStore` for a
Pi, `PostgresStore` for cloud mode, and `tests/test_store_contract.py` asserting the two behave
identically. Two invariants hold anywhere in the repo:

- **`store.py` and `config.py` are the only files under `dinkydash/` that open a file**, and
  `pgstore.py` and `db.py` are the only ones that import psycopg. `grep -rn "open(" dinkydash web`
  is the check, and it should stay that short. A new file read anywhere else is a caller that cloud
  mode will have to fork.
- **Every `PostgresStore` query is scoped to `self.family_id`.** There is no unscoped read and no
  unscoped write in that file, and there must never be one. An id arriving in a URL is a claim, not
  a fact, and the place to check it is before it reaches a store.

The seven operations, how the halves are written, the migration runner, the connection pool, what
the payload may hold and how a tick's two cadences are decided are in
[`dinkydash/CLAUDE.md`](../dinkydash/CLAUDE.md).

## Changing the payload shape

Ask first whether the value can be recomputed from config + date. If it can, it belongs in
`board.build_view`, not the payload — that is what keeps the stale state honest. The payload is for
things only the generator can know. Then ask which half owns it: a key a refresh writes goes in
`runner.REFRESH_KEYS` so `write_brief` carries it forward, and a key the brief writes must be one a
refresh never touches.
