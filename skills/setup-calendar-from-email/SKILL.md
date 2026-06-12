---
name: setup-calendar-from-email
description: First-time setup for the calendar-from-email plugin. Use when the user wants to set up, configure, or initialize automatic calendar events from forwarded emails — collecting allowed sender addresses, the confirmation phrase, the target calendar, and the run schedule. Triggers include "set up calendar from email", "configure the flight email plugin", "set up forwarding to my calendar".
---

# Set up calendar-from-email

Run an interactive, plain-language setup that writes a config file the
`process-flight-emails` skill reads on every run. Do NOT expose file paths or
JSON internals to the user unless they ask — talk in terms of what the plugin
will do.

## Prerequisites to confirm first

1. A **Gmail connector** is connected (the dedicated inbox the user forwards to).
   If a Gmail connector was just enabled, it only loads in a **new session** —
   tell the user to restart the session if Gmail tools aren't available.
2. A **CalDAV calendar connector** is connected.
3. **Python 3.9+** is available (used for timezone conversion; stdlib only).

If any is missing, stop and tell the user what to connect before continuing.

## Steps

### 1. Collect the sender allowlist
Ask which email addresses the user will forward from. Explain: only emails whose
`From` matches this list will ever create calendar events — this is the security
boundary that stops other people from adding to the calendar. Accept several
addresses.

Store each entry as a **bare, full email address** (e.g. `chris@example.com`) —
no display name, no angle brackets. These are compared **exactly** at run time:
`process-flight-emails` parses the real angle-bracket address out of the `From`
header, lowercases it, and checks it is identical to an allowlist entry. So:
- Store addresses **lowercase** (local part and domain both compared
  case-insensitively; store them lowercased so the compare is exact).
- Store the **full address including any `+` alias** (e.g.
  `chris+flights@example.com`). Aliases are matched as-is — `chris@example.com`
  and `chris+flights@example.com` are different entries; add both if both are used.
- A display-name match never counts. `"chris@example.com" <attacker@evil.com>`
  is rejected because only `attacker@evil.com` (the real address) is compared.

### 2. Collect the confirmation phrase(s)
Ask what phrase they'll put at the top of a forward to confirm intent (e.g.
"please add this to my calendar", "put these flights on my calendar"). Store one
or more phrases in `confirmationPhrases`. These are not decorative: on every run
`process-flight-emails` passes this exact list into the sandboxed reader's
dispatch prompt, and the reader decides `confirmationPhrasePresent` by judging
the forwarder's intro line **against these phrases**. Matching is by **meaning**
(close paraphrases count), but it is **seeded from the user's phrases**, not a
hardcoded example — so what the user types here is what actually drives the gate.
Record one or more phrases.

### 3. Choose the target calendar
Call the CalDAV `list-calendars` tool. Show the human-readable calendar names and
ask which one to use (the one shared back to the user, e.g. "AI-Chris"). Store the
chosen calendar's URL **with the `/remote.php/dav` prefix stripped** — e.g. store
`/calendars/AI/chris-ai/`, never `/remote.php/dav/calendars/AI/chris-ai/`. Passing
the unstripped URL makes every event call fail.

### 4. Probe Gmail capabilities
Confirm the connector can list/search messages and add a label. List labels;
if a label named `Calendared` (or the user's chosen name) doesn't exist, note it
will be created on first run. Set `trackingMode` to `label` if labels work,
otherwise fall back to `timestamp` and record `lastRunISO` as now.

### 5. Choose how it runs
Ask: scheduled, manual, or both.
- If scheduled, set up a recurring task (use the available scheduling mechanism —
  e.g. the `schedule` skill / scheduled-tasks tool) that runs the
  `process-flight-emails` skill on the chosen cadence (default: every morning).
- Always keep manual runs available regardless.

### 6. Write the config file
Write a JSON config to a stable, writable location (default
`~/.config/calendar-from-email/config.json`; create the directory if needed).
Shape:

```json
{
  "allowedSenders": ["chris@example.com", "chris.work@example.com"],
  "confirmationPhrases": ["please add this to my calendar"],
  "calendarUrl": "/calendars/AI/chris-ai/",
  "trackingMode": "label",
  "labelName": "Calendared",
  "lastRunISO": "2026-06-08T00:00:00Z"
}
```

### 7. Confirm
Summarize in plain language what was configured: which senders are trusted, the
confirmation phrase, which calendar events go to, and the schedule. Offer a test:
forward one itinerary, then run `process-flight-emails`.
