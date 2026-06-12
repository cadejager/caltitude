# Using the CalDAV plugin

> **Historical.** The plugin now uses the **Nextcloud MCP** connector
> (`docs/nextcloud-connector.md`), which supports named-timezone events. These
> CalDAV notes are kept for reference only.

Notes for driving the installed **caldav** MCP plugin (npm `caldav-mcp` → `ts-caldav`,
backed by a Nextcloud calendar server). Verified working 2026-06-08.

## TL;DR — the one gotcha

`list-calendars` returns calendar URLs prefixed with **`/remote.php/dav`**, e.g.
`/remote.php/dav/calendars/AI/personal/`. **Do not pass that URL as-is.** The
server's base URL already includes `/remote.php/dav`, so passing the full path
doubles it and every event call fails with a generic
*"Failed to retrieve vevents…"* / *"Failed to create event."*

**Strip the `/remote.php/dav` prefix** before using a calendar URL anywhere else.

| `list-calendars` returns                   | use this instead          |
| ------------------------------------------ | ------------------------- |
| `/remote.php/dav/calendars/AI/personal/`   | `/calendars/AI/personal/` |
| `/remote.php/dav/calendars/AI/chris-ai/`   | `/calendars/AI/chris-ai/` |

## Tools

### `list-calendars` — no args
Returns name + URL for each calendar. Available calendars: **Personal**
(`/calendars/AI/personal/`), **Contact birthdays**, **AI-Chris**
(`/calendars/AI/chris-ai/`).

### `list-events`
- `calendarUrl` (stripped path, required)
- `start`, `end` — ISO 8601, required. UTC `Z` works (`2026-06-01T00:00:00Z`).

Returns each event's `uid`, `summary`, `start`, `end`, and optional
`description` / `location`. Times come back as UTC.

### `create-event`
Required: `summary`, `start`, `end`, `calendarUrl` (stripped path).
Optional: `description`, `location`, `recurrenceRule`.

```jsonc
{
  "calendarUrl": "/calendars/AI/personal/",
  "summary":     "Team sync",            // the event title
  "description": "Weekly check-in",
  "location":    "Room 4 / Zoom",
  "start":       "2026-06-15T09:00:00-04:00",
  "end":         "2026-06-15T17:00:00-04:00"
}
```
Returns the new event's `uid`.

`recurrenceRule` (optional object): `freq` (`DAILY|WEEKLY|MONTHLY|YEARLY`),
`interval`, `count`, `until` (ISO), `byday` (e.g. `["MO","WE"]`), `bymonthday`,
`bymonth`.

### `update-event` — ⚠ currently broken
Takes `uid` + `calendarUrl` plus any fields to change. **Does not work against
this server** — it returns HTTP 403 regardless of the path used. Cause: the
plugin re-fetches the event, then PUTs to a href the server rejects. Workaround:
delete + re-create, or edit in the Nextcloud web UI. (Fixing it needs a change
in the `caldav-mcp` / `ts-caldav` package, not in how we call it.)

### `delete-event`
`uid` + `calendarUrl` (stripped path). Get the `uid` from `list-events`.

## Start / end times and time zones

- `start` and `end` are ISO 8601 datetimes. Supply a UTC offset
  (`...T09:00:00-04:00`) or a `Z` suffix.
- **The offset only fixes the instant** — the plugin converts both to a UTC
  `Date` before storing, so the event is saved in UTC. Verified:
  `09:00-04:00` → stored `13:00Z`, `17:00-04:00` → stored `21:00Z`.
- **You cannot set a named time zone (TZID), and you cannot give start and end
  different time zones.** The MCP tool exposes no `tzid` field (the underlying
  `ts-caldav` library supports `startTzid`/`endTzid`, but `caldav-mcp` doesn't
  surface them). To place an event "at 9am in zone X," compute that instant's
  UTC offset yourself and put it in the ISO string.

## Reminders / alarms

**Not supported.** There is no reminder/alarm parameter on `create-event` or
`update-event`, and the library does not emit a `VALARM`. Reminders must be
added in the Nextcloud web UI after the event exists.

## Field reference

| Want to set        | Field                                    | Supported |
| ------------------ | ---------------------------------------- | --------- |
| Title              | `summary`                                | ✅        |
| Description        | `description`                            | ✅        |
| Location           | `location`                               | ✅        |
| Start / end time   | `start` / `end` (ISO 8601 w/ offset)     | ✅        |
| Per-field timezone | —                                        | ❌ stored as UTC |
| Recurrence         | `recurrenceRule`                         | ✅        |
| Reminders / alarms | —                                        | ❌        |

## Worked example (all verified)

```
list-calendars
  → Personal = /remote.php/dav/calendars/AI/personal/   (strip → /calendars/AI/personal/)

create-event
  calendarUrl=/calendars/AI/personal/
  summary="Caldav plugin test event"
  description="…"  location="123 Test Street, Testville"
  start=2026-06-15T09:00:00-04:00  end=2026-06-15T17:00:00-04:00
  → uid 3384dd98-226b-4f82-919f-865c8ff77ff4   (stored 13:00Z–21:00Z)
```
A test event with that uid currently exists on **Personal**; delete it with
`delete-event` if you don't want it.
```
```
