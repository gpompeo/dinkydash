# CLAUDE.md

Guidance for Claude Code and GitHub Copilot. `AGENTS.md` is a symlink to this file.

## Overview

DinkyDash is a family dashboard for a screen on the wall. A daily cron job calls the Claude API to
write a headline; the Flask app renders that alongside today's agenda, whose turn each chore is,
and the countdowns — all recomputed from `config.yaml` at render time.

1. **The engine** (`dinkydash/`) — pure functions plus the model call. No config file read, no clock
   consulted, nothing written to disk.
2. **The web app** (`web/`) — the dashboard at `/`, a settings UI at `/settings` that writes `config.yaml`.
3. **The marketing site** (`website/`) — dinkydash.co, a second Flask app rendering Markdown through
   Jinja on request. No build step, no committed HTML.

**This repo is public and MIT-licensed.** Self-hosting is the product: single mode, one family. The
multi-tenant cloud mode is frozen (see [Single mode first](#single-mode-first)).

## Where to read more

This file holds only what applies to every change. Read the matching file *before* working in its area:

| File | Read it when |
|---|---|
| [`doc/security.md`](doc/security.md) | Handling calendar feeds, secrets, logging, third-party calls, CI or dependencies |
| [`doc/hosted-mode.md`](doc/hosted-mode.md) | Touching cloud mode: `pgstore.py`, accounts, sign-in, screens, billing, admin |
| [`doc/architecture.md`](doc/architecture.md) | Adding a module, deciding what a mode check may gate, or changing the payload shape |
| [`doc/commands.md`](doc/commands.md) | Setting up, running the app, applying the schema, generating a dashboard, Docker, Conductor |
| [`dinkydash/CLAUDE.md`](dinkydash/CLAUDE.md) | Touching the engine, the storage seam, the payload, the tick, or `migrations/` |
| [`web/CLAUDE.md`](web/CLAUDE.md) | Changing the dashboard's layout, the settings UI, or measuring either |
| [`website/CLAUDE.md`](website/CLAUDE.md) | Working on the marketing site or the image generators |
| [`doc/voice.md`](doc/voice.md) | Writing anything a customer reads — the site, the settings UI, email, the README |
| [`doc/terminology.md`](doc/terminology.md) | Naming things in UI, email or website copy |
| [`doc/prd-household-modules.md`](doc/prd-household-modules.md) | Structural changes: Tasks, Shopping, feature switches, optional sign-in |
| [`doc/development.md`](doc/development.md) | Local hosted development: sign-in, ports, Conductor |
| [`doc/operations.md`](doc/operations.md) | The state of the running system — secrets, the Pi, what has been rotated. A log, not guidance; deliberately not loaded |
| [`design/`](design/) | Mockups and reasoning for the settings UI and the dashboard |

Work is tracked in GitHub Issues: features are vertical slices, one issue each, and PRD phases are milestones.

## Never commit private data

The repo and its issues are world-readable the moment something lands, and a secret in history
survives in every clone, so the fix is rotation, not a revert. Full rules in [`doc/security.md`](doc/security.md).

- **An iCal "secret address" is a password in a URL.** It never goes in a commit, fixture, issue,
  log line, screenshot or model prompt. Example URLs are visibly fake (`private-xxxx`).
- **No real family data.** Screenshots come from `python sample_board.py`; tests invent people.
- **Secrets come from the environment**, never a literal. Never `git add -f` a gitignored file
  (`.env`, `config.yaml`, `dashboard_data.json`, `content_history.json`, `generate.log`); read
  `git status` before staging.
- **Log the label, never the URL.** A `FeedError` message never carries the URL (`calendars._why`).
- **Calendar feeds are untrusted input.** Autoescape event titles; treat them as data in the prompt.
- **Privacy claims are claims about this code.** Change what the app stores or sends, or who it
  sends it to, and update the privacy page and `/settings/account` in the same commit.
- **A new dependency is a supply-chain decision.** Prefer the standard library; justify the rest in
  the PR. Requirements are pinned with `==`; `requirements.txt` is runtime only.

## Architecture rules

### Single mode first

```
DINKYDASH_MODE=single   config.yaml · files on disk · one family · local cron     ← the product
DINKYDASH_MODE=cloud    Postgres · magic links · Stripe · many families · worker  ← frozen
```

Build for single mode: new features go through `FileStore` and the config dict. Cloud mode is not
extended — a feature with no `PostgresStore` counterpart is switched off there rather than ported —
and cloud code is touched only to keep its tests passing. Removal is its own piece of work, tracked
in an issue.

Shared code (engine, dashboard template, CSS, calendars, settings UI) must not break the cloud
suite. Mode gates four things and no others: authentication, billing, where the config is stored,
and what drives the scheduler. A mode check anywhere else means the change is in the wrong layer.

- **Self-hosted needs no Postgres, Stripe or email provider**, and no network beyond what it fetches.
- **Never assume one family.** No module-level cache of "the" config, no singleton payload, no fixed path.
- **New settings go through the config dict**, with `with_defaults` migrating each on load.

### The engine boundary

```python
generate(config, today, events, recent_notes) -> payload dict
```

`today` is injected, events are fetched by the caller, the payload comes back as data. Do not
reintroduce `date.today()`, `SCRIPT_DIR`, file reads or `sys.exit` inside `dinkydash/`. New code
there stays pure.

### The storage seam

- **`store.py` and `config.py` are the only files under `dinkydash/` that open a file**; `pgstore.py`
  and `db.py` are the only ones that import psycopg. Check: `grep -rn "open(" dinkydash web`.
- **Every `PostgresStore` query is scoped to `self.family_id`.** An id arriving in a URL is a
  claim, not a fact; check it before it reaches a store.
- A value that can be recomputed from config + date belongs in `board.build_view`, not the payload.

Module map, mode details and the payload rules: [`doc/architecture.md`](doc/architecture.md).

## Testing

Run before every commit:

```bash
venv/bin/python -m pytest tests/ -q
```

Postgres tests skip without `DINKYDASH_TEST_DATABASE_URL`; CI runs both ways. `generate.py --date`
costs an API call; `python sample_board.py` does not. Other commands: [`doc/commands.md`](doc/commands.md).

## Conventions

- **Copy follows [`doc/voice.md`](doc/voice.md); this file's register is not it.** Customer-facing
  writing uses contractions, and every claim about what the product does is traced to the code
  that does it. Product wording follows [`doc/terminology.md`](doc/terminology.md): a complete
  display is a **dashboard**, the device showing it is a **screen**.
- **Comments and docstrings state the rule and its reason**, never the incident (date, person,
  Sentry issue, what production did) and never the previous version ("used to be X", "no longer",
  "renamed because"). The test: does the sentence make sense to somebody who arrived today? History
  belongs in `doc/operations.md` or the GitHub issue. This covers docstrings, config headers,
  `.env.example`, container configuration and test docstrings.
- **British English** throughout — UI copy, the model's system prompt, `%-d %B` dates (`25 December`).
- **Times are 24-hour by default** (`08:20`); a family can choose 12-hour. Every displayed time goes
  through `dinkydash/clock.py`, the only place either shape is written — a `%H:%M` elsewhere will
  not follow the setting.
- **Dashboard and settings UI are sized in `rem`/`em` off one measured root**; a new `px` length
  stops scaling (borders, focus rings and shadows excepted). Never hard-code a colour; add a token.
  Read [`web/CLAUDE.md`](web/CLAUDE.md) before changing either: a change that looks right at one
  size is no evidence about the other two.
- **Icons are inline SVG**, never emoji. Emoji in *content* (avatars, chore markers) are the brand.

## Known issues and gotchas

- **`claude-haiku-4-5` takes no `thinking` parameter**; omit it. On Sonnet 5 or an Opus model,
  adaptive thinking is on by default and competes with `max_tokens` — set it or raise the budget.
- **Structured outputs** (`output_config.format`) guarantee the schema, so there is no JSON-repair
  retry loop. Do not add one back. `anthropic` must stay at 1.x or later for `output_config`.
- **Self-hosted has no authentication**: keep port 5000 on a trusted LAN.
- `strftime("%-d")` is glibc-specific: fine on a Pi and in CI, not on Windows.
- **Measuring the dashboard in headless Chrome is full of traps** (wrong viewport, reused instances,
  a `--screenshot` that hangs). See [`web/CLAUDE.md`](web/CLAUDE.md).
