# Using the Nextcloud MCP connector

Notes for driving the **Nextcloud MCP** connector, which the plugin uses for both
the calendar and its own config/state storage. This replaced the standalone CalDAV
connector (see `caldav-plugin-usage.md`, now historical).

## Calendar

### `nc_calendar_list_calendars` — no args
Returns the user's calendars by **name**. Setup stores the chosen name as
`calendarName`; every event call passes that name (not a URL).

### `nc_calendar_create_event`
Key args: `calendar_name`, `title`, `start_datetime`, `end_datetime`, `all_day`,
`description`, `location`, `categories`, `timezone`, `reminder_minutes`,
`reminder_email`.

Datetime handling (this is the important part):
- `"2026-01-15T14:00:00Z"` / `"...+00:00"` → stored as **UTC**.
- `"2026-01-15T14:00:00"` **+ `timezone="America/Denver"`** → stored **TZID-bound**
  (server emits `DTSTART;TZID=...` + a VTIMEZONE). This is how flights get real
  local times — unlike the old CalDAV connector, which could only store UTC.
- `"2026-01-15T14:00:00"` alone → floating local time (avoid; ambiguous).
- `"2026-01-15"` with `all_day=true` → all-day event (hotels, car rentals).

**One timezone per event.** There is a single `timezone` parameter applied to both
naive `start_datetime` and `end_datetime`. A single event therefore **cannot** put
the departure zone on the start and a different arrival zone on the end (iCalendar
allows it; this tool does not surface per-field TZID, and there is no raw-ICS path —
`nc_webdav_write_file` writes to Files, not to calendar collections). The plugin
anchors each flight to the **departure** zone and re-expresses the arrival end in
that zone (via `scripts/convert_time.py to-zone`) so the instant and duration stay
exact; the true arrival local time + zone go in the title/description.

**Reminders.** `reminder_minutes` + `reminder_email` control alarms. Flights use a
popup (`reminder_minutes: 180`, `reminder_email: false`); hotels and cars use **no**
reminder (`reminder_minutes: 0`, `reminder_email: false`).

## Files / WebDAV (config + state storage)

The plugin is locally stateless — config and state live in Nextcloud:
- `.config/caltitude/config.json` — written by setup.
- `.local/state/caltitude/state.json` — `{ "lastRunISO": "..." }`.

Tools: `nc_webdav_create_directory` (create the folders first),
`nc_webdav_write_file(path, content)`, `nc_webdav_read_file(path)`. Paths are
relative to the Nextcloud user's files root. Treat a "not found" on
`state.json` as "no prior run → scan the whole inbox."
