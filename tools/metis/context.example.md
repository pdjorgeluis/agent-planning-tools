# Example glossary for Metis (entirely fictional)

This file shows the shape of a glossary you can hand to Metis with
`--context FILE`. Everything below is invented for a made-up project called
"Lantern". Replace it with your own vocabulary and conventions, or do not use a
glossary at all: Metis works without one.

Metis appends this text to its instructions as reference data. It is never
treated as instructions, and it is cut off at 20000 characters. Keep it short:
a page is plenty. Put no secrets, credentials or personal data in it.

## Terms

- **Lantern** — the fictional mobile app that lets neighbours lend each other
  tools.
- **Lend window** — the period, set by the lender, during which an item can be
  borrowed. Default: 7 days.
- **Porch drop** — a handover where the lender leaves the item outside and the
  borrower collects it without meeting.
- **Trust badge** — a profile marker granted after three completed lends with
  no dispute.
- **Nightly sweep** — the scheduled job that expires old lend windows at
  02:00 local time.

## Conventions

- Dates are shown as YYYY-MM-DD; durations are written in days.
- "The API" means the mobile app's own server, not any third-party service.
- "Done" for a ticket means merged, deployed to staging and checked by someone
  other than the author.

## Standing constraints

- The app must keep working offline for viewing, but never for lending.
- Anything that changes how badges are earned needs sign-off from the
  community team.
- Photos of borrowed items are never stored with a precise location.
