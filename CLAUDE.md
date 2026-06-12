# CLAUDE.md — caltitude

Guidance for working on this plugin. The repo root **is** the plugin (this file,
`.claude-plugin/`, `skills/`, `agents/`, `scripts/`, `evals/`, `docs/` all live at
the top level). User-facing overview is in `README.md`; this file is for whoever is
editing the plugin.

## What it is

A Claude Cowork plugin that turns forwarded travel emails (flights, hotels, car
rentals) into Nextcloud calendar events. Three moving parts:

- **`skills/process-flight-emails/SKILL.md`** — the trusted orchestrator. Finds new
  mail, gates on sender + intent, creates events, tags + archives, advances state.
- **`agents/email-event-extractor.md`** — a sandboxed reader subagent. The **only**
  component that reads email bodies. Its only tool is `get_thread` (read-only).
- **`scripts/convert_time.py`** — deterministic date/time math (the LLM must not do
  timezone or date arithmetic itself).

The skills/agent are **instructions for Claude**, not code — correctness lives in
the contracts between them. Keep them precise and mutually consistent.

## Invariants — do not break these

- **Prompt-injection boundary.** The orchestrator must NEVER call `get_thread` or
  otherwise read an email body; it works only from `search_threads` results (IDs,
  `From`, and an untrusted snippet it must not act on). Only the sandboxed reader
  reads bodies, and it has no action tools. If you ever give the orchestrator body
  access or the reader an action tool, you've broken the whole security model.
  **One fresh reader per email, dispatched in parallel** — never a single reader
  shared across emails. The per-email isolation keeps one email's body (incl. an
  injection attempt) from bleeding into another's extraction; collapsing it into a
  shared reader is a regression.
- **Two gates, both required.** An event is created only if (a) the email's real
  `From` address exactly matches the allowlist (parse the angle-bracket address,
  lowercase, exact compare — never substring-match the raw header), AND (b) the
  reader reports calendar-add intent from the forwarder's note. Intent is judged by
  meaning; there is no configured phrase.
- **No LLM date/time math.** Always shell out to `convert_time.py` for UTC/zone
  conversion and date shifting. Adding ad-hoc "the model computes the time" steps is
  a regression.

## Connector facts (verified live — trust these over guesses)

Nextcloud MCP (`mcp__Nextcloud_MCP__*`):
- `nc_calendar_create_event` takes the calendar's **internal `name`** (e.g.
  `chris-ai`), NOT the `display_name` (`AI-Chris`). Setup stores the internal name.
- **One `timezone` per event.** A flight can't carry a departure TZID on the start
  and an arrival TZID on the end. Flights are anchored to the departure zone; the
  arrival end is re-expressed into that zone via `convert_time.py to-zone`.
- **All-day `end_datetime` is EXCLUSIVE.** To show a stay/rental inclusive of the
  checkout/dropoff day, pass `end = inclusive_end + 1 day`
  (`convert_time.py add-days <date> --days 1`). This also makes same-day items valid.
- `nc_webdav_create_directory` is **not recursive** — create each path level in
  order (`.local`, `.local/state`, `.local/state/caltitude`). It returns 409 when a
  parent is missing, 201 on create, 405 if the directory already exists.
- Config/state live in Nextcloud WebDAV, locally stateless:
  `.config/caltitude/config.json`, `.local/state/caltitude/state.json`.

Gmail MCP (`mcp__67d2a7f7-...__*`):
- Thread-oriented: `search_threads` (snippet only, no body), `get_thread` (full
  body), `list_labels` (returns empty when there are no user labels),
  `create_label`, `label_*`/`unlabel_*`.
- The `label:` search operator needs label **IDs**, not display names.
- Archive = remove the `INBOX` label via `unlabel_*` with `labelIds:["INBOX"]`.
- `after:` takes `YYYY/MM/DD` (date granularity is fine — the `caltitude` label +
  archiving prevent same-day reprocessing). Don't use epoch.

The standalone CalDAV connector is **retired** (`docs/caldav-plugin-usage.md` is
historical). Use Nextcloud MCP.

## State / incremental scan

Capture `runStartISO` at the **start** of a run; write it to `state.json` only
**after** the run succeeds (so interrupted runs and mid-run arrivals are never
skipped). Missing `state.json` → first run → scan the whole inbox.

## Testing & building

- `python3 evals/test_convert_time.py` — the only runnable tests (deterministic,
  cover `to-utc`/`to-local`/`to-zone`/`add-days` + DST/date-only edge cases). Keep
  them green; add cases when you change `convert_time.py`.
- `evals/reader_agent_evals.md` + `evals/orchestrator_evals.md` are behavioral specs
  (not auto-run). `evals/expected/*.json` hold expected reader output for the two
  real-email fixtures. If you change the reader schema or event-creation rules,
  update these in the same change.
- Fixtures must contain **no real PII** (`13`/`14` are anonymized real emails; keep
  airports/flight numbers/times/hotel+car names+addresses, scrub names/emails/
  phones/employers/loyalty/record numbers).
- Build: `zip -r /tmp/caltitude.plugin . -x ".git/*" -x "*.plugin" -x
  "docs/*" -x "evals/*" -x "*/__pycache__/*" -x ".gitignore"`. The `.plugin` is a
  gitignored build artifact. **Rebuild + reinstall after changes** — the installed
  plugin does not auto-update from the repo.

## Conventions

- Keep the skills nontechnical-facing where they talk to the user, but precise about
  tool names/fields internally.
- When you change a field name or event-creation rule, trace it across all three of:
  the reader spec, the orchestrator spec, and `evals/expected/*.json`.
- Git: feature work on a branch → PR for the owner (`cadejager`) to merge; never
  push to `main` directly (see the global `~/.claude/CLAUDE.md`).
