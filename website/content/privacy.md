---
title: Privacy
seo_title: "Privacy — DinkyDash"
template: page.html
description: What the self-hosted dashboard stores, the services it can contact, and how the separate website uses analytics.
---

*Last updated: 16 November 2026.*

DinkyDash runs on your own machine. Your configuration, calendar links,
appointments, task completions, shopping list and generated dashboard are kept
in files there. You control the machine and any backups you make.

## Where information goes

- **Calendar providers:** the app fetches each enabled calendar link from its
  provider. The link is a credential: anyone who has it may be able to read
  your calendar.
- **Anthropic:** if you provide an API key, the app sends details including
  family names, ages, interests, location, pets, calendar events, tasks and
  countdowns to Anthropic to write a headline. You use your own key and
  agreement with Anthropic. The dashboard also works without a key.
- **SendGrid:** if you configure a SendGrid key and send feedback from the app,
  the message goes through SendGrid to the configured feedback mailbox. Don't
  include calendar links or other private details unless you intend to share them.

The app doesn't provide an account on this site, collect payments or send error
reports to a hosted dashboard service. Its optional parent password, PIN hashes
and screen link are kept on your machine. Restrict network access to people you
trust; the password doesn't make a public internet deployment safe.

## This website

The website is separate from your dashboard. Its pages load **Fathom** and
**Ahrefs** analytics. If configured, they can also load **Google Ads**. A
campaign cookie may be set when a page is opened with campaign parameters.
These services receive information from your browser when their scripts load;
they don't receive data from your locally running dashboard through those
scripts. The website operator's hosting and privacy arrangements depend on
where this copy of the site is deployed.
