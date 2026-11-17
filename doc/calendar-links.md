# Finding your calendar link

DinkyDash reads calendars over iCal, the sharing format every calendar app speaks. Google Calendar,
Apple iCloud Calendar, Outlook and Cozi all give you an iCal link, and any of them works. Add one
feed per person and they merge into a single agenda.

This is a link, not a login. DinkyDash never signs in to your Google, Apple or Microsoft account: it
fetches the link on a schedule and can only read.

**Treat the link like a password.** The long random string in it is the login. Whoever holds the
link reads that whole calendar for as long as it exists, and no provider tells you who has used it.
Keep it out of screenshots, shared documents, public issues and group chats. Every example address
here is visibly fake, with an `xxxx` run in it.

Each link covers **one** calendar. A household with a personal, a school and a partner's calendar
needs three links, one from each.

## Google Calendar

1. Open [Google Calendar](https://calendar.google.com/) in a browser on a computer. The phone apps
   do not show this.
2. Open **Settings** (the gear), then choose the calendar under **Settings for my calendars**. You
   can also hover over it in the sidebar and pick **Settings and sharing** from its menu.
3. Scroll to **Integrate calendar** and copy the **Secret address in iCal format**.

```url
https://calendar.google.com/calendar/ical/you%40gmail.com/private-xxxx/basic.ics
```

- If the address leaks, press **Reset** beside it. Google issues a new one and the old one stops
  working at once, so anything pointed at the old address needs the new one.
- The **public address** on the same screen only works on a calendar you have made public. You want
  the secret one.
- On a work or school account an administrator can switch secret addresses off for everyone. If the
  section is missing, that is why. A personal Google account is the way round it: make a family
  calendar there and invite your work account to the events that matter.
- A calendar shared *with* you has no secret address of yours to hand out. Ask the owner for theirs.
- Google caches the feed at their end, so a change can take hours to appear.

## Apple iCloud Calendar

1. Open [iCloud Calendar](https://www.icloud.com/calendar/) in a browser and sign in. The Calendar
   app on a Mac, iPhone or iPad has the same switch.
2. Hover over the calendar in the sidebar and click the **information icon** next to its name (tap
   it on a tablet).
3. Switch on **Public Calendar**, then press **Copy**.

```url
webcal://p00-caldav.icloud.com/published/2/xxxxxxxxxxxx
```

- **Paste it as Apple gives it to you.** DinkyDash converts `webcal://` to `https://` and leaves the
  rest alone. A plain `http://` link is refused, because it would send the address across the
  network in the clear.
- "Public" means a long random address, not a listed page. Anyone holding it can read the calendar.
- **Switching Public Calendar off and on again issues a different link** and the old one is dead,
  as it is if the calendar is deleted and recreated. A screen that goes blank months after setup
  usually needs the new link from iCloud.

## Outlook and Microsoft 365

1. Open [Outlook on the web](https://outlook.live.com/calendar/).
2. Go to **Settings** (the gear), then **Calendar**, then **Shared calendars**.
3. Under **Publish a calendar**, choose the calendar.
4. Set the permission to **Can view all details**. The other options hide titles and locations, so
   the dashboard would show "Busy" and nothing else.
5. Press **Publish**. Two links appear: copy the **ICS** one. The HTML link is a web page, not a
   calendar feed, and will fail to parse.

```url
https://outlook.office365.com/owa/calendar/xxxxxxxx@example.com/xxxxxxxx/calendar.ics
```

- A personal Outlook.com account produces a slightly different host. Either shape is fine.
- To take it back, stop publishing under **Shared calendars**. Republishing gives a different link.
- On a work or school account, publishing is an administrator setting and often off. Use a
  personal Outlook.com account for the family calendar, or ask the administrator.

## Cozi

Do this on a computer.

1. Sign in to [Cozi](https://my.cozi.com/) in a browser and open **Settings**.
2. In the calendar section, open **Shared Cozi Calendars**.
3. Switch the family member you want from **Unshared** to **Shared**.
4. Press **View or send Cozi URL**, then **Copy Cozi URL**.

The address is a long `https://` link on a `cozi.com` server ending in `.ics`. Each family member is
a separate feed, so share and add each one you want. Cozi Gold is not needed. Setting a member back
to **Unshared** stops the link working.

## Adding the link

Put it in `config.yaml` under `calendars:`, or use **Settings, Calendars, Add a calendar** in the
settings UI: give it a name, paste the address into **Calendar link (iCal / ICS)** and press
**Test calendar link**. That says how many events it found and what the next one is, so you know it
works before you save.

## A personal calendar with work in it

You do not need a separate family calendar. If your own calendar also holds work meetings and
private appointments, add it anyway and fill in **Only show events shared with** with the other
parent's email address. Only the events they are invited to, or that they organised, reach the
dashboard. The rest is dropped as the feed is read, so it is never stored and never sent to Claude.

- **Use the address on the invitation.** Google, Apple and Outlook record guests by email address.
  If they have two, list both with a comma between them.
- **Press Test calendar link before you save.** It says how many events get through out of how many
  and warns you if none do. That usually means the address is not the one on the invitations, or
  nothing in the next fortnight has been shared yet.
- Each calendar has its own list, so a school calendar with no guests is left alone. Saving a
  calendar clears what was fetched from it before; the next refresh fetches it afresh, or press
  **Refresh calendars**.

In `config.yaml` the setting is `shared_with`, a list of addresses under that calendar.

## When a calendar stops working

A failed feed is flagged under Settings, Calendars, and the dashboard keeps showing whatever it
last fetched from it. Replace the link if the provider has regenerated it (see the notes above for
iCloud, Outlook and Google). The rest of the checks are in [running-it.md](running-it.md).
