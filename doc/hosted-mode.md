# Hosted (cloud) mode rules

Read this when touching cloud mode: `pgstore.py`, `db.py`, `accounts.py`, `web/routes/auth.py`,
`screen.py`, `admin.py`, `billing.py`, or anything that gates on `DINKYDASH_MODE`. Cloud mode is
frozen: it stays in the tree and its tests keep passing, but new work does not extend it (see
[Single mode first](../CLAUDE.md#single-mode-first)).

Self-hosted is one family on their own network with **no authentication by design**. Cloud mode is a
different product on the same code, so it raises the stakes. Each rule is enforced in the named file
and its test.

Hosted operations have checks beyond this repository's self-hosted container setup; do not treat the
Raspberry Pi image as a deployment of cloud mode. Cloud changes still require the database, worker
and privacy boundaries below. General privacy rules are in [security.md](security.md).

## Scoping and access

- **Every read and write is scoped to a `family_id` from the session** (`web/family.py`), one
  `PostgresStore` per request over one pool per process. Nothing a caller sends names a family.
  When a route does take a family id, check it in `family.py`, and **a mismatch is a 404, never a
  403** — "forbidden" confirms the row exists.
- **`/admin` is gated by `DINKYDASH_ADMIN_EMAILS`; a miss is a 404 and an unset list is nobody.**
  It shows aggregates (`growth_by_day`, paying count) and a roster of addresses and bookkeeping
  columns — never a config, a name, a calendar or a family id (`tests/test_admin.py`).
- **Cloud mode refuses to start without `DINKYDASH_SECRET_KEY`**; the session is the authentication.
- **CSRF on every writing form, in both modes** (`web/session.py`); a test walks the templates.

## Sign-in

- **Magic links** (`dinkydash/accounts.py`): 32 random bytes, only the SHA-256 stored, fifteen
  minutes, spent by one `UPDATE ... WHERE used_at IS NULL RETURNING`. **`GET /login/link` only
  renders a button; its `POST` spends the link**, because mail scanners follow links but do not
  submit forms. Do not auto-submit that page.
- **`/login` answers identically whether or not the address has an account**, including when
  rate-limited, refused by the bot check, or when the send fails — it is also the sign-up form, so
  there is no second route to give the game away. The family is created when the link is spent,
  not when the form is posted, so a stranger's POST costs an email and not a trial.
- **Turnstile** (`web/turnstile.py`) is on only when both keys are set. A refusal is answered
  before the address is looked up; an unreachable Cloudflare lets the request through.
- **Rate limits are ours** (`web/ratelimit.py`, per IP, in process; per address in Postgres), so a
  refusal is a log line: the caller's IP, the domain of the address asked about, never the address.

## Tokens and logs

- **Tokens stay out of logs.** Login tokens ride in `?t=`; screen tokens are in `/s/<token>`.
  The gunicorn access format uses `%(U)s`, and `auth.NoTokens` scrubs both from both request
  loggers (`tests/test_auth.py`, `tests/test_screen.py`).
- **Screen tokens never expire**, so `/s/<token>` is `noindex`, `no-store`, makes no third-party
  request, never echoes the token, and is rotatable. A wrong token is a 404. Only misses are
  rate-limited.

## Third parties and spend

- **Fathom** (`web/fathom.py`) loads only with `FATHOM_SITE_ID`, only on the public sign-in pages
  and the one new-account page, and sends the path without the query string.
- **Spend caps** (`dinkydash/budget.py`) count calls, not money, per family and globally, charged
  on the attempt. A refusal is an `OverBudget`, a `GenerationError`, so the existing keep-last-good
  path handles it. **Anything new that calls Anthropic takes a budget**, the way it takes a store.
- **Sentry** (`dinkydash/sentry.py`, cloud only) receives the exception, our frames, the log
  template and the request method. `scrub` strips URLs, headers, bodies, locals, breadcrumbs and
  log arguments. **Keep data in a `log.error`'s arguments, never its template** (`tests/test_sentry.py`).
- **Anything new that sends data to a third party is named on the privacy page and
  `/settings/account`** in the same commit.
