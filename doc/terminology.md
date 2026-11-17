# Product terminology

Checked against the application on 11 September 2026. This is the reference for
product copy, help pages, emails, accessibility labels, design mockups and images.
Use British English and sentence case, except for the product name **PompDash**.

## The dashboard

**Dashboard** is the name of the complete PompDash display: the agenda, chore turns,
countdowns and headline. It replaces the former product term **board**.
Use **dashboard** in prose and **Dashboard** at the start of a heading or button.

A **screen** is the physical TV, tablet, monitor or Raspberry Pi panel showing a dashboard.
Several screens can show the same dashboard; changing its settings affects all of them.
A **calendar** is one source of events, not the whole dashboard.

## Glossary

| Term | Meaning | Current interface and usage |
|---|---|---|
| PompDash | The product | Preserve the capital P and D: one word, two capitals. |
| Dashboard | The complete household display | “Dashboard”, “View dashboard”, “Set up your dashboard”, “Show on the dashboard”, “Dashboard colours”, “Name on the dashboard”. |
| Screen | A device displaying the dashboard | Use dashboard when referring to its shared content. |
| Screen setup | One screen's touch mode, first page and rotation | Made at Settings > Screens > Screen setup. It is part of that screen's link, never stored on the server, so screens never affect each other. |
| Screen link | The bearer address a screen opens when parent sign-in is enabled | Anyone with the link can view the dashboard. Replacing it invalidates the previous link. |
| Settings | The area for configuring the household and dashboard | Available at `/settings`; optional parent sign-in protects it. |
| Family / household | The people sharing a dashboard and its settings | One household per self-hosted installation. “Name on the dashboard” controls its displayed name. |
| Person / People | A household member | “People”, “Add a person”, “New person”, “Remove this person”. Birth date supplies the age and birthday countdown; names can participate in chores. |
| Pet / Pets | A household animal | “Pets”, “Add a pet”, “New pet”, “Kind of animal”. A pet can be mentioned in the headline. Pets are not a section of the dashboard. |
| Task / Tasks | A household job with a recurrence and an assignment | “Tasks”, “Add a task”, “New task”, “Remove this task”. Recurrence is once, daily, weekly, monthly or on chosen weekdays; assignment is fixed, rotate, anyone or everyone. Ticked off from the phone page. Replaces the old “Chore”. |
| Shopping | The family's shared list of things to buy | “Shopping”, “Add an item”, “Bought”, “Clear bought”. Edited on the phone page and shown on the wall while the Shopping switch is on. Its text never reaches the model. |
| Activity | The parent-only page of check-ins | “Activity”: streaks, the last thirty days and one-tap corrections for the last fourteen days. Not a leaderboard. |
| Phone page | The page each person opens on their own phone | At `/h`. With sign-in on, a person picks their name and enters a PIN set by a parent; a signed-in parent can pick anyone. With sign-in off, name selection is open. Then they tick tasks and edit Shopping. “Phone page” in docs; “your phone” in copy. |
| Streak | Consecutive days a person completed everything due to them | Shown on the wall and the phone page, with a best streak. A day with nothing due neither adds to nor breaks it. |
| Rotation order | The sequence of people who take a task | “Whose turn, in order” shows the saved sequence. Checkboxes select people; arrows move them earlier or later. Newly selected people join at the end, and Save keeps the changes. This is separate from reordering People or the task list. |
| Whose turn | A task's assignment | An assignment option in the task editor. Ticking is done on the phone page, and there is no on-demand swap. |
| Calendar / Calendars | A connected source of events | “Calendars”, “Calendar name”, “Add a calendar”, “Save calendar”. Multiple enabled calendars merge into the agenda. The name is for recognising the source in settings. |
| Calendar link | The calendar provider's iCal/ICS subscription address | Field label: “Calendar link (iCal / ICS)”. HTTPS and `webcal://` are accepted; a provider's ordinary webpage or sharing page is not necessarily a calendar feed. |
| Guest filter | The optional restriction to events shared with selected email addresses | Visible label: “Only show events shared with”. Matching guests or organisers allow an event through. An empty field allows all events from that calendar. |
| On / Paused | Whether a calendar contributes events | List status labels. The edit checkbox is “Show on the dashboard”. Pausing keeps the calendar entry and clears its stored events. |
| Agenda | The combined event list | The dashboard labels it “Today” and, when there is room, “Tomorrow”. It is assembled from calendars; it is not AI-generated. |
| Headline | The large heading on the dashboard | Written once a day. A stale dashboard uses a headline worked out from the day instead, and says so once that headline was due. |
| Daily note | Not a part of the dashboard | Do not use it in copy. The dashboard shows a headline, not a separate note. A stored brief and an export can still contain a note field. |
| Special date / Special dates | A named annual occasion | “Special dates”, “Add a date”, “What is it”, with “Day” and “Month” under “Date”. Lists use named months, such as “1 July”. Invalid stored dates are flagged for repair and omitted from countdowns; 29 February is allowed. |
| Countdown | Days remaining until a birthday or special date | Appears under “Coming up”. Birthday countdowns come from People and need no duplicate special-date entry. |
| Refresh calendars | Fetch the latest events from enabled calendars | Updates the agenda; it does not rewrite the headline. “Fetch the calendars” sets this interval under “How often it updates”. |
| Daily headline | The headline Claude writes once a day | “Rewrite daily headline” fetches calendars, then writes a fresh one. Before the first one the action is “Write first daily headline”. “Write the daily headline at” sets the schedule. Pending feedback says “Writing your daily headline…”. Not “daily message”, “daily line” or “the day's line”. |
| Time zone | The household's clock for dates, events and daily generation | “Time zone” under “Family & system”, with a suggested local zone during setup. |
| Clock | Whether times are written 24-hour or 12-hour | “Clock” under “Family & system”, beside “Time zone”: “24-hour (15:45)” or “12-hour (3:45 pm)”. The time zone decides what a time is; this decides how it is written. Defaults to 24-hour and applies to the agenda, the computed headline and the generated daily headline. |
| Emoji | The small picture beside a person, pet, chore or special date | “Emoji” on the edit forms: a row of quick picks, “None”, and “More…”, which opens “Choose an emoji” with a search box that also takes an emoji typed on the keyboard. Shown as the avatar in settings lists and beside chores and countdowns on the dashboard. |
| Colours | The dashboard’s light or dark appearance | “Dashboard colours”, choices “Light” and “Dark”. Changes apply immediately. |

## Copy conventions

Use **chore** for the household task and **calendar** for a connected event source in settings.
**Daily headline** names the headline Claude writes each day, and it is the only name for it:
not **daily message**, which sounds like a note somebody sends, and not **daily line** or
**the day's line**. Plain **headline** is fine where the dashboard's heading is meant, whoever
wrote it. **Daily note** is not a thing the dashboard shows; do not use it in new copy. Keep
**brief** for implementation details. Use **Refresh calendars** for fetching events, which does
not write a new daily headline. “Feed” is appropriate when explaining iCal/ICS, not as a
competing settings label for a connected calendar.

“Your dashboard” groups settings shared by every screen. A **screen** is the physical device,
not a separate copy of the household settings. Removal confirmations name the item, and explain
any effects on chore rotations or stored calendar events. **Keep editing** / **Discard changes**
applies to leaving an unsaved form; **Keep current link** / **Replace screen link** applies to
revoking the shared screen address.

## Implementation names and compatibility

Existing source files, Python names, Flask endpoint names, CSS classes, screenshot URLs and the
JSON export key `board` retain their technical spelling. Examples include `dinkydash/board.py`,
`web/templates/board.html`, `board.index`, `sample_board.py` and existing image paths. They are
implementation or compatibility identifiers, not approved product wording. A terminology edit
must not silently change a saved export format, a working link or an import.

When adding or changing a concept, update its entry here in the same change. Check the actual
labels in `web/routes/settings.py`, `web/setup.py` and `web/templates/`, then check sign-in
emails, documentation text, metadata, image captions and screenshots for the same wording.
