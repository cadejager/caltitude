# Evals for `caltitude`

Two layers, matching the plugin's two kinds of risk:

1. **Deterministic unit tests** for the timezone converter — the one piece of
   real code that can silently corrupt every event if it's wrong.
2. **Behavioral / LLM specs** for the sandboxed reader agent and the orchestrator
   skill — the security-critical and correctness-critical parts (prompt-injection
   resistance, allowlist + intent gating, multi-modal extraction, incremental
   scan, dedup) that can't be checked by a plain assertion.

```
evals/
├── README.md                       ← this file
├── test_convert_time.py            ← runnable unit tests: timezone converter (layer 1)
├── test_validate_reader_output.py  ← runnable unit tests: reader-output guard (layer 1)
├── test_overflow_reader.py         ← runnable unit tests: overflow MCP tool (layer 1)
├── reader_agent_evals.md           ← cases for email-event-extractor (layer 2)
├── orchestrator_evals.md           ← cases for process-flight-emails (layer 2)
├── expected/                       ← full expected reader output for the real-email fixtures
└── fixtures/                       ← sample forwarded itineraries (incl. adversarial + real)
```

## Layer 1 — running the deterministic tests

Requires only Python 3.9+ (stdlib `zoneinfo`; the plugin's own dependency).

```bash
# from the plugin root
python3 evals/test_convert_time.py            # timezone converter
python3 evals/test_validate_reader_output.py  # reader-output validator/guard
python3 evals/test_overflow_reader.py         # scoped get_thread-overflow MCP tool
```

`test_overflow_reader.py` covers the bundled overflow tool the reader uses when a
`get_thread` result is too big: its **path-guard** (refuses anything that isn't a
saved `get_thread` result under a `tool-results/` dir — no creds file, no traversal),
its body extraction/compaction (HTML stripped, URLs removed, capped), and the
minimal MCP `initialize`/`tools/list`/`tools/call` handlers.

`test_validate_reader_output.py` covers the deterministic guard the orchestrator
runs on the reader's (untrusted) output: rejecting non-schema/prose output
(second-order injection), dropping items whose shell/date-bound fields are
malformed (e.g. a `depTz` carrying a shell payload), sanitizing free-text, and
dropping smuggled unknown keys.

The tests load `scripts/convert_time.py` by path and call `convert()` /
`parse_input_time()` directly — the same code path the CLI uses — so the
assertions are exact. They cover local↔UTC both directions, the new **`to-zone`**
re-expression (used to anchor a flight's arrival end to its departure zone),
summer/winter DST offsets, the spring-forward gap and fall-back ambiguity
warnings, the RFC-2822 `Date:` header path, `--tz` being ignored when the input
carries an offset, the `now` input, invalid timezone / time handling, and an
overnight timezone-crossing red-eye.

A green run looks like `Ran 55 tests ... OK`. If `scripts/convert_time.py` changes
behavior, update the expected values here in the same PR (the values were derived
from the real script, not assumed).

## Layer 2 — using the behavioral specs

These describe inputs and expected behavior for the LLM components; they are not
auto-runnable here. Each `.md` case has **Setup / Expected / Failure**.

### Reader agent (`reader_agent_evals.md`)
Stage the fixture as a Gmail thread (or mock `get_thread` to return its contents),
dispatch the `email-event-extractor` agent with that `threadId` (its only tool is
the read-only `get_thread`), and grade the returned JSON. The reader emits
`confirmationPhrasePresent` plus `flights`/`hotels`/`cars`. R8–R12 are
prompt-injection tests (weight heavily); R14 is the multi-modal flights+hotel+car
case; R15 the flexible-confirmation case. The two real-email fixtures (13, 14) have
full expected output in `evals/expected/`.

### Orchestrator (`orchestrator_evals.md`)
Run against a test Gmail + Nextcloud (or mocked connectors) using the baseline
config in that file. Verifies the sender allowlist, intent gating, multi-modal
event creation (TZID flights + all-day hotel/car), `caltitude` tagging + INBOX
archiving, the incremental `after:lastRunISO` scan with whole-inbox fallback,
Nextcloud config/state read+write, pagination, and that the orchestrator never
fetches bodies (`get_thread` is the reader's job alone).

### Cross-check
The ISO times asserted in the orchestrator spec come from the real converter and
line up with `test_convert_time.py` and `evals/expected/*.json`. If you change the
converter, re-derive both.

## Fixtures

`fixtures/01`–`12` are synthetic itineraries (incl. the adversarial `06`–`08`,
`12`: "ignore previous instructions", a fake in-body confirmation, a spoofed
in-body `From`, and an HTML-comment smuggled instruction — all inert data).

`fixtures/13`–`14` are built from **real** forwarded emails, **anonymized**: names,
personal/work emails, phone numbers, employer/trip names, loyalty/record/ticket
numbers, and card endings were replaced or removed; airports, flight numbers,
times, hotel name+address, and car company+address were kept. `13` is a 4-segment
American Airlines itinerary; `14` is a Concur trip with flights **+ hotel + car**.

`fixtures/15`–`19` (synthetic, audit round) cover: `15` schema-valid fabricated
JSON injected in the body (passes the validator → the reader is the only defense);
`16` a trusted email with calendar intent but **non-travel** content; `17` a
multi-message **thread** where only one message is the itinerary; `18` a segment
with a **missing year** (inferred from the email Date); `19` a **truncated** second
segment that must be omitted.

Full expected reader output is in `evals/expected/` for the objective cases
(`13`, `14`, `15`, `17`).
