# The dashboard and the settings UI

Guidance for `web/`. The root `CLAUDE.md` holds the rules that apply to every change; this
file holds the ones that only bite here. Sizing conventions are in the root under
**Conventions** — this is the reasoning behind them and the traps in measuring them.

## Adding to the settings UI

**Adding a field to a settings section.** Add a tuple to the section's `fields` list in
`web/routes/settings.py` — `(name, label, kind, required, help)`. The list template and the edit
form both render from it, and `parse_field` reads it back. `kind` is one of `text`, `url`, `date`,
`monthday`, `textarea`, `checkbox`, `emoji`, `color`, `people`, `emails`, `recurrence`, `assignment` (the last two are the task editor's radios, in `settings/_task_rules.html`, read back by `dinkydash/taskform.py`). A new `kind` needs a
branch in `parse_field` and a branch in `web/templates/settings/edit.html`; nothing else.

**Validation errors belong to fields.** `validate` maps field names to messages. The editor links
an error summary to each control or fieldset, focuses the summary, and connects inline errors
with `aria-describedby` and `aria-invalid`. Grouped controls use legends; date parts and colour
choices also have individual names. Annual dates validate through `context.parse_monthday`,
which accepts 29 February but rejects impossible combinations. Invalid stored dates remain
editable in settings and are omitted from countdowns until repaired.

**A chore owns its participant order.** Render saved choices before unselected people and submit
them in that order. Reordering People or chores must not change it. The rotation picker moves
checked inputs in the DOM; without JavaScript, its update/move buttons redisplay the submitted
draft. Only Save persists it. Keep an initial hidden Save button so Enter still saves.

**`date` means a date of birth, and it is bounded.** The input carries `min` and `max` of
1900-01-01 and today, and `validate` refuses anything outside them, naming the year it received.
Both halves are needed: a phone's year wheel scrolls down to the year 1, and without the server
check a mistyped year would show up on the People page as somebody 2,009 years old. A `date`
field that is not a birthday needs a kind of its own rather than a looser bound on this one.

**The `emoji` kind is a row of quick picks, None, and a dialog with the rest.** The row is
plain radios; the dialog is `settings/_emoji_picker.html` plus `web/static/emoji-picker.js`,
drawn once after the form (so Enter in its search box cannot press Save, and nothing in it
carries a `name`) and filled on first open from `web/static/emoji.json`. That list is
hand-maintained: nine groups, each entry `[emoji, Unicode's short name, search words]`, the
search words being British spellings and what a family calls things ("football", "biscuit",
"bins", "bonfire night"), and **nothing newer than Emoji 13.1**, so a Pi's Noto Color Emoji
draws all of it. `tests/test_emoji_picker.py` checks the shape, that nothing is in twice and
that every quick pick is in it. A choice lands in the field's `-own` radio — always in the
markup, hidden while empty — or ticks the quick pick it matches, ignoring the variation
selector, so "🍽️" from the list saves as the "🍽" the quick pick already had. The search box
also takes an emoji typed on the phone's own keyboard, which is how anything not on the list
gets in. Without the script, "More…" stays `hidden` and the row is what it always was. Server
side, `web/emoji.py` checks the *shape* of one emoji — a pictograph from Unicode's
`Extended_Pictographic` ranges (reserved space included, so next year's emoji pass), with an
optional variation selector and skin tone or tag flag, or a keycap, or a two-letter flag,
joined by zero-width joiners, ten code points at most — and `validate` answers anything
else, "🐶🐱" and "!!!" and "日本語" included, with "Choose one emoji." The standard library
cannot split graphemes, which is why the grammar is written out rather than counted. The
browser applies the same grammar before offering what was typed (`looksLikeEmoji` in
`emoji-picker.js`), so the dialog never offers what Save would refuse: change one, change
the other, and `tests/test_emoji_picker.py::TestOneEmoji` is the table to keep them honest
against.

**Adding a whole settings section.** Add an entry to `SECTIONS` and a row to
`web/templates/settings/home.html`. The list, edit, delete and reorder routes are generic and need
no changes.

**Renaming a section's URL.** Keep the old name in `LEGACY_SECTION_NAMES` in `web/routes/settings.py`.
It resolves to the current name before the view runs, so forms already open on a screen still
post to it, and the feature switch, sign-in guard and CSRF check are the ones the current URL has.
Never redirect a legacy POST: it would drop the form or write twice.

**Edits stay protected until Save.** Mark editable forms with `data-dirty-guard` for the shared
`settings.js` navigation warning. Set it to `changed` when redisplaying an unsaved draft after
a calendar test or validation error. Only dirty forms attach `beforeunload`, so unchanged pages
remain eligible for Firefox's history cache. Custom controls that change submitted values must
emit a bubbling `input` or `change` event, including chore reordering.
Destructive forms use a named `data-confirm` prompt and
an empty `confirmed` field; the server must also require `confirmed=yes` and otherwise render
`settings/confirm.html`, so confirmation works without JavaScript. Home actions use `data-pending`
for the shared waiting dialog; keep their submit buttons unnamed so disabling them preserves the
POST body. The operator page overrides the interactions block to remain script-free.

**Every control has a hover, a press and a keyboard state, and a new one needs all three.** They
live at the foot of the shared sheet in `settings/base.html`. Hover rules sit behind
`@media (hover: hover)` — on a phone a hover is a tap that never ends, left glowing on the row
you just came back from — while `:active` and `:focus-visible` apply everywhere. The cue is one
the mockups set with `a:hover`: filled things darken, bare things get `--warm` or `--tint` behind
them, links underline, and nothing changes size. **An inline `style` on a button beats every one
of those rules**, which is why "Not now" and "Delete my account" became `.btn.quiet` and
`.btn.danger.fill` rather than keeping theirs; a new look for a button is a variant, not an
attribute. Two more things a pointer expects: `.btn:disabled` looks disabled and refuses the
cursor, and on a list page the link stretches over the whole row (`a.row-main::after`), so the
avatar and the pill open the item the way the home page's rows already did; anything that must
stay its own target inside a row sits above it the way `.move` does.

**The feedback pill is offered only when `web.feedback.enabled()` finds a mail key.**
The route composes one message to `feedback.recipient()` via SendGrid. The message is never
logged, and `doc/self-hosting.md` must describe this optional flow.

**A route gets its store from `web.family.current_store()`.** It returns the `FileStore`
configured for this app. The optional parent sign-in and wall token guard routes separately;
the token is a bearer credential and must be redacted from access logs.

**The app bar lives in `settings/base.html`.** Pages set `back_href` and `back_label` for
the back link; the heading reuses the `title` block. Settings home and sign-in pages override
`appbar` for their branded headers. Save belongs at the end of the form. Keep an initial
hidden Save button before "Test calendar link" so Enter saves.

**Every form that writes needs one hidden field.** `<input type="hidden" name="csrf_token"
value="{{ csrf_token() }}">`, right inside the `<form>`. `csrf_token()` is a Jinja global set up by
`web/session.py`, so no route has to remember to pass anything — but a form without the field is a
400, and the CSRF tests walk the templates and fail on one. There is
deliberately no switch to turn the check off; the test client in `tests/conftest.py` fills the field
in the way a browser does.

**The settings home has two personalities**, decided by `web/setup.py`. Until the family is set up
and its first dashboard written, the top of the page is a checklist — who lives here, time zone, a
calendar, the screen — and the daily controls (Refresh calendars, View dashboard, Rewrite daily headline) are not
offered at all; after that it is the day's status card. Invented example people and pets carry
`invented: true`. Saving an item clears its mark. `config.is_set_up` gives the same answer to the
page and to the tick. The time
zone step reads the phone's own zone with `Intl.DateTimeFormat` and offers it as one tap to
`POST /settings/timezone`, which refuses any name `zoneinfo` does not know.

**The settings shell** is shared by the settings pages and parent sign-in. The dashboard is
outside this shell. `web.feedback.enabled()` gates the optional feedback route on its mail key.

## The dashboard's layout

**Changing the dashboard layout.** Everything is sized in `rem` off one root value, so check all three
sizes at `/preview` rather than just the one you are looking at.

That root value is *measured*, not guessed. The script at the foot of `board.html` binary-
searches the largest `html { font-size }` whose content still fits the viewport, capped at
`min(120px, innerHeight / 9)`. A quiet day therefore grows until it fills the screen. A busy
day shrinks only as far as a readable floor (13px). If it still overflows there, the script
hides one thing at a time — locations (`.tight`), then tomorrow (`.drop-tomorrow`), then
the furthest countdown, then the last of today's events — and searches again afterwards so
the type can grow back. **A step is kept only if the page comes out shorter.** In two
columns the taller column sets the height, so a row taken from the shorter one frees
nothing and only leaves a gap: today's events are never hidden to make room for the side
card. The first event and the nearest countdown always stay. Today's hidden events are
removed whole and counted on a `+N more` line. When no step helps, the type goes below
the floor instead. Labels never go below 12px (`max(0.82rem, 12px)`). On a panel shorter
than 520px, tomorrow's addresses are hidden even when the day otherwise fits, because a
wrapped address is what pushes a short panel over. The CSS `clamp()` is the no-JS fallback
and is deliberately smaller. Because `body` is `height:100vh;overflow:hidden`, nothing ever
reports an overflow — so the script lets the page lay out freely for one measurement
(`height:auto`) and puts it straight back.

**The same script is what refreshes the dashboard, and it never reloads the page** (DIN-60). Every
`view.reload_seconds` it fetches `location.href`, parses the copy, and swaps the `<body>` in — then
re-fits, because the content changed. A copy that does not arrive (the fetch fails, times out at
30 s, comes back 5xx, or is not a dashboard at all) leaves the last good one on the wall, shows the
`.offline` badge — "Reconnecting · Last updated 08:20", or "Showing Thursday's dashboard" once the
day in `data-today` is over in the family's `data-timezone` — and tries again in a minute. A 4xx or
a redirect is a deliberate answer (the link was rotated, a session ended) and gets a real reload, so
the server's own page shows the way it always did. **A swap keeps the `<head>`**, and with it the CSS,
the fonts and the script itself, so the body carries `assets.board_version()` — a hash of the
dashboard's templates and font files — and a copy whose version differs is a deploy and gets a real
reload too, at the one moment that is safe: a copy has just arrived. The 30 s deadline is a promise
raced against the attempt, not only an abort, because older WebKit cannot abort a fetch and a
request that stalls would otherwise hold the in-flight guard for ever; the guard is time-based for
the same reason. The `<meta http-equiv="refresh">` survives only
inside `<noscript>`: a browser running the script must never see it, or the two race and the tag's
reload lands the error page the script exists to avoid. `tests/test_board_refresh.py` pins that
contract; the swap and the badge themselves are checked in a browser, below. The same fetch
sends `X-Viewport` (CSS width, height and `devicePixelRatio`) unless the page is framed, and
`/s/<token>` stores it; the first navigation sends no header. What this does *not*
cover is a reboot while offline — the browser then has nothing to show, and only a service worker
would change that, which DIN-60 keeps open.

**Nunito is served from `web/static/fonts/`, not from Google**, as one variable font per subset
(`nunito-latin.woff2`, `nunito-latin-ext.woff2`, covering weights 200-1000 so every weight the dashboard
asks for comes out of one download). `web/templates/_fonts.html` holds the `@font-face` rules and the
reasoning, inline in every page's head with a preload of the Latin file — a stylesheet cost each page
one more round trip before the font could start; the files are byte-for-byte what Google was serving, so the metrics did not change; what
changed is that a screen at `/s/<token>` no longer tells Google that URL, and a Pi with no internet
renders the same dashboard rather than falling back to a system font.

**Inter sets the headlines**, from the same folder and preloaded the same way:
`inter-latin.woff2` and `inter-latin-ext.woff2`, cut down from the published variable font to
weights 500-800 with the optical-size axis kept, so a large heading draws Inter's tighter display
cut. It is the dashboard's headline and waiting screen; in settings, the app bar title,
`.card-title` and dialog headings. Large Inter wants negative tracking (about -0.03em at headline
sizes, less as it gets smaller). The `PompDash` wordmark stays in Nunito (`h1.wordmark`), as the
settings app bar does. Body text, times, chores and countdowns are Nunito. Cutting it again needs
`fonttools`, which is a tool run once on a laptop, not a dependency:
`instantiateVariableFont(font, {"wght": (500, 800)})`.

**One theme, one palette file.** `theme` in `config.yaml` (`light` or `dark`; missing or unrecognised
is dark, via `config.theme_of`) sets `data-theme` on `<html>` for the dashboard, the settings shell
and the phone page, and `web/templates/_theme.html` is the only place a template names a colour:
Tokyo Night for dark, Tokyo Night Day for light. Settings pages get `theme` from a context
processor in `web/__init__.py`; the dashboard gets it from `build_view`. A new colour is a token
defined in both themes there; `tests/test_theme.py` fails on a literal elsewhere, on a token
missing from either theme, and on text or control colours below contrast (4.5:1 text, 3:1 edges).
`THEME_COLOURS` in `config.py` repeats each `--bg` for `theme-color` and the manifests; the test
keeps them equal. The theme picker previews each theme with a nested `data-theme`.

**Depth is gradients and shadows, never blur, on the dashboard.** The page is a faint radial
gradient, the side column and the empty-day box are raised cards (`--card`, `--card-edge`,
`--card-lift`), and the chore pills carry a sheen and an inset edge. Every one of them is a token
with a dark value beside the light one. A Pi paints a gradient or a shadow once and leaves it;
`backdrop-filter` it repaints, which is why only the settings app bar uses it.

It re-fits on `document.fonts.ready` as well as on resize, and that is not optional. Nunito and Inter arrive
after the first paint and sets taller lines than the system fallback, so a size measured before it
lands can overflow once it swaps in — measured at 557px of content in a 480px panel. The dashboard only
looks right because it re-measures when the font arrives.

**The agenda's time column is a token, because a family can choose a 12-hour clock.** It does not
shrink, so it is sized for the widest time that clock can write — `--time-column`, 5.2rem for
`12:00` and 7.35rem for `12:00` plus a smaller `pm`, selected by `data-clock` on `<html>` beside
`data-theme`. The suffix is a `<span class="meridiem">` at 0.65em; at full size it is wider than
the column and wraps under the digits, which is the gap beside the title. Twelve-hour times are
right-aligned in that column, so a one-digit hour ends on the same edge as `12:00`. Tomorrow's
type is 1.28rem against today's 1.9rem, and its column is `calc(var(--time-column) * 1.28 / 1.9)`,
so the footnote does not keep a gap sized for the larger row. **`data-clock` is on `<html>`, which a refresh keeps**, so `swap()` carries it across by
hand the way it already did the theme; forget that and a family who changes the setting gets the new
times in the old column until something forces a real reload. The times themselves are written in
`dinkydash/clock.py` — see the root `CLAUDE.md`. The span is added in the dashboard template only.

**The agenda's row budget.** `MAX_EVENTS = 5` is the budget for the whole agenda, not today's cap.
Today fills it first; tomorrow tops up whatever is left, capped again at `MAX_TOMORROW = 3` so it
stays a footnote even on an empty day. A five-event day therefore renders exactly as it did before
tomorrow existed. This is what "if there is space" means in code — a fixed row count, decided by a
pure function, rather than a layout measurement. The fit script may still hide tomorrow, or the
tail of today, when a short panel cannot hold the rows that budget already allowed.

What those rows cost depends on which column is taller, so measure against a real config rather
than `config.example.yaml`. In two-column mode the side column (chores plus countdowns) usually
sets the page height, and the agenda grows into slack it was already wasting. On a config with
three chores and four birthdays the 800x480 root moves 14.23px -> 14.10px on a three-event day —
under 1% — and 14.23px -> 13.32px on a quiet one. The two-chore example config has a shorter side
column, so there the agenda *is* the constraint and the same change costs 8% and 13%. The stacked
single-column layout (an iPad in portrait) has no side column to hide behind and always pays the
full price, around 13-18%. Everything fits at all three sizes in every case. Raising either
constant spends more type size, so measure at `/preview` before you do.

**There is no waiting screen.** Before the first brief the view is in state `first`: the
dashboard itself, with turns, countdowns and agenda worked out from the config, under a headline
worked out from the day, and no banner because no line is late. That holds while the family is
still setting up, which is what lets the settings home preview the dashboard from the first second.
It refreshes every minute rather than five, so the model's line reaches the wall soon after
[Two cadences, one tick](../dinkydash/CLAUDE.md#two-cadences-one-tick) writes it.

In two-column mode the body is a grid of agenda and side column, and both stretch to the
height left under the headline. The breakpoint is `min-aspect-ratio: 5/4` and `min-width:
640px`, so a 4:3 landscape tablet stays in two columns and a portrait tablet stacks the
side column under the agenda. An empty today puts `day-empty` on `.body` — a class, because
`:has()` is not in the oldest browser this page still lays out in — and that row gives the
side column the wider share (`1fr` / `1.8fr`), which is what keeps a countdown on one line
inside the side card's padding. The columns are `1.8rem` apart rather than wider because the
card's own edge separates them.
The empty box is `flex: 0 0 auto`, the height of its words, so tomorrow sits under it. Stacked, each column's flex basis is its content height and
leftover space is shared — a zero basis would split that page by ratio and let the side
column shrink shorter than its text. There is no note on the dashboard. Long event titles,
chore pills and countdowns wrap (`overflow-wrap: break-word`, `min-width: 0` on the flex item).

## Dashboard pages and screen setup

`dinkydash/pages.py` is the registry (`REGISTRY`, `available(config)`) and the pure parsing of a screen's
setup from its link (`mode`, `page`, `rotate`, `every`; `link_query` writes it back). Nothing is stored on
the server: the link is the setup, so screens cannot affect each other, and the touch screen's rotation
switch is kept in that browser's `localStorage` (`pompdash.rotate`). A new page is a `Page` appended to
`REGISTRY` with a `template` partial; every available page renders as a hidden `body > section[data-page]`
and `board.html`'s script shows, rotates and restores them across a refresh swap. `fit()` returns early
while the main page is hidden, so a page sized to its own needs must do its own fitting. With one page
nothing extra is drawn. The pager is a flex strip under the board, no `gap` (Safari 12 test), margins only.
Tests: `tests/test_pages.py`, `tests/test_board_pages.py`, `tests/test_board_pages_browser.py`.

The **week page** (`_week.html`, `board.week_view`) is the first registered page: seven columns, read-only,
available while a calendar is switched on. Its columns are fixed by the screen, so `fitWeek()` in `board.html`
hides trailing events of a column that overflows and counts them in its `+N more`; it runs from `fit()`'s
early return while the main page is hidden. It leaves locations off and sizes in `rem` like the rest.
Tests: `tests/test_week.py`, `tests/test_week_browser.py`.

## Phone page, wall token and sign-in

`web/parent.py` holds the optional sign-in (`enabled()`, `guard()`, the attempt limiter); the settings
blueprint and `/` both call it. `routes/phone.py` serves `/h` (name picker, then `/h/<tab>`, which 404s
while its feature is off) and `POST /h/tick`; `routes/wall.py` serves the wall at `/s/<token>`, only
registered when a password is set. Each has its own `changes` route returning the change counter, and
the board script polls it every 15 seconds. Every writing route checks CSRF and the access rule first.
Task editor radios need no JavaScript (`settings/_task_rules.html`).

## Home screens and manifests

**Saving a page to a home screen.** `/` and `/settings/` each serve their own web app manifest
(`web/manifest.py` holds what they share), so a saved link gets the mark and a name instead of a
URL — the dashboard full screen for a tablet used as the panel, the settings UI standalone on a phone.
They must keep **different `id`s**: share one and the phone treats them as a single app, so saving
the dashboard would replace the settings icon. iOS reads none of the manifest; its icon and label come
from the `apple-touch-icon` link and `apple-mobile-web-app-title` in the page head, which is why
both are set on both pages. The PNGs in `web/static/` are drawn by `scripts/generate_icons.py`,
which renders the same mark as the favicon at every size the app needs — the outputs
are committed, so Pillow stays out of `requirements.txt` (it is declared in `requirements-dev.txt`).
**Editing `favicon.svg` means re-running that script**, or the PNGs keep serving the
old mark. The settings page offers this once and
remembers a "Not now" in `localStorage`; it hides itself when already running from a home screen.
Note that Chrome's own install prompt needs https, so on a home network it never fires and the
written steps are what people see.

**"View dashboard" opens the dashboard in its own tab, and so does the "Dashboard" link beside it.** The dashboard
is the wall panel: full screen, no link out, and it reloads itself for years. Opened in the same tab
from a settings page saved to a phone's home screen it was a dead end — a saved web app has no
address bar and, on an iPhone, no Back button, so the way out was to force-quit the app; and in a
Safari tab every self-reload adds a history entry, so Back needed one tap per reload spent looking.
Its own tab is a way back the dashboard never has to draw: a tab to close, an in-app sheet with Done on
iOS, a custom tab with an X on Android. **Do not answer this with a Settings control on the dashboard.**
A tablet set up in the same tab would keep it on the wall, because the reload keeps the URL. `tests/test_settings.py` asserts the tab and the dashboard's lack of a way back.

## Static files, and moving between pages

**Every static URL goes through `static_url()`, never `url_for('static', ...)`**.
`web/assets.py` puts the file's content version on the URL — `?v=` and twelve hex digits of its
SHA-256 — and answers a request carrying the
current version with a year of `Cache-Control` and `immutable`. A bare URL, or one with the version
from before a deploy, keeps Flask's `no-cache`. That is the whole difference between a tap that
draws at once and one that asks the server about the font first: Flask's default made every
navigation pay for the stylesheet and then the font again, one after the other, after the page.

**A static response carries no session.** `web/session.py` skips `save_session` for the static
endpoint, because Flask re-signs a permanent session on every response and marks the response
`Vary: Cookie` — and a font that varies on a cookie whose value changes with every page is one no
cache can ever match. Put a cookie on a static response and the year silently stops working.

**The settings shell crossfades between pages and renders the next one early.** Both live in
`settings/base.html`, and browsers that do not know them ignore them. `@view-transition
{ navigation: auto }` turns the cut into a 150 ms fade (Chrome 126+, Safari 18.2+). The
`speculationrules` block has Chrome (121+) fetch and render whichever `/settings/` link the pointer
hovers or a finger touches down on, so the tap lands on a page that is already there. **Every page
under `/settings/` is a read on GET, and has to stay one**: a prerender runs the page. A link that downloads or writes on GET must be excluded from prerendering. Forms are not links and are never
speculated. The dashboard is outside the pattern on purpose: it reloads itself, and `/preview` renders
it three times over.

## Measuring the dashboard

Everything below is about *checking* a layout change, and every line of it was learned the
hard way.

- **Headless Chrome lies about the viewport.** `--window-size=800,480` renders into 800x393 — 87px
  short — while `--screenshot` still writes an 800x480 PNG, so the bottom fifth looks empty when it
  is simply not there. Add 87 to the height you want (`--window-size=800,567` gives a true 480), and
  confirm it by reading `window.innerHeight` out of the page rather than trusting the flag. Chrome
  also reuses a running instance unless each run gets its own `--user-data-dir`, which silently
  makes every size in a loop return the first one's numbers.
- **Do not trust `--window-size` for layout work at all.** Even with the +87 correction it has been
  seen to ignore the flag and report a 756x469 viewport, which silently puts the dashboard on the wrong
  side of the `3/2` media query. Size the page with an **iframe of exactly the target dimensions**
  instead, the way `/preview` already does, and read the numbers out of `iframe.contentWindow`. That
  is deterministic; the flag is not.
- **Headless Chrome's `--screenshot` and `--dump-dom` hang until the timeout**, though they do
  write their output first. This used to be blamed on the dashboard's `<meta http-equiv="refresh">`;
  that tag now sits inside `<noscript>`, and on 11 September 2026 the Playwright-cached Chromium
  build hung just the same on `/healthz`, a page with no script and no tag. So it is the tool, not
  the page: always wrap the call in `timeout`, and prefer a driven browser (below) for anything that
  has to wait for something.
- **Checking the refresh needs a browser and a clock you control.** The script's timer is five
  minutes; Playwright's `page.clock.install()` and `fastForward()` fire it on demand, and
  `page.route()` can refuse, 503 or 404 the fetch to walk every branch — the memory note on
  scripted Playwright checks has the cached Chromium and the `NODE_PATH` to use.
- The honest check is `scrot` over SSH on the Pi itself: a real 800x480 panel, a real kiosk browser,
  no capture artifacts. The dashboard refreshes itself every 5 minutes on a default config, so a
  change takes one refresh to appear — check `refresh_minutes` before concluding it did not work.

## The change counter

`/changes` (wall) and `/h/changes` (phone) return `FileStore.change_token()` as a bare number, `no-store`, with the access rule of the page they serve (`board.change_counter` is the shared body). The board script polls it every 15 seconds, skips while `document.hidden`, polls at once on `visibilitychange`, and calls the existing `refresh()` when the number moves; a failed poll is silent. It polls only when `<body data-changes>` is set, which `render_board` does for stores that have `change_token`. The token page (#4) must pass its own `changes_url`.
