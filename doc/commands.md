# Commands and workflow

Read this when setting up a checkout, running the app, applying the schema, generating a dashboard
or working in a new Conductor workspace. Local hosted development (sign-in, port overrides,
Conductor configuration) is in [development.md](development.md).

## Setup (Python 3.11+)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest + the website build; not deployed to the Pi
cp config.example.yaml config.yaml
```

## Tests

Run before every commit:

```bash
venv/bin/python -m pytest tests/ -q
```

That is the suite a self-hoster runs: the Postgres tests skip, everything else passes. To run the
other half — the store contract against a real database, and the cloud-mode dashboard — point it at
a scratch database:

```bash
pip install -r requirements-cloud.txt          # psycopg; not in requirements.txt
createdb dinkydash_test
DINKYDASH_TEST_DATABASE_URL=postgresql:///dinkydash_test venv/bin/python -m pytest tests/ -q
```

The fixture migrates that database itself, so there is nothing to set up and nothing to tear down.
CI runs it both ways on every push, because the parity assertions only mean something if they
actually run. The tests cover leap years, timezone conversion, event ordering, rotation, staleness
and the config round-trip — the things that break silently — in under a second.

## Apply the schema (cloud mode only)

```bash
venv/bin/python migrate.py --status   # what is outstanding
venv/bin/python migrate.py            # apply it
```

**It does not read `.env`.** That file holds the live cluster under production's own key
`DATABASE_URL_DIRECT`, and a schema tool that loaded it would treat "apply my change" as "apply it
to the running service" — silently, because an up-to-date schema reports the same either way. So
with nothing named it migrates `db.DEV_DATABASE_URL`, this machine's development database and the
one `dev.py` serves — put through `db.on_this_machine` first, because a URL with no host is
redirected by `PGHOST` and a local-looking default is not a local one. `DATABASE_URL_DIRECT` is
used when the *environment* sets it, which on App Platform's pre-deploy job is the only thing set
and on a laptop takes an export; `--database-url` overrides both, and an empty value there is
refused rather than fallen back from.

## Generate a dashboard (needs `ANTHROPIC_API_KEY` in `.env`)

```bash
python generate.py                  # today: fetch the calendars and write the brief
python generate.py --tick           # only what is due now — what cron runs
python generate.py --date 2026-12-24  # any date, for testing
```

`--tick` and `--date` are mutually exclusive: a tick works from the real clock. `--config` also
decides where `dashboard_data.json` and `content_history.json` live, so a scratch config keeps its
generated files beside it.

**Testing without spending money.** `generate.py --date ...` still costs one API call. To exercise
the dashboard with no call, run `python sample_board.py`, which writes a plausible payload for
today. It refuses to overwrite a real one, so delete `dashboard_data.json` first if that is what you
want. Then edit the file by hand — change `generated_for_date` to an older date to see the stale
state, or move it aside entirely to see the dashboard before its first brief.

## Run

```bash
venv/bin/python dev.py              # hosted dashboard + marketing site; Conductor's default run action
python app.py                       # self-hosted app; or: flask run --host=0.0.0.0
FLASK_APP=website.site flask run --port 5001   # marketing site (pip install -r requirements-site.txt)
```

- `dev.py` requires a development `DATABASE_URL` **on this machine** — loopback or a Unix socket; a
  remote database is refused before anything connects, because a workspace's `.env` can carry one —
  and a `DINKYDASH_SECRET_KEY`. Outstanding migrations are applied on start, because that database
  is disposable. Both processes stop together; the launcher always selects cloud mode and refuses
  invalid setup.
- The self-hosted dashboard is at `/`, settings at `/settings`, all three screen sizes at `/preview`.
- The marketing site has no build step and no `docs/` directory: `website/site.py` renders
  `content/*.md` through `website/templates/` on request. Adding a page is "write a Markdown file".

## Docker Compose (self-hosted)

```bash
mkdir -p data
cp config.example.yaml data/config.yaml
docker compose pull
docker compose up -d
```

The web and scheduled-worker services use the same GHCR image and share `./data:/data`.
`DINKYDASH_CONFIG=/data/config.yaml` keeps settings and generated files persistent; the worker runs
`generate.py --tick` every five minutes. `ANTHROPIC_API_KEY` is optional for serving and calendar
refreshes, and is required for daily briefs. Put it in an untracked `.env` file. The image is
published for `linux/arm64` and `linux/amd64` when a GitHub Release is published
(`.github/workflows/publish-image.yml`).

## Local data in a new Conductor workspace

`config.yaml`, `dashboard_data.json` and `content_history.json` are gitignored, so a new workspace
only receives them through Files to copy, which reads `.worktreeinclude` **from the main checkout on
disk** — having it on the branch is not enough. If the main checkout is parked on an old commit that
predates that file, Conductor falls back to its default `.env*` pattern: `.env` arrives, the rest
does not. `.conductor/settings.toml` covers the gap by falling back to `config.example.yaml` and
seeding a sample dashboard, so a workspace always opens on something real. Copied data still wins
over both.

## Ralph loop (unattended implementation)

`scripts/ralph/ralph.sh` runs the same prompt (`scripts/ralph/prompt.md`) in a fresh container until
the ready GitHub issues are done. Each iteration picks one issue whose blockers are closed, builds
it test-first, commits to the current branch and closes the issue. It never pushes and refuses to
run on `main` or with a dirty tree.

```bash
git switch -c feat/household-modules
export CLAUDE_CODE_OAUTH_TOKEN=...   # from `claude setup-token`
export GH_TOKEN=...                  # fine-grained, this repository, Issues read and write
scripts/ralph/ralph.sh once          # one iteration to watch first
scripts/ralph/ralph.sh 10            # then up to 10, stopping on COMPLETE or STUCK
```

The container (`scripts/ralph/Dockerfile`) bakes in Python 3.11, the dev and cloud requirements at
`/opt/venv`, and the Claude Code and GitHub CLIs. It mounts only the checkout. Notes go to
`.ralph/progress.txt` (gitignored). Read the commits and the issue comments before merging.
