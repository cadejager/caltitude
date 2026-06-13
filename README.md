# caltitude

Forward an itinerary email to a dedicated inbox, and this plugin turns each
flight, hotel, and car rental into an event on your calendar — automatically.

## What it does

1. You forward a travel email (flights, and/or hotel and car rental — e.g. a
   Concur trip) to a dedicated Gmail inbox, adding a short note at the top like
   *"please add these to my calendar"* or *"could you schedule these."*
2. On a schedule (or when you ask), the plugin reads new emails since it last ran,
   checks they came from a sender you trust, and extracts each travel item.
3. It creates events on your Nextcloud calendar: **flights** at their real local
   airport times, **hotels** and **car rentals** as multi-day all-day events. Then
   it tags the email `caltitude` and archives it.

## Setup

Run the **setup-caltitude** skill once. It asks for:

- **Trusted senders** — the addresses you'll forward from, each entered as its own
  field. Only emails from these can ever create events.
- **Target calendar** — picked from your Nextcloud calendar list.
- **Schedule** — run automatically (e.g. each morning), manually, or both.

There is **no fixed confirmation phrase** to configure: just add a short
"add this to my calendar" note when you forward, and the reader recognizes the
intent by meaning.

## Prerequisites

- A **Gmail connector** for the dedicated inbox. (If you just enabled it, restart
  the session so its tools load.)
- **`uv` / `uvx`** installed — it launches the bundled Nextcloud server.
  (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`.)
- **Python 3.9+** (used for exact timezone conversion; standard library only).

**Nextcloud is built in** — the plugin ships its own Nextcloud connector, so there's
nothing separate to install or connect. When you enable the plugin it asks once for
your **Nextcloud URL, username, and an app password** (Nextcloud → Settings →
Security → Devices & sessions). The password is stored securely (your OS keychain).
Because the connector is part of the plugin, it works in **scheduled runs** too —
not just interactive sessions. First launch fetches the server via `uvx`, so the
machine needs network access (and, for a scheduled run, a populated `uv` cache — a
fully offline scheduled run will fail).

> **macOS / Linux only.** The bundled server launches via `/bin/sh`; Windows is not
> currently supported (a plugin's `.mcp.json` has no per-OS command).

> **Upgrading from the Nextcloud desktop extension?** **Disable it.** The bundled
> server and the extension share the same `Nextcloud_MCP` name — if both stay
> enabled they collide, and a scheduled run could bind to the extension (which
> doesn't load in scheduled tasks), reproducing the very failure this fixes.

## Security model

- **Sender allowlist** is the boundary: an event is only ever created if the
  email's `From` (the real address, exact-matched) is a trusted sender.
- **Calendar-add intent** confirms *you* meant to add it — judged by meaning from
  the note you put at the top of the forward.
- **Sandboxed reader**: the only component that reads email *content* has a single
  read-only tool (`get_thread`) and no action tools — no calendar, labeling,
  shell, or file access — so instructions hidden in a body can't cause anything.
  The orchestrator never fetches the body and gates only on the `From` address.
- **Validated reader output**: even the reader's *result* is treated as untrusted —
  the orchestrator runs it through a deterministic validator and uses only the
  normalized, format-checked JSON, so a subverted reader can't smuggle instructions
  or a malformed value back into the trusted orchestrator.

## Storage (Nextcloud, locally stateless)

The plugin keeps nothing on the local machine. In your Nextcloud files:

- `.config/caltitude/config.json` — the trusted senders, calendar name, and label.
- `.local/state/caltitude/state.json` — the last-run timestamp, so each run only
  scans mail newer than the last one (the whole inbox on the very first run).

## How items become events

- **Flights** are stored anchored to the **departure timezone** so the calendar
  shows true local times; the arrival's local time and zone are in the title and
  description. (The Nextcloud connector accepts one timezone per event, so a single
  flight can't carry a different arrival zone on its end — the instant and duration
  are still exact.) Flights get a popup reminder before departure.
- **Hotels** and **car rentals** are single multi-day **all-day** events spanning
  check-in through checkout (and pickup through dropoff) **inclusive**, with the
  exact times in the description and **no** notification.

## Tagging & dedup

Each processed email is labeled `caltitude` and **archived** (removed from the
inbox). Combined with the last-run timestamp, that means nothing is ever processed
or duplicated twice.

## Development

Layout:

| Path | What it is |
| --- | --- |
| `.claude-plugin/plugin.json` | Plugin manifest + `userConfig` (Nextcloud URL/username/app-password) |
| `.mcp.json` | Bundles the Nextcloud MCP server, with credentials from `userConfig` |
| `scripts/run-nextcloud-mcp.sh` / `.cmd` | Launcher that locates `uvx` and starts the Nextcloud server |
| `skills/` | The `setup-caltitude` and `process-flight-emails` skills |
| `agents/email-event-extractor.md` | Sandboxed reader agent (the injection boundary) |
| `scripts/convert_time.py` | Deterministic timezone converter (local↔UTC↔zone) + `add-days` date math |
| `scripts/validate_reader_output.py` | Deterministic guard that validates/normalizes the reader's (untrusted) JSON output |
| `evals/` | Converter + validator unit tests, and reader/orchestrator behavioral specs |
| `docs/` | Notes on the Nextcloud and (historical) CalDAV connectors |

Run the converter tests:

```bash
python3 evals/test_convert_time.py
```

Build the installable plugin package (excludes repo-only files):

```bash
zip -r /tmp/caltitude.plugin . \
  -x ".git/*" -x "*.plugin" -x "docs/*" -x "evals/*" \
  -x "*/__pycache__/*" -x ".gitignore"
```
