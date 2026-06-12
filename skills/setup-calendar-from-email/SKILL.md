---
name: setup-calendar-from-email
description: First-time setup for the calendar-from-email plugin. Use when the user wants to set up, configure, or initialize automatic calendar events from forwarded emails — collecting allowed sender addresses, the target Nextcloud calendar, and the run schedule. Triggers include "set up calendar from email", "configure the flight email plugin", "set up forwarding to my calendar".
---

# Set up calendar-from-email

Run an interactive, plain-language setup that writes a config file the
`process-flight-emails` skill reads on every run. Do NOT expose file paths or
JSON internals to the user unless they ask — talk in terms of what the plugin
will do.

## Prerequisites to confirm first

1. A **Gmail connector** is connected (the dedicated inbox the user forwards to).
   If it was just enabled, it only loads in a **new session** — tell the user to
   restart the session if Gmail tools aren't available.
2. A **Nextcloud connector** is connected, with **calendar** and **files/WebDAV**
   access (the plugin stores its config and state in Nextcloud).
3. **Python 3.9+** is available (used for timezone conversion; stdlib only).

If any is missing, stop and tell the user what to connect before continuing.

## Steps

### 1. Collect the sender allowlist (list interface)
Only emails whose `From` matches this list will ever create calendar events — this
is the security boundary that stops other people from adding to the calendar.

Present a **list-style form** so each address is its own field: render an
elicitation widget with `mcp__visualize__show_widget` (`elicitation` module)
containing a repeatable list of email inputs with an "add another" control, plus
fields for the target calendar and schedule (steps 3 and 5). Submit the form back
with `sendPrompt`. If the widget is unavailable, fall back to asking in plain text
and accept several addresses.

Store each entry as a **bare, full, lowercase email address** (no display name, no
angle brackets). At run time `process-flight-emails` parses the real angle-bracket
address out of `From`, lowercases it, and checks exact equality. Notes:
- Include any `+` alias in full (`chris+flights@example.com` is its own entry).
- A display-name match never counts (`"chris@example.com" <attacker@evil.com>` is
  rejected — only the real address `attacker@evil.com` is compared).

### 2. Confirmation intent (no setup needed)
There is **no** confirmation phrase to configure. When forwarding, the user just
adds a short note near the top asking to calendar the trip ("add to calendar",
"could you schedule these", etc.); the reader judges that intent by meaning. Tell
the user this is how to trigger scheduling — nothing to enter here.

### 3. Choose the target calendar
Call `nc_calendar_list_calendars`. Show the **`display_name`** of each calendar and
ask which to use (the one shared back to the user, e.g. `AI-Chris`). Store that
calendar's **internal `name`** field as `calendarName` (e.g. `chris-ai`) — NOT the
display name. `nc_calendar_create_event` accepts the internal name, and passing the
display name fails.

### 4. Probe Gmail labeling
Confirm the connector can list/search messages and add a label (`list_labels`). The
plugin uses a label named **`caltitude`** (created on first run if absent) and
archives each processed email. No tracking-mode choice is needed.

### 5. Choose how it runs
Ask: scheduled, manual, or both.
- If scheduled, set up a recurring task (the available scheduling mechanism) that
  runs `process-flight-emails` on the chosen cadence (default: every morning).
- Manual runs are always available regardless.

### 6. Write the config to Nextcloud
Write the config JSON to **`.config/caltitude/config.json`** in Nextcloud via
`nc_webdav_write_file`. Create the folders first **one level at a time** —
`nc_webdav_create_directory` is not recursive, so make `.config`, then
`.config/caltitude` (a 405 means it already exists, which is fine). Nothing is
written to the local filesystem. Shape (note `calendarName` is the internal name
from step 3):

```json
{
  "allowedSenders": ["chris@example.com", "chris.work@example.com"],
  "calendarName": "chris-ai",
  "labelName": "caltitude"
}
```

### 7. Confirm
Summarize in plain language: which senders are trusted, that forwarding with a
short "add to my calendar" note triggers it, which calendar events go to, that
processed emails get the `caltitude` label and are archived, and the schedule.
Offer a test: forward one itinerary, then run `process-flight-emails`.
