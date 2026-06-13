---
name: setup-caltitude
description: First-time setup for the caltitude plugin. Use when the user wants to set up, configure, or initialize automatic calendar events from forwarded emails — collecting the Nextcloud credentials, allowed sender addresses, the target calendar, and the run schedule. Triggers include "set up caltitude", "set up calendar from email", "configure the flight email plugin", "set up forwarding to my calendar".
---

# Set up caltitude

Run an interactive, plain-language setup. It happens in **two phases** because the
bundled Nextcloud server only reads its credentials when it launches (at session
start), so the credentials must be in place *before* the calendar steps can work.

Do NOT expose internal JSON details unless the user asks — talk in terms of what
the plugin will do. Paths and the one credentials file ARE part of the user-facing
flow here, so those may be shown.

## How credentials work (read this first)

This plugin bundles its own Nextcloud server (`.mcp.json` → `Nextcloud_MCP`,
launched via `scripts/run-nextcloud-mcp.sh`). The server needs three values in its
environment: `NEXTCLOUD_HOST`, `NEXTCLOUD_USERNAME`, `NEXTCLOUD_PASSWORD`.

These do **not** come from a settings form. A Claude Code plugin can't use the MCPB
`userConfig` mechanism, so `.mcp.json` carries no credentials at all. Instead, the
launch script loads them from a local env file:

```
${XDG_CONFIG_HOME:-$HOME/.config}/caltitude/nextcloud.env
```

i.e. normally `~/.config/caltitude/nextcloud.env`, with lines:

```
NEXTCLOUD_HOST=https://cloud.example.com
NEXTCLOUD_USERNAME=chris
NEXTCLOUD_PASSWORD=<app password>
```

**Credential-handling rule for the assistant:** you may collect and write the host
and username (not secrets). You must NOT ask for, accept, or write the
`NEXTCLOUD_PASSWORD` yourself — the user fills that one line in their own editor.
Write the file with a blank `NEXTCLOUD_PASSWORD=` line and have them complete it.

## Prerequisites to confirm

1. A **Gmail connector** is connected (the dedicated inbox the user forwards to).
   If it was just enabled, it only loads in a **new session** — tell the user to
   restart if Gmail tools aren't available.
2. **`uv` / `uvx` is installed** (it launches the bundled server). If the Nextcloud
   tools later error with "uvx not found", have the user install uv:
   `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or
   `brew install uv`, then restart. **macOS/Linux only** (the server is launched via
   `/bin/sh`; Windows is unsupported).
3. **Python 3.9+** is available (timezone conversion; stdlib only).

Quick check for whether Nextcloud is already live: call `nc_calendar_list_calendars`.
If it succeeds, credentials are already in place — skip Phase 1 and go to Phase 2.
If it errors or the tool is absent, do Phase 1.

---

## Phase 1 — credentials (one-time, needs a restart afterward)

### 1.1 Collect the non-secret values
Ask the user, in chat, for their **Nextcloud URL** (e.g. `https://cloud.example.com`)
and **Nextcloud username**. Do not ask for the password.

### 1.2 Write the env file (without the password)
Target: `~/.config/caltitude/nextcloud.env` (honor `$XDG_CONFIG_HOME` if set).
Create the `caltitude` directory if needed, write the file with the host and
username filled in and a **blank** password line, then restrict permissions:

```
NEXTCLOUD_HOST=<their url>
NEXTCLOUD_USERNAME=<their username>
NEXTCLOUD_PASSWORD=
```

Then `chmod 600` the file.

If you cannot write outside the project/sandbox in this runtime, fall back to giving
the user a copy-paste block to run in their own terminal that does the same thing
(`mkdir -p`, write the two known lines + blank password line, `chmod 600`). Either
way the password line stays blank.

### 1.3 Hand off the password
Tell the user to open the file in their editor and paste their **Nextcloud app
password** after `NEXTCLOUD_PASSWORD=`, then save. The app password is created in
Nextcloud → Settings → Security → Devices & sessions — **not** the login password.
Example: `nano ~/.config/caltitude/nextcloud.env`.

### 1.4 Restart
The bundled server reads these values only at launch, so the user must **restart the
session** before continuing. Tell them that when they come back, re-running setup (or
just asking to finish caltitude setup) will pick up at Phase 2. Stop here until the
restart happens.

---

## Phase 2 — configuration (after restart, once Nextcloud responds)

Confirm `nc_calendar_list_calendars` now works. If it still errors, the password
line is probably empty or wrong, or uv is missing — revisit Phase 1 / prerequisites.

### 2.1 Collect the sender allowlist (list interface)
Only emails whose `From` matches this list will ever create calendar events — this
is the security boundary that stops other people from adding to the calendar.

Present a **list-style form** so each address is its own field: render an
elicitation widget with `mcp__visualize__show_widget` (`elicitation` module)
containing a repeatable list of email inputs with an "add another" control, plus
fields for the target calendar and schedule (2.3 and 2.4). Submit the form back with
`sendPrompt`. If the widget is unavailable, fall back to asking in plain text and
accept several addresses.

Store each entry as a **bare, full, lowercase email address** (no display name, no
angle brackets). At run time `process-flight-emails` builds a Gmail `from:(…)` query
clause from these, so only mail from these senders is ever returned. Notes:
- Include any `+` alias in full (`chris+flights@example.com` is its own entry).
- Gmail's `from:` is a search match, not a strict address-equality check — a
  determined display-name spoof *could* match. This is the accepted trade for not
  reading attacker-influenced `From` text in the orchestrator.

### 2.2 Confirmation intent (no setup needed)
There is **no** confirmation phrase to configure. When forwarding, the user just
adds a short note near the top asking to calendar the trip ("add to calendar",
"could you schedule these", etc.); the reader judges that intent by meaning. Tell
the user this is how to trigger scheduling — nothing to enter here.

### 2.3 Choose the target calendar
Call `nc_calendar_list_calendars`. Show the **`display_name`** of each calendar and
ask which to use (e.g. `AI-Chris`). Store that calendar's **internal `name`** field
as `calendarName` (e.g. `chris-ai`) — NOT the display name. `nc_calendar_create_event`
accepts the internal name, and passing the display name fails.

### 2.4 Probe Gmail labeling
Confirm the connector can list/search messages and add a label (`list_labels`). The
plugin uses a label named **`caltitude`** (created on first run if absent) and
archives each processed email. No tracking-mode choice is needed.

### 2.5 Choose how it runs
Ask whether they want scheduled runs, manual, or both. Manual ("run my flight
emails") is always available regardless.

For scheduled runs, let the user pick **any number of run times** — e.g. "8am",
"8am and 6pm", "every 3 hours", "weekdays at noon". Create scheduled task(s) that
invoke `process-flight-emails` accordingly:
- Prefer **one** scheduled task whose cron covers all the chosen times when they
  share a cadence (cron lists work: `0 8,18 * * *` for 8am + 6pm; `0 */3 * * *` for
  every 3 hours; add `* * 1-5` style day fields for weekday-only).
- If the requested times can't be expressed in a single cron (genuinely different
  cadences), create **multiple** scheduled tasks — give each a distinct, descriptive
  id (e.g. `caltitude-morning`, `caltitude-evening`) so they don't collide and can
  be managed/removed individually.
- Confirm back the exact times you scheduled. The user can re-run setup later to
  add, change, or remove run times.

### 2.6 Write the config to Nextcloud
Write the config JSON to **`.config/caltitude/config.json`** in Nextcloud via
`nc_webdav_write_file`. Create the folders first **one level at a time** —
`nc_webdav_create_directory` is not recursive, so make `.config`, then
`.config/caltitude` (a 405 means it already exists, which is fine). Note: this is the
Nextcloud Files config, separate from the local `nextcloud.env` credentials file.
Shape (`calendarName` is the internal name from 2.3):

```json
{
  "allowedSenders": ["chris@example.com", "chris.work@example.com"],
  "calendarName": "chris-ai",
  "labelName": "caltitude"
}
```

### 2.7 Confirm
Summarize in plain language: that credentials live in `~/.config/caltitude/nextcloud.env`,
which senders are trusted, that forwarding with a short "add to my calendar" note
triggers it, which calendar events go to, that processed emails get the `caltitude`
label and are archived, and the schedule. Offer a test: forward one itinerary, then
run `process-flight-emails`.
