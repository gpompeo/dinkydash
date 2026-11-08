![DinkyDash — the digital family calendar for screens you already own](website/images/social-preview.png)

# DinkyDash

The digital family calendar for screens you already own — a TV, an old tablet, or a Raspberry Pi.

![The DinkyDash dashboard: today's agenda, whose turn each chore is, and the countdowns](screenshot.png)

Website: [dinkydash.co](https://dinkydash.co)

DinkyDash merges your calendars into one agenda, works out whose turn each chore is, counts down to the next birthday, and once a day asks Claude for a headline. Then it puts the lot on a screen at home — light or dark, sized to read from across the kitchen.

## Two ways to run it

**Self-hosted (this repo).** Free and MIT-licensed, runs on your own hardware. Use Docker Compose
on Linux, including a 64-bit Raspberry Pi; the container image is published for `linux/arm64` and
`linux/amd64`. See the [self-hosted Docker quickstart](#quickstart) for setup and run instructions.

> Self-hosting is **community-supported**. Issues and pull requests are welcome, but there's no support commitment — if you need it to just work, use the hosted version.

**Hosted.** [Start a free 14-day trial.](https://app.dinkydash.co/login) No card required. After that it's $39 a year or $6 a month, and nothing is charged unless you choose to subscribe. Built from this same repo, in cloud mode — see [Single mode first](CLAUDE.md#single-mode-first).

## What the dashboard shows

- Today's agenda, in time order, merged from as many Google, Apple iCloud and Outlook
  calendars as you like — anything with an iCal link, pasted in, no account sign-in
- A personal calendar can show only the events shared with your partner, and keep
  work and private appointments to itself
- A look at tomorrow underneath it, on the days today leaves room
- Whose turn each chore is — it moves on with the date, nothing to tick off
- Countdowns to birthdays, holidays and special dates
- An AI-written headline, tied to the day
- Light or dark, chosen in the settings UI

Configure all of it from your phone at `/settings`, or by editing `config.yaml` directly — they are
the same file, and the UI keeps your comments.

## How it works

```
[cron every 5m] → generate.py --tick → every hour by default: re-fetches every iCal feed
                                     → once a day at a time you set, 06:00 by default
                                       (and at once on the first run): calls Claude
                                     → saves dashboard_data.json

[browser]       → web/routes/board.py → recomputes chores, countdowns and today's agenda
                                      → renders the dashboard
```

Only the headline comes from the model. Ages, countdowns, chore turns and the
agenda are recomputed on every render, so if a day's run fails the times and turns on the wall
are still today's — the headline is one worked out from the day, and the dashboard says so.

---

## Quickstart

Self-host the app with Docker Compose on a Linux host, including a Raspberry Pi with a 64-bit OS.
The published image supports `linux/amd64` and `linux/arm64`.

```bash
git clone https://github.com/gpompeo/dinkydash.git
cd dinkydash
mkdir -p data
cp config.example.yaml data/config.yaml
docker compose pull
docker compose up -d
```

Open `http://<host-lan-address>:5000` for the dashboard or `/settings` to configure it from
your phone. Compose mounts `./data` at `/data`; the configuration and generated dashboard/history
files stay there across container replacements. The settings UI edits the same `data/config.yaml`
file.

The dashboard, calendar refreshes, chores and countdowns work without an Anthropic key. The daily
headline/brief requires one. To enable it, create a local `.env` file (already gitignored) containing
`ANTHROPIC_API_KEY=your-key`, then restart the services with `docker compose up -d`. The key is
passed to the containers at runtime and is not included in the image.

Every five minutes, Compose checks whether it's time to update the dashboard: calendars refresh
hourly by default and the brief is written once daily at 06:00 in the configured timezone. The
first brief is generated as soon as the family configuration is set up. Change these settings in
`/settings` or in `data/config.yaml`.

The GitHub release workflow publishes the version-tagged image and `latest` to
[GitHub Container Registry](https://github.com/gpompeo/dinkydash/pkgs/container/dinkydash) for
both architectures. After the first release, set the GHCR package visibility to **Public** in
GitHub's package settings if it was created as private; public access is needed for an
unauthenticated `docker compose pull`.

The getting-started guide has provider-specific directions for finding Google, iCloud and Outlook
iCal links, plus Raspberry Pi kiosk/screen setup.

> **There is no login.** The dashboard and the settings UI are both served without authentication, so
> anyone who can reach the port can read your family's agenda and rewrite `config.yaml` — names,
> birthdays, and every calendar link in it. The Compose port is published on the host's network
> interfaces: allow access only from your trusted LAN using the host firewall, and never forward
> port 5000 or expose it directly to the public internet.
>
> That is deliberate rather than unfinished: DinkyDash is a config file with a web form on it, and
> the file has no login either. It assumes it is on your home network, the same as a printer.
>
> **So keep the port off the public internet.** Do not forward port 5000 on your router. If you need
> it from outside the house, reach it over a VPN such as [Tailscale](https://tailscale.com) or
> [WireGuard](https://www.wireguard.com), or put a reverse proxy with basic auth in front of it.
>
> Hosted mode is a different matter — it authenticates every request and is scoped per family. See
> [Hosted mode raises the stakes](CLAUDE.md#hosted-mode-raises-the-stakes).

---

## Documentation

| What you want | Where it is |
|---|---|
| Self-host with Docker Compose | [Quickstart](#quickstart) |
| Find calendar links and set up a Raspberry Pi screen | [dinkydash.co/getting-started](https://dinkydash.co/getting-started/) |
| Every config key, with comments | [`config.example.yaml`](config.example.yaml) |
| Living with it: the daily cycle, the two buttons, what to check when something looks wrong | [`doc/running-it.md`](doc/running-it.md) |
| Coming from an older version | [`doc/upgrading.md`](doc/upgrading.md) |
| Working on the code, and how the hosted build shares it | [`CLAUDE.md`](CLAUDE.md) |
| Product terms and UI wording | [`doc/terminology.md`](doc/terminology.md) |

The install and Pi guides live on the website rather than here, so there is one copy of each
to keep right.

## Local hosted development

Conductor's **dev** run action starts the hosted dashboard and marketing website
together. The same command outside Conductor is `venv/bin/python dev.py`.
See [local development](doc/development.md) for the required development database
and session key, ports, sign-in, and how Conductor picks up the run configuration.
The self-hosted quickstart above is unchanged.

## Running the tests

```bash
pip install -r requirements-dev.txt   # adds pytest and the website build; not needed on the Pi
python -m pytest tests/ -q
```

The suite runs in seconds. It covers leap years, timezone conversion, event ordering, chore
rotation, the stale-dashboard logic, the config round-trip, and the settings routes that write it.

GitHub Actions runs the same command on every push and pull request, on Python 3.11
(`.github/workflows/test.yml`), alongside a [gitleaks](https://github.com/gitleaks/gitleaks) scan of
the full history. Every requirements file is pinned with `==`, so a clean `pip install` gets the
versions CI passed on. A pull request that fails either check shows a red X.

## Key files

| Path | Purpose |
|------|---------|
| `dinkydash/` | The engine. Pure functions plus the model call — no clock, no file reads |
| `dinkydash/context.py` | Ages, birthdays, countdowns, chore rotation |
| `dinkydash/calendars.py` | iCal fetch, parse, recurrence, merging feeds |
| `dinkydash/board.py` | Turns config + payload into what the dashboard renders |
| `dinkydash/runner.py` | The two halves of the cycle: `refresh_calendars` and `write_brief` |
| `dinkydash/schedule.py` | `due()` — which of the two the clock and the config owe right now |
| `dinkydash/store.py` | Where the config, the dashboard and the note history are kept |
| `migrations/` | The hosted schema, plain SQL. Self-hosting needs none of it |
| `web/` | Flask app — dashboard, settings UI, templates |
| `web/templates/board.html` | The dashboard itself, light and dark, all screen sizes |
| `generate.py` | Command-line skin over `dinkydash.runner` — this is what cron calls |
| `app.py` | Flask entry point |
| `config.yaml` | All configuration. The settings UI writes this same file |
| `config.example.yaml` | Template config, documenting every key |
| `tests/` | The test suite. Run it before committing |
| `doc/` | Running it day to day, and upgrading from an older version |
| `design/` | Mockups for the dashboard and settings UI, with the reasoning |
| `.env` | `ANTHROPIC_API_KEY` (not in git) |
| `.env.example` | The template for it — copy to `.env` |
| `.github/workflows/test.yml` | CI: pytest and gitleaks, on every push and pull request |
| `.gitleaks.toml` | Secret-scanning rules, including one for iCal secret addresses |
| `dashboard_data.json` | The generated payload (not in git) |
| `content_history.json` | A rolling record of the last 30 days' runs (not in git) |

## Contributing

Pull requests are welcome. The codebase is one monorepo serving both the self-hosted and the hosted build, so a change has to work in both modes — read [CLAUDE.md](CLAUDE.md) before starting anything structural, and open an issue first for larger changes.

Known rough edges are listed under "Known issues" in [CLAUDE.md](CLAUDE.md).

## License

MIT — see [LICENSE](LICENSE).
