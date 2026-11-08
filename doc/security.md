# Security and privacy rules

Read this when handling calendar feeds, secrets, logging, third-party calls, CI or dependencies. It
applies in both modes. The rules that only exist in cloud mode are in [hosted-mode.md](hosted-mode.md).

DinkyDash is open source, and the hosted product is built in the same public repo. Everything pushed
is world-readable the moment it lands, and the repo is itself the funnel — the Show HN and
r/selfhosted launch point straight at it. The code is read by strangers, so a careless commit is an
incident rather than a tidy-up.

- **Nothing private goes in.** Not a key, not a real family's data, not a calendar URL.
- **Hygiene is visible.** Careless handling of somebody's calendar is a public, permanent argument
  against trusting the hosted version too.

## What must never be committed

`.gitignore` covers `.env`, `config.yaml`, `dashboard_data.json`, `content_history.json` and
`generate.log`. That is the safety net, not the plan: read `git status` before staging and never
`git add -f` one of them. A secret in history survives in every clone and fork after the commit that
removes it, so the fix is rotation, not a revert.

- **An iCal "secret address" is a password in a URL.** Whoever holds it reads that family's whole
  calendar, indefinitely, and there is no way to see who has. It never goes in a commit, a test
  fixture, an issue, a log line, a screenshot, or a prompt to any model. Example URLs in the docs
  and in `config.example.yaml` are visibly fake (`private-xxxx`); keep new ones that way, because
  `.gitleaks.toml` has a rule for the real shape and CI fails on it.
- **Real family data.** Names, dates of birth and children's faces are the entire content of this
  app. Screenshots for the README or the marketing site come from `python sample_board.py`, which
  invents people. Tests invent people too.
- **Secrets come from the environment**, never a literal in code or config. `.env` is not in git and
  there is a copy wherever the app runs, so rotating a key means editing each copy where it
  lives — on a Pi in place, and in the main checkout — rather than pushing one over the other.
- **A new dependency is a supply-chain decision** in an app holding other families' calendars.
  Prefer the standard library; justify anything else in the PR.

## Issues are public too

Engineering work is tracked as GitHub Issues, and issues in a public repo are world-readable exactly
like the code: no secret, no real family data, no calendar URL, no screenshot of a real dashboard.
Anything that must not be public goes in a private repository, and the issue here says only that a
private note exists. Strategy documents (pricing, positioning, launch plans) live outside this
repository and its issues.

## Handling other people's data

- **Calendar feeds are untrusted remote input.** Event titles land in the rendered page and in the
  model prompt. Autoescaping covers the page: the single `|safe` in `web/` is on the QR code
  `segno` draws from our own screen URL, and none goes on feed or user content. In the prompt the
  text is data: an event titled "ignore your instructions and ..." must not change what the model does.
- **`fetch_feed` fetches URLs a stranger typed, from our infrastructure.** `calendars.py` allows
  https only (`webcal://` is normalised, plain `http` refused); refuses private, loopback,
  link-local, reserved and multicast addresses; follows redirects by hand and re-checks each hop;
  connects to the address it checked, keeping the hostname for TLS and `Host`; ignores environment
  proxies; and caps the body at 10 MB. `FeedRefused` subclasses `FeedError`, so one bad URL is a
  failed feed, not a failed tick. Tests: `test_feed_safety.py`, `test_feed_transport.py`.
- **Calendar contents go to Anthropic** for the headline, and the privacy page, the sub-processor
  list, `/settings/account` and the blurb beside the calendar field say so. **Those pages are
  claims about this code**: change what the app stores, sends, or sends it to, and change the
  policy in the same commit. Anything new that sends data to a third party is named on the privacy
  page and `/settings/account` in the same commit.
- **Log the label, never the URL** (`fetch_events` logs `entry["label"]`). **Ticks log metadata,
  never generated family text.** Access-log redaction covers malformed and encoded screen URLs too
  (`tests/test_private_logs.py`).
- **A `FeedError` message must never carry the URL, and `calendars._why` is what keeps it out.**
  `requests` formats both `raise_for_status()` and connection errors with the full URL (`404 Client
  Error: ... for url: https://.../private-REALSECRET/basic.ics`), and that message reaches
  `generate.log` and the feed status on the settings page. `_why` reduces it to a category and a
  status code, and the host is left out too: it is not possible to tell `calendar.google.com` from
  `calendar.the-smiths.example` in code. The parse error is scrubbed for the same reason — a parser
  quotes the line it choked on, which is an appointment. `tests/test_secrets_and_headers.py` fails
  if any of that regresses.

## Self-hosted has no authentication by default

Unless `DINKYDASH_PARENT_PASSWORD` is set (`web/parent.py`: a signed 30-day session, per-caller rate limit, CSRF on every form, refusing to start without `DINKYDASH_SECRET_KEY`), anyone who can reach the port can edit the config. That is the same trust model as the file it
writes, so keep port 5000 on a trusted LAN and never expose it to the public internet. The README
says so in a callout under **Quickstart**. Cloud mode cannot inherit this — see
[hosted-mode.md](hosted-mode.md).

With sign-in on, the phone page (`/h`, `web/routes/phone.py`) lets a family member pick their name and type a PIN if a parent set one. PINs are four to eight digits, hashed with `scrypt` (`dinkydash/pins.py`), compared in constant time and kept in `auth.json` beside the config (mode 0600, gitignored, never in `config.yaml`). Wrong PINs share the sign-in rate limit (ten in fifteen minutes per caller). A person with no PIN can be picked by anyone who reaches the page; that is the meaning of optional.

## The safety net, and what it does not cover

`.github/workflows/test.yml` runs two jobs on every push and pull request: **pytest** (Python 3.11,
with and without Postgres) and **gitleaks** over the full history (`fetch-depth: 0`), using the
pinned MIT binary rather than the upstream action. `.gitleaks.toml` adds rules for iCal secret
addresses (Google `private-` + 32 hex, iCloud `/published/2/`). Its one allowlist entry is the
public Ahrefs site key. **Allowlist only values that are public by design**; a real secret that
reached a commit is fixed by rotating it. GitHub secret scanning is on as a second layer.

Not covered: anything password-shaped in a URL other than the two calendar shapes needs its own
gitleaks rule. `config.yaml` is in early history with two children's first names and no credential;
that is public and permanent, and the reason the rules above exist.

**Requirements are pinned with `==`** to what CI passes. Bump deliberately; `anthropic` must stay at
1.x or later for `output_config`. **`requirements.txt` is runtime only** — what a Pi installs.
`website/` and tooling dependencies go in `requirements-dev.txt`.
