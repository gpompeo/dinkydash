# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`doc/terminology.md`**: this repo's glossary. It defines the product terms (dashboard, screen, chore, special date and so on) and the copy conventions. There is no `GLOSSARY.md`; do not create one, because that would duplicate this file. When a skill says "the glossary", it means this file.
- **`doc/voice.md`** before writing anything a customer reads.
- **`doc/adr/`**: read ADRs that touch the area you're about to work in, if the folder exists.

If a file doesn't exist, **proceed silently**. Don't flag its absence; don't suggest creating it upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates ADRs lazily when decisions actually get resolved, and should add new terms to `doc/terminology.md`.

## File structure

Single-context repo:

```
/
├── doc/terminology.md      ← the glossary
├── doc/voice.md
├── doc/adr/               ← decisions, created when the first one is recorded
└── dinkydash/ web/ website/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `doc/terminology.md`. Don't drift to synonyms it explicitly avoids: for example **dashboard** for the whole display and **screen** for the device showing it, never **board**, and **daily headline**, never **daily message**.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`, and add the entry to `doc/terminology.md` in the same change).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
