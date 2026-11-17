---
title: About DinkyDash
seo_title: "About DinkyDash — An Open-Source Family Calendar"
template: page.html
description: DinkyDash is an open-source family calendar for a screen you already own. We can host it for you, or you can run it yourself for free.
---

DinkyDash is a **family calendar for a screen you already own**. Open it on a TV, an old tablet or a Raspberry Pi, and your family gets one screen with today's calendar, whose turn each chore is, and countdowns to the big days. A short headline at the top is written fresh each day.

It was built by [Caspar](https://casparwre.de), an indie developer in Berlin, for his own kids. It's been open source since 2021, because a family calendar shouldn't cost a dedicated screen and a subscription.

## What the dashboard shows

- **Today's agenda.** What's happening today, in time order, merged from every calendar you add.
- **Whose turn it is.** Each chore passes to the next person every day, so nobody has to keep track.
- **Countdowns.** Days until birthdays, holidays and the dates everyone keeps asking about.
- **A headline.** One line about the day, written by AI. It's the only part an AI writes.

## How it runs

Once a day, at a time you pick, Claude reads the day ahead and writes the headline. Your calendars are fetched on their own schedule, every hour unless you choose otherwise. Whose turn it is and the countdowns are worked out from the date each time the page loads, so they're right even if nobody has touched anything for months.

## The principles

- **Bring your own screen.** Anything with a browser works. There's no hardware to buy from us, now or later.
- **Nothing to feed.** The turns move on by themselves, and nobody has to chase anybody. Ticking a task off from your phone is there if you want it, not something the wall needs.
- **Yours to keep.** The code is MIT-licensed and public, so the dashboard can't be taken away from you.

## Run it yourself


**You host it.** It's free to run on your own machine. Add your own Anthropic key if you want a daily headline; details about your family and calendars go to Anthropic to write it. Setting it up takes an afternoon and some comfort with a terminal. The [privacy page](/privacy/) explains what goes where.

## Where to start

- [Self-hosting guide](/getting-started/): from nothing to a dashboard on your wall
- [The ~$150 DIY build](/diy-skylight-calendar/): the Raspberry Pi and touchscreen route
- [How it compares to Skylight, Hearth and the rest](/skylight-calendar-alternatives/)
- [The code, on GitHub](https://github.com/caspii/dinkydash)
