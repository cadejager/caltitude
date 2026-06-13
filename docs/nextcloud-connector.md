# Using the Nextcloud MCP connector

Notes for driving the **Nextcloud MCP** connector, which the plugin uses for both
the calendar and its own config/state storage. This replaced the standalone CalDAV
connector (see `caldav-plugin-usage.md`, now historical).

> **Bundled (v0.3.0+).** The plugin ships its own Nextcloud server — see the
> repo-root `.mcp.json` (server `Nextcloud_MCP`, launched via
> `scripts/run-nextcloud-mcp.sh`). **Credentials are NOT `userConfig`/`${user_config.*}`**
> — those are Desktop-Extension (`.mcpb`) features that don't work in a plugin (and
> caused the plugin to stop loading when we tried). Instead the launcher loads
> `~/.config/caltitude/nextcloud.env` (mode `600`) and exports `NEXTCLOUD_HOST`/
> `USERNAME`/`PASSWORD`; `setup-caltitude` writes that file (host + username; the
> user pastes the app password). Because the server is part of the plugin, it loads
> **wherever the plugin's skill runs — including scheduled tasks** (a desktop
> `.mcpb` extension does *not*, which is why scheduled runs failed before). Requires
> `uv`/`uvx` on the machine (first launch fetches the server; a fully offline
> scheduled run will fail). **macOS/Linux only** — launched via `/bin/sh`; a plugin
> `.mcp.json` has no `platform_overrides`, so the shipped `run.cmd` is currently
> unreachable and Windows is unsupported. If you previously installed the Nextcloud
> **desktop extension**, **disable it**: it shares the `Nextcloud_MCP` name, so with
> both enabled they collide and a scheduled run could bind to the extension (which
> doesn't load in scheduled tasks) — reproducing the original failure.

## Calendar

### `nc_calendar_list_calendars` — no args
Returns each calendar with both an internal **`name`** (e.g. `chris-ai`) and a
**`display_name`** (e.g. `AI-Chris`). **`nc_calendar_create_event` takes the
internal `name`** — setup shows the user the display name but stores the internal
`name` as `calendarName`. (Verified live: passing `chris-ai` works.)

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
  **All-day `end_datetime` is EXCLUSIVE** (verified live): an event with
  `start 2027-03-01`, `end 2027-03-04` renders on 03-01/02/03 only — `03-04` is not
  covered. So to show check-in..checkout inclusive, pass `end_datetime` = the
  inclusive end **+ 1 day** (`convert_time.py add-days <date> --days 1`).

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

**`nc_webdav_create_directory` is not recursive** (verified live: it returns 409
when a parent is missing, 201 on create, 405 if the dir already exists). Create
each level in order — e.g. `.local`, then `.local/state`, then
`.local/state/caltitude`.
