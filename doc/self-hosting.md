# Self-hosting PompDash

From nothing to a working family dashboard: first on your own computer, then as a wall screen on a
Raspberry Pi that boots into it and keeps itself up to date. It uses a terminal.

Docker Compose is the shortest route and is in the [README quickstart](../README.md#quickstart).
This guide is the same app run without containers, plus the Raspberry Pi kiosk setup. Day-to-day
running is in [running-it.md](running-it.md).

You don't need an Anthropic API key to try it: step 3 of part 1 shows the dashboard with a canned
headline. You only need a key for the headline written each day.

## What you need

- **Python 3.11 or newer.**
- **One or more calendar links** in iCal format. Google Calendar, Apple iCloud Calendar, Outlook and
  Cozi all give you one; the steps are in [calendar-links.md](calendar-links.md). Treat the link
  like a password: anyone who has it can read that calendar.
- **An Anthropic API key** ([get one here](https://platform.claude.com/settings/keys)), only for
  the daily headline.
- **A screen.** A Raspberry Pi 4 with 2GB of RAM and the official 7-inch display (800x480) is the
  easy path; see [the hardware notes](#hardware-for-a-raspberry-pi-screen). The dashboard is a web
  page, so an old tablet, a smart TV or a Fire TV that can open a URL will show it too.

## What leaves your machine

- **Calendar feeds** are fetched from the links you paste in. Nothing signs in to an account.
- **The daily headline** sends the Anthropic API the family name and location, each person's
  name, age and interests, pet names, today's event titles, times and locations, the next few days'
  event titles, today's tasks and the countdowns (`dinkydash/prompt.py`). Without
  `ANTHROPIC_API_KEY` the run is refused and nothing is sent.
- **The week page** shows events from earlier in the current week, so the calendar fetch
  reaches back to the first day of your week. Those earlier events are stored in the dashboard
  file on your machine and drawn on the wall; they are never added to the headline prompt, which
  carries today's events and the next few days' titles only.
- **Feedback** from the settings page exists only if `SENDGRID_API_KEY` is set. It goes to
  `DINKYDASH_FEEDBACK_TO`, or to the default support address in `dinkydash/mail.py` when that is
  unset. See [security.md](security.md).

Everything else, including `config.yaml`, the generated dashboard and your completions, stays in
the files on your machine. A screen's page setup (touch or not, first page, rotation) lives in the
link that screen opens, and the rotation switch on a touch screen is remembered in that browser's
own `localStorage`; neither is sent anywhere or written to the server.

## Part 1: run it on your computer

### Step 1: Get the code

```bash
git clone https://github.com/gpompeo/pompdash.git
cd dinkydash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The `venv` is a private folder for PompDash's Python packages, so they do not touch the rest of your system. Recent Raspberry Pi OS and macOS both block installing packages without one.

### Step 2: Make your config

```bash
cp config.example.yaml config.yaml
```

`config.yaml` is the single source of truth. You can edit it by hand now, or leave it and do everything from the settings page in step 5 — they write the same file. A typical config looks like this:

```yaml
family_name: "The Wilsons"
timezone: "Europe/Berlin"     # decides when "today" rolls over
location: "Berlin, Germany"   # optional, gives the headline a sense of place
theme: dark                   # or light

calendars:                    # as many as you like; merged into one agenda
  - label: "Alice's calendar"
    url: "https://calendar.google.com/calendar/ical/you%40gmail.com/private-xxxx/basic.ics"
    enabled: true

people:
  - id: alice
    name: "Alice"
    date_of_birth: "2015-03-15"
    avatar_emoji: "🦖"
    avatar_color: purple
    interests: "drawing, dinosaurs"
  - id: bob
    name: "Bob"
    date_of_birth: "2017-06-20"
    avatar_emoji: "⚽"
    avatar_color: blue
    interests: "lego, football"

pets:
  - name: "Buddy"
    type: "dog"
    avatar_emoji: "🐕"

tasks:                        # people are named by their id
  - title: "Set the table"
    emoji: "🍽"
    recurrence: {kind: daily}
    assignment: {mode: rotate, people: [alice, bob]}
  - title: "Feed Buddy"
    emoji: "🦴"
    recurrence: {kind: daily}
    assignment: {mode: rotate, people: [bob, alice]}

special_dates:                # repeat every year, so no year to set
  - title: "Christmas"
    emoji: "🎄"
    date: "12/25"
  - title: "Summer holidays"
    emoji: "☀️"
    date: "07/01"

claude_model: "claude-haiku-4-5"
max_tokens: 1024
```

The example URL above is deliberately fake. Paste your own iCal address in its place — [calendar links](calendar-links.md) has the steps for Google, Apple, Outlook and Cozi. Add one calendar entry per person, and they all merge into a single agenda.

### Step 3: See the dashboard with no API key

You can look at the real dashboard before you get an API key. This costs nothing and calls no service:

```bash
python sample_board.py     # writes a dashboard for today, with a canned headline
python app.py              # starts the server
```

Open **http://localhost:5000**. The chore turns, ages and countdowns are computed from the `config.yaml` you just wrote, so edit it, reload, and you see your own family. Only the headline is fake. `sample_board.py` refuses to overwrite a real dashboard, so it is safe to leave in place.

Stop the server with `Ctrl+C` when you are done looking.

### Step 4: Add your Anthropic API key

The headline comes from the Claude API. Create a file called `.env` in the project folder:

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

`.env` holds the key and nothing else. The key never goes in `config.yaml`, because that file is meant to be shared and edited.

### Step 5: Generate the real dashboard and run it

```bash
python generate.py        # fetches calendars, calls Claude, writes today's dashboard
python app.py             # starts the server
```

Now these three pages are live:

- **http://localhost:5000** — the dashboard.
- **http://localhost:5000/settings** — change people, chores, calendars, colours and the timezone from a phone. It writes `config.yaml` and keeps your comments.
- **http://localhost:5000/preview** — the dashboard at the Pi, TV and tablet sizes at once, handy for a layout change.

#### Config fields explained

| Field | What it does |
|---|---|
| `family_name` | Shown in the corner of the dashboard. |
| `timezone` | An IANA name like `Europe/Berlin`. Decides when "today" rolls over and how event times read. Set it even on a Pi whose clock is already local — the engine works from this, not the machine clock. |
| `location` | Your city and country. Optional; gives the headline a sense of place. |
| `week_start` | The first day of the week page: `monday` to `sunday`, default `sunday`. A missing or unrecognised value is Sunday. Changing it makes the next tick fetch the calendars again. Also on **Settings > System**. |
| `theme` | `dark` (the default) or `light`. One choice for the dashboard, the settings pages and the phone page; a missing or unrecognised value is dark. |
| `calendars` | One entry per iCal feed: a `label`, a `url` (the secret iCal address) and `enabled`. Merged into one agenda. An optional `shared_with` list of email addresses shows only the events with one of those people as a guest or organiser. |
| `people` | `name`, `date_of_birth` (YYYY-MM-DD), an `avatar_emoji`, an `avatar_color`, and `interests` that can shape the headline. |
| `pets` | `name`, `type` and an `avatar_emoji`. |
| `tasks` | Jobs with a `recurrence` (daily, weekly and so on) and an `assignment`: who does it, by person `id`, in rotation or fixed. |
| `special_dates` | Countdowns to yearly events, as `MM/DD` with no year. |
| `claude_model` | `claude-haiku-4-5` costs roughly $0.13 a month at one dashboard a day. `claude-sonnet-5` writes better for about three times that. |
| `max_tokens` | Maximum length of the AI response. |

The settings page adds a short `id` to each person, pet, chore, date and calendar the first time you open it. Leave those alone — they are how the page tells one entry from another.

**Upgrading an old config?** See [upgrading](upgrading.md).

#### Editing from your phone

Everything on the dashboard is editable at `/settings`. Three things worth knowing:

- **A saved dashboard is from the last run.** Editing a chore or a person shows up on the next page load, but the headline is only rewritten once a day. Press **Rewrite daily headline** on the settings home page to get fresh copy immediately. Each press is one API call.
- **Adding a calendar checks the link.** Paste an iCal address and press **Test calendar link**. It tells you how many events it found and what the next one is, so you are not left guessing whether the URL works.
- **A personal calendar can keep its private side.** Fill in **Only show events shared with** on that calendar, and only the events the other parent is on reach the dashboard. See [a personal calendar with work in it](calendar-links.md#a-personal-calendar-with-work-in-it).

The dashboard shows up straight away, before anything is generated: until the first headline's written, it uses one worked out from the day. After that it's either today's dashboard or a stale one after a failed or missing run. When the headline is late, the times, turns and countdowns are still today's. The headline is one worked out from the day, and the dashboard says so.

---

## Part 2: put it on a Raspberry Pi

This turns a Pi with a small screen into a wall dashboard that boots straight into the dashboard and refreshes itself. The examples use the username `pi` and the folder `/home/pi`. If you chose a different username in Raspberry Pi Imager, substitute it everywhere.

### Step 1: Install Raspberry Pi OS

Install **Raspberry Pi OS** with the [Raspberry Pi Imager](https://www.raspberrypi.com/software/). In the imager's settings, set your username, enable SSH, and enter your Wi-Fi name and password. The current release is Trixie (Debian 13), which boots into a Wayland desktop — the kiosk steps below cover that, with an X11 alternative.

### Step 2: First boot — connect and install packages

SSH in from your computer, update, and install what the dashboard and the browser need:

```bash
ssh pi@raspberrypi.local
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv chromium fonts-noto-color-emoji
```

The emoji font is not optional — without it, every avatar and chore marker shows as an empty box.

### Step 3: Copy PompDash onto the Pi

Clone it directly on the Pi:

```bash
cd /home/pi
git clone https://github.com/gpompeo/pompdash.git
cd dinkydash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

Then edit `config.yaml` with your family's details, or fill it in later from the settings page. For updating the Pi after the first time, see [Updating later](#updating-later).

### Step 4: Add your API key on the Pi

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > /home/pi/dinkydash/.env
```

Check it works:

```bash
python generate.py
python app.py
```

Open `http://raspberrypi.local:5000` from another device on the same network to confirm the dashboard appears, then stop it with `Ctrl+C`.

### Step 5: Run it as a service

A systemd service starts the dashboard on boot and restarts it if it ever stops. `run_app.sh` ships with the repo and is what the service runs.

Create `/etc/systemd/system/dinkydash.service`:

```ini
[Unit]
Description=PompDash Family Dashboard
After=network.target

[Service]
ExecStart=/home/pi/dinkydash/run_app.sh
User=pi
WorkingDirectory=/home/pi/dinkydash
Restart=always

[Install]
WantedBy=multi-user.target
```

The dashboard serves on port 5000. To use another port, add a line like `Environment=DINKYDASH_PORT=5123` under `[Service]` and use that port everywhere below.

Enable and start it:

```bash
chmod +x /home/pi/dinkydash/run_app.sh
sudo systemctl daemon-reload
sudo systemctl enable dinkydash.service
sudo systemctl start dinkydash.service
```

### Step 6: Keep the dashboard up to date

A cron job ticks every five minutes, and each tick does only what your settings say is owed —
nothing at all, most of the time. Calendars are re-fetched every hour, so an appointment added at
09:00 for 15:00 reaches the dashboard the same afternoon. The headline is written once a day, at 06:00. Both
are yours to change under **Settings → How often it updates**.

The tick writes no headline while the example family (Mia, Theo and Biscuit) is still in
`config.yaml`. Replace them, by hand or on the settings page, and the first headline follows on
the next tick.

```bash
crontab -e
```

Add this line:

```cron
*/5 * * * * cd /home/pi/dinkydash && venv/bin/python generate.py --tick >> generate.log 2>&1
```

Runs never pile up: if one is still going when the next is due, the next skips itself. If a run
fails, the dashboard keeps today's agenda, turns and countdowns, shows a headline worked out from the
day and says so — the screen never goes blank, and the next tick tries again.

A once-a-day cron entry also works, and does the fetch and the headline together:

```cron
0 6 * * * cd /home/pi/dinkydash && venv/bin/python generate.py >> generate.log 2>&1
```

It just never sees a change you make to your calendar during the day, and the settings above have
no effect on it. Use one line or the other, not both.

### Step 7: Show the dashboard full screen at boot (kiosk)

Kiosk mode launches Chromium full screen with nothing around it. Current Raspberry Pi OS uses the Wayland desktop by default, so that is the main path. A classic X11 alternative follows for people who want the older, simpler tools.

First, save this launcher as `/home/pi/run.sh`. It waits for the dashboard to answer before opening the browser, which avoids the "localhost refused to connect" screen at boot:

```bash
#!/bin/sh
# Wait up to 60 seconds for PompDash to answer, then open it full screen.
echo 'Waiting for PompDash...'
i=0
while [ $i -lt 60 ]; do
    if curl -s -o /dev/null http://localhost:5000/ 2>/dev/null; then
        break
    fi
    i=$((i + 1))
    sleep 1
done

chromium \
  --kiosk \
  --password-store=basic \
  --disable-infobars \
  --disable-restore-session-state \
  --noerrdialogs \
  --no-first-run \
  --enable-features=OverlayScrollbar \
  http://localhost:5000/
```

Make it executable:

```bash
chmod +x /home/pi/run.sh
```

Turn screen blanking off so the dashboard does not disappear after ten minutes: run `sudo raspi-config`, then **Display Options → Screen Blanking → No**. (Non-interactively: `sudo raspi-config nonint do_blanking 1`.)

#### The Wayland desktop (the default)

Create the file `/home/pi/.config/labwc/autostart` and put one line in it:

```sh
/home/pi/run.sh &
```

Reboot. The Pi logs in, the desktop starts, and the dashboard opens full screen once the service is up.

One rough edge on Wayland: the mouse pointer does not hide itself when idle. If a mouse is plugged in, park the pointer in a corner, or unplug it — a wall panel needs no mouse. If that bothers you, use the X11 alternative below, which hides the pointer properly.

#### The X11 alternative (classic tools)

X11 is the older desktop. It is a little more work to switch to, but the mature tools for hiding the pointer and controlling the screen all work. This is what the PompDash Pi runs.

Switch the desktop to X11:

```bash
sudo raspi-config nonint do_wayland W1
```

Then edit `/home/pi/.config/lxsession/LXDE-pi/autostart` so it reads:

```
@lxpanel --profile LXDE-pi
@pcmanfm --desktop --profile LXDE-pi
@unclutter
@xset s off
@xset -dpms
@xset s noblank
@/home/pi/run.sh
```

That hides the pointer (`unclutter`), stops the screen blanking (`xset`), and launches the dashboard. Reboot to apply. On the newest OS the X11 session differs and this file may not exist — if so, prefer the Wayland path above.

### Step 8: Turn the screen off at night (optional)

Save power by switching the panel's backlight off overnight. Save this as `/home/pi/screen_control.sh`:

```bash
#!/bin/bash
# Turn the display backlight off or on. This works with the current graphics
# driver, where the older `vcgencmd display_power` command no longer does.
BL=/sys/class/backlight/*/bl_power
case "$1" in
    off) echo 1 | sudo tee $BL >/dev/null ;;
    on)  echo 0 | sudo tee $BL >/dev/null ;;
    *)   echo "Usage: $0 [on|off]"; exit 1 ;;
esac
```

Make it executable and schedule it in `crontab -e`:

```bash
chmod +x /home/pi/screen_control.sh
```

```cron
0 22 * * * /home/pi/screen_control.sh off
0 7 * * * /home/pi/screen_control.sh on
```

The Pi keeps running; only the panel sleeps. This uses the backlight file directly, so it works the same on Wayland and X11. It relies on the default user's passwordless `sudo`, which Raspberry Pi Imager sets up.

### Step 9: Rotate the display (optional)

If the screen is mounted upside down:

- **Simplest:** open **Screens** in the desktop's settings (the Control Centre on Trixie), right-click the display and set its orientation.
- **On Wayland, from a script:** add a line above the browser launch in `/home/pi/.config/labwc/autostart`, for example `wlr-randr --output DSI-1 --transform 180 &`.
- **On X11:** add `@xrandr --output DSI-1 --rotate inverted` to the autostart file from step 7.

The old `lcd_rotate` and `display_rotate` lines in `config.txt` no longer apply with the current graphics driver — use one of the methods above instead. If you have a touchscreen and the touch points end up mirrored, add `dtoverlay=vc4-kms-dsi-7inch,invx,invy` to `/boot/firmware/config.txt`.

---

## Troubleshooting

**Emoji show as empty boxes.** Install the font and refresh the cache: `sudo apt install fonts-noto-color-emoji && fc-cache -fv`.

**"localhost refused to connect" at boot.** Chromium started before the dashboard was ready. The `run.sh` above waits up to 60 seconds; make sure your autostart calls it rather than launching Chromium directly.

**The dashboard says today's headline hasn't arrived.** A generation run failed. Look at `generate.log` in the project folder. The usual causes are an expired API key, no network when the headline was due, or a calendar link that stopped working. Fix it, then press **Rewrite daily headline** on the settings page.

**Times are off by an hour.** The timezone under Settings → Family & system is what the engine uses, not the machine clock. Set it even if the clock is already local.

**A calendar shows nothing.** Check it under Settings → Calendars — a failed feed says so. Apple regenerates iCloud links when a calendar stops being shared, so a link that worked last month may need replacing. If the calendar has **Only show events shared with** filled in, open it and press **Test calendar link**: a working link with no events getting through means the address is not the one on the invitations.

**A GNOME keyring password box appears.** The `--password-store=basic` flag in `run.sh` prevents this. Make sure it is present.

**The screen still blanks.** Confirm you set **Screen Blanking → No** (Wayland) or that the `@xset` lines are present (X11).

**Wi-Fi is blocked after a fresh install.** Some images soft-block Wi-Fi until you set a country: `sudo raspi-config nonint do_wifi_country DE && sudo rfkill unblock wifi` (use your own country code).

---

## Updating later

To pick up a new version, pull it on the Pi itself — over SSH, or with a keyboard attached:

```bash
cd /home/pi/dinkydash
git pull
venv/bin/pip install -r requirements.txt
sudo systemctl restart dinkydash.service
```

Your settings and your key stay where they are: `config.yaml`, the dashboard's data files and `.env` are not in git, so a pull does not touch them.

---

## Quick reference

```bash
# On your computer
source venv/bin/activate
python sample_board.py                # a dashboard with no API call, for a first look
python generate.py                    # today's real dashboard (one API call)
python generate.py --date 2026-12-24  # any date, for checking a countdown
python app.py                         # dashboard at /, settings at /settings

# On the Raspberry Pi
sudo systemctl status dinkydash       # is it running
sudo systemctl restart dinkydash      # restart after a change
journalctl -u dinkydash -f            # the app's log
tail -f /home/pi/dinkydash/generate.log   # calendar fetches and headlines
/home/pi/screen_control.sh off        # screen off
/home/pi/screen_control.sh on         # screen on
```

Once it is set up, the family gets a fresh dashboard every day, and there is nothing to tap and nothing to maintain.

## Hardware for a Raspberry Pi screen

| Model | Verdict |
|---|---|
| **Pi 4 (2GB)** | The sweet spot. Runs Chromium in kiosk mode comfortably and is easy to find second-hand. |
| **Pi 5** | Works and boots faster, but costs more and runs hotter for a mostly idle job. |
| **Pi Zero 2 W** | Chromium is a heavy browser and the Zero struggles. Workable if you are patient. |
| **Pi 3** | Fine if you already own one. Slow to boot, but it only boots once. |

2GB of RAM is enough: the dashboard is one page that refreshes itself, with no database.

The layout targets **800x480**, the resolution of the official Raspberry Pi 7" Touch Display, which
connects over DSI (one ribbon cable, no HDMI) and is powered from the Pi. Any HDMI monitor works too:
the layout scales to fit, and a bigger screen reads better from across a room. Touch is optional;
the dashboard is read-only on the wall and everything is edited from a phone at `/settings`.

A Pi 4 with the 7" display draws under 10 watts. The backlight schedule in step 8 cuts that
overnight.

Use a MicroSD card of 16GB or more, a USB-C power supply, and a case or stand. On Raspberry Pi OS
Bookworm and later the boot configuration is `/boot/firmware/config.txt`, not `/boot/config.txt`.
