# calendar-from-email

Forward an itinerary email to a dedicated inbox, and this plugin turns each flight
into an event on your calendar — automatically.

## What it does

1. You forward a flight-itinerary email to a dedicated Gmail inbox, adding a line
   at the top like *"please add these to my calendar."*
2. On a schedule (or when you ask), the plugin reads new emails, checks they came
   from a sender you trust, and extracts each flight leg.
3. It creates a calendar event per leg on the calendar you chose, with the
   departure/arrival airports and local times in the title.

## Setup

Run the **setup-calendar-from-email** skill once. It asks for:

- **Trusted senders** — the email addresses you'll forward from. Only emails from
  these addresses can ever create events.
- **Confirmation phrase** — the line you add when forwarding (e.g. "please add
  this to my calendar"). Matched by meaning, not exact text.
- **Target calendar** — picked from your CalDAV calendar list.
- **Schedule** — run automatically (e.g. each morning), manually, or both.

## Prerequisites

- A **Gmail connector** for the dedicated inbox. (If you just enabled it, restart
  the session so its tools load.)
- A **CalDAV calendar connector**.
- **Python 3.9+** (used for exact timezone conversion; standard library only).

## Security model

- **Sender allowlist** is the boundary: an event is only ever created if the
  email's `From` matches a trusted sender. Others can't add to your calendar.
- **Confirmation phrase** confirms *you* meant to add it.
- **Sandboxed reader**: the only component that reads email *content* has no tools
  and can only return data. Instructions hidden in an email body do nothing — the
  orchestrator never treats email content as commands, and reads only the `From`
  header to decide who's trusted.

## Known limitations

- The CalDAV connector stores events in **UTC** with no named timezone, so the
  calendar grid renders in *your* viewing timezone. Each leg's local departure and
  arrival times (with zone abbreviations) are written into the event title and
  description so they stay readable. The event is always at the correct absolute
  moment.
- Editing existing events via the connector is currently broken, so the plugin
  only **creates** events. Processed emails are labeled so re-runs never make
  duplicates.
- No reminders/alarms (connector limitation) — add those in your calendar UI.

## How it tracks what's new

After processing, each email is labeled (default `Calendared`). Each run only
looks at inbox emails missing that label, so nothing is processed twice. (If the
connector can't write labels, it falls back to a stored last-run timestamp.)

## Development

Layout:

| Path | What it is |
| --- | --- |
| `.claude-plugin/plugin.json` | Plugin manifest |
| `skills/` | The `setup-calendar-from-email` and `process-flight-emails` skills |
| `agents/email-event-extractor.md` | Sandboxed reader agent (the injection boundary) |
| `scripts/convert_time.py` | Deterministic local↔UTC timezone converter |
| `evals/` | Converter unit tests + reader/orchestrator behavioral specs |
| `docs/` | Notes on the CalDAV and Gmail connectors (gotchas, field references) |

Run the converter tests:

```bash
python3 evals/test_convert_time.py
```

Build the installable plugin package (excludes repo-only files):

```bash
zip -r /tmp/calendar-from-email.plugin . \
  -x ".git/*" -x "*.plugin" -x "docs/*" -x "evals/*" \
  -x "*/__pycache__/*" -x ".gitignore"
```
