# Architecture

Read this when adding a module, moving code between layers or changing the payload shape. The
rules that always apply are in [CLAUDE.md](../CLAUDE.md).

## Self-hosted app

One family runs the dashboard and settings UI on their own machine. Configuration and generated
data live in files through `FileStore`. `generate.py --tick`, normally called by cron or the
Compose worker, refreshes calendars and writes the headline on the household's schedule.
An explicit `DINKYDASH_MODE=cloud` is refused; there is no hosted backend.

The optional parent password protects settings and the dashboard at `/`; a rotating bearer link
lets a screen display the dashboard without a parent session. Phone pages use the same file store.
Keep the service on a trusted network even when sign-in is enabled.

## Engine boundary

```python
generate(config, today, events, recent_notes) -> payload dict
```

`today` is injected, events are fetched by the caller and the payload comes back as data. New
engine code does not consult the clock, read files or exit the process. `store.py` and `config.py`
are the only files under `dinkydash/` that open files.

## Module map

- `dinkydash/config.py` and `store.py`: configuration, household files and atomic writes.
- `dinkydash/calendars.py`, `schedule.py`, `runner.py`: feed fetches and scheduled refreshes.
- `dinkydash/context.py`, `recurrence.py`, `streaks.py`, `activity.py`, `shopping.py`: household
  calculations and list operations.
- `dinkydash/board.py`, `clock.py`: dashboard view and configured time formatting.
- `dinkydash/prompt.py`, `claude_client.py`, `generate.py`: headline generation.
- `web/__init__.py`, `family.py`, `session.py`: app factory, store access and CSRF/session handling.
- `web/routes/`: dashboard, settings, optional sign-in, phone, wall token and activity routes.
- `website/`: a separate marketing site and image generators; not required by the dashboard.

## Storage and payload

The store is passed into the runner and web app rather than cached globally. Its `save_agenda`
accepts only agenda keys and `save_brief` the remaining keys, so one refresh cannot overwrite the
other's work. Settings changes invalidate affected calendar data before a fetch can publish it.
See [the engine guide](../dinkydash/CLAUDE.md) for the locking and cadence rules.

A value recomputable from config and date belongs in `board.build_view`, not the payload. The
payload contains what the generator fetched or wrote. Add refresh-owned fields to
`runner.REFRESH_KEYS` so a brief carries them forward without overwriting them.
