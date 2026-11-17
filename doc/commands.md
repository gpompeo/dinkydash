# Commands and workflow

Read this when setting up a checkout, running the app, generating a dashboard
or working in a new Conductor workspace. Local development (port overrides,
Conductor configuration) is in [development.md](development.md).

## Setup (Python 3.11+)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest and Pillow; not deployed to the Pi
cp config.example.yaml config.yaml
```

## Tests

Run before every commit:

```bash
venv/bin/python -m pytest tests/ -q
```

CI runs this self-hosted suite on each push and pull request. No database is required.

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
venv/bin/python dev.py              # dashboard on loopback
python app.py                       # dashboard; or: flask run --host=0.0.0.0
```

The dashboard is at `/`, settings at `/settings`, and screen-size previews at `/preview`.

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

The container (`scripts/ralph/Dockerfile`) bakes in Python 3.11, the development requirements at
`/opt/venv`, and the Claude Code and GitHub CLIs. It mounts only the checkout. Notes go to
`.ralph/progress.txt` (gitignored). Read the commits and the issue comments before merging.
